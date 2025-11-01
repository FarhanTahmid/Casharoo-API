from rest_framework import permissions
from cashbooks.models import CashBook

class CashBookAccessPermission(permissions.BasePermission):
    """
    Custom permission to check if user has access to a cashbook.
    - Owner has full access
    - Members have access based on their role (viewer, editor, admin)
    """
    
    def has_permission(self, request, view):
        # User must be authenticated
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Get the cashbook from the object
        if hasattr(obj, 'cashbook'):
            cashbook = obj.cashbook
        else:
            cashbook = obj
        
        # Safe methods (GET, HEAD, OPTIONS) require view permission
        if request.method in permissions.SAFE_METHODS:
            return cashbook.has_permission(request.user, 'view')
        
        # Write methods require edit permission
        if request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            return cashbook.has_permission(request.user, 'edit')
        
        return False

class CashBookAdminPermission(permissions.BasePermission):
    """
    Permission for admin-only actions like managing categories, payment methods, and members.
    - Owner has full access
    - Admin members have access
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Get the cashbook from the object
        if hasattr(obj, 'cashbook'):
            cashbook = obj.cashbook
        else:
            cashbook = obj
        
        # Check if user is owner or admin
        return cashbook.owner == request.user or cashbook.has_permission(request.user, 'admin')


class CashBookOwnerPermission(permissions.BasePermission):
    """
    Permission for owner-only actions.
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Get the cashbook from the object
        if hasattr(obj, 'cashbook'):
            cashbook = obj.cashbook
        else:
            cashbook = obj
        
        return cashbook.owner == request.user
class IsCashBookOwnerOrMember(permissions.BasePermission):
    """
    Permission to check if user is cashbook owner or has appropriate member role
    """
    
    def has_object_permission(self, request, view, obj):
        # Get the cashbook object
        if hasattr(obj, 'cashbook'):
            cashbook = obj.cashbook
        elif obj.__class__.__name__ == 'CashBook':
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