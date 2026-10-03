from django.contrib import admin
from .models import Account, Budget, Category, Transaction

SYNC_READONLY = ['id', 'workspace', 'version', 'server_seq', 'created_at', 'updated_at', 'deleted_at']


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'kind', 'currency', 'workspace', 'is_archived']
    list_filter = ['kind', 'currency', 'is_archived']
    search_fields = ['name', 'workspace__owner__email']
    readonly_fields = SYNC_READONLY


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'kind', 'workspace']
    list_filter = ['kind']
    search_fields = ['name', 'workspace__owner__email']
    readonly_fields = SYNC_READONLY


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['occurred_on', 'kind', 'amount_minor', 'currency', 'account', 'category', 'source']
    list_filter = ['kind', 'source', 'occurred_on']
    search_fields = ['note', 'workspace__owner__email']
    readonly_fields = SYNC_READONLY + ['currency']
    date_hierarchy = 'occurred_on'


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ['category', 'amount_minor', 'currency', 'workspace']
    readonly_fields = SYNC_READONLY
