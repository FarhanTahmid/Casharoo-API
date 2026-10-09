from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from billing.entitlements import explain


class Command(BaseCommand):
    help = 'Show what a user is entitled to and where each value comes from.'

    def add_arguments(self, parser):
        parser.add_argument('email')

    def handle(self, *args, email, **options):
        user = get_user_model().objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f'No user with the email {email}.')
        entitlements, rows = explain(user)
        end = entitlements.expires_at.isoformat() if entitlements.expires_at else 'no end'
        grace = ', in grace period' if entitlements.in_grace else ''
        self.stdout.write(f'{user.email}: {entitlements.plan.name} (from {entitlements.source}, {end}{grace})')
        for row in rows:
            self.stdout.write(f'  {row["key"]:32} {row["value"]}')
            for step in row['steps']:
                self.stdout.write(f'  {"":32}   {step}')
