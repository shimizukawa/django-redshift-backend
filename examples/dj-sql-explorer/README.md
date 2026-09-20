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
