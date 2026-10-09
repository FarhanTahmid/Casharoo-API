"""
Plans, what each plan gives, why a user is on a plan, and what they have used.

None of these tables is tenant data: they belong to a user or to nobody, they
are never synced to a device, and only the admin and billing/ write to them.
"""
import secrets

import pghistory
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import connection, models
from django.db.models import Q
from django.utils import timezone

from .catalog.keys import FLAG, LIMIT, QUOTA

KIND_CHOICES = [(FLAG, 'Flag (on / off)'), (LIMIT, 'Limit (how many at once)'), (QUOTA, 'Quota (how much per month)')]


class Feature(models.Model):
    """One thing a plan can give. System rows mirror billing/catalog/keys.py."""
    key = models.CharField(
        max_length=80, unique=True,
        validators=[RegexValidator(r'^[a-z0-9_]+(\.[a-z0-9_]+)*$', 'Lowercase words joined by dots, like "insights.export".')],
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=FLAG)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')
    unit = models.CharField(max_length=30, blank=True, default='')
    # Declared in code and enforced by the server. Others are passed to the app as they are.
    is_system = models.BooleanField(default=False, editable=False)
    client_visible = models.BooleanField(default=True, help_text='Send this feature to the app.')
    sort = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort', 'key']

    def __str__(self):
        return f"{self.name} ({self.key})"


@pghistory.track()
class Plan(models.Model):
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=60)
    name_bn = models.CharField('name (Bangla)', max_length=60, blank=True, default='')
    tagline = models.CharField(max_length=200, blank=True, default='')
    tagline_bn = models.CharField('tagline (Bangla)', max_length=200, blank=True, default='')
    rank = models.PositiveSmallIntegerField(
        default=0, help_text='Higher wins when a user holds more than one plan, and counts as an upgrade.',
    )
    is_default = models.BooleanField(default=False, help_text='The plan of everyone without a subscription.')
    is_public = models.BooleanField(default=True, help_text='Shown on the upgrade screen.')
    is_active = models.BooleanField(default=True, help_text='Inactive plans cannot be given out; existing holders keep them.')
    sort = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort', 'rank']
        constraints = [
            models.UniqueConstraint(fields=['is_default'], condition=Q(is_default=True), name='one_default_plan'),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.is_default and not self.is_active:
            raise ValidationError({'is_active': 'The default plan must stay active.'})


@pghistory.track()
class PlanFeature(models.Model):
    """What one plan gives for one feature. No row means off, or zero."""
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='values')
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name='plan_values')
    enabled = models.BooleanField(default=False, help_text='For flags.')
    limit = models.PositiveBigIntegerField(null=True, blank=True, help_text='For limits and quotas.')
    unlimited = models.BooleanField(default=False, help_text='For limits and quotas.')

    class Meta:
        ordering = ['feature__sort', 'feature__key']
        constraints = [
            models.UniqueConstraint(fields=['plan', 'feature'], name='one_value_per_plan_feature'),
        ]

    def __str__(self):
        return f"{self.plan.code}: {self.feature.key}"

    def clean(self):
        if self.feature_id is None:
            return
        if self.feature.kind == FLAG:
            self.limit, self.unlimited = None, False
        else:
            self.enabled = False
            if self.unlimited:
                self.limit = None
            elif self.limit is None:
                raise ValidationError({'limit': 'Give a number, or tick unlimited.'})


class Product(models.Model):
    """Something sold in a store that puts the buyer on a plan."""
    PROVIDER_CHOICES = [('play', 'Google Play'), ('app_store', 'App Store'), ('web', 'Web checkout'), ('dev', 'Development')]
    PERIOD_CHOICES = [
        ('monthly', 'Monthly'), ('yearly', 'Yearly'),
        ('pass_30', '30-day pass'), ('pass_365', '365-day pass'), ('lifetime', 'Lifetime'),
    ]
    PERIOD_DAYS = {'monthly': 30, 'yearly': 365, 'pass_30': 30, 'pass_365': 365, 'lifetime': None}

    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    product_id = models.CharField(max_length=100)
    base_plan_id = models.CharField(max_length=100, blank=True, default='')
    offer_id = models.CharField(max_length=100, blank=True, default='')
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='products')
    period = models.CharField(max_length=20, choices=PERIOD_CHOICES)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'product_id', 'base_plan_id'], name='one_product_per_store_id',
            ),
        ]

    def __str__(self):
        return f"{self.provider}:{self.product_id} → {self.plan.code} ({self.period})"


