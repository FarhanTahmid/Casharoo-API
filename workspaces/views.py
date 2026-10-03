from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Workspace, Membership
from .serializers import WorkspaceSerializer, MembershipSerializer
from .services import create_demo_business, create_workspace, workspaces_for
from .tenancy import TenantScopedMixin


class WorkspaceViewSet(TenantScopedMixin,
                       mixins.ListModelMixin,
                       mixins.RetrieveModelMixin,
                       mixins.CreateModelMixin,
                       mixins.UpdateModelMixin,
                       mixins.DestroyModelMixin,
                       viewsets.GenericViewSet):
    """
    Workspaces the user belongs to. Creating one always makes a business
    workspace; the personal workspace is created automatically on sign-up.
    """
    serializer_class = WorkspaceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return workspaces_for(self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workspace = create_workspace(
            owner=request.user,
            name=serializer.validated_data['name'],
            kind=Workspace.KIND_BUSINESS,
            default_currency=serializer.validated_data.get('default_currency', 'BDT'),
        )
        return Response(self.get_serializer(workspace).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        if serializer.instance.role_of(self.request.user) not in Membership.MANAGER_ROLES:
            raise PermissionDenied('Only the owner or an admin can edit this workspace.')
        serializer.save()

    def perform_destroy(self, instance):
        if instance.kind == Workspace.KIND_PERSONAL:
            raise PermissionDenied('The personal workspace cannot be deleted.')
        if instance.owner_id != self.request.user.id:
            raise PermissionDenied('Only the owner can delete this workspace.')
        instance.soft_delete()

    @action(detail=False, methods=['post'])
    def demo(self, request):
        """A sample business with a few weeks of entries, for trying the app out."""
        workspace = create_demo_business(request.user)
        return Response(self.get_serializer(workspace).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        workspace = self.get_object()
        memberships = workspace.memberships.select_related('user')
        return Response(MembershipSerializer(memberships, many=True).data)
