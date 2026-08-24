# Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an AWS-free, password-only Redshift connection foundation on Django's public base-backend classes without activating it through the existing `ENGINE` entry point.

**Architecture:** Production settings validation and AWS driver calls live only in `driver.py`; an internal `_backend.py` composes the connection lifecycle with conservative Django base components. `client.py` preserves `psql` behavior and `creation.py` rejects unsupported database provisioning, while the current `base.py` remains untouched until the final activation layer.

**Tech Stack:** Python 3.10-3.14, Django 4.2.30/5.2/6.0/6.1 public base backend APIs, `redshift-connector>=2.1.14,<3`, pytest, uv, Ruff 0.6.2, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-24-backend-foundation-design.md`

## Global Constraints

- Support only username/password authentication in this layer.
- Require non-empty top-level `USER` and `PASSWORD`; they override duplicate `OPTIONS` values.
- Reject all 45 inventoried alternate-authentication options before a driver or socket call.
- Keep `django_redshift_backend.base.DatabaseWrapper` and `ENGINE = "django_redshift_backend"` behavior unchanged.
- Import and call `redshift_connector` only from `django_redshift_backend/driver.py` in production code.
- Inherit only from Django's public `django.db.backends.base` classes.
- Do not change `meta.py`, `distkey.py`, `DistKey`, `SortKey`, migrations, or database schema.
- Do not require AWS credentials, `psql`, or a real Redshift cluster in tests.
- Use uv for all Python environment and test commands.

---

### Task 1: Promote the investigated driver contract into production

**Files:**
- Create: `django_redshift_backend/driver.py`
- Modify: `driver_tests/test_connect_options.py`
- Modify: `driver_tests/test_django_exceptions.py`
- Delete: `driver_tests/option_contract.py`

**Interfaces:**
- Consumes: Django `ImproperlyConfigured`; public `redshift_connector.connect` and DB-API exception namespace.
- Produces: `Database`, `build_connect_kwargs(settings_dict)`, `connect(**kwargs)`, `classify_options(options)`, `classify_dbshell_options(options)`, and `redact_connect_kwargs(kwargs)`.

- [ ] **Step 1: Point option tests at the not-yet-created production module**

Replace the imports in `driver_tests/test_connect_options.py`:

```python
from django.core.exceptions import ImproperlyConfigured

from django_redshift_backend.driver import (
    DBSHELL_OPTIONS,
    DEFERRED_AUTH_OPTIONS,
    REQUIRED_DRIVER_OPTIONS,
    build_connect_kwargs,
    classify_dbshell_options,
    classify_options,
    connect,
    redact_connect_kwargs,
)
```

Replace each configuration assertion from `pytest.raises(ValueError, ...)` to
`pytest.raises(ImproperlyConfigured, ...)`. Add this delegation test:

```python
def test_connect_delegates_only_validated_keyword_arguments(monkeypatch):
    calls = []
    expected = object()

    def fake_connect(**kwargs):
        calls.append(kwargs)
        return expected

    monkeypatch.setattr("django_redshift_backend.driver.Database.connect", fake_connect)

    result = connect(user="alice", password="secret", host="example.test")

    assert result is expected
    assert calls == [{"user": "alice", "password": "secret", "host": "example.test"}]


def test_invalid_port_is_a_redacted_configuration_error():
    settings = {
        "USER": "alice",
        "PASSWORD": "secret",
        "PORT": "not-a-port",
        "OPTIONS": {},
    }
    with pytest.raises(ImproperlyConfigured, match="PORT must be an integer") as error:
        build_connect_kwargs(settings)
    assert "not-a-port" not in str(error.value)
```

- [ ] **Step 2: Verify the production import fails**

Run:

```powershell
uv run --project driver_tests --python 3.12 --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests/test_connect_options.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'django_redshift_backend.driver'`.

- [ ] **Step 3: Promote the prototype with Django configuration errors**

Create `django_redshift_backend/driver.py` from the exact constants and option
classification logic currently in `driver_tests/option_contract.py`. Make these
specific production changes:

```python
import inspect

import redshift_connector as Database
from django.core.exceptions import ImproperlyConfigured


def _configuration_error(message):
    raise ImproperlyConfigured(message)


def connect(**kwargs):
    return Database.connect(**kwargs)
```

Within `classify_options()`, `classify_dbshell_options()`, and
`_require_nonempty()`, replace every `raise ValueError(message)` with
`_configuration_error(message)`. Inspect the public signature through
`Database.connect`:

```python
public_driver_options = set(inspect.signature(Database.connect).parameters)
```

Keep `STANDARD_SETTING_MAP`, `DRIVER_SSLMODES`, `DBSHELL_SSLMODES`, all 45
`DEFERRED_AUTH_OPTIONS`, `REQUIRED_DRIVER_OPTIONS`, `DBSHELL_OPTIONS`,
`REJECTED_LEGACY_OPTIONS`, and `SENSITIVE_OPTIONS` byte-for-byte equivalent to
the investigated contract. Delete `driver_tests/option_contract.py` after all
tests import the production module.

Convert `PORT` without exposing its value in an exception:

```python
for setting_name, driver_name in STANDARD_SETTING_MAP.items():
    value = settings_dict.get(setting_name)
    if value in (None, ""):
        continue
    if setting_name == "PORT":
        try:
            value = int(value)
        except (TypeError, ValueError):
            _configuration_error("PORT must be an integer")
    driver[driver_name] = value
```

- [ ] **Step 4: Use the production exception namespace in Django wrapping tests**

Update `driver_tests/test_django_exceptions.py`:

```python
from django_redshift_backend.driver import Database


class Wrapper:
    Database = Database
```

Construct each source exception with `getattr(Database, name)` instead of
importing `redshift_connector` directly.

- [ ] **Step 5: Run driver option and exception tests**

Run:

```powershell
uv run --project driver_tests --python 3.12 --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests/test_connect_options.py driver_tests/test_django_exceptions.py -q
```

Expected: all selected tests pass, including all 45 authentication rejections.

- [ ] **Step 6: Confirm no test-only contract implementation remains**

Run:

```powershell
rg -n "option_contract|import redshift_connector" driver_tests django_redshift_backend -g "*.py"
```

Expected: no `option_contract` references; the production driver import appears
only in `django_redshift_backend/driver.py`. Direct driver imports may remain in
metadata/surface investigation tests that inspect the third-party package itself.

- [ ] **Step 7: Commit the production driver boundary**

```powershell
git add django_redshift_backend/driver.py driver_tests
git commit -m "feat: add Redshift driver boundary"
```

---

### Task 2: Implement the internal base wrapper lifecycle

**Files:**
- Create: `django_redshift_backend/_backend.py`
- Create: `driver_tests/test_backend_wrapper.py`
- Modify: `driver_tests/test_django_exceptions.py`

**Interfaces:**
- Consumes: `driver.Database`, `driver.build_connect_kwargs()`, `driver.connect()`, `client.DatabaseClient`, and `creation.DatabaseCreation` (introduced in later tasks; use Django base classes until those files exist, then switch the class attributes in their tasks).
- Produces: internal `django_redshift_backend._backend.DatabaseWrapper` with `get_connection_params()`, `get_new_connection()`, `init_connection_state()`, `create_cursor()`, `_set_autocommit()`, and `is_usable()`.

- [ ] **Step 1: Write fake DB-API objects and failing lifecycle tests**

Create `driver_tests/test_backend_wrapper.py`:

```python
from unittest.mock import patch

import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.utils import NotSupportedError

from django_redshift_backend import driver
from django_redshift_backend._backend import DatabaseWrapper


class FakeCursor:
    def __init__(self, error=None):
        self.error = error
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, sql):
        if self.error:
            raise self.error
        self.executed.append(sql)


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.autocommit = False

    def cursor(self):
        return self._cursor


def settings_dict(**overrides):
    values = {
        "NAME": "warehouse",
        "HOST": "example.test",
        "PORT": "5439",
        "USER": "alice",
        "PASSWORD": "secret",
        "OPTIONS": {},
        "TIME_ZONE": None,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "AUTOCOMMIT": True,
    }
    values.update(overrides)
    return values


def test_wrapper_uses_public_base_backend():
    assert issubclass(DatabaseWrapper, BaseDatabaseWrapper)
    assert DatabaseWrapper.vendor == "redshift"
    assert DatabaseWrapper.Database is driver.Database


def test_connection_params_use_password_contract():
    wrapper = DatabaseWrapper(settings_dict(), "default")
    assert wrapper.get_connection_params() == {
        "database": "warehouse",
        "host": "example.test",
        "port": 5439,
        "user": "alice",
        "password": "secret",
    }


def test_new_connection_delegates_to_driver(monkeypatch):
    wrapper = DatabaseWrapper(settings_dict(), "default")
    expected = object()
    calls = []
    monkeypatch.setattr(driver, "connect", lambda **kwargs: calls.append(kwargs) or expected)
    params = {"user": "alice", "password": "secret"}
    assert wrapper.get_new_connection(params) is expected
    assert calls == [params]


def test_create_cursor_rejects_named_cursor():
    wrapper = DatabaseWrapper(settings_dict(), "default")
    wrapper.connection = FakeConnection(FakeCursor())
    assert wrapper.create_cursor() is wrapper.connection._cursor
    with pytest.raises(NotSupportedError, match="named cursor"):
        wrapper.create_cursor(name="server-side")


def test_autocommit_uses_public_driver_attribute():
    wrapper = DatabaseWrapper(settings_dict(), "default")
    wrapper.connection = FakeConnection(FakeCursor())
    wrapper._set_autocommit(True)
    assert wrapper.connection.autocommit is True


def test_init_connection_state_delegates_without_session_sql():
    wrapper = DatabaseWrapper(settings_dict(), "foundation-test")
    wrapper.connection = FakeConnection(FakeCursor())
    with patch.object(BaseDatabaseWrapper, "init_connection_state") as initialize:
        wrapper.init_connection_state()
    initialize.assert_called_once_with()
    assert wrapper.connection._cursor.executed == []


def test_is_usable_executes_health_query():
    cursor = FakeCursor()
    wrapper = DatabaseWrapper(settings_dict(), "default")
    wrapper.connection = FakeConnection(cursor)
    assert wrapper.is_usable() is True
    assert cursor.executed == ["SELECT 1"]


def test_is_usable_swallows_driver_error():
    cursor = FakeCursor(driver.Database.OperationalError("offline"))
    wrapper = DatabaseWrapper(settings_dict(), "default")
    wrapper.connection = FakeConnection(cursor)
    assert wrapper.is_usable() is False
```

- [ ] **Step 2: Verify wrapper tests fail before implementation**

Run:

```powershell
uv run --project driver_tests --python 3.12 --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests/test_backend_wrapper.py -q
```

Expected: collection fails because `django_redshift_backend._backend` does not exist.

- [ ] **Step 3: Implement the minimal internal wrapper**

Create `django_redshift_backend/_backend.py`:

```python
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.base.client import BaseDatabaseClient
from django.db.backends.base.creation import BaseDatabaseCreation
from django.db.backends.base.features import BaseDatabaseFeatures
from django.db.backends.base.introspection import BaseDatabaseIntrospection
from django.db.backends.base.operations import BaseDatabaseOperations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.utils import NotSupportedError

from . import driver


class DatabaseWrapper(BaseDatabaseWrapper):
    vendor = "redshift"
    display_name = "Amazon Redshift"
    Database = driver.Database

    client_class = BaseDatabaseClient
    creation_class = BaseDatabaseCreation
    features_class = BaseDatabaseFeatures
    introspection_class = BaseDatabaseIntrospection
    ops_class = BaseDatabaseOperations
    SchemaEditorClass = BaseDatabaseSchemaEditor

    data_types = {}
    data_types_suffix = {}
    data_type_check_constraints = {}

    def get_connection_params(self):
        return driver.build_connect_kwargs(self.settings_dict)

    def get_new_connection(self, conn_params):
        return driver.connect(**conn_params)

    def init_connection_state(self):
        super().init_connection_state()

    def create_cursor(self, name=None):
        if name is not None:
            raise NotSupportedError("Amazon Redshift does not support named cursors.")
        return self.connection.cursor()

    def _set_autocommit(self, autocommit):
        self.connection.autocommit = autocommit

    def is_usable(self):
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except self.Database.Error:
            return False
        return True
```

- [ ] **Step 4: Bind exception wrapping tests to the internal wrapper**

Replace the local test wrapper in `driver_tests/test_django_exceptions.py`:

```python
from django_redshift_backend._backend import DatabaseWrapper
```

At the start of each parameterized test, construct an uninitialized wrapper and
reset the state Django's error wrapper mutates:

```python
wrapper = DatabaseWrapper.__new__(DatabaseWrapper)
wrapper.errors_occurred = False
driver_exception = getattr(DatabaseWrapper.Database, name)
```

Pass that fresh `wrapper` to `DatabaseErrorWrapper`, proving Django
dereferences the production wrapper's `Database` namespace without carrying
`errors_occurred` between parameterized cases.

- [ ] **Step 5: Run lifecycle and exception tests**

Run:

```powershell
uv run --project driver_tests --python 3.12 --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests/test_backend_wrapper.py driver_tests/test_django_exceptions.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit the wrapper lifecycle**

```powershell
git add django_redshift_backend/_backend.py driver_tests/test_backend_wrapper.py driver_tests/test_django_exceptions.py
git commit -m "feat: add base wrapper connection lifecycle"
```

---

### Task 3: Preserve the psql dbshell contract

**Files:**
- Create: `django_redshift_backend/client.py`
- Create: `driver_tests/test_client.py`
- Modify: `django_redshift_backend/_backend.py`

**Interfaces:**
- Consumes: Django `BaseDatabaseClient` and `driver.classify_dbshell_options()`.
- Produces: `client.DatabaseClient.settings_to_cmd_args_env(settings_dict, parameters)` and `DatabaseWrapper.client_class`.

- [ ] **Step 1: Write failing dbshell argument and environment tests**

Create `driver_tests/test_client.py`:

```python
import pytest
from django.core.exceptions import ImproperlyConfigured

from django_redshift_backend.client import DatabaseClient


def test_psql_arguments_and_environment_preserve_existing_contract():
    settings = {
        "NAME": "warehouse",
        "HOST": "example.test",
        "PORT": 5439,
        "USER": "alice",
        "PASSWORD": "secret",
        "OPTIONS": {
            "passfile": "/tmp/pgpass",
            "service": "analytics",
            "sslmode": "require",
            "sslrootcert": "/tmp/root.crt",
            "sslcert": "/tmp/client.crt",
            "sslkey": "/tmp/client.key",
        },
    }

    args, env = DatabaseClient.settings_to_cmd_args_env(settings, ["-c", "SELECT 1"])

    assert args == [
        "psql", "-U", "alice", "-h", "example.test", "-p", "5439",
        "-c", "SELECT 1", "warehouse",
    ]
    assert env == {
        "PGPASSWORD": "secret",
        "PGPASSFILE": "/tmp/pgpass",
        "PGSERVICE": "analytics",
        "PGSSLMODE": "require",
        "PGSSLROOTCERT": "/tmp/root.crt",
        "PGSSLCERT": "/tmp/client.crt",
        "PGSSLKEY": "/tmp/client.key",
    }


def test_service_omits_default_database_and_empty_environment_is_none():
    args, env = DatabaseClient.settings_to_cmd_args_env(
        {"NAME": "", "HOST": "", "PORT": "", "USER": "", "PASSWORD": "", "OPTIONS": {"service": "analytics"}},
        [],
    )
    assert args == ["psql"]
    assert env == {"PGSERVICE": "analytics"}


def test_missing_name_and_service_uses_postgres_database():
    args, env = DatabaseClient.settings_to_cmd_args_env(
        {"NAME": "", "HOST": "", "PORT": "", "USER": "", "PASSWORD": "", "OPTIONS": {}},
        [],
    )
    assert args == ["psql", "postgres"]
    assert env is None


def test_invalid_psql_sslmode_is_rejected():
    with pytest.raises(ImproperlyConfigured, match="Unsupported psql sslmode"):
        DatabaseClient.settings_to_cmd_args_env(
            {"NAME": "warehouse", "OPTIONS": {"sslmode": "invalid"}}, []
        )
```

