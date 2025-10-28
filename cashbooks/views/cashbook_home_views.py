from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.core.exceptions import ValidationError

from ..models import (
    CashBook, CashBookAdditionalMember
)
from ..serializers import (
    CashBookListSerializer, CashBookDetailSerializer, CashBookCreateUpdateSerializer,
    CashBookAdditionalMemberSerializer
)
from ..permissions import IsCashBookOwnerOrMember, IsCashBookOwner
from system_manager.utils.audit_utils import AuditLogMixin


class CashBookHomeViewSet(viewsets.ModelViewSet, AuditLogMixin):
    """
    ViewSet for CashBook CRUD operations with comprehensive error handling
    """
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['book_name', 'description']
    ordering_fields = ['created_at', 'last_edited_at']
    ordering = ['-created_at', '-last_edited_at']
    
    def get_queryset(self):
        user = self.request.user
        # Get cashbooks owned by user or where user is a member
        return CashBook.objects.filter(
            Q(owner=user) | Q(cashbookadditionalmember__member=user)
        ).distinct()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return CashBookListSerializer
        elif self.action == 'retrieve':
            return CashBookDetailSerializer
        return CashBookCreateUpdateSerializer
    
    def get_permissions(self):
        if self.action == 'destroy':
            return [IsAuthenticated(), IsCashBookOwner()]
        elif self.action in ['update', 'partial_update']:
            return [IsAuthenticated(), IsCashBookOwnerOrMember()]
        return [IsAuthenticated()]
    
    def list(self, request, *args, **kwargs):
        """List cashbooks with error handling"""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            return Response(
                {'detail': 'Failed to fetch cashbooks. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def retrieve(self, request, *args, **kwargs):
        """Retrieve single cashbook with error handling"""
        try:
            return super().retrieve(request, *args, **kwargs)
        except CashBook.DoesNotExist:
            return Response(
                {'detail': 'Cashbook not found or you do not have access.'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'detail': 'Failed to retrieve cashbook. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def create(self, request, *args, **kwargs):
        """Create cashbook with enhanced validation"""
        try:
            # Validate book_name
            book_name = request.data.get('book_name', '').strip()
            if not book_name:
                return Response(
                    {'book_name': ['Cashbook name is required.']},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if len(book_name) > 100:
                return Response(
                    {'book_name': ['Cashbook name must not exceed 100 characters.']},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check for duplicate name for this user
            if CashBook.objects.filter(owner=request.user, book_name__iexact=book_name).exists():
                return Response(
                    {'book_name': ['You already have a cashbook with this name.']},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            serializer = self.get_serializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            self.perform_create(serializer)
            
            return Response(
                {
                    'message': 'Cashbook created successfully.',
                    'data': serializer.data
                },
                status=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            return Response(
                {'detail': 'Failed to create cashbook. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def perform_create(self, serializer):
        instance = serializer.save(owner=self.request.user)
        self.log_action(
            request=self.request,
            action='CREATE',
            model_name='CashBook',
            record_ids=instance.id,
            changes=serializer.data,
            operation='Created new cashbook'
        )
    
    def update(self, request, *args, **kwargs):
        """Update cashbook with validation"""
        try:
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
            
            # Validate book_name if provided
            book_name = request.data.get('book_name')
            if book_name is not None:
                book_name = book_name.strip()
                if not book_name:
                    return Response(
                        {'book_name': ['Cashbook name cannot be empty.']},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                if len(book_name) > 100:
                    return Response(
                        {'book_name': ['Cashbook name must not exceed 100 characters.']},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Check for duplicate name (excluding current cashbook)
                if CashBook.objects.filter(
                    owner=request.user, 
                    book_name__iexact=book_name
                ).exclude(id=instance.id).exists():
                    return Response(
                        {'book_name': ['You already have a cashbook with this name.']},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            self.perform_update(serializer)
            
            return Response(
                {
                    'message': 'Cashbook updated successfully.',
                    'data': serializer.data
                },
                status=status.HTTP_200_OK
            )
            
        except CashBook.DoesNotExist:
            return Response(
                {'detail': 'Cashbook not found or you do not have access.'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'detail': 'Failed to update cashbook. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def partial_update(self, request, *args, **kwargs):
        """Partial update with error handling"""
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Delete cashbook with error handling"""
        try:
            instance = self.get_object()
            
            # Additional check: Only owner can delete
            if instance.owner != request.user:
                return Response(
                    {'detail': 'Only the owner can delete this cashbook.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            cashbook_name = instance.book_name
            self.perform_destroy(instance)
            
            return Response(
                {'message': f'Cashbook "{cashbook_name}" deleted successfully.'},
                status=status.HTTP_200_OK
            )
            
        except CashBook.DoesNotExist:
            return Response(
                {'detail': 'Cashbook not found or already deleted.'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'detail': 'Failed to delete cashbook. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['delete'], url_path="bulk-delete")
    def bulk_delete(self, request):
        """Bulk delete cashbooks with comprehensive validation"""
        try:
            uuid_list = request.data.get('ids', [])
            
            # Validation
            if not uuid_list:
                return Response(
                    {'detail': 'No cashbook IDs provided for deletion.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not isinstance(uuid_list, list):
                return Response(
                    {'detail': 'Invalid format. IDs must be provided as a list.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if len(uuid_list) > 50:
                return Response(
                    {'detail': 'Cannot delete more than 50 cashbooks at once.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get cashbooks that user owns (users can only delete their own cashbooks)
            cashbooks = CashBook.objects.filter(
                id__in=uuid_list,
                owner=request.user
            )
            
            if not cashbooks.exists():
                return Response(
                    {'detail': 'No cashbooks found or you do not have permission to delete them.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            deleted_count = cashbooks.count()
            
            # Check if some IDs were not found
            requested_count = len(uuid_list)
            if deleted_count < requested_count:
                not_found_count = requested_count - deleted_count
                return Response(
                    {
                        'detail': f'{not_found_count} cashbook(s) not found or you do not own them.',
                        'deleted_count': 0
                    },
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Use transaction for atomic deletion
            with transaction.atomic():
                deleted_ids = list(cashbooks.values_list('id', flat=True))
                cashbooks.delete()
            
            message = f'{deleted_count} cashbook(s) deleted successfully.' if deleted_count > 1 else 'Cashbook deleted successfully.'
            
            return Response(
                {
                    'message': message,
                    'deleted_ids': deleted_ids,
                    'deleted_count': deleted_count
                },
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            return Response(
                {'detail': 'Failed to delete cashbooks. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def balance(self, request, pk=None):
        """Get current balance of cashbook with error handling"""
        try:
            cashbook = self.get_object()
            balance = cashbook.get_balance()
            
            # Get total cash in and cash out
            cash_in = cashbook.entry_set.filter(entry_type='cash_in').aggregate(
                total=Sum('amount'))['total'] or 0
            cash_out = cashbook.entry_set.filter(entry_type='cash_out').aggregate(
                total=Sum('amount'))['total'] or 0
            
            return Response({
                'balance': float(balance),
                'total_cash_in': float(cash_in),
                'total_cash_out': float(cash_out)
            })
            
        except CashBook.DoesNotExist:
            return Response(
                {'detail': 'Cashbook not found or you do not have access.'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'detail': 'Failed to retrieve balance. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def add_member(self, request, pk=None):
        """Add a member to cashbook with validation"""
        try:
            cashbook = self.get_object()
            
            # Check permission
            if not cashbook.has_permission(request.user, 'admin'):
                return Response(
                    {'detail': 'Only the owner or an admin can add members.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            serializer = CashBookAdditionalMemberSerializer(data=request.data)
            if serializer.is_valid():
                # Check if member already exists
                member_id = request.data.get('member')
                if CashBookAdditionalMember.objects.filter(
                    cashbook=cashbook, 
                    member_id=member_id
                ).exists():
                    return Response(
                        {'detail': 'This user is already a member of this cashbook.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                serializer.save(cashbook=cashbook, added_by=request.user)
                return Response(
                    {
                        'message': 'Member added successfully.',
                        'data': serializer.data
                    },
                    status=status.HTTP_201_CREATED
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        except CashBook.DoesNotExist:
            return Response(
                {'detail': 'Cashbook not found or you do not have access.'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'detail': 'Failed to add member. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['patch'], url_path='members/(?P<member_id>[^/.]+)')
    def update_member_role(self, request, pk=None, member_id=None):
        """Update member role with validation"""
        try:
            cashbook = self.get_object()
            
            # Check permission
            if not cashbook.has_permission(request.user, 'admin'):
                return Response(
                    {'detail': 'Only the owner or an admin can update member roles.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            member = get_object_or_404(CashBookAdditionalMember, id=member_id, cashbook=cashbook)
            
            new_role = request.data.get('role')
            if not new_role:
                return Response(
                    {'detail': 'Role is required.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if new_role not in ['viewer', 'editor', 'admin']:
                return Response(
                    {'detail': 'Invalid role. Choose from: viewer, editor, admin.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            member.role = new_role
            member.save()
            
            serializer = CashBookAdditionalMemberSerializer(member)
            return Response(
                {
                    'message': 'Member role updated successfully.',
                    'data': serializer.data
                },
                status=status.HTTP_200_OK
            )
            
        except CashBook.DoesNotExist:
            return Response(
                {'detail': 'Cashbook not found or you do not have access.'},
                status=status.HTTP_404_NOT_FOUND
            )
        except CashBookAdditionalMember.DoesNotExist:
            return Response(
                {'detail': 'Member not found in this cashbook.'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'detail': 'Failed to update member role. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['delete'], url_path='members/(?P<member_id>[^/.]+)')
    def remove_member(self, request, pk=None, member_id=None):
        """Remove a member from cashbook with validation"""
        try:
            cashbook = self.get_object()
            
            # Check permission
            if not cashbook.has_permission(request.user, 'admin'):
                return Response(
                    {'detail': 'Only the owner or an admin can remove members.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            member = get_object_or_404(CashBookAdditionalMember, id=member_id, cashbook=cashbook)
            member_name = str(member.member)
            member.delete()
            
            return Response(
                {'message': f'Member "{member_name}" removed successfully.'},
                status=status.HTTP_200_OK
            )
            
        except CashBook.DoesNotExist:
            return Response(
                {'detail': 'Cashbook not found or you do not have access.'},
                status=status.HTTP_404_NOT_FOUND
            )
        except CashBookAdditionalMember.DoesNotExist:
            return Response(
                {'detail': 'Member not found in this cashbook.'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'detail': 'Failed to remove member. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )