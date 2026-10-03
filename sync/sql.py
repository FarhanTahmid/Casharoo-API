"""
Migration operations for the sync change cursor.

Every synced table has a `server_seq` column filled by a trigger on insert
and update. A client pulls rows with `server_seq` greater than the last value
it saw, so within one workspace the numbers must come out in commit order.
The trigger guarantees that by locking the workspace row before taking the
next number: a second writer to the same workspace waits until the first has
committed.

Usage, in a migration that runs after the table exists and depends on
('sync', '0002_server_seq'):

    operations = [*enable_sync('cashbook_entry'), ...]
"""
from django.db import migrations

CREATE_FUNCTION = """
CREATE SEQUENCE sync_server_seq;
CREATE FUNCTION sync_assign_server_seq() RETURNS trigger AS $$
BEGIN
    PERFORM 1 FROM workspaces_workspace WHERE id = NEW.workspace_id FOR NO KEY UPDATE;
    NEW.server_seq := nextval('sync_server_seq');
    RETURN NEW;
END
$$ LANGUAGE plpgsql;
"""
DROP_FUNCTION = """
DROP FUNCTION sync_assign_server_seq();
DROP SEQUENCE sync_server_seq;
"""


def enable_sync(table):
    return [
        migrations.RunSQL(
            sql=[
                f'CREATE TRIGGER sync_server_seq BEFORE INSERT OR UPDATE ON "{table}" '
                f'FOR EACH ROW EXECUTE FUNCTION sync_assign_server_seq()',
                f'CREATE INDEX "{table}_ws_seq" ON "{table}" (workspace_id, server_seq)',
            ],
            reverse_sql=[
                f'DROP INDEX "{table}_ws_seq"',
                f'DROP TRIGGER sync_server_seq ON "{table}"',
            ],
        )
    ]
