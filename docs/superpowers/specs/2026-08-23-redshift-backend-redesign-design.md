# Django Redshift Backend Redesign

## Status

Approved for planning on 2026-08-23. Implementation beyond the driver
investigation must not begin until that pull request records a GO decision.

## Context

The current backend vendors Django 4.0 database and PostgreSQL backend code so
that psycopg2 can continue to connect to Amazon Redshift's PostgreSQL-compatible
interface. This isolates the backend from supported Django database APIs and has
already caused signature mismatches such as `date_trunc_sql()` on Django 4.1 and
later.

The redesign addresses GitHub issues #167, #168, #171, #175, and #183 by
building a Redshift backend directly on Django's public base backend classes and
using AWS's `redshift_connector` driver. The existing implementation remains an
important source of Redshift-specific behavior and workarounds, but vendored
Django code is not a foundation for the new implementation.

The design was checked against these local Django sources:

- Django 4.2.30 in `../django-4.2.30`.
- Django 5.2 in the `origin/stable/5.2.x` ref of `../django`.
- Django 6.0 and 6.1 in the corresponding stable refs of `../django`.
- Django 6.x development code (currently 6.2 alpha) in `../django`.

## Goals

- Support Django 4.2.30 as a compatibility bridge for existing users, plus
  Django 5.2 LTS and Django 6.x as normally supported releases.
- Replace psycopg2 with AWS's `redshift_connector` after an explicit adoption
  investigation.
- Implement the backend from `django.db.backends.base` rather than inheriting
  from or vendoring Django's PostgreSQL backend.
- Preserve the existing `ENGINE`, standard `DATABASES` settings, `DistKey`, and
  `SortKey` APIs where the driver permits it.
- Preserve existing migration files and avoid requiring a database schema
  migration solely because the package was upgraded.
- Reuse existing migration, SQL generation, schema editing, and introspection
  tests as executable specifications.
- Keep all investigation, decisions, implementation, and verification visible
  in a GitHub stacked pull request series.

## Non-goals

- Providing upstream security maintenance for the end-of-life Django 4.2
  series, or supporting Django releases older than 4.2.30.
- Retaining psycopg2 as an alternative runtime driver.
- Maintaining a psycopg2 compatibility adapter around `redshift_connector`.
- Inheriting from or copying a complete Django PostgreSQL backend.
- Automatically changing an existing user's Redshift schema on package upgrade.
- Provisioning Redshift or running real-Redshift CI in the initial stack.
- Certifying each SAML, Okta, Azure AD, browser SSO, or other identity-provider
  plugin without a real Redshift environment.

## Supported version matrix

The first redesigned release declares
`Django>=4.2.30,<6.2,!=5.0.*,!=5.1.*` and `requires-python>=3.10`. Its required
CI matrix is:

- Django 4.2.30 on Python 3.10, 3.11, and 3.12.
- Django 5.2 on Python 3.10, 3.11, 3.12, 3.13, and 3.14.
- Django 6.0 on Python 3.12, 3.13, and 3.14.
- Django 6.1 on Python 3.12, 3.13, and 3.14.

These combinations follow Django's published compatibility: Django 4.2.30
supports Python 3.8 through 3.12, Django 5.2.8 and later support Python 3.10
through 3.14, and Django 6.0 and 6.1 support Python 3.12 through 3.14. The
backend's Python floor limits the Django 4.2 jobs to Python 3.10 through 3.12.

Django 4.2 support is an explicitly bounded compatibility bridge because the
current backend advertises 4.2 support but has known failures on that series.
It does not imply that this project supplies Django security fixes. A later
release may drop 4.2 after an announced support decision; the isolated 4.2
schema compatibility module, its selection branch, and its dedicated tests
must then be removable together.

Django's `main` branch is tested on Python 3.14 as a non-blocking early-warning
job and is not a supported release target. A future Django 6.x minor is not
claimed automatically: support requires a focused pull request that inspects
its database backend release notes, adds the stable minor to the dependency
range and full supported Python matrix, and makes those jobs blocking.

## Public compatibility contract

The redesigned major version preserves:

- `ENGINE = "django_redshift_backend"`.
- Standard `NAME`, `HOST`, `PORT`, `USER`, and `PASSWORD` settings.
- `django_redshift_backend.DistKey` and
  `django_redshift_backend.SortKey`.
- Deserialization of existing migration files containing those import paths.
- The legacy `django_redshift_backend.distkey.DistKey` import shim, because old
  application migration files may still import it directly.
- Existing `dbshell` command arguments and environment behavior through
  `psql`.

