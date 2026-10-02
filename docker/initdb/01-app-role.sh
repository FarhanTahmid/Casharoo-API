#!/bin/sh
# The application connects as a role that is NOT a superuser: PostgreSQL
# superusers skip row-level security, which is the second layer of tenant isolation.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE ROLE "$APP_DB_USER" LOGIN NOSUPERUSER NOBYPASSRLS CREATEDB PASSWORD '$APP_DB_PASSWORD';
    CREATE DATABASE "$APP_DB_NAME" OWNER "$APP_DB_USER";
EOSQL
