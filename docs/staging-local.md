# Staging on this machine (Cloudflare tunnel)

Until there is a server, staging runs on the founder's PC: the API with
production settings, published through a free Cloudflare *quick tunnel*.
Testers' phones reach it over HTTPS at a random `https://<words>.trycloudflare.com`
address. It works only while the PC is on and the tunnel is running.

## One-time setup

1. **cloudflared:** `winget install Cloudflare.cloudflared`
2. **Either Docker Desktop** (recommended; also checks the production image)
   **or** the no-Docker mode below.
3. **Email:** sign-up and password reset send codes by email, so staging needs
   a real SMTP account. Brevo's free tier (300 mails/day) or a Gmail address
   with an [app password](https://myaccount.google.com/apppasswords) both work.
4. `copy .env.staging.example .env.staging` and fill in `SECRET_KEY`,
   `FIELD_ENCRYPTION_KEYS` and the `EMAIL_*` values (commands for the keys are
   in the file). `.env.staging` is gitignored.

### No-Docker mode only

Create a database and a role that is **not** a superuser (superusers skip
row-level security, the second layer of tenant isolation):

```
psql -U postgres -c "CREATE ROLE casharoo_staging LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'choose-one'"
psql -U postgres -c "CREATE DATABASE casharoo_staging OWNER casharoo_staging"
```

and set `PROD_DATABASE_*` in `.env.staging` to match.

## Start and stop

```
./scripts/staging-up.ps1              # Docker
./scripts/staging-up.ps1 -Mode venv   # this machine's PostgreSQL + .venv + waitress
```

The script migrates, starts the API and the email worker, waits for
`/health/?db=1`, then starts the tunnel and prints:

```
  Server address for the app (Settings -> Server): https://example-words.trycloudflare.com
```

Ctrl+C stops the tunnel. `./scripts/staging-down.ps1` (add `-Mode venv` if
used) stops the API and worker; the data stays.

## Testers

Give testers the staging APK (`docs/release.md` in the app repo) and the
address above. In the app: **Settings → Server**, paste, confirm, sign up.
The address changes every time the tunnel restarts; send the new one and
testers paste it again (that signs them out; their data is on the server).

## Checks

- `curl https://<address>/health/?db=1` → `{"status": "ok", "database": "ok"}`
- Sign up from the app; the code email arrives (if not, see the worker log:
  `docker compose logs worker`, or `logs\staging-worker.err.log`).
- Admin: `https://<address>/<ADMIN_URL>` after
  `python manage.py createsuperuser` (in Docker:
  `docker compose -f docker-compose.yml -f docker-compose.staging.yml exec web python manage.py createsuperuser`).

## How it is wired

- `docker-compose.staging.yml` layers production settings over the dev
  compose file: `PROJECT_ENVIRONMENT=production`, its own database volume,
  port 8000 bound to `127.0.0.1` only.
- `STAGING_TUNNEL=1` adds `.trycloudflare.com` to `ALLOWED_HOSTS` and
  `CSRF_TRUSTED_ORIGINS`; `TRUSTED_PROXY_COUNT=1` trusts cloudflared's
  `X-Forwarded-Proto`, so HTTPS redirects and secure cookies behave as in production.
- Later: a named tunnel on the real domain (`cloudflared tunnel create`, a DNS
  route for `staging-api.<domain>`) gives a fixed address, and then the
  app's `config/staging.json` can point at it directly.
