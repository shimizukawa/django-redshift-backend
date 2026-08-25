# Operations and Features Design

**Status:** Approved for implementation on 2026-08-25.

## Goal

Add an AWS-free operations and feature-contract layer for the redesigned
backend on Django 4.2.30, 5.2, 6.0, and 6.1. The layer fixes the modern Django
operation signatures behind issue #171, preserves useful Redshift behavior
from the existing backend, incorporates the intent of pull request #103, and
removes accidental PostgreSQL capability claims without activating the new
backend entry point.

## Evidence hierarchy

Redshift behavior is decided from these sources, in order:

1. The current Amazon Redshift Database Developer Guide is authoritative for
   supported SQL and semantics.
2. Django 4.2.30 and the inspected Django 5.2/6.x public backend APIs define
   the integration contract.
3. Existing django-redshift-backend code and tests record behavior that users
   may depend on, but PostgreSQL inheritance alone is not evidence that
   Redshift supports a feature.
4. Project issues and unmerged pull requests record implementation knowledge
   and user-visible failures. Their intent is retained even when their exact
   code is unsuitable for current Django.

The unit tests prove that Django generates SQL matching the documented
Redshift contract. Real-Redshift execution is not a prerequisite for accepting
a feature documented by AWS. Driver behavior or service behavior not specified
by AWS remains deferred to future integration testing.

## Scope

This stack layer will:

- Create `django_redshift_backend/operations.py` based only on Django's public
  `BaseDatabaseOperations`.
- Create `django_redshift_backend/features.py` based only on Django's public
  `BaseDatabaseFeatures`.
- Register both classes on the inactive internal wrapper in `_backend.py`.
- Add database-free operation, feature, expression, and conflict-path tests to
  `driver_tests`.
- Run the existing 15-cell Django/Python/driver contract matrix.
- Preserve the current `django_redshift_backend.base.DatabaseWrapper` as the
  active `ENGINE` implementation until the final activation layer.

This layer will not:

- Change `base.py`, `meta.py`, `distkey.py`, migration files, models, or the
  database schema.
- Introduce a custom SQL compiler.
- Implement schema editing, migration SQL, introspection, or data type
  registration.
- Add IAM, profile, Serverless, or identity-provider authentication.
- Require AWS credentials or a Redshift cluster.
- Claim that savepoints, `RETURNING`, `ON CONFLICT`, `DISTINCT ON`, indexes,
  tablespaces, PostgreSQL JSON operators, or enforced key constraints work.

## Architecture

### `features.py`

`DatabaseFeatures` starts from `django.db.backends.base.features.BaseDatabaseFeatures`.
It explicitly declares every Redshift capability that otherwise has an unsafe
or version-sensitive default. It does not inherit PostgreSQL features.

The initial feature policy is:

| Capability | Declaration | Reason |
| --- | --- | --- |
| Transactions | supported | AWS documents `BEGIN`, `COMMIT`, and `ROLLBACK`. |
| Savepoints | unsupported | AWS lists `ROLLBACK TO SAVEPOINT` as unsupported. |
| Insert/update returning | unsupported | Redshift `INSERT` has no `RETURNING` clause. |
| Bulk insert | supported | Redshift documents multi-row `VALUES`. |
| Ignore/update conflicts | unsupported | Redshift has no PostgreSQL `ON CONFLICT`. |
| `SELECT FOR UPDATE` variants | unsupported | The current backend already rejects them and Redshift uses different concurrency semantics. |
| Normal `DISTINCT` | supported | Redshift documents `SELECT DISTINCT`. |
| `DISTINCT ON` | unsupported | It is absent from Redshift syntax and issue #14 records the failure. |
| Aggregate `FILTER` | unsupported | Preserve Django's existing `CASE WHEN` emulation. |
| Window expressions | supported | AWS documents `OVER`, partitions, ordering, and `ROWS` frames. |
| Native UUID | unsupported | Preserve VARCHAR storage and Python conversion. |
| JSON text storage | supported | Preserve JSON serialization to the existing VARCHAR representation. |
| PostgreSQL JSON operators/contains | unsupported | Text storage does not provide PostgreSQL `->`, `@>`, or related semantics. |
| Native duration/temporal subtraction | supported | AWS documents interval types and date/timestamp arithmetic. |
| Enforced PK/FK/UNIQUE/CHECK constraints | unsupported | Redshift key constraints are informational and CHECK constraints are unsupported. |
| Indexes and tablespaces | unsupported | AWS lists both as unsupported PostgreSQL features. |
| DDL rollback | unsupported | Redshift DDL and `TRUNCATE` have transaction exceptions. |
| Combined alters | unsupported | Preserve the current conservative declaration; schema handling is a later layer. |
| PostgreSQL collations | unsupported | AWS does not support locale-specific or user-defined PostgreSQL collations. |
| Explain formats | none | Redshift returns text plans; JSON, XML, and YAML formats are not documented. |
| Explain options | `VERBOSE` only | AWS documents `EXPLAIN [VERBOSE] query`. |
| Group by selected primary keys | unsupported | Redshift does not enforce primary-key uniqueness. |
| Comments and default-keyword insert flags | unsupported | Preserve the current conservative contract until their dedicated SQL is designed. |

