from django.conf import settings
from django.urls import path

from . import views

app_name = 'billing'

urlpatterns = [
    path('entitlements/', views.EntitlementsView.as_view(), name='entitlements'),
    path('plans/', views.PlansView.as_view(), name='plans'),
    path('promo/redeem/', views.PromoRedeemView.as_view(), name='promo-redeem'),
    path('offers/<slug:slug>/claim/', views.OfferClaimView.as_view(), name='offer-claim'),
    path('keep/', views.KeepView.as_view(), name='keep'),
    path('keep/<str:feature>/', views.KeepChoiceView.as_view(), name='keep-choice'),
    path('events/', views.FunnelEventView.as_view(), name='events'),
]

if settings.BILLING_DEV_TOOLS:
    urlpatterns.append(path('dev/simulate/', views.DevSimulateView.as_view(), name='dev-simulate'))
