from django.contrib import admin
from .models import CRUDLog


@admin.register(CRUDLog)
class CRUDLogAdmin(admin.ModelAdmin):
    list_display = ('id','user', 'action', 'model_name', 'record_ids', 'timestamp')
    search_fields=('user__username','user__email','action','model_name')
    list_filter = ('action', 'model_name')
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]
