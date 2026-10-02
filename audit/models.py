from django.db import models
from django.conf import settings
import uuid


class CRUDLog(models.Model):
    """
    Model to track all Create, Read, Update, Delete operations in the system.
    This provides a complete audit trail of all data modifications.
    """
    ACTION_CHOICES = (
        ('CREATE', 'Create'),
        ('READ', 'Read'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='crud_logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    operation=models.TextField(blank=True, null=True, help_text="Optional description for the action")
    model_name = models.CharField(max_length=1000,null=False,blank=False)
    record_ids = models.TextField(null=True, blank=True, help_text="ID of the records being modified")
    changes = models.JSONField(null=True, blank=True, help_text="JSON representation of the changes made")

    timestamp = models.DateTimeField(auto_now_add=True,editable=False,null=False,blank=False)
    ip_address = models.GenericIPAddressField(null=False,blank=False,editable=False)
    user_agent = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "CRUD Log"
        verbose_name_plural = "CRUD Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['action']),
            models.Index(fields=['model_name']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f"{self.get_action_display()} on {self.model_name}:{self.record_ids} by {self.user or 'Anonymous'}"