Feature names added only in newer Django versions may be assigned on older
versions because class attributes are harmless there. Tests assert the values
through the public feature object in every supported version; production code
does not branch on Django version.

### `operations.py`

`DatabaseOperations` starts from
`django.db.backends.base.operations.BaseDatabaseOperations`. It contains only
SQL generation and value adaptation required by this layer.

The public operation contract includes:

- Identifier quoting with double quotes, without double-quoting an already
  quoted identifier.
- Parameter-preserving `date_extract_sql()`, `date_trunc_sql()`,
  `datetime_cast_date_sql()`, `datetime_cast_time_sql()`,
  `datetime_extract_sql()`, `datetime_trunc_sql()`, `time_extract_sql()`, and
  `time_trunc_sql()` using the signatures shared by Django 4.2 through 6.x.
- Redshift `EXTRACT`, `DATE_TRUNC`, and `AT TIME ZONE` SQL. Lookup values and
  time-zone names are parameters rather than interpolated values.
- Django weekday numbering implemented from Redshift's documented `dow`
  result. ISO weekday and ISO year use compositions of documented Redshift
  date operations instead of undocumented PostgreSQL date parts.
- Normal `DISTINCT`, and an explicit `NotSupportedError` for field-specific
  distinct.
- An explicit modern-signature rejection for all `SELECT FOR UPDATE` variants.
- JSON serialization with Django's supplied encoder, integer pass-through,
  IP-address string adaptation, and UUID string-to-`uuid.UUID` conversion.
- Multi-row `VALUES` SQL without PostgreSQL conflict clauses.
- Plain `EXPLAIN` and `EXPLAIN VERBOSE`; formats and other PostgreSQL options
  are rejected before SQL execution.
- One `TRUNCATE TABLE <quoted-name>;` statement per table. Redshift identity
  values are not reset, and `allow_cascade` adds no PostgreSQL clause because
  Redshift permits truncating referenced tables and its constraints are
  informational.
- Empty sequence-reset SQL and an empty deferrable suffix.
- Redshift-compatible temporal subtraction SQL.
- Join expressions without the PostgreSQL backend's type-cast insertion.

`max_name_length()` remains 63 for compatibility with names produced by the
existing backend even though Redshift documents a 127-byte identifier limit.
Changing the value could alter automatically generated constraint or index
names and is therefore deferred to the schema/migration compatibility layer.

### Inserted identity retrieval

Redshift does not support `RETURNING`, and the driver contract does not supply
a portable generated identity value. The existing backend retrieves the value
with `SELECT MAX(pk)` after an insert. This behavior is preserved to avoid
breaking saved model instances before a tested replacement exists.

The new implementation quotes both the table and primary-key identifiers and
documents that the query is not concurrency-safe: another insert may become
the maximum before the lookup runs. A safe replacement requires a separate
design backed by Redshift semantics. The limitation does not justify silently
returning no primary key in this compatibility layer.

## Issue and pull-request decisions

### Issue #102 and pull request #103: adopt the intent

Issue #102 reports that adding a ManyToMany relation emitted unsupported
`ON CONFLICT DO NOTHING`. Pull request #103 proposed two coordinated changes:

1. Set `supports_ignore_conflicts = False`.
2. Return an empty conflict suffix.

The feature flag is the essential behavior. In Django 4.2 through 6.x it stops
the auto-created ManyToMany manager from selecting its conflict-ignoring fast
path. Django instead queries existing through-table rows and inserts only the
missing target IDs with a normal bulk insert.

The current backend has the modern empty `on_conflict_suffix_sql()` behavior
but does not set the feature flag to false. Consequently, it can still choose
the fast path without adding an actual conflict clause. Because Redshift does
not enforce unique constraints, that incomplete combination can create
duplicate relation rows rather than ignore them.

This design adopts pull request #103's complete intent:

- `supports_ignore_conflicts` is false.
- Explicit user calls to `bulk_create(ignore_conflicts=True)` raise Django's
  `NotSupportedError` before SQL generation.
- Auto-created ManyToMany additions take Django's existing-row lookup path and
  remain functional.
- No `ON CONFLICT` text is generated.

The lookup-then-insert sequence can still race when concurrent writers add the
same relation, because Redshift constraints are informational. That limitation
is documented and is not misrepresented as atomic conflict handling.

