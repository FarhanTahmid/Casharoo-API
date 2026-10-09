from django.db import migrations

from billing.seed import seed


def load_defaults(apps, schema_editor):
    """A new database starts with the default plans, so the first user already has one."""
    seed(
        apps.get_model('billing', 'Feature'), apps.get_model('billing', 'Plan'),
        apps.get_model('billing', 'PlanFeature'), apps.get_model('billing', 'BillingSettings'),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0001_initial'),
    ]

    operations = [
        # Going back leaves the rows: the tables themselves go with 0001
        migrations.RunPython(load_defaults, migrations.RunPython.noop),
    ]
