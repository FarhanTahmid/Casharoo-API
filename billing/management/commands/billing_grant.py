from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from billing.models import Plan
from billing.offers import grant


class Command(BaseCommand):
    help = 'Put a user on a plan. Example: billing_grant tester@example.com plus --days 30 --reason "beta tester"'

    def add_arguments(self, parser):
        parser.add_argument('email')
        parser.add_argument('plan', help='Plan code, such as plus or business.')
        parser.add_argument('--days', type=int, help='How long it lasts. Without it, it never ends.')
        parser.add_argument('--reason', default='granted from the command line')

    def handle(self, *args, email, plan, days, reason, **options):
        user = get_user_model().objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f'No user with the email {email}.')
        found = Plan.objects.filter(code=plan, is_active=True).first()
        if found is None:
            codes = ', '.join(Plan.objects.filter(is_active=True).values_list('code', flat=True))
            raise CommandError(f'No active plan "{plan}". Plans: {codes}.')
        if days is not None and days <= 0:
            raise CommandError('--days must be positive.')
        subscription = grant(user, found, days=days, reason=reason)
        until = subscription.current_period_end
        self.stdout.write(self.style.SUCCESS(
            f'{user.email} is on {found.name} {"until " + until.isoformat() if until else "with no end"}.'
        ))
