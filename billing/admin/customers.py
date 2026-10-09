import uuid
from datetime import timedelta

from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import action, display

from workspaces.models import Workspace

from .. import locks, offers, usage
from ..catalog.keys import F, QUOTA
from ..entitlements import explain, forget
from ..models import BillingSettings, EntitlementOverride, Feature, KeepSelection, Subscription, UsageCounter
from ..rules import RULES
from .base import PageMixin, see_tenant_rows
from .forms import CreditsForm, GrantForm, OverrideForm

# The most users one bulk grant may touch; a bigger audience is what a campaign is for
BULK_GRANT_MAX = 500


def billing_url(user_id):
    return reverse('admin:billing_user', args=[user_id])


def user_link(user):
    return format_html('<a href="{}" class="text-primary-600">{}</a>', billing_url(user.pk), user.email)


@admin.register(Subscription)
class SubscriptionAdmin(PageMixin, ModelAdmin):
    list_display = ['user_billing', 'plan', 'source', 'state', 'starts_at', 'current_period_end', 'reason']
    list_filter = ['plan', 'source', 'status', 'cancel_at_period_end']
    search_fields = ['user__email', 'user__username', 'external_id', 'reason']
    date_hierarchy = 'created_at'
    autocomplete_fields = ['user']
    list_select_related = ['user', 'plan']
    readonly_fields = ['provider', 'external_id', 'product', 'campaign', 'promo_code', 'created_by', 'created_at', 'updated_at']
    fieldsets = [
        (None, {'fields': ['user', 'plan', 'source', 'status', 'reason']}),
        ('Period', {'fields': ['starts_at', 'current_period_end', 'cancel_at_period_end']}),
        ('Where it came from', {'fields': ['provider', 'external_id', 'product', 'campaign', 'promo_code', 'created_by', 'created_at', 'updated_at']}),
    ]
    actions = ['revoke_selected']

    @display(description='User', ordering='user__email')
    def user_billing(self, subscription):
        return user_link(subscription.user)

    @display(description='State', label={'live': 'success', 'in grace': 'warning', 'ended': 'info', 'revoked': 'danger', 'not started': 'info'})
    def state(self, subscription):
        if subscription.status == Subscription.STATUS_REVOKED:
            return 'revoked'
        now = timezone.now()
        if subscription.starts_at > now:
            return 'not started'
        live, grace = subscription.is_live(now, timedelta(days=BillingSettings.load().grace_days))
        return 'in grace' if grace else ('live' if live else 'ended')

    def get_readonly_fields(self, request, obj=None):
        # A subscription is a record of what was given to whom; only its end and status change
        if obj is not None:
            return self.readonly_fields + ['user', 'plan', 'source', 'starts_at']
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        return False  # revoke instead, so the record stays

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
            if not obj.source:
                obj.source = Subscription.SOURCE_GRANT
        super().save_model(request, obj, form, change)
        forget()

    @admin.action(description='Revoke the selected subscriptions', permissions=['change'])
    def revoke_selected(self, request, queryset):
        count = 0
        for subscription in queryset.filter(status=Subscription.STATUS_ACTIVE):
            offers.revoke(subscription, f'by {request.user.email}')
            count += 1
        messages.success(request, f'{count} subscription(s) revoked.')

    # ------------------------------------------------------ one user's billing

    def get_urls(self):
        view = self.admin_site.admin_view
        return [
            path('user/<uuid:user_id>/', view(self.user_view), name='billing_user'),
            path('grant/', view(self.bulk_grant_view), name='billing_bulk_grant'),
        ] + super().get_urls()

    def user_view(self, request, user_id):
        """Everything about one user's plan on one page, with the things staff do about it."""
        self.need(request, 'billing.view_subscription')
        user = get_object_or_404(get_user_model(), pk=user_id)
        forms = {
            'grant': GrantForm(user=request.user, prefix='grant'),
            'override': OverrideForm(prefix='override'),
            'credits': CreditsForm(prefix='credits'),
        }
        if request.method == 'POST':
            done = self._user_action(request, user, forms)
            if done:
                return redirect(billing_url(user.pk))

        with see_tenant_rows(request):
            entitlements, rows = explain(user)
            keep = self._keep_states(user, entitlements)
        quotas = [
            {
                'feature': feature,
                **usage.snapshot(user, feature.key, entitlements.limit_of(feature.key)),
            }
            for feature in Feature.objects.filter(kind=QUOTA)
        ]
        for quota in quotas:
            total = None if quota['limit'] is None else quota['limit'] + quota['bonus']
            quota['total'] = total
            quota['percent'] = min(100, round(100 * quota['used'] / total)) if total else 0
        storage = UsageCounter.objects.filter(
            user=user, feature_key=F.STORAGE_ATTACHMENTS_MB.key, period=UsageCounter.LIFETIME,
        ).first()
        now = timezone.now()
        return self.page(
            request, 'billing/admin/user_billing.html', f'Billing: {user.email}',
            subject=user, entitlements=entitlements, rows=rows, quotas=quotas, keep=keep,
            source_label=dict(Subscription.SOURCE_CHOICES).get(entitlements.source, entitlements.source),
            storage_mb=round((storage.used if storage else 0) / (1024 * 1024), 1),
            storage_limit=entitlements.limit_of(F.STORAGE_ATTACHMENTS_MB),
            subscriptions=Subscription.objects.filter(user=user).select_related('plan', 'created_by')[:20],
            overrides=EntitlementOverride.objects.filter(user=user).select_related('feature', 'created_by'),
            forms=forms, now=now,
            can={
                'grant': request.user.has_perm('billing.add_subscription'),
                'revoke': request.user.has_perm('billing.change_subscription'),
                'override': request.user.has_perm('billing.add_entitlementoverride'),
                'remove_override': request.user.has_perm('billing.delete_entitlementoverride'),
                'reset_keep': request.user.has_perm('billing.delete_keepselection'),
            },
            user_change=reverse('admin:identity_appuser_change', args=[user.pk]),
        )

    def _keep_states(self, user, entitlements):
        """What a downgrade locked for this user, with names."""
        owned = list(Workspace.objects.filter(owner=user))
        result = []
        for rule in RULES.values():
            limit = entitlements.limit_of(rule.feature)
            if limit is None:
                continue
            for workspace in (owned if rule.per_workspace else [None]):
                state = locks._state(user, rule, workspace, limit, entitlements.settings.reselect_cooldown_days)
                if not state.over:
                    continue
                queryset = rule.queryset(user, workspace)
                if rule.feature == F.TEAM_SEATS:
                    queryset = queryset.select_related('user')
                labels = {row.pk: rule.label(row) for row in queryset}
                result.append({
                    'feature': rule.feature, 'scope': rule.scope(workspace) if workspace is not None else '',
                    'workspace': workspace, 'limit': limit, 'pending': state.pending,
                    'can_change_at': state.can_change_at,
                    'kept': [labels.get(row_id, row_id) for row_id in state.kept],
                    'locked': [labels.get(row_id, row_id) for row_id in state.ids if row_id in state.locked],
                })
        return result

    def _user_action(self, request, user, forms):
        """Carry out what a button on the user's billing page asked for. True when it was done."""
        what = request.POST.get('action')
        if what == 'grant':
            self.need(request, 'billing.add_subscription')
            form = forms['grant'] = GrantForm(request.POST, user=request.user, prefix='grant')
            if not form.is_valid():
                return False
            data = form.cleaned_data
            subscription = offers.grant(user, data['plan'], days=data['days'], reason=data['reason'], by=request.user)
            self.log_addition(request, subscription, f'Granted {data["plan"].name}: {data["reason"]}')
            messages.success(request, f'{user.email} is on {data["plan"].name} now.')
        elif what == 'override':
            self.need(request, 'billing.add_entitlementoverride')
            form = forms['override'] = OverrideForm(request.POST, prefix='override')
            if not form.is_valid():
                return False
            try:
                override = form.build(user, request.user)
            except ValidationError as error:
                form.add_error(None, error)
                return False
            override.save()
            forget()
            messages.success(request, f'Override added: {override.feature.name}.')
        elif what == 'credits':
            self.need(request, 'billing.add_entitlementoverride')
            form = forms['credits'] = CreditsForm(request.POST, prefix='credits')
            if not form.is_valid():
                return False
            data = form.cleaned_data
            usage.top_up(
                user, data['feature'].key, data['amount'], f'admin:{uuid.uuid4().hex}',
                actor=request.user, ref=data['reason'],
            )
            messages.success(request, f'{data["amount"]} added to {data["feature"].name} for this month.')
        elif what == 'revoke':
            self.need(request, 'billing.change_subscription')
            subscription = get_object_or_404(Subscription, pk=request.POST.get('id'), user=user)
            offers.revoke(subscription, f'by {request.user.email}')
            messages.success(request, 'Subscription revoked.')
        elif what == 'remove_override':
            self.need(request, 'billing.delete_entitlementoverride')
            get_object_or_404(EntitlementOverride, pk=request.POST.get('id'), user=user).delete()
            forget()
            messages.success(request, 'Override removed.')
        elif what == 'reset_keep':
            self.need(request, 'billing.delete_keepselection')
            rule = RULES.get(request.POST.get('feature'))
            if rule is None:
                return False
            workspace = None
            if rule.per_workspace:
                workspace = get_object_or_404(Workspace, pk=request.POST.get('scope'), owner=user)
            locks.reset(user, rule, workspace)
            messages.success(request, 'Their choice was cleared. They can choose again in the app.')
        else:
            return False
        return True

    # ------------------------------------------------------------ bulk grant

    def bulk_grant_view(self, request):
        """Second step of "Grant a plan" on the user list: which plan, how long, why."""
        self.need(request, 'billing.add_subscription')
        ids = request.session.get('billing_bulk_grant') or []
        users = list(get_user_model().objects.filter(pk__in=ids).order_by('email'))
        if not users:
            messages.error(request, 'Select users first, then choose "Grant a plan".')
            return redirect('admin:identity_appuser_changelist')
        form = GrantForm(request.POST or None, user=request.user)
        if request.method == 'POST' and form.is_valid():
            data = form.cleaned_data
            with transaction.atomic():
                for user in users:
                    offers.grant(user, data['plan'], days=data['days'], reason=data['reason'], by=request.user)
            del request.session['billing_bulk_grant']
            messages.success(request, f'{len(users)} user(s) are on {data["plan"].name} now.')
            return redirect('admin:identity_appuser_changelist')
        return self.page(
            request, 'billing/admin/bulk_grant.html', 'Grant a plan', users=users, form=form,
            back=reverse('admin:identity_appuser_changelist'),
        )


