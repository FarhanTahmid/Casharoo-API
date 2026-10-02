from rest_framework.routers import DefaultRouter

from .views import WorkspaceViewSet

app_name = 'workspaces'

router = DefaultRouter()
router.register(r'', WorkspaceViewSet, basename='workspace')

urlpatterns = router.urls
