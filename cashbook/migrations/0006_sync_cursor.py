from django.db import migrations

from sync.sql import enable_sync

# Every synced table (history tables are not synced).
# workspaces/tests.py fails if one is missing here.
TABLES = [
    'cashbook_cashbook',
    'cashbook_cashbookadditionalmember',
    'cashbook_entrycategory',
    'cashbook_paymentmethod',
    'cashbook_entry',
    'cashbook_entrybills',
    'cashbook_entryextrafields',
]


class Migration(migrations.Migration):

    dependencies = [
        ('cashbook', '0005_remove_cashbook_insert_insert_and_more'),
        ('sync', '0002_server_seq'),
    ]

    operations = [operation for table in TABLES for operation in enable_sync(table)]
