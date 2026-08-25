# Schema and Migration Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an internal, database-free Redshift schema editor that supports the established Django matrix, preserves historical migration APIs, corrects future DistKey migration replay, and never repairs an existing database automatically.

**Architecture:** `schema.py` inherits Django's installed `BaseDatabaseSchemaEditor` and implements focused Redshift DDL helpers instead of copying Django's `_alter_field()`. `schema_django42.py` is a deletion-oriented subclass selected only for Django 4.2, while `_backend.DatabaseWrapper` registers the new editor and explicit type mappings without activating the public engine in `base.py`. Migration-corpus tests apply operations through `collect_sql=True` without a database connection.

**Tech Stack:** Python 3.10-3.14, Django 4.2.30/5.2/6.x public base-backend and migration APIs, `redshift-connector>=2.1.14,<3`, pytest 8, uv, Ruff 0.6.2, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-25-schema-migration-design.md`

## Global Constraints

- Treat the current Amazon Redshift Database Developer Guide as authoritative for DDL syntax and limitations.
- Use Django's installed `django.db.backends.base.schema.BaseDatabaseSchemaEditor`; do not import or copy Django's PostgreSQL backend or this project's `_vendor` schema code.
- Do not copy Django's complete `_alter_field()` implementation. Keep Redshift sequences in focused helpers with direct SQL tests.
- Keep `django_redshift_backend.base.DatabaseWrapper` and the public `ENGINE = "django_redshift_backend"` behavior unchanged in this stack layer.
- Register the new editor only on `django_redshift_backend._backend.DatabaseWrapper`.
- Keep `meta.py`, `distkey.py`, `DistKey`, `SortKey`, and checked-in migration files unchanged.
- Preserve the import paths `django_redshift_backend.DistKey`, `django_redshift_backend.SortKey`, and `django_redshift_backend.distkey.DistKey`.
- Keep `supports_foreign_keys=False` even while emitting informational FK DDL; Redshift does not enforce those constraints.
- Keep check constraints, ordinary indexes, generated columns, collations, tablespaces, and database comments unsupported.
- Correct future `AddIndex(DistKey)` and `RemoveIndex(DistKey)` operations, but never inspect or repair an already-applied database automatically.
- Preserve the legacy behavior in which a Python default used to add or recreate a non-null column remains as a Redshift database DEFAULT.
- Reject non-null add/recreation when no supported literal Python default or literal `db_default` exists; never synthesize `0`, an empty string, or the current time.
- Do not claim atomic DDL; keep `can_rollback_ddl=False`.
- Require no AWS credentials, PostgreSQL service, `psql`, or Redshift cluster.
- Use uv for every Python environment, test, lint, build, and packaging command.

## File map

- `django_redshift_backend/schema.py`: common schema editor, Redshift DDL templates, literal rendering, table options, constraints, index dispatch, add/alter/remove field behavior, and column-recreation helpers.
- `django_redshift_backend/schema_django42.py`: Django 4.2-only subclass and removal comment; no common Redshift behavior.
- `django_redshift_backend/_backend.py`: internal schema-editor selection and Redshift data type registration.
- `django_redshift_backend/features.py`: only schema capability flags that must be made explicitly conservative.
- `driver_tests/schema_helpers.py`: database-free wrapper, SQL collection, and normalization helpers shared by schema tests.
- `driver_tests/test_schema_base.py`: inheritance, selection, data types, literal rendering, and activation boundary.
- `driver_tests/test_schema_create.py`: CREATE TABLE, DISTKEY, SORTKEY, type, and validation contracts.
- `driver_tests/test_schema_indexes_constraints.py`: DistKey operations, unsupported indexes, and informational constraints.
- `driver_tests/test_schema_add_field.py`: AddField/default/FK/UNIQUE contracts and unsupported additions.
- `driver_tests/test_schema_alter_field.py`: direct VARCHAR widening, focused column recreation, conversions, null/default rules, and remove-field fallback.
- `driver_tests/test_schema_migrations.py`: historical import, deconstruction, migration graph/state, autodetector, and SQL replay contracts.
- `driver_tests/conftest.py`: install the existing `tests.testapp` migration corpus for database-free tests.
- `doc/schema-migrations.rst`: user-visible limitations, DistKey diagnosis, optional repair migration, persistent default behavior, and SortKey guidance.
- `doc/index.rst`: include the new schema/migration guide.
- `.github/workflows/driver-contract.yml`: unchanged unless the test count proves an existing matrix exclusion; the current matrix already runs all `driver_tests` on every supported combination.

---

### Task 1: Establish the common editor, Django 4.2 boundary, and Redshift type contract

**Files:**
- Create: `django_redshift_backend/schema.py`
- Create: `django_redshift_backend/schema_django42.py`
- Create: `driver_tests/schema_helpers.py`
- Create: `driver_tests/test_schema_base.py`
- Modify: `django_redshift_backend/_backend.py`
- Modify: `django_redshift_backend/features.py`
- Modify: `driver_tests/test_activation_boundary.py`
- Modify: `driver_tests/test_features.py`

**Interfaces:**
- Consumes: Django `BaseDatabaseSchemaEditor`; internal `_backend.DatabaseWrapper`; `DatabaseOperations.quote_name()`; `features.DatabaseFeatures`.
- Produces: `schema.DatabaseSchemaEditor`; `schema_django42.DatabaseSchemaEditor`; `_backend.schema_editor_class_for(version)`; explicit `DatabaseWrapper.data_types` and `data_types_suffix`; `schema_helpers.collect_schema_sql(callback)`.

- [ ] **Step 1: Write the failing base schema tests**

Create `driver_tests/schema_helpers.py`:

```python
import re

from django_redshift_backend._backend import DatabaseWrapper


