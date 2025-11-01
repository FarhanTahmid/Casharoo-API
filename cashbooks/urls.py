from django.urls import path, include
from rest_framework_nested import routers

from .views.cashbook_home_views import CashBookHomeViewSet
from .views.entry_viewset import EntryViewSet
from .views.entry_category_viewset import EntryCategoryViewSet
from .views.payment_method_viewset import PaymentMethodViewSet
from .views.cashbook_stats_viewset import CashBookStatsViewSet

# Main router for cashbook-level resources
# Assuming you have a CashBookViewSet in your main app
router = routers.DefaultRouter()
router.register(r'cashbooks', CashBookHomeViewSet, basename='cashbook')

# Nested router for entries under a cashbook
# URL pattern: /cashbooks/{cashbook_pk}/entries/
cashbook_router = routers.DefaultRouter()

# Register nested routers under cashbook
entries_router = routers.NestedDefaultRouter(
    cashbook_router, 
    r'cashbooks', 
    lookup='cashbook'
)
entries_router.register(
    r'entries', 
    EntryViewSet, 
    basename='cashbook-entries'
)

# Categories router under cashbook
categories_router = routers.NestedDefaultRouter(
    cashbook_router,
    r'cashbooks',
    lookup='cashbook'
)
categories_router.register(
    r'categories',
    EntryCategoryViewSet,
    basename='cashbook-categories'
)

# Payment methods router under cashbook
payment_methods_router = routers.NestedDefaultRouter(
    cashbook_router,
    r'cashbooks',
    lookup='cashbook'
)
payment_methods_router.register(
    r'payment-methods',
    PaymentMethodViewSet,
    basename='cashbook-payment-methods'
)

# Stats router under cashbook
stats_router = routers.NestedDefaultRouter(
    cashbook_router,
    r'cashbooks',
    lookup='cashbook'
)
stats_router.register(
    r'stats',
    CashBookStatsViewSet,
    basename='cashbook-stats'
)

# URL patterns
urlpatterns = [
    # Include nested routers
    path('', include(entries_router.urls)),
    path('', include(categories_router.urls)),
    path('', include(payment_methods_router.urls)),
    path('', include(stats_router.urls)),
]