- [ ] **Step 2: Verify client tests fail before implementation**

Run:

```powershell
uv run --project driver_tests --python 3.12 --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests/test_client.py -q
```

Expected: collection fails because `django_redshift_backend.client` does not exist.

- [ ] **Step 3: Implement the independent psql client**

Create `django_redshift_backend/client.py` with the argument ordering from
Django's PostgreSQL client but no PostgreSQL backend import:

```python
from django.db.backends.base.client import BaseDatabaseClient

from .driver import classify_dbshell_options


class DatabaseClient(BaseDatabaseClient):
    executable_name = "psql"

    @classmethod
    def settings_to_cmd_args_env(cls, settings_dict, parameters):
        options = classify_dbshell_options(settings_dict.get("OPTIONS", {}))
        host = settings_dict.get("HOST")
        port = settings_dict.get("PORT")
        dbname = settings_dict.get("NAME")
        user = settings_dict.get("USER")
        password = settings_dict.get("PASSWORD")

        if not dbname and not options.get("service"):
            dbname = "postgres"

        args = [cls.executable_name]
        if user:
            args.extend(["-U", user])
        if host:
            args.extend(["-h", host])
        if port:
            args.extend(["-p", str(port)])
        args.extend(parameters)
        if dbname:
            args.append(dbname)

        option_environment = {
            "passfile": "PGPASSFILE",
            "service": "PGSERVICE",
            "sslmode": "PGSSLMODE",
            "sslrootcert": "PGSSLROOTCERT",
            "sslcert": "PGSSLCERT",
            "sslkey": "PGSSLKEY",
        }
        env = {environment: str(options[name]) for name, environment in option_environment.items() if options.get(name)}
        if password:
            env["PGPASSWORD"] = str(password)
        return args, env or None
```

- [ ] **Step 4: Register the client on the internal wrapper**

In `django_redshift_backend/_backend.py`:

```python
from .client import DatabaseClient


class DatabaseWrapper(BaseDatabaseWrapper):
    client_class = DatabaseClient
```

Remove the now-unused `BaseDatabaseClient` import.

- [ ] **Step 5: Run dbshell and wrapper tests**

Run:

```powershell
uv run --project driver_tests --python 3.12 --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests/test_client.py driver_tests/test_backend_wrapper.py -q
```

Expected: all selected tests pass and no test spawns `psql`.

- [ ] **Step 6: Commit the independent dbshell client**

```powershell
git add django_redshift_backend/client.py django_redshift_backend/_backend.py driver_tests/test_client.py
git commit -m "feat: preserve Redshift dbshell contract"
```

---

### Task 4: Reject unsupported test database provisioning

**Files:**
- Create: `django_redshift_backend/creation.py`
- Create: `driver_tests/test_creation.py`
- Create: `driver_tests/test_activation_boundary.py`
- Modify: `django_redshift_backend/_backend.py`

**Interfaces:**
- Consumes: Django `BaseDatabaseCreation` and `NotSupportedError`.
- Produces: `creation.DatabaseCreation` and `DatabaseWrapper.creation_class`.

- [ ] **Step 1: Write failing no-SQL creation tests**

Create `driver_tests/test_creation.py`:

```python
import pytest
from django.db.backends.base.creation import BaseDatabaseCreation
from django.db.utils import NotSupportedError

from django_redshift_backend.creation import DatabaseCreation


class ConnectionThatMustNotBeUsed:
    settings_dict = {"NAME": "warehouse"}

    def cursor(self):
        raise AssertionError("test database rejection must happen before SQL")

    def close(self):
        raise AssertionError("test database rejection must happen before close")


@pytest.mark.parametrize(
    ("method_name", "args"),
    [
        ("create_test_db", ()),
        ("clone_test_db", ("worker-1",)),
        ("destroy_test_db", ()),
    ],
)
def test_test_database_operations_are_rejected_before_connection_use(method_name, args):
    creation = DatabaseCreation(ConnectionThatMustNotBeUsed())
    assert isinstance(creation, BaseDatabaseCreation)
    with pytest.raises(NotSupportedError, match=method_name):
        getattr(creation, method_name)(*args)
```

