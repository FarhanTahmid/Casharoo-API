from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from workspaces.models import Workspace
from workspaces.tenancy import TenantScopedMixin

from .. import gates, locks, offers, payload
from ..catalog.keys import BY_KEY, F
from ..entitlements import resolve
from ..models import FunnelEvent
from ..rules import RULES

_entitlements = serializers.DictField(help_text='Plan, features, locks, ads and offers of the signed-in user.')


class BillingView(TenantScopedMixin, APIView):
    """
    Everything here answers for the signed-in user only; no endpoint takes a
    user id. The tenant scope is needed because working out what a downgrade
    locked counts rows in the user's workspaces.
    """
    permission_classes = [IsAuthenticated]
    # Billing's own endpoints change nothing a plan limits
    billing_gate = gates.exempt('billing endpoints')

    def entitlements(self):
        return Response(payload.build(self.request.user))


class EntitlementsView(BillingView):
    @extend_schema(responses=_entitlements)
    def get(self, request):
        return self.entitlements()


class PlansView(BillingView):
    @extend_schema(responses=serializers.DictField(help_text='Public plans and what each gives.'))
    def get(self, request):
        return Response(payload.plans())


class PromoRedeemView(BillingView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'promo_redeem'

    @extend_schema(
        request=inline_serializer('PromoRedeemRequest', {'code': serializers.CharField()}),
        responses=_entitlements,
    )
    def post(self, request):
        code = request.data.get('code')
        if not isinstance(code, str) or not code.strip():
            raise ValidationError({'code': [offers.BAD_CODE]})
        try:
            offers.redeem(request.user, code)
        except offers.OfferError as error:
            raise ValidationError({'code': [str(error)]})
        return self.entitlements()


class OfferClaimView(BillingView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'promo_redeem'

    @extend_schema(request=None, responses=_entitlements)
    def post(self, request, slug):
        try:
            offers.claim(request.user, slug)
        except offers.OfferError as error:
            raise ValidationError({'detail': str(error)})
        return self.entitlements()


class KeepView(BillingView):
    """What the user is over the limit on, with names, so they can choose what stays editable."""

    @extend_schema(responses=serializers.ListField(child=serializers.DictField()))
    def get(self, request):
        user = request.user
        owned = {str(workspace.pk): workspace for workspace in Workspace.objects.filter(owner=user)}
        choices = []
        for lock in payload.build(user)['locks']:
            rule = RULES[lock['feature']]
            workspace = owned.get(lock['scope'])
            rows = rule.queryset(user, workspace).order_by('created_at', 'id')
            if rule.feature == F.TEAM_SEATS:
                rows = rows.select_related('user')
            kept = set(lock['kept'])
            choices.append({
                **lock,
                'noun': rule.noun,
                'workspace_name': workspace.name if workspace is not None else '',
                'items': [
                    {'id': str(row.pk), 'label': rule.label(row), 'kept': str(row.pk) in kept} for row in rows
                ],
            })
        return Response(choices)


class KeepChoiceView(BillingView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'billing_keep'

    @extend_schema(
        request=inline_serializer('KeepChoiceRequest', {
            'scope': serializers.CharField(required=False, allow_blank=True, help_text='Workspace id, for a per-workspace limit.'),
            'ids': serializers.ListField(child=serializers.UUIDField()),
        }),
        responses=_entitlements,
    )
    def put(self, request, feature):
        rule = RULES.get(feature)
        if rule is None:
            raise ValidationError({'feature': 'Nothing to choose for this.'})
        try:
            ids = serializers.ListField(child=serializers.UUIDField(), max_length=500).run_validation(
                request.data.get('ids')
            )
        except ValidationError as error:
            raise ValidationError({'ids': error.detail})

        workspace = None
        if rule.per_workspace:
            # Only the owner decides, and only for a workspace that is theirs
            try:
                workspace = Workspace.objects.filter(owner=request.user, pk=request.data.get('scope')).first()
            except (DjangoValidationError, ValueError, TypeError):
                workspace = None
            if workspace is None:
                raise ValidationError({'scope': 'Workspace not found.'})

        entitlements = resolve(request.user)
        try:
            locks.choose(
                request.user, rule, workspace, entitlements.limit_of(rule.feature),
                entitlements.settings.reselect_cooldown_days, ids,
            )
        except DjangoValidationError as error:
            raise ValidationError({'ids': error.messages})
        return self.entitlements()


class FunnelEventView(BillingView):
    """The app reports that an upgrade screen was seen or tapped. Nothing here grants anything."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'billing_events'

    @extend_schema(
        request=inline_serializer('FunnelEventRequest', {
            'kind': serializers.ChoiceField(choices=FunnelEvent.CLIENT_KINDS),
            'feature': serializers.CharField(required=False, allow_blank=True),
        }),
        responses={204: None},
    )
    def post(self, request):
        kind = request.data.get('kind')
        if kind not in FunnelEvent.CLIENT_KINDS:
            raise ValidationError({'kind': f'One of: {", ".join(FunnelEvent.CLIENT_KINDS)}.'})
        feature = request.data.get('feature') or ''
        FunnelEvent.objects.create(
            user=request.user, kind=kind, origin='app',
            # Only names the server knows, so the table cannot be filled with junk
            feature_key=feature if feature in BY_KEY else '',
            plan_code=resolve(request.user).plan.code,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DevSimulateView(BillingView):
    """Development only: act out a store event for the signed-in user. Not routed in production."""

    @extend_schema(
        request=inline_serializer('DevSimulateRequest', {
            'action': serializers.ChoiceField(choices=['purchase', 'renew', 'cancel', 'expire', 'refund']),
            'plan': serializers.CharField(required=False),
            'period': serializers.CharField(required=False),
        }),
        responses=_entitlements,
    )
    def post(self, request):
        from ..models import Plan, Product
        from ..providers.dev import ACTIONS, DevProvider

        if not settings.BILLING_DEV_TOOLS:
            return Response(status=status.HTTP_404_NOT_FOUND)
        action = request.data.get('action')
        if action not in ACTIONS:
            raise ValidationError({'action': f'One of: {", ".join(ACTIONS)}.'})
        plan_code = request.data.get('plan')
        period = request.data.get('period') or 'monthly'
        if action == 'purchase':
            if not Plan.objects.filter(code=plan_code, is_active=True).exists():
                raise ValidationError({'plan': 'No such plan.'})
            if period not in Product.PERIOD_DAYS:
                raise ValidationError({'period': f'One of: {", ".join(Product.PERIOD_DAYS)}.'})
        try:
            DevProvider().simulate(request.user, action, plan_code=plan_code, period=period)
        except ValueError as error:
            raise ValidationError({'action': str(error)})
        return self.entitlements()
