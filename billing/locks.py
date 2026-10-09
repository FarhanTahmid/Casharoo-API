"""
What stays editable when a user holds more than their plan allows.

Nothing is deleted on a downgrade. The user picks which rows to keep working
with; until they do, the oldest ones are kept. Everything else is read-only
until they upgrade, or delete or archive something.
"""
from dataclasses import dataclass
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .entitlements import cached, forget
from .models import KeepSelection


@dataclass(frozen=True)
class KeepState:
    limit: int | None
    #: Every row that counts, oldest first
    ids: tuple = ()
    kept: tuple = ()
    locked: frozenset = frozenset()
    #: Over the limit and the user has not chosen yet
    pending: bool = False
    can_change_at: object = None

    @property
    def over(self):
        return bool(self.locked)


def _chosen(owner, rule, workspace):
    return list(KeepSelection.objects.filter(
        user=owner, feature_key=rule.feature.key, scope=rule.scope(workspace) if workspace else '',
    ))


def state(owner, rule, workspace, limit, cooldown_days):
    """Which rows of this limit the owner keeps and which are locked. Cached for the request."""
    scope = rule.scope(workspace) if workspace is not None else ''
    return cached(
        ('keep', owner.pk, rule.feature.key, scope),
        lambda: _state(owner, rule, workspace, limit, cooldown_days),
    )


def _state(owner, rule, workspace, limit, cooldown_days):
    if limit is None:
        return KeepState(limit=None)
    ids = tuple(rule.queryset(owner, workspace).order_by('created_at', 'id').values_list('id', flat=True))
    if len(ids) <= limit:
        return KeepState(limit=limit, ids=ids, kept=ids)

    chosen = _chosen(owner, rule, workspace)
    chosen_ids = {choice.object_id for choice in chosen}
    kept = [row_id for row_id in ids if row_id in chosen_ids][:limit]
    # A kept row that was deleted or archived frees its place for the next oldest
    for row_id in ids:
        if len(kept) >= limit:
            break
        if row_id not in kept:
            kept.append(row_id)
    kept_set = set(kept)

    can_change_at = None
    current = [choice for choice in chosen if choice.limit_at_choice == limit]
    if current:
        can_change_at = max(choice.chosen_at for choice in current) + timedelta(days=cooldown_days)
        if can_change_at <= timezone.now():
            can_change_at = None
    return KeepState(
        limit=limit, ids=ids, kept=tuple(row_id for row_id in ids if row_id in kept_set),
        locked=frozenset(ids) - kept_set, pending=not current, can_change_at=can_change_at,
    )


def choose(owner, rule, workspace, limit, cooldown_days, ids, force=False):
    """
    Save which rows the owner keeps. `force` skips the cooldown (staff only).
    Raises ValidationError when the choice is not theirs to make.
    """
    if limit is None:
        raise ValidationError('Nothing needs choosing: this is unlimited on the current plan.')
    if limit == 0:
        raise ValidationError('The current plan does not include any of these.')
    with transaction.atomic():
        forget()
        current = _state(owner, rule, workspace, limit, cooldown_days)
        if not current.over:
            raise ValidationError('Nothing needs choosing: everything fits the current plan.')
        if current.can_change_at is not None and not force:
            raise ValidationError('This choice cannot be changed yet.')
        wanted = list(dict.fromkeys(ids))
        if len(wanted) != limit:
            raise ValidationError(f'Choose exactly {limit}.')
        if not set(wanted) <= set(current.ids):
            raise ValidationError('One of these cannot be chosen.')

        scope = rule.scope(workspace) if workspace is not None else ''
        KeepSelection.objects.filter(user=owner, feature_key=rule.feature.key, scope=scope).delete()
        now = timezone.now()
        for row_id in wanted:
            # One at a time so the signal that tells the app to refresh fires
            KeepSelection.objects.create(
                user=owner, feature_key=rule.feature.key, scope=scope,
                object_id=row_id, limit_at_choice=limit, chosen_at=now,
            )
    forget()


def reset(owner, rule, workspace):
    """Back to "oldest are kept", and the user may choose again at once."""
    scope = rule.scope(workspace) if workspace is not None else ''
    for choice in KeepSelection.objects.filter(user=owner, feature_key=rule.feature.key, scope=scope):
        choice.delete()
    forget()