- [ ] **Step 2: Write the activation-boundary test**

Create `driver_tests/test_activation_boundary.py`:

```python
from pathlib import Path


def test_existing_engine_entry_point_is_not_activated():
    base_source = (
        Path(__file__).parents[1] / "django_redshift_backend" / "base.py"
    ).read_text(encoding="utf-8")
    assert "from ._backend import" not in base_source
    assert "from django_redshift_backend._backend import" not in base_source
```

This static guard intentionally avoids importing the current psycopg2-backed
entry point in the isolated driver environment.

- [ ] **Step 3: Verify creation tests fail before implementation**

Run:

```powershell
uv run --project driver_tests --python 3.12 --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests/test_creation.py driver_tests/test_activation_boundary.py -q
```

Expected: creation test collection fails because
`django_redshift_backend.creation` does not exist; the activation guard passes.

- [ ] **Step 4: Implement explicit creation rejection**

Create `django_redshift_backend/creation.py`:

```python
from django.db.backends.base.creation import BaseDatabaseCreation
from django.db.utils import NotSupportedError


class DatabaseCreation(BaseDatabaseCreation):
    def create_test_db(
        self, verbosity=1, autoclobber=False, serialize=None, keepdb=False
    ):
        raise NotSupportedError("create_test_db is not supported by Amazon Redshift.")

    def clone_test_db(self, suffix, verbosity=1, autoclobber=False, keepdb=False):
        raise NotSupportedError("clone_test_db is not supported by Amazon Redshift.")

    def destroy_test_db(
        self, old_database_name=None, verbosity=1, keepdb=False, suffix=None
    ):
        raise NotSupportedError("destroy_test_db is not supported by Amazon Redshift.")
```

The `serialize=None` signature accepts calls from all supported Django versions;
its differing historical default cannot affect an operation that always fails
before reading the argument.

- [ ] **Step 5: Register creation and assert component construction**

In `django_redshift_backend/_backend.py`:

```python
from .creation import DatabaseCreation


class DatabaseWrapper(BaseDatabaseWrapper):
    creation_class = DatabaseCreation
```

Remove the unused `BaseDatabaseCreation` import and add to
`driver_tests/test_backend_wrapper.py`:

```python
from django_redshift_backend.creation import DatabaseCreation


def test_wrapper_registers_foundation_components():
    wrapper = DatabaseWrapper(settings_dict(), "default")
    assert wrapper.client.__class__.__name__ == "DatabaseClient"
    assert isinstance(wrapper.creation, DatabaseCreation)
```

- [ ] **Step 6: Run creation, activation, and wrapper tests**

Run:

```powershell
uv run --project driver_tests --python 3.12 --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests/test_creation.py driver_tests/test_activation_boundary.py driver_tests/test_backend_wrapper.py -q
```

Expected: all selected tests pass without accessing connection methods.

- [ ] **Step 7: Commit explicit provisioning behavior**

```powershell
git add django_redshift_backend/creation.py django_redshift_backend/_backend.py driver_tests/test_creation.py driver_tests/test_activation_boundary.py driver_tests/test_backend_wrapper.py
git commit -m "feat: define Redshift test database limits"
```

---

### Task 5: Verify the complete foundation across the supported matrix

**Files:**
- Verify unchanged: `.github/workflows/driver-contract.yml`
- Verify unchanged: `pyproject.toml`
- Test: `driver_tests/`
- Test: `tests/`

**Interfaces:**
- Consumes: all production and test interfaces from Tasks 1-4.
- Produces: a fully green, AWS-free Backend foundation branch ready for its stacked PR.

- [ ] **Step 1: Run the complete representative contract suite**

```powershell
uv run --project driver_tests --python 3.12 --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests -q
```

Expected: all driver investigation and foundation tests pass.

- [ ] **Step 2: Run the driver security-floor and investigated-release checks**

