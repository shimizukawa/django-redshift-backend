# Redshift Introspection Implementation Plan

**Goal:** Add database-free, AWS-driver-backed Redshift introspection to the internal backend so `inspectdb` can reconstruct ordinary table metadata.

## Acceptance criteria

| Area | Required outcome |
| --- | --- |
| Discovery | Current-schema tables, external tables, views, and comments are mapped correctly. |
| Columns and constraints | Driver metadata and the narrow UNIQUE query produce Django-shaped results. |
| Version behavior | Only Django 4.2 uses the relation tuple adapter. |
| Compatibility | inspectdb improves without schema changes or public activation in this layer. |
| Verification limits | Offline contracts and live evidence are distinguished; S3/Glue live discovery is not claimed. |

## Verification checklist

Each item states the decision gate before the detailed implementation examples.
The references retain the commands and technical expectations for that item.

### 1. Register the internal layer

**Purpose:** Register introspection only on the internal backend.

**Pass condition:** The internal wrapper constructs the independent introspection class while the public activation boundary is preserved.

**Verification:** Run component registration and activation-boundary contracts. [Implementation and commands](#reference-1-register-the-internal-layer).

### 2. Convert current-schema tables and driver columns

**Purpose:** Convert current-schema table and column metadata.

**Pass condition:** SVV_TABLES discovery retains comments and base/external/view categories; driver columns retain type, identity, and nullability information.

**Verification:** Run table-list, column-description, schema-isolation, and field-type contracts. [Implementation and commands](#reference-2-convert-current-schema-tables-and-driver-columns).

### 3. Reconstruct PK, FK, UNIQUE, and relation tuples

**Purpose:** Reconstruct informational constraints and relation tuples.

**Pass condition:** PK/FK/UNIQUE grouping and schema scoping meet Django contracts; only 4.2 uses the relation adapter.

**Verification:** Run constraint and relation tests on supported Django versions. [Implementation and commands](#reference-3-reconstruct-pk-fk-unique-and-relation-tuples).

### 4. Exercise `inspectdb` without activating the public backend

**Purpose:** Prove inspectdb model generation through the internal backend.

**Pass condition:** Generated models retain identity, FK, UNIQUE, and unmanaged-table semantics without production test switches.

**Verification:** Run management-command and activation-boundary contracts. [Implementation and commands](#reference-4-exercise-inspectdb-without-activating-the-public-backend).

### 5. Record evidence and run the release-quality checks

**Purpose:** Record metadata sources and verify the complete layer.

**Pass condition:** Catalog/API boundaries, limits, and version-qualified live evidence are distinguished from offline contracts; quality gates pass.

**Verification:** Run the full driver suite, lint, formatting, and applicable compatibility checks. [Implementation and commands](#reference-5-record-evidence-and-run-the-release-quality-checks).

## Implementation reference

The following scope, file map, examples, and commands support the checklist.
Intermediate failing examples describe the implementation sequence; they are
not the pass condition for the completed component.

**Architecture:** `DatabaseIntrospection` converts the public `redshift_connector` metadata methods into Django `TableInfo`, `FieldInfo`, relations, and constraints. A narrow `information_schema` query supplies UNIQUE metadata unavailable from the driver. A Django-4.2 subclass adapts only the relation tuple shape; 5.2 and 6.x share the common implementation.

**Tech Stack:** Python 3.10+, Django 4.2/5.2/6.0/6.1, `redshift-connector>=2.1.14,<3`, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-08-29-introspection-design.md`

### Global Constraints

- Keep `django_redshift_backend.base` and the public `ENGINE="django_redshift_backend"` inactive until the activation layer.
- Do not change models, migrations, schema SQL, `meta.py`, `distkey.py`, or package dependency metadata.
- Support Django 4.2, 5.2, 6.0, and 6.1. Isolate only the 4.2 relation tuple compatibility in a removable module.
- Use SVV_TABLES for current-schema discovery and driver metadata for columns, PKs, and imported FKs. Use no direct `pg_catalog` query.
- UNIQUE metadata may use only a parameterized `information_schema` query.
- Offline mocks assert catalog SQL, observable driver calls, and Django-facing results. Version-qualified live evidence is recorded separately; no S3/Glue live fixture is claimed.

---

### File Structure

- Create `django_redshift_backend/introspection.py`: common API conversion, type mapping, constraints, and modern relations.
- Create `django_redshift_backend/introspection_django42.py`: two-element relation compatibility subclass.
- Modify `django_redshift_backend/_backend.py`: version-select introspection class.
- Create `driver_tests/test_introspection.py`: fake metadata cursor, unit contracts, and command output tests.
- Modify `driver_tests/test_activation_boundary.py`: public entry point remains legacy.
- Create `docs/superpowers/research/2026-08-29-redshift-introspection.md`: sources, limitation, and deferred validation.

### Reference 1: Register the internal layer

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

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command; it must pass.


### Reference 2: Convert current-schema tables and driver columns

**Files:** Modify `driver_tests/test_introspection.py` and `django_redshift_backend/introspection.py`.

**Interfaces:** `get_table_list(cursor) -> list[TableInfo]`; `get_table_description(cursor, table_name) -> list[FieldInfo]`. Discovery queries `SVV_TABLES` in the current schema; columns use `cursor.get_columns(schema_pattern=schema, tablename_pattern=table_name)` and exact schema/table filtering.

- [ ] **Step 1: Write failing API-contract tests**

```python
def test_table_list_uses_current_schema_catalog(introspection, cursor):
    cursor.fetchall.return_value = (
        ("orders", "BASE TABLE", "order facts"),
        ("spectrum_orders", "EXTERNAL TABLE", "external order facts"),
        ("order_summary", "VIEW", "summary"),
    )
    assert introspection.get_table_list(cursor) == [
        TableInfo("orders", "t", "order facts"),
        TableInfo("spectrum_orders", "t", "external order facts"),
        TableInfo("order_summary", "v", "summary"),
    ]
    sql = " ".join(cursor.execute.call_args.args[0].split())
    assert "FROM svv_tables" in sql
    assert "table_schema = current_schema()" in sql
    assert "table_type IN ('BASE TABLE', 'EXTERNAL TABLE', 'VIEW')" in sql


def test_column_description_maps_identity_and_nullability(introspection, cursor):
    cursor.get_columns.return_value = (column_row("id", "int4", nullable="NO", identity="YES"),)
    row = introspection.get_table_description(cursor, "orders")[0]
    assert (row.name, row.type_code, row.null_ok, row.is_autofield) == ("id", "int4", False, True)
```

- [ ] **Step 2: Verify RED**

Run: `uv --cache-dir .uv-cache run --project driver_tests pytest driver_tests/test_introspection.py -k "table_list or column_description" -q`

Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement common conversion**

Query `SVV_TABLES` in the current schema; map base/external tables to `t`, views to `v`, and remarks to `TableInfo.comment`. Convert JDBC-shaped column rows to Django `FieldInfo`; use the driver `TYPE_NAME` as `type_code`; map null/default/size/precision/scale/collation/comment; translate `IS_AUTOINCREMENT == "YES"` to `is_autofield`. Map `bool`, integer widths, float widths, character types, numeric, date/time, intervals, and `varbyte`. Do not map unknown names so Django emits its standard guessed `TextField`.

- [ ] **Step 4: Verify GREEN**

Run: `uv --cache-dir .uv-cache run --project driver_tests pytest driver_tests/test_introspection.py -k "table_list or column_description or field_type" -q`

Expected: PASS.

### Reference 3: Reconstruct PK, FK, UNIQUE, and relation tuples

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

Group ordered `get_primary_keys(schema=schema, table=table_name)` and `get_imported_keys(schema=schema, table=table_name)` rows by constraint name. Build Django dictionaries with `columns`, `primary_key`, `unique`, `foreign_key`, `check`, `index`, `definition`, and `options`. Query UNIQUE metadata only from `information_schema.table_constraints` joined to `information_schema.key_column_usage`, with schema/table parameters and ordinal ordering. The 4.2 subclass removes only the third relation item. Select it in `_backend.py` when `django.VERSION[:2] == (4, 2)`.

- [ ] **Step 4: Verify GREEN**

Run: `uv --cache-dir .uv-cache run --project driver_tests pytest driver_tests/test_introspection.py -k "constraints or relations" -q`

Expected: PASS.

### Reference 4: Exercise `inspectdb` without activating the public backend

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

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command; it must pass.

### Reference 5: Record evidence and run the release-quality checks

**Files:** Create `docs/superpowers/research/2026-08-29-redshift-introspection.md`.

- [ ] **Step 1: Record official sources and deferred validation**

List the AWS Metadata API, SHOW CONSTRAINTS, information-schema, and informational-constraint sources. Record the missing UNIQUE API and why the single narrow query is used. Distinguish version-qualified manual live results from AWS-free contracts and the unprovisioned S3/Glue fixture.

- [ ] **Step 2: Verify the complete layer**

```bash
uv --cache-dir .uv-cache run --project driver_tests pytest driver_tests -q
uv run pytest tests/test_inspectdb.py -q
uv run ruff check django_redshift_backend driver_tests tests
uv run ruff format --check django_redshift_backend driver_tests tests
git diff --check
```

Expected: each command exits 0.