Breaking changes are allowed for the removal of psycopg2, unsupported
psycopg2-only `OPTIONS`, driver exception details, and behavior that is proven
to be a bug in the current backend. Every accepted break must be documented in
the migration guide.

## Architecture

The runtime entry point remains `django_redshift_backend.base`. It exposes a
`DatabaseWrapper` built from Django's `BaseDatabaseWrapper` and composes focused
Redshift components.

### Core modules

- `base.py`: Django backend entry point, `DatabaseWrapper`, type mapping,
  operators, and component registration.
- `driver.py`: the only boundary that imports and calls `redshift_connector`;
  translates Django settings into driver arguments.
- `features.py`: conservative declarations of verified Redshift capabilities.
- `operations.py`: quoting, date/time SQL, expression SQL, value adaptation,
  and conversion.
- `schema.py`: Redshift DDL, table/column alteration workarounds, `DISTKEY`, and
  `SORTKEY` generation.
- `schema_django42.py`: only schema-editor overrides that tests prove are
  required by Django 4.2. `base.py` selects this class only on Django 4.2; all
  later supported versions use the common class from `schema.py`.
- `introspection.py`: Redshift-safe catalog queries for tables, columns,
  relations, keys, and constraints.
- `client.py`: the small, independent `psql` implementation required to retain
  `dbshell` behavior.
- `creation.py`: only the Redshift-supported subset of test database creation
  behavior currently inherited indirectly from PostgreSQL. Unsupported clone
  or creation operations must fail explicitly rather than silently using
  PostgreSQL assumptions.

`meta.py` and `distkey.py` remain unchanged unless a compatibility test requires
a correction. No separate compiler, validation, or version-wide compatibility
module is introduced initially. Django's default compiler and validation class
are used. Version-specific code is added only when tests prove that the same
implementation cannot satisfy all supported Django versions.

The Django 4.2 schema boundary is intentionally deletion-oriented. Common
Redshift behavior remains in `schema.py`; `schema_django42.py` must contain no
5.2-or-later behavior and must override only the smallest test-proven surface.
The version selection has a removal comment naming the 4.2-only tests that
protect it. Dropping Django 4.2 consists of deleting that module, the single
selection branch, and those tests rather than untangling inline version checks.

### Django API boundary

`DatabaseWrapper` implements the driver-facing methods required by Django's
base wrapper:

- `get_connection_params()`
- `get_new_connection()`
- `init_connection_state()`
- `create_cursor()`
- `_set_autocommit()`
- `is_usable()`

`driver.py` also exposes the driver's public DB-API exception namespace as
`Database`, and `DatabaseWrapper.Database` references it. Contract tests cover
all exception names Django's `DatabaseErrorWrapper` dereferences: `Error`,
`InterfaceError`, `DatabaseError`, `DataError`, `OperationalError`,
`IntegrityError`, `InternalError`, `ProgrammingError`, and
`NotSupportedError`.

Modern operation signatures are implemented directly. For example,
`date_trunc_sql(self, lookup_type, sql, params, tzname=None)` is stable across
the inspected Django 4.2 through 6.x sources and resolves #171 without a
version branch.

Django 6.0 renamed insert-returning APIs to general returning APIs. Redshift
does not support `RETURNING`, so its feature flags remain false and the base
implementation handles this difference. The backend must not add speculative
compatibility code for unused APIs.

### Connection data flow

The normal connection flow is:

1. Django validates and normalizes `DATABASES` settings.
2. `DatabaseWrapper.get_connection_params()` maps standard settings and
   separates backend-owned options from driver options.
3. `driver.py` validates the final argument set and calls
   `redshift_connector.connect()`.
4. The wrapper configures autocommit and verified connection state.
5. Django's standard cursor wrappers provide debug logging and exception
   wrapping.

The initial setting mapping is:

- `NAME` to `database`.
- `HOST` to `host`.
- `PORT` to `port`.
- `USER` to the driver user or IAM database-user field selected by the
  documented authentication mode.
- `PASSWORD` to `password`.
- Driver-specific values under `OPTIONS` to matching public `connect()`
  keyword arguments.

Backend-owned options are removed before the driver call. Unknown options are
rejected with `ImproperlyConfigured`; they are not silently ignored. The driver
investigation records the exact precedence when the same value appears in a
standard setting and in `OPTIONS`.

The investigation publishes an option crosswalk with four explicit groups:

- Backend-owned options consumed before the driver call.
- Public `redshift_connector.connect()` options passed to the driver.
- Existing `dbshell` options (`passfile`, `service`, `sslmode`, `sslrootcert`,
  `sslcert`, and `sslkey`) consumed only by `client.py` where applicable.
- Rejected legacy psycopg2 options, with their replacement or removal reason.

