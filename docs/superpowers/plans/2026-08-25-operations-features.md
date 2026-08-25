# Operations and Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a documented, AWS-free Redshift operations and feature layer that fixes issue #171, adopts pull request #103's complete conflict-handling intent, and remains inactive through the public backend entry point.

**Architecture:** `features.py` and `operations.py` inherit only Django's public base-backend classes and are registered only by the internal `_backend.DatabaseWrapper`. Feature flags are conservative and evidence-backed; SQL methods preserve parameters and reject PostgreSQL-only syntax before execution. `base.py` remains the active engine until the final stack layer.

**Tech Stack:** Python 3.10-3.14, Django 4.2.30/5.2.8/6.0/6.1 public base backend APIs, `redshift-connector>=2.1.14,<3`, pytest, uv, Ruff 0.6.2, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-25-operations-features-design.md`

## Global Constraints

- Treat the current Amazon Redshift Database Developer Guide as authoritative for Redshift SQL support and semantics.
- Use only public classes and functions under `django.db.backends.base`, `django.db.backends.utils`, and public ORM expression/compiler APIs.
- Do not inherit from, import, or copy Django's PostgreSQL backend or the project's `_vendor` package.
- Do not create a custom compiler or set `compiler_module` to a project module.
- Keep `django_redshift_backend.base.DatabaseWrapper` and `ENGINE = "django_redshift_backend"` behavior unchanged.
- Do not change `base.py`, `meta.py`, `distkey.py`, migrations, models, schema SQL, data type registration, or introspection.
- Support username/password authentication only; do not change the driver boundary.
- Do not require AWS credentials, `psql`, PostgreSQL, or a Redshift cluster.
- Preserve the existing `SELECT MAX(pk)` identity lookup and document its concurrency limitation.
- Set `supports_ignore_conflicts=False`; do not generate `ON CONFLICT`.
- Keep field-specific `DISTINCT ON` unsupported and do not implement pull request #104's compiler copy.
- Use the same production implementation on Django 4.2 through 6.x; add no Django-version branches.
- Use uv for every Python environment, test, lint, and build command.

---

### Task 1: Declare conservative Redshift feature contracts

**Files:**
- Create: `django_redshift_backend/features.py`
- Create: `driver_tests/test_features.py`
- Modify: `django_redshift_backend/_backend.py`
- Modify: `driver_tests/test_backend_wrapper.py`

**Interfaces:**
- Consumes: Django `BaseDatabaseFeatures`; `_backend.DatabaseWrapper` from the previous stack layer.
- Produces: `features.DatabaseFeatures`; `_backend.DatabaseWrapper.features_class = DatabaseFeatures`; explicit capability flags used by Django ORM and later tasks.

- [ ] **Step 1: Write the failing feature and wrapper tests**

Create `driver_tests/test_features.py`:

```python
import pytest
from django.db.backends.base.features import BaseDatabaseFeatures

from django_redshift_backend._backend import DatabaseWrapper
from django_redshift_backend.features import DatabaseFeatures


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


def test_features_use_public_base_class():
    assert issubclass(DatabaseFeatures, BaseDatabaseFeatures)


def test_internal_wrapper_registers_redshift_features():
    wrapper = DatabaseWrapper(settings_dict(), "feature-contract")
    assert wrapper.features_class is DatabaseFeatures
    assert isinstance(wrapper.features, DatabaseFeatures)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("supports_transactions", True),
        ("uses_savepoints", False),
        ("can_release_savepoints", False),
        ("can_return_columns_from_insert", False),
        ("can_return_rows_from_bulk_insert", False),
        ("can_return_rows_from_update", False),
        ("has_bulk_insert", True),
        ("supports_ignore_conflicts", False),
        ("supports_update_conflicts", False),
        ("supports_update_conflicts_with_target", False),
        ("has_select_for_update", False),
        ("has_select_for_update_nowait", False),
        ("has_select_for_update_skip_locked", False),
        ("has_select_for_update_of", False),
        ("has_select_for_no_key_update", False),
        ("can_distinct_on_fields", False),
        ("allows_group_by_selected_pks", False),
        ("allows_group_by_select_index", True),
        ("has_real_datatype", True),
        ("has_native_uuid_field", False),
        ("has_native_duration_field", True),
        ("supports_temporal_subtraction", True),
        ("supports_aggregate_filter_clause", False),
        ("supports_over_clause", True),
        ("supports_frame_range_fixed_distance", False),
        ("only_supports_unbounded_with_preceding_and_following", False),
        ("supports_json_field", True),
        ("has_native_json_field", False),
        ("can_introspect_json_field", False),
        ("has_json_object_function", False),
        ("supports_primitives_in_json_field", True),
        ("has_json_operators", False),
        ("supports_json_field_contains", False),
        ("supports_json_negative_indexing", False),
        ("supports_foreign_keys", False),
        ("can_create_inline_fk", False),
        ("can_defer_constraint_checks", False),
        ("supports_deferrable_unique_constraints", False),
        ("supports_nullable_unique_constraints", False),
        ("supports_partially_nullable_unique_constraints", False),
        ("supports_column_check_constraints", False),
        ("supports_table_check_constraints", False),
        ("can_introspect_default", False),
        ("can_introspect_foreign_keys", False),
        ("can_introspect_check_constraints", False),
        ("supports_tablespaces", False),
        ("supports_index_column_ordering", False),
        ("supports_index_on_text_field", False),
        ("supports_partial_indexes", False),
        ("supports_functions_in_partial_indexes", False),
        ("supports_covering_indexes", False),
        ("supports_expression_indexes", False),
        ("indexes_foreign_keys", False),
        ("can_rename_index", False),
        ("supports_sequence_reset", False),
        ("can_rollback_ddl", False),
        ("supports_atomic_references_rename", False),
        ("supports_combined_alters", False),
        ("supports_collation_on_charfield", False),
        ("supports_collation_on_textfield", False),
        ("supports_non_deterministic_collations", False),
        ("supports_comments", False),
        ("supports_comments_inline", False),
        ("supports_default_keyword_in_insert", True),
        ("supports_default_keyword_in_bulk_insert", True),
        ("supports_nulls_distinct_unique_constraints", False),
        ("supports_tuple_lookups", False),
        ("supports_tuple_comparison_against_subquery", False),
        ("supports_on_delete_db_cascade", False),
        ("supports_on_delete_db_default", False),
        ("supports_on_delete_db_null", False),
        ("supports_paramstyle_pyformat", False),
        ("supports_select_for_update_with_limit", False),
        ("supports_inspectdb", False),
        ("nulls_order_largest", True),
        ("delete_can_self_reference_subquery", True),
    ],
)
def test_redshift_feature_contract(name, expected):
    wrapper = DatabaseWrapper(settings_dict(), "feature-contract")
    assert getattr(wrapper.features, name) is expected


def test_redshift_explain_formats_are_text_only():
    wrapper = DatabaseWrapper(settings_dict(), "feature-contract")
    assert wrapper.features.supported_explain_formats == set()
```

Extend `driver_tests/test_backend_wrapper.py` imports and registration test:

```python
from django_redshift_backend.features import DatabaseFeatures


def test_wrapper_registers_foundation_components():
    wrapper = DatabaseWrapper(settings_dict(), "default")
    assert wrapper.client.__class__.__name__ == "DatabaseClient"
    assert isinstance(wrapper.creation, DatabaseCreation)
    assert isinstance(wrapper.features, DatabaseFeatures)
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```powershell
uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with Django==5.2.8 --with redshift-connector==2.1.14 --with psycopg2-binary pytest driver_tests/test_features.py driver_tests/test_backend_wrapper.py -q
```

Expected: collection fails because `django_redshift_backend.features` does not exist. Accept this missing production module as the RED state only if the identical import path is used by the later GREEN run.

- [ ] **Step 3: Implement the feature class and register it**

Create `django_redshift_backend/features.py`:

```python
from django.db.backends.base.features import BaseDatabaseFeatures


class DatabaseFeatures(BaseDatabaseFeatures):
    supports_transactions = True
    uses_savepoints = False
    can_release_savepoints = False

    can_return_columns_from_insert = False
    can_return_rows_from_bulk_insert = False
    can_return_rows_from_update = False
    has_bulk_insert = True
    supports_ignore_conflicts = False
    supports_update_conflicts = False
    supports_update_conflicts_with_target = False

    has_select_for_update = False
    has_select_for_update_nowait = False
    has_select_for_update_skip_locked = False
    has_select_for_update_of = False
    has_select_for_no_key_update = False
    supports_select_for_update_with_limit = False

    can_distinct_on_fields = False
    allows_group_by_selected_pks = False
    allows_group_by_select_index = True

    has_real_datatype = True
    has_native_uuid_field = False
    has_native_duration_field = True
    supports_temporal_subtraction = True

    supports_aggregate_filter_clause = False
    supports_over_clause = True
    supports_frame_range_fixed_distance = False
    only_supports_unbounded_with_preceding_and_following = False

    supports_json_field = True
    has_native_json_field = False
    can_introspect_json_field = False
    has_json_object_function = False
    supports_primitives_in_json_field = True
    has_json_operators = False
    supports_json_field_contains = False
    supports_json_negative_indexing = False

    supports_foreign_keys = False
    can_create_inline_fk = False
    can_defer_constraint_checks = False
    supports_deferrable_unique_constraints = False
    supports_nullable_unique_constraints = False
    supports_partially_nullable_unique_constraints = False
    supports_column_check_constraints = False
    supports_table_check_constraints = False
    can_introspect_default = False
    can_introspect_foreign_keys = False
    can_introspect_check_constraints = False

    supports_tablespaces = False
    supports_index_column_ordering = False
    supports_index_on_text_field = False
    supports_partial_indexes = False
    supports_functions_in_partial_indexes = False
    supports_covering_indexes = False
    supports_expression_indexes = False
    indexes_foreign_keys = False
    can_rename_index = False

    supports_sequence_reset = False
    can_rollback_ddl = False
    supports_atomic_references_rename = False
    supports_combined_alters = False

    supports_collation_on_charfield = False
    supports_collation_on_textfield = False
    supports_non_deterministic_collations = False
    supports_comments = False
    supports_comments_inline = False

    supports_default_keyword_in_insert = True
    supports_default_keyword_in_bulk_insert = True
    supports_nulls_distinct_unique_constraints = False
    supports_tuple_lookups = False
    supports_tuple_comparison_against_subquery = False
    supports_on_delete_db_cascade = False
    supports_on_delete_db_default = False
    supports_on_delete_db_null = False
    supports_paramstyle_pyformat = False
    supports_inspectdb = False

    supported_explain_formats = set()
    nulls_order_largest = True
    delete_can_self_reference_subquery = True
```

Modify `_backend.py`:

```python
from .features import DatabaseFeatures


class DatabaseWrapper(BaseDatabaseWrapper):
    features_class = DatabaseFeatures
```

Remove the now-unused `BaseDatabaseFeatures` import from `_backend.py`.

- [ ] **Step 4: Run feature tests on the oldest and newest Django lines**

Run:

```powershell
uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with Django==4.2.30 --with redshift-connector==2.1.14 --with psycopg2-binary pytest driver_tests/test_features.py driver_tests/test_backend_wrapper.py -q
uv --cache-dir .uv-cache run --python 3.14 --project driver_tests --with "Django~=6.1.0" --with redshift-connector==2.1.16 --with psycopg2-binary pytest driver_tests/test_features.py driver_tests/test_backend_wrapper.py -q
```

Expected: both commands pass with the same feature manifest.

- [ ] **Step 5: Commit the feature contract**

```powershell
git add django_redshift_backend/features.py django_redshift_backend/_backend.py driver_tests/test_features.py driver_tests/test_backend_wrapper.py
git commit -m "feat: declare Redshift feature contracts"
```

---

### Task 2: Implement modern date/time operations and issue #171 regression

**Files:**
- Create: `django_redshift_backend/operations.py`
- Create: `driver_tests/conftest.py`
- Create: `driver_tests/test_operations_datetime.py`
- Create: `driver_tests/test_issue_171.py`
- Modify: `django_redshift_backend/_backend.py`

**Interfaces:**
- Consumes: Django `BaseDatabaseOperations`, `split_tzname_delta`, ORM `Trunc`, and Task 1's internal wrapper.
- Produces: `operations.DatabaseOperations`; modern date/time operation methods returning `(sql: str, params: tuple)`; `_backend.DatabaseWrapper.ops_class = DatabaseOperations`.

- [ ] **Step 1: Configure Django once for database-free ORM compilation**