```powershell
uv run --project driver_tests --python 3.12 --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --project driver_tests --python 3.14 --with "Django~=6.1.0" --with "redshift-connector==2.1.16" pytest driver_tests -q
```

Expected: both complete suites pass.

- [ ] **Step 3: Run every blocking compatibility cell**

Execute every one of the 15 exact combinations in
`.github/workflows/driver-contract.yml`:

```powershell
uv run --project driver_tests --python 3.10 --with "Django==4.2.30" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --project driver_tests --python 3.11 --with "Django==4.2.30" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --project driver_tests --python 3.12 --with "Django==4.2.30" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --project driver_tests --python 3.10 --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --project driver_tests --python 3.11 --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --project driver_tests --python 3.12 --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --project driver_tests --python 3.13 --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --project driver_tests --python 3.14 --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --project driver_tests --python 3.12 --with "Django~=6.0.0" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --project driver_tests --python 3.13 --with "Django~=6.0.0" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --project driver_tests --python 3.14 --with "Django~=6.0.0" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --project driver_tests --python 3.12 --with "Django~=6.1.0" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --project driver_tests --python 3.13 --with "Django~=6.1.0" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --project driver_tests --python 3.14 --with "Django~=6.1.0" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --project driver_tests --python 3.14 --with "Django~=6.1.0" --with "redshift-connector==2.1.16" pytest driver_tests -q
```

Expected: all 15 cells pass with the same test count within a given driver
contract; no cell skips a foundation test.

- [ ] **Step 4: Run the unchanged current-backend regression suite**

```powershell
uv --cache-dir .uv-cache run --python 3.12 --with pytest --with pytest-cov --with mock --with django-environ --with psycopg2-binary pytest -q
```

Expected: 10 passed, 22 skipped, with only the existing deprecation warning.

- [ ] **Step 5: Run lint and packaging checks**

```powershell
uv --cache-dir .uv-cache run --with tox tox -e lint
uv --cache-dir .uv-cache run --with build --with twine python -m build
uv --cache-dir .uv-cache run --with twine twine check dist/*
$wheel = Get-ChildItem dist/*.whl | Select-Object -First 1
uv --cache-dir .uv-cache run python -m zipfile -l $wheel.FullName
```

Expected: lint, sdist/wheel build, and metadata checks pass. Inspect the wheel
and confirm it contains `django_redshift_backend/driver.py`, `_backend.py`,
`client.py`, and `creation.py`, and contains no `driver_tests` package.

- [ ] **Step 6: Verify architectural boundaries statically**

```powershell
rg -n "import redshift_connector|from redshift_connector" django_redshift_backend -g "*.py"
rg -n "django\.db\.backends\.postgresql|_vendor" django_redshift_backend/_backend.py django_redshift_backend/driver.py django_redshift_backend/client.py django_redshift_backend/creation.py
git diff redesign/01-driver-investigation -- django_redshift_backend/base.py django_redshift_backend/meta.py django_redshift_backend/distkey.py
git diff redesign/01-driver-investigation -- pyproject.toml .github/workflows/driver-contract.yml
git diff --check
```

Expected: only `driver.py` imports the AWS driver; no new foundation module
imports PostgreSQL or vendored code; the three compatibility files have no
diff; dependency metadata and the already-complete 15-cell workflow have no
diff; whitespace checks pass.

- [ ] **Step 7: Commit any verification-only correction**

If a matrix, lint, or package failure requires a correction, return to the task
that owns the failing interface, add a regression test there, repeat its
red/green cycle, and commit it with that task's files. If no correction is
required, do not create an empty commit.

- [ ] **Step 8: Prepare the stacked PR evidence**

Record in the child PR body:

- Base: `redesign/01-driver-investigation`
- Head: `redesign/02-backend-foundation`
- Password-only authentication scope
- Current `base.py` intentionally not activated
- All 15 compatibility results and root regression result
- Real Redshift and alternate authentication deferred
- No database migration or public migration-API change

Update tracking PR #1's stack checklist and add a milestone comment after the
child PR is published and GitHub Actions is green.
