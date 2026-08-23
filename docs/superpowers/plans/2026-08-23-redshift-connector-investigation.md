# AWS Redshift Connector Investigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a reviewable GO/NO-GO decision for adopting AWS's public
`redshift_connector` DB-API without activating the redesigned backend.

**Architecture:** Keep the investigation harness under `driver_tests/`, isolated
from the current package's `django<5.2` dependency and database-dependent
fixtures. Test only public driver APIs, model the future Django settings
crosswalk in a non-runtime contract helper, and record behaviors that require a
real Redshift service as deferred rather than claiming they were verified.

**Tech Stack:** Python 3.10-3.14, Django 4.2.30/5.2/6.0/6.1, uv,
pytest, `redshift_connector` 2.1.14 and 2.1.16, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-23-redshift-backend-redesign-design.md`

## Global Constraints

- Start `redesign/01-driver-investigation` from `redesign/00-plan`; its PR base
  is `redesign/00-plan`.
- Use uv for every environment, dependency, and test command.
- Do not import or depend on a private `redshift_connector` module or member.
- Do not open a socket or require AWS credentials in normal CI.
- Do not activate `redshift_connector` in `django_redshift_backend.base` in this
  PR.
- Test the security floor `redshift_connector==2.1.14` and the investigated
  release `redshift_connector==2.1.16`; the proposed GO constraint is
  `redshift-connector>=2.1.14,<3`.
- Treat Django 4.2.30 as a bounded compatibility bridge on Python 3.10-3.12.
- Test Django 5.2 on Python 3.10-3.14 and Django 6.0/6.1 on Python 3.12-3.14.
- Never log or snapshot passwords, access keys, secret keys, session tokens,
  client secrets, web identity tokens, or bearer tokens.
- A failed must-pass contract produces NO-GO and stops work before the backend
  foundation layer.

---

## File Structure

- `driver_tests/pyproject.toml`: isolated uv project for the investigation.
- `driver_tests/uv.lock`: exact investigation dependency resolution.
- `driver_tests/__init__.py`: makes the contract helper import path explicit.
- `driver_tests/option_contract.py`: non-runtime prototype of option
  classification, precedence, and redaction.
- `driver_tests/test_metadata_contract.py`: supported Python, version floor,
  DB-API constants, exceptions, and constructors.
- `driver_tests/test_connect_options.py`: public `connect()` parameters and the
  settings/options crosswalk.
- `driver_tests/test_django_exceptions.py`: Django `DatabaseErrorWrapper`
  compatibility.
- `driver_tests/test_connection_cursor_contract.py`: public connection and
  cursor surface, including explicit named-cursor limitations.
- `.github/workflows/driver-contract.yml`: AWS-free supported-version matrix.
- `docs/superpowers/research/2026-08-23-redshift-connector-investigation.md`:
  evidence, dependency and license review, option crosswalk, deferred checks,
  and final GO/NO-GO decision.

### Task 1: Isolated uv Investigation Harness

**Files:**
- Create: `driver_tests/pyproject.toml`
- Create: `driver_tests/uv.lock`
- Create: `driver_tests/__init__.py`

**Interfaces:**
- Consumes: Python 3.10 or later and the repository checkout.
- Produces: `uv run --project driver_tests ...` as the command prefix used by
  every later task.

- [ ] **Step 1: Create the child branch from the approved parent**

```powershell
git switch redesign/00-plan
git switch -c redesign/01-driver-investigation
```

- [ ] **Step 2: Verify that the isolated project does not exist yet**

Run:

```powershell
uv run --project driver_tests python -c "import redshift_connector"
```

Expected: FAIL because `driver_tests/pyproject.toml` does not exist.

- [ ] **Step 3: Create the investigation project**

Create `driver_tests/pyproject.toml`:

```toml
[project]
name = "django-redshift-backend-driver-investigation"
version = "0.0.0"
requires-python = ">=3.10"
dependencies = [
    "packaging>=24",
    "pytest>=8,<9",
    "redshift-connector>=2.1.14,<3",
]
```

Create an empty `driver_tests/__init__.py`.

- [ ] **Step 4: Lock and smoke-test the isolated project**

Run:

```powershell
uv lock --project driver_tests
uv run --project driver_tests python -c "import redshift_connector; print(redshift_connector.__version__)"
```

Expected: the lock succeeds and the command prints `2.1.16` for the initial
investigation lock.

- [ ] **Step 5: Commit the harness**

```powershell
git add driver_tests/pyproject.toml driver_tests/uv.lock driver_tests/__init__.py
git commit -m "test: add isolated Redshift driver harness"
```

### Task 2: Package Metadata and DB-API Contract

**Files:**
- Create: `driver_tests/test_metadata_contract.py`

**Interfaces:**
- Consumes: `redshift_connector` selected by the isolated uv project.
- Produces: executable adoption requirements for version, Python support,
  DB-API level, parameter style, thread safety, exception hierarchy, and DB-API
  constructors.

- [ ] **Step 1: Write the public metadata and DB-API tests**

Create `driver_tests/test_metadata_contract.py`:

```python
import sys
from importlib.metadata import metadata, version