Create `driver_tests/conftest.py`:

```python
import django
from django.conf import settings


def pytest_configure():
    if not settings.configured:
        settings.configure(
            DATABASES={},
            INSTALLED_APPS=[],
            SECRET_KEY="driver-contract",
            USE_TZ=False,
        )
    django.setup()
```

- [ ] **Step 2: Write failing direct date/time operation tests**

Create `driver_tests/test_operations_datetime.py`:

```python
from django.test import override_settings

from django_redshift_backend._backend import DatabaseWrapper
from django_redshift_backend.operations import DatabaseOperations


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


def operations():
    return DatabaseWrapper(settings_dict(), "datetime-contract").ops


def test_internal_wrapper_registers_redshift_operations():
    wrapper = DatabaseWrapper(settings_dict(), "datetime-contract")
    assert wrapper.ops_class is DatabaseOperations
    assert isinstance(wrapper.ops, DatabaseOperations)


def test_date_extract_preserves_params():
    sql, params = operations().date_extract_sql("month", "event_time + %s", (7,))
    assert sql == "EXTRACT(MONTH FROM event_time + %s)"
    assert params == (7,)


def test_django_weekday_numbering_uses_documented_dow():
    sql, params = operations().date_extract_sql("week_day", "event_time", ())
    assert sql == "EXTRACT(DOW FROM event_time) + 1"
    assert params == ()


def test_iso_weekday_uses_documented_dow_composition():
    sql, params = operations().date_extract_sql("iso_week_day", "event_time", ())
    assert sql == "MOD(EXTRACT(DOW FROM event_time) + 6, 7) + 1"
    assert params == ()


def test_iso_year_uses_week_thursday():
    sql, params = operations().date_extract_sql("iso_year", "event_time", ())
    assert sql == (
        "EXTRACT(YEAR FROM DATE_TRUNC('week', event_time) + INTERVAL '3 day')"
    )
    assert params == ()


def test_date_extract_rejects_untrusted_lookup():
    try:
        operations().date_extract_sql("year); DROP TABLE x; --", "event_time", ())
    except ValueError as error:
        assert str(error) == "Unsupported date part identifier."
    else:
        raise AssertionError("invalid date part was accepted")


def test_date_trunc_parameterizes_date_part():
    sql, params = operations().date_trunc_sql("day", "event_time + %s", (7,))
    assert sql == "DATE_TRUNC(%s, event_time + %s)"
    assert params == ("day", 7)


@override_settings(USE_TZ=True)
def test_datetime_trunc_parameterizes_timezone():
    sql, params = operations().datetime_trunc_sql(
        "hour", "event_time + %s", (7,), "Asia/Tokyo"
    )
    assert sql == "DATE_TRUNC(%s, event_time + %s AT TIME ZONE %s)"
    assert params == ("hour", 7, "Asia/Tokyo")


@override_settings(USE_TZ=True)
def test_datetime_casts_preserve_timezone_params():
    ops = operations()
    date_sql, date_params = ops.datetime_cast_date_sql(
        "event_time", (), "Asia/Tokyo"
    )
    time_sql, time_params = ops.datetime_cast_time_sql(
        "event_time", (), "Asia/Tokyo"
    )
    assert date_sql == "(event_time AT TIME ZONE %s)::date"
    assert date_params == ("Asia/Tokyo",)
    assert time_sql == "(event_time AT TIME ZONE %s)::time"
    assert time_params == ("Asia/Tokyo",)


def test_time_extract_and_trunc_use_modern_signatures():
    ops = operations()
    extract_sql, extract_params = ops.time_extract_sql("minute", "event_time", ())
    trunc_sql, trunc_params = ops.time_trunc_sql("minute", "event_time", ())
    assert extract_sql == "EXTRACT(MINUTE FROM event_time)"
    assert extract_params == ()
    assert trunc_sql == "DATE_TRUNC(%s, event_time)::time"
    assert trunc_params == ("minute",)
```

- [ ] **Step 3: Write the failing ORM-level issue #171 regression**

Create `driver_tests/test_issue_171.py`:

```python
import datetime

from django.db import models
from django.db.models import DateTimeField, Value
from django.db.models.functions import Trunc
from django.db.models.sql.compiler import SQLCompiler
from django.db.models.sql.query import Query

from django_redshift_backend._backend import DatabaseWrapper


class TemporalEvent(models.Model):
    class Meta:
        app_label = "driver_contract"
        managed = False


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


def test_trunc_expression_compiles_through_django_orm():
    wrapper = DatabaseWrapper(settings_dict(), "issue-171")
    query = Query(TemporalEvent)
    compiler = SQLCompiler(query, wrapper, "issue-171")
    value = datetime.datetime(2026, 8, 25, 12, 30)
    expression = Trunc(
        Value(value, output_field=DateTimeField()),
        "day",
        output_field=DateTimeField(),
    ).resolve_expression(query)

    sql, params = compiler.compile(expression)

    assert sql == "DATE_TRUNC(%s, %s)"
    assert tuple(params) == ("day", str(value))
```

- [ ] **Step 4: Run the tests to verify RED**

Run:

```powershell
uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with Django==5.2.8 --with redshift-connector==2.1.14 --with psycopg2-binary pytest driver_tests/test_operations_datetime.py driver_tests/test_issue_171.py -q
```

Expected: collection fails because `django_redshift_backend.operations` does not exist.

- [ ] **Step 5: Implement parameter-preserving date/time operations**

Create the initial `django_redshift_backend/operations.py`:

