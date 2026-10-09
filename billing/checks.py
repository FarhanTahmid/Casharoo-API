from django.core.checks import Error, register
from django.db import DatabaseError


@register()
def default_plan_exists(app_configs, **kwargs):
    """Everyone without a subscription is on the default plan, so there has to be exactly one."""
    from .models import Plan

    try:
        count = Plan.objects.filter(is_default=True).count()
    except DatabaseError:
        return []  # before the first migrate
    if count == 1:
        return []
    return [Error(
        f'billing needs exactly one default plan, found {count}.',
        hint='Run `python manage.py billing_seed`, or tick "is default" on one plan in the admin.',
        id='billing.E001',
    )]
