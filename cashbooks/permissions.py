from rest_framework import permissions
from cashbooks.models import CashBook


class IsCashBookOwnerOrMember(permissions.BasePermission):
    """
    Permission to check if user is cashbook owner or has appropriate member role
    """
    
    def has_object_permission(self, request, view, obj):
        # Get the cashbook object
        if hasattr(obj, 'cashbook'):
            cashbook = obj.cashbook
        elif isinstance(obj.__class__.__name__, 'CashBook'):
            cashbook = obj
        else:
            return False
        
        # Owner has all permissions
        if cashbook.owner == request.user:
            return True
        
        # Check member permissions
        member = cashbook.cashbookadditionalmember_set.filter(member=request.user).first()
        
        if not member:
            return False
        
        # GET, HEAD, OPTIONS allowed for all members
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # POST, PUT, PATCH, DELETE require editor or admin role
        if request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            return member.role in ['editor', 'admin']
        
        return False


class IsCashBookOwnerOrAdmin(permissions.BasePermission):
    """
    Permission for managing cashbook members - only owner or admin members
    """
    
    def has_object_permission(self, request, view, obj):
        # Get the cashbook object
        if hasattr(obj, 'cashbook'):
            cashbook = obj.cashbook
        else:
            cashbook = obj
        
        # Owner has all permissions
        if cashbook.owner == request.user:
            return True
        
        # Check if user is admin member
        member = cashbook.cashbookadditionalmember_set.filter(member=request.user).first()
        
        if not member:
            return False
        
        # Only admin members can manage other members
        return member.role == 'admin'


class IsCashBookOwner(permissions.BasePermission):
    """
    Only cashbook owner can delete the cashbook
    """
    
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        return False