import redshift_connector
from packaging.specifiers import SpecifierSet
from packaging.version import Version


DRIVER_RANGE = SpecifierSet(">=2.1.14,<3")
DBAPI_EXCEPTIONS = (
    "Error",
    "InterfaceError",
    "DatabaseError",
    "DataError",
    "OperationalError",
    "IntegrityError",
    "InternalError",
    "ProgrammingError",
    "NotSupportedError",
)


def test_installed_driver_is_in_proposed_range():
    assert Version(version("redshift-connector")) in DRIVER_RANGE


def test_driver_metadata_supports_running_python():
    requires_python = SpecifierSet(metadata("redshift-connector")["Requires-Python"])
    running = ".".join(map(str, sys.version_info[:3]))
    assert requires_python.contains(running)


def test_dbapi_module_constants_match_django_sql_contract():
    assert redshift_connector.apilevel == "2.0"
    assert redshift_connector.paramstyle == "format"
    assert redshift_connector.threadsafety == 1


def test_dbapi_exception_namespace_is_complete():
    for name in DBAPI_EXCEPTIONS:
        exception = getattr(redshift_connector, name)
        assert issubclass(exception, Exception)
    assert issubclass(redshift_connector.InterfaceError, redshift_connector.Error)
    for name in DBAPI_EXCEPTIONS[2:]:
        assert issubclass(getattr(redshift_connector, name), redshift_connector.DatabaseError)


def test_dbapi_value_constructors_are_public():
    for name in (
        "Binary",
        "Date",
        "Time",
        "Timestamp",
        "DateFromTicks",
        "TimeFromTicks",
        "TimestampFromTicks",
    ):
        assert callable(getattr(redshift_connector, name))
```

- [ ] **Step 2: Run against the investigated release**

Run:

```powershell
uv run --project driver_tests --with redshift-connector==2.1.16 pytest driver_tests/test_metadata_contract.py -v
```

Expected: all four tests PASS.

- [ ] **Step 3: Run against the security floor**

Run:

```powershell
uv run --project driver_tests --with redshift-connector==2.1.14 pytest driver_tests/test_metadata_contract.py -v
```

Expected: all four tests PASS.

- [ ] **Step 4: Commit the DB-API contract**

```powershell
git add driver_tests/test_metadata_contract.py
git commit -m "test: record Redshift driver DB-API contract"
```

### Task 3: Connection Option Crosswalk Prototype

**Files:**
- Create: `driver_tests/option_contract.py`
- Create: `driver_tests/test_connect_options.py`

**Interfaces:**
- Consumes: a Django-style settings dictionary and the public signature of
  `redshift_connector.connect()`.
- Produces: `classify_options(options) -> tuple[dict, dict]`,
  `build_connect_kwargs(settings_dict) -> dict`, and
  `redact_connect_kwargs(kwargs) -> dict`. These are investigation helpers,
  not runtime backend APIs.

- [ ] **Step 1: Write failing crosswalk tests**

Create `driver_tests/test_connect_options.py`:

```python
import inspect

import pytest
import redshift_connector

from driver_tests.option_contract import (
    REQUIRED_DRIVER_OPTIONS,
    build_connect_kwargs,
    classify_options,
    redact_connect_kwargs,
)


