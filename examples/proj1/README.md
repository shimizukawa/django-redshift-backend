# Django Redshift backend example project

`proj1` is a small Django project for exercising this repository's
`django-redshift-backend` implementation against a database. It is intended
for development, manual investigation, and reproduction of backend behavior;
it is not a production application.

The project has its own uv lockfile and virtual environment. The backend is
installed as an editable dependency from the repository root, so local backend
changes are immediately available to this project.

## Set up the project

From the repository root, create or update `examples/proj1/.venv`:

```powershell
uv sync --directory examples/proj1
```

Dependencies are declared in `pyproject.toml` and pinned in `uv.lock`.

## Configure the database

Copy `.env.sample` to an ignored `.env` file and replace the example values:

```powershell
Copy-Item examples/proj1/.env.sample examples/proj1/.env
```

`config/settings.py` reads these values:

- `DATABASE_URL`: a `redshift://` URL containing the username, URL-encoded
  password, endpoint, port, and database name.
- `SECRET_KEY`: a temporary value is sufficient for local validation.
- `DEBUG`: optional; it defaults to `False`.

Set `ENV_FILE` to an alternate file path when you do not want to use
`examples/proj1/.env`. Environment variables can also be supplied directly.
Never commit credentials or a populated `.env` file.

## Run Django commands

Commands can be run from the repository root without activating the virtual
environment:

```powershell
uv run --directory examples/proj1 python manage.py check
uv run --directory examples/proj1 python manage.py migrate
uv run --directory examples/proj1 python manage.py shell
```

Use the shell, management commands, or temporary reproduction code to exercise
the ORM behavior under investigation. Keep test data disposable and remove it
after validation.

## Optional disposable Redshift environment

If an existing Redshift database is not available, the Python CDK app in
[`../cdk`](../cdk/README.md) can create a temporary Redshift Serverless
environment. Put its endpoint, port, database, username, and the password used
during deployment into `DATABASE_URL`. The CDK stack is operated separately
and must be destroyed after validation.
