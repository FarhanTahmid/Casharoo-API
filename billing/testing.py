"""
Shortcuts for tests, in billing and in any app that gates something.

    grant_plan(user, 'plus')
    set_limit(user, F.PERSONAL_ACCOUNTS, 6)
    set_flag(user, F.BUDGET_MONTH_OVERRIDE, True)
    set_mode('log_only')
"""
from .entitlements import forget
from .models import BillingSettings, EntitlementOverride, Feature, Plan, PlanFeature
from .offers import grant


def grant_plan(user, plan_code, days=None, **extra):
    extra.setdefault('reason', 'test')
    return grant(user, Plan.objects.get(code=plan_code), days=days, **extra)


def set_limit(user, feature, limit, mode=EntitlementOverride.MODE_SET):
    """Override a limit or quota for one user. `limit=None` means unlimited."""
    override = EntitlementOverride.objects.create(
        user=user, feature=Feature.objects.get(key=str(feature)), mode=mode,
        limit=limit, unlimited=limit is None, reason='test',
    )
    forget()
    return override


def set_flag(user, feature, enabled, mode=EntitlementOverride.MODE_SET):
    override = EntitlementOverride.objects.create(
        user=user, feature=Feature.objects.get(key=str(feature)), mode=mode, enabled=enabled, reason='test',
    )
    forget()
    return override


def set_plan_value(plan_code, feature, *, enabled=False, limit=None, unlimited=False):
    """Change what a plan gives, the way the admin would."""
    PlanFeature.objects.update_or_create(
        plan=Plan.objects.get(code=plan_code), feature=Feature.objects.get(key=str(feature)),
        defaults={'enabled': enabled, 'limit': limit, 'unlimited': unlimited},
    )
    forget()


def set_mode(mode):
    settings = BillingSettings.load()
    settings.enforcement_mode = mode
    settings.save()
    forget()
    return settings