def test_public_connect_signature_covers_required_modes():
    parameters = set(inspect.signature(redshift_connector.connect).parameters)
    assert REQUIRED_DRIVER_OPTIONS <= parameters


def test_standard_settings_map_and_override_duplicate_options():
    settings = {
        "NAME": "warehouse",
        "HOST": "redshift.example",
        "PORT": "5439",
        "USER": "app_user",
        "PASSWORD": "password-value",
        "OPTIONS": {
            "database": "ignored-option-database",
            "user": "ignored-option-user",
            "ssl": True,
            "iam": False,
        },
    }
    assert build_connect_kwargs(settings) == {
        "database": "warehouse",
        "host": "redshift.example",
        "port": 5439,
        "user": "app_user",
        "password": "password-value",
        "ssl": True,
        "iam": False,
    }


def test_dbshell_and_driver_options_are_classified_by_consumer():
    driver, dbshell = classify_options(
        {"sslmode": "verify-full", "passfile": "pgpass", "profile": "dev"}
    )
    assert driver == {"sslmode": "verify-full", "profile": "dev"}
    assert dbshell == {"sslmode": "verify-full", "passfile": "pgpass"}


@pytest.mark.parametrize(
    "name",
    ["options", "isolation_level", "cursor_factory", "connection_factory", "client_encoding"],
)
def test_legacy_psycopg2_options_are_rejected(name):
    with pytest.raises(ValueError, match=name):
        classify_options({name: "value"})


def test_unknown_options_are_rejected():
    with pytest.raises(ValueError, match="unknown_option"):
        classify_options({"unknown_option": True})


def test_credentials_are_redacted_without_changing_non_secrets():
    values = {
        "user": "app_user",
        "password": "password-value",
        "access_key_id": "access-key",
        "secret_access_key": "secret-key",
        "session_token": "session-token",
        "client_secret": "client-secret",
        "web_identity_token": "web-token",
        "token": "bearer-token",
        "region": "ap-northeast-1",
    }
    assert redact_connect_kwargs(values) == {
        "user": "app_user",
        "password": "********",
        "access_key_id": "********",
        "secret_access_key": "********",
        "session_token": "********",
        "client_secret": "********",
        "web_identity_token": "********",
        "token": "********",
        "region": "ap-northeast-1",
    }
```

- [ ] **Step 2: Run the crosswalk tests and confirm the helper is absent**

Run:

```powershell
uv run --project driver_tests pytest driver_tests/test_connect_options.py -v
```

Expected: collection FAILS with
`ModuleNotFoundError: No module named 'driver_tests.option_contract'`.

- [ ] **Step 3: Implement the smallest crosswalk helper**

Create `driver_tests/option_contract.py`:

```python
import inspect

import redshift_connector


STANDARD_SETTING_MAP = {
    "NAME": "database",
    "HOST": "host",
    "PORT": "port",
    "USER": "user",
    "PASSWORD": "password",
}
REQUIRED_DRIVER_OPTIONS = {
    "user",
    "database",
    "password",
    "port",
    "host",
    "ssl",
    "sslmode",
    "timeout",
    "application_name",
    "access_key_id",
    "secret_access_key",
    "session_token",
    "profile",
    "credentials_provider",
    "region",
    "cluster_identifier",
    "iam",
    "db_user",
    "role_arn",
    "is_serverless",
    "serverless_acct_id",
    "serverless_work_group",
    "web_identity_token",
    "token",
}
DBSHELL_OPTIONS = {
    "passfile",
    "service",
    "sslmode",
    "sslrootcert",
    "sslcert",
    "sslkey",
}
REJECTED_LEGACY_OPTIONS = {
    "options",
    "isolation_level",
    "cursor_factory",
    "connection_factory",
    "client_encoding",
}
SENSITIVE_OPTIONS = {
    "password",
    "access_key_id",
    "secret_access_key",
    "session_token",
    "client_secret",
    "web_identity_token",
    "token",
}


def classify_options(options):
    public_driver_options = set(inspect.signature(redshift_connector.connect).parameters)
    driver = {}
    dbshell = {}
    for name, value in options.items():
        if name in REJECTED_LEGACY_OPTIONS:
            raise ValueError(f"Unsupported legacy psycopg2 option: {name}")
        consumed = False
        if name in public_driver_options:
            driver[name] = value
            consumed = True
        if name in DBSHELL_OPTIONS:
            dbshell[name] = value
            consumed = True
        if not consumed:
            raise ValueError(f"Unknown database option: {name}")
    return driver, dbshell


