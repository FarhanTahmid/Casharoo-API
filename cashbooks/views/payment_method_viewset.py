from rest_framework import viewsets,status
from rest_framework.decorators import action
from rest_framework.response import Response

from django.db import transaction
from django.shortcuts import get_object_or_404

from ..permissions import CashBookAdminPermission
from ..models import PaymentMethod,CashBook
from ..serializers import PaymentMethodSerializer


class PaymentMethodViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing payment methods.
    Supports CRUD with soft delete and bulk creation.
    """
    serializer_class = PaymentMethodSerializer
    permission_classes = [CashBookAdminPermission]
    
    def get_queryset(self):
        """Get payment methods for a specific cashbook (excluding soft-deleted)"""
        cashbook_id = self.kwargs.get('cashbook_pk')
        if not cashbook_id:
            return PaymentMethod.objects.none()
        
        cashbook = get_object_or_404(CashBook, id=cashbook_id)
        
        # Check if user has admin permission
        if not (cashbook.owner == self.request.user or 
                cashbook.has_permission(self.request.user, 'admin')):
            return PaymentMethod.objects.none()
        
        return PaymentMethod.objects.filter(
            cashbook=cashbook,
            is_deleted=False
        ).order_by('payment_method_name')
    
    def list(self, request, *args, **kwargs):
        """
        List all payment methods for a cashbook.
        Also returns default payment method suggestions that are not yet added.
        """
        cashbook_id = self.kwargs.get('cashbook_pk')
        cashbook = get_object_or_404(CashBook, id=cashbook_id)
        
        # Check permission
        if not cashbook.has_permission(request.user, 'view'):
            return Response(
                {'error': 'You do not have permission to view payment methods'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        
        # Get existing payment method names
        existing_methods = set(queryset.values_list('payment_method_name', flat=True))
        
        # Get suggestions (default methods not yet added)
        suggestions = [
            method for method in PaymentMethod.GENERAL_PAYMENT_METHODS 
            if method not in existing_methods
        ]
        
        return Response({
            'payment_methods': serializer.data,
            'suggestions': suggestions
        })
    
    def create(self, request, *args, **kwargs):
        """Create a new payment method for a cashbook"""
        cashbook_id = self.kwargs.get('cashbook_pk')
        cashbook = get_object_or_404(CashBook, id=cashbook_id)
        
        # Check admin permission
        if not (cashbook.owner == request.user or 
                cashbook.has_permission(request.user, 'admin')):
            return Response(
                {'error': 'You do not have permission to create payment methods'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Check if payment method already exists (including soft-deleted)
        existing = PaymentMethod.objects.filter(
            cashbook=cashbook,
            payment_method_name=serializer.validated_data['payment_method_name']
        ).first()
        
        if existing:
            if existing.is_deleted:
                # Restore soft-deleted method
                existing.is_deleted = False
                existing.deleted_at = None
                existing.save()
                return Response(
                    {
                        'message': 'Payment method restored successfully',
                        'payment_method': PaymentMethodSerializer(existing).data
                    },
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {'error': 'Payment method with this name already exists'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Check if payment method is a default one from GENERAL_PAYMENT_METHODS
        is_default = serializer.validated_data['payment_method_name'] in PaymentMethod.GENERAL_PAYMENT_METHODS
        
        payment_method = serializer.save(cashbook=cashbook, is_default=is_default)
        return Response(
            {
                'message': 'Payment method created successfully',
                'payment_method': PaymentMethodSerializer(payment_method).data
            },
            status=status.HTTP_201_CREATED
        )
    
    def update(self, request, *args, **kwargs):
        """Update a payment method"""
        instance = self.get_object()
        
        # Check admin permission
        if not (instance.cashbook.owner == request.user or 
                instance.cashbook.has_permission(request.user, 'admin')):
            return Response(
                {'error': 'You do not have permission to update payment methods'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Prevent editing default payment methods that aren't customized yet
        if instance.is_default and instance.payment_method_name in PaymentMethod.GENERAL_PAYMENT_METHODS:
            return Response(
                {'error': 'Cannot edit default payment methods. Create a custom one instead.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)
        payment_method = serializer.save()
        
        return Response(
            {
                'message': 'Payment method updated successfully',
                'payment_method': PaymentMethodSerializer(payment_method).data
            },
            status=status.HTTP_200_OK
        )
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete a payment method"""
        instance = self.get_object()
        
        # Check admin permission
        if not (instance.cashbook.owner == request.user or 
                instance.cashbook.has_permission(request.user, 'admin')):
            return Response(
                {'error': 'You do not have permission to delete payment methods'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Soft delete
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.save()
        
        return Response(
            {'message': 'Payment method deleted successfully'},
            status=status.HTTP_200_OK
        )
    
    @action(detail=False, methods=['post'], url_path='bulk-create')
    def bulk_create(self, request, cashbook_pk=None):
        """
        Bulk create payment methods from a list.
        Body: {"payment_methods": ["Method1", "Method2", ...]}
        """
        cashbook = get_object_or_404(CashBook, id=cashbook_pk)
        
        # Check admin permission
        if not (cashbook.owner == request.user or 
                cashbook.has_permission(request.user, 'admin')):
            return Response(
                {'error': 'You do not have permission to create payment methods'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        method_names = request.data.get('payment_methods', [])
        if not isinstance(method_names, list):
            return Response(
                {'error': 'payment_methods must be a list'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        created = []
        skipped = []
        
        with transaction.atomic():
            for name in method_names:
                # Check if exists
                existing = PaymentMethod.objects.filter(
                    cashbook=cashbook,
                    payment_method_name=name
                ).first()
                
                if existing:
                    if existing.is_deleted:
                        # Restore
                        existing.is_deleted = False
                        existing.deleted_at = None
                        existing.save()
                        created.append(name)
                    else:
                        skipped.append(name)
                else:
                    # Create new - check if it's a default payment method
                    is_default = name in PaymentMethod.GENERAL_PAYMENT_METHODS
                    PaymentMethod.objects.create(
                        cashbook=cashbook,
                        payment_method_name=name,
                        is_default=is_default
                    )
                    created.append(name)
        
        return Response({
            'message': f'{len(created)} payment methods created/restored',
            'created': created,
            'skipped': skipped
        }, status=status.HTTP_201_CREATED)