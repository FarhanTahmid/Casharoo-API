# Spendroo API

Django 5.2 + Django REST Framework on PostgreSQL. One deployable plus a background worker.

## Apps

| App | Holds |
|---|---|
| `identity` | User model, profile endpoint. Authentication itself is django-allauth (headless). |
| `workspaces` | The tenant: `Workspace`, `Membership`, roles, row-level-security helpers. |
| `cashbook` | Cashbooks, entries, categories, payment methods, reports. |
| `ledger_personal` | Personal mode: accounts, categories, transactions (incl. transfers), budgets. |
| `sync` | Offline sync for the app: change log pull and idempotent mutation push. |
| `notifications` | Email accounts, email queue backend and task. |
| `audit` | Request logging, `CRUDLog`. |

## Run locally

```
python -m venv .venv && .venv/Scripts/activate      # Python 3.12
pip install -r requirements.txt
cp .env.example .env                                # fill in SECRET_KEY and database
python manage.py migrate
python manage.py runserver
python manage.py procrastinate worker               # background jobs, separate terminal
```

Or with Docker: `docker compose up --build`.

Tests: `python manage.py test`.

## API

- `/api/v1/` application endpoints. Schema at `/api/v1/schema/`, Swagger at `/api/v1/docs/`.
- `/_allauth/app/v1/` sign-up, login, logout, email verification, password reset, Google sign-in, MFA, sessions.
  Login returns `meta.session_token`; send it on every request as `X-Session-Token`.
- `/api/v1/sync/pull/?workspace=<id>&since=<seq>` changes since a cursor, per table, tombstones included.
- `/api/v1/sync/push/` a batch of client mutations (`upsert`/`delete`), each with a client UUID so retries apply once.
  Upserts carry only the changed columns, so concurrent edits to different fields both survive.
  Sync has its own rate limit (`sync` scope), separate from the rest of the API.
- `/api/v1/me/` profile, plus `onboarded_at` and `primary_mode` so onboarding is asked once per account.
- `POST /api/v1/workspaces/` creates a business; an optional client `id` makes retries return the same workspace.
- `/health/` liveness; `/health/?db=1` also checks the database.

## Rules the code relies on

- **Money** is an integer in minor units (`amount_minor`) plus an ISO 4217 `currency`. No floats.
- **Tenant data** lives in models that inherit `WorkspaceOwnedModel`. Each such table needs
  `workspaces.rls.enable_rls` in a migration, and each view on it needs `TenantScopedMixin`.
  Tests fail if a table is missed.
- **Synced tables** are listed in `sync/registry.py` and need `sync.sql.enable_sync` in a migration
  (a trigger stamps `server_seq`). Tests fail if a tenant table lacks it.
- **Ids** are UUIDv7 (`spendroo.ids.uuid7`); clients generate the same kind offline.
- **Deletes** are tombstones (`soft_delete()`), never SQL deletes, so clients can sync them.
  Deleting a cashbook tombstones its entries, categories, payment methods and grants too.
- **Budgets** are per expense category: one recurring (`month` empty) plus optional one-month overrides.
- **Transfers** are two transactions sharing `transfer_group_id`, moving money in opposite directions.
- **Edit history** is written by database triggers (django-pghistory) into `*Event` tables.
- **Secrets stored in the database** use `spendroo.fields.EncryptedTextField`.
- The **database role** must not be a PostgreSQL superuser in production; superusers skip row-level security.
