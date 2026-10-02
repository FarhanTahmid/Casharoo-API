from django.db import transaction
from .models import Workspace, Membership
from .tenancy import add_workspace_to_context


def create_workspace(owner, name, kind=Workspace.KIND_BUSINESS, default_currency='BDT'):
    """Create a workspace together with its owner membership."""
    with transaction.atomic():
        workspace = Workspace.objects.create(
            owner=owner, name=name, kind=kind, default_currency=default_currency
        )
        Membership.objects.create(workspace=workspace, user=owner, role=Membership.ROLE_OWNER)
    add_workspace_to_context(workspace.id)
    return workspace


def get_personal_workspace(user):
    """Return the user's personal workspace, creating it if it is missing."""
    workspace = Workspace.objects.filter(owner=user, kind=Workspace.KIND_PERSONAL).first()
    if workspace is None:
        workspace = create_workspace(owner=user, name='Personal', kind=Workspace.KIND_PERSONAL)
    return workspace


def workspaces_for(user):
    """Workspaces the user belongs to."""
    return Workspace.objects.filter(
        memberships__user=user, memberships__deleted_at__isnull=True
    ).distinct()
