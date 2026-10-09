from django.db import migrations
from django.db.models import F
from django.utils import timezone

DEFAULT_EXPENSE = [
    'Food', 'Transport', 'Housing', 'Utilities', 'Health', 'Education',
    'Shopping', 'Entertainment', 'Mobile & Internet', 'Gifts & Donations', 'Other',
]
DEFAULT_INCOME = ['Salary', 'Business', 'Gift', 'Other income']


def mark_defaults(apps, schema_editor):
    """
    Categories made before the marker existed: the ones still carrying a
    starting name are taken to be the starting ones. Bumping the version and
    the timestamp sends the change to every device on its next pull.
    """
    Category = apps.get_model('ledger_personal', 'Category')
    for kind, names in (('expense', DEFAULT_EXPENSE), ('income', DEFAULT_INCOME)):
        Category.objects.filter(kind=kind, name__in=names, is_default=False).update(
            is_default=True, version=F('version') + 1, updated_at=timezone.now(),
        )


class Migration(migrations.Migration):

    dependencies = [
        ('ledger_personal', '0004_category_is_default'),
    ]

    operations = [
        migrations.RunPython(mark_defaults, migrations.RunPython.noop),
    ]
