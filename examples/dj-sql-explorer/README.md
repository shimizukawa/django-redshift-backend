# Django SQL Explorer example

This example runs `django-sql-explorer` against a database configured through
`DATABASE_URL`. It has its own uv environment so its optional dependencies do
not affect the repository's development environment.

From the repository root, install the locked dependencies:

```console
uv sync --directory examples/dj-sql-explorer
```

Copy `.env.sample` to `.env` and replace the sample `DATABASE_URL` credentials
and endpoint with a reachable Redshift database. Then run Django commands from
the example environment:

```console
uv run --directory examples/dj-sql-explorer python manage.py check
uv run --directory examples/dj-sql-explorer python manage.py migrate
uv run --directory examples/dj-sql-explorer python manage.py runserver
```

Open `/explorer/` after starting the server. The example is intended for local
validation only; do not expose it publicly or use production credentials.

## Redshift migration limitation

The complete django-sql-explorer migration history currently requires table
rebuilds that the backend does not yet automate. On a fresh validation database,
the affected tables are empty:

- `0018_alter_databaseconnection_host_and_more` changes encrypted connection
  fields from `varchar` to `varbyte`.
- `0028_promptlog_database_connection_promptlog_user_request` adds a
  `NOT NULL` field without retaining a database default.

For disposable validation environments only, verify the affected table has no
rows, recreate it from the target migration state, and fake-apply that migration
before continuing. Never use this workaround when either table contains data.
General, data-preserving table rebuild support is tracked in
[django-redshift-backend#189](https://github.com/jazzband/django-redshift-backend/issues/189).
