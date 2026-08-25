# Backend Foundation Design

## Status

Approved in conversation on 2026-08-24. This design is the third layer of the
stack and is based on the GO decision in `redesign/01-driver-investigation`.

## Purpose

Build and test the new AWS-driver connection foundation without changing the
backend selected by `ENGINE = "django_redshift_backend"`. This layer makes the
connection boundary reviewable while the operations, schema, and introspection
layers are still incomplete.

## Scope

This layer provides:

- A `BaseDatabaseWrapper`-based internal wrapper with Django's required
  connection lifecycle methods.
- The production `redshift_connector` boundary and password-only settings
  validation proven by the driver investigation.
- The existing `psql` dbshell contract without PostgreSQL-backend inheritance.
- Explicit rejection of unsupported test database provisioning.
- AWS-free contract tests across the supported Django/Python matrix.

This layer does not:

- Change `django_redshift_backend.base.DatabaseWrapper` or activate the new
  backend for existing `ENGINE` settings.
- Add Redshift operations, feature opt-ins, schema behavior, or introspection.
- Remove psycopg2, vendored Django code, or the current dependency metadata.
- Support IAM, profile, Serverless, IdP/provider, or token authentication.
- Connect to a real Redshift cluster.

## Staging architecture

The new wrapper lives in `django_redshift_backend/_backend.py` and is an
internal implementation detail. The leading underscore is deliberate: users
must not import it, and its path is not a compatibility promise. The final
activation layer changes `base.py` to expose this wrapper through the existing
backend entry point. Keeping the wrapper in `_backend.py` avoids moving its
implementation during activation while allowing `base.py` to remain untouched
in this layer.

The focused final-location components are:

- `driver.py`: the only production module that imports and calls
  `redshift_connector`.
- `client.py`: `psql` command and environment construction.
- `creation.py`: explicit unsupported test-database operations.

`_backend.py` temporarily composes Django's base feature, operation,
introspection, schema, and validation classes. Later stack layers replace
those class attributes with Redshift implementations. No feature is opted in
speculatively.

Alternatives rejected:

- Editing `base.py` now would activate an incomplete backend.
- A temporary `foundation.py` would require moving the wrapper later and would
  create avoidable review churn.
- A runtime flag selecting old or new wrappers would create an unsupported
  public configuration path and double the test surface.

## Driver boundary

`driver.py` promotes the investigation prototype into production code. It
exports `Database` as the public `redshift_connector` module so Django's
`DatabaseErrorWrapper` can dereference the required DB-API exception names.

It exposes focused functions:

- `build_connect_kwargs(settings_dict) -> dict[str, object]`
- `connect(**kwargs)` as the single call to `redshift_connector.connect()`
- `classify_options(options) -> tuple[dict, dict]`
- `classify_dbshell_options(options) -> dict`
- `redact_connect_kwargs(kwargs) -> dict`

Configuration errors are translated from the prototype's `ValueError` to
`django.core.exceptions.ImproperlyConfigured`. Messages name invalid setting
keys but never include their values.

The settings contract remains:

- `NAME` maps to `database` when non-empty.
- `HOST` maps to `host` when non-empty.
- `PORT` maps to an integer `port` when non-empty.
- Non-empty top-level `USER` and `PASSWORD` are mandatory and override any
  duplicate values in `OPTIONS`.
- Public password-compatible driver options pass through.
- Unknown options, legacy psycopg2-only options, and all 45 inventoried
  alternate-authentication options fail before `connect()` is called.
- `sslmode` accepts only `verify-ca` and `verify-full` at the driver boundary.

`redact_connect_kwargs()` remains independently testable but the wrapper does
not log connection arguments in this layer.

## Wrapper lifecycle

`_backend.DatabaseWrapper` directly subclasses Django's
`BaseDatabaseWrapper`, declares `vendor = "redshift"`,
`display_name = "Amazon Redshift"`, and exposes `Database = driver.Database`.

It implements only the public base-backend lifecycle required across the
inspected Django 4.2.30 through 6.x sources:

- `get_connection_params()` delegates to `driver.build_connect_kwargs()`.
- `get_new_connection(conn_params)` delegates to `driver.connect()`.
- `init_connection_state()` delegates to the base implementation and emits no
  Redshift session SQL.