@admin.action(description='Grant a plan to the selected users', permissions=['grant_plan'])
def grant_plan_to_selected(modeladmin, request, queryset):
    """For the user list. Sends staff to a page that asks which plan, how long and why."""
    ids = [str(pk) for pk in queryset.values_list('pk', flat=True)[:BULK_GRANT_MAX + 1]]
    if len(ids) > BULK_GRANT_MAX:
        messages.error(
            request,
            f'That is more than {BULK_GRANT_MAX} users. For a large group, start a campaign instead: '
            'it reaches everyone in its audience without one grant per person.',
        )
        return None
    request.session['billing_bulk_grant'] = ids
    return redirect('admin:billing_bulk_grant')


@admin.register(EntitlementOverride)
class EntitlementOverrideAdmin(ModelAdmin):
    list_display = ['user_billing', 'feature', 'mode', 'value', 'starts_at', 'ends_at', 'reason', 'created_by']
    list_filter = ['mode', 'feature']
    search_fields = ['user__email', 'reason']
    autocomplete_fields = ['user', 'feature']
    list_select_related = ['user', 'feature', 'created_by']
    readonly_fields = ['created_by', 'created_at']

    @display(description='User', ordering='user__email')
    def user_billing(self, override):
        return user_link(override.user)

    @display(description='Value')
    def value(self, override):
        if override.feature.kind == 'flag':
            return 'on' if override.enabled else 'off'
        return 'unlimited' if override.unlimited else override.limit

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        forget()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        forget()


@admin.register(KeepSelection)
class KeepSelectionAdmin(ModelAdmin):
    """What users chose to keep editable after a downgrade. Deleting a row lets them choose again."""
    list_display = ['user', 'feature_key', 'scope', 'object_id', 'limit_at_choice', 'chosen_at']
    list_filter = ['feature_key']
    search_fields = ['user__email']
    list_select_related = ['user']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
