# Redshift Introspection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add database-free, AWS-driver-backed Redshift introspection to the internal backend so `inspectdb` can reconstruct ordinary table metadata.

**Architecture:** `DatabaseIntrospection` converts the public `redshift_connector` metadata methods into Django `TableInfo`, `FieldInfo`, relations, and constraints. A narrow `information_schema` query supplies UNIQUE metadata unavailable from the driver. A Django-4.2 subclass adapts only the relation tuple shape; 5.2 and 6.x share the common implementation.

**Tech Stack:** Python 3.10+, Django 4.2.30/5.2/6.x, `redshift-connector>=2.1.14,<3`, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-08-29-introspection-design.md`

## Global Constraints

- Keep `django_redshift_backend.base` and the public `ENGINE="django_redshift_backend"` inactive until stack layer 06.
- Do not change models, migrations, schema SQL, `meta.py`, `distkey.py`, or package dependency metadata.
- Support Django 4.2.30, 5.2, and 6.x. Isolate only the 4.2 relation tuple compatibility in a removable module.
- Use AWS Metadata API for tables, columns, PKs, and imported FKs. Use no direct `pg_catalog` query.
- UNIQUE metadata may use only a parameterized `information_schema` query.
- No live Redshift validation is available. Mocks must assert observable driver calls and Django-facing results.

---

## File Structure

- Create `django_redshift_backend/introspection.py`: common API conversion, type mapping, constraints, and modern relations.
- Create `django_redshift_backend/introspection_django42.py`: two-element relation compatibility subclass.
- Modify `django_redshift_backend/_backend.py`: version-select introspection class.
- Create `driver_tests/test_introspection.py`: fake metadata cursor, unit contracts, and command output tests.
- Modify `driver_tests/test_activation_boundary.py`: public entry point remains legacy.
- Create `docs/superpowers/research/2026-08-29-redshift-introspection.md`: sources, limitation, and deferred validation.

### Task 1: Register the internal layer

**Files:** Create `driver_tests/test_introspection.py`, `django_redshift_backend/introspection.py`; modify `django_redshift_backend/_backend.py`.

**Interfaces:** Produces `django_redshift_backend.introspection.DatabaseIntrospection`, selected by `DatabaseWrapper.introspection_class`.

- [ ] **Step 1: Write a failing registration test**

```python
from django_redshift_backend import _backend


def test_internal_backend_registers_redshift_introspection():
    assert _backend.DatabaseWrapper.introspection_class.__module__ == (
        "django_redshift_backend.introspection"
    )
```

- [ ] **Step 2: Verify RED**

Run: `uv --cache-dir .uv-cache run --project driver_tests pytest driver_tests/test_introspection.py::test_internal_backend_registers_redshift_introspection -q`

Expected: FAIL because `_backend` selects `BaseDatabaseIntrospection`.

- [ ] **Step 3: Implement the smallest registration**

```python
from django.db.backends.base.introspection import BaseDatabaseIntrospection


class DatabaseIntrospection(BaseDatabaseIntrospection):
    pass
```

Import this class in `_backend.py` and assign it to `introspection_class`.

- [ ] **Step 4: Verify GREEN and commit**

Run the Step 2 command; it must pass. Then:

```bash
git add django_redshift_backend/_backend.py django_redshift_backend/introspection.py driver_tests/test_introspection.py
git commit -m "feat: register Redshift introspection"
```

### Task 2: Convert tables and columns from AWS Metadata API

**Files:** Modify `driver_tests/test_introspection.py` and `django_redshift_backend/introspection.py`.

**Interfaces:** `get_table_list(cursor) -> list[TableInfo]`; `get_table_description(cursor, table_name) -> list[FieldInfo]`. They call `cursor.get_tables(types=["TABLE", "VIEW"])` and `cursor.get_columns(tablename_pattern=table_name)`.

- [ ] **Step 1: Write failing API-contract tests**

```python
def test_table_list_uses_driver_metadata_and_preserves_view_comment(introspection, cursor):
    cursor.get_tables.return_value = (
        ("dev", "public", "orders", "TABLE", "order facts"),
        ("dev", "public", "order_summary", "VIEW", "summary"),
    )
    assert introspection.get_table_list(cursor) == [
        TableInfo("orders", "t", "order facts"),
        TableInfo("order_summary", "v", "summary"),
    ]
    cursor.get_tables.assert_called_once_with(types=["TABLE", "VIEW"])


def test_column_description_maps_identity_and_nullability(introspection, cursor):
    cursor.get_columns.return_value = (column_row("id", "int4", nullable="NO", identity="YES"),)
    row = introspection.get_table_description(cursor, "orders")[0]
    assert (row.name, row.type_code, row.null_ok, row.is_autofield) == ("id", "int4", False, True)
