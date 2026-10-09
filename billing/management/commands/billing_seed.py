from django.core.management.base import BaseCommand

from billing.seed import seed_live


class Command(BaseCommand):
    help = (
        'Load the default plans and features (billing/catalog/defaults.py). '
        'Only adds what is missing, so changes made in the admin stay.'
    )
    # It is what repairs a database the system check complains about
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Put every default back, overwriting admin changes.')
        parser.add_argument('--dry-run', action='store_true', help='Show what would change and change nothing.')
        parser.add_argument(
            '--check', action='store_true',
            help='Show how the database differs from the defaults (what --force would change). Changes nothing.',
        )

    def handle(self, *args, force, dry_run, check, **options):
        if check:
            force = dry_run = True
        changes = seed_live(force=force, dry_run=dry_run)
        for change in changes:
            self.stdout.write(f'  {change}')
        if not changes:
            self.stdout.write(self.style.SUCCESS(
                'The database matches the defaults.' if check else 'Nothing to add: the catalog is already loaded.'
            ))
        elif dry_run:
            self.stdout.write(self.style.WARNING(f'{len(changes)} change(s) not applied.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'{len(changes)} change(s) applied.'))