### Issue #14 and pull request #104: preserve rejection, defer emulation

Issue #14 established that Redshift does not support PostgreSQL `DISTINCT ON`.
The current backend raises `NotSupportedError` for `QuerySet.distinct(*fields)`.

Pull request #104 proposed emulating the behavior with
`ROW_NUMBER() OVER (PARTITION BY ...)`, but it also added a 271-line copy of an
old Django `SQLCompiler.as_sql()`. That code contains version-specific compiler
internals and APIs that predate the supported Django versions. Adopting it
would recreate the vendoring problem that issue #167 asks the redesign to
remove.

This layer therefore:

- Keeps normal `distinct()` working.
- Keeps field-specific distinct explicitly unsupported.
- Does not add a compiler module or set `compiler_module`.
- Records window-function emulation as a possible future focused design. Any
  future implementation must work through supported Django extension points,
  specify ordering and annotation semantics, and have its own cross-version
  test corpus.

Deferring pull request #104 is not a regression from a released supported
behavior because the proposal remains unmerged and the current backend rejects
field-specific distinct.

### Issue #171: implement the current operation signatures

Issue #171 demonstrates a `TypeError` when Django's `Trunc` expression passes
the `params` argument introduced after the vendored Django 4.0 implementation.
The inspected Django 4.2 through 6.x sources share the modern signatures used
by this design. The regression test compiles an actual Django `Trunc`
expression through the inactive redesigned wrapper and verifies SQL and
parameter preservation.

### Issues #167, #168, #175, and #183

- The independent base-class implementation satisfies issue #167's request to
  stop relying on a vendored PostgreSQL backend.
- The 15-cell blocking matrix makes Django 5.2 and 6.x support explicit for
  issues #168 and #183 rather than relying only on dependency metadata.
- Issue #175 is addressed by the driver boundary, but the initial release
  remains username/password-only by prior decision; it does not expand this
  layer's scope.

### Issue #109: retain for the schema layer

Issue #109 records duplicate identity syntax caused by Django-version changes.
It is schema-generation knowledge, not an operations concern. This layer does
not change AutoField mappings. The later schema/migration design must include
the released fix and prove that existing migration state remains unchanged.

## Compatibility classification

| Behavior | Result | Classification |
| --- | --- | --- |
| `Trunc` and modern date/time expressions | Work with modern signatures and preserved params | Existing bug fix |
| Plain `distinct()` | Preserved | Compatible |
| `distinct(*fields)` | Continues to raise `NotSupportedError` | Compatible |
| Model identity assignment | Preserves `MAX(pk)` lookup and its documented limitation | Compatible |
| ManyToMany `.add()` | Uses Django's pre-check path and emits no `ON CONFLICT` | Existing bug fix / PR #103 adoption |
| Explicit `bulk_create(ignore_conflicts=True)` | Raises before SQL generation | Intentional correction of a false capability claim |
| Nested `atomic()` | No database savepoint; an inner failure affects the containing transaction | Intentional correction of a PostgreSQL-only capability claim |
| PostgreSQL EXPLAIN formats/options | Rejected; plain and `VERBOSE` remain | Intentional correction |
| PostgreSQL JSON operators | Rejected while text serialization remains | Intentional correction |
| PostgreSQL tablespace/index/collation assumptions | Feature flags are false | Intentional correction; schema SQL remains later work |
| Multiple-table PostgreSQL `TRUNCATE`, `RESTART IDENTITY`, and `CASCADE` syntax | Replaced by one Redshift statement per table without reset/cascade clauses | Intentional correction |
| Existing migrations and database schema | Unchanged | Compatible; no database migration required |

The intentional corrections are recorded now and must be copied into the
activation PR's migration guide. They take effect for users only when the new
wrapper becomes the public backend in the final stack layer.

## Error handling

- Unsupported ORM capabilities fail with Django's `NotSupportedError` before a
  driver or socket call whenever Django exposes a validation hook.
- Invalid date/time lookup identifiers fail before interpolation.
- EXPLAIN formats and options outside Redshift's documented syntax fail before
  execution.
- Error text names the unsupported capability but does not expose SQL
  parameters or connection values.
- No method silently emits PostgreSQL syntax for an unsupported feature.

## Test strategy

All new tests live in `driver_tests` and use `uv`.

1. **Feature contract tests** instantiate the inactive wrapper and assert the
   explicit capability values on every supported Django version.
2. **Operation unit tests** assert SQL and parameter tuples for quoting,
   date/time extraction and truncation, timezone conversion, normal and
   field-specific distinct, identity lookup, UUID/JSON/IP adaptation,
   temporal subtraction, bulk values, flush, and explain behavior.
3. **Issue #171 regression** compiles Django's real `Trunc` expression through
   the redesigned wrapper. A direct method-call test alone is insufficient.
