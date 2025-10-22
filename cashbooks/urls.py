from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views.cashbook_views import CashBookViewSet

router=DefaultRouter()
router.register(r'cashbooks', CashBookViewSet, basename='cashbooks')


urlpatterns = [
    path('', include(router.urls)),
]
