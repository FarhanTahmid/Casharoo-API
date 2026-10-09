"""
Metered use: quotas that refill every month (AI credits) and totals that only
grow or shrink (attachment storage).

Counting is one conditional UPDATE, so two requests racing for the last unit
cannot both get it. Every change is an event with a key the caller chooses;
sending the same key again changes nothing.
"""
from datetime import datetime

from django.db import IntegrityError, transaction
from django.db.models import F as Col
from django.db.models.functions import Greatest
from django.utils import timezone

from .models import UsageCounter, UsageEvent


def period_key(now=None):
    return timezone.localtime(now or timezone.now()).strftime('%Y-%m')


def resets_at(now=None):
    local = timezone.localtime(now or timezone.now())
    year, month = (local.year + 1, 1) if local.month == 12 else (local.year, local.month + 1)
    return datetime(year, month, 1, tzinfo=local.tzinfo)


def counter(user, feature, period=None):
    """The counter row, created empty when missing."""
    return UsageCounter.objects.get_or_create(
        user=user, feature_key=str(feature), period=period or period_key(),
    )[0]


def snapshot(user, feature, limit, period=None):
    """Numbers for a meter. `limit` is the plan's allowance, None when unlimited."""
    row = UsageCounter.objects.filter(
        user=user, feature_key=str(feature), period=period or period_key(),
    ).first()
    used, bonus = (row.used, row.bonus) if row else (0, 0)
    return {
        'limit': limit,
        'bonus': bonus,
        'used': used,
        'remaining': None if limit is None else max(limit + bonus - used, 0),
    }


def take(user, feature, amount, key, limit, *, period=None, workspace=None, actor=None, ref=''):
    """
    Count `amount` against the user's allowance. Returns (event, taken): taken
    is False when it did not fit, and then nothing was counted. A key seen
    before returns its first event without counting again.
    """
    if amount <= 0:
        raise ValueError('amount must be positive')
    period = period or period_key()
    try:
        with transaction.atomic():
            earlier = UsageEvent.objects.filter(idempotency_key=key).first()
            if earlier is not None:
                return earlier, True
            row = counter(user, feature, period)
            rows = UsageCounter.objects.filter(pk=row.pk)
            if limit is not None:
                rows = rows.filter(used__lte=Col('bonus') + limit - amount)
            if not rows.update(used=Col('used') + amount, updated_at=timezone.now()):
                return None, False
            event = UsageEvent.objects.create(
                user=user, feature_key=str(feature), period=period, kind=UsageEvent.KIND_CONSUME,
                amount=amount, idempotency_key=key, workspace=workspace, actor=actor, ref=ref,
            )
    except IntegrityError:
        # The same key arrived twice at once and the other one won; this one's count was rolled back
        return UsageEvent.objects.get(idempotency_key=key), True
    return event, True


def give_back(key):
    """Undo a take, once. Unknown and already-refunded keys are ignored."""
    with transaction.atomic():
        event = UsageEvent.objects.select_for_update().filter(
            idempotency_key=key, kind=UsageEvent.KIND_CONSUME, refunded_at__isnull=True,
        ).first()
        if event is None:
            return False
        UsageCounter.objects.filter(
            user_id=event.user_id, feature_key=event.feature_key, period=event.period,
        ).update(used=Greatest(Col('used') - event.amount, 0), updated_at=timezone.now())
        event.refunded_at = timezone.now()
        event.save(update_fields=['refunded_at'])
    return True


def top_up(user, feature, amount, key, *, actor=None, ref='', period=None):
    """Extra allowance for the current period only. Returns False when the key was used before."""
    if amount <= 0:
        raise ValueError('amount must be positive')
    period = period or period_key()
    try:
        with transaction.atomic():
            if UsageEvent.objects.filter(idempotency_key=key).exists():
                return False
            row = counter(user, feature, period)
            UsageCounter.objects.filter(pk=row.pk).update(bonus=Col('bonus') + amount, updated_at=timezone.now())
            UsageEvent.objects.create(
                user=user, feature_key=str(feature), period=period, kind=UsageEvent.KIND_TOP_UP,
                amount=amount, idempotency_key=key, actor=actor, ref=ref,
            )
    except IntegrityError:
        return False  # the same key at the same moment: the other one landed
    return True
