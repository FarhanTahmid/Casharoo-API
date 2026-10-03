from django.db import migrations

from sync.sql import CREATE_FUNCTION, DROP_FUNCTION


class Migration(migrations.Migration):

    dependencies = [
        ('sync', '0001_initial'),
        ('workspaces', '0002_workspace_is_demo'),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_FUNCTION, reverse_sql=DROP_FUNCTION),
    ]
