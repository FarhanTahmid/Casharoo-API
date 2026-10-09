import secrets

from django.db import migrations


def resolve_clashes(usernames):
    """
    Given (pk, username) pairs oldest first, return {pk: new_username} for the
    accounts whose username clashes case-insensitively with an earlier one.
    The earliest account keeps its name; later ones get 4 random digits.
    """
    taken = set()
    renames = {}
    for pk, username in usernames:
        if username.lower() not in taken:
            taken.add(username.lower())
            continue
        while True:
            candidate = f'{username[:146]}{secrets.randbelow(10000):04d}'
            if candidate.lower() not in taken:
                break
        taken.add(candidate.lower())
        renames[pk] = candidate
    return renames


def dedupe(apps, schema_editor):
    AppUser = apps.get_model('identity', 'AppUser')
    rows = AppUser.objects.order_by('date_joined', 'pk').values_list('pk', 'username')
    for pk, username in resolve_clashes(list(rows)).items():
        AppUser.objects.filter(pk=pk).update(username=username)


class Migration(migrations.Migration):
    dependencies = [
        ('identity', '0002_usersettings_onboarded_at_usersettings_primary_mode'),
    ]

    operations = [
        migrations.RunPython(dedupe, migrations.RunPython.noop),
    ]
