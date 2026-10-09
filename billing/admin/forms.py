from datetime import timedelta

from django import forms
from django.utils import timezone
from unfold.widgets import (
    UnfoldAdminIntegerFieldWidget, UnfoldAdminSelectWidget, UnfoldAdminSplitDateTimeWidget,
    UnfoldAdminTextInputWidget, UnfoldBooleanSwitchWidget,
)

from ..catalog.keys import QUOTA
from ..models import Benefit, EntitlementOverride, Feature, Plan, PromoCode

# Staff without the right to edit plans may hand out a plan for this long at most
SUPPORT_MAX_DAYS = 30


def can_grant_freely(user):
    return user.has_perm('billing.change_plan')


class GrantForm(forms.Form):
    plan = forms.ModelChoiceField(
        queryset=Plan.objects.filter(is_active=True).order_by('rank'), widget=UnfoldAdminSelectWidget,
    )
    days = forms.IntegerField(
        required=False, min_value=1, max_value=3650, widget=UnfoldAdminIntegerFieldWidget,
        help_text='How long it lasts. Leave empty for no end.',
    )
    reason = forms.CharField(
        max_length=300, widget=UnfoldAdminTextInputWidget, help_text='Why. Kept with the grant.',
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.limited = not can_grant_freely(user)
        if self.limited:
            self.fields['days'].required = True
            self.fields['days'].max_value = SUPPORT_MAX_DAYS
            self.fields['days'].help_text = f'How long it lasts, up to {SUPPORT_MAX_DAYS} days.'

    def clean_days(self):
        days = self.cleaned_data.get('days')
        if self.limited and (days is None or days > SUPPORT_MAX_DAYS):
            raise forms.ValidationError(f'You can grant a plan for up to {SUPPORT_MAX_DAYS} days.')
        return days


class OverrideForm(forms.Form):
    feature = forms.ModelChoiceField(queryset=Feature.objects.all(), widget=UnfoldAdminSelectWidget)
    mode = forms.ChoiceField(choices=EntitlementOverride.MODE_CHOICES, widget=UnfoldAdminSelectWidget)
    enabled = forms.BooleanField(required=False, initial=True, widget=UnfoldBooleanSwitchWidget, label='On (for a flag)')
    limit = forms.IntegerField(required=False, min_value=0, widget=UnfoldAdminIntegerFieldWidget, label='Number (for a limit or quota)')
    unlimited = forms.BooleanField(required=False, widget=UnfoldBooleanSwitchWidget)
    days = forms.IntegerField(
        required=False, min_value=1, max_value=3650, widget=UnfoldAdminIntegerFieldWidget,
        help_text='Leave empty to keep it until removed.',
    )
    reason = forms.CharField(max_length=300, widget=UnfoldAdminTextInputWidget)

    def build(self, user, by):
        """The override this form describes, validated. Raises ValidationError into the form."""
        data = self.cleaned_data
        now = timezone.now()
        override = EntitlementOverride(
            user=user, feature=data['feature'], mode=data['mode'], enabled=data['enabled'],
            limit=data['limit'], unlimited=data['unlimited'], starts_at=now,
            ends_at=now + timedelta(days=data['days']) if data['days'] else None,
            reason=data['reason'], created_by=by,
        )
        override.full_clean()
        return override


class CreditsForm(forms.Form):
    feature = forms.ModelChoiceField(
        queryset=Feature.objects.filter(kind=QUOTA), widget=UnfoldAdminSelectWidget, label='Quota',
    )
    amount = forms.IntegerField(min_value=1, max_value=1_000_000, widget=UnfoldAdminIntegerFieldWidget)
    reason = forms.CharField(max_length=200, widget=UnfoldAdminTextInputWidget)


class GenerateCodesForm(forms.Form):
    count = forms.IntegerField(min_value=1, max_value=1000, initial=10, widget=UnfoldAdminIntegerFieldWidget)
    note = forms.CharField(
        max_length=200, widget=UnfoldAdminTextInputWidget, help_text='Who these are for. Not shown to users.',
    )
    kind = forms.ChoiceField(choices=PromoCode.KIND_CHOICES, widget=UnfoldAdminSelectWidget)
    plan = forms.ModelChoiceField(
        queryset=Plan.objects.filter(is_active=True).order_by('rank'), required=False, widget=UnfoldAdminSelectWidget,
    )
    days = forms.IntegerField(required=False, min_value=1, max_value=3650, widget=UnfoldAdminIntegerFieldWidget)
    quota = forms.ModelChoiceField(
        queryset=Feature.objects.filter(kind=QUOTA), required=False, widget=UnfoldAdminSelectWidget,
    )
    amount = forms.IntegerField(required=False, min_value=1, widget=UnfoldAdminIntegerFieldWidget)
    uses_per_code = forms.IntegerField(
        min_value=1, initial=1, widget=UnfoldAdminIntegerFieldWidget, help_text='How many people can use each code.',
    )
    valid_days = forms.IntegerField(
        required=False, min_value=1, widget=UnfoldAdminIntegerFieldWidget,
        help_text='Days until the codes stop working. Leave empty for no end.',
    )

    def clean(self):
        data = super().clean()
        if data.get('kind') == Benefit.BENEFIT_PLAN and not (data.get('plan') and data.get('days')):
            raise forms.ValidationError('A plan code needs a plan and a number of days.')
        if data.get('kind') == Benefit.BENEFIT_QUOTA and not (data.get('quota') and data.get('amount')):
            raise forms.ValidationError('A quota code needs a quota and an amount.')
        return data


class RestoreForm(forms.Form):
    moment = forms.SplitDateTimeField(
        widget=UnfoldAdminSplitDateTimeWidget, label='Put the plan back to how it was at',
    )

    def clean_moment(self):
        moment = self.cleaned_data['moment']
        if moment > timezone.now():
            raise forms.ValidationError('That is in the future.')
        return moment
