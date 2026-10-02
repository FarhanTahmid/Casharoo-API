"""
Encrypted model field for secrets that must be read back (SMTP passwords,
mailbox refresh tokens). Values are encrypted with Fernet before they reach
the database, so a database dump alone does not expose them.

Keys come from settings.FIELD_ENCRYPTION_KEYS. The first key encrypts; every
key can decrypt, so a key is rotated by putting the new one first.
"""
from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.db import models

PREFIX = 'fernet:'


def _fernet():
    return MultiFernet([Fernet(key) for key in settings.FIELD_ENCRYPTION_KEYS])


def encrypt(value):
    return PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(value):
    return _fernet().decrypt(value[len(PREFIX):].encode()).decode()


class EncryptedTextField(models.TextField):
    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == '' or value.startswith(PREFIX):
            return value
        return encrypt(value)

    def from_db_value(self, value, expression, connection):
        if value is None or not value.startswith(PREFIX):
            return value
        return decrypt(value)
