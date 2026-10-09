"""
Where paid subscriptions come from.

A provider turns what a store says into Subscription rows. The app never
tells the server it has paid: the server hears it from the provider, and only
through apply_state(). The store provider (RevenueCat) will implement
fetch_state() against the store's own API; the development provider takes the
state as given.
"""
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from ..entitlements import forget
from ..models import BillingEvent, FunnelEvent, Product, Subscription


@dataclass(frozen=True)
class PurchaseState:
    """One subscription as the provider currently reports it."""
    external_id: str
    product: Product
    #: None for a purchase that never ends
    period_end: object
    active: bool = True
    cancel_at_period_end: bool = False


class PaymentProvider:
    name = ''
    source = Subscription.SOURCE_STORE

    def apply_state(self, user, state, event_id, kind='', payload=None):
        """
        Make the user's subscription match `state`. The same event_id applied
        twice changes nothing the second time. Returns the Subscription, or
        None for a replay.
        """
        try:
            with transaction.atomic():
                event = BillingEvent.objects.create(
                    provider=self.name, event_id=event_id, kind=kind, user=user, payload=payload or {},
                )
        except IntegrityError:
            return None

        with transaction.atomic():
            subscription = Subscription.objects.select_for_update().filter(
                provider=self.name, external_id=state.external_id,
            ).first()
            is_new = subscription is None
            if is_new:
                subscription = Subscription(
                    user=user, provider=self.name, external_id=state.external_id, source=self.source,
                )
            elif subscription.user_id != user.pk:
                # A purchase belongs to the account that made it
                event.status, event.error = BillingEvent.STATUS_FAILED, 'purchase belongs to another user'
                event.save(update_fields=['status', 'error'])
                return None
            subscription.plan = state.product.plan
            subscription.product = state.product
            subscription.current_period_end = state.period_end
            subscription.cancel_at_period_end = state.cancel_at_period_end
            subscription.status = Subscription.STATUS_ACTIVE if state.active else Subscription.STATUS_REVOKED
            subscription.save()
            if is_new and state.active:
                FunnelEvent.objects.create(
                    user=user, kind=FunnelEvent.KIND_PURCHASE, plan_code=state.product.plan.code,
                )
            event.status, event.processed_at = BillingEvent.STATUS_PROCESSED, timezone.now()
            event.save(update_fields=['status', 'processed_at'])
        forget()
        return subscription
