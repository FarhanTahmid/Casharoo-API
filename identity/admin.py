from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import action
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from billing.admin.customers import grant_plan_to_selected
from .models import AppUser, UserSettings


@admin.register(AppUser)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = ('id','email', 'username', 'first_name', 'last_name', 'is_active', 'date_joined')
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'date_joined')
    search_fields = ('email', 'username', 'first_name', 'last_name')
    ordering = ('-date_joined',)
    actions = [grant_plan_to_selected]
    actions_detail = ['billing']

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('username', 'first_name', 'last_name', 'bio', 'phone', 'profile_picture')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'password1', 'password2'),
        }),
    )

    readonly_fields = ('date_joined', 'last_login')

    @action(description=_('Billing'), icon='credit_card', permissions=['see_billing'])
    def billing(self, request, object_id):
        return redirect(reverse('admin:billing_user', args=[object_id]))

    def has_see_billing_permission(self, request, object_id=None):
        return request.user.has_perm('billing.view_subscription')

    def has_grant_plan_permission(self, request):
        return request.user.has_perm('billing.add_subscription')


@admin.register(UserSettings)
class UserSettingsAdmin(ModelAdmin):
    list_display = ('user', 'get_auto_reports')
    search_fields = ('user__email',)


# Groups hold the "Billing admin" and "Support" roles; same look as the rest
admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass
