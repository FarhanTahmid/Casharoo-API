from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from unfold.admin import ModelAdmin

from workspaces.tenancy import bypass_tenant_context, clear_tenant_context


class ReadOnlyAdmin(ModelAdmin):
    """For records the system writes: staff look, nobody edits."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PageMixin:
    """Custom pages inside the admin, with its menu and its look."""

    # For the buttons on these pages. Named methods, not 'app.codename'
    # strings: unfold's system check looks those up in the database, which
    # fails before the first migrate. Buttons on one object also pass its id.
    def has_see_plans_permission(self, request, object_id=None):
        return request.user.has_perm('billing.view_plan')

    def has_add_plans_permission(self, request, object_id=None):
        return request.user.has_perm('billing.add_plan')

    def has_edit_plan_values_permission(self, request, object_id=None):
        return request.user.has_perm('billing.change_planfeature')

    def has_add_codes_permission(self, request, object_id=None):
        return request.user.has_perm('billing.add_promocode')

    def page(self, request, template, title, **context):
        return TemplateResponse(request, template, {
            **self.admin_site.each_context(request),
            'title': title,
            'opts': self.model._meta,
            **context,
        })

    def need(self, request, *permissions):
        if not all(request.user.has_perm(permission) for permission in permissions):
            raise PermissionDenied


class see_tenant_rows:
    """
    Staff who are not superusers see no tenant rows (row-level security).
    Counting a user's accounts or cashbooks for the billing pages needs them,
    so this lifts the restriction for the length of the block.
    """

    def __init__(self, request):
        self.restore = not request.user.is_superuser

    def __enter__(self):
        bypass_tenant_context()

    def __exit__(self, *error):
        if self.restore:
            clear_tenant_context()
