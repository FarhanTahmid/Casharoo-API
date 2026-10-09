"""
A pretend store for development and tests: purchases happen because you say
so. It only exists where settings.BILLING_DEV_TOOLS is on, which production
settings refuse to start with.
"""
import uuid
from datetime import timedelta

from django.utils import timezone

from ..models import Plan, Product, Subscription
from .base import PaymentProvider, PurchaseState

ACTIONS = ('purchase', 'renew', 'cancel', 'expire', 'refund')


class DevProvider(PaymentProvider):
    name = 'dev'

    def product_for(self, plan_code, period):
        plan = Plan.objects.get(code=plan_code)
        return Product.objects.get_or_create(
            provider=self.name, product_id=plan.code, base_plan_id=period,
            defaults={'plan': plan, 'period': period},
        )[0]

    def simulate(self, user, action, plan_code=None, period='monthly'):
        """Act out one store event for the user. Returns the Subscription it left behind, or None."""
        now = timezone.now()
        current = Subscription.objects.filter(user=user, provider=self.name).order_by('-created_at').first()
        if action == 'purchase':
            product = self.product_for(plan_code, period)
            external_id = f'dev-{uuid.uuid4().hex}'
        elif current is None:
            raise ValueError('There is no development purchase to act on. Send "purchase" first.')
        else:
            product, external_id = current.product, current.external_id

        days = Product.PERIOD_DAYS[product.period]
        ends = None if days is None else now + timedelta(days=days)
        states = {
            'purchase': PurchaseState(external_id, product, ends),
            'renew': PurchaseState(external_id, product, ends),
            'cancel': PurchaseState(
                external_id, product, current.current_period_end if current else ends, cancel_at_period_end=True,
            ),
            # A minute past, so the subscription is in its grace period right away
            'expire': PurchaseState(external_id, product, now - timedelta(minutes=1)),
            'refund': PurchaseState(external_id, product, now, active=False),
        }
        return self.apply_state(
            user, states[action], event_id=f'dev-{uuid.uuid4().hex}', kind=action,
            payload={'action': action, 'plan': product.plan.code, 'period': product.period},
        )
