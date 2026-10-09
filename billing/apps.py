from django.apps import AppConfig
from django.db.models.signals import post_migrate


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'billing'

    def ready(self):
        from django.contrib import admin

        from . import checks, signals  # noqa: F401
        from .roles import ensure_roles

        # The admin opens on the billing dashboard. The roles are set up after
        # every app's migrate, since they also hold permissions of other apps
        admin.site.index_template = 'billing/admin/dashboard.html'
        post_migrate.connect(ensure_roles, dispatch_uid='billing_ensure_roles')
