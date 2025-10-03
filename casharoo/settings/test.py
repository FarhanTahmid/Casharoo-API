"""
Django TEST settings for nexora_erp project.
"""
from .base import *

# DEBUG
DEBUG = True

# Hosts
ALLOWED_HOSTS = ['*']

# WSGI APPLICATION
WSGI_APPLICATION = 'casharoo.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': os.environ.get('TEST_DATABASE_ENGINE'),
        'NAME': os.environ.get('TEST_DATABASE_NAME'),
        'USER': os.environ.get('TEST_DATABASE_USER'),
        'PASSWORD': os.environ.get('TEST_DATABASE_PASSWORD'),
        'HOST': os.environ.get('TEST_DATABASE_HOST'),
        'PORT': os.environ.get('TEST_DATABASE_PORT'),
    }
}

# JWT Configuration
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=120),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',
    'JTI_CLAIM': 'jti',
    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}

# CORS Configuration
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000',
    cast=lambda v: [s.strip() for s in v.split(',')]
)

CORS_ALLOW_CREDENTIALS = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
# static root
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
        os.path.join(BASE_DIR, 'static'),
    ]
# Media files
MEDIA_ROOT = os.path.join(BASE_DIR, 'Media_Files/')
MEDIA_URL = "/media_files/"