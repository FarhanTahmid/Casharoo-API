from django.db import migrations

from workspaces.rls import enable_rls

# Every table with a workspace_id column, history tables included.
# workspaces/tests.py fails if a tenant table is missing here.
TABLES = [
    'cashbook_cashbook',
    'cashbook_cashbookadditionalmember',
    'cashbook_entrycategory',
    'cashbook_paymentmethod',
    'cashbook_entry',
    'cashbook_entrybills',
    'cashbook_entryextrafields',
    'cashbook_cashbookevent',
    'cashbook_cashbookadditionalmemberevent',
    'cashbook_entrycategoryevent',
    'cashbook_paymentmethodevent',
    'cashbook_entryevent',
]


class Migration(migrations.Migration):

    dependencies = [
        ('cashbook', '0003_initial'),
    ]

    operations = [operation for table in TABLES for operation in enable_rls(table)]
