# Schema and Migration Compatibility Design

**Date:** 2026-08-25

**Status:** Draft for spec review

**Stack parent:** `redesign/03-operations-features`

## Context

The legacy backend vendors Django 4.0 schema-editor internals and copies large
parts of Django 3.2-era `BaseDatabaseSchemaEditor` behavior into `base.py`.
That preserves old Redshift workarounds, but it also freezes Django internals
and prevents reliable support for Django 4.2, 5.2, and 6.x.

This layer replaces that implementation with a Redshift schema editor based on
the installed Django version's public base backend. It preserves the useful
Redshift-specific knowledge in the existing code while avoiding a new copy of
Django's complete `_alter_field()` orchestration.

The upgrade must not itself require users to create or apply a database
migration. Existing migration files and their serialized public APIs remain
valid. Corrections to SQL generated when migrations are applied in the future
are allowed, but the package never repairs an existing database automatically.

## Goals

- Implement Redshift DDL using the installed Django
  `BaseDatabaseSchemaEditor` as the base class.
- Support the schema-editor contracts of Django 4.2.30, 5.2, and the supported
  Django 6.x minors.
- Keep Django 4.2-only behavior isolated and deletion-oriented.
- Preserve existing `DistKey`, `SortKey`, and historical migration import and
  deconstruction paths.
- Reuse the existing schema and migration tests as source material, including
  their SQL expectations and `sqlmigrate` coverage.
- Turn those tests into database-free contract tests that do not treat
  PostgreSQL as proof of Redshift behavior.
- Generate DDL that agrees with the Amazon Redshift SQL documentation.
- Correct future application of `AddIndex(DistKey)` without modifying an
  already-applied database.
- Fail explicitly for unsupported schema operations rather than silently
  pretending they succeeded.

## Non-goals

- Activating the redesigned backend through the public
  `django_redshift_backend.base.DatabaseWrapper` entry point.
- Connecting to a real Redshift cluster in CI.
- Automatically inspecting or repairing existing tables.
- Implementing the full introspection layer; that belongs to a later stack
  layer.
- Supporting IAM authentication or non-password authentication.
- Supporting ordinary, partial, expression, covering, or PostgreSQL operator
  class indexes.
- Tracking changes to `Meta.ordering` as database schema changes.
- Adding new public distribution-style or sort-style APIs.
- Supporting generated columns, collations, tablespaces, or database comments.
- Claiming that Redshift informational constraints enforce integrity.

## Authoritative references

The existing backend is evidence of compatibility intent, but AWS documentation
is authoritative for Redshift SQL behavior:

