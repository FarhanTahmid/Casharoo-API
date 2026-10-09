"""
Loads billing/catalog/defaults.py into the database.

By default it only adds what is missing, so running it again after the admin
changed a limit leaves the change alone. `force` puts every default back.
The models are passed in so a migration can hand over its historical ones.
"""
from .catalog import defaults
from .catalog.keys import ALL, FLAG

DEFAULT_AD_PLACEMENTS = ['overview', 'budgets', 'accounts', 'cashbooks', 'cashbook_report']


def _default_row(plan_code, feature):
    """Field values of the PlanFeature row the defaults describe."""
    value = defaults.value_for(plan_code, feature)
    if feature.kind == FLAG:
        return {'enabled': bool(value), 'limit': None, 'unlimited': False}
    if value == defaults.UNLIMITED:
        return {'enabled': False, 'limit': None, 'unlimited': True}
    return {'enabled': False, 'limit': value, 'unlimited': False}


def _show(row):
    if row['unlimited']:
        return 'unlimited'
    return str(row['limit']) if row['limit'] is not None else ('on' if row['enabled'] else 'off')


def seed(Feature, Plan, PlanFeature, BillingSettings, force=False, dry_run=False):
    """Returns the changes made (or, with dry_run, that would be made) as lines of text."""
    changes = []

    features = {}
    for position, known in enumerate(ALL):
        wanted = {'name': known.name, 'description': known.description, 'unit': known.unit, 'sort': position * 10}
        feature = Feature.objects.filter(key=known.key).first()
        if feature is None:
            changes.append(f'feature {known.key}: add')
            if not dry_run:
                feature = Feature.objects.create(key=known.key, kind=known.kind, is_system=True, **wanted)
        else:
            # The kind is what the code enforces; it is never the admin's to change
            fixed = {'kind': known.kind, 'is_system': True}
            if force:
                fixed.update(wanted)
            different = {name: value for name, value in fixed.items() if getattr(feature, name) != value}
            if different:
                changes.append(f'feature {known.key}: set {", ".join(sorted(different))}')
                if not dry_run:
                    Feature.objects.filter(pk=feature.pk).update(**different)
        features[known.key] = feature

    plans = {}
    for wanted in defaults.PLANS:
        fields = {name: value for name, value in wanted.items() if name != 'code'}
        plan = Plan.objects.filter(code=wanted['code']).first()
        if plan is None:
            changes.append(f'plan {wanted["code"]}: add')
            if not dry_run:
                # Whether it becomes the default is settled below, once
                plan = Plan.objects.create(code=wanted['code'], **{**fields, 'is_default': False})
        elif force:
            different = {
                name: value for name, value in fields.items()
                if name != 'is_default' and getattr(plan, name) != value
            }
            if different:
                changes.append(f'plan {wanted["code"]}: set {", ".join(sorted(different))}')
                if not dry_run:
                    Plan.objects.filter(pk=plan.pk).update(**different)
        plans[wanted['code']] = plan

    for code, plan in plans.items():
        for known in ALL:
            wanted = _default_row(code, known)
            feature = features[known.key]
            row = None
            if plan is not None and feature is not None:
                row = PlanFeature.objects.filter(plan=plan, feature=feature).first()
            if row is None:
                changes.append(f'{code}.{known.key}: add {_show(wanted)}')
                if not dry_run:
                    PlanFeature.objects.create(plan=plan, feature=feature, **wanted)
            elif force:
                current = {name: getattr(row, name) for name in wanted}
                if current != wanted:
                    changes.append(f'{code}.{known.key}: {_show(current)} -> {_show(wanted)}')
                    if not dry_run:
                        PlanFeature.objects.filter(pk=row.pk).update(**wanted)

    default_code = next(plan['code'] for plan in defaults.PLANS if plan['is_default'])
    current_default = Plan.objects.filter(is_default=True).first()
    if current_default is None or (force and current_default.code != default_code):
        changes.append(f'plan {default_code}: make default')
        if not dry_run:
            Plan.objects.filter(is_default=True).update(is_default=False)
            Plan.objects.filter(code=default_code).update(is_default=True)

    if not BillingSettings.objects.filter(pk=1).exists():
        changes.append('settings: add')
        if not dry_run:
            BillingSettings.objects.create(pk=1, ads_placements=DEFAULT_AD_PLACEMENTS)

    return changes


def seed_live(force=False, dry_run=False):
    """Seed with the real models, and tell running apps the catalog moved."""
    from django.db import transaction

    from .entitlements import forget
    from .models import BillingSettings, Feature, Plan, PlanFeature, Stamp

    with transaction.atomic():
        changes = seed(Feature, Plan, PlanFeature, BillingSettings, force=force, dry_run=dry_run)
        if changes and not dry_run:
            Stamp.bump(Stamp.CATALOG)
    forget()
    return changes
