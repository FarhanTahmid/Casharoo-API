"""
The tables a client can sync, and who may write to each.

Rows travel as flat dicts keyed by database column name (`cashbook_id`, not
`cashbook`). The same names are used by the client's local database.
"""
from billing.catalog.keys import F
from billing.sync_gates import NO_GATES, Flag, Limit, Lock
from cashbook.models import CashBook, CashBookAdditionalMember, Entry, EntryCategory, PaymentMethod
from ledger_personal.models import Account, Budget, Category, Transaction
from workspaces.models import Membership

SYNC_COLUMNS = ['id', 'workspace_id', 'version', 'server_seq', 'created_at', 'updated_at', 'deleted_at']


class SyncTable:
    #: columns a client may set
    writable = []
    #: columns that cannot change once the row exists
    immutable = []
    #: extra columns sent on pull but never accepted on push
    read_only = []
    #: foreign key column -> (model, must share this other column with the row or None)
    references = {}
    #: what the owner's plan limits here (billing/sync_gates.py), checked on
    #: every create and update. Each table says so itself, NO_GATES included:
    #: a test fails for a table that leaves this unset.
    plan_gates = None

    def __init__(self, name, model):
        self.name = name
        self.model = model

    def to_row(self, obj):
        columns = SYNC_COLUMNS + self.writable + self.read_only
        return {column: getattr(obj, column) for column in columns}

    def visible(self, queryset, user, role):
        """Narrow a workspace's rows to what this member may see."""
        return queryset

    def can_write(self, user, role, obj, op):
        """op is 'create', 'update' or 'delete'. obj already carries the new values."""
        return False


class WorkspaceLevelTable(SyncTable):
    """Personal-ledger tables: only the people who run the workspace."""

    def visible(self, queryset, user, role):
        return queryset if role in Membership.MANAGER_ROLES else queryset.none()

    def can_write(self, user, role, obj, op):
        return role in Membership.MANAGER_ROLES


class CashBookTable(SyncTable):
    writable = ['book_name', 'description', 'currency']
    immutable = ['currency']
    plan_gates = [Limit(F.BUSINESS_CASHBOOKS), Lock(F.BUSINESS_CASHBOOKS)]

    def visible(self, queryset, user, role):
        if role in (*Membership.MANAGER_ROLES, Membership.ROLE_VIEWER):
            return queryset
        return queryset.filter(id__in=accessible_cashbook_ids(user, role))

    def can_write(self, user, role, obj, op):
        if op == 'create':
            return role in Membership.MANAGER_ROLES
        if op == 'delete':
            return role == Membership.ROLE_OWNER
        return obj.has_permission(user, 'edit')


class CashBookChildTable(SyncTable):
    """Rows that hang off a cashbook and follow its per-book permissions."""
    required_permission = 'edit'
    # Read-only together with the book they belong to
    plan_gates = [Lock(F.BUSINESS_CASHBOOKS, target=lambda row: row.cashbook_id)]

    def visible(self, queryset, user, role):
        if role in (*Membership.MANAGER_ROLES, Membership.ROLE_VIEWER):
            return queryset
        return queryset.filter(cashbook__cashbookadditionalmember__member=user,
                               cashbook__cashbookadditionalmember__deleted_at__isnull=True)

    def can_write(self, user, role, obj, op):
        return obj.cashbook.has_permission(user, self.required_permission)


def accessible_cashbook_ids(user, role):
    if role in (*Membership.MANAGER_ROLES, Membership.ROLE_VIEWER):
        return CashBook.all_objects.values('id')
    return CashBookAdditionalMember.objects.filter(member=user).values('cashbook_id')


class EntryCategoryTable(CashBookChildTable):
    writable = ['cashbook_id', 'category_name', 'is_default']
    immutable = ['cashbook_id']
    references = {'cashbook_id': (CashBook, None)}
    required_permission = 'admin'


class PaymentMethodTable(CashBookChildTable):
    writable = ['cashbook_id', 'payment_method_name', 'is_default']
    immutable = ['cashbook_id']
    references = {'cashbook_id': (CashBook, None)}
    required_permission = 'admin'


class EntryTable(CashBookChildTable):
    writable = [
        'cashbook_id', 'category_id', 'payment_method_id', 'entry_type', 'amount_minor',
        'title', 'remarks', 'entry_date', 'source',
    ]
    immutable = ['cashbook_id']
    read_only = ['currency', 'created_by_id']
    references = {
        'cashbook_id': (CashBook, None),
        'category_id': (EntryCategory, 'cashbook_id'),
        'payment_method_id': (PaymentMethod, 'cashbook_id'),
    }


class CashBookMemberTable(CashBookChildTable):
    """Per-book grants. Managed online through the REST API; clients only read them."""
    read_only = ['cashbook_id', 'member_id', 'role']
    # Never written through sync; the REST endpoint that adds a member checks seats
    plan_gates = NO_GATES

    def visible(self, queryset, user, role):
        if role in Membership.MANAGER_ROLES:
            return queryset
        return queryset.filter(member=user)

    def can_write(self, user, role, obj, op):
        return False


class AccountTable(WorkspaceLevelTable):
    writable = ['name', 'kind', 'currency', 'opening_balance_minor', 'is_archived']
    immutable = ['currency']
    plan_gates = [
        # Archived accounts do not count, so bringing one back needs room like a new one
        Limit(F.PERSONAL_ACCOUNTS, counts=lambda account: not account.is_archived),
        # A locked account can still be archived
        Lock(F.PERSONAL_ACCOUNTS, unless=lambda account: account.is_archived),
    ]


class CategoryTable(WorkspaceLevelTable):
    writable = ['name', 'kind']
    # Set by the server on the categories an account starts with
    read_only = ['is_default']
    plan_gates = [
        Limit(F.PERSONAL_CUSTOM_CATEGORIES, counts=lambda category: not category.is_default),
        Lock(F.PERSONAL_CUSTOM_CATEGORIES),
    ]


class TransactionTable(WorkspaceLevelTable):
    writable = [
        'account_id', 'category_id', 'kind', 'amount_minor', 'transfer_group_id',
        'occurred_on', 'note', 'source',
    ]
    read_only = ['currency']
    references = {'account_id': (Account, None), 'category_id': (Category, None)}
    # Read-only together with the account they are on
    plan_gates = [Lock(F.PERSONAL_ACCOUNTS, target=lambda transaction: transaction.account_id)]


class BudgetTable(WorkspaceLevelTable):
    writable = ['category_id', 'amount_minor', 'currency', 'month']
    references = {'category_id': (Category, None)}
    # The recurring budget is for everyone; a different limit for one month is a plan feature
    plan_gates = [Flag(F.BUDGET_MONTH_OVERRIDE, when=lambda budget: budget.month is not None)]


# Parents before children: a push batch is applied in the order sent, and a
# pull is applied by the client in this order.
TABLES = {
    table.name: table for table in [
        CashBookTable('cashbooks', CashBook),
        EntryCategoryTable('entry_categories', EntryCategory),
        PaymentMethodTable('payment_methods', PaymentMethod),
        EntryTable('entries', Entry),
        CashBookMemberTable('cashbook_members', CashBookAdditionalMember),
        AccountTable('accounts', Account),
        CategoryTable('categories', Category),
        TransactionTable('transactions', Transaction),
        BudgetTable('budgets', Budget),
    ]
}
