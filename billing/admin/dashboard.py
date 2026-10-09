"""The admin's home page: who is on what, what users run into, and what is running."""
import json
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

from .. import usage
from ..catalog.keys import BY_KEY, F
from ..models import BillingSettings, Campaign, FunnelEvent, Plan, PromoRedemption, Subscription, UsageCounter


def environment(request):
    """The badge next to the site name, so nobody edits production thinking it is a test."""
    if settings.DEBUG:
        return ['Development', 'info']
    if getattr(settings, 'STAGING_TUNNEL', False) or any('trycloudflare' in host for host in settings.ALLOWED_HOSTS):
        return ['Staging', 'warning']
    return ['Production', 'danger']


def plan_counts(now):
    """Users on each plan. Whoever has no live subscription is on the default plan."""
    grace = timedelta(days=BillingSettings.load().grace_days)
    best = {}
    subscriptions = Subscription.objects.filter(
        status=Subscription.STATUS_ACTIVE, starts_at__lte=now,
    ).select_related('plan')
    for subscription in subscriptions:
        if not subscription.is_live(now, grace)[0]:
            continue
        current = best.get(subscription.user_id)
        if current is None or subscription.plan.rank > current.rank:
            best[subscription.user_id] = subscription.plan

    plans = list(Plan.objects.order_by('rank'))
    default = next((plan for plan in plans if plan.is_default), None)
    counts = {plan.pk: 0 for plan in plans}
    lifted = 0
    for plan in best.values():
        if default is None or plan.rank > default.rank:
            counts[plan.pk] = counts.get(plan.pk, 0) + 1
            lifted += 1
    total = get_user_model().objects.filter(is_active=True).count()
    if default is not None:
        counts[default.pk] = max(total - lifted, 0)
    return total, [
        {'plan': plan, 'count': counts.get(plan.pk, 0),
         'percent': round(100 * counts.get(plan.pk, 0) / total) if total else 0}
        for plan in plans
    ]


def dashboard_callback(request, context):
    if not request.user.has_perm('billing.view_subscription'):
        return context

    now = timezone.now()
    week, month = now - timedelta(days=7), now - timedelta(days=30)
    billing_settings = BillingSettings.load()
    total, plans = plan_counts(now)

    hits = list(
        FunnelEvent.objects.filter(kind=FunnelEvent.KIND_LIMIT_HIT, created_at__gte=month)
        .values('feature_key').annotate(
            hits=Count('id'), users=Count('user', distinct=True),
            last_week=Count('id', filter=Q(created_at__gte=week)),
        ).order_by('-hits')[:12]
    )
    for hit in hits:
        known = BY_KEY.get(hit['feature_key'])
        hit['name'] = known.name if known else hit['feature_key']

    funnel = dict(
        FunnelEvent.objects.filter(created_at__gte=month).values_list('kind').annotate(count=Count('id'))
    )
    ending = Subscription.objects.filter(
        status=Subscription.STATUS_ACTIVE, current_period_end__gt=now, current_period_end__lte=now + timedelta(days=7),
    ).select_related('user', 'plan').order_by('current_period_end')
    campaigns = Campaign.objects.filter(is_active=True, starts_at__lte=now, ends_at__gt=now)
    credits = UsageCounter.objects.filter(
        feature_key=F.AI_CREDITS.key, period=usage.period_key(now),
    ).aggregate(used=Sum('used'), users=Count('id'))

    context.update({
        'billing': {
            'mode': billing_settings.enforcement_mode,
            'mode_label': billing_settings.get_enforcement_mode_display(),
            'not_enforcing': billing_settings.enforcement_mode != BillingSettings.MODE_ENFORCE,
            'settings_url': reverse('admin:billing_billingsettings_changelist'),
            'total_users': total,
            'paying': sum(row['count'] for row in plans if not row['plan'].is_default),
            'plans': plans,
            'new_subscriptions': Subscription.objects.filter(created_at__gte=week).count(),
            'new_users': get_user_model().objects.filter(date_joined__gte=week).count(),
            'ending': list(ending[:10]),
            'ending_count': ending.count(),
            'hits': hits,
            'hits_chart': json.dumps({
                'labels': [hit['name'] for hit in hits],
                'datasets': [{
                    'label': 'Times refused in 30 days',
                    'data': [hit['hits'] for hit in hits],
                    'backgroundColor': 'var(--color-primary-600)',
                }],
            }),
            'funnel': [
                ('Limits hit', funnel.get(FunnelEvent.KIND_LIMIT_HIT, 0)),
                ('Upgrade screens seen', funnel.get(FunnelEvent.KIND_PAYWALL_VIEW, 0)),
                ('Upgrade taps', funnel.get(FunnelEvent.KIND_UPGRADE_TAP, 0)),
                ('Purchases', funnel.get(FunnelEvent.KIND_PURCHASE, 0)),
                ('Codes redeemed', funnel.get(FunnelEvent.KIND_REDEEM, 0)),
                ('Offers claimed', funnel.get(FunnelEvent.KIND_CLAIM, 0)),
            ],
            'campaigns': list(campaigns[:8]),
            'redemptions': PromoRedemption.objects.filter(created_at__gte=month).count(),
            'credits_used': credits['used'] or 0,
            'credits_users': credits['users'] or 0,
            'links': {
                'matrix': reverse('admin:billing_plan_matrix'),
                'users': reverse('admin:identity_appuser_changelist'),
                'subscriptions': reverse('admin:billing_subscription_changelist'),
                'campaigns': reverse('admin:billing_campaign_changelist'),
                'new_campaign': reverse('admin:billing_campaign_add'),
                'codes': reverse('admin:billing_promocode_generate'),
                'hits': reverse('admin:billing_funnelevent_changelist') + '?kind__exact=limit_hit',
            },
        },
    })
    return context