The crosswalk defines standard-setting versus `OPTIONS` precedence and marks
every credential-bearing value that must be redacted.

### Authentication scope

The initial implementation supports configuration and unit-level contracts for:

- Username/password authentication.
- IAM through the boto3 default credential chain.
- IAM through an AWS profile.
- Provisioned cluster parameters.
- Redshift Serverless workgroup parameters.
- Pass-through of documented identity-provider options.

IAM and identity-provider behavior is not claimed as integration-tested until a
real Redshift environment is available. Secrets and tokens must not appear in
debug SQL, logs, raised configuration messages, or test snapshots.

## AWS driver adoption gate

The first implementation pull request investigates `redshift_connector` and
must record one of two outcomes:

- **GO:** the public driver API satisfies the required contract with a small,
  Redshift-specific adapter.
- **NO-GO:** implementation stops, the failed requirements and evidence are
  added to the parent design pull request, and this design is revised before
  another implementation layer begins.

The investigation covers:

- Supported Python versions, license, release activity, security maintenance,
  dependency size, and dependency conflicts.
- DB-API 2.0 parameter styles, especially `%s` and `pyformat`.
- Cursor execution, `executemany()`, fetch methods, description, and row count.
- Commit, rollback, close, autocommit, and context-manager behavior.
- Django exception wrapping against the driver's public exception hierarchy.
- Availability of every exception name required by
  `DatabaseErrorWrapper`, and translation tests for each name.
- Connection health, thread-safety assumptions, `CONN_MAX_AGE`, and Django's
  connection-per-thread model.
- Binary, UUID, Decimal, date, time, datetime, timezone, Boolean, JSON-as-text,
  NULL, Redshift-specific, and unknown type behavior.
- Savepoint and named/server-side cursor support.
- Password and IAM connection argument construction.

The adoption criteria are:

- No psycopg2 compatibility layer is required.
- SQL parameter substitution is delegated to the driver.
- No private driver API is required.
- Django connection, cursor, transaction, and exception contracts can be met by
  focused adapter code.
- Password and IAM configurations share one validated settings boundary.

The selected driver version constraint is recorded in the investigation PR
before it receives a GO decision.

## Preserving existing implementation knowledge

Before replacing a component, its current code is classified into:

1. Redshift-specific behavior to preserve.
2. Vendored Django/PostgreSQL behavior that the supported Django version now
   supplies.
3. Historical compatibility code that is no longer applicable.

The schema inventory must explicitly cover:

- Unsupported indexes and PostgreSQL-only constraints.
- `DISTKEY` and `SORTKEY` table options.
- `identity(1, 1)`, `varchar(max)`, `varbyte`, UUID, and JSON-as-text mappings.
- Column recreation used to emulate unsupported `ALTER COLUMN` operations.
- VARCHAR length and null/default alterations.
- Binary-to-character and character-to-binary alterations.
- SORTKEY column removal behavior.
- Redshift-specific limitations around defaults and constraints.

The introspection inventory must preserve catalog queries that avoid PostgreSQL
functions unavailable in Redshift and the identity-column mapping used by
`inspectdb`.

## Database migration compatibility

Installing the redesigned package without changing application models must not
require a database migration. The acceptance contract is:

- `makemigrations --check` reports no model-state change.
- Existing migration modules import and deserialize unchanged.
- `DistKey` and `SortKey` deconstruction paths remain stable.
- The backend runs no automatic schema repair or migration at connection time.

The migration gate is database-free and executable in normal CI. It:

1. Loads the repository's existing migration corpus from disk without reading
   applied-migration state from a database.
2. Reconstructs project states and asserts that the migration modules and
   `DistKey`/`SortKey` values deconstruct to the existing import paths.
3. Runs Django's migration autodetector against unchanged model states and
   asserts that it produces no new migration operations.
4. Applies each schema operation to a schema editor with `collect_sql=True`
   without opening a database connection.
5. Compares normalized generated SQL with checked-in expected SQL and an
   explicit manifest of approved semantic differences.

Existing migrations and representative models form a migration corpus. Tests
compare SQL produced by the current and redesigned implementations and classify
each difference as:

- Semantically equivalent formatting or quoting.
- An intentional correction affecting future schema operations only.
- A bug fix for which existing databases may benefit from an explicit,
  user-owned migration.

The third category is never applied automatically. It requires release notes,
diagnostic SQL or a Django system check when feasible, and an optional migration
example. Any unavoidable database migration must be justified by a concrete bug
or limitation that the redesign fixes.

## Test strategy

### Normal CI, without AWS

- Driver contract tests using public APIs, mocks, and fake connection/cursor
  objects.
