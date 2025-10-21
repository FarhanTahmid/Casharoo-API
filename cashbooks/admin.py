from django.contrib import admin
from django.utils.html import format_html
from .models import (
    CashBook, CashBookAdditionalMember, EntryCategory, 
    PaymentMethod, Entry, EntryBills, EntryExtraFields
)


@admin.register(CashBook)
class CashBookAdmin(admin.ModelAdmin):
    list_display = ['id','book_name', 'owner', 'get_balance_display', 'created_at', 'last_edited_at']
    list_filter = ['created_at', 'last_edited_at']
    search_fields = ['book_name', 'owner__email', 'owner__username']
    readonly_fields = ['id', 'created_at', 'last_edited_at', 'get_balance_display']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'owner', 'book_name', 'description')
        }),
        ('Balance', {
            'fields': ('get_balance_display',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'last_edited_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_balance_display(self, obj):
        balance = obj.get_balance()
        balance_float = float(balance)
        color = 'green' if balance_float >= 0 else 'red'

        # Format balance first, then use format_html safely
        formatted_balance = f"{balance_float:.2f}"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            formatted_balance
        )

    get_balance_display.short_description = 'Current Balance'



@admin.register(CashBookAdditionalMember)
class CashBookAdditionalMemberAdmin(admin.ModelAdmin):
    list_display = ['member', 'cashbook', 'role', 'added_by', 'added_at']
    list_filter = ['role', 'added_at']
    search_fields = ['member__email', 'member__username', 'cashbook__book_name']
    readonly_fields = ['id', 'added_at']
    
    fieldsets = (
        ('Member Information', {
            'fields': ('id', 'cashbook', 'member', 'role')
        }),
        ('Metadata', {
            'fields': ('added_by', 'added_at')
        }),
    )


@admin.register(EntryCategory)
class EntryCategoryAdmin(admin.ModelAdmin):
    list_display = ['category_name', 'cashbook', 'is_default', 'created_at']
    list_filter = ['is_default', 'created_at']
    search_fields = ['category_name', 'cashbook__book_name']
    readonly_fields = ['id', 'created_at']
    
    fieldsets = (
        ('Category Information', {
            'fields': ('id', 'cashbook', 'category_name', 'is_default')
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ['payment_method_name', 'cashbook', 'is_default', 'created_at']
    list_filter = ['is_default', 'created_at']
    search_fields = ['payment_method_name', 'cashbook__book_name']
    readonly_fields = ['id', 'created_at']
    
    fieldsets = (
        ('Payment Method Information', {
            'fields': ('id', 'cashbook', 'payment_method_name', 'is_default')
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )


class EntryBillsInline(admin.TabularInline):
    model = EntryBills
    extra = 0
    readonly_fields = ['id', 'uploaded_at']
    fields = ['bill_file', 'uploaded_at']


class EntryExtraFieldsInline(admin.TabularInline):
    model = EntryExtraFields
    extra = 0
    readonly_fields = ['id']
    fields = ['field_name', 'field_value']


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ['title', 'cashbook', 'entry_type', 'amount', 'category', 'payment_method', 'entry_date', 'created_by']
    list_filter = ['entry_type', 'entry_date', 'timestamp', 'category', 'payment_method']
    search_fields = ['title', 'remarks', 'cashbook__book_name', 'created_by__email']
    readonly_fields = ['id', 'timestamp', 'updated_at']
    date_hierarchy = 'entry_date'
    inlines = [EntryBillsInline, EntryExtraFieldsInline]
    
    fieldsets = (
        ('Entry Information', {
            'fields': ('id', 'cashbook', 'title', 'entry_type', 'amount')
        }),
        ('Classification', {
            'fields': ('category', 'payment_method', 'created_by')
        }),
        ('Details', {
            'fields': ('remarks', 'entry_date')
        }),
        ('Timestamps', {
            'fields': ('timestamp', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('cashbook', 'category', 'payment_method', 'created_by')


@admin.register(EntryBills)
class EntryBillsAdmin(admin.ModelAdmin):
    list_display = ['id', 'entry', 'bill_file', 'uploaded_at']
    list_filter = ['uploaded_at']
    search_fields = ['entry__title', 'entry__cashbook__book_name']
    readonly_fields = ['id', 'uploaded_at']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('entry', 'entry__cashbook')


@admin.register(EntryExtraFields)
class EntryExtraFieldsAdmin(admin.ModelAdmin):
    list_display = ['field_name', 'field_value', 'entry']
    search_fields = ['field_name', 'field_value', 'entry__title']
    readonly_fields = ['id']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('entry', 'entry__cashbook')