- `create_cursor(name=None)` returns `self.connection.cursor()` when `name` is
  `None`; named/server-side cursors raise `NotSupportedError`.
- `_set_autocommit(autocommit)` assigns the driver's public `autocommit`
  attribute.
- `is_usable()` executes `SELECT 1` with a short-lived cursor and returns
  `True`; any `Database.Error` returns `False` and does not escape.

The health query uses a context-managed cursor when supported by the driver's
public contract. It contains no credentials and performs no transaction-state
repair.

The wrapper defines only minimal empty type maps required for safe
construction. It is not used for ORM compilation in this layer. Query and DDL
behavior belongs to later stack layers.

## dbshell client

`client.DatabaseClient` subclasses Django's `BaseDatabaseClient`, retains
`executable_name = "psql"`, and implements the PostgreSQL-compatible command
line behavior users already receive from the current backend.

It maps `NAME`, `HOST`, `PORT`, and `USER` to `psql` arguments and `PASSWORD`
to `PGPASSWORD`. The dbshell-only options `passfile`, `service`, `sslmode`,
`sslrootcert`, `sslcert`, and `sslkey` map to their corresponding libpq
environment variables. Extra parameters are appended without interpretation.

The complete psql `sslmode` domain remains accepted here. Driver option
classification and dbshell option classification stay separate, so a
dbshell-only value is never forwarded to `redshift_connector`.

Tests assert argument order and environment values but never spawn `psql`.

## Test database creation

Redshift database creation, cloning, and destruction are not safe PostgreSQL
operations. `creation.DatabaseCreation` subclasses `BaseDatabaseCreation` and
raises Django `NotSupportedError` with the operation name from
`create_test_db()`, `clone_test_db()`, and `destroy_test_db()` before executing
SQL.

This explicit behavior prevents Django's generic implementation from issuing
unsupported or destructive statements. Real-Redshift test isolation remains a
future design.

## Test organization

The existing `driver_tests` uv project remains the isolated compatibility
matrix. Its tests import production `django_redshift_backend.driver` instead
of keeping a duplicate option prototype. The repository root is added to the
test import path without installing the root project's current Django
dependency constraint; each workflow cell continues to select its exact
Django and driver versions.

New AWS-free tests cover:

- Every existing option, precedence, redaction, and exception contract against
  production `driver.py`.
- Driver connect delegation and proof that invalid settings never call it.
- Wrapper component construction on every supported Django minor.
- Connection parameter mapping, connection creation, unnamed/named cursors,
  autocommit, initialization, and health checks using fakes.
- Django exception wrapping using `DatabaseWrapper.Database`.
- Exact `psql` arguments and environment variables, including separation of
  dbshell-only options.
- Explicit creation, clone, and destruction rejection without cursor access.
- The staging invariant that `django_redshift_backend.base.DatabaseWrapper`
  remains the existing wrapper and is not `_backend.DatabaseWrapper`.

The 15-cell workflow from the driver investigation remains blocking. Root
regression tests, lint, and package-content checks must also pass. Tests must
not access the network, invoke `psql`, or require AWS credentials.

## Compatibility and activation

Because `base.py`, public imports, and dependency metadata remain unchanged,
this layer does not change the installed backend's runtime behavior and cannot
request a database migration. `DistKey`, `SortKey`, `meta.py`, and `distkey.py`
remain untouched.

Activation is permitted only after operations/features, schema/migrations, and
introspection layers pass their gates. The activation PR will:

1. Make `base.py` expose `_backend.DatabaseWrapper`.
2. Attach the completed Redshift component classes.
3. Replace psycopg2 metadata with `redshift-connector>=2.1.14,<3`.
4. Remove vendored Django code and the compatibility adapter.
5. Run the no-database-migration and release verification gates.

## Acceptance criteria

- Production connection code inherits only from Django public base-backend
  classes.
- `driver.py` is the sole production `redshift_connector` import/call boundary.
- Password-only validation and all 45 alternate-authentication rejections run
  before driver connection.
- All wrapper lifecycle methods behave against fake public DB-API objects on
  Django 4.2.30, 5.2, 6.0, and 6.1.
- dbshell behavior is preserved without importing a PostgreSQL backend.
- Unsupported test database operations fail explicitly before SQL execution.
- Current `base.py` and public migration APIs remain unchanged.
- All local and GitHub Actions checks pass without AWS access.
