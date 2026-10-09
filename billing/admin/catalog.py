import json

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display

from .. import history, payload
from ..catalog.keys import FLAG
from ..entitlements import forget
from ..models import BillingSettings, Feature, Plan, PlanFeature, Product, Subscription
from .base import PageMixin
from .forms import RestoreForm


@admin.register(Feature)
class FeatureAdmin(ModelAdmin):
    list_display = ['name', 'key', 'kind', 'unit', 'enforced_by', 'client_visible', 'sort']
    list_filter = ['kind', 'is_system', 'client_visible']
    search_fields = ['key', 'name']
    ordering = ['sort', 'key']
    fields = ['key', 'kind', 'name', 'description', 'unit', 'client_visible', 'sort', 'is_system']

    @display(description='Enforced by', label={'the server': 'success', 'the app only': 'info'})
    def enforced_by(self, feature):
        return 'the server' if feature.is_system else 'the app only'

    def get_readonly_fields(self, request, obj=None):
        # What the server enforces is declared in code; renaming it here would switch the check off
        if obj is not None and obj.is_system:
            return ['key', 'kind', 'is_system']
        return ['is_system']

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and not (obj is not None and obj.is_system)


class PlanFeatureInline(TabularInline):
    model = PlanFeature
    extra = 0
    fields = ['feature', 'enabled', 'limit', 'unlimited']
    ordering = ['feature__sort', 'feature__key']
    autocomplete_fields = ['feature']


