"""What the app is told about a user's plan. The app only displays this; the server decides again on every write."""
import hashlib
import json
from datetime import timedelta

from django.utils import timezone

from workspaces.models import Workspace

from . import locks, offers, usage
from .catalog.keys import F, FLAG, QUOTA
from .entitlements import resolve
from .models import Benefit, BillingSettings, Feature, Plan, PlanFeature, UsageCounter
from .rules import RULES


def _iso(moment):
    return moment.isoformat() if moment else None


def _plan(plan):
    return {
        'code': plan.code, 'name': plan.name, 'name_bn': plan.name_bn,
        'tagline': plan.tagline, 'tagline_bn': plan.tagline_bn, 'rank': plan.rank,
    }


def _value(value):
    if value.kind == FLAG:
        return {'kind': FLAG, 'enabled': value.enabled}
    return {'kind': value.kind, 'limit': value.limit, 'unlimited': value.limit is None}


def _features(user, entitlements, now):
    result = {}
    for feature in Feature.objects.filter(client_visible=True):
        entry = _value(entitlements.value(feature.key))
        if feature.kind == QUOTA:
            entry.update(usage.snapshot(user, feature.key, entry['limit']))
            entry['resets_at'] = _iso(usage.resets_at(now))
        result[feature.key] = entry
    storage = result.get(F.STORAGE_ATTACHMENTS_MB.key)
    if storage is not None:
        counted = usage.snapshot(user, F.STORAGE_ATTACHMENTS_MB, None, period=UsageCounter.LIFETIME)
        storage['used_bytes'] = counted['used']
    return result


def _locks(user, entitlements):
    """One entry per limit the user is over, saying what stays editable."""
    owned = list(Workspace.objects.filter(owner=user))
    cooldown = entitlements.settings.reselect_cooldown_days
    result = []
    for rule in RULES.values():
        limit = entitlements.limit_of(rule.feature)
        if limit is None:
            continue
        for workspace in (owned if rule.per_workspace else [None]):
            state = locks.state(user, rule, workspace, limit, cooldown)
            if not state.over:
                continue
            result.append({
                'feature': rule.feature.key,
                'scope': rule.scope(workspace) if workspace is not None else '',
                'limit': limit,
                'kept': [str(row_id) for row_id in state.kept],
                'locked': sorted(str(row_id) for row_id in state.locked),
                'pending': state.pending,
                'can_change_at': _iso(state.can_change_at),
            })
    return result


def _benefit(holder, kind):
    if kind == Benefit.BENEFIT_PLAN:
        return {'kind': kind, 'plan': holder.benefit_plan.code, 'days': holder.benefit_days}
    if kind == Benefit.BENEFIT_QUOTA:
        return {'kind': kind, 'feature': holder.benefit_feature.key, 'amount': holder.benefit_amount}
    if kind == Benefit.BENEFIT_STORE_OFFER:
        return {'kind': kind, 'store_offer_id': holder.store_offer_id}
    return {'kind': kind}


def _offers(user, entitlements, now):
    return [
        {
            'slug': campaign.slug,
            'title': campaign.title, 'title_bn': campaign.title_bn,
            'body': campaign.body, 'body_bn': campaign.body_bn,
            'cta': campaign.cta, 'cta_bn': campaign.cta_bn,
            'placements': campaign.placements,
            'ends_at': _iso(campaign.ends_at),
            'benefit': _benefit(campaign, campaign.kind),
            'applied': campaign.auto_apply,
            'claimed': claimed,
            'claimable': offers.claimable(campaign, claimed),
        }
        for campaign, claimed in offers.offers_for(user, entitlements, now)
    ]


def _ads(user, entitlements, now):
    settings = entitlements.settings
    quiet_until = user.date_joined + timedelta(days=settings.ads_honeymoon_days)
    plan_shows_ads = entitlements.can(F.ADS)
    return {
        'enabled': plan_shows_ads and now >= quiet_until,
        # When the app should start showing them, for a new user on a plan with ads
        'starts_at': _iso(quiet_until) if plan_shows_ads and now < quiet_until else None,
        'placements': settings.ads_placements if plan_shows_ads else [],
    }


def build(user, now=None):
    now = now or timezone.now()
    entitlements = resolve(user)
    settings = entitlements.settings
    # With the switch on "log only" or "off" the server refuses nothing, so
    # the app must not refuse or lock anything on its own either
    enforced = settings.enforcement_mode == BillingSettings.MODE_ENFORCE
    body = {
        'enforced': enforced,
        'plan': _plan(entitlements.plan),
        'source': entitlements.source,
        'expires_at': _iso(entitlements.expires_at),
        'in_grace': entitlements.in_grace,
        'offline_grace_days': settings.offline_grace_days,
        'warn_at_percent': settings.warn_at_percent,
        'features': _features(user, entitlements, now),
        'locks': _locks(user, entitlements) if enforced else [],
        'ads': _ads(user, entitlements, now),
        'offers': _offers(user, entitlements, now),
    }
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return {'version': digest, 'server_time': _iso(now), **body}


def plans():
    """Every plan a user can move to, with what it gives, for the upgrade screen."""
    public = list(Plan.objects.filter(is_public=True, is_active=True).order_by('rank'))
    rows = PlanFeature.objects.filter(plan__in=public, feature__client_visible=True).select_related('feature')
    by_plan = {}
    for row in rows:
        feature = row.feature
        entry = (
            {'kind': FLAG, 'enabled': row.enabled} if feature.kind == FLAG
            else {'kind': feature.kind, 'limit': None if row.unlimited else (row.limit or 0), 'unlimited': row.unlimited}
        )
        by_plan.setdefault(row.plan_id, {})[feature.key] = entry
    features = [
        {'key': feature.key, 'kind': feature.kind, 'name': feature.name, 'unit': feature.unit}
        for feature in Feature.objects.filter(client_visible=True)
    ]
    return {
        'features': features,
        'plans': [{**_plan(plan), 'features': by_plan.get(plan.id, {})} for plan in public],
    }