4. **Issue #102 / PR #103 regression** proves the false conflict flag is absent,
   explicit conflict-ignore is rejected, and an auto-created ManyToMany manager
   chooses the existing-row pre-check path without generating `ON CONFLICT`.
5. **Activation boundary tests** prove the public `base.DatabaseWrapper` is
   still the existing implementation while `_backend.DatabaseWrapper` uses
   the new operations and features.
6. **Compatibility tests** prove `base.py`, `meta.py`, `distkey.py`, migration
   modules, and schema-facing behavior are unchanged in this layer.
7. **Matrix verification** runs all 15 existing Django/Python/driver cells,
   the root regression suite, Ruff, package build, twine check, and wheel
   content inspection.

Tests do not open a network socket, require AWS credentials, invoke `psql`, or
connect to PostgreSQL or Redshift.

## References

Project history:

- [Issue #14: SELECT DISTINCT ON is not supported](https://github.com/jazzband/django-redshift-backend/issues/14)
- [Issue #102: Error when adding to ManyToManyField](https://github.com/jazzband/django-redshift-backend/issues/102)
- [Pull request #103: Removes the unsupported ON CONFLICT DO NOTHING clause](https://github.com/jazzband/django-redshift-backend/pull/103)
- [Pull request #104: add distinct on support](https://github.com/jazzband/django-redshift-backend/pull/104)
- [Issue #109: AutoField generates duplicate identity syntax](https://github.com/jazzband/django-redshift-backend/issues/109)
- [Issue #167: Reimplementation for Django 4.2+](https://github.com/jazzband/django-redshift-backend/issues/167)
- [Issue #168: Add Django 5.2 support](https://github.com/jazzband/django-redshift-backend/issues/168)
- [Issue #171: Operations signatures incompatible with Django 4.1+](https://github.com/jazzband/django-redshift-backend/issues/171)
- [Issue #175: IAM support](https://github.com/jazzband/django-redshift-backend/issues/175)
- [Issue #183: Support Django 6](https://github.com/jazzband/django-redshift-backend/issues/183)

Amazon Redshift specifications:

- [Amazon Redshift and PostgreSQL](https://docs.aws.amazon.com/redshift/latest/dg/c_redshift-and-postgres-sql.html)
- [Unsupported PostgreSQL features](https://docs.aws.amazon.com/redshift/latest/dg/c_unsupported-postgresql-features.html)
- [Unsupported PostgreSQL functions](https://docs.aws.amazon.com/redshift/latest/dg/c_unsupported-postgresql-functions.html)
- [Table constraints](https://docs.aws.amazon.com/redshift/latest/dg/t_Defining_constraints.html)
- [Date and time functions](https://docs.aws.amazon.com/redshift/latest/dg/Date_functions_header.html)
- [Interval data types and literals](https://docs.aws.amazon.com/redshift/latest/dg/r_interval_data_types.html)
- [BEGIN](https://docs.aws.amazon.com/redshift/latest/dg/r_BEGIN.html)
- [INSERT](https://docs.aws.amazon.com/redshift/latest/dg/r_INSERT_30.html)
- [TRUNCATE](https://docs.aws.amazon.com/redshift/latest/dg/r_TRUNCATE.html)
- [EXPLAIN](https://docs.aws.amazon.com/redshift/latest/dg/r_EXPLAIN.html)
- [Window functions](https://docs.aws.amazon.com/redshift/latest/dg/c_Window_functions.html)

Django sources inspected locally:

- Django 4.2.30 `django/db/backends/base/features.py` and
  `django/db/backends/base/operations.py`.
- Current Django 6.x `django/db/backends/base/features.py` and
  `django/db/backends/base/operations.py`.
- Both versions' `django/db/models/fields/related_descriptors.py`, confirming
  that `supports_ignore_conflicts=False` selects the ManyToMany pre-check path.
- Both versions' `django/db/models/query.py`, confirming that explicit
  `bulk_create(ignore_conflicts=True)` raises when the feature is false.

## Delivery

The work is delivered on `redesign/03-operations-features`, based directly on
`redesign/02-backend-foundation`. Its pull request is added above PR #4 in the
same GitHub stack and links tracking PR #1. Tracking PR #1 records the feature
decisions, intentional compatibility corrections, review layers, and final CI
results.

## Completion criteria

- The internal wrapper uses the independent Redshift operations and feature
  classes without activating them through the public `ENGINE`.
- Issue #171 is reproduced and fixed through Django's ORM expression API.
- The complete behavioral intent of PR #103 is covered without real Redshift.
- PR #104 is explicitly deferred and no custom compiler is introduced.
- Every enabled Redshift capability claim is supported by AWS documentation;
  capabilities without sufficient evidence remain false.
- All supported-version matrix cells pass.
- No existing migration or database schema change is required.
