"""
Tenant context for PostgreSQL row-level security.

Every tenant table has a policy that only shows rows whose workspace_id is in
the session setting `app.workspace_ids`, unless `app.bypass_rls` is 'on'
(see workspaces/rls.py). The settings are managed here:

- A new connection starts in bypass mode, so management commands, the worker
  and the shell see everything.
- TenantContextMiddleware switches every HTTP request to "no workspaces"
  before the view runs. A view that forgets to activate a tenant sees nothing.
- TenantScopedMixin activates the workspaces of the authenticated user.

RLS does not apply to PostgreSQL superusers, so the application must connect
with a role that is not one.
"""
from django.db import connection
from django.db.backends.signals import connection_created
from django.dispatch import receiver


def _set(workspace_ids, bypass):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.workspace_ids', %s, false), set_config('app.bypass_rls', %s, false)",
            [','.join(str(workspace_id) for workspace_id in workspace_ids), 'on' if bypass else 'off'],
        )


def bypass_tenant_context():
    _set([], bypass=True)


def clear_tenant_context():
    _set([], bypass=False)


def activate_tenant_context(user):
    """Limit the connection to the workspaces the user is a member of."""
    from .models import Membership

    if not user or not user.is_authenticated:
        clear_tenant_context()
        return
    workspace_ids = Membership.objects.filter(user=user).values_list('workspace_id', flat=True)
    _set(list(workspace_ids), bypass=False)


def add_workspace_to_context(workspace_id):
    """A workspace created mid-request becomes visible to the rest of the request."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.workspace_ids', true)")
        current = cursor.fetchone()[0] or ''
        ids = [value for value in current.split(',') if value] + [str(workspace_id)]
        cursor.execute("SELECT set_config('app.workspace_ids', %s, false)", [','.join(ids)])


@receiver(connection_created)
def _bypass_on_new_connection(sender, connection, **kwargs):
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'on', false)")


class TenantContextMiddleware:
    """Fail closed: a request sees no tenant rows until a view activates a tenant."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # The Django admin is the only session-authenticated surface
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and user.is_superuser:
            bypass_tenant_context()
        else:
            clear_tenant_context()
        try:
            return self.get_response(request)
        finally:
            bypass_tenant_context()


class TenantScopedMixin:
    """For DRF views that read or write tenant tables."""

    def perform_authentication(self, request):
        super().perform_authentication(request)
        activate_tenant_context(request.user)
