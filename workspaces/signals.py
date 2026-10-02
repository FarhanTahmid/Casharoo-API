from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .services import get_personal_workspace


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_personal_workspace(sender, instance, created, **kwargs):
    """Every user gets a personal workspace on sign-up."""
    if created and not kwargs.get('raw'):
        get_personal_workspace(instance)