@pghistory.track()
class Subscription(models.Model):
    """One reason a user is on a plan for a while. The best live one decides the plan."""
    SOURCE_STORE = 'store'
    SOURCE_WEB_PASS = 'web_pass'
    SOURCE_GRANT = 'grant'
    SOURCE_PROMO = 'promo_code'
    SOURCE_CAMPAIGN = 'campaign'
    SOURCE_TRIAL = 'trial'
    SOURCE_CHOICES = [
        (SOURCE_STORE, 'Store purchase'), (SOURCE_WEB_PASS, 'Web pass'), (SOURCE_GRANT, 'Granted by staff'),
        (SOURCE_PROMO, 'Promo code'), (SOURCE_CAMPAIGN, 'Campaign'), (SOURCE_TRIAL, 'Trial'),
    ]
    # Paid for, so a late renewal gets a few days before the plan is taken away
    PAID_SOURCES = (SOURCE_STORE, SOURCE_WEB_PASS)

    STATUS_ACTIVE = 'active'
    STATUS_REVOKED = 'revoked'
    STATUS_CHOICES = [(STATUS_ACTIVE, 'Active'), (STATUS_REVOKED, 'Revoked')]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='subscriptions')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    starts_at = models.DateTimeField(default=timezone.now)
    current_period_end = models.DateTimeField(null=True, blank=True, help_text='Empty means it never ends.')
    cancel_at_period_end = models.BooleanField(default=False)

    provider = models.CharField(max_length=20, blank=True, default='')
    external_id = models.CharField(max_length=200, blank=True, default='')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    reason = models.CharField(max_length=300, blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions_given',
    )
    campaign = models.ForeignKey('Campaign', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    promo_code = models.ForeignKey('PromoCode', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'status'])]
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'external_id'], condition=~Q(external_id=''), name='one_subscription_per_external_id',
            ),
        ]

    def __str__(self):
        return f"{self.user_id} on {self.plan.code} ({self.source})"

    def is_live(self, now, grace):
        """(counts now, is in its grace period)"""
        if self.status != self.STATUS_ACTIVE or self.starts_at > now:
            return False, False
        end = self.current_period_end
        if end is None or now < end:
            return True, False
        if self.source in self.PAID_SOURCES and now < end + grace:
            return True, True
        return False, False


@pghistory.track()
class EntitlementOverride(models.Model):
    """A change to one feature for one user, on top of their plan."""
    MODE_RAISE = 'raise'
    MODE_SET = 'set'
    MODE_ADD = 'add'
    MODE_CHOICES = [
        # The safe one: a user who later upgrades is never held below their new plan
        (MODE_RAISE, 'At least this (never less than the plan gives)'),
        (MODE_ADD, 'Add to what the plan gives'),
        (MODE_SET, 'Exactly this, even if the plan gives more'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='entitlement_overrides')
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name='overrides')
    mode = models.CharField(max_length=5, choices=MODE_CHOICES, default=MODE_RAISE)
    enabled = models.BooleanField(default=True, help_text='For flags.')
    limit = models.PositiveBigIntegerField(null=True, blank=True, help_text='For limits and quotas.')
    unlimited = models.BooleanField(default=False, help_text='For limits and quotas.')
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True, help_text='Empty means until removed.')
    reason = models.CharField(max_length=300)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='overrides_given',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['user'])]

    def __str__(self):
        return f"{self.user_id}: {self.mode} {self.feature.key}"

    def clean(self):
        if self.feature_id is None:
            return
        if self.feature.kind == FLAG:
            if self.mode == self.MODE_ADD:
                raise ValidationError({'mode': 'A flag can only be set.'})
            self.limit, self.unlimited = None, False
        elif self.mode == self.MODE_ADD:
            if self.unlimited or not self.limit:
                raise ValidationError({'limit': 'Give the number to add.'})
        elif not self.unlimited and self.limit is None:
            raise ValidationError({'limit': 'Give a number, or tick unlimited.'})
        if self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({'ends_at': 'Must be after the start.'})


class Benefit(models.Model):
    """What a promo code or a campaign gives."""
    BENEFIT_NONE = 'none'
    BENEFIT_PLAN = 'plan'
    BENEFIT_QUOTA = 'quota'
    BENEFIT_STORE_OFFER = 'store_offer'

    benefit_plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, null=True, blank=True, related_name='+', verbose_name='plan',
    )
    benefit_days = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='days', help_text='How long the plan lasts once taken.',
    )
    benefit_feature = models.ForeignKey(
        Feature, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
        limit_choices_to={'kind': QUOTA}, verbose_name='quota',
    )
    benefit_amount = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='amount', help_text='Added to this month, once.',
    )

    class Meta:
        abstract = True

    def clean_benefit(self, kind):
        if kind == self.BENEFIT_PLAN:
            if self.benefit_plan_id is None or not self.benefit_days:
                raise ValidationError('A plan benefit needs a plan and a number of days.')
        elif kind == self.BENEFIT_QUOTA:
            if self.benefit_feature_id is None or not self.benefit_amount:
                raise ValidationError('A quota benefit needs a quota and an amount.')

    def describe_benefit(self, kind):
        if kind == self.BENEFIT_PLAN and self.benefit_plan_id:
            return f"{self.benefit_plan.name} for {self.benefit_days} day{'' if self.benefit_days == 1 else 's'}"
        if kind == self.BENEFIT_QUOTA and self.benefit_feature_id:
            return f"+{self.benefit_amount} {self.benefit_feature.name}"
        return ''


def generate_promo_code():
    # No 0/O or 1/I, so a code read aloud or copied by hand survives
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(secrets.choice(alphabet) for _ in range(12))


@pghistory.track()
class PromoCode(Benefit):
    KIND_CHOICES = [(Benefit.BENEFIT_PLAN, 'A plan for some days'), (Benefit.BENEFIT_QUOTA, 'Extra quota this month')]

    code = models.CharField(max_length=40, unique=True, default=generate_promo_code)
    note = models.CharField(max_length=200, blank=True, default='', help_text='Who it is for. Not shown to users.')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=Benefit.BENEFIT_PLAN)
    max_redemptions = models.PositiveIntegerField(null=True, blank=True, help_text='Empty means no cap.')
    redeemed_count = models.PositiveIntegerField(default=0, editable=False)
    only_plans = models.ManyToManyField(
        Plan, blank=True, related_name='+', help_text='Only users currently on one of these. Empty means anyone.',
    )
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    campaign = models.ForeignKey('Campaign', on_delete=models.SET_NULL, null=True, blank=True, related_name='promo_codes')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.code

    @staticmethod
    def normalize(code):
        return ''.join(str(code or '').split()).upper()

    def clean(self):
        self.code = self.normalize(self.code)
        if len(self.code) < 6:
            raise ValidationError({'code': 'Use at least 6 characters.'})
        self.clean_benefit(self.kind)

    def save(self, *args, **kwargs):
        self.code = self.normalize(self.code)
        super().save(*args, **kwargs)


class PromoRedemption(models.Model):
    promo_code = models.ForeignKey(PromoCode, on_delete=models.CASCADE, related_name='redemptions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='promo_redemptions')
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['promo_code', 'user'], name='one_redemption_per_user_per_code'),
        ]


