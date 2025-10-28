from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views.cashbook_home_views import CashBookHomeViewSet

router=DefaultRouter()
router.register(r'cashbooks', CashBookHomeViewSet, basename='cashbooks')


urlpatterns = [
    path('', include(router.urls)),
]
