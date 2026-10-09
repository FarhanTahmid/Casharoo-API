from django.contrib import admin
from unfold.decorators import display

from ..models import BillingEvent, FunnelEvent, UsageCounter, UsageEvent
from .base import ReadOnlyAdmin


@admin.register(FunnelEvent)
class FunnelEventAdmin(ReadOnlyAdmin):
    list_display = ['created_at', 'kind', 'feature_key', 'plan_code', 'user', 'origin', 'enforced']
    list_filter = ['kind', 'feature_key', 'plan_code', 'origin', 'enforced']
    search_fields = ['user__email']
    list_select_related = ['user']
    date_hierarchy = 'created_at'


@admin.register(UsageCounter)
class UsageCounterAdmin(ReadOnlyAdmin):
    list_display = ['user', 'feature_key', 'period', 'used', 'bonus', 'updated_at']
    list_filter = ['feature_key', 'period']
    search_fields = ['user__email']
    list_select_related = ['user']


@admin.register(UsageEvent)
class UsageEventAdmin(ReadOnlyAdmin):
    list_display = ['created_at', 'user', 'kind', 'feature_key', 'amount', 'period', 'refunded', 'ref']
    list_filter = ['kind', 'feature_key']
    search_fields = ['user__email', 'idempotency_key', 'ref']
    list_select_related = ['user']
    date_hierarchy = 'created_at'

    @display(description='Given back', boolean=True)
    def refunded(self, event):
        return event.refunded_at is not None


@admin.register(BillingEvent)
class BillingEventAdmin(ReadOnlyAdmin):
    list_display = ['created_at', 'provider', 'kind', 'user', 'status', 'event_id']
    list_filter = ['provider', 'status', 'kind']
    search_fields = ['event_id', 'user__email']
    list_select_related = ['user']
    date_hierarchy = 'created_at'