def build_connect_kwargs(settings_dict):
    driver, _ = classify_options(settings_dict.get("OPTIONS", {}))
    for setting_name, driver_name in STANDARD_SETTING_MAP.items():
        value = settings_dict.get(setting_name)
        if value not in (None, ""):
            driver[driver_name] = int(value) if setting_name == "PORT" else value
    return driver


def redact_connect_kwargs(kwargs):
    return {
        name: "********" if name in SENSITIVE_OPTIONS and value is not None else value
        for name, value in kwargs.items()
    }
```

- [ ] **Step 4: Run both driver releases**

Run:

```powershell
uv run --project driver_tests --with redshift-connector==2.1.14 pytest driver_tests/test_connect_options.py -v
uv run --project driver_tests --with redshift-connector==2.1.16 pytest driver_tests/test_connect_options.py -v
```

Expected: all parameterized cases PASS for both releases.

- [ ] **Step 5: Commit the crosswalk prototype**

```powershell
git add driver_tests/option_contract.py driver_tests/test_connect_options.py
git commit -m "test: prototype Redshift connection option crosswalk"
```

### Task 4: Django Exception Translation Contract

**Files:**
- Create: `driver_tests/test_django_exceptions.py`

**Interfaces:**
- Consumes: the driver's public exception namespace and Django's public
  `DatabaseErrorWrapper`.
- Produces: proof that all nine exception names required by Django are present
  and translated without a psycopg2 adapter.

- [ ] **Step 1: Write the exception translation test**

Create `driver_tests/test_django_exceptions.py`:

```python
import pytest
import redshift_connector
from django import db
from django.db.utils import DatabaseErrorWrapper


EXCEPTION_NAMES = (
    "Error",
    "InterfaceError",
    "DatabaseError",
    "DataError",
    "OperationalError",
    "IntegrityError",
    "InternalError",
    "ProgrammingError",
    "NotSupportedError",
)


class Wrapper:
    Database = redshift_connector
    errors_occurred = False


@pytest.mark.parametrize("name", EXCEPTION_NAMES)
def test_django_translates_public_driver_exception(name):
    wrapper = Wrapper()
    driver_exception = getattr(redshift_connector, name)
    django_exception = getattr(db, name)
    with pytest.raises(django_exception):
        with DatabaseErrorWrapper(wrapper):
            raise driver_exception("contract probe")
    assert wrapper.errors_occurred is (name not in {"DataError", "IntegrityError"})
```

- [ ] **Step 2: Run on Django 4.2.30 and 5.2.8**

Run:

```powershell
uv run --project driver_tests --with Django==4.2.30 pytest driver_tests/test_django_exceptions.py -v
uv run --project driver_tests --with Django==5.2.8 pytest driver_tests/test_django_exceptions.py -v
```

Expected: all nine cases PASS on both Django versions.

- [ ] **Step 3: Run on Django 6.0 and 6.1**

Run:

```powershell
uv run --python 3.12 --project driver_tests --with "Django~=6.0.0" pytest driver_tests/test_django_exceptions.py -v
uv run --python 3.12 --project driver_tests --with "Django~=6.1.0" pytest driver_tests/test_django_exceptions.py -v
```

Expected: all nine cases PASS on both Django versions.

- [ ] **Step 4: Commit the Django exception contract**

```powershell
git add driver_tests/test_django_exceptions.py
git commit -m "test: verify Django maps Redshift driver exceptions"
```

### Task 5: Public Connection, Cursor, and Type Surface

**Files:**
- Create: `driver_tests/test_connection_cursor_contract.py`

**Interfaces:**
- Consumes: public `Connection` and `Cursor` classes.
- Produces: evidence for synchronous lifecycle methods, `%s` execution,
  result metadata, context managers, and the absence of a named-cursor
  parameter.

- [ ] **Step 1: Write public-surface tests**

Create `driver_tests/test_connection_cursor_contract.py`:

```python
import inspect

import redshift_connector


