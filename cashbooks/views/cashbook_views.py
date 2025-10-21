from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404

from ..models import (
    CashBook, CashBookAdditionalMember
)
from ..serializers import (
    CashBookListSerializer, CashBookDetailSerializer, CashBookCreateUpdateSerializer,
    CashBookAdditionalMemberSerializer
)
from ..permissions import IsCashBookOwnerOrMember, IsCashBookOwner
from system_manager.utils.audit_utils import AuditLogMixin

class CashBookViewSet(viewsets.ModelViewSet,AuditLogMixin):
    """
    ViewSet for CashBook CRUD operations
    """
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['book_name', 'description']
    ordering_fields = ['created_at', 'last_edited_at']
    ordering = ['-created_at','-last_edited_at']
    
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
    
    def perform_create(self, serializer):
        instance=serializer.save(owner=self.request.user)
        self.log_action(
            request=self.request,
            action='CREATE',
            model_name='CashBook',
            record_ids=instance.id,
            changes=serializer.data,
            operation='Created new cashbook'
        )            
    
    @action(detail=True, methods=['get'])
    def balance(self, request, pk=None):
        """Get current balance of cashbook"""
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
    
    @action(detail=True, methods=['post'])
    def add_member(self, request, pk=None):
        """Add a member to cashbook"""
        cashbook = self.get_object()
        
        # Check permission
        if not cashbook.has_permission(request.user, 'admin'):
            return Response(
                {'error': 'Only owner or admin can add members'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = CashBookAdditionalMemberSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(cashbook=cashbook, added_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['patch'], url_path='members/(?P<member_id>[^/.]+)')
    def update_member_role(self, request, pk=None, member_id=None):
        """Update member role"""
        cashbook = self.get_object()
        
        # Check permission
        if not cashbook.has_permission(request.user, 'admin'):
            return Response(
                {'error': 'Only owner or admin can update member roles'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        member = get_object_or_404(CashBookAdditionalMember, id=member_id, cashbook=cashbook)
        
        new_role = request.data.get('role')
        if new_role not in ['viewer', 'editor', 'admin']:
            return Response(
                {'error': 'Invalid role. Choose from: viewer, editor, admin'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        member.role = new_role
        member.save()
        
        serializer = CashBookAdditionalMemberSerializer(member)
        return Response(serializer.data)
    
    @action(detail=True, methods=['delete'], url_path='members/(?P<member_id>[^/.]+)')
    def remove_member(self, request, pk=None, member_id=None):
        """Remove a member from cashbook"""
        cashbook = self.get_object()
        
        # Check permission
        if not cashbook.has_permission(request.user, 'admin'):
            return Response(
                {'error': 'Only owner or admin can remove members'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        member = get_object_or_404(CashBookAdditionalMember, id=member_id, cashbook=cashbook)
        member.delete()
        
        return Response({'message': 'Member removed successfully'}, status=status.HTTP_204_NO_CONTENT)