```python
import re

from django.conf import settings
from django.db.backends.base.operations import BaseDatabaseOperations
from django.db.backends.utils import split_tzname_delta


class DatabaseOperations(BaseDatabaseOperations):
    _extract_format_re = re.compile(r"[A-Z_]+\Z")

    def _validated_date_part(self, lookup_type):
        date_part = lookup_type.upper()
        if not self._extract_format_re.fullmatch(date_part):
            raise ValueError("Unsupported date part identifier.")
        return date_part

    def _prepare_tzname_delta(self, tzname):
        tzname, sign, offset = split_tzname_delta(tzname)
        if offset:
            sign = "-" if sign == "+" else "+"
            return f"{tzname}{sign}{offset}"
        return tzname

    def _convert_sql_to_tz(self, sql, params, tzname):
        if tzname and settings.USE_TZ:
            return (
                f"{sql} AT TIME ZONE %s",
                (*params, self._prepare_tzname_delta(tzname)),
            )
        return sql, tuple(params)

    def date_extract_sql(self, lookup_type, sql, params):
        if lookup_type == "week_day":
            return f"EXTRACT(DOW FROM {sql}) + 1", params
        if lookup_type == "iso_week_day":
            return f"MOD(EXTRACT(DOW FROM {sql}) + 6, 7) + 1", params
        if lookup_type == "iso_year":
            return (
                "EXTRACT(YEAR FROM "
                f"DATE_TRUNC('week', {sql}) + INTERVAL '3 day')",
                params,
            )
        date_part = self._validated_date_part(lookup_type)
        return f"EXTRACT({date_part} FROM {sql})", params

    def date_trunc_sql(self, lookup_type, sql, params, tzname=None):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return f"DATE_TRUNC(%s, {sql})", (lookup_type, *params)

    def datetime_cast_date_sql(self, sql, params, tzname):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return f"({sql})::date", params

    def datetime_cast_time_sql(self, sql, params, tzname):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return f"({sql})::time", params

    def datetime_extract_sql(self, lookup_type, sql, params, tzname):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return self.date_extract_sql(lookup_type, sql, params)

    def datetime_trunc_sql(self, lookup_type, sql, params, tzname):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return f"DATE_TRUNC(%s, {sql})", (lookup_type, *params)

    def time_extract_sql(self, lookup_type, sql, params):
        return self.date_extract_sql(lookup_type, sql, params)

    def time_trunc_sql(self, lookup_type, sql, params, tzname=None):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return f"DATE_TRUNC(%s, {sql})::time", (lookup_type, *params)
```

Modify `_backend.py`:

```python
from .operations import DatabaseOperations


class DatabaseWrapper(BaseDatabaseWrapper):
    ops_class = DatabaseOperations
```

Remove the now-unused `BaseDatabaseOperations` import.

- [ ] **Step 6: Run direct and ORM regression tests on Django 4.2 and 6.1**

Run:

```powershell
uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with Django==4.2.30 --with redshift-connector==2.1.14 --with psycopg2-binary pytest driver_tests/test_operations_datetime.py driver_tests/test_issue_171.py -q
uv --cache-dir .uv-cache run --python 3.14 --project driver_tests --with "Django~=6.1.0" --with redshift-connector==2.1.16 --with psycopg2-binary pytest driver_tests/test_operations_datetime.py driver_tests/test_issue_171.py -q
```

Expected: both pass; the ORM test reaches `DatabaseOperations.datetime_trunc_sql()` without the issue #171 `TypeError`.

- [ ] **Step 7: Commit the date/time layer**

```powershell
git add django_redshift_backend/operations.py django_redshift_backend/_backend.py driver_tests/conftest.py driver_tests/test_operations_datetime.py driver_tests/test_issue_171.py
git commit -m "feat: add modern Redshift date operations"
```

---

### Task 3: Preserve supported general operations and reject PostgreSQL syntax

**Files:**
- Modify: `django_redshift_backend/operations.py`
- Create: `driver_tests/test_operations.py`
- Create: `driver_tests/test_temporal_subtraction.py`

**Interfaces:**
- Consumes: Task 2's `DatabaseOperations`; Django `NotSupportedError`, `Col`, management command styles, JSON encoders, and field metadata.
- Produces: quoting, distinct, identity lookup, converters, adapters, bulk values, flush, explain, temporal subtraction, join preparation, and explicit unsupported-operation behavior.

- [ ] **Step 1: Write failing quoting, distinct, identity, and unsupported-operation tests**

Create `driver_tests/test_operations.py` with the common setup and first tests:

```python
import ipaddress
import json
import uuid
from types import SimpleNamespace

import pytest
from django.core.management.color import no_style
from django.db.models import IntegerField
from django.db.utils import NotSupportedError

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


def operations():
    return DatabaseWrapper(settings_dict(), "operations-contract").ops


class FakeCursor:
    def __init__(self, row=(42,)):
        self.row = row
        self.calls = []

    def execute(self, sql):
        self.calls.append(sql)

    def fetchone(self):
        return self.row


def test_quote_name_quotes_once():
    ops = operations()
    assert ops.quote_name("event") == '"event"'
    assert ops.quote_name('"event"') == '"event"'


def test_plain_distinct_is_supported():
    assert operations().distinct_sql([], []) == (["DISTINCT"], [])


def test_field_specific_distinct_remains_unsupported():
    with pytest.raises(NotSupportedError, match="DISTINCT ON fields"):
        operations().distinct_sql(['"event"."kind"'], [[]])


def test_last_insert_id_preserves_quoted_max_workaround():
    cursor = FakeCursor()
    result = operations().last_insert_id(cursor, "event table", "event id")
    assert result == 42
    assert cursor.calls == ['SELECT MAX("event id") FROM "event table"']


def test_select_for_update_is_explicitly_unsupported():
    with pytest.raises(NotSupportedError, match="SELECT FOR UPDATE"):
        operations().for_update_sql(
            nowait=True,
            skip_locked=True,
            of=('"event"',),
            no_key=True,
        )


def test_sequence_and_deferrable_operations_are_empty():
    ops = operations()
    assert ops.sequence_reset_sql(no_style(), []) == []
    assert ops.sequence_reset_by_name_sql(no_style(), []) == []
    assert ops.deferrable_sql() == ""


def test_compatibility_name_limit_is_preserved():
    assert operations().max_name_length() == 63
```

- [ ] **Step 2: Add failing value adaptation and converter tests**

Append to `driver_tests/test_operations.py`:

```python
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, value):
        if isinstance(value, set):
            return sorted(value)
        return super().default(value)


def test_json_integer_and_ip_values_use_driver_neutral_types():
    ops = operations()
    assert ops.adapt_integerfield_value(7, "IntegerField") == 7
    assert ops.adapt_json_value({"values": {2, 1}}, CustomJSONEncoder) == (
        '{"values": [1, 2]}'
    )
    assert ops.adapt_ipaddressfield_value(ipaddress.ip_address("192.0.2.1")) == (
        "192.0.2.1"
    )
    assert ops.adapt_ipaddressfield_value("") is None


def test_uuid_converter_accepts_text_uuid_and_none():
    ops = operations()
    value = uuid.uuid4()
    expression = SimpleNamespace(
        output_field=SimpleNamespace(get_internal_type=lambda: "UUIDField")
    )
    converters = ops.get_db_converters(expression)
    assert ops.convert_uuidfield_value in converters
    assert ops.convert_uuidfield_value(str(value), expression, ops.connection) == value
    assert ops.convert_uuidfield_value(value, expression, ops.connection) == value
    assert ops.convert_uuidfield_value(None, expression, ops.connection) is None


def test_non_uuid_expression_has_no_redshift_converter():
    expression = SimpleNamespace(output_field=IntegerField())
    assert operations().get_db_converters(expression) == []
```

