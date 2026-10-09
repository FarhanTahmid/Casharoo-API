import csv
from datetime import timedelta

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import timezone
from unfold.admin import ModelAdmin
from unfold.decorators import action, display
from unfold.widgets import UnfoldAdminCheckboxSelectMultipleWidget

from ..entitlements import forget
from ..models import Benefit, Campaign, CampaignClaim, PromoCode, PromoRedemption, Subscription
from .base import PageMixin, ReadOnlyAdmin
from .forms import GenerateCodesForm


def window_state(obj, now=None):
    now = now or timezone.now()
    if not obj.is_active:
        return 'off'
    if obj.starts_at > now:
        return 'scheduled'
    if obj.ends_at and obj.ends_at <= now:
        return 'ended'
    return 'running'


STATE_COLOURS = {'running': 'success', 'scheduled': 'info', 'ended': 'warning', 'off': 'danger', 'used up': 'warning'}


class CampaignForm(forms.ModelForm):
    placements = forms.MultipleChoiceField(
        choices=Campaign.PLACEMENT_CHOICES, required=False, widget=UnfoldAdminCheckboxSelectMultipleWidget,
        help_text='Where the app shows it.',
    )

    class Meta:
        model = Campaign
        fields = '__all__'


def audience_size(campaign):
    """How many users the campaign reaches right now. None when that cannot be counted cheaply."""
    users = get_user_model().objects.filter(is_active=True)
    if campaign.joined_after:
        users = users.filter(date_joined__gte=campaign.joined_after)
    if campaign.joined_before:
        users = users.filter(date_joined__lt=campaign.joined_before)
    if campaign.audience == Campaign.AUDIENCE_USERS:
        return users.filter(pk__in=campaign.audience_users.values('pk')).count()
    if campaign.audience == Campaign.AUDIENCE_PLANS:
        # Who holds which plan by subscription; everyone else is on the default plan
        now = timezone.now()
        plan_ids = set(campaign.audience_plans.values_list('pk', flat=True))
        live = Subscription.objects.filter(
            Q(current_period_end__isnull=True) | Q(current_period_end__gt=now),
            status=Subscription.STATUS_ACTIVE, starts_at__lte=now,
        )
        best = {}
        for user_id, plan_id, rank in live.values_list('user_id', 'plan_id', 'plan__rank'):
            if user_id not in best or rank > best[user_id][1]:
                best[user_id] = (plan_id, rank)
        subscribers_in = [user_id for user_id, (plan_id, _) in best.items() if plan_id in plan_ids]
        count = users.filter(pk__in=subscribers_in).count()
        if any(plan.is_default for plan in campaign.audience_plans.all()):
            count += users.exclude(pk__in=list(best)).count()
        return count
    return users.count()


@admin.register(Campaign)
class CampaignAdmin(ModelAdmin):
    form = CampaignForm
    list_display = ['name', 'state', 'audience', 'offer', 'starts_at', 'ends_at', 'claims', 'priority']
    list_filter = ['is_active', 'kind', 'audience']
    search_fields = ['name', 'slug', 'title']
    prepopulated_fields = {'slug': ['name']}
    filter_horizontal = ['audience_plans']
    autocomplete_fields = ['audience_users']
    readonly_fields = ['reach', 'claimed_count', 'created_by', 'created_at', 'updated_at']
    fieldsets = [
        (None, {'fields': ['name', 'slug', 'is_active', 'starts_at', 'ends_at', 'priority']}),
        ('Who sees it', {
            'fields': ['audience', 'audience_plans', 'audience_users', 'joined_after', 'joined_before', 'reach'],
            'description': 'Save to see how many users this reaches before switching it on.',
        }),
        ('What it gives', {
            'fields': ['kind', 'benefit_plan', 'benefit_days', 'auto_apply', 'benefit_feature', 'benefit_amount',
                       'store_offer_id', 'max_claims', 'claimed_count'],
            'description': 'A discount on the price is made in the store; put its offer id here and the app will show that offer. '
                           'With "auto apply", everyone in the audience has the plan for as long as the campaign runs.',
        }),
        ('What the app shows', {'fields': ['placements', 'title', 'title_bn', 'body', 'body_bn', 'cta', 'cta_bn']}),
        ('Record', {'fields': ['created_by', 'created_at', 'updated_at'], 'classes': ['collapse']}),
    ]
    actions = ['switch_on', 'switch_off']

    @display(description='State', label=STATE_COLOURS)
    def state(self, campaign):
        return window_state(campaign)

    @display(description='Gives')
    def offer(self, campaign):
        text = campaign.describe_benefit(campaign.kind) or campaign.get_kind_display()
        return f'{text} (applies by itself)' if campaign.auto_apply else text

    @display(description='Claimed')
    def claims(self, campaign):
        return f'{campaign.claimed_count} of {campaign.max_claims}' if campaign.max_claims else campaign.claimed_count

    @display(description='Reaches')
    def reach(self, campaign):
        if campaign.pk is None:
            return 'Save first.'
        return f'{audience_size(campaign):,} user(s) right now'

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        forget()

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        forget()

    @admin.action(description='Switch on', permissions=['change'])
    def switch_on(self, request, queryset):
        for campaign in queryset:
            campaign.is_active = True
            campaign.save(update_fields=['is_active', 'updated_at'])
        forget()
        messages.success(request, f'{queryset.count()} campaign(s) switched on.')

    @admin.action(description='Switch off', permissions=['change'])
    def switch_off(self, request, queryset):
        for campaign in queryset:
            campaign.is_active = False
            campaign.save(update_fields=['is_active', 'updated_at'])
        forget()
        messages.success(request, f'{queryset.count()} campaign(s) switched off.')


