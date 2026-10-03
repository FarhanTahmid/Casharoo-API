from django.db.models.signals import post_save
from django.dispatch import receiver

from workspaces.models import Workspace
from workspaces.tenancy import add_workspace_to_context
from .models import Account, Category


@receiver(post_save, sender=Workspace)
def seed_personal_workspace(sender, instance, created, **kwargs):
    """A new personal workspace starts with a cash account and the usual categories."""
    if not created or kwargs.get('raw') or instance.kind != Workspace.KIND_PERSONAL:
        return
    # The workspace was created in this request, so row-level security has to let it in
    add_workspace_to_context(instance.id)
    Account.objects.create(workspace=instance, name='Cash', kind='cash', currency=instance.default_currency)
    Category.objects.bulk_create(
        [Category(workspace=instance, name=name, kind='expense') for name in Category.DEFAULT_EXPENSE]
        + [Category(workspace=instance, name=name, kind='income') for name in Category.DEFAULT_INCOME]
    )