- [ ] **Step 3: Add failing bulk, flush, explain, temporal, and join tests**

Append:

```python
def test_bulk_insert_uses_multi_row_values_without_conflict_clause():
    sql = operations().bulk_insert_sql(
        [],
        [["%s", "%s"], ["%s", "%s"]],
    )
    assert sql == "VALUES (%s, %s), (%s, %s)"
    assert "CONFLICT" not in sql


def test_flush_uses_one_redshift_statement_per_table():
    sql = operations().sql_flush(
        no_style(),
        ["event", "event detail"],
        reset_sequences=True,
        allow_cascade=True,
    )
    assert sql == [
        'TRUNCATE TABLE "event";',
        'TRUNCATE TABLE "event detail";',
    ]
    assert all("RESTART IDENTITY" not in statement for statement in sql)
    assert all("CASCADE" not in statement for statement in sql)


def test_explain_supports_only_plain_and_verbose():
    ops = operations()
    assert ops.explain_query_prefix() == "EXPLAIN"
    assert ops.explain_query_prefix(verbose=True) == "EXPLAIN VERBOSE"
    with pytest.raises(ValueError, match="does not support any formats"):
        ops.explain_query_prefix(format="JSON")
    with pytest.raises(ValueError, match="Unknown options: ANALYZE"):
        ops.explain_query_prefix(analyze=True)


@pytest.mark.parametrize("internal_type", ["DateField", "DateTimeField", "TimeField"])
def test_temporal_subtraction_uses_microsecond_datediff(internal_type):
    ops = operations()
    sql, params = ops.subtract_temporals(
        internal_type,
        ("lhs_value + %s", (1,)),
        ("rhs_value + %s", (2,)),
    )
    assert sql == (
        "(INTERVAL '1 microsecond' * "
        "DATEDIFF(microsecond, (rhs_value + %s), (lhs_value + %s)))"
    )
    assert params == (2, 1)


def test_join_preparation_does_not_add_postgresql_casts():
    ops = operations()
    lhs_field = IntegerField()
    rhs_field = IntegerField()
    lhs, rhs = ops.prepare_join_on_clause("lhs", lhs_field, "rhs", rhs_field)
    assert lhs.alias == "lhs"
    assert lhs.target is lhs_field
    assert rhs.alias == "rhs"
    assert rhs.target is rhs_field


def test_default_compiler_remains_in_use():
    assert operations().compiler_module == "django.db.models.sql.compiler"
```

Create `driver_tests/test_temporal_subtraction.py` with an unmanaged model and
the public ORM compiler path used by every supported Django release:

```python
import datetime

import pytest
from django.db import models
from django.db.models import DateField, DateTimeField, TimeField, Value
from django.db.models.sql.compiler import SQLCompiler
from django.db.models.sql.query import Query

from django_redshift_backend._backend import DatabaseWrapper


class Event(models.Model):
    class Meta:
        app_label = "driver_contract"
        managed = False


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


def compile_subtraction(lhs_value, lhs_field, rhs_value, rhs_field):
    wrapper = DatabaseWrapper(settings_dict(), "temporal-subtraction")
    query = Query(Event)
    compiler = SQLCompiler(query, wrapper, "temporal-subtraction")
    expression = (
        Value(lhs_value, output_field=lhs_field)
        - Value(rhs_value, output_field=rhs_field)
    ).resolve_expression(query)
    sql, params = compiler.compile(expression)
    return sql, tuple(params)


@pytest.mark.parametrize(
    ("lhs_value", "rhs_value", "field", "expected_params"),
    [
        (
            datetime.date(2026, 8, 25),
            datetime.date(2026, 8, 24),
            DateField,
            ("2026-08-24", "2026-08-25"),
        ),
        (
            datetime.datetime(2026, 8, 25, 12, 30, 45, 123456),
            datetime.datetime(2026, 8, 24, 10, 15, 30, 654321),
            DateTimeField,
            ("2026-08-24 10:15:30.654321", "2026-08-25 12:30:45.123456"),
        ),
        (
            datetime.time(12, 30, 45, 123456),
            datetime.time(10, 15, 30, 654321),
            TimeField,
            ("10:15:30.654321", "12:30:45.123456"),
        ),
    ],
    ids=["date", "datetime", "time"],
)
def test_same_type_temporal_subtraction_compiles_to_interval(
    lhs_value, rhs_value, field, expected_params
):
    sql, params = compile_subtraction(
        lhs_value,
        field(),
        rhs_value,
        field(),
    )
    assert sql == (
        "(INTERVAL '1 microsecond' * DATEDIFF(microsecond, (%s), (%s)))"
    )
    assert params == expected_params


@pytest.mark.parametrize(
    ("lhs_value", "lhs_field", "rhs_value", "rhs_field", "expected_params"),
    [
        (
            datetime.date(2026, 8, 25),
            DateField,
            datetime.datetime(2026, 8, 24, 10, 15, 30),
            DateTimeField,
            ("2026-08-25", "2026-08-24 10:15:30"),
        ),
        (
            datetime.datetime(2026, 8, 25, 12, 30, 45),
            DateTimeField,
            datetime.date(2026, 8, 24),
            DateField,
            ("2026-08-25 12:30:45", "2026-08-24"),
        ),
    ],
    ids=["date-minus-datetime", "datetime-minus-date"],
)
def test_mixed_temporal_subtraction_exposes_deferred_compiler_limitation(
    lhs_value, lhs_field, rhs_value, rhs_field, expected_params
):
    """Characterize Django's pass-through SQL; don't claim runtime correctness."""
    sql, params = compile_subtraction(
        lhs_value,
        lhs_field(),
        rhs_value,
        rhs_field(),
    )
    assert sql == "(%s - %s)"
    assert params == expected_params
```

The mixed tests intentionally characterize Django's public compilation path.
In Django 4.2 through current 6.x, only same-type temporal operands reach
`subtract_temporals()`. Mixed Date/DateTime operands use `CombinedExpression`;
the public `combine_expression()` hook has no field-type metadata and
`check_expression_support()` is not called there. Do not override the compiler,
monkeypatch Django, or guess from SQL strings. Runtime-correct mixed subtraction
remains deferred to the compiler-focused layer.

- [ ] **Step 4: Run the tests to verify RED**

Run:

```powershell
uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with Django==5.2.8 --with redshift-connector==2.1.14 --with psycopg2-binary pytest driver_tests/test_operations.py driver_tests/test_temporal_subtraction.py -q
```

Expected: tests fail on unimplemented quoting, identity, unsupported behavior, adapters, flush, and explain methods.

- [ ] **Step 5: Implement the general operation methods**

Add these imports and class members to `operations.py`:

```python
import json
import uuid

from django.db.models.expressions import Col
from django.db.utils import NotSupportedError


class DatabaseOperations(BaseDatabaseOperations):
    explain_prefix = "EXPLAIN"

    def quote_name(self, name):
        if name.startswith('"') and name.endswith('"'):
            return name
        return f'"{name}"'

    def distinct_sql(self, fields, params):
        if fields:
            raise NotSupportedError(
                "DISTINCT ON fields is not supported by this database backend"
            )
        return ["DISTINCT"], []

    def last_insert_id(self, cursor, table_name, pk_name):
        """Return MAX(pk), preserving the existing non-concurrency-safe contract."""
        cursor.execute(
            f"SELECT MAX({self.quote_name(pk_name)}) "
            f"FROM {self.quote_name(table_name)}"
        )
        return cursor.fetchone()[0]

    def for_update_sql(self, nowait=False, skip_locked=False, of=(), no_key=False):
        raise NotSupportedError(
            "SELECT FOR UPDATE is not implemented for this database backend"
        )

    def sequence_reset_sql(self, style, model_list):
        return []

    def sequence_reset_by_name_sql(self, style, sequences):
        return []

    def deferrable_sql(self):
        return ""

    def max_name_length(self):
        return 63

    def get_db_converters(self, expression):
        converters = super().get_db_converters(expression)
        if expression.output_field.get_internal_type() == "UUIDField":
            converters.append(self.convert_uuidfield_value)
        return converters

    def convert_uuidfield_value(self, value, expression, connection):
        if value is not None and not isinstance(value, uuid.UUID):
            value = uuid.UUID(value)
        return value

    def adapt_integerfield_value(self, value, internal_type):
        return value

    def adapt_json_value(self, value, encoder):
        return json.dumps(value, cls=encoder)

    def adapt_ipaddressfield_value(self, value):
        return str(value) if value else None

    def bulk_insert_sql(self, fields, placeholder_rows):
        rows = (", ".join(row) for row in placeholder_rows)
        return "VALUES " + ", ".join(f"({row})" for row in rows)

    def sql_flush(self, style, tables, *, reset_sequences=False, allow_cascade=False):
        return [
            f"{style.SQL_KEYWORD('TRUNCATE TABLE')} "
            f"{style.SQL_FIELD(self.quote_name(table))};"
            for table in tables
        ]

    def explain_query_prefix(self, format=None, **options):
        if format:
            return super().explain_query_prefix(format=format, **options)
        normalized = {name.upper(): value for name, value in options.items()}
        unknown = sorted(set(normalized) - {"VERBOSE"})
        if unknown:
            raise ValueError(f"Unknown options: {', '.join(unknown)}")
        if normalized.get("VERBOSE"):
            return "EXPLAIN VERBOSE"
        return "EXPLAIN"

    def subtract_temporals(self, internal_type, lhs, rhs):
        lhs_sql, lhs_params = lhs
        rhs_sql, rhs_params = rhs
        return (
            "(INTERVAL '1 microsecond' * "
            f"DATEDIFF(microsecond, ({rhs_sql}), ({lhs_sql})))",
            (*rhs_params, *lhs_params),
        )

    def prepare_join_on_clause(self, lhs_table, lhs_field, rhs_table, rhs_field):
        return Col(lhs_table, lhs_field), Col(rhs_table, rhs_field)
```

Keep the Task 2 date/time methods in the same class. Do not add
`insert_statement()`, `on_conflict_suffix_sql()`, or `compiler_module` overrides;
Django's public base methods already produce `INSERT INTO`, an empty unsupported
conflict suffix, and the default compiler module.

- [ ] **Step 6: Run all operation tests on Django 4.2 and 6.1**

Run:

```powershell
uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with Django==4.2.30 --with redshift-connector==2.1.14 --with psycopg2-binary pytest driver_tests/test_operations.py driver_tests/test_operations_datetime.py driver_tests/test_issue_171.py driver_tests/test_temporal_subtraction.py -q
uv --cache-dir .uv-cache run --python 3.14 --project driver_tests --with "Django~=6.1.0" --with redshift-connector==2.1.16 --with psycopg2-binary pytest driver_tests/test_operations.py driver_tests/test_operations_datetime.py driver_tests/test_issue_171.py driver_tests/test_temporal_subtraction.py -q
```

Expected: all pass with identical SQL contracts.

- [ ] **Step 7: Commit the general operation contract**

```powershell
git add django_redshift_backend/operations.py driver_tests/test_operations.py driver_tests/test_temporal_subtraction.py
git commit -m "feat: add Redshift operation contracts"
```

---

### Task 4: Reproduce issue #102 and adopt pull request #103 behavior

**Files:**
- Create: `driver_tests/test_conflict_contract.py`

**Interfaces:**
- Consumes: Task 1's `supports_ignore_conflicts=False`; Django's public `QuerySet` validation and ManyToMany manager behavior.
- Produces: database-free proof that explicit conflict-ignore is rejected and auto-created ManyToMany relations choose the existing-row pre-check path.

- [ ] **Step 1: Write the explicit bulk-create conflict regression**

Create `driver_tests/test_conflict_contract.py`:

```python
from types import SimpleNamespace

import pytest
from django.db import models
from django.db.models import query as query_module
from django.db.models.fields import related_descriptors
from django.db.models.query import QuerySet
from django.db.utils import NotSupportedError

from django_redshift_backend._backend import DatabaseWrapper


class Target(models.Model):
    class Meta:
        app_label = "driver_contract"


class Source(models.Model):
    targets = models.ManyToManyField(Target)

    class Meta:
        app_label = "driver_contract"


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


def fake_connections():
    wrapper = DatabaseWrapper(settings_dict(), "redshift-contract")
    return {"redshift-contract": SimpleNamespace(features=wrapper.features)}


def test_explicit_ignore_conflicts_fails_before_sql(monkeypatch):
    monkeypatch.setattr(query_module, "connections", fake_connections())
    queryset = QuerySet(model=Target, using="redshift-contract")
    with pytest.raises(NotSupportedError, match="does not support ignoring conflicts"):
        queryset._check_bulk_create_options(True, False, None, None)
```

- [ ] **Step 2: Write the ManyToMany path-selection regression**

Append:

```python
def test_many_to_many_add_uses_existing_row_precheck(monkeypatch):
    connections = fake_connections()
    monkeypatch.setattr(related_descriptors, "connections", connections)
    manager = Source(pk=1).targets

    can_ignore_conflicts, must_send_signals, can_fast_add = manager._get_add_plan(
        "redshift-contract", manager.source_field_name
    )

    assert can_ignore_conflicts is False
    assert must_send_signals is False
    assert can_fast_add is False


def test_no_operation_generates_on_conflict():
    wrapper = DatabaseWrapper(settings_dict(), "redshift-contract")
    suffix = wrapper.ops.on_conflict_suffix_sql([], None, [], [])
    assert suffix == ""
    assert "CONFLICT" not in suffix
```

- [ ] **Step 3: Temporarily demonstrate the released backend's incomplete flag**

Before changing any production code in this task, run this read-only comparison:

```powershell
uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with Django==5.2.8 --with redshift-connector==2.1.14 --with psycopg2-binary python -c "from django_redshift_backend.base import DatabaseWrapper as Old; from django_redshift_backend._backend import DatabaseWrapper as New; s={'NAME':'warehouse','HOST':'example.test','PORT':'5439','USER':'alice','PASSWORD':'secret','OPTIONS':{},'TIME_ZONE':None,'CONN_MAX_AGE':0,'CONN_HEALTH_CHECKS':False,'AUTOCOMMIT':True}; print(Old(s,'old').features.supports_ignore_conflicts, New(s,'new').features.supports_ignore_conflicts)"
```

Expected: `True False`. Record this as evidence that Task 1 completes PR #103's missing feature flag while the public backend remains untouched.

- [ ] **Step 4: Run the conflict regressions on Django 4.2 and 6.1**

Run:

```powershell
uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with Django==4.2.30 --with redshift-connector==2.1.14 --with psycopg2-binary pytest driver_tests/test_conflict_contract.py -q
uv --cache-dir .uv-cache run --python 3.14 --project driver_tests --with "Django~=6.1.0" --with redshift-connector==2.1.16 --with psycopg2-binary pytest driver_tests/test_conflict_contract.py -q
```

Expected: all tests pass without a database connection. `_get_add_plan()` is used
only as test instrumentation for Django's public ManyToMany `add()` path; no
private Django helper is imported or called by production code.

- [ ] **Step 5: Commit the PR #103 regressions**

```powershell
git add driver_tests/test_conflict_contract.py
git commit -m "test: preserve Redshift conflict behavior"
```

---

### Task 5: Prove activation and compatibility boundaries

**Files:**
- Modify: `driver_tests/test_activation_boundary.py`
- Modify: `driver_tests/test_backend_wrapper.py`

**Interfaces:**
- Consumes: Tasks 1-4 production classes and the existing public `base.DatabaseWrapper`.
- Produces: behavioral proof that the new components are registered only on the internal wrapper and that pull request #104's custom compiler is absent.

- [ ] **Step 1: Add focused activation-boundary tests**

Replace `driver_tests/test_activation_boundary.py` with:

```python
from django.db.backends.base.features import BaseDatabaseFeatures
from django.db.backends.base.operations import BaseDatabaseOperations

from django_redshift_backend import _backend, base
from django_redshift_backend.features import DatabaseFeatures
from django_redshift_backend.operations import DatabaseOperations


def test_existing_engine_entry_point_is_not_activated():
    assert base.DatabaseWrapper is not _backend.DatabaseWrapper


def test_new_components_are_internal_only():
    assert _backend.DatabaseWrapper.features_class is DatabaseFeatures
    assert _backend.DatabaseWrapper.ops_class is DatabaseOperations
    assert base.DatabaseWrapper.features_class is not DatabaseFeatures
    assert base.DatabaseWrapper.ops_class is not DatabaseOperations


def test_new_components_use_only_public_base_classes():
    assert issubclass(DatabaseFeatures, BaseDatabaseFeatures)
    assert issubclass(DatabaseOperations, BaseDatabaseOperations)


def test_pull_request_104_compiler_copy_is_not_activated():
    assert DatabaseOperations.compiler_module == "django.db.models.sql.compiler"
```

- [ ] **Step 2: Extend wrapper component registration**

Ensure `driver_tests/test_backend_wrapper.py` imports and asserts both new classes:

```python
from django_redshift_backend.features import DatabaseFeatures
from django_redshift_backend.operations import DatabaseOperations


def test_wrapper_registers_foundation_components():
    wrapper = DatabaseWrapper(settings_dict(), "default")
    assert wrapper.client.__class__.__name__ == "DatabaseClient"
    assert isinstance(wrapper.creation, DatabaseCreation)
    assert isinstance(wrapper.features, DatabaseFeatures)
    assert isinstance(wrapper.ops, DatabaseOperations)
```

- [ ] **Step 3: Run activation and full representative contracts**

Run:

```powershell
uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with Django==4.2.30 --with redshift-connector==2.1.14 --with psycopg2-binary pytest driver_tests -q
uv --cache-dir .uv-cache run --python 3.12 --project driver_tests --with Django==5.2.8 --with redshift-connector==2.1.14 --with psycopg2-binary pytest driver_tests -q
uv --cache-dir .uv-cache run --python 3.14 --project driver_tests --with "Django~=6.1.0" --with redshift-connector==2.1.16 --with psycopg2-binary pytest driver_tests -q
```

Expected: all three suites pass without AWS, PostgreSQL, Redshift, or `psql`.

- [ ] **Step 4: Verify forbidden files and dependencies are unchanged**

Run:

