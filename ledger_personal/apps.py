from django.apps import AppConfig


class LedgerPersonalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ledger_personal'

    def ready(self):
        from . import signals  # noqa: F401
