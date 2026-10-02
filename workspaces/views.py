from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Workspace, Membership
from .serializers import WorkspaceSerializer, MembershipSerializer
from .services import create_workspace, workspaces_for


class WorkspaceViewSet(mixins.ListModelMixin,
                       mixins.RetrieveModelMixin,
                       mixins.CreateModelMixin,
                       mixins.UpdateModelMixin,
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

    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        workspace = self.get_object()
        memberships = workspace.memberships.select_related('user')
        return Response(MembershipSerializer(memberships, many=True).data)
