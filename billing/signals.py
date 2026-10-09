"""Moves the stamps the app watches (see models.Stamp) whenever billing data changes."""
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from .models import (
    BillingSettings, Campaign, CampaignClaim, EntitlementOverride, Feature, KeepSelection, Plan,
    PlanFeature, PromoRedemption, Stamp, Subscription,
)

CATALOG_MODELS = (Feature, Plan, PlanFeature, Campaign, BillingSettings)
USER_MODELS = (Subscription, EntitlementOverride, KeepSelection, CampaignClaim, PromoRedemption)


def _catalog_changed(sender, **kwargs):
    if not kwargs.get('raw'):
        Stamp.bump(Stamp.CATALOG)


def _user_changed(sender, instance, **kwargs):
    if not kwargs.get('raw'):
        Stamp.bump(Stamp.for_user(instance.user_id))


for model in CATALOG_MODELS:
    post_save.connect(_catalog_changed, sender=model, dispatch_uid=f'billing_catalog_save_{model.__name__}')
    post_delete.connect(_catalog_changed, sender=model, dispatch_uid=f'billing_catalog_delete_{model.__name__}')

for model in USER_MODELS:
    post_save.connect(_user_changed, sender=model, dispatch_uid=f'billing_user_save_{model.__name__}')
    post_delete.connect(_user_changed, sender=model, dispatch_uid=f'billing_user_delete_{model.__name__}')


@receiver(m2m_changed, sender=Campaign.audience_plans.through)
@receiver(m2m_changed, sender=Campaign.audience_users.through)
def _campaign_audience_changed(sender, action, **kwargs):
    if action in ('post_add', 'post_remove', 'post_clear'):
        Stamp.bump(Stamp.CATALOG)