```

- [ ] **Step 2: Verify RED**

Run: `uv --cache-dir .uv-cache run --project driver_tests pytest driver_tests/test_introspection.py -k "table_list or column_description" -q`

Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement common conversion**

Map driver table categories to `t`/`v`, including the remark as `TableInfo.comment`. Convert JDBC-shaped column rows to Django `FieldInfo`; use the driver `TYPE_NAME` as `type_code`; map null/default/size/precision/scale/collation/comment; translate `IS_AUTOINCREMENT == "YES"` to `is_autofield`. Map `bool`, integer widths, float widths, character types, numeric, date/time, intervals, and `varbyte`. Do not map unknown names so Django emits its standard guessed `TextField`.

- [ ] **Step 4: Verify GREEN and commit**

Run: `uv --cache-dir .uv-cache run --project driver_tests pytest driver_tests/test_introspection.py -k "table_list or column_description or field_type" -q`

Expected: PASS. Then commit `django_redshift_backend/introspection.py` and `driver_tests/test_introspection.py` with message `feat: introspect Redshift tables and columns`.

### Task 3: Reconstruct PK, FK, UNIQUE, and relation tuples

**Files:** Create `django_redshift_backend/introspection_django42.py`; modify `_backend.py`, `introspection.py`, and `test_introspection.py`.

**Interfaces:** `get_constraints(cursor, table_name) -> dict`; modern `get_relations()` values are `(referenced_column, referenced_table, None)`; 4.2 values are `(referenced_column, referenced_table)`.

- [ ] **Step 1: Write failing grouped-constraint tests**

```python
def test_constraints_group_primary_foreign_and_unique_metadata(introspection, cursor):
    cursor.get_primary_keys.return_value = (("dev", "public", "orders", "id", 1, "orders_pkey"),)
    cursor.get_imported_keys.return_value = (("dev", "public", "customer", "id", "dev", "public", "orders", "customer_id", 1, 3, 3, "orders_customer_fk", "customer_pkey", 7),)
    cursor.fetchall.return_value = [("orders_code_key", "code", 1)]
    constraints = introspection.get_constraints(cursor, "orders")
    assert constraints["orders_pkey"]["primary_key"] is True
    assert constraints["orders_customer_fk"]["foreign_key"] == ("customer", "id")
    assert constraints["orders_code_key"]["unique"] is True


def test_django42_relations_omit_on_delete_value(django42_introspection, cursor):
    cursor.get_imported_keys.return_value = imported_key_rows()
    assert django42_introspection.get_relations(cursor, "orders") == {"customer_id": ("id", "customer")}
```

- [ ] **Step 2: Verify RED**

Run: `uv --cache-dir .uv-cache run --project driver_tests pytest driver_tests/test_introspection.py -k "constraints or relations" -q`

Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement grouping and the 4.2 adapter**

Group ordered `get_primary_keys(table=table_name)` and `get_imported_keys(table=table_name)` rows by constraint name. Build Django dictionaries with `columns`, `primary_key`, `unique`, `foreign_key`, `check`, `index`, `definition`, and `options`. Query UNIQUE metadata only from `information_schema.table_constraints` joined to `information_schema.key_column_usage`, with `%s` table parameter and ordinal ordering. The 4.2 subclass removes only the third relation item. Select it in `_backend.py` when `django.VERSION[:2] == (4, 2)`.

- [ ] **Step 4: Verify GREEN and commit**

Run: `uv --cache-dir .uv-cache run --project driver_tests pytest driver_tests/test_introspection.py -k "constraints or relations" -q`

Expected: PASS. Commit the four code/test files with message `feat: introspect Redshift keys and constraints`.

### Task 4: Exercise `inspectdb` without activating the public backend

**Files:** Modify `driver_tests/test_introspection.py`, `driver_tests/test_activation_boundary.py`, and `tests/test_inspectdb.py`.

**Interfaces:** The management command consumes a fake driver connection/cursor and produces identity, FK with `models.DO_NOTHING`, single-column `unique=True`, and `managed = False` output.

- [ ] **Step 1: Write failing management-command and boundary tests**

```python
def test_inspectdb_uses_internal_metadata_contract(internal_connection):
    output = run_inspectdb(internal_connection, "orders")
    assert "customer = models.ForeignKey('Customer', models.DO_NOTHING" in output
    assert "code = models.CharField(max_length=32, unique=True)" in output


def test_public_backend_does_not_activate_internal_introspection():
    assert public_wrapper.introspection_class is not internal_wrapper.introspection_class
```

- [ ] **Step 2: Verify RED**

Run: `uv --cache-dir .uv-cache run --project driver_tests pytest driver_tests/test_introspection.py driver_tests/test_activation_boundary.py -k "inspectdb or introspection" -q`

Expected: FAIL with missing fake driver lifecycle or incorrect output.

- [ ] **Step 3: Wire only test support**

Patch the internal connection alias so its context-managed `cursor()` yields the fake metadata cursor. Do not add a production test switch. Keep the existing PostgreSQL-fixture test as legacy coverage and annotate that the new driver-backed contract is database-free.

- [ ] **Step 4: Verify GREEN and commit**

Run the Step 2 command; it must pass. Commit the three tests with message `test: cover Redshift inspectdb contract`.

### Task 5: Record evidence and run the release-quality checks

**Files:** Create `docs/superpowers/research/2026-08-29-redshift-introspection.md`.

- [ ] **Step 1: Record official sources and deferred validation**

List the AWS Metadata API, SHOW CONSTRAINTS, information-schema, and informational-constraint sources. Record the missing UNIQUE API and why the single narrow query is used. State that live Redshift validation remains a future issue.

- [ ] **Step 2: Verify the complete layer**

```bash
uv --cache-dir .uv-cache run --project driver_tests pytest driver_tests -q
uv run pytest tests/test_inspectdb.py -q
uv run ruff check django_redshift_backend driver_tests tests
uv run ruff format --check django_redshift_backend driver_tests tests
git diff --check
```

Expected: each command exits 0.

- [ ] **Step 3: Commit and verify again**

Commit documentation and formatter output with `docs: record Redshift introspection evidence`, then run the exact Step 2 commands again and include their results in the PR description.
