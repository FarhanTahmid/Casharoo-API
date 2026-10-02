"""
Django PRODUCTION settings for Casharooo.
"""
from django.core.exceptions import ImproperlyConfigured
from .base import *

# DEBUG
DEBUG = False

if not SECRET_KEY:
    raise ImproperlyConfigured('SECRET_KEY must be set in production.')
if not config('FIELD_ENCRYPTION_KEYS', default=''):
    raise ImproperlyConfigured('FIELD_ENCRYPTION_KEYS must be set in production.')

# Hosts
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    cast=lambda v: [s.strip() for s in v.split(',')]
)
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='',
    cast=lambda v: [s.strip() for s in v.split(',') if s.strip()]
)

# Database
DATABASES = {'default': database_from_env('PROD')}

# Email goes through the background worker, which sends it over SMTP
EMAIL_BACKEND = 'notifications.backends.QueuedEmailBackend'
EMAIL_DELIVERY_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

# Security Configuration
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_SECONDS = 31536000
SECURE_REDIRECT_EXEMPT = [r'^health/$']
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_PRELOAD = True
if TRUSTED_PROXY_COUNT:
    # The proxy terminates TLS and tells us the original scheme
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Additional Settings for Production for logging
# In production, don't log to console, only to files
for logger_config in LOGGING['loggers'].values():
    if 'console' in logger_config.get('handlers', []):
        logger_config['handlers'].remove('console')