- Settings mapping and secret-redaction tests.
- Connection lifecycle, transaction, autocommit, exception, and health tests.
- Django 4.2.30, Django 5.2, and supported Django 6.x operation signature
  tests.
- Schema-editor selection tests proving that Django 4.2 alone uses
  `schema_django42.py`, while later versions use the common implementation.
- A regression test reproducing #171 through Django's `Trunc` expression.
- Feature-flag tests that start from Django base defaults and opt in only to
  verified Redshift features.
- SQL generation golden tests for DDL and ORM queries.
- Existing migration tests adapted to the supported Django APIs.
- Migration-corpus and schema golden tests on every supported Django minor,
  with any approved version-specific SQL difference recorded explicitly.
- Database-free `collect_sql=True` and `sqlmigrate`-equivalent tests.
- Migration import, deconstruction, graph, plan, and `makemigrations --check`
  tests. Migration graph and SQL collection must not query applied-migration
  state from a database.
- Introspection query and result-shaping tests with mock cursors.
- Existing `inspectdb` expectations.

The current PostgreSQL substitute fixture is not treated as proof that the AWS
driver or Redshift SQL works. It may be retained temporarily only where it tests
driver-independent ORM behavior, and is removed when equivalent contract tests
exist.

### Deferred integration testing

Real-Redshift tests, including IAM and Serverless authentication, remain skipped
and clearly marked. A future issue will cover AWS account setup, secretless
GitHub authentication, cost controls, test isolation, and scheduled or
release-gated execution. Initial release notes must state that IAM is
contract-tested but not integration-tested.

## Error handling

- Configuration mistakes raise `ImproperlyConfigured` before opening a socket.
- Driver errors flow through Django's standard `DatabaseErrorWrapper` using the
  driver's public DB-API exception hierarchy.
- Unsupported Redshift capabilities raise Django `NotSupportedError` with a
  specific operation name.
- Failed schema emulation must preserve transaction state where Redshift allows
  it and must not silently continue after partial execution.
- Logs and exception messages redact credentials, tokens, secret keys, and
  session tokens.
- Unsupported test database creation, cloning, or `dbshell` configurations fail
  explicitly and are documented.

## Stacked pull request delivery

All branches are pushed to `shimizukawa/django-redshift-backend` so GitHub's
same-repository stacked pull request requirement is satisfied. The stack is:

1. `redesign/00-plan`: this design, roadmap, and tracking parent; no runtime
   change.
2. `redesign/01-driver-investigation`: driver evidence, contract tests, settings
   mapping prototype, and GO/NO-GO decision.
3. `redesign/02-backend-foundation`: independent wrapper, driver boundary,
   connection lifecycle, client, and creation contracts without activating the
   new backend entry point.
4. `redesign/03-operations-features`: operations, conservative features, and
   #171 regression coverage.
5. `redesign/04-schema-migrations`: schema editor, migration corpus, SQL
   comparison, and no-database-migration gates.
6. `redesign/05-introspection`: catalog queries and `inspectdb` behavior.
7. `redesign/06-activate-cleanup-release`: activate the new entry point, remove
   vendored Django and psycopg2, update the test matrix and documentation, and
   prepare the major release.

Each branch is based on the branch immediately below it. Every pull request must
pass CI and contain a focused diff. Changes committed to a lower branch require
a cascading rebase of all branches above it.

### Progress recording

The `00-plan` pull request is the authoritative status page:

- Its body is edited in place with the current stack checklist, current phase,
  decisions, risks, and links.
- Milestone results, GO/NO-GO decisions, blockers, compatibility findings,
  completed review layers, and cascading rebases are appended as comments.
- Progress-only updates do not modify this design document.
- A changed architectural decision updates this document in `00-plan`, followed
  by a cascading rebase.
- Child pull requests contain their own scope, acceptance criteria, tests, and
  dependency links.

## Completion criteria

The redesign is complete when:

- The driver investigation records GO and every adoption criterion is covered
  by evidence.
- Django 4.2.30, Django 5.2, and the supported Django 6.x matrix pass without
  the vendored backend.
- Every Django 4.2-only schema override is isolated in `schema_django42.py` and
  covered by a dedicated test, so the module, selection branch, and tests can
  be deleted together when 4.2 support ends.
- The #171 regression passes through Django ORM APIs.
- Existing public imports and migrations remain valid.
- The migration compatibility gates report no upgrade-induced model or schema
  migration.
- The vendored Django 4.0 code, psycopg2 dependency, and psycopg2 adapter are
  removed.
- Documentation states all breaking changes and the absence of real-Redshift
  IAM verification.
- Deferred real-Redshift integration work is recorded in a follow-up issue.