@admin.register(Plan)
class PlanAdmin(PageMixin, ModelAdmin):
    list_display = ['name', 'code', 'rank', 'default_badge', 'is_public', 'is_active', 'subscribers']
    list_filter = ['is_public', 'is_active']
    search_fields = ['code', 'name']
    ordering = ['sort', 'rank']
    inlines = [PlanFeatureInline]
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = [
        (None, {'fields': ['code', 'name', 'name_bn', 'tagline', 'tagline_bn']}),
        ('How it behaves', {'fields': ['rank', 'is_default', 'is_public', 'is_active', 'sort']}),
        ('Dates', {'fields': ['created_at', 'updated_at'], 'classes': ['collapse']}),
    ]
    actions_list = ['open_matrix', 'open_history']
    actions_detail = ['duplicate', 'restore']

    @display(description='Default', boolean=True)
    def default_badge(self, plan):
        return plan.is_default

    @display(description='Holders with a subscription')
    def subscribers(self, plan):
        return Subscription.objects.filter(plan=plan, status=Subscription.STATUS_ACTIVE).values('user').distinct().count()

    def get_readonly_fields(self, request, obj=None):
        # The code is what subscriptions, products and the app refer to
        return self.readonly_fields + (['code'] if obj is not None else [])

    def has_delete_permission(self, request, obj=None):
        if obj is not None and (obj.is_default or obj.subscriptions.exists()):
            return False  # archive it instead: untick "is active"
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            if obj.is_default:
                # Moving the default is one step for the admin, two for the constraint
                Plan.objects.filter(is_default=True).exclude(pk=obj.pk).update(is_default=False)
            elif not Plan.objects.filter(is_default=True).exclude(pk=obj.pk).exists():
                # Everyone without a subscription is on the default plan: there must always be one
                obj.is_default = True
                messages.warning(
                    request, f'{obj.name} is still the default plan. To change that, tick "is default" on another plan.',
                )
            super().save_model(request, obj, form, change)
        forget()

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        forget()

    def get_urls(self):
        view = self.admin_site.admin_view
        return [
            path('matrix/', view(self.matrix_view), name='billing_plan_matrix'),
            path('history/', view(self.history_view), name='billing_plan_history'),
        ] + super().get_urls()

    @action(description='Plan matrix', icon='grid_on', permissions=['see_plans'])
    def open_matrix(self, request):
        return redirect('admin:billing_plan_matrix')

    @action(description='Change history', icon='history', permissions=['see_plans'])
    def open_history(self, request):
        return redirect('admin:billing_plan_history')

    @action(description='Duplicate', icon='content_copy', permissions=['add_plans'])
    def duplicate(self, request, object_id):
        plan = get_object_or_404(Plan, pk=object_id)
        code = f'{plan.code}-copy'
        number = 2
        while Plan.objects.filter(code=code).exists():
            code, number = f'{plan.code}-copy-{number}', number + 1
        with transaction.atomic():
            copy = Plan.objects.create(
                code=code, name=f'{plan.name} (copy)', name_bn=plan.name_bn, tagline=plan.tagline,
                tagline_bn=plan.tagline_bn, rank=plan.rank, sort=plan.sort + 1,
                # Hidden and unused until it has been looked over
                is_default=False, is_public=False, is_active=True,
            )
            for row in plan.values.all():
                PlanFeature.objects.create(
                    plan=copy, feature=row.feature, enabled=row.enabled, limit=row.limit, unlimited=row.unlimited,
                )
        messages.success(request, f'Copied to "{copy.name}". It is hidden from users until you make it public.')
        return redirect('admin:billing_plan_change', copy.pk)

    @action(description='Restore from history', icon='restore', permissions=['edit_plan_values'])
    def restore(self, request, object_id):
        plan = get_object_or_404(Plan, pk=object_id)
        form = RestoreForm(request.POST or None)
        preview = None
        if request.method == 'POST' and form.is_valid():
            moment = form.cleaned_data['moment']
            if 'confirm' in request.POST:
                changes = history.restore_plan(plan, moment)
                messages.success(request, f'{plan.name} restored: {len(changes)} value(s) changed.')
                return redirect('admin:billing_plan_change', plan.pk)
            preview = history.restore_plan(plan, moment, dry_run=True)
        return self.page(
            request, 'billing/admin/restore.html', f'Restore {plan.name}',
            plan=plan, form=form, preview=preview,
            back=reverse('admin:billing_plan_change', args=[plan.pk]),
        )

    def history_view(self, request):
        self.need(request, 'billing.view_plan')
        return self.page(
            request, 'billing/admin/plan_history.html', 'Plan changes', changes=history.plan_changes(limit=300),
            headers=['When', 'Who', 'Plan', 'Feature', 'Before', 'After'],
        )

    def matrix_view(self, request):
        """Every plan against every feature in one grid, editable in place."""
        self.need(request, 'billing.view_plan')
        can_edit = request.user.has_perm('billing.change_planfeature')
        plans = list(Plan.objects.order_by('rank', 'sort'))
        features = list(Feature.objects.order_by('sort', 'key'))
        rows = {(row.plan_id, row.feature_id): row for row in PlanFeature.objects.all()}

        errors = []
        if request.method == 'POST':
            self.need(request, 'billing.change_planfeature')
            changed = self._save_matrix(request.POST, plans, features, rows, errors)
            if not errors:
                messages.success(request, f'{changed} value(s) changed. They apply to everyone on those plans now.'
                                 if changed else 'Nothing was changed.')
                return redirect('admin:billing_plan_matrix')
            messages.error(request, 'Nothing was saved. ' + ' '.join(errors))

        grid = []
        for feature in features:
            cells = []
            for plan in plans:
                row = rows.get((plan.id, feature.id))
                name = f'v-{plan.id}-{feature.id}'
                if feature.kind == FLAG:
                    value = 'on' if row is not None and row.enabled else ''
                else:
                    value = '' if row is None else ('∞' if row.unlimited else str(row.limit or 0))
                # After a failed save, show what was typed
                if request.method == 'POST':
                    value = request.POST.get(name, '')
                cells.append({'name': name, 'value': value})
            grid.append({'feature': feature, 'is_flag': feature.kind == FLAG, 'cells': cells})
        return self.page(
            request, 'billing/admin/matrix.html', 'Plan matrix', plans=plans, grid=grid, can_edit=can_edit,
        )

    def _save_matrix(self, data, plans, features, rows, errors):
        """Apply the posted grid. Everything or nothing: any error leaves the database as it was."""
        wanted = []
        for feature in features:
            for plan in plans:
                raw = (data.get(f'v-{plan.id}-{feature.id}') or '').strip()
                if feature.kind == FLAG:
                    values = {'enabled': raw == 'on', 'limit': None, 'unlimited': False}
                elif raw.lower() in ('∞', 'unlimited', 'inf', '*'):
                    values = {'enabled': False, 'limit': None, 'unlimited': True}
                elif raw.isdigit():
                    values = {'enabled': False, 'limit': int(raw), 'unlimited': False}
                elif raw == '':
                    values = {'enabled': False, 'limit': 0, 'unlimited': False}
                else:
                    errors.append(f'{plan.name} / {feature.name}: "{raw}" is not a number or ∞.')
                    continue
                wanted.append((plan, feature, values))
        if errors:
            return 0

        changed = 0
        with transaction.atomic():
            for plan, feature, values in wanted:
                row = rows.get((plan.id, feature.id))
                if row is None:
                    PlanFeature.objects.create(plan=plan, feature=feature, **values)
                    changed += 1
                elif any(getattr(row, name) != value for name, value in values.items()):
                    for name, value in values.items():
                        setattr(row, name, value)
                    try:
                        row.full_clean(exclude=['plan', 'feature'])
                    except ValidationError as error:
                        errors.append(f'{plan.name} / {feature.name}: {"; ".join(error.messages)}')
                        transaction.set_rollback(True)
                        return 0
                    row.save()
                    changed += 1
        forget()
        return changed


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ['product_id', 'base_plan_id', 'provider', 'plan', 'period', 'is_active']
    list_filter = ['provider', 'plan', 'period', 'is_active']
    search_fields = ['product_id', 'base_plan_id', 'offer_id']


@admin.register(BillingSettings)
class BillingSettingsAdmin(PageMixin, ModelAdmin):
    fieldsets = [
        ('Enforcement', {
            'fields': ['enforcement_mode'],
            'description': 'The master switch. "Log only" is for trying a change of limits without refusing anyone.',
        }),
        ('Grace and downgrades', {'fields': ['grace_days', 'offline_grace_days', 'reselect_cooldown_days', 'warn_at_percent']}),
        ('Ads', {'fields': ['ads_honeymoon_days', 'ads_placements']}),
    ]
    actions_detail = ['preview_plans']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # There is one row; go straight to it
        return redirect('admin:billing_billingsettings_change', BillingSettings.load().pk)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        forget()

    @action(description='What the app is told about plans', icon='visibility', permissions=['see_plans'])
    def preview_plans(self, request, object_id):
        return self.page(
            request, 'billing/admin/preview.html', 'What the app is told about plans',
            body=json.dumps(payload.plans(), indent=2, ensure_ascii=False),
            back=reverse('admin:billing_billingsettings_change', args=[object_id]),
        )
