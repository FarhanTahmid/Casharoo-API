"""
Migration operations for row-level security on tenant tables.

Usage, in a migration that runs after the table exists:

    operations = [*enable_rls('cashbook_entry'), ...]

FORCE makes the policy apply to the table owner as well, which is the role the
application normally connects with. The settings read by the policy are
managed in workspaces/tenancy.py.
"""
from django.db import migrations

POLICY = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR workspace_id = ANY(string_to_array(NULLIF(current_setting('app.workspace_ids', true), ''), ',')::uuid[])"
)


def enable_rls(table):
    return [
        migrations.RunSQL(
            sql=[
                f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY',
                f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY',
                f'CREATE POLICY workspace_isolation ON "{table}" USING ({POLICY}) WITH CHECK ({POLICY})',
            ],
            reverse_sql=[
                f'DROP POLICY workspace_isolation ON "{table}"',
                f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY',
                f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY',
            ],
        )
    ]