- [Amazon Redshift and PostgreSQL](https://docs.aws.amazon.com/redshift/latest/dg/c_redshift-and-postgres-sql.html)
- [CREATE TABLE](https://docs.aws.amazon.com/redshift/latest/dg/r_CREATE_TABLE_NEW.html)
- [ALTER TABLE](https://docs.aws.amazon.com/redshift/latest/dg/r_ALTER_TABLE.html)
- [ALTER TABLE examples](https://docs.aws.amazon.com/redshift/latest/dg/r_ALTER_TABLE_examples_basic.html)
- [Supported data types](https://docs.aws.amazon.com/redshift/latest/dg/c_Supported_data_types.html)
- [Isolation levels](https://docs.aws.amazon.com/redshift/latest/dg/c_serial_isolation.html)

The upstream Django source trees are the authority for the supported framework
contracts:

- [Django 4.2.30 source](https://github.com/django/django/tree/4.2.30) for
  Django 4.2.30.
- [Django main source](https://github.com/django/django/tree/main) for current
  Django 6.x development behavior.

## Architecture

### Common schema editor

`django_redshift_backend/schema.py` defines the common
`DatabaseSchemaEditor`. It inherits directly from Django's
`django.db.backends.base.schema.BaseDatabaseSchemaEditor`, not from the
PostgreSQL backend and not from any vendored copy.

The common editor owns Redshift behavior that has the same meaning across all
supported Django versions:

- table creation and Redshift table attributes;
- Redshift data type DDL;
- `DISTKEY` and `SORTKEY` generation;
- explicit rejection of unsupported indexes;
- Redshift-safe add, alter, rename, and remove column behavior;
- direct VARCHAR enlargement and column recreation for other supported
  conversions;
- default and nullability handling;
- informational primary-key, foreign-key, and unique constraints;
- VARBYTE default and conversion SQL;
- the existing SORTKEY-column removal recovery;
- database-free SQL collection and literal rendering.

The implementation prefers narrow schema-editor hooks such as
`table_sql()`, `column_sql()`, `add_field()`, `remove_field()`,
`_alter_column_type_sql()`, and `_alter_column_null_sql()`. A large copied
`_alter_field()` implementation is not accepted. If Redshift requires an
operation sequence that cannot be expressed through a narrow hook, that
sequence is placed in a focused helper whose inputs and emitted statements are
tested directly.

### Django 4.2 deletion boundary

`django_redshift_backend/schema_django42.py` may define a subclass of the
common editor. It contains only overrides that the Django 4.2 matrix proves
cannot use the common implementation.

No method is placed there merely because Django 4.2 is old. If the common
editor passes the 4.2 tests unchanged, the module remains trivial or is not
created until needed.

The internal wrapper selects the 4.2 class only when running Django 4.2. The
selection has a removal comment naming the 4.2-only tests. Removing Django 4.2
support must consist of deleting:

1. `schema_django42.py`;
2. the single version-selection branch;
3. the tests that exist solely to protect that branch.

Common Redshift behavior must never be moved into the 4.2 module.

### Stack activation boundary

This layer assigns the new schema editor to
`django_redshift_backend._backend.DatabaseWrapper.SchemaEditorClass`. The
redesigned wrapper is still internal. The public
`django_redshift_backend.base.DatabaseWrapper` remains on the legacy editor
until the later integration layer activates the complete backend.

An activation-boundary test proves that installing this intermediate stacked
PR does not change the public engine entry point.

### Feature interaction

The schema layer may tighten feature declarations when the DDL contract exposes
an inherited Django default that is unsafe. In particular:

- `supports_foreign_keys` remains `False` even though Redshift accepts FK DDL,
  because Redshift does not enforce the constraint and Django 6.x can use this
  flag to omit a join on the assumption of enforced referential integrity.
- `supports_column_check_constraints` and
  `supports_table_check_constraints` remain `False`.
- `can_rollback_ddl` remains `False`.
- all index capability flags remain `False`.
- generated-column, collation, tablespace, and comment support remain false.
- expression database defaults are not claimed unless every accepted
  expression is proven against the Redshift rules. Literal defaults can still
  be rendered by the schema editor.

## Public and migration compatibility

The following APIs and serialized paths remain unchanged:

- `django_redshift_backend.DistKey`;
- `django_redshift_backend.SortKey`;
- `django_redshift_backend.distkey.DistKey`;
- the existing `DistKey.deconstruct()` result;
- the existing `SortKey.deconstruct()` result;
- `ENGINE = "django_redshift_backend"`.

`meta.py` and `distkey.py` remain unchanged unless a failing compatibility test
demonstrates a required correction. They are retained because existing source
and migration modules import them, not as a new abstraction boundary.

Installing the new package with unchanged application models must satisfy all
of these conditions:

- existing migration modules import and deserialize;
- reconstructing their `ProjectState` succeeds;
- `makemigrations --check` detects no state change;
- no migration file in the repository is rewritten;
- the backend performs no schema query or repair at connection time;
- no new migration is required solely by the package upgrade.

## DDL contracts

### Data types

The schema tests preserve the existing Redshift intent for at least:

- `AutoField` as `integer identity(1, 1)`;
- `BigAutoField` as `bigint identity(1, 1)`;
- `SmallAutoField` as the Redshift-supported small integer identity form;
- `TextField` as `varchar(max)`;
- `UUIDField` as `varchar(36)`;
- `JSONField` as text-backed `varchar`;
- `BinaryField` as `varbyte(max_length)`;
- standard numeric, boolean, date, time, and timestamp types through explicit
  Redshift mappings rather than PostgreSQL inheritance.

The existing `REDSHIFT_VARCHAR_LENGTH_MULTIPLIER` setting remains supported.
It is applied to bounded VARCHAR declarations in one focused helper and is
covered by compatibility tests.

### CreateModel

`CreateModel` emits a single Redshift `CREATE TABLE` statement containing:

- column definitions;
- nullability and supported literal defaults;
- identity attributes;
- primary-key, unique, and foreign-key informational constraints;
- a single table-level `DISTKEY(column)` when declared;
- a compound table-level `SORTKEY(columns...)` from `SortKey` values in model
  ordering.

Only one `DistKey` is accepted and it must contain exactly one field. Field
names are resolved to database column names, including foreign-key `attname`
columns. Invalid declarations fail before SQL execution.

Redshift permits only one DISTKEY and accepts up to 400 SORTKEY columns. The
backend validates its own API invariants and leaves Redshift-specific type and
quota validation to the database where a complete database-free check would be
duplicative or unreliable.

### DistKey migration operations

`DistKey` remains a subclass of Django `Index` for migration serialization,
but the schema editor dispatches it separately from unsupported indexes.

- `AddIndex(DistKey)` emits
  `ALTER TABLE <table> ALTER DISTKEY <column>`.
- `RemoveIndex(DistKey)` emits
  `ALTER TABLE <table> ALTER DISTSTYLE AUTO`.
- replacing a `DistKey` is represented by the migration operations Django
  generates and produces the corresponding explicit Redshift alteration.

The legacy editor silently ignores `AddIndex(DistKey)`. Consequently, the
repository's existing `0001_initial.py` can create a table without its intended
DISTKEY when replayed as migrations. The redesigned editor corrects future
replay and future `AddIndex` operations.

This correction does not modify existing databases whose migration is already
recorded as applied. Release documentation must provide:

- diagnostic SQL for finding the current distribution style and key;
- an explanation of the historical no-op;
- an optional, user-owned migration example for applying the intended key.

The backend never runs that repair automatically.

### SortKey migration behavior

`SortKey` remains a `str` subclass stored in `Meta.ordering`. It affects table
creation, including migration-time `CreateModel`, exactly as the existing API
intends.

Django does not treat a later `Meta.ordering` change as a schema operation.
This layer does not invent an automatic DDL side effect for
`AlterModelOptions`. Users who need to change an existing Redshift sort key
must use an explicit migration operation such as `RunSQL`. That limitation is
documented.

### Ordinary indexes

Amazon Redshift does not support PostgreSQL secondary indexes. Therefore:

- `_model_indexes_sql()` does not generate ordinary indexes;
- `db_index=True` does not generate an index statement;
- PostgreSQL LIKE indexes are not generated;
- a model-level ordinary `Index` encountered during `CreateModel` is rejected
  rather than discarded;
- explicit `AddIndex` and `RemoveIndex` for anything other than `DistKey`
  raise `NotSupportedError` with the model and index name;
- partial, expression, covering, concurrent, operator-class, and
  `index_together` operations are not silently accepted.

This intentionally changes the legacy no-op behavior. A migration that
explicitly asks for an unsupported index must not report success when it did
nothing.

### Informational constraints

Redshift accepts primary-key, foreign-key, and unique constraints but does not
enforce them. It can use them as optimizer hints. The schema editor preserves
their DDL for compatibility with existing models and migrations, while feature
flags continue to tell Django that foreign-key integrity is not enforced.

The editor does not emit check constraints. Constraint discovery and
introspection are deferred to the introspection stack layer.

Simple field-based `UniqueConstraint`, `unique=True`, and historical
`unique_together` declarations emit informational UNIQUE constraints. Their
matching remove and alter operations emit constraint DDL. Conditional,
expression-based, included-column, operator-class, and nulls-distinct unique
constraints are index-backed PostgreSQL features and are rejected. Explicit
check-constraint operations are rejected instead of becoming no-ops.

Documentation must warn users that declared PK, FK, and UNIQUE constraints
must be kept true by their loading process; incorrect metadata can allow the
Redshift planner to produce incorrect results.

### AddField

Redshift `ALTER TABLE ADD COLUMN` cannot add a DISTKEY, SORTKEY, IDENTITY,
PRIMARY KEY, UNIQUE, or REFERENCES attribute. The editor therefore separates
column addition from supported informational constraint statements.

A nullable field, or a non-null field with a supported temporary/default value,
can be added directly. Adding a non-null field without a usable default is
rejected before execution with an actionable `NotSupportedError`, because the
operation is unsafe for a populated table.

Defaults used only to populate a migration do not become permanent database
defaults unless the model explicitly declares a supported `db_default` on a
Django version that provides that API.

### AlterField

The direct Redshift type alteration path is deliberately narrow:

- increasing the declared size of a VARCHAR column uses
  `ALTER COLUMN ... TYPE varchar(n)` when the column has no incompatible
  encoding or default condition known to the editor;
- every other supported type conversion uses the tested column-recreation
  sequence.

The recreation sequence is:

1. add a temporary column with the new definition;
2. copy or cast values from the old column;
3. drop the old column;
4. rename the temporary column to the original name;
5. recreate supported informational constraints when required.

The helper owns temporary-name construction, quoting, conversion SQL, and
constraint sequencing. Tests cover VARCHAR decrease, numeric and character
conversion, binary-to-character, character-to-binary, nullability changes,
literal default changes, primary keys, unique fields, and related fields.

The design does not claim that this sequence is atomic. Redshift DDL rollback
is not advertised, and emitted SQL makes the multi-statement operation visible
to users reviewing `sqlmigrate` output.

### Defaults across Django versions

Django 4.2 has Python-side field defaults but no `Field.db_default`. Django 5.0
and later add database defaults and generated fields. The common editor detects
capabilities through the installed Django field contract rather than importing
newer symbols on 4.2.

- Python-side migration defaults continue to support safe `AddField` and
  recreation operations.
- literal `db_default` values may be emitted on CREATE/ADD and preserved by
  recreation.
- changing or dropping a database default uses recreation because Redshift has
  no general `ALTER COLUMN SET/DROP DEFAULT` syntax in its documented
  `ALTER TABLE` grammar.
- expression defaults remain unsupported initially because Redshift requires a
  variable-free expression and a broad Django feature flag cannot express that
  subset safely.
- generated fields remain unsupported.

### RemoveField and SORTKEY recovery

Normal field removal emits Redshift `DROP COLUMN`. The existing compatibility
workaround for removing a column that Redshift reports as part of a SORTKEY is
preserved in focused form:

1. only the documented Redshift sort-key conflict is intercepted;
2. unrelated driver/database errors are re-raised unchanged;
3. the editor emits `ALTER SORTKEY NONE`;
4. it retries the field removal.

Driver-specific exception translation and reconnect behavior must use the new
driver boundary rather than importing psycopg2 types.

## Database-free migration gate

The repository's existing migration corpus and representative models are the
compatibility fixture. The gate runs without querying `django_migrations` or
opening a real connection.

It performs these checks:

1. import every existing migration module;
2. load the migration graph without reading applied-migration state;
3. reconstruct each relevant `ProjectState`;
4. assert stable `DistKey` and `SortKey` deconstruction paths;
5. compare unchanged model state with the autodetector and require zero new
   operations;
6. apply forwards and selected backwards schema operations through an internal
   wrapper with `collect_sql=True`;
7. normalize and compare generated SQL with checked-in expectations;
8. run a `sqlmigrate`-equivalent plan and require meaningful SQL assertions,
   not merely a non-empty result.

The old `test_sqlmigrate` is retained as source material but its real-database
skip and its assertion that any SQL is acceptable are replaced. Existing
`tests/test_migrations.py` cases are similarly extracted from their PostgreSQL
fixture and classified against AWS Redshift behavior.

## SQL compatibility classification

Every difference between legacy and redesigned generated SQL is recorded as
one of:

1. **Equivalent:** formatting, quoting, constraint-name, or statement-order
   differences with the same supported Redshift meaning.
2. **Future correction:** a corrected operation used when a migration is
   applied or replayed after installing the new backend, with no automatic
   effect on an already-applied database.
3. **Optional existing-database correction:** a historical bug or limitation
   that an existing database may retain. It requires documentation, diagnostic
   SQL, and an optional user-owned migration example.

Category 3 changes never execute on package import or connection.

The known `AddIndex(DistKey)` no-op is category 3 for existing databases and a
category 2 correction for future migration application.

## Test strategy

### Schema contract tests

Tests cover:

- internal schema-editor class selection by Django version;
- public activation isolation;
- Redshift type mappings and VARCHAR multiplication;
- CREATE TABLE with identity, PK, FK, UNIQUE, defaults, DISTKEY, and SORTKEY;
- invalid and multiple DistKey declarations;
- foreign-key field-to-column resolution;
- DistKey add and remove operations;
- explicit rejection of ordinary index operations;
- AddField constraints and temporary defaults;
- direct VARCHAR enlargement;
- recreation for VARCHAR reduction and other type changes;
- nullability and literal default transitions;
- VARBYTE literal and conversion SQL;
- removal of ordinary and SORTKEY columns;
- quoting and parameter collection without a driver connection;
- unsupported generated fields, comments, collations, and tablespaces;
- informational-constraint generation while `supports_foreign_keys` remains
  false.

### Migration compatibility tests

Tests cover:

- imports of `django_redshift_backend`, `.meta`, and `.distkey` paths;
- deconstruction and reconstruction of `DistKey` and `SortKey`;
- the checked-in `testapp` migration graph and project states;
- no-change migration autodetection;
- forward SQL from the existing `0001_initial.py`;
- selected backwards operation SQL;
- semantic SQL golden files or fixtures with explicitly documented
  version-specific differences;
- no database cursor creation during the database-free gate.

### Version matrix

The schema and migration contracts run on every supported combination already
established by the redesign:

- Django 4.2.30 on Python 3.10-3.12;
- Django 5.2 on Python 3.10-3.14;
- supported Django 6.x minors on Python 3.12-3.14.

The expected semantic SQL is shared across versions. A version-specific golden
is allowed only when Django intentionally changes a name or syntax detail and
the difference is recorded. It is not used to hide an accidental divergence.

### Legacy tests

The existing root suite remains green during this stack layer. Database-backed
PostgreSQL substitute tests may remain temporarily for the inactive legacy
entry point, but they are not evidence for the redesigned editor and do not
block removal once equivalent contract coverage exists.

### Deferred Redshift verification

Real-Redshift execution remains a future issue. The design relies on AWS
documentation and database-free SQL contracts now. The future integration
suite should verify representative CREATE, ADD, ALTER, recreation, constraint,
DISTKEY, SORTKEY, and rollback-failure behavior against a disposable Redshift
environment.

## Error model

Unsupported requests raise Django `NotSupportedError` before SQL execution
where the condition is knowable from model and migration state. Messages name
the operation and relevant model, field, or index.

Invalid backend declarations such as multiple DistKeys or a multi-column
DistKey raise `ValueError`, preserving the existing validation category.

Database errors arising from supported SQL are translated through the driver
boundary. The schema module does not import psycopg2 or rely on psycopg2
adapters.

The SORTKEY removal fallback catches only the translated programming error with
the known Redshift conflict. Every other error propagates.

## Documentation requirements

The implementation PR documents:

- supported and rejected schema operations;
- informational constraint semantics and their optimizer risk;
- the existing DistKey migration no-op;
- diagnostic SQL for existing distribution keys;
- an optional migration example to set the intended DistKey;
- the lack of automatic schema repair;
- the limitation on changing SortKey through `Meta.ordering`;
- multi-statement, non-atomic column recreation;
- the Django 4.2 compatibility module's deletion boundary.

## Acceptance criteria

This layer is complete when:

1. `schema.py` uses Django's installed public base schema editor and no vendored
   schema implementation.
2. No large Django `_alter_field()` copy is introduced.
3. Any 4.2-only override is isolated, test-proven, and deletion-commented.
4. The internal wrapper selects the correct schema editor while the public
   engine remains inactive.
5. Existing migration modules and public deconstruction paths remain stable.
6. `makemigrations --check` produces no migration for unchanged models.
7. The existing migration corpus produces reviewed, database-free Redshift SQL.
8. Future `AddIndex(DistKey)` and `RemoveIndex(DistKey)` produce documented
   Redshift DDL.
9. Existing databases are not inspected or modified automatically.
10. Unsupported ordinary indexes fail explicitly.
11. The supported Django/Python matrix, root regression suite, lint, build,
    Twine, import, protected-file, and activation-boundary checks pass.
12. No code in the new schema path imports psycopg2 or a vendored Django schema
    module.

## Risks and mitigations

### Django internal contract drift

Risk: schema-editor hooks remain framework internals even when imported from a
public backend module.

Mitigation: override the smallest surface, run every supported minor, and keep
semantic SQL tests shared across versions.

### Column recreation data risk

Risk: multi-statement recreation can fail partway and can transform data during
casts.

Mitigation: limit supported conversions, expose the full sequence through
`sqlmigrate`, retain `can_rollback_ddl=False`, and document backup/review
requirements.

### Informational constraint misuse

Risk: Redshift can optimize based on constraints it does not enforce.

Mitigation: keep Django's enforcement feature false, document the requirement
for externally maintained integrity, and never claim constraint checking.

### Corrected migration replay differs from an existing database

Risk: a newly created database gains the intended DistKey while an existing
database created through the historical no-op does not.

Mitigation: classify the difference explicitly, provide diagnostic and optional
migration guidance, and avoid automatic repair.

### Django 4.2 compatibility contaminates common code

Risk: scattered version checks make eventual removal difficult.

Mitigation: one selection branch and a test-proven, deletion-oriented
`schema_django42.py` boundary.