def parameter_names(member):
    return tuple(inspect.signature(member).parameters)


def test_connection_exposes_required_synchronous_methods():
    connection = redshift_connector.Connection
    assert parameter_names(connection.cursor) == ("self",)
    assert parameter_names(connection.commit) == ("self",)
    assert parameter_names(connection.rollback) == ("self",)
    assert parameter_names(connection.close) == ("self",)
    assert parameter_names(connection.__enter__) == ("self",)
    assert parameter_names(connection.__exit__) == (
        "self",
        "exc_type",
        "exc_value",
        "traceback",
    )


def test_cursor_exposes_required_dbapi_surface():
    cursor = redshift_connector.Cursor
    assert parameter_names(cursor.execute)[:3] == ("self", "operation", "args")
    assert parameter_names(cursor.executemany) == ("self", "operation", "param_sets")
    assert parameter_names(cursor.fetchone) == ("self",)
    assert parameter_names(cursor.fetchmany) == ("self", "num")
    assert parameter_names(cursor.fetchall) == ("self",)
    assert parameter_names(cursor.close) == ("self",)
    assert isinstance(cursor.description, property)
    assert isinstance(cursor.rowcount, property)


def test_named_server_side_cursor_is_not_a_public_driver_contract():
    assert "name" not in inspect.signature(redshift_connector.Connection.cursor).parameters
```

- [ ] **Step 2: Run against minimum and investigated releases**

Run:

```powershell
uv run --project driver_tests --with redshift-connector==2.1.14 pytest driver_tests/test_connection_cursor_contract.py -v
uv run --project driver_tests --with redshift-connector==2.1.16 pytest driver_tests/test_connection_cursor_contract.py -v
```

Expected: all three tests PASS. The named-cursor test records an explicit
limitation rather than a failure.

- [ ] **Step 3: Commit the public-surface contract**

```powershell
git add driver_tests/test_connection_cursor_contract.py
git commit -m "test: record Redshift connection and cursor surface"
```

### Task 6: AWS-Free Compatibility Matrix

**Files:**
- Create: `.github/workflows/driver-contract.yml`

**Interfaces:**
- Consumes: all tests under `driver_tests/` and GitHub-hosted Python runners.
- Produces: blocking coverage for every supported Django/Python combination at
  the security floor, plus a latest-driver smoke job.

- [ ] **Step 1: Create the dedicated workflow**

Create `.github/workflows/driver-contract.yml`:

```yaml
name: Redshift driver contract

on:
  pull_request:
  push:
    branches: [master]

jobs:
  contract:
    name: Python ${{ matrix.python }} / ${{ matrix.django }} / driver ${{ matrix.driver }}
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        include:
          - {python: "3.10", django: "Django==4.2.30", driver: "2.1.14"}
          - {python: "3.11", django: "Django==4.2.30", driver: "2.1.14"}
          - {python: "3.12", django: "Django==4.2.30", driver: "2.1.14"}
          - {python: "3.10", django: "Django==5.2.8", driver: "2.1.14"}
          - {python: "3.11", django: "Django==5.2.8", driver: "2.1.14"}
          - {python: "3.12", django: "Django==5.2.8", driver: "2.1.14"}
          - {python: "3.13", django: "Django==5.2.8", driver: "2.1.14"}
          - {python: "3.14", django: "Django==5.2.8", driver: "2.1.14"}
          - {python: "3.12", django: "Django~=6.0.0", driver: "2.1.14"}
          - {python: "3.13", django: "Django~=6.0.0", driver: "2.1.14"}
          - {python: "3.14", django: "Django~=6.0.0", driver: "2.1.14"}
          - {python: "3.12", django: "Django~=6.1.0", driver: "2.1.14"}
          - {python: "3.13", django: "Django~=6.1.0", driver: "2.1.14"}
          - {python: "3.14", django: "Django~=6.1.0", driver: "2.1.14"}
          - {python: "3.14", django: "Django~=6.1.0", driver: "2.1.16"}
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
        with:
          python-version: ${{ matrix.python }}
          enable-cache: true
      - name: Run public driver contracts
        run: >-
          uv run --project driver_tests
          --with "${{ matrix.django }}"
          --with "redshift-connector==${{ matrix.driver }}"
          pytest driver_tests -q
