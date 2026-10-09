"""
What a user may do right now.

    default plan  ->  best live subscription or running campaign  ->  overrides

A user with no subscription is on the default plan; nothing is stored for
them. A workspace's entitlements are its owner's.
"""
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import timedelta

from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from django.utils import timezone

from .catalog.keys import BY_KEY, FLAG
from .models import BillingSettings, Campaign, EntitlementOverride, Plan, PlanFeature, Subscription

# Filled for the length of one request by EntitlementsCacheMiddleware. Outside
# a request (commands, the shell, the worker) nothing is cached.
_request_cache = ContextVar('billing_request_cache', default=None)


def begin_request_cache():
    return _request_cache.set({})


def end_request_cache(token):
    _request_cache.reset(token)


def forget():
    """Call after changing anything a resolve depends on within a request."""
    cache = _request_cache.get()
    if cache is not None:
        cache.clear()


def forget_counts():
    """Call after rows that count toward a limit were added, removed or archived within a request."""
    cache = _request_cache.get()
    if cache is not None:
        for key in [key for key in cache if isinstance(key, tuple) and key[0] == 'keep']:
            del cache[key]


def cached(key, compute):
    cache = _request_cache.get()
    if cache is None:
        return compute()
    if key not in cache:
        cache[key] = compute()
    return cache[key]


@dataclass(frozen=True)
class Value:
    key: str
    kind: str
    enabled: bool = False
    #: None means unlimited (limits and quotas only)
    limit: int | None = 0

    @property
    def unlimited(self):
        return self.kind != FLAG and self.limit is None

    @property
    def allowed(self):
        """Whether the plan gives this at all."""
        return self.enabled if self.kind == FLAG else (self.limit is None or self.limit > 0)

    def fits(self, total):
        return self.limit is None or total <= self.limit


@dataclass(frozen=True)
class Entitlements:
    user_id: object
    plan: Plan
    #: 'default', a Subscription source, or 'campaign'
    source: str
    expires_at: object = None
    in_grace: bool = False
    subscription_id: int | None = None
    campaign_slug: str = ''
    values: dict = field(default_factory=dict)
    #: feature key -> where its value came from, oldest first
    trace: dict = field(default_factory=dict)
    settings: BillingSettings = None

    def value(self, feature):
        key = str(feature)
        found = self.values.get(key)
        if found is not None:
            return found
        # Nothing says the plan has it: off, or zero
        known = BY_KEY.get(key)
        return Value(key, known.kind if known else FLAG)

    def can(self, feature):
        return self.value(feature).allowed

    def limit_of(self, feature):
        return self.value(feature).limit


def default_plan():
    plan = Plan.objects.filter(is_default=True).first()
    if plan is None:
        raise ImproperlyConfigured('billing has no default plan. Run `python manage.py billing_seed`.')
    return plan


def campaign_matches(campaign, user, plan):
    """Whether the user is in the campaign's audience. Does not look at dates or caps."""
    if campaign.joined_after and user.date_joined < campaign.joined_after:
        return False
    if campaign.joined_before and user.date_joined >= campaign.joined_before:
        return False
    if campaign.audience == Campaign.AUDIENCE_PLANS:
        return plan.id in {p.id for p in campaign.audience_plans.all()}
    if campaign.audience == Campaign.AUDIENCE_USERS:
        return campaign.audience_users.filter(pk=user.pk).exists()
    return True


def running_campaigns(now):
    return list(
        Campaign.objects.filter(is_active=True, starts_at__lte=now, ends_at__gt=now)
        .select_related('benefit_plan', 'benefit_feature').prefetch_related('audience_plans')
    )


def _plan_values(plan):
    values, trace = {}, {}
    for row in PlanFeature.objects.filter(plan=plan).select_related('feature'):
        feature = row.feature
        if feature.kind == FLAG:
            value = Value(feature.key, FLAG, enabled=row.enabled)
        else:
            value = Value(feature.key, feature.kind, limit=None if row.unlimited else (row.limit or 0))
        values[feature.key] = value
        trace[feature.key] = [f'plan {plan.code}: {describe(value)}']
    return values, trace


