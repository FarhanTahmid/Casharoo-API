"""
The record of what each plan gave and when, read from the history that
database triggers keep for PlanFeature, and a way to put a plan back.
"""
from django.contrib.auth import get_user_model
from django.db import transaction

from .entitlements import forget
from .models import Feature, Plan, PlanFeature

VALUE_FIELDS = ('enabled', 'limit', 'unlimited')


def _show(kind, values):
    if values is None:
        return 'not set'
    if kind == 'flag':
        return 'on' if values['enabled'] else 'off'
    return 'unlimited' if values['unlimited'] else str(values['limit'] or 0)


def _events():
    return PlanFeature.pgh_event_model.objects.select_related('pgh_context')


def plan_changes(limit=200, plan=None):
    """Newest first: when, who, which plan and feature, and the value before and after."""
    events = _events().order_by('pgh_created_at', 'pgh_id')
    if plan is not None:
        events = events.filter(plan_id=plan.pk)
    plans = dict(Plan.objects.values_list('id', 'name'))
    features = {feature.id: feature for feature in Feature.objects.all()}

    changes, last = [], {}
    for event in events:
        key = (event.plan_id, event.feature_id)
        values = {name: getattr(event, name) for name in VALUE_FIELDS}
        before = last.get(key)
        last[key] = values
        if before == values:
            continue
        feature = features.get(event.feature_id)
        kind = feature.kind if feature else 'flag'
        metadata = event.pgh_context.metadata if event.pgh_context_id else {}
        changes.append({
            'when': event.pgh_created_at,
            'user_id': metadata.get('user'),
            'plan': plans.get(event.plan_id, '(deleted plan)'),
            'feature': feature.name if feature else '(deleted feature)',
            'before': _show(kind, before),
            'after': _show(kind, values),
        })
    changes = changes[::-1][:limit]

    # The history stores who made a change as the id in text form
    user_ids = {change['user_id'] for change in changes if change['user_id']}
    emails = {str(pk): email for pk, email in get_user_model().objects.filter(pk__in=user_ids).values_list('pk', 'email')}
    for change in changes:
        change['who'] = emails.get(str(change['user_id']), 'system')
    return changes


def plan_values_at(plan, moment):
    """feature id -> values, as the plan stood at `moment`."""
    values = {}
    events = _events().filter(plan_id=plan.pk, pgh_created_at__lte=moment).order_by('pgh_created_at', 'pgh_id')
    for event in events:
        values[event.feature_id] = {name: getattr(event, name) for name in VALUE_FIELDS}
    return values


def restore_plan(plan, moment, dry_run=False):
    """
    Put the plan's values back to what they were at `moment`. A value that did
    not exist then is removed, which turns that feature off for the plan.
    Returns the changes as lines of text.
    """
    then = plan_values_at(plan, moment)
    features = {feature.id: feature for feature in Feature.objects.all()}
    changes = []
    with transaction.atomic():
        for row in PlanFeature.objects.filter(plan=plan).select_related('feature'):
            now = {name: getattr(row, name) for name in VALUE_FIELDS}
            wanted = then.pop(row.feature_id, None)
            if wanted == now:
                continue
            changes.append(f'{row.feature.name}: {_show(row.feature.kind, now)} → {_show(row.feature.kind, wanted)}')
            if dry_run:
                continue
            if wanted is None:
                row.delete()
            else:
                for name, value in wanted.items():
                    setattr(row, name, value)
                row.save()
        for feature_id, wanted in then.items():
            feature = features.get(feature_id)
            if feature is None:
                continue  # the feature itself is gone
            changes.append(f'{feature.name}: not set → {_show(feature.kind, wanted)}')
            if not dry_run:
                PlanFeature.objects.create(plan=plan, feature=feature, **wanted)
    forget()
    return changes