```

- [ ] **Step 2: Validate the workflow and run the local representative jobs**

Run:

```powershell
uv run --python 3.12 --project driver_tests --with Django==4.2.30 --with redshift-connector==2.1.14 pytest driver_tests -q
uv run --python 3.12 --project driver_tests --with Django==5.2.8 --with redshift-connector==2.1.14 pytest driver_tests -q
uv run --python 3.14 --project driver_tests --with "Django~=6.1.0" --with redshift-connector==2.1.16 pytest driver_tests -q
```

Expected: all tests PASS in all three representative environments.

- [ ] **Step 3: Commit the matrix**

```powershell
git add .github/workflows/driver-contract.yml
git commit -m "ci: add Redshift driver contract matrix"
```

### Task 7: Evidence Report and GO/NO-GO Gate

**Files:**
- Create: `docs/superpowers/research/2026-08-23-redshift-connector-investigation.md`
- Modify: `docs/superpowers/specs/2026-08-23-redshift-backend-redesign-design.md`
  only if the result is NO-GO or evidence changes an approved assumption.

**Interfaces:**
- Consumes: test results, uv lock metadata, official AWS documentation, AWS's
  driver repository/changelog, and published security advisories.
- Produces: one explicit `Decision: GO` or `Decision: NO-GO` and the evidence
  needed by `redesign/02-backend-foundation`.

- [ ] **Step 1: Write the evidence report with measured results**

Create the report with these sections and facts:

```markdown
# AWS Redshift Connector Investigation

## Decision

The first content line in the final section must be exactly `Decision: GO` if
every must-pass item below passes. Otherwise it must be exactly
`Decision: NO-GO`, followed by each failed requirement.

## Candidate and proposed constraint

- Investigated release: 2.1.16.
- Security floor: 2.1.14, which contains the fix for GHSA-29h4-r29x-hchv.
- Proposed runtime constraint after GO: `redshift-connector>=2.1.14,<3`.
- Python metadata: `Requires-Python >=3.8`; CI verifies the project's 3.10-3.14 matrix.

## Maintenance, license, security, and dependencies

- Record the 2.1.14-2.1.16 release dates and current release activity.
- Record that wheel metadata says `Apache License 2.0` while its license
  classifier says BSD; resolve the discrepancy against the packaged LICENSE
  and NOTICE files before GO.
- Record direct dependencies from the locked distribution, including boto3,
  botocore, requests, lxml, Beautiful Soup, pytz, scramp, packaging, and
  setuptools; note that numpy/pandas belong only to the `full` extra.
- Record GHSA-r244-wg5g-6w2r as fixed in 2.1.7 and
  GHSA-29h4-r29x-hchv as fixed in 2.1.14.

## Must-pass public contracts

- DB-API 2.0, `format` parameter style, and thread-safety level 1.
- Complete Django exception namespace and `DatabaseErrorWrapper` translation.
- Explicit public connection parameters for password, IAM, profile,
  provisioned cluster, Serverless workgroup, and IdP pass-through modes.
- Public synchronous connection/cursor lifecycle methods and result metadata.
- No production dependency on a private driver API or a psycopg2 adapter.
- All blocking AWS-free CI jobs pass at the minimum driver version.

## Connection option crosswalk

- Standard `NAME`, `HOST`, `PORT`, `USER`, and `PASSWORD` values override
  duplicate driver names in `OPTIONS`.
- Driver options are accepted only when present in the public `connect()`
  signature.
- `passfile`, `service`, `sslrootcert`, `sslcert`, and `sslkey` are retained
  only for `dbshell`; `sslmode` is consumed by both the driver and `dbshell`.
- `options`, `isolation_level`, `cursor_factory`, `connection_factory`, and
  `client_encoding` are rejected legacy psycopg2 options.
- Unknown options fail before opening a socket.
- Enumerate every redacted option from `SENSITIVE_OPTIONS`.

## Explicit limitations and deferred integration checks

- `Connection.cursor()` has no public named-cursor argument; Django chunked
  cursors must initially use an ordinary cursor or be marked unsupported.
