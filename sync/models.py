from django.conf import settings
from django.db import models


class SyncMutation(models.Model):
    """
    One row per client mutation the server has processed. The id is generated
    on the device, so a retried push finds its earlier result here instead of
    being applied twice.
    """
    STATUS_APPLIED = 'applied'
    STATUS_REJECTED = 'rejected'

    id = models.UUIDField(primary_key=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='+')
    table = models.CharField(max_length=40)
    row_id = models.UUIDField()
    status = models.CharField(max_length=10)
    error_code = models.CharField(max_length=40, blank=True, default='')
    error_detail = models.TextField(blank=True, default='')
    # Machine-readable extras for the app, such as which plan limit refused it
    error_meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['created_at'])]