@admin.register(PromoCode)
class PromoCodeAdmin(PageMixin, ModelAdmin):
    list_display = ['code', 'note', 'state', 'gives', 'used', 'starts_at', 'ends_at', 'campaign']
    list_filter = ['is_active', 'kind', 'campaign']
    search_fields = ['code', 'note']
    filter_horizontal = ['only_plans']
    readonly_fields = ['redeemed_count', 'created_by', 'created_at']
    fieldsets = [
        (None, {'fields': ['code', 'note', 'is_active', 'starts_at', 'ends_at', 'campaign']}),
        ('What it gives', {'fields': ['kind', 'benefit_plan', 'benefit_days', 'benefit_feature', 'benefit_amount']}),
        ('Who can use it', {
            'fields': ['max_redemptions', 'redeemed_count', 'only_plans'],
            'description': 'Each person can use a code once. Codes are given away, never sold: selling access '
                           'outside the store breaks its payment rules.',
        }),
        ('Record', {'fields': ['created_by', 'created_at'], 'classes': ['collapse']}),
    ]
    actions = ['export_csv', 'switch_off']
    actions_list = ['generate']

    @display(description='State', label=STATE_COLOURS)
    def state(self, promo):
        if promo.max_redemptions is not None and promo.redeemed_count >= promo.max_redemptions:
            return 'used up'
        return window_state(promo)

    @display(description='Gives')
    def gives(self, promo):
        return promo.describe_benefit(promo.kind)

    @display(description='Used')
    def used(self, promo):
        return f'{promo.redeemed_count} of {promo.max_redemptions}' if promo.max_redemptions else promo.redeemed_count

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def get_urls(self):
        return [
            path('generate/', self.admin_site.admin_view(self.generate_view), name='billing_promocode_generate'),
        ] + super().get_urls()

    @action(description='Generate codes', icon='auto_awesome', permissions=['add_codes'])
    def generate(self, request):
        return redirect('admin:billing_promocode_generate')

    def generate_view(self, request):
        self.need(request, 'billing.add_promocode')
        form = GenerateCodesForm(request.POST or None)
        if request.method == 'POST' and form.is_valid():
            data = form.cleaned_data
            now = timezone.now()
            is_plan = data['kind'] == Benefit.BENEFIT_PLAN
            codes = [
                PromoCode(
                    note=data['note'], kind=data['kind'], created_by=request.user,
                    benefit_plan=data['plan'] if is_plan else None, benefit_days=data['days'] if is_plan else None,
                    benefit_feature=None if is_plan else data['quota'],
                    benefit_amount=None if is_plan else data['amount'],
                    max_redemptions=data['uses_per_code'], starts_at=now,
                    ends_at=now + timedelta(days=data['valid_days']) if data['valid_days'] else None,
                )
                for _ in range(data['count'])
            ]
            PromoCode.objects.bulk_create(codes)
            messages.success(request, f'{len(codes)} code(s) made. Select them and choose "Export as CSV" to hand them out.')
            return redirect(f"{reverse('admin:billing_promocode_changelist')}?q={data['note']}")
        return self.page(
            request, 'billing/admin/form_page.html', 'Generate promo codes', form=form,
            submit_label='Generate', back=reverse('admin:billing_promocode_changelist'),
            intro='Makes random codes that all give the same thing. Give them away; never sell them.',
        )

    @admin.action(description='Export as CSV', permissions=['view'])
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="promo-codes.csv"'
        writer = csv.writer(response)
        writer.writerow(['code', 'gives', 'uses', 'max_uses', 'ends_at', 'note'])
        for promo in queryset.select_related('benefit_plan', 'benefit_feature'):
            writer.writerow([
                promo.code, promo.describe_benefit(promo.kind), promo.redeemed_count, promo.max_redemptions or '',
                promo.ends_at.isoformat() if promo.ends_at else '', promo.note,
            ])
        return response

    @admin.action(description='Switch off', permissions=['change'])
    def switch_off(self, request, queryset):
        for promo in queryset:
            promo.is_active = False
            promo.save(update_fields=['is_active'])
        messages.success(request, f'{queryset.count()} code(s) switched off.')


@admin.register(PromoRedemption)
class PromoRedemptionAdmin(ReadOnlyAdmin):
    list_display = ['promo_code', 'user', 'created_at']
    search_fields = ['promo_code__code', 'user__email']
    list_select_related = ['promo_code', 'user']
    date_hierarchy = 'created_at'


@admin.register(CampaignClaim)
class CampaignClaimAdmin(ReadOnlyAdmin):
    list_display = ['campaign', 'user', 'created_at']
    list_filter = ['campaign']
    search_fields = ['user__email']
    list_select_related = ['campaign', 'user']
    date_hierarchy = 'created_at'
