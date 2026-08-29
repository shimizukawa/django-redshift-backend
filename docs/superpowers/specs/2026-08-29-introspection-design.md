# Redshift Introspection Design

## Goal

Implement the Redshift-specific introspection layer used by the internal
`django_redshift_backend._backend` entry point. It must support Django 4.2.30,
5.2, and 6.x without requiring existing users to change models, migration
files, or database schema merely because they upgrade this package.

The layer must make `inspectdb` useful for ordinary Redshift tables without a
live Redshift cluster in the test environment.

## Scope

This stack layer implements these Django introspection contracts:

- table and view discovery;
- column descriptions, including nullability, defaults, comments, identity,
  type, precision, scale, and collation metadata;
- primary-key and foreign-key discovery;
- unique-constraint discovery;
- `get_constraints()`, `get_relations()`, and the primary-key helper methods
  required by `inspectdb`.

It does not activate the internal backend as the public `ENGINE`, remove the
legacy backend, or change package dependency metadata. Those changes remain in
the activation layer.

## Metadata sources

The primary metadata interface is the AWS-maintained `redshift_connector`
cursor API:

- `get_tables()` for table and view discovery;
- `get_columns()` for column descriptions and identity metadata;
- `get_primary_keys()` for primary-key metadata;
- `get_imported_keys()` for foreign-key metadata.

This avoids reintroducing the legacy PostgreSQL-catalog queries. AWS recommends
the driver metadata API as the stable integration boundary as Redshift evolves.

The driver has no public unique-constraint metadata API. `get_constraints()`
therefore makes one deliberately narrow, parameterized query against
`information_schema.table_constraints` joined to
`information_schema.key_column_usage`, restricted to the requested visible
table and `constraint_type = 'UNIQUE'`. AWS documents
`information_schema.table_constraints` as the source of Redshift constraint
names and types. No `pg_catalog` query is added.

## Django version boundary

`introspection.py` contains the shared AWS metadata conversion and the common
field-type mapping. `introspection_django42.py` contains only the Django 4.2
compatibility subclass for `get_relations()`, whose values are two-tuples:
`(referenced_column, referenced_table)`.

Django 5.2 and 6.x use the common implementation, whose relation values are
three-tuples: `(referenced_column, referenced_table, None)`. Redshift exposes
foreign keys as informational metadata; this layer does not infer an
application `on_delete` action. Django's `inspectdb` therefore emits its normal
`models.DO_NOTHING` default on those versions.

`_backend.py` selects the 4.2 class only for `django.VERSION[:2] == (4, 2)`,
following the existing removable `schema_django42.py` pattern. Removing Django
4.2 support later must require deleting this selector and the dedicated module,
not modifying the common implementation.

## Conversion rules

`get_tables()` converts the driver's `TABLE` and `VIEW` result categories into
Django `TableInfo` values of `t` and `v`, retaining the driver remarks as table
comments. Unsupported table categories are excluded from the normal
`inspectdb` set.

`get_columns()` converts its JDBC-shaped rows into Django `FieldInfo` values.
The type code is the driver-supplied Redshift type name, so the backend maps
documented Redshift names (`bool`, integer widths, float widths, character
types, `numeric`, date/time types, intervals, and `varbyte`) directly to Django
field names. Unknown types deliberately raise `KeyError`, preserving Django's
standard `inspectdb` fallback to a commented `TextField` guess.

Identity metadata maps integer, bigint, and smallint columns to `AutoField`,
`BigAutoField`, and `SmallAutoField`. It never consults sequence metadata:
Redshift identity columns do not require Django sequence-reset support, so
`get_sequences()` returns an empty list.

`get_constraints()` merges grouped primary keys, foreign keys, and unique
constraints into Django's documented constraint-dictionary shape. Redshift has
no backend-supported indexes or check constraints, so those are not invented.
Primary, foreign, and unique constraints remain informational metadata; their
presence never asserts that the stored data satisfies them.

## Compatibility and migration policy

The public `django_redshift_backend` entry point remains the legacy backend in
this layer. Existing applications consequently retain their current runtime
behavior until the later activation PR. The new layer changes only explicit
introspection through the internal backend.

No model state, migration operation, migration serialization, or emitted schema
SQL changes in this layer. Existing applications do not receive an automatic
database migration. A user who explicitly runs `inspectdb` may see improved
generated models for identity, keys, and unique fields; choosing whether to
adopt that generated source remains their action.

## Tests

All tests are database-free and use a cursor double with AWS metadata methods.
They cover:

- driver method selection and arguments, table/view filtering, and comments;
- field conversion, null/default/size/precision/scale/collation mapping,
  identity conversion, and unknown-type fallback;
- grouped composite primary, foreign, and unique constraints;
- Django 4.2 versus 5.2/6.x relation tuple contracts;
- `inspectdb` output for a table with identity, FK, and UNIQUE metadata;
- the public-entry-point activation boundary and migration compatibility gates.

The implementation does not treat a PostgreSQL substitute or a mocked result
as proof of live Redshift behavior. A future integration issue will validate
the contracts against an actual Redshift cluster.
