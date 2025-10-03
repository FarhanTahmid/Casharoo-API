#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from dotenv import load_dotenv

def main():
    """Run administrative tasks."""
    # load dotnenv
    load_dotenv()
    
    if os.environ.get('PROJECT_ENVIRONMENT')=='development':
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casharoo.settings.dev')
    elif os.environ.get('PROJECT_ENVIRONMENT')=='production':
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casharoo.settings.prod')
    elif os.environ.get('PROJECT_ENVIRONMENT')=='test':
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casharoo.settings.test')
    else:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casharoo.settings.dev')

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
