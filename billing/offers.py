"""
The ways a user gets something beyond their plan without buying it: a grant
from staff, a promo code, a campaign.
"""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import F as Col
from django.utils import timezone

from . import usage
from .entitlements import campaign_matches, forget, resolve, running_campaigns
from .models import Benefit, Campaign, CampaignClaim, FunnelEvent, PromoCode, PromoRedemption, Subscription


class OfferError(Exception):
    """Why a code or an offer could not be taken. The message is safe to show."""


# One answer for a code that never existed, ran out or expired, so guessing learns nothing
BAD_CODE = 'This code is not valid.'


def grant(user, plan, *, days=None, until=None, source=Subscription.SOURCE_GRANT, reason='', by=None,
          campaign=None, promo_code=None):
    """Put the user on a plan. `days` or `until` bound it; with neither it never ends."""
    if days is not None:
        until = timezone.now() + timedelta(days=days)
    subscription = Subscription.objects.create(
        user=user, plan=plan, source=source, current_period_end=until, reason=reason,
        created_by=by, campaign=campaign, promo_code=promo_code,
    )
    forget()
    return subscription


def revoke(subscription, reason=''):
    subscription.status = Subscription.STATUS_REVOKED
    if reason:
        subscription.reason = f'{subscription.reason} | revoked: {reason}'.strip(' |')[:300]
    subscription.save(update_fields=['status', 'reason', 'updated_at'])
    forget()


def _give(holder, kind, user, *, source, reason, key):
    """Hand out what a promo code or a campaign carries. Returns the subscription, if it made one."""
    if kind == Benefit.BENEFIT_PLAN:
        return grant(
            user, holder.benefit_plan, days=holder.benefit_days, source=source, reason=reason,
            campaign=holder if isinstance(holder, Campaign) else None,
            promo_code=holder if isinstance(holder, PromoCode) else None,
        )
    if kind == Benefit.BENEFIT_QUOTA:
        usage.top_up(user, holder.benefit_feature.key, holder.benefit_amount, key, ref=reason)
    return None


def redeem(user, code):
    """Redeem a promo code for the user. Returns the PromoCode. Raises OfferError."""
    now = timezone.now()
    plan = resolve(user).plan
    with transaction.atomic():
        promo = PromoCode.objects.select_for_update().filter(code=PromoCode.normalize(code)).first()
        if promo is None or not promo.is_active or promo.starts_at > now or (promo.ends_at and promo.ends_at <= now):
            raise OfferError(BAD_CODE)
        if promo.max_redemptions is not None and promo.redeemed_count >= promo.max_redemptions:
            raise OfferError(BAD_CODE)
        if PromoRedemption.objects.filter(promo_code=promo, user=user).exists():
            raise OfferError('You have already used this code.')
        allowed = set(promo.only_plans.values_list('id', flat=True))
        if allowed and plan.id not in allowed:
            raise OfferError('This code cannot be used with your current plan.')

        subscription = _give(
            promo, promo.kind, user, source=Subscription.SOURCE_PROMO,
            reason=f'promo code {promo.code}', key=f'promo:{promo.pk}:{user.pk}',
        )
        PromoRedemption.objects.create(promo_code=promo, user=user, subscription=subscription)
        PromoCode.objects.filter(pk=promo.pk).update(redeemed_count=Col('redeemed_count') + 1)
        FunnelEvent.objects.create(user=user, kind=FunnelEvent.KIND_REDEEM, plan_code=plan.code)
    forget()
    return promo


def offers_for(user, entitlements, now=None):
    """Running campaigns the user is in the audience of, most important first, with their claim state."""
    now = now or timezone.now()
    # Someone lifted by a campaign is still in the audience their own plan put them in
    held_plan = entitlements.plan
    campaigns = running_campaigns(now)
    if entitlements.source == 'campaign':
        held_plan = _plan_without_campaigns(user, now)
    matching = [campaign for campaign in campaigns if campaign_matches(campaign, user, held_plan)]
    claimed = set(
        CampaignClaim.objects.filter(user=user, campaign__in=matching).values_list('campaign_id', flat=True)
    )
    return [(campaign, campaign.pk in claimed) for campaign in matching]


def _plan_without_campaigns(user, now):
    from .entitlements import default_plan

    best = default_plan()
    grace = timedelta(days=resolve(user).settings.grace_days)
    for subscription in Subscription.objects.filter(user=user, status=Subscription.STATUS_ACTIVE).select_related('plan'):
        if subscription.is_live(now, grace)[0] and subscription.plan.rank > best.rank:
            best = subscription.plan
    return best


def claimable(campaign, claimed):
    if claimed or campaign.auto_apply or campaign.kind not in (Benefit.BENEFIT_PLAN, Benefit.BENEFIT_QUOTA):
        return False
    return campaign.max_claims is None or campaign.claimed_count < campaign.max_claims


def claim(user, slug):
    """Take what a campaign offers, once. Returns the Campaign. Raises OfferError."""
    now = timezone.now()
    entitlements = resolve(user)
    gone = OfferError('This offer is no longer available.')
    with transaction.atomic():
        campaign = Campaign.objects.select_for_update().filter(slug=slug).first()
        if campaign is None or not campaign.is_running(now):
            raise gone
        if not any(found.pk == campaign.pk for found, _ in offers_for(user, entitlements, now)):
            raise gone
        if CampaignClaim.objects.filter(campaign=campaign, user=user).exists():
            raise OfferError('You have already taken this offer.')
        if not claimable(campaign, claimed=False):
            raise gone
        subscription = _give(
            campaign, campaign.kind, user, source=Subscription.SOURCE_CAMPAIGN,
            reason=f'campaign {campaign.slug}', key=f'campaign:{campaign.pk}:{user.pk}',
        )
        try:
            with transaction.atomic():
                CampaignClaim.objects.create(campaign=campaign, user=user, subscription=subscription)
        except IntegrityError:
            raise OfferError('You have already taken this offer.')
        Campaign.objects.filter(pk=campaign.pk).update(claimed_count=Col('claimed_count') + 1)
        FunnelEvent.objects.create(user=user, kind=FunnelEvent.KIND_CLAIM, plan_code=entitlements.plan.code)
    forget()
    return campaign
