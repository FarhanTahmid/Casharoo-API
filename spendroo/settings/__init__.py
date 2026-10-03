"""
Selects the settings module from PROJECT_ENVIRONMENT, so that
DJANGO_SETTINGS_MODULE='spendroo.settings' works for wsgi/asgi.
"""
import os
from dotenv import load_dotenv

load_dotenv()

_environment = os.environ.get('PROJECT_ENVIRONMENT')

if _environment == 'production':
    from .prod import *
elif _environment == 'test':
    from .test import *
else:
    from .dev import *
