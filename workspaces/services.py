from django.db import transaction
from .models import Workspace, Membership
from .tenancy import add_workspace_to_context


def create_workspace(owner, name, kind=Workspace.KIND_BUSINESS, default_currency='BDT', workspace_id=None):
    """Create a workspace together with its owner membership."""
    extra = {'id': workspace_id} if workspace_id else {}
    with transaction.atomic():
        workspace = Workspace.objects.create(
            owner=owner, name=name, kind=kind, default_currency=default_currency, **extra
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


# (days ago, entry type, amount in major units, title, category, payment method)
# About two months, so reports and month-over-month views have something to show
DEMO_ENTRIES = [
    (56, 'cash_in', 15000, 'Opening cash', 'Income', 'Cash'),
    (54, 'cash_out', 6200, 'Stock purchase', 'Other', 'Bank Transfer'),
    (50, 'cash_in', 3600, 'Counter sales', 'Income', 'Cash'),
    (47, 'cash_in', 2100, 'Nagad sales', 'Income', 'Nagad'),
    (44, 'cash_out', 8000, 'Shop rent', 'Housing', 'Bank Transfer'),
    (41, 'cash_out', 720, 'Electricity bill', 'Utilities', 'bKash'),
    (38, 'cash_in', 4800, 'Wholesale order', 'Income', 'Bank Transfer'),
    (35, 'cash_out', 2500, 'Staff wages', 'Personal', 'Cash'),
    (31, 'cash_out', 450, 'Packaging', 'Household Items/Supplies', 'Cash'),
    (28, 'cash_in', 3300, 'Counter sales', 'Income', 'Cash'),
    (24, 'cash_out', 1200, 'Delivery van fuel', 'Transportation', 'Cash'),
    (20, 'cash_in', 2650, 'bKash sales', 'Income', 'bKash'),
    (16, 'cash_out', 5400, 'Stock purchase', 'Other', 'Bank Transfer'),
    (13, 'cash_in', 3000, 'Counter sales', 'Income', 'Cash'),
    (12, 'cash_out', 4500, 'Stock purchase', 'Other', 'Cash'),
    (11, 'cash_in', 3200, 'Counter sales', 'Income', 'Cash'),
    (10, 'cash_in', 1850, 'bKash sales', 'Income', 'bKash'),
    (9, 'cash_out', 600, 'Electricity bill', 'Utilities', 'bKash'),
    (8, 'cash_in', 4100, 'Counter sales', 'Income', 'Cash'),
    (7, 'cash_out', 2500, 'Staff wages', 'Personal', 'Cash'),
    (5, 'cash_in', 2750, 'Counter sales', 'Income', 'Cash'),
    (4, 'cash_out', 350, 'Van fare', 'Transportation', 'Cash'),
    (3, 'cash_in', 5200, 'Wholesale order', 'Income', 'Bank Transfer'),
    (2, 'cash_out', 8000, 'Shop rent', 'Housing', 'Bank Transfer'),
    (1, 'cash_in', 3900, 'Counter sales', 'Income', 'Cash'),
]


def create_demo_business(user):
    """Return the user's demo business, creating it with sample data the first time."""
    # Imported here: cashbook depends on workspaces, not the other way round
    from datetime import timedelta
    from django.utils import timezone
    from cashbook.models import CashBook, Entry, EntryCategory, PaymentMethod

    existing = Workspace.objects.filter(owner=user, is_demo=True).first()
    if existing is not None:
        return existing

    today = timezone.localdate()
    with transaction.atomic():
        workspace = create_workspace(owner=user, name='Demo shop')
        workspace.is_demo = True
        workspace.save(update_fields=['is_demo'])
        book = CashBook.objects.create(
            workspace=workspace, created_by=user, book_name='Shop cash', currency=workspace.default_currency
        )
        categories = {
            name: EntryCategory.objects.create(cashbook=book, category_name=name, is_default=True)
            for name in EntryCategory.GENERAL_CATEGORIES
        }
        methods = {
            name: PaymentMethod.objects.create(cashbook=book, payment_method_name=name, is_default=True)
            for name in PaymentMethod.GENERAL_PAYMENT_METHODS
        }
        for days_ago, entry_type, amount, title, category, method in DEMO_ENTRIES:
            Entry.objects.create(
                cashbook=book, created_by=user, entry_type=entry_type, amount_minor=amount * 100, title=title,
                category=categories[category], payment_method=methods[method],
                entry_date=today - timedelta(days=days_ago),
            )
    return workspace
