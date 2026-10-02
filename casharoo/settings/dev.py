"""
Django DEVELOPMENT settings for Casharooo.
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
