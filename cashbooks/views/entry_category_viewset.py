from rest_framework import viewsets,status
from rest_framework.decorators import action
from rest_framework.response import Response

from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction

from ..models import(
    EntryCategory,CashBook
)
from ..serializers import (
    EntryCategorySerializer
)
from ..permissions import CashBookAdminPermission

class EntryCategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing entry categories.
    Supports CRUD with soft delete and bulk creation.
    """
    serializer_class = EntryCategorySerializer
    permission_classes = [CashBookAdminPermission]
    
    def get_queryset(self):
        """Get categories for a specific cashbook (excluding soft-deleted)"""
        cashbook_id = self.kwargs.get('cashbook_pk')
        if not cashbook_id:
            return EntryCategory.objects.none()
        
        cashbook = get_object_or_404(CashBook, id=cashbook_id)
        
        # Check if user has admin permission
        if not (cashbook.owner == self.request.user or 
                cashbook.has_permission(self.request.user, 'admin')):
            return EntryCategory.objects.none()
        
        return EntryCategory.objects.filter(
            cashbook=cashbook,
            is_deleted=False
        ).order_by('category_name')
    
    def list(self, request, *args, **kwargs):
        """
        List all categories for a cashbook.
        Also returns default category suggestions that are not yet added.
        """
        cashbook_id = self.kwargs.get('cashbook_pk')
        cashbook = get_object_or_404(CashBook, id=cashbook_id)
        
        # Check permission
        if not cashbook.has_permission(request.user, 'view'):
            return Response(
                {'error': 'You do not have permission to view categories'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        
        # Get existing category names
        existing_categories = set(queryset.values_list('category_name', flat=True))
        
        # Get suggestions (default categories not yet added)
        suggestions = [
            cat for cat in EntryCategory.GENERAL_CATEGORIES 
            if cat not in existing_categories
        ]
        
        return Response({
            'categories': serializer.data,
            'suggestions': suggestions
        })
    
    def create(self, request, *args, **kwargs):
        """Create a new category for a cashbook"""
        cashbook_id = self.kwargs.get('cashbook_pk')
        cashbook = get_object_or_404(CashBook, id=cashbook_id)
        
        # Check admin permission
        if not (cashbook.owner == request.user or 
                cashbook.has_permission(request.user, 'admin')):
            return Response(
                {'error': 'You do not have permission to create categories'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Check if category already exists (including soft-deleted)
        existing = EntryCategory.objects.filter(
            cashbook=cashbook,
            category_name=serializer.validated_data['category_name']
        ).first()
        
        if existing:
            if existing.is_deleted:
                # Restore soft-deleted category
                existing.is_deleted = False
                existing.deleted_at = None
                existing.save()
                return Response(
                    {
                        'message': 'Category restored successfully',
                        'category': EntryCategorySerializer(existing).data
                    },
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {'error': 'Category with this name already exists'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Check if category is a default one from GENERAL_CATEGORIES
        is_default = serializer.validated_data['category_name'] in EntryCategory.GENERAL_CATEGORIES
        
        category = serializer.save(cashbook=cashbook, is_default=is_default)
        return Response(
            {
                'message': 'Category created successfully',
                'category': EntryCategorySerializer(category).data
            },
            status=status.HTTP_201_CREATED
        )
    
    def update(self, request, *args, **kwargs):
        """Update a category"""
        instance = self.get_object()
        
        # Check admin permission
        if not (instance.cashbook.owner == request.user or 
                instance.cashbook.has_permission(request.user, 'admin')):
            return Response(
                {'error': 'You do not have permission to update categories'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Prevent editing default categories that aren't customized yet
        if instance.is_default and instance.category_name in EntryCategory.GENERAL_CATEGORIES:
            return Response(
                {'error': 'Cannot edit default categories. Create a custom one instead.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get('partial', False))
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        
        return Response(
            {
                'message': 'Category updated successfully',
                'category': EntryCategorySerializer(category).data
            },
            status=status.HTTP_200_OK
        )
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete a category"""
        instance = self.get_object()
        
        # Check admin permission
        if not (instance.cashbook.owner == request.user or 
                instance.cashbook.has_permission(request.user, 'admin')):
            return Response(
                {'error': 'You do not have permission to delete categories'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Soft delete
        instance.is_deleted = True
        instance.deleted_at = timezone.now()
        instance.save()
        
        return Response(
            {'message': 'Category deleted successfully'},
            status=status.HTTP_200_OK
        )
    
    @action(detail=False, methods=['post'], url_path='bulk-create')
    def bulk_create(self, request, cashbook_pk=None):
        """
        Bulk create categories from a list.
        Body: {"categories": ["Category1", "Category2", ...]}
        """
        cashbook = get_object_or_404(CashBook, id=cashbook_pk)
        
        # Check admin permission
        if not (cashbook.owner == request.user or 
                cashbook.has_permission(request.user, 'admin')):
            return Response(
                {'error': 'You do not have permission to create categories'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        category_names = request.data.get('categories', [])
        if not isinstance(category_names, list):
            return Response(
                {'error': 'categories must be a list'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        created = []
        skipped = []
        
        with transaction.atomic():
            for name in category_names:
                # Check if exists
                existing = EntryCategory.objects.filter(
                    cashbook=cashbook,
                    category_name=name
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
                    # Create new - check if it's a default category
                    is_default = name in EntryCategory.GENERAL_CATEGORIES
                    EntryCategory.objects.create(
                        cashbook=cashbook,
                        category_name=name,
                        is_default=is_default
                    )
                    created.append(name)
        
        return Response({
            'message': f'{len(created)} categories created/restored',
            'created': created,
            'skipped': skipped
        }, status=status.HTTP_201_CREATED)