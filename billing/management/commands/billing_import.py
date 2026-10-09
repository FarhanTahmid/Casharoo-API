import json

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from billing.catalog_io import load


class Command(BaseCommand):
    help = 'Load plans and features from a billing_export file. Adds and updates; never deletes.'
    # A database without a default plan is exactly what this may be fixing
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('path')

    def handle(self, *args, path, **options):
        try:
            with open(path, encoding='utf-8') as file:
                data = json.load(file)
        except (OSError, ValueError) as error:
            raise CommandError(f'Cannot read {path}: {error}')
        try:
            written = load(data)
        except (ValidationError, KeyError) as error:
            raise CommandError(f'Nothing was changed. {error}')
        self.stdout.write(self.style.SUCCESS(f'Catalog loaded: {written} row(s) written.'))
