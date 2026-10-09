from allauth.account.signals import password_changed, password_set
from django.dispatch import receiver

from audit.utils.audit_utils import AuditLogMixin


def _log_password(request, user, operation):
    if request is None:
        return
    AuditLogMixin().log_action(request, 'UPDATE', 'AppUser', user.pk, operation=operation)


@receiver(password_changed)
def log_password_changed(sender, request, user, **kwargs):
    _log_password(request, user, 'password_changed')


@receiver(password_set)
def log_password_set(sender, request, user, **kwargs):
    _log_password(request, user, 'password_set')