def settings_dict():
    return {
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


def make_wrapper(alias="schema-contract"):
    return DatabaseWrapper(settings_dict(), alias)


def collect_schema_sql(callback):
    wrapper = make_wrapper()
    with wrapper.schema_editor(collect_sql=True, atomic=False) as editor:
        callback(editor)
    return [normalize_sql(statement) for statement in editor.collected_sql]


def normalize_sql(sql):
    return re.sub(r"\s+", " ", str(sql)).strip()
```

Create `driver_tests/test_schema_base.py` with these initial tests:

```python
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from django.db.backends.base.schema import BaseDatabaseSchemaEditor

from django_redshift_backend import _backend
from django_redshift_backend.schema import DatabaseSchemaEditor
from django_redshift_backend.schema_django42 import (
    DatabaseSchemaEditor as DatabaseSchemaEditor42,
)

from .schema_helpers import make_wrapper


def test_schema_editor_uses_installed_public_base_class():
    assert issubclass(DatabaseSchemaEditor, BaseDatabaseSchemaEditor)


def test_django42_selection_is_one_deletion_oriented_branch():
    assert _backend.schema_editor_class_for((4, 2, 30)) is DatabaseSchemaEditor42
    assert _backend.schema_editor_class_for((5, 2, 8)) is DatabaseSchemaEditor
    assert _backend.schema_editor_class_for((6, 0, 0)) is DatabaseSchemaEditor
    assert _backend.schema_editor_class_for((6, 1, 0)) is DatabaseSchemaEditor


def test_internal_wrapper_registers_selected_schema_editor():
    wrapper = make_wrapper()
    assert wrapper.SchemaEditorClass is _backend.schema_editor_class_for(
        __import__("django").VERSION
    )


def test_redshift_data_types_and_identity_suffixes_are_explicit():
    assert _backend.DatabaseWrapper.data_types["AutoField"] == "integer"
    assert _backend.DatabaseWrapper.data_types["BigAutoField"] == "bigint"
    assert _backend.DatabaseWrapper.data_types["SmallAutoField"] == "smallint"
    assert _backend.DatabaseWrapper.data_types["TextField"] == "varchar(max)"
    assert _backend.DatabaseWrapper.data_types["UUIDField"] == "varchar(36)"
    assert _backend.DatabaseWrapper.data_types["JSONField"] == "varchar"
    assert _backend.DatabaseWrapper.data_types["BinaryField"] == "varbyte(%(max_length)s)"
    assert _backend.DatabaseWrapper.data_types_suffix == {
        "AutoField": "identity(1, 1)",
        "BigAutoField": "identity(1, 1)",
        "SmallAutoField": "identity(1, 1)",
    }


def test_quote_value_supports_database_free_sql_collection():
    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    assert editor.quote_value(None) == "NULL"
    assert editor.quote_value(True) == "TRUE"
    assert editor.quote_value(False) == "FALSE"
    assert editor.quote_value(Decimal("1.25")) == "1.25"
    assert editor.quote_value("O'Reilly%") == "'O''Reilly%%'"
    assert editor.quote_value(b"\x80\x00") == "to_varbyte('8000', 'hex')"
    assert editor.quote_value(UUID("12345678-1234-5678-1234-567812345678")) == (
        "'12345678-1234-5678-1234-567812345678'"
    )
    assert editor.quote_value(date(2026, 8, 25)) == "'2026-08-25'"
    assert editor.quote_value(time(12, 30, 45)) == "'12:30:45'"
    assert editor.quote_value(datetime(2026, 8, 25, 12, 30, 45)) == (
        "'2026-08-25T12:30:45'"
    )
```

Append to `driver_tests/test_activation_boundary.py`:

```python
from django_redshift_backend.schema import DatabaseSchemaEditor


def test_new_schema_editor_is_internal_only():
    assert _backend.DatabaseWrapper.SchemaEditorClass.__module__.startswith(
        "django_redshift_backend.schema"
    )
    assert base.DatabaseWrapper.SchemaEditorClass is not DatabaseSchemaEditor
```

- [ ] **Step 2: Run the focused tests to verify red**

Run:

```powershell
uv run --project driver_tests --with "Django==5.2.8" pytest driver_tests/test_schema_base.py driver_tests/test_activation_boundary.py -q
```

Expected: collection fails because `schema.py`, `schema_django42.py`, and `schema_editor_class_for()` do not exist.

- [ ] **Step 3: Implement the common editor skeleton and literal renderer**

Create `django_redshift_backend/schema.py` with the common base and exact literal categories covered above:

```python
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from django.conf import settings
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


class DatabaseSchemaEditor(BaseDatabaseSchemaEditor):
    sql_create_table = "CREATE TABLE %(table)s (%(definition)s)"
    sql_delete_column = "ALTER TABLE %(table)s DROP COLUMN %(column)s CASCADE"
    sql_delete_fk = "ALTER TABLE %(table)s DROP CONSTRAINT %(name)s"

    @property
    def multiply_varchar_length(self):
        return int(getattr(settings, "REDSHIFT_VARCHAR_LENGTH_MULTIPLIER", 1))

    def quote_value(self, value):
        if value is None:
            return "NULL"
        if value is True:
            return "TRUE"
        if value is False:
            return "FALSE"
        if isinstance(value, bytes):
            return f"to_varbyte('{value.hex()}', 'hex')"
        if isinstance(value, (date, datetime, time, UUID)):
            value = value.isoformat() if hasattr(value, "isoformat") else str(value)
            return "'{}'".format(value.replace("'", "''").replace("%", "%%"))
        if isinstance(value, str):
            return "'{}'".format(value.replace("'", "''").replace("%", "%%"))
        if isinstance(value, (int, float, Decimal)):
            return str(value)
        raise ValueError(f"Cannot render {type(value).__name__} as Redshift DDL")
```

Create `django_redshift_backend/schema_django42.py`:

```python
from .schema import DatabaseSchemaEditor as CommonDatabaseSchemaEditor


class DatabaseSchemaEditor(CommonDatabaseSchemaEditor):
    """Django 4.2-only deletion boundary.

    Remove this module, the selector branch in _backend.py, and the
    test_django42_selection_is_one_deletion_oriented_branch test together when
    Django 4.2 support is dropped. Common Redshift behavior does not belong
    here.
    """
```

Modify `_backend.py` to import `django`, register explicit Redshift types, and use one selector:

```python
import django

from .schema import DatabaseSchemaEditor


def schema_editor_class_for(version):
    if version[:2] == (4, 2):
        from .schema_django42 import DatabaseSchemaEditor as DatabaseSchemaEditor42

        return DatabaseSchemaEditor42
    return DatabaseSchemaEditor


class DatabaseWrapper(BaseDatabaseWrapper):
    SchemaEditorClass = schema_editor_class_for(django.VERSION)
    data_types = {
        "AutoField": "integer",
        "BigAutoField": "bigint",
        "SmallAutoField": "smallint",
        "BinaryField": "varbyte(%(max_length)s)",
        "BooleanField": "boolean",
        "CharField": "varchar(%(max_length)s)",
        "CommaSeparatedIntegerField": "varchar(%(max_length)s)",
        "DateField": "date",
        "DateTimeField": "timestamp with time zone",
        "DecimalField": "numeric(%(max_digits)s, %(decimal_places)s)",
        "DurationField": "interval",
        "EmailField": "varchar(%(max_length)s)",
        "FileField": "varchar(%(max_length)s)",
        "FilePathField": "varchar(%(max_length)s)",
        "FloatField": "double precision",
        "IntegerField": "integer",
        "BigIntegerField": "bigint",
        "IPAddressField": "varchar(15)",
        "GenericIPAddressField": "varchar(39)",
        "JSONField": "varchar",
        "OneToOneField": "integer",
        "PositiveBigIntegerField": "bigint",
        "PositiveIntegerField": "integer",
        "PositiveSmallIntegerField": "smallint",
        "SlugField": "varchar(%(max_length)s)",
        "SmallIntegerField": "smallint",
        "TextField": "varchar(max)",
        "TimeField": "time",
        "UUIDField": "varchar(36)",
    }
    data_types_suffix = {
        "AutoField": "identity(1, 1)",
        "BigAutoField": "identity(1, 1)",
        "SmallAutoField": "identity(1, 1)",
    }
```

Set `supports_expression_defaults = False`, `supports_stored_generated_columns = False`, and `supports_virtual_generated_columns = False` explicitly in `features.py`, and add those three expectations to `driver_tests/test_features.py`.

- [ ] **Step 4: Run focused tests to verify green**

Run:

```powershell
uv run --project driver_tests --with "Django==4.2.30" pytest driver_tests/test_schema_base.py driver_tests/test_activation_boundary.py driver_tests/test_features.py -q
uv run --project driver_tests --with "Django==5.2.8" pytest driver_tests/test_schema_base.py driver_tests/test_activation_boundary.py driver_tests/test_features.py -q
uv run --project driver_tests --with "Django~=6.1.0" pytest driver_tests/test_schema_base.py driver_tests/test_activation_boundary.py driver_tests/test_features.py -q
```

Expected: all three commands pass. If Django 4.2 lacks either generated-column feature attribute on its base class, the explicit subclass attributes still make the tests pass without adding a version branch.

- [ ] **Step 5: Commit the schema foundation**

```powershell
git add django_redshift_backend/schema.py django_redshift_backend/schema_django42.py django_redshift_backend/_backend.py django_redshift_backend/features.py driver_tests/schema_helpers.py driver_tests/test_schema_base.py driver_tests/test_activation_boundary.py driver_tests/test_features.py
git commit -m "feat: establish Redshift schema editor"
```

---

### Task 2: Generate CREATE TABLE, DISTKEY, SORTKEY, and informational foreign keys

**Files:**
- Modify: `django_redshift_backend/schema.py`
- Create: `driver_tests/test_schema_create.py`

**Interfaces:**
- Consumes: `DatabaseSchemaEditor`, `DatabaseWrapper.data_types`, `DistKey`, `SortKey`, and `collect_schema_sql()` from Task 1.
- Produces: `DatabaseSchemaEditor.table_sql(model)`, `_get_create_options(model)`, `_validate_model_ddl(model)`, `_validate_field_ddl(field)`, `_model_indexes_sql(model)`, and `_informational_fk_sql(model, field)`.

- [ ] **Step 1: Write failing CREATE TABLE contract tests**

Create `driver_tests/test_schema_create.py`:

```python
import pytest
from django.db import models
from django.db.utils import NotSupportedError
from django.test.utils import isolate_apps, override_settings

from django_redshift_backend import DistKey, SortKey

from .schema_helpers import collect_schema_sql


@isolate_apps("driver_tests")
def test_create_model_emits_redshift_types_and_table_keys():
    class Referenced(models.Model):
        id = models.IntegerField(primary_key=True)

        class Meta:
            app_label = "driver_tests"

    class Event(models.Model):
        customer = models.ForeignKey(Referenced, models.CASCADE)
        created_at = models.DateTimeField()
        body = models.TextField()
        payload = models.BinaryField(max_length=16)

        class Meta:
            app_label = "driver_tests"
            indexes = [DistKey(fields=["customer"])]
            ordering = [SortKey("created_at"), SortKey("-id")]

    sql = collect_schema_sql(lambda editor: editor.create_model(Event))
    joined = " ".join(sql)
    assert 'CREATE TABLE "driver_tests_event"' in joined
    assert '"id" integer' in joined
    assert "identity(1, 1)" in joined
    assert '"body" varchar(max)' in joined
    assert '"payload" varbyte(16)' in joined
    assert 'DISTKEY("customer_id")' in joined
    assert 'SORTKEY("created_at", "id")' in joined
    assert 'FOREIGN KEY ("customer_id")' in joined
    assert 'REFERENCES "driver_tests_referenced" ("id")' in joined


@override_settings(REDSHIFT_VARCHAR_LENGTH_MULTIPLIER=3)
@isolate_apps("driver_tests")
def test_create_model_applies_varchar_byte_multiplier_once():
    class Label(models.Model):
        value = models.CharField(max_length=100)

        class Meta:
            app_label = "driver_tests"

    sql = collect_schema_sql(lambda editor: editor.create_model(Label))
    assert '"value" varchar(300)' in " ".join(sql)


@pytest.mark.parametrize("fields", [[], ["id", "name"]])
@isolate_apps("driver_tests")
def test_distkey_requires_exactly_one_field(fields):
    class InvalidKey(models.Model):
        name = models.CharField(max_length=20)

        class Meta:
            app_label = "driver_tests"
            indexes = [DistKey(fields=fields, name="invalid_distkey")]

    with pytest.raises(ValueError, match="exactly one field"):
        collect_schema_sql(lambda editor: editor.create_model(InvalidKey))


@isolate_apps("driver_tests")
def test_create_model_rejects_more_than_one_distkey():
    class DuplicateKey(models.Model):
        first = models.IntegerField()
        second = models.IntegerField()

        class Meta:
            app_label = "driver_tests"
            indexes = [
                DistKey(fields=["first"], name="first_distkey"),
                DistKey(fields=["second"], name="second_distkey"),
            ]

    with pytest.raises(ValueError, match="more than one DistKey"):
        collect_schema_sql(lambda editor: editor.create_model(DuplicateKey))


@isolate_apps("driver_tests")
def test_create_model_rejects_ordinary_model_index():
    class Indexed(models.Model):
        value = models.IntegerField()

        class Meta:
            app_label = "driver_tests"
            indexes = [models.Index(fields=["value"], name="ordinary_idx")]

    with pytest.raises(NotSupportedError, match="ordinary_idx"):
        collect_schema_sql(lambda editor: editor.create_model(Indexed))


@isolate_apps("driver_tests")
def test_db_index_is_an_implicit_noop_not_create_index_sql():
    class Indexed(models.Model):
        value = models.IntegerField(db_index=True)

        class Meta:
            app_label = "driver_tests"

    sql = collect_schema_sql(lambda editor: editor.create_model(Indexed))
    assert "CREATE INDEX" not in " ".join(sql)
```

Add a capability-based composite primary-key test for Django versions exposing
`models.CompositePrimaryKey`. Define `pk = models.CompositePrimaryKey("tenant",
"code")` and assert CREATE TABLE contains `PRIMARY KEY ("tenant", "code")`.
Skip only when the public field class is absent.

Add parameterized tests proving a model tablespace, table comment, field
tablespace, field comment, collation, and generated field are rejected before
the CREATE TABLE statement is collected. Construct only arguments exposed by
the installed Django signature and skip absent framework features.

- [ ] **Step 2: Run the CREATE tests to verify red**

Run:

```powershell
uv run --project driver_tests --with "Django==5.2.8" pytest driver_tests/test_schema_create.py -q
```

Expected: failures show missing table options, wrong VARCHAR length, absent informational FK, and ordinary index handling inherited from the base editor.

- [ ] **Step 3: Implement focused table-option and CREATE hooks**

In `schema.py`, import `re`, `FieldDoesNotExist`, `NotSupportedError`, `DistKey`, and `SortKey`, then add:

```python
    def _column_name(self, model, field_name):
        normalized = field_name.removeprefix("-")
        try:
            field = model._meta.get_field(normalized)
        except FieldDoesNotExist:
            column = normalized
        else:
            column = field.get_attname_column()[1]
        return self.quote_name(column)

    def _validate_field_ddl(self, field):
        unsupported = {
            "tablespace": getattr(field, "db_tablespace", None),
            "comment": getattr(field, "db_comment", None),
            "collation": getattr(field, "db_collation", None),
            "generated column": getattr(field, "generated", False),
        }
        for label, value in unsupported.items():
            if value:
                raise NotSupportedError(
                    f"Amazon Redshift does not support {label} on {field.name}."
                )

    def _validate_model_ddl(self, model):
        if model._meta.db_tablespace:
            raise NotSupportedError(
                f"Amazon Redshift does not support tablespace on {model._meta.label}."
            )
        if getattr(model._meta, "db_table_comment", None):
            raise NotSupportedError(
                f"Amazon Redshift does not support table comments on {model._meta.label}."
            )
        for field in model._meta.local_fields:
            self._validate_field_ddl(field)

    def _get_create_options(self, model):
        distkeys = [index for index in model._meta.indexes if isinstance(index, DistKey)]
        if len(distkeys) > 1:
            raise ValueError(f"Model {model.__name__} has more than one DistKey.")
        options = []
        if distkeys:
            if len(distkeys[0].fields) != 1:
                raise ValueError(
                    f"DistKey on model {model.__name__} must have exactly one field."
                )
            options.append(f"DISTKEY({self._column_name(model, distkeys[0].fields[0])})")
        sortkeys = [
            self._column_name(model, value)
            for value in model._meta.ordering
            if isinstance(value, SortKey)
        ]
        if sortkeys:
            options.append(f"SORTKEY({', '.join(sortkeys)})")
        return " ".join(options)

    def table_sql(self, model):
        sql, params = super().table_sql(model)
        options = self._get_create_options(model)
        if options:
            sql = f"{sql} {options}"
        return sql, params

    def _validate_model_indexes(self, model):
        for index in model._meta.indexes:
            if not isinstance(index, DistKey):
                raise NotSupportedError(
                    f"Amazon Redshift does not support index {index.name!r}."
                )

    def _model_indexes_sql(self, model):
        self._validate_model_indexes(model)
        return []

    def _informational_fk_sql(self, model, field):
        return self._create_fk_sql(
            model,
            field,
            "_fk_%(to_table)s_%(to_column)s",
        )

    def create_model(self, model):
        self._validate_model_ddl(model)
        self._validate_model_indexes(model)
        super().create_model(model)
        for field in model._meta.local_fields:
            if field.remote_field and field.db_constraint:
                self.deferred_sql.append(self._informational_fk_sql(model, field))
```

Calling `_validate_model_indexes()` before `super().create_model()` is required:
an unsupported explicit model index must fail before the CREATE TABLE statement
is executed, not after leaving a partially created table.

Extend `column_sql()` narrowly to multiply only a leading bounded VARCHAR declaration. Preserve parameters and leave `varchar(max)` unchanged:

```python
    def column_sql(self, model, field, include_default=False):
        definition, params = super().column_sql(model, field, include_default)
        if definition is None:
            return definition, params
        match = re.match(r"varchar\((\d+)\)", definition)
        if match:
            length = int(match.group(1)) * self.multiply_varchar_length
            definition = re.sub(r"^varchar\(\d+\)", f"varchar({length})", definition)
        return definition, params
```

Run the focused tests. If Django places identity suffixes in a different order between supported versions, assert semantic fragments here and reserve normalized full-statement goldens for Task 6.

- [ ] **Step 4: Verify CREATE behavior on the oldest and newest contracts**

```powershell
uv run --project driver_tests --with "Django==4.2.30" pytest driver_tests/test_schema_create.py driver_tests/test_schema_base.py -q
uv run --project driver_tests --with "Django~=6.1.0" pytest driver_tests/test_schema_create.py driver_tests/test_schema_base.py -q
```

Expected: both commands pass without a Django-version conditional in `schema.py`.

- [ ] **Step 5: Commit CREATE TABLE support**

```powershell
git add django_redshift_backend/schema.py driver_tests/test_schema_create.py
git commit -m "feat: generate Redshift table DDL"
```

---

### Task 3: Implement DistKey operations and explicit index/constraint behavior

**Files:**
- Modify: `django_redshift_backend/schema.py`
- Create: `driver_tests/test_schema_indexes_constraints.py`

**Interfaces:**
- Consumes: `_column_name()`, `DistKey`, Django `UniqueConstraint`, `CheckConstraint`, and base constraint SQL helpers.
- Produces: `add_index()`, `remove_index()`, `add_constraint()`, `remove_constraint()`, and `_validate_supported_constraint()`.

- [ ] **Step 1: Write failing DistKey and index tests**

Create `driver_tests/test_schema_indexes_constraints.py` with a shared isolated model and these assertions:

```python
import pytest
from django.db import models
from django.db.utils import NotSupportedError
from django.test.utils import isolate_apps

from django_redshift_backend import DistKey

from .schema_helpers import collect_schema_sql


@isolate_apps("driver_tests")
def test_add_distkey_uses_alter_distkey():
    class Event(models.Model):
        customer = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    index = DistKey(fields=["customer"], name="event_customer_distkey")
    sql = collect_schema_sql(lambda editor: editor.add_index(Event, index))
    assert sql == [
        'ALTER TABLE "driver_tests_event" ALTER DISTKEY "customer";'
    ]


@isolate_apps("driver_tests")
def test_remove_distkey_returns_table_to_auto_distribution():
    class Event(models.Model):
        customer = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    index = DistKey(fields=["customer"], name="event_customer_distkey")
    sql = collect_schema_sql(lambda editor: editor.remove_index(Event, index))
    assert sql == [
        'ALTER TABLE "driver_tests_event" ALTER DISTSTYLE AUTO;'
    ]


@pytest.mark.parametrize("method", ["add_index", "remove_index"])
@isolate_apps("driver_tests")
def test_explicit_ordinary_index_operation_fails(method):
    class Event(models.Model):
        value = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    index = models.Index(fields=["value"], name="event_value_idx")
    with pytest.raises(NotSupportedError, match="event_value_idx"):
        collect_schema_sql(lambda editor: getattr(editor, method)(Event, index))
```

Add tests for simple and advanced constraints:

```python
@isolate_apps("driver_tests")
def test_simple_unique_constraint_is_informational_ddl():
    class Event(models.Model):
        code = models.CharField(max_length=20)

        class Meta:
            app_label = "driver_tests"

    constraint = models.UniqueConstraint(fields=["code"], name="event_code_uniq")
    sql = collect_schema_sql(lambda editor: editor.add_constraint(Event, constraint))
    assert sql == [
        'ALTER TABLE "driver_tests_event" ADD CONSTRAINT "event_code_uniq" UNIQUE ("code");'
    ]


@pytest.mark.parametrize(
    "constraint",
    [
        models.CheckConstraint(condition=models.Q(value__gte=0), name="value_check"),
        models.UniqueConstraint(
            models.functions.Lower("value"),
            name="lower_value_uniq",
        ),
        models.UniqueConstraint(
            fields=["value"],
            condition=models.Q(value__isnull=False),
            name="conditional_value_uniq",
        ),
    ],
)
@isolate_apps("driver_tests")
def test_unsupported_constraints_fail_explicitly(constraint):
    class Event(models.Model):
        value = models.CharField(max_length=20)

        class Meta:
            app_label = "driver_tests"

    with pytest.raises(NotSupportedError, match=constraint.name):
        collect_schema_sql(lambda editor: editor.add_constraint(Event, constraint))
```

- [ ] **Step 2: Run the focused tests to verify red**

```powershell
uv run --project driver_tests --with "Django==5.2.8" pytest driver_tests/test_schema_indexes_constraints.py -q
```

Expected: DistKey calls inherit unsupported base index SQL, and unsupported advanced constraints are not rejected consistently.

- [ ] **Step 3: Implement DistKey dispatch and constraint validation**

Add these templates and methods to `DatabaseSchemaEditor`:

```python
    sql_alter_distkey = "ALTER TABLE %(table)s ALTER DISTKEY %(column)s"
    sql_remove_distkey = "ALTER TABLE %(table)s ALTER DISTSTYLE AUTO"

    def _validate_distkey(self, model, index):
        if len(index.fields) != 1:
            raise ValueError(
                f"DistKey on model {model.__name__} must have exactly one field."
            )
        return self._column_name(model, index.fields[0])

    def add_index(self, model, index, concurrently=False):
        if not isinstance(index, DistKey):
            raise NotSupportedError(
                f"Amazon Redshift does not support index {index.name!r}."
            )
        self.execute(
            self.sql_alter_distkey
            % {
                "table": self.quote_name(model._meta.db_table),
                "column": self._validate_distkey(model, index),
            }
        )

    def remove_index(self, model, index, concurrently=False):
        if not isinstance(index, DistKey):
            raise NotSupportedError(
                f"Amazon Redshift does not support index {index.name!r}."
            )
        self.execute(
            self.sql_remove_distkey
            % {"table": self.quote_name(model._meta.db_table)}
        )
```

Add `_validate_supported_constraint(constraint)` that accepts only a `UniqueConstraint` with non-empty `fields` and no expressions, condition, include, opclasses, or `nulls_distinct`. It raises `NotSupportedError` naming every `CheckConstraint` or advanced unique constraint. Call it before `super().add_constraint()` and `super().remove_constraint()`. Add `_validate_model_constraints(model)` and call it at the start of `create_model()` so an unsupported model constraint fails before CREATE TABLE is executed. Keep the Task 2 `_validate_model_indexes(model)` call immediately after it.

Reject historical `index_together` changes explicitly:

```python
    def alter_index_together(self, model, old_index_together, new_index_together):
        if set(old_index_together) != set(new_index_together):
            raise NotSupportedError(
                f"Amazon Redshift does not support index_together on {model._meta.label}."
            )
```

Because Django constructor names differ around the check-condition rename, tests instantiate `CheckConstraint` only with the keyword returned by a small test helper based on `inspect.signature(models.CheckConstraint)`. The production code remains version-free.

- [ ] **Step 4: Run index/constraint tests across Django versions**

```powershell
uv run --project driver_tests --with "Django==4.2.30" pytest driver_tests/test_schema_indexes_constraints.py -q
uv run --project driver_tests --with "Django==5.2.8" pytest driver_tests/test_schema_indexes_constraints.py -q
uv run --project driver_tests --with "Django~=6.1.0" pytest driver_tests/test_schema_indexes_constraints.py -q
```

Expected: all commands pass; warnings about Django's `check` to `condition` rename are avoided by the test helper.

- [ ] **Step 5: Commit index and constraint behavior**

```powershell
git add django_redshift_backend/schema.py driver_tests/test_schema_indexes_constraints.py
git commit -m "feat: add Redshift key and constraint DDL"
```

---

### Task 4: Implement AddField with persistent compatibility defaults

**Files:**
- Modify: `django_redshift_backend/schema.py`
- Create: `driver_tests/test_schema_add_field.py`

**Interfaces:**
- Consumes: `column_sql()`, `_informational_fk_sql()`, base `effective_default()`, and literal rendering.
- Produces: `_has_db_default(field)`, `_has_usable_add_default(field)`, `_column_for_add(field)`, and `add_field(model, field)`.

- [ ] **Step 1: Write failing AddField tests**

Create `driver_tests/test_schema_add_field.py`. Use `isolate_apps()` and `copy.copy()` historical fields so each operation has a model-bound field. Cover these exact contracts:

```python
import pytest
from django.db import models
from django.db.utils import NotSupportedError
from django.test.utils import isolate_apps

from .schema_helpers import collect_schema_sql


@isolate_apps("driver_tests")
def test_add_nullable_field_is_direct():
    class Pony(models.Model):
        weight = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    field = models.CharField(max_length=10, null=True)
    field.set_attributes_from_name("name")
    field.model = Pony
    sql = collect_schema_sql(lambda editor: editor.add_field(Pony, field))
    assert sql == [
        'ALTER TABLE "driver_tests_pony" ADD COLUMN "name" varchar(10) NULL;'
    ]


@isolate_apps("driver_tests")
def test_add_nonnull_field_keeps_python_default_for_compatibility():
    class Pony(models.Model):
        weight = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    field = models.CharField(max_length=10, default="unknown")
    field.set_attributes_from_name("name")
    field.model = Pony
    sql = collect_schema_sql(lambda editor: editor.add_field(Pony, field))
    assert sql == [
        'ALTER TABLE "driver_tests_pony" ADD COLUMN "name" varchar(10) DEFAULT \'unknown\' NOT NULL;'
    ]


@isolate_apps("driver_tests")
def test_add_nonnull_field_without_default_fails_before_execution():
    class Pony(models.Model):
        weight = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    field = models.CharField(max_length=10)
    field.set_attributes_from_name("name")
    field.model = Pony
    with pytest.raises(NotSupportedError, match="non-null.*default"):
        collect_schema_sql(lambda editor: editor.add_field(Pony, field))


@isolate_apps("driver_tests")
def test_add_unique_field_separates_column_and_constraint():
    class Pony(models.Model):
        weight = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    field = models.CharField(max_length=10, default="", unique=True)
    field.set_attributes_from_name("name")
    field.model = Pony
    sql = collect_schema_sql(lambda editor: editor.add_field(Pony, field))
    assert " UNIQUE" not in sql[0]
    assert "ADD CONSTRAINT" in sql[1]
    assert "UNIQUE" in sql[1]
```

Add a relation test asserting that `ADD COLUMN` contains neither `REFERENCES` nor `UNIQUE`, followed by an informational FK statement. Add tests rejecting an added `AutoField`, generated field when available, non-literal `db_default` when available, and every unsupported field option accepted by `_validate_field_ddl()`.

- [ ] **Step 2: Run AddField tests to verify red**

```powershell
uv run --project driver_tests --with "Django==5.2.8" pytest driver_tests/test_schema_add_field.py -q
```

Expected: the inherited base editor emits unsupported inline attributes or attempts to drop a temporary default.

- [ ] **Step 3: Implement a focused AddField path**

Import `copy`, `NOT_PROVIDED`, and `Value`. Add version-safe helpers:

```python
    def _has_db_default(self, field):
        has_db_default = getattr(field, "has_db_default", None)
        return bool(has_db_default and has_db_default())

    def _literal_db_default(self, field):
        if not self._has_db_default(field):
            return False
        return isinstance(field._db_default_expression, Value)

    def _has_usable_add_default(self, field):
        if self._literal_db_default(field):
            return True
        return (
            field.default is not NOT_PROVIDED
            and not callable(field.default)
            and self.effective_default(field) is not None
        )

    def _column_for_add(self, field):
        column_field = copy.copy(field)
        column_field._unique = False
        column_field.primary_key = False
        return column_field
```

Implement `add_field()` without calling the base method:

1. Route implicit M2M tables to `create_model()`.
2. Reject AutoField variants because Redshift cannot add IDENTITY.
3. Reject generated fields and non-literal `db_default`.
4. Reject `null=False` without `_has_usable_add_default(field)`, including
   callable Python defaults whose evaluated value would incorrectly become a
   fixed database DEFAULT.
5. Build the column definition from `_column_for_add(field)` with `include_default=True`.
6. Execute one `ADD COLUMN` statement and deliberately do not emit Django's usual `DROP DEFAULT`.
7. Append a simple UNIQUE constraint for `field.unique`.
8. Append `_informational_fk_sql()` for a relational field with `db_constraint=True`.

Use exact SQL templates:

```python
    sql_create_column = "ALTER TABLE %(table)s ADD COLUMN %(column)s %(definition)s"

    def add_field(self, model, field):
        if field.many_to_many and field.remote_field.through._meta.auto_created:
            return self.create_model(field.remote_field.through)
        if field.get_internal_type() in {"AutoField", "BigAutoField", "SmallAutoField"}:
            raise NotSupportedError("Amazon Redshift cannot add an IDENTITY column.")
        self._validate_field_ddl(field)
        if self._has_db_default(field) and not self._literal_db_default(field):
            raise NotSupportedError("Amazon Redshift expression db_default is unsupported.")
        if not field.null and not self._has_usable_add_default(field):
            raise NotSupportedError(
                f"Cannot add non-null field {model._meta.label}.{field.name} without a literal default."
            )
        definition, params = self.column_sql(
            model,
            self._column_for_add(field),
            include_default=True,
        )
        self.execute(
            self.sql_create_column
            % {
                "table": self.quote_name(model._meta.db_table),
                "column": self.quote_name(field.column),
                "definition": definition,
            },
            params,
        )
        if field.unique:
            self.execute(self._create_unique_sql(model, [field]))
        if field.remote_field and field.db_constraint:
            self.execute(self._informational_fk_sql(model, field))
```

If cloning a relation retains inline reference metadata on one supported minor, set `column_field.remote_field = field.remote_field` but rely on `supports_foreign_keys=False` and `can_create_inline_fk=False`; do not add a version branch.

- [ ] **Step 4: Verify AddField behavior across the contract matrix edges**

```powershell
uv run --project driver_tests --with "Django==4.2.30" pytest driver_tests/test_schema_add_field.py -q
uv run --project driver_tests --with "Django==5.2.8" pytest driver_tests/test_schema_add_field.py -q
uv run --project driver_tests --with "Django~=6.1.0" pytest driver_tests/test_schema_add_field.py -q
```

Expected: all commands pass. Django 4.2 skips only the `db_default` and generated-field cases via capability-based `pytest.mark.skipif`, not production version checks.

- [ ] **Step 5: Commit AddField behavior**

```powershell
git add django_redshift_backend/schema.py driver_tests/test_schema_add_field.py
git commit -m "feat: add Redshift column migration DDL"
```

---

### Task 5: Implement direct VARCHAR changes, focused recreation, and SORTKEY removal

**Files:**
- Modify: `django_redshift_backend/schema.py`
- Create: `driver_tests/test_schema_alter_field.py`

**Interfaces:**
- Consumes: `_has_usable_add_default()`, `_column_for_add()`, `column_sql()`, constraint helpers, and Django's translated `ProgrammingError`.
- Produces: `_varchar_length()`, `_can_alter_varchar_directly()`, `_conversion_sql()`, `_recreate_column()`, focused `_alter_field()`, and `remove_field()`.

- [ ] **Step 1: Write failing direct-alter and recreation tests**

Create `driver_tests/test_schema_alter_field.py` with a helper that binds old and new fields to the same isolated model. Add exact SQL sequence tests for:

```python
def alter_sql(model, old_field, new_field):
    old_field.model = model
    new_field.model = model
    return collect_schema_sql(
        lambda editor: editor.alter_field(model, old_field, new_field)
    )
```

Required cases and expected statements:

- `CharField(max_length=10, null=True)` to length 20 emits one `ALTER COLUMN TYPE varchar(20)`.
- length 20 to 10 on a nullable field emits ADD temporary, UPDATE, DROP, and RENAME.
- non-null length reduction with `default=""` emits the same four statements and leaves `DEFAULT ''` on the replacement.
- non-null length reduction without a default raises `NotSupportedError` before collecting any SQL.
- character to `BinaryField(max_length=16, null=True)` updates with an explicit `::varbyte` conversion.
- binary to character updates with an explicit `::varchar` conversion.
- changing only a Python default emits no SQL.
- changing a nullable literal `db_default` to another literal recreates with
  the new DEFAULT.
- dropping a literal `db_default` from a nullable field recreates without a
  DEFAULT.
- dropping a literal `db_default` from a non-null field raises
  `NotSupportedError` before SQL collection.
- nullable to non-null with a literal default recreates and retains that DEFAULT.
- nullable to non-null without a default raises `NotSupportedError`.
- non-null to nullable recreates without a DEFAULT.
- renaming a column emits the base Redshift `RENAME COLUMN` statement and updates deferred references.
- recreation of a field currently used by `DistKey` or `SortKey` raises
  `NotSupportedError` before SQL collection; changing table-key columns is not
  silently allowed to remove physical table attributes.

Add a fake-execution test for SORTKEY recovery:

```python
def test_remove_sortkey_column_retries_only_known_redshift_error(monkeypatch):
    calls = []
    editor = make_wrapper().schema_editor(atomic=False)

    def remove_once(self, model, field):
        calls.append((model, field))
        if len(calls) == 1:
            raise ProgrammingError("cannot drop sortkey column")

    monkeypatch.setattr(BaseDatabaseSchemaEditor, "remove_field", remove_once)
    monkeypatch.setattr(editor, "execute", lambda sql, params=(): calls.append(str(sql)))
    editor.remove_field(Pony, Pony._meta.get_field("name"))
    assert any("ALTER SORTKEY NONE" in value for value in calls if isinstance(value, str))
    assert len([value for value in calls if isinstance(value, tuple)]) == 2
```

Add a second test proving a programming error with different text is re-raised.

- [ ] **Step 2: Run the focused alter tests to verify red**

```powershell
uv run --project driver_tests --with "Django==5.2.8" pytest driver_tests/test_schema_alter_field.py -q
```

Expected: the inherited base editor emits unsupported ALTER DEFAULT/NULL SQL and lacks recreation and SORTKEY recovery.

- [ ] **Step 3: Implement focused direct-alter and conversion helpers**

Add these helpers to `schema.py`:

```python
    _varchar_re = re.compile(r"^varchar\((\d+)\)$", re.IGNORECASE)

    def _varchar_length(self, db_type):
        match = self._varchar_re.fullmatch(db_type or "")
        return int(match.group(1)) if match else None

    def _can_alter_varchar_directly(self, old_field, new_field, old_type, new_type):
        old_length = self._varchar_length(old_type)
        new_length = self._varchar_length(new_type)
        return (
            old_length is not None
            and new_length is not None
            and new_length >= old_length
            and old_field.null == new_field.null
            and old_field.unique == new_field.unique
            and old_field.primary_key == new_field.primary_key
            and not self._has_db_default(old_field)
            and not self._has_db_default(new_field)
        )

    def _conversion_sql(self, old_field, new_field):
        old_column = self.quote_name(old_field.column)
        old_kind = old_field.get_internal_type()
        new_kind = new_field.get_internal_type()
        if old_kind == "BinaryField" and new_kind != "BinaryField":
            return f"{old_column}::varchar"
        if old_kind != "BinaryField" and new_kind == "BinaryField":
            return f"{old_column}::varbyte"
        return old_column
```

Use `sql_alter_column_type = "ALTER TABLE %(table)s ALTER COLUMN %(column)s TYPE %(type)s"` for the direct path.

- [ ] **Step 4: Implement the focused recreation helper and `_alter_field()` dispatcher**

Implement `_recreate_column(model, old_field, new_field)` as a self-contained four-statement sequence. Use this concrete structure:

```python
    def _recreate_column(self, model, old_field, new_field):
        if getattr(new_field, "generated", False):
            raise NotSupportedError("Amazon Redshift generated fields are unsupported.")
        if self._has_db_default(new_field) and not self._literal_db_default(new_field):
            raise NotSupportedError("Amazon Redshift expression db_default is unsupported.")
        if not new_field.null and not self._has_usable_add_default(new_field):
            raise NotSupportedError(
                f"Cannot recreate non-null field {model._meta.label}.{new_field.name} "
                "without a literal default."
            )
        table_key_fields = {
            value.removeprefix("-")
            for value in model._meta.ordering
            if isinstance(value, SortKey)
        }
        table_key_fields.update(
            index.fields[0]
            for index in model._meta.indexes
            if isinstance(index, DistKey) and len(index.fields) == 1
        )
        if new_field.name in table_key_fields:
            raise NotSupportedError(
                f"Cannot recreate Redshift table-key field {model._meta.label}.{new_field.name}."
            )

        temporary = self._column_for_add(new_field)
        temporary.column = f"{new_field.column}_tmp"
        definition, params = self.column_sql(
            model,
            temporary,
            include_default=True,
        )
        self.execute(
            self.sql_create_column
            % {
                "table": self.quote_name(model._meta.db_table),
                "column": self.quote_name(temporary.column),
                "definition": definition,
            },
            params,
        )
        self.execute(
            "UPDATE %(table)s SET %(temporary)s = %(value)s "
            "WHERE %(old)s IS NOT NULL"
            % {
                "table": self.quote_name(model._meta.db_table),
                "temporary": self.quote_name(temporary.column),
                "value": self._conversion_sql(old_field, new_field),
                "old": self.quote_name(old_field.column),
            }
        )
        self.execute(
            self.sql_delete_column
            % {
                "table": self.quote_name(model._meta.db_table),
                "column": self.quote_name(old_field.column),
            }
        )
        self.execute(
            self.sql_rename_column
            % {
                "table": self.quote_name(model._meta.db_table),
                "old_column": self.quote_name(temporary.column),
                "new_column": self.quote_name(new_field.column),
                "type": new_field.db_parameters(connection=self.connection)["type"],
            }
        )
        self._recreate_state_constraints(model, new_field)
```

Add `_recreate_state_constraints(model, field)` with exact state-owned
constraints:

```python
    def _recreate_state_constraints(self, model, field):
        if field.primary_key:
            self.execute(self._create_primary_key_sql(model, field))
        elif field.unique:
            self.execute(self._create_unique_sql(model, [field]))
        for fields in model._meta.unique_together:
            if field.name in fields:
                unique_fields = [model._meta.get_field(name) for name in fields]
                self.execute(self._create_unique_sql(model, unique_fields))
        for constraint in model._meta.constraints:
            if isinstance(constraint, UniqueConstraint) and field.name in constraint.fields:
                self._validate_supported_constraint(constraint)
                self.execute(constraint.create_sql(model, self))
        if field.remote_field and field.db_constraint:
            self.execute(self._informational_fk_sql(model, field))
        for relation in model._meta.related_objects:
            related_field = relation.field
            if related_field.db_constraint and related_field.target_field.name == field.name:
                self.execute(
                    self._informational_fk_sql(relation.related_model, related_field)
                )
```

The helper must also satisfy these rules:

- reject a generated field or non-literal `db_default`;
- reject `new_field.null=False` when `_has_usable_add_default(new_field)` is false;
- use a copied new field named `<column>_tmp`, with UNIQUE/PK attributes suppressed for the ADD statement;
- call `column_sql(model, temporary, include_default=True)` so a required compatibility default persists;
- update every non-null old value through `_conversion_sql()`;
- drop the old column with CASCADE;
- rename the temporary column;
- recreate state-known UNIQUE, PK, outgoing FK, and incoming FK informational constraints.

Implement a focused `_alter_field()` dispatcher no larger than the Redshift decisions it owns:

```python
    def _alter_field(
        self,
        model,
        old_field,
        new_field,
        old_type,
        new_type,
        old_db_params,
        new_db_params,
        strict=False,
    ):
        if old_field.column != new_field.column:
            self.execute(
                self._rename_field_sql(
                    model._meta.db_table,
                    old_field,
                    new_field,
                    new_type,
                )
            )
            old_field = copy.copy(old_field)
            old_field.column = new_field.column
        if self._can_alter_varchar_directly(old_field, new_field, old_type, new_type):
            if old_type != new_type:
                self.execute(
                    self.sql_alter_column_type
                    % {
                        "table": self.quote_name(model._meta.db_table),
                        "column": self.quote_name(new_field.column),
                        "type": new_type,
                    }
                )
            return
        old_python_default = old_field.default
        new_python_default = new_field.default
        physical_change = (
            old_type != new_type
            or old_field.null != new_field.null
            or old_field.unique != new_field.unique
            or old_field.primary_key != new_field.primary_key
            or self._has_db_default(old_field) != self._has_db_default(new_field)
            or (
                self._has_db_default(old_field)
                and old_field.db_default != new_field.db_default
            )
            or (
                bool(old_field.remote_field) != bool(new_field.remote_field)
                or getattr(old_field, "db_constraint", None)
                != getattr(new_field, "db_constraint", None)
            )
        )
        if not physical_change and old_python_default != new_python_default:
            return
        if physical_change:
            self._recreate_column(model, old_field, new_field)
```

Do not call `super()._alter_field()` for the physical paths; that would reintroduce unsupported default/null clauses and version drift. Preserve Django's public `alter_field()` validation and M2M routing, which invokes this focused hook.

- [ ] **Step 5: Implement precise SORTKEY removal recovery**

Import `ProgrammingError` from `django.db.utils` and add:

```python
    def remove_field(self, model, field):
        try:
            return super().remove_field(model, field)
        except ProgrammingError as error:
            if "cannot drop sortkey" not in str(error).lower():
                raise
            if self.connection.errors_occurred:
                self.connection.close()
                self.connection.connect()
            self.execute(
                "ALTER TABLE %(table)s ALTER SORTKEY NONE"
                % {"table": self.quote_name(model._meta.db_table)}
            )
            return super().remove_field(model, field)
```

The test fake must expose `errors_occurred=False`; a separate test with `True` asserts one `close()` and one `connect()` call.

- [ ] **Step 6: Verify focused alter behavior across supported Django edges**

```powershell
uv run --project driver_tests --with "Django==4.2.30" pytest driver_tests/test_schema_alter_field.py -q
uv run --project driver_tests --with "Django==5.2.8" pytest driver_tests/test_schema_alter_field.py -q
uv run --project driver_tests --with "Django~=6.1.0" pytest driver_tests/test_schema_alter_field.py -q
```

Expected: all tests pass, and `rg -n "BASED FROM|django40|postgresql.schema" django_redshift_backend/schema.py django_redshift_backend/schema_django42.py` returns no matches.

- [ ] **Step 7: Commit alter/remove behavior**

```powershell
git add django_redshift_backend/schema.py driver_tests/test_schema_alter_field.py
git commit -m "feat: add focused Redshift column alterations"
```

---

### Task 6: Convert the historical migration corpus into a database-free compatibility gate

**Files:**
- Modify: `driver_tests/conftest.py`
- Create: `driver_tests/test_schema_migrations.py`
- Verify unchanged: `django_redshift_backend/meta.py`
- Verify unchanged: `django_redshift_backend/distkey.py`
- Verify unchanged: `tests/testapp/migrations/0001_initial.py`
- Verify unchanged: `tests/testapp/models.py`

**Interfaces:**
- Consumes: existing `tests.testapp` models/migration, `MigrationLoader`, `ProjectState`, `MigrationAutodetector`, and `collect_schema_sql()`.
- Produces: migration import/state/deconstruction/autodetector/forward-SQL contracts and a checked-in semantic SQL expectation.

- [ ] **Step 1: Make the existing test app available to driver contract tests**

Change `driver_tests/conftest.py` configuration from `INSTALLED_APPS=[]` to:

```python
INSTALLED_APPS=["tests.testapp"]
```

Keep `DATABASES={}` so importing and rendering migration state cannot connect to a database. Add a smoke test in the new file:

```python
from django.apps import apps


def test_existing_migration_corpus_app_is_installed_without_database():
    assert apps.get_app_config("testapp").name == "tests.testapp"
```

- [ ] **Step 2: Write failing public-path and graph/state tests**

Create `driver_tests/test_schema_migrations.py`:

```python
from importlib import import_module

from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.graph import MigrationGraph
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.state import ProjectState

from django_redshift_backend import DistKey, SortKey
from django_redshift_backend.distkey import DistKey as LegacyDistKey


def test_historical_public_paths_remain_stable():
    assert LegacyDistKey is DistKey
    assert DistKey(fields=["customer"], name="customer_distkey").deconstruct()[1] == (
        "django_redshift_backend.DistKey"
    )
    assert SortKey("-created_at").deconstruct()[0] == (
        "django_redshift_backend.SortKey"
    )


def test_existing_migration_module_imports_unchanged():
    module = import_module("tests.testapp.migrations.0001_initial")
    migration = module.Migration("0001_initial", "testapp")
    assert migration.initial is True
    assert migration.operations


def test_loader_builds_disk_graph_without_connection(monkeypatch):
    loader = MigrationLoader(None, ignore_no_migrations=True)
    assert ("testapp", "0001_initial") in loader.disk_migrations
    assert loader.graph.leaf_nodes("testapp") == [("testapp", "0001_initial")]


def test_unchanged_rendered_state_has_no_detected_changes():
    loader = MigrationLoader(None, ignore_no_migrations=True)
    state = loader.project_state(("testapp", "0001_initial"))
    changes = MigrationAutodetector(state, state.clone()).changes(MigrationGraph())
    assert changes == {}
```

- [ ] **Step 3: Run graph/state tests to verify red or expose configuration gaps**

```powershell
uv run --project driver_tests --with "Django==4.2.30" pytest driver_tests/test_schema_migrations.py -q
```

Expected before the conftest change: the loader cannot find `testapp`. Expected after the minimal conftest change: import, graph, state, and deconstruction tests pass without creating a cursor.

- [ ] **Step 4: Add forward migration replay with semantic SQL assertions**

Add a helper that applies the existing operations without `MigrationExecutor` or `MigrationRecorder`:

```python
def collect_migration_sql(migration):
    state = ProjectState()

    def apply(editor):
        nonlocal state
        for operation in migration.operations:
            next_state = state.clone()
            operation.state_forwards(migration.app_label, next_state)
            operation.database_forwards(
                migration.app_label,
                editor,
                state,
                next_state,
            )
            state = next_state

    return collect_schema_sql(apply), state
```

Add a test that imports `0001_initial`, calls this helper, and asserts:

- all five CREATE TABLE statements are present;
- `testapp_testmodelwithmetakeys` is created;
- a later statement contains `ALTER DISTKEY "fk_id"`, proving the historical `AddIndex(DistKey)` no-op is corrected;
- a SORTKEY declaration contains `"created_at"` and `"id"` in order;
- no `CREATE INDEX` statement exists;
- no connection/cursor method was called.

Store the normalized statements in an explicit tuple named `EXPECTED_0001_SEMANTIC_SQL` in the test module. Where constraint names differ across Django minors, normalize only the generated digest segment with:

```python
def normalize_generated_name(sql):
    return re.sub(r"_[0-9a-f]{8}_(fk|uniq|pk)\b", r"_<digest>_\1", sql)
```

Do not normalize keywords, column order, types, defaults, DISTKEY, SORTKEY, or operation order.

- [ ] **Step 5: Add a makemigrations check contract**

Use `call_command()` with no database settings:

```python
from django.core.management import call_command


def test_makemigrations_check_requires_no_new_migration(capsys):
    call_command("makemigrations", "testapp", check=True, dry_run=True, verbosity=1)
    captured = capsys.readouterr()
    assert "No changes detected" in captured.out
```

If Django 4.2 writes the message to stderr, combine `captured.out + captured.err` in the assertion for all versions. Do not skip the command and do not configure a database.

- [ ] **Step 6: Verify the migration gate on every supported Django minor**

```powershell
uv run --project driver_tests --with "Django==4.2.30" pytest driver_tests/test_schema_migrations.py -q
uv run --project driver_tests --with "Django==5.2.8" pytest driver_tests/test_schema_migrations.py -q
uv run --project driver_tests --with "Django~=6.0.0" pytest driver_tests/test_schema_migrations.py -q
uv run --project driver_tests --with "Django~=6.1.0" pytest driver_tests/test_schema_migrations.py -q
```

Expected: every command passes with identical semantic SQL after digest-only normalization.

- [ ] **Step 7: Prove protected compatibility files did not change**

```powershell
git diff redesign/03-operations-features -- django_redshift_backend/meta.py django_redshift_backend/distkey.py tests/testapp/migrations/0001_initial.py tests/testapp/models.py
```

Expected: no output.

- [ ] **Step 8: Commit the migration compatibility gate**

```powershell
git add driver_tests/conftest.py driver_tests/test_schema_migrations.py
git commit -m "test: preserve Redshift migration compatibility"
```

---

### Task 7: Document upgrade behavior and run the complete release gate

**Files:**
- Create: `doc/schema-migrations.rst`
- Modify: `doc/index.rst`
- Modify: `driver_tests/test_schema_base.py`
- Modify: `driver_tests/test_schema_create.py`
- Modify: `driver_tests/test_schema_indexes_constraints.py`
- Modify: `driver_tests/test_schema_add_field.py`
- Modify: `driver_tests/test_schema_alter_field.py`
- Modify: `driver_tests/test_schema_migrations.py`
- Verify: `.github/workflows/driver-contract.yml`

**Interfaces:**
- Consumes: all schema and migration contracts from Tasks 1-6 and the established GitHub Actions matrix.
- Produces: user-facing migration guidance, final negative-boundary tests, and full verification evidence for the stacked PR.

- [ ] **Step 1: Write the user-facing schema migration guide**

Create `doc/schema-migrations.rst` with these concrete sections and commands:

```rst
Schema and migration compatibility
==================================

Upgrading the backend does not create or apply a Django migration and does not
inspect or repair existing Redshift tables.

DISTKEY migration compatibility
-------------------------------

Older releases serialized ``DistKey`` as ``AddIndex`` but silently ignored the
database operation. New migration application emits ``ALTER DISTKEY``. Check an
existing table before choosing to repair it::

    SELECT "column", distkey
    FROM pg_table_def
    WHERE schemaname = 'public' AND tablename = 'your_table'
    ORDER BY sortkey, "column";

An application that confirms the intended key can add its own migration::

    from django.db import migrations

    class Migration(migrations.Migration):
        dependencies = [("your_app", "previous_migration")]
        operations = [
            migrations.RunSQL(
                'ALTER TABLE "your_table" ALTER DISTKEY "customer_id"',
                'ALTER TABLE "your_table" ALTER DISTSTYLE AUTO',
            ),
        ]

The backend never runs this correction automatically.

SORTKEY changes
---------------

``SortKey`` values in ``Meta.ordering`` affect table creation. Django does not
turn later ordering changes into schema operations, so changing an existing
sort key requires an explicit application migration.

Persistent defaults on non-null columns
---------------------------------------

Redshift can add a non-null column with a DEFAULT but does not document
``ALTER COLUMN DROP DEFAULT``. A Python default used while adding or recreating
a non-null column therefore remains a database DEFAULT for compatibility with
older backend releases. A non-null operation without a literal default is
rejected; the backend never invents a replacement value.

Informational constraints
-------------------------

Redshift does not enforce PRIMARY KEY, FOREIGN KEY, or UNIQUE constraints, but
its planner can use them. Data-loading processes must preserve the declared
relationships. Incorrect informational constraints can produce incorrect query
results.

Non-atomic recreation
---------------------

Most type reductions and nullability changes use ADD, UPDATE, DROP, and RENAME
statements. Review ``sqlmigrate`` output and take an appropriate backup because
the backend does not advertise transactional DDL rollback.
```

Add `schema-migrations` to the `toctree` in `doc/index.rst`.

- [ ] **Step 2: Add final negative architecture tests**

Append tests that scan the production modules through `pathlib.Path`:

```python
def test_new_schema_path_has_no_vendored_or_psycopg2_dependency():
    root = Path(__file__).parents[1] / "django_redshift_backend"
    source = "\n".join(
        (root / name).read_text(encoding="utf-8")
        for name in ("schema.py", "schema_django42.py", "_backend.py")
    )
    assert "_vendor" not in source
    assert "psycopg2" not in source
    assert "django.db.backends.postgresql" not in source


def test_schema_editor_does_not_copy_django_alter_field_commentary():
    source = (root / "schema.py").read_text(encoding="utf-8")
    assert "BASED FROM" not in source
    assert "four_way_default_alteration" not in source
```

Add an activation test asserting `base.py`, `meta.py`, `distkey.py`, and the existing migration file have the same Git blob IDs as `redesign/03-operations-features`. Implement this as a verification command rather than hard-coding commit hashes into a unit test.

- [ ] **Step 3: Run Ruff and all driver contracts on the current interpreter**

```powershell
uv run --with "ruff==0.6.2" ruff check django_redshift_backend driver_tests
uv run --with "ruff==0.6.2" ruff format --check django_redshift_backend driver_tests
uv run --project driver_tests --with "Django==5.2.8" pytest driver_tests -q
```

Expected: every command exits 0. Apply only mechanical Ruff fixes and rerun both Ruff commands if formatting changes.

- [ ] **Step 4: Run every supported Django/Python/driver matrix cell**

Run the same 15 cells declared in `.github/workflows/driver-contract.yml`, explicitly selecting Python with uv:

```powershell
uv run --python 3.10 --project driver_tests --with "Django==4.2.30" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --python 3.11 --project driver_tests --with "Django==4.2.30" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --python 3.12 --project driver_tests --with "Django==4.2.30" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --python 3.10 --project driver_tests --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --python 3.11 --project driver_tests --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --python 3.12 --project driver_tests --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --python 3.13 --project driver_tests --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --python 3.14 --project driver_tests --with "Django==5.2.8" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --python 3.12 --project driver_tests --with "Django~=6.0.0" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --python 3.13 --project driver_tests --with "Django~=6.0.0" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --python 3.14 --project driver_tests --with "Django~=6.0.0" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --python 3.12 --project driver_tests --with "Django~=6.1.0" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --python 3.13 --project driver_tests --with "Django~=6.1.0" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --python 3.14 --project driver_tests --with "Django~=6.1.0" --with "redshift-connector==2.1.14" pytest driver_tests -q
uv run --python 3.14 --project driver_tests --with "Django~=6.1.0" --with "redshift-connector==2.1.16" pytest driver_tests -q
```

Expected: all 15 commands exit 0. Record the pass count for each cell in the PR body; do not infer unrun cells from neighboring versions.

- [ ] **Step 5: Run root regression, build, packaging, and protected-file gates**

```powershell
uv run --with pytest --with django-environ pytest -q
uv build --sdist --wheel
uvx twine check dist/*
git diff --check redesign/03-operations-features..HEAD
git diff --exit-code redesign/03-operations-features -- django_redshift_backend/base.py django_redshift_backend/meta.py django_redshift_backend/distkey.py tests/testapp/migrations/0001_initial.py tests/testapp/models.py
git grep -n -E "_vendor|django\.db\.backends\.postgresql|psycopg2" -- django_redshift_backend/schema.py django_redshift_backend/schema_django42.py django_redshift_backend/_backend.py
```

Expected:

- root regression retains the known database skips and no failures;
- build and Twine exit 0;
- `git diff --check` exits 0;
- the protected-file diff exits 0 with no output;
- the forbidden-import grep exits 1 with no matches.

- [ ] **Step 6: Commit documentation and final test hardening**

```powershell
git add doc/schema-migrations.rst doc/index.rst driver_tests/test_schema_base.py driver_tests/test_schema_create.py driver_tests/test_schema_indexes_constraints.py driver_tests/test_schema_add_field.py driver_tests/test_schema_alter_field.py driver_tests/test_schema_migrations.py
git commit -m "docs: explain schema migration compatibility"
```

- [ ] **Step 7: Perform a final branch review before push or PR creation**

```powershell
git status --short --branch
git log --oneline --decorate redesign/03-operations-features..HEAD
git diff --stat redesign/03-operations-features..HEAD
git diff --check redesign/03-operations-features..HEAD
```

Expected: a clean `redesign/04-schema-migrations` worktree, only the planned schema/migration files in the stack diff, and no whitespace errors.

Do not push or create the stacked PR until the final review and verification evidence have been reported to the user.
