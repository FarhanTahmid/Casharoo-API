"""
Django DEVELOPMENT settings for Spendroo.
"""
from .base import *

# DEBUG
DEBUG = True

# Hosts
ALLOWED_HOSTS = ['*']

# Database
DATABASES = {'default': database_from_env('DEV')}

# Verification codes are printed in the runserver console
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# POST /api/v1/billing/dev/simulate/ acts out purchases without a store
BILLING_DEV_TOOLS = True
