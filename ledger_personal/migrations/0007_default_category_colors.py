from django.db import migrations
from django.db.models import F
from django.utils import timezone

DEFAULT_COLORS = {
    'Food': '#F08A3C', 'Transport': '#3B9EE5', 'Housing': '#2F6FD0', 'Utilities': '#F5B530',
    'Health': '#D9485F', 'Education': '#7A5AF8', 'Shopping': '#E05C9A', 'Entertainment': '#B65FD6',
    'Mobile & Internet': '#12A5C4', 'Gifts & Donations': '#E8705F', 'Other': '#6B7C93',
    'Salary': '#2DB86F', 'Business': '#1FA6A0', 'Gift': '#8BBF3F', 'Other income': '#A9793E',
}


def colour_defaults(apps, schema_editor):
    """
    Starting categories made before they had colours of their own. One the
    user already coloured, or renamed, is left alone. Bumping the version and
    the timestamp sends the change to every device on its next pull.
    """
    Category = apps.get_model('ledger_personal', 'Category')
    for name, color in DEFAULT_COLORS.items():
        Category.objects.filter(is_default=True, name=name, color__isnull=True).update(
            color=color, version=F('version') + 1, updated_at=timezone.now(),
        )


class Migration(migrations.Migration):

    dependencies = [
        ('ledger_personal', '0006_category_color'),
    ]

    operations = [
        migrations.RunPython(colour_defaults, migrations.RunPython.noop),
    ]