```powershell
git diff redesign/02-backend-foundation -- django_redshift_backend/base.py django_redshift_backend/meta.py django_redshift_backend/distkey.py pyproject.toml .github/workflows/driver-contract.yml
rg -n "django\.db\.backends\.postgresql|django_redshift_backend\._vendor" django_redshift_backend/features.py django_redshift_backend/operations.py django_redshift_backend/_backend.py
rg -n "compiler_module\s*=" django_redshift_backend
```

Expected: the first two commands have no output. The compiler search finds no new project override; inherited references under the untouched vendored/current backend do not count as redesigned-component use.

- [ ] **Step 5: Commit the activation boundary**

```powershell
git add driver_tests/test_activation_boundary.py driver_tests/test_backend_wrapper.py
git commit -m "test: lock operations activation boundary"
```

---

### Task 6: Run the full matrix and prepare stacked PR evidence

**Files:**
- Modify only if verification exposes a defect in Tasks 1-5.
- Do not create a temporary PR-body file.

**Interfaces:**
- Consumes: the completed branch and existing GitHub Actions matrix.
- Produces: fresh verification evidence, a clean branch, and the PR/tracking text used by the finishing workflow.

- [ ] **Step 1: Run all 15 workflow cells exactly**

Run this PowerShell matrix and stop on the first failure:

```powershell
$cells = @(
    @('3.10', 'Django==4.2.30', '2.1.14'),
    @('3.11', 'Django==4.2.30', '2.1.14'),
    @('3.12', 'Django==4.2.30', '2.1.14'),
    @('3.10', 'Django==5.2.8', '2.1.14'),
    @('3.11', 'Django==5.2.8', '2.1.14'),
    @('3.12', 'Django==5.2.8', '2.1.14'),
    @('3.13', 'Django==5.2.8', '2.1.14'),
    @('3.14', 'Django==5.2.8', '2.1.14'),
    @('3.12', 'Django~=6.0.0', '2.1.14'),
    @('3.13', 'Django~=6.0.0', '2.1.14'),
    @('3.14', 'Django~=6.0.0', '2.1.14'),
    @('3.12', 'Django~=6.1.0', '2.1.14'),
    @('3.13', 'Django~=6.1.0', '2.1.14'),
    @('3.14', 'Django~=6.1.0', '2.1.14'),
    @('3.14', 'Django~=6.1.0', '2.1.16')
)
foreach ($cell in $cells) {
    uv --cache-dir .uv-cache run --python $cell[0] --project driver_tests --with $cell[1] --with "redshift-connector==$($cell[2])" --with psycopg2-binary pytest driver_tests -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

Expected: all 15 cells pass. Record the exact test count from the output; do not predict it in the PR body.

- [ ] **Step 2: Run root regression and lint**

```powershell
uv --cache-dir .uv-cache run --python 3.12 --with pytest --with pytest-cov --with mock --with django-environ --with psycopg2-binary pytest -q
uv --cache-dir .uv-cache run --with tox tox -e lint
```

Expected: root regression remains 10 passed and 22 skipped with only the known Django deprecation warning; lint passes.

- [ ] **Step 3: Build and inspect distributions**

```powershell
uv --cache-dir .uv-cache run --with build --with twine python -m build
uv --cache-dir .uv-cache run --with twine twine check dist/*
$wheel = Get-ChildItem -LiteralPath dist -Filter *.whl | Sort-Object LastWriteTime -Descending | Select-Object -First 1
uv --cache-dir .uv-cache run --python 3.12 python -m zipfile -l $wheel.FullName
```

Expected: build and twine checks pass; the wheel contains `features.py` and `operations.py` and contains no `driver_tests` package.

- [ ] **Step 4: Re-run architectural boundary checks**

```powershell
rg -n "import redshift_connector|from redshift_connector" django_redshift_backend -g "*.py"
rg -n "django\.db\.backends\.postgresql|django_redshift_backend\._vendor" django_redshift_backend/features.py django_redshift_backend/operations.py django_redshift_backend/_backend.py
git diff redesign/02-backend-foundation -- django_redshift_backend/base.py django_redshift_backend/meta.py django_redshift_backend/distkey.py pyproject.toml .github/workflows/driver-contract.yml
git diff --check
git status --short
```

Expected: only `driver.py` imports `redshift_connector`; redesigned components have no PostgreSQL or vendored imports; forbidden files are unchanged; diff check passes; status is clean.

- [ ] **Step 5: Prepare the stacked PR description in memory**

Use this structure when the finishing workflow selects push/PR:

```markdown
## Scope

Add independent Redshift operations and conservative feature contracts as the
direct child of the Backend foundation PR. The public backend entry point
remains inactive.

## Decisions

- AWS documentation is authoritative for enabled Redshift capabilities.
- Issue #171 is fixed through modern Django date/time operation signatures.
- Pull request #103's complete intent is adopted: ManyToMany uses Django's
  pre-check path and explicit conflict-ignore is unsupported.
- Pull request #104 remains deferred; no custom compiler is introduced.
- Existing `MAX(pk)` identity retrieval is preserved with its concurrency
  limitation documented.

## Compatibility

- No database migration or schema change.
- `base.py`, `meta.py`, `distkey.py`, and existing migration files are unchanged.
- Intentional corrections reject PostgreSQL-only conflict, savepoint, EXPLAIN,
  JSON-operator, index, tablespace, collation, and TRUNCATE assumptions.
- These corrections remain inactive until the final activation layer.

## Verification

- All 15 Django/Python/driver cells passed; exact per-cell test counts are
  recorded in the verification comment generated from the matrix output.
- Root regression: 10 passed, 22 skipped.
- Ruff, package build, twine check, wheel inspection, and boundary checks passed.
- No AWS credentials, PostgreSQL, Redshift, or psql was required.

## Parent

https://github.com/shimizukawa/django-redshift-backend/pull/4

## Tracking

https://github.com/shimizukawa/django-redshift-backend/pull/1
```

Update tracking PR #1's stack checklist, current status, decisions, risks, and
verification, then append one progress comment containing the observed per-cell
test counts. Link the new PR above PR #4 in the existing GitHub stack.

- [ ] **Step 6: Stop for the finishing workflow**

Do not push or create a PR from this task automatically. Invoke
`superpowers:verification-before-completion`, then
`superpowers:finishing-a-development-branch` and follow the user's selected
integration option.