- Real parameter binding, round trips for UUID/Decimal/date/time/datetime/
  timezone/Boolean/JSON/NULL/Redshift-specific/unknown types, savepoint SQL,
  `execute()`/`executemany()`/fetch/result-metadata behavior, connection health
  after network failure, `CONN_MAX_AGE`, IAM, IdP, provisioned cluster, and
  Serverless behavior remain unverified without a real Redshift service.
- Autocommit defaults and context-manager behavior are supported by AWS's
  public documentation/source evidence but are not integration-tested here.

## Commands and results

- Record each exact uv command, package version, Python/Django version, test
  count, and pass/fail result.

## Sources

- Link AWS's Python connector API reference, official driver repository,
  changelog/releases, PyPI release metadata, and the two security advisories.
```

Do not leave the instructional sentences in the final report. Replace them
with the actual observed evidence and a single decision.

- [ ] **Step 2: Apply the mechanical decision rule**

Run every command from Tasks 2-6 and inspect the GitHub Actions matrix.

Expected GO condition: every must-pass public contract and every blocking CI
job passes, the packaged LICENSE/NOTICE resolves the metadata discrepancy, and
the backend can proceed without private driver APIs or a psycopg2 adapter.

Expected NO-GO condition: any mandatory exception, parameter style, public
connection option, supported-version job, or license/security requirement
fails. Record NO-GO, update the parent design, and do not create
`redesign/02-backend-foundation`.

- [ ] **Step 3: Run final verification**

Run:

```powershell
uv run --python 3.12 --project driver_tests --with Django==4.2.30 --with redshift-connector==2.1.14 pytest driver_tests -q
uv run --python 3.12 --project driver_tests --with Django==5.2.8 --with redshift-connector==2.1.14 pytest driver_tests -q
uv run --python 3.12 --project driver_tests --with "Django~=6.0.0" --with redshift-connector==2.1.14 pytest driver_tests -q
uv run --python 3.14 --project driver_tests --with "Django~=6.1.0" --with redshift-connector==2.1.16 pytest driver_tests -q
git diff --check
git status --short
```

Expected: every test command passes, `git diff --check` is silent, and status
lists only the completed report before it is committed.

- [ ] **Step 4: Commit the decision**

```powershell
git add docs/superpowers/research/2026-08-23-redshift-connector-investigation.md
git commit -m "docs: record Redshift driver adoption decision"
```

If NO-GO changed the parent design, stage that design file in the same decision
commit and explain the design change in the commit body.

- [ ] **Step 5: Push and open the stacked child PR**

```powershell
git push --set-upstream origin redesign/01-driver-investigation
$decision = (Select-String -Path docs/superpowers/research/2026-08-23-redshift-connector-investigation.md -Pattern '^Decision: (GO|NO-GO)$').Matches[0].Groups[1].Value
$prBody = @'
## Scope

Investigate AWS's public `redshift_connector` DB-API as the first child of #1.
This PR does not activate the redesigned backend.

## Decision

**DECISION_VALUE** — see the checked-in investigation report for measured evidence,
the option crosswalk, security and dependency review, and deferred
real-Redshift checks.

## Acceptance criteria

- Public DB-API, connection, cursor, exception, and option contracts are tested.
- Django 4.2.30, 5.2, 6.0, and 6.1 compatibility jobs are blocking.
- Both the 2.1.14 security floor and investigated 2.1.16 release are covered.
- No private driver API or psycopg2 compatibility adapter is required.

## Parent

https://github.com/shimizukawa/django-redshift-backend/pull/1
'@
$prBody = $prBody.Replace('DECISION_VALUE', $decision)
$childUrl = gh pr create --repo shimizukawa/django-redshift-backend --base redesign/00-plan --head shimizukawa:redesign/01-driver-investigation --title "Redesign 1/7: investigate AWS Redshift driver" --body $prBody
gh stack link $childUrl --parent https://github.com/shimizukawa/django-redshift-backend/pull/1
```

After GitHub Actions finishes, edit the PR verification section to include each
blocking job result and its test count. Do not commit a temporary PR body file.

- [ ] **Step 6: Update the tracking PR**

Edit PR #1's current-status and stack sections, then append a progress comment
containing the child PR URL, commit, decision, driver constraint, CI result,
deferred checks, and whether the next layer is unblocked.
