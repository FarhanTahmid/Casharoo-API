"""
Django TEST settings for Spendroo. Used by CI.
"""
from .base import *

# DEBUG
DEBUG = False

# Hosts
ALLOWED_HOSTS = ['*']

# Database
DATABASES = {'default': database_from_env('TEST')}

# Fast hashing; never use outside tests
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

BILLING_DEV_TOOLS = True
