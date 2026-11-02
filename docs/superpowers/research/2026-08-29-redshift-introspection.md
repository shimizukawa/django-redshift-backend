# Redshift Introspection Evidence

## Decision

The internal backend uses the AWS-maintained `redshift_connector` metadata API
instead of copying the legacy PostgreSQL catalog queries. The API supplies
`get_columns()`, `get_primary_keys()`, and `get_imported_keys()`.
Current-schema table/view discovery uses `SVV_TABLES`, including external
tables and comments, with explicit schema isolation.

AWS recommends this driver API because it insulates application integrations
from Redshift system-catalog changes:

- [Use the Amazon Redshift driver metadata API for applications and tools](https://docs.aws.amazon.com/redshift/latest/mgmt/discovering-metadata-driver-api.html)
- [Amazon Redshift Python connector](https://docs.aws.amazon.com/redshift/latest/mgmt/python-redshift-driver.html)

## UNIQUE exception

The public driver API exposes primary and foreign keys, but not unique
constraints. AWS documents `SHOW CONSTRAINTS` as a primary-/foreign-key
operation. The backend consequently uses one parameterized query against
`information_schema.table_constraints` and
`information_schema.key_column_usage` for `constraint_type = 'UNIQUE'`.
It does not query `pg_catalog`.

- [SHOW CONSTRAINTS](https://docs.aws.amazon.com/redshift/latest/dg/r_SHOW_CONSTRAINTS.html)
- [ALTER TABLE examples: locating constraint names](https://docs.aws.amazon.com/redshift/latest/dg/r_ALTER_TABLE_examples_basic.html)

## Semantics and deferred validation

Redshift considers PRIMARY KEY, FOREIGN KEY, and UNIQUE constraints
informational rather than enforced. The backend returns them as schema metadata
for `inspectdb`; it makes no assertion that existing table contents satisfy
them.

- [Table constraints](https://docs.aws.amazon.com/redshift/latest/dg/t_Defining_constraints.html)

AWS-free tests verify catalog SQL, public driver calls, schema scoping, and
Django result shaping. Recorded manual Redshift validation covers ordinary
tables and inspectdb in both examples; its versions and limits are recorded
separately. External-table discovery is covered by catalog contracts, without
a provisioned S3/Glue live fixture.
