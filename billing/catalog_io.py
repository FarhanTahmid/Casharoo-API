"""Moves the catalog (features, plans and what each plan gives) between databases as JSON."""
from django.core.exceptions import ValidationError
from django.db import transaction

from .catalog.keys import BY_KEY, KINDS
from .entitlements import forget
from .models import Feature, Plan, PlanFeature

FORMAT = 1
PLAN_FIELDS = ['name', 'name_bn', 'tagline', 'tagline_bn', 'rank', 'is_default', 'is_public', 'is_active', 'sort']
FEATURE_FIELDS = ['kind', 'name', 'description', 'unit', 'client_visible', 'sort']
VALUE_FIELDS = ['enabled', 'limit', 'unlimited']


def export():
    return {
        'format': FORMAT,
        'features': [
            {'key': feature.key, **{name: getattr(feature, name) for name in FEATURE_FIELDS}}
            for feature in Feature.objects.order_by('sort', 'key')
        ],
        'plans': [
            {
                'code': plan.code,
                **{name: getattr(plan, name) for name in PLAN_FIELDS},
                'values': {
                    row.feature.key: {name: getattr(row, name) for name in VALUE_FIELDS}
                    for row in plan.values.select_related('feature')
                },
            }
            for plan in Plan.objects.order_by('sort', 'rank')
        ],
    }


def load(data):
    """
    Make the database's catalog match `data`: adds and updates, never deletes
    a plan or a feature. Returns how many rows it wrote. Raises
    ValidationError, having changed nothing, when the data is not usable.
    """
    if not isinstance(data, dict) or data.get('format') != FORMAT:
        raise ValidationError(f'Not a billing catalog export (format {FORMAT}).')
    plans = data.get('plans') or []
    if sum(1 for plan in plans if plan.get('is_default')) != 1:
        raise ValidationError('Exactly one plan must be the default.')

    written = 0
    with transaction.atomic():
        features = {}
        for item in data.get('features') or []:
            key = item['key']
            fields = {name: item[name] for name in FEATURE_FIELDS if name in item}
            known = BY_KEY.get(key)
            if known is not None:
                fields['kind'] = known.kind  # what the code enforces wins
            elif fields.get('kind') not in KINDS:
                raise ValidationError(f'Feature {key}: unknown kind.')
            features[key], _ = Feature.objects.update_or_create(
                key=key, defaults={**fields, 'is_system': known is not None},
            )
            written += 1

        # Clear the old default first: two defaults at once would break the constraint
        Plan.objects.filter(is_default=True).update(is_default=False)
        for item in plans:
            plan, _ = Plan.objects.update_or_create(
                code=item['code'], defaults={name: item[name] for name in PLAN_FIELDS if name in item},
            )
            written += 1
            for key, value in (item.get('values') or {}).items():
                feature = features.get(key) or Feature.objects.filter(key=key).first()
                if feature is None:
                    raise ValidationError(f'Plan {plan.code}: unknown feature {key}.')
                row = PlanFeature(plan=plan, feature=feature, **{name: value.get(name) for name in VALUE_FIELDS})
                row.enabled, row.unlimited = bool(row.enabled), bool(row.unlimited)
                row.clean()
                PlanFeature.objects.update_or_create(
                    plan=plan, feature=feature,
                    defaults={name: getattr(row, name) for name in VALUE_FIELDS},
                )
                written += 1
    forget()
    return written
