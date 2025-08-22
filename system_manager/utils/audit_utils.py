import json
import logging

from ..models import CRUDLog
from django.utils import timezone
from system_manager.utils.private_user_data import PrivateUserData
from django_countries.fields import Country
from decimal import Decimal
from datetime import date,datetime,time
from uuid import UUID
from django.core.files.base import File
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile

class AuditLogMixin:
    logger=logging.getLogger('system_manager.utils.audit_utils.AuditLogMixin')
    
    """
    Mixin to add audit logging functionality to ViewSets.
    Tracks all CRUD operations with user, timestamp, and change details.
    """

    def log_action(self, request, action, model_name, record_ids, changes=None,operation=None):
        """
        Log CRUD action to audit trail

        Args:
            request: HTTP request object
            action: Action type ('CREATE', 'READ', 'UPDATE', 'DELETE')
            model_name: Name of the model being operated on
            record_id: ID or identifier of the record
            changes: Dictionary of changes made (for CREATE/UPDATE/DELETE)
            operation: Optional description of the operation performed
        """
        try:
            # Get user from request
            user = request.user if request.user.is_authenticated else None

            # Get IP address
            ip_address = PrivateUserData._get_client_ip(request)

            # Get user agent
            user_agent = request.META.get('HTTP_USER_AGENT', '')

            if changes:
                changes=self.make_json_serializable(changes)

            # Create audit log entry
            CRUDLog.objects.create(
                user=user,
                action=action,
                model_name=model_name,
                record_ids=str(record_ids),
                timestamp=timezone.now(),
                ip_address=ip_address,
                user_agent=user_agent,
                changes=changes,
                operation=operation
            )
        except Exception as e:
            # Log the error but don't fail the main operation
            self.logger.error(f"Exception occured while creating CRUDLog: {str(e)}",exc_info=True)
            pass

    def make_json_serializable(self, data):
        """
        Recursively convert data to JSON serializable types.
        Handles all common Django data types that cause JSON serialization issues.
        """
        if data is None:
            return None

        if isinstance(data, dict):
            return {key: self.make_json_serializable(value) for key, value in data.items()}
        elif isinstance(data, (list, tuple)):
            return [self.make_json_serializable(item) for item in data]
        else:

            # Handle different data types
            if isinstance(data, Decimal):
                return str(data)
            elif isinstance(data, (date, datetime)):
                return data.isoformat()
            elif isinstance(data, time):
                return data.isoformat()
            elif isinstance(data, UUID):
                return str(data)
            elif isinstance(data, (InMemoryUploadedFile, TemporaryUploadedFile)):
                return {
                    'filename': data.name,
                    'size': data.size,
                    'content_type': data.content_type,
                    'file_uploaded': True
                }
            elif isinstance(data, File):
                return {
                    'filename': data.name if data.name else None,
                    'url': data.url if hasattr(data, 'url') and data else None,
                    'file_field': True
                }
            elif isinstance(data, Country):
                return str(data)
            elif hasattr(data, '__dict__') and hasattr(data, '_meta'):
                # Handle Django model instances
                return f"{data._meta.model_name}:{str(data)}"
            elif hasattr(data, '__dict__'):
                # Handle other objects with dict representation
                return str(data)
            else:
                # Try to JSON serialize, fallback to string if it fails
                try:
                    json.dumps(data)
                    return data
                except (TypeError, ValueError):
                    return str(data)

    def _get_changes(self, old_data, new_data):
        """
        Compare old and new data to identify changes

        Args:
            old_data: Dictionary of old field values
            new_data: Dictionary of new field values

        Returns:
            Dictionary containing changed fields with old and new values
        """
        try:
            changes = {}

            # Get all unique keys from both dictionaries
            all_keys = set(old_data.keys()) | set(new_data.keys())

            for key in all_keys:
                old_value = old_data.get(key)
                new_value = new_data.get(key)

                # Skip timestamp fields and ID fields for change tracking
                if key in ['created_at', 'updated_at', 'id']:
                    continue

                # Compare values (handle None values)
                if old_value != new_value:
                    changes[key] = {
                        'old': old_value,
                        'new': new_value
                    }

            return changes if changes else None
        except Exception as e:
            self.logger.error(f"Error while getting changes: {e}",exc_info=True)