@pghistory.track()
class Campaign(Benefit):
    """A time-boxed offer for a group of users, shown in the app."""
    AUDIENCE_EVERYONE = 'everyone'
    AUDIENCE_PLANS = 'plans'
    AUDIENCE_USERS = 'users'
    AUDIENCE_CHOICES = [
        (AUDIENCE_EVERYONE, 'Everyone'), (AUDIENCE_PLANS, 'Users on chosen plans'), (AUDIENCE_USERS, 'Chosen users'),
    ]
    KIND_CHOICES = [
        (Benefit.BENEFIT_NONE, 'Message only'),
        (Benefit.BENEFIT_PLAN, 'A plan for some days'),
        (Benefit.BENEFIT_QUOTA, 'Extra quota this month'),
        (Benefit.BENEFIT_STORE_OFFER, 'A store offer (discount set up in the store)'),
    ]
    PLACEMENT_CHOICES = [
        ('home_banner', 'Banner on the home screen'),
        ('upgrade_sheet', 'On the upgrade sheet'),
        ('plan_screen', 'On the Plan screen'),
    ]
    PLACEMENTS = [value for value, _ in PLACEMENT_CHOICES]

    slug = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=100, help_text='For staff. Not shown to users.')
    is_active = models.BooleanField(default=False)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()
    priority = models.IntegerField(default=0, help_text='Higher shows first.')

    audience = models.CharField(max_length=10, choices=AUDIENCE_CHOICES, default=AUDIENCE_EVERYONE)
    audience_plans = models.ManyToManyField(Plan, blank=True, related_name='+')
    audience_users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='+')
    joined_after = models.DateTimeField(null=True, blank=True, help_text='Only accounts created after this.')
    joined_before = models.DateTimeField(null=True, blank=True, help_text='Only accounts created before this.')

    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=Benefit.BENEFIT_NONE)
    auto_apply = models.BooleanField(
        default=False,
        help_text='Everyone in the audience gets a plan benefit while the campaign runs, without tapping anything.',
    )
    store_offer_id = models.CharField(max_length=100, blank=True, default='')
    max_claims = models.PositiveIntegerField(null=True, blank=True, help_text='Empty means no cap.')
    claimed_count = models.PositiveIntegerField(default=0, editable=False)

    placements = models.JSONField(default=list, blank=True)
    title = models.CharField(max_length=80)
    title_bn = models.CharField('title (Bangla)', max_length=80, blank=True, default='')
    body = models.CharField(max_length=240, blank=True, default='')
    body_bn = models.CharField('body (Bangla)', max_length=240, blank=True, default='')
    cta = models.CharField('button', max_length=30, blank=True, default='')
    cta_bn = models.CharField('button (Bangla)', max_length=30, blank=True, default='')

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', '-starts_at']

    def __str__(self):
        return self.name

    def clean(self):
        if self.ends_at and self.starts_at and self.ends_at <= self.starts_at:
            raise ValidationError({'ends_at': 'Must be after the start.'})
        if not isinstance(self.placements, list) or any(p not in self.PLACEMENTS for p in self.placements):
            raise ValidationError({'placements': f'Choose from: {", ".join(self.PLACEMENTS)}.'})
        self.clean_benefit(self.kind)
        if self.kind == self.BENEFIT_STORE_OFFER and not self.store_offer_id:
            raise ValidationError({'store_offer_id': 'Give the offer id set up in the store.'})
        if self.auto_apply and self.kind != self.BENEFIT_PLAN:
            raise ValidationError({'auto_apply': 'Only a plan benefit can apply by itself.'})

    def is_running(self, now):
        return self.is_active and self.starts_at <= now < self.ends_at


class CampaignClaim(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='claims')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='campaign_claims')
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['campaign', 'user'], name='one_claim_per_user_per_campaign'),
        ]


class UsageCounter(models.Model):
    """How much of a quota the user has used in one period. `user` is who pays: a workspace's owner."""
    LIFETIME = 'lifetime'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='usage_counters')
    feature_key = models.CharField(max_length=80)
    period = models.CharField(max_length=10, help_text='YYYY-MM, or "lifetime".')
    used = models.PositiveBigIntegerField(default=0)
    # Extra allowance for this period only: top-ups, promo codes, rewarded ads
    bonus = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'feature_key', 'period'], name='one_counter_per_user_feature_period'),
        ]

    def __str__(self):
        return f"{self.user_id} {self.feature_key} {self.period}: {self.used}"


class UsageEvent(models.Model):
    """Every change to a counter. The key makes a retried request count once."""
    KIND_CONSUME = 'consume'
    KIND_TOP_UP = 'top_up'
    KIND_CHOICES = [(KIND_CONSUME, 'Used'), (KIND_TOP_UP, 'Top-up')]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='usage_events')
    feature_key = models.CharField(max_length=80)
    period = models.CharField(max_length=10)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_CONSUME)
    amount = models.PositiveBigIntegerField()
    idempotency_key = models.CharField(max_length=120, unique=True)
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    ref = models.CharField(max_length=200, blank=True, default='')
    refunded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'feature_key', 'period'])]


class KeepSelection(models.Model):
    """
    After a downgrade leaves a user with more than a limit allows, the rows
    they chose to keep writable. `scope` is the workspace id for a limit that
    is counted per workspace, otherwise empty.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='keep_selections')
    feature_key = models.CharField(max_length=80)
    scope = models.CharField(max_length=36, blank=True, default='')
    object_id = models.UUIDField()
    # The limit they chose under. A different limit later lets them choose again at once.
    limit_at_choice = models.PositiveBigIntegerField()
    chosen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'feature_key', 'scope', 'object_id'], name='one_keep_per_object'),
        ]


class BillingEvent(models.Model):
    """A message from a payment provider. The unique id makes a replay harmless."""
    STATUS_RECEIVED = 'received'
    STATUS_PROCESSED = 'processed'
    STATUS_FAILED = 'failed'

    provider = models.CharField(max_length=20)
    event_id = models.CharField(max_length=200)
    kind = models.CharField(max_length=60, blank=True, default='')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=10, default=STATUS_RECEIVED)
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['provider', 'event_id'], name='one_event_per_provider_id'),
        ]


class FunnelEvent(models.Model):
    """What led up to an upgrade, or did not: limits hit, upgrade screens seen."""
    KIND_LIMIT_HIT = 'limit_hit'
    KIND_PAYWALL_VIEW = 'paywall_view'
    KIND_UPGRADE_TAP = 'upgrade_tap'
    KIND_REDEEM = 'redeem'
    KIND_CLAIM = 'claim'
    KIND_PURCHASE = 'purchase'
    KIND_CHOICES = [
        (KIND_LIMIT_HIT, 'Limit hit'), (KIND_PAYWALL_VIEW, 'Upgrade screen seen'), (KIND_UPGRADE_TAP, 'Upgrade tapped'),
        (KIND_REDEEM, 'Code redeemed'), (KIND_CLAIM, 'Offer claimed'), (KIND_PURCHASE, 'Purchase'),
    ]
    # What the app is allowed to report
    CLIENT_KINDS = (KIND_PAYWALL_VIEW, KIND_UPGRADE_TAP)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='funnel_events')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    feature_key = models.CharField(max_length=80, blank=True, default='')
    plan_code = models.CharField(max_length=40, blank=True, default='')
    origin = models.CharField(max_length=10, default='server')
    # False when the limit was only logged (enforcement switched to log-only)
    enforced = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['kind', 'created_at'])]


@pghistory.track()
class BillingSettings(models.Model):
    """The one row of switches for the whole billing system."""
    MODE_ENFORCE = 'enforce'
    MODE_LOG_ONLY = 'log_only'
    MODE_OFF = 'off'
    MODE_CHOICES = [
        (MODE_ENFORCE, 'Enforce: refuse what a plan does not allow'),
        (MODE_LOG_ONLY, 'Log only: allow everything, record what would have been refused'),
        (MODE_OFF, 'Off: allow everything'),
    ]

    enforcement_mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=MODE_ENFORCE)
    grace_days = models.PositiveSmallIntegerField(
        default=3, help_text='Days a paid plan stays after its period ends, while the store retries the payment.',
    )
    offline_grace_days = models.PositiveSmallIntegerField(
        default=3, help_text='Days the app trusts its last known plan after expiry while it cannot reach the server.',
    )
    reselect_cooldown_days = models.PositiveSmallIntegerField(
        default=30, help_text='After a downgrade, how often a user may change which items stay editable.',
    )
    warn_at_percent = models.PositiveSmallIntegerField(default=75, help_text='The app warns once a limit is this full.')
    ads_honeymoon_days = models.PositiveSmallIntegerField(default=7, help_text='No ads for this long after sign-up.')
    ads_placements = models.JSONField(
        default=list, blank=True, help_text='Screens that may show a banner, for example ["overview", "accounts"].',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'billing settings'
        verbose_name_plural = 'billing settings'

    def __str__(self):
        return 'Billing settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('The billing settings cannot be deleted.')

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1)[0]


class Stamp(models.Model):
    """
    A counter that moves whenever something that decides entitlements changes:
    'catalog' for plans, features, campaigns and settings, 'user:<id>' for one
    user's subscriptions, overrides and choices. The app compares it after each
    sync to know when to ask for its entitlements again.
    """
    CATALOG = 'catalog'

    scope = models.CharField(max_length=60, unique=True)
    version = models.PositiveBigIntegerField(default=1)

    @staticmethod
    def for_user(user_id):
        return f'user:{user_id}'

    @classmethod
    def bump(cls, scope):
        table = connection.ops.quote_name(cls._meta.db_table)
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {table} (scope, version) VALUES (%s, 1) "
                f"ON CONFLICT (scope) DO UPDATE SET version = {table}.version + 1",
                [scope],
            )

    @classmethod
    def current(cls, user_id):
        versions = dict(
            cls.objects.filter(scope__in=[cls.CATALOG, cls.for_user(user_id)]).values_list('scope', 'version')
        )
        return f"{versions.get(cls.CATALOG, 0)}.{versions.get(cls.for_user(user_id), 0)}"
