"""
Base Django settings for casharooo project.

"""
import os
from dotenv import load_dotenv
from pathlib import Path
from datetime import timedelta
from decouple import config

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECRET KEY
SECRET_KEY = os.environ.get('SECRET_KEY')

# Application definition

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS=[
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
]

LOCAL_APPS=[
    'app_users',
    'system_manager',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# Middlewares
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Logging middleware
    'system_manager.logger.middleware.LoggerMiddleware',
]

# Root URL configuration
ROOT_URLCONF = 'casharoo.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR,'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Custom AUTH model
AUTH_USER_MODEL = 'app_users.AppUser'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Dhaka'

USE_I18N = True

USE_TZ = True

# Resized Image Fields
DJANGORESIZED_DEFAULT_SIZE = [1920, 1080]
DJANGORESIZED_DEFAULT_SCALE = 0.8
DJANGORESIZED_DEFAULT_QUALITY = 85
DJANGORESIZED_DEFAULT_KEEP_META = True
DJANGORESIZED_DEFAULT_NORMALIZE_ROTATION = True

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour'
    }
}

# Logging configuration
LOGS_DIR = BASE_DIR/'logs'
LOGS_DIR.mkdir(exist_ok=True)

# Set directory permissions for web server access (Linux/Unix systems)
try:
    os.chmod(LOGS_DIR, 0o755)  # rwxr-xr-x permissions
except (OSError, AttributeError):
    # Handle Windows or permission errors gracefully
    pass

# Django Logging Configuration Dictionary
# This follows Django's standard logging configuration format
LOGGING = {
    # Configuration version - always set to 1 for current Django versions
    'version': 1,
    
    # Don't disable existing loggers - allows third-party packages to log
    'disable_existing_loggers': False,
    
    # ==========================================================================
    # LOG MESSAGE FORMATTERS
    # ==========================================================================
    # Formatters define how log messages appear in output files and console
    
    'formatters': {
        # Detailed formatter for production file logs
        # Provides comprehensive information for troubleshooting and analysis
        'detailed': {
            'format': '{asctime} | {levelname:8} | {name} | {message}',
            'style': '{',  # Use new-style string formatting
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        
        # Simple formatter for console output during development
        # Reduces clutter while providing essential information
        'simple': {
            'format': '{asctime} | {levelname} | {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        
        # JSON-compatible formatter for log aggregation systems
        # Includes file path and line number for debugging
        'json': {
            'format': '{asctime} | {levelname} | {name} | {message} | {pathname}:{lineno}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    
    # ==========================================================================
    # LOG OUTPUT HANDLERS
    # ==========================================================================
    # Handlers determine where log messages are sent (files, console, etc.)
    
    'handlers': {
        # Console handler for development and debugging
        # Shows log messages in terminal/command prompt
        'console': {
            'level': 'INFO',  # Only show INFO level and above in console
            'class': 'logging.StreamHandler',  # Standard output stream
            'formatter': 'simple',  # Use simple format for readability
        },
        
        # HTTP request/response logs with automatic rotation
        # Captures all web traffic for performance and usage analysis
        'requests_file': {
            'level': 'INFO',  # Log all requests (INFO level and above)
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'requests.log',
            'maxBytes': 10 * 1024 * 1024,  # 10MB maximum file size
            'backupCount': 10,  # Keep 10 backup files (100MB total retention)
            'formatter': 'detailed',  # Use detailed format for analysis
            'encoding': 'utf-8',  # Support international characters
        },
        
        # Error and exception logs with extended retention
        # Critical for debugging and system monitoring
        'errors_file': {
            'level': 'WARNING',  # Log warnings, errors, and critical messages
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'errors.log',
            'maxBytes': 5 * 1024 * 1024,  # 5MB maximum file size
            'backupCount': 20,  # Keep 20 backup files (errors are important!)
            'formatter': 'detailed',  # Detailed format for debugging
            'encoding': 'utf-8',
        },
        
        # Authentication and security event logs
        # Essential for compliance and security monitoring
        'auth_file': {
            'level': 'INFO',  # Log all authentication events
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'auth.log',
            'maxBytes': 5 * 1024 * 1024,  # 5MB maximum file size
            'backupCount': 15,  # Keep 15 backup files for audit trail
            'formatter': 'detailed',  # Detailed format for security analysis
            'encoding': 'utf-8',
        },
        
        # General application logs for system events
        # Catches miscellaneous application events and system messages
        'general_file': {
            'level': 'INFO',  # Log general information and above
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'general.log',
            'maxBytes': 10 * 1024 * 1024,  # 10MB maximum file size
            'backupCount': 5,  # Keep 5 backup files (moderate retention)
            'formatter': 'detailed',  # Detailed format for analysis
            'encoding': 'utf-8',
        },
    },
    
    # ==========================================================================
    # SPECIALIZED LOGGERS
    # ==========================================================================
    # Loggers categorize and route different types of log messages
    
    'loggers': {
        # HTTP request/response logger
        # Used by ERPLoggerMiddleware for all web traffic logging
        'erp.requests': {
            'handlers': ['requests_file', 'console'],  # File + console output
            'level': 'INFO',  # Log INFO level and above
            'propagate': False,  # Don't pass to parent loggers (avoid duplicates)
        },
        
        # Error and exception logger  
        # Used for unhandled exceptions and application errors
        'erp.errors': {
            'handlers': ['errors_file', 'console'],  # File + console output
            'level': 'WARNING',  # Log WARNING level and above
            'propagate': False,  # Independent error handling
        },
        
        # Authentication and security event logger
        # Used for login/logout events and security monitoring
        'erp.auth': {
            'handlers': ['auth_file', 'console'],  # File + console output
            'level': 'INFO',  # Log all auth events
            'propagate': False,  # Separate from general logging
        },
        
        # Django's default logger for framework messages
        # Handles Django internal logging (database, cache, etc.)
        'django': {
            'handlers': ['general_file', 'console'],  # File + console output
            'level': 'INFO',  # Framework information and above
            'propagate': False,  # Don't duplicate Django's internal logging
        },
        
        # Root logger - catches any unrouted log messages
        # Fallback for any logging not handled by specific loggers
        '': {
            'handlers': ['general_file', 'console'],  # Default output
            'level': 'INFO',  # General information level
        },
    },
}

# Maximum log message length (prevents memory issues with very long messages)
LOGGING_MAX_MESSAGE_LENGTH = 8192  # 8KB maximum per log message

# Log file permissions (Unix/Linux systems)
LOGGING_FILE_PERMISSIONS = 0o644  # rw-r--r-- (readable by owner and group)

# Timezone for log timestamps (should match Django's TIME_ZONE setting)
LOGGING_TIMEZONE = 'Asia/Dhaka'