def describe(value):
    if value.kind == FLAG:
        return 'on' if value.enabled else 'off'
    return 'unlimited' if value.limit is None else str(value.limit)


def _apply_override(values, trace, override):
    feature = override.feature
    current = values.get(feature.key) or Value(feature.key, feature.kind)
    wanted = None if override.unlimited else (override.limit or 0)
    if feature.kind == FLAG:
        enabled = override.enabled or (override.mode == EntitlementOverride.MODE_RAISE and current.enabled)
        new = Value(feature.key, FLAG, enabled=enabled)
    elif override.mode == EntitlementOverride.MODE_ADD:
        new = current if current.limit is None else Value(feature.key, feature.kind, limit=current.limit + wanted)
    elif override.mode == EntitlementOverride.MODE_RAISE and (
        current.limit is None or (wanted is not None and wanted <= current.limit)
    ):
        new = current  # the plan already gives as much
    else:
        new = Value(feature.key, feature.kind, limit=wanted)
    values[feature.key] = new
    trace.setdefault(feature.key, []).append(
        f'override #{override.pk} ({override.mode}, "{override.reason}"): {describe(new)}'
    )


def resolve(user, now=None):
    """The user's entitlements. Cached for the rest of the request."""
    if now is not None:
        return _resolve(user, now)
    return cached(('entitlements', user.pk), lambda: _resolve(user, timezone.now()))


def _resolve(user, now):
    settings = cached('settings', BillingSettings.load)
    grace = timedelta(days=settings.grace_days)

    plan, source, expires_at, in_grace, subscription_id, campaign_slug = default_plan(), 'default', None, False, None, ''
    base_plan = plan

    # (rank, not in grace, ends later) decides between several live subscriptions
    best_key = None
    subscriptions = Subscription.objects.filter(
        user=user, status=Subscription.STATUS_ACTIVE, starts_at__lte=now,
    ).select_related('plan')
    for subscription in subscriptions:
        live, grace_now = subscription.is_live(now, grace)
        if not live or subscription.plan.rank <= base_plan.rank:
            continue
        end = subscription.current_period_end
        key = (subscription.plan.rank, not grace_now, end is None, end or now)
        if best_key is None or key > best_key:
            best_key = key
            plan, source, expires_at, in_grace = subscription.plan, subscription.source, end, grace_now
            subscription_id = subscription.pk

    # A campaign that applies by itself lifts everyone in its audience for as long as it runs.
    # Its audience is judged on the plan the user holds without it.
    held_plan = plan
    for campaign in running_campaigns(now):
        if not campaign.auto_apply or campaign.benefit_plan is None:
            continue
        if campaign.benefit_plan.rank <= plan.rank or not campaign_matches(campaign, user, held_plan):
            continue
        plan, source, expires_at, in_grace = campaign.benefit_plan, 'campaign', campaign.ends_at, False
        subscription_id, campaign_slug = None, campaign.slug

    values, trace = _plan_values(plan)
    overrides = EntitlementOverride.objects.filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=now), user=user, starts_at__lte=now,
    ).select_related('feature').order_by('created_at', 'pk')
    for override in overrides:
        _apply_override(values, trace, override)

    return Entitlements(
        user_id=user.pk, plan=plan, source=source, expires_at=expires_at, in_grace=in_grace,
        subscription_id=subscription_id, campaign_slug=campaign_slug,
        values=values, trace=trace, settings=settings,
    )


def owner_of(workspace):
    return cached(('owner', workspace.pk), lambda: workspace.owner)


def for_workspace(workspace):
    """A workspace runs on its owner's plan, whoever is using it."""
    return resolve(owner_of(workspace))


def explain(user, now=None):
    """Per feature: the value and how it was arrived at. For the admin and `billing_explain`."""
    entitlements = _resolve(user, now or timezone.now())
    keys = sorted(set(BY_KEY) | set(entitlements.values))
    return entitlements, [
        {
            'key': key,
            'value': describe(entitlements.value(key)),
            'steps': entitlements.trace.get(key) or [f'plan {entitlements.plan.code}: not set, so off'],
        }
        for key in keys
    ]
