from rest_framework import viewsets,status,filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q,Sum
from django.db import transaction
from django.core.exceptions import ValidationError

from ..models import CashBook
from system_manager.utils.audit_utils import AuditLogMixin

class CashbookViewset(viewsets.ViewSet,AuditLogMixin):
    
    permission_classes=[IsAuthenticated]
    
    @action(details=True,methods=['POST'],url_path='create-entry')
    def create_entry(self,request,pk):
        try:
            pass
        except Exception as e:
            return Response(
                {'error':"Something went wrong."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )