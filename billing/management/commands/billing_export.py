import json

from django.core.management.base import BaseCommand

from billing.catalog_io import export


class Command(BaseCommand):
    help = 'Write the plans and features as JSON, to load elsewhere with billing_import.'

    def add_arguments(self, parser):
        parser.add_argument('path', nargs='?', help='File to write. Prints to the screen without it.')

    def handle(self, *args, path, **options):
        text = json.dumps(export(), indent=2, ensure_ascii=False)
        if path is None:
            self.stdout.write(text)
            return
        with open(path, 'w', encoding='utf-8') as file:
            file.write(text + '\n')
        self.stdout.write(self.style.SUCCESS(f'Catalog written to {path}.'))
