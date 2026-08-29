# Activation and 6.0 Release Design

## Goal

Deliver 6.0.0 by activating the AWS `redshift_connector` backend behind the
existing `ENGINE = "django_redshift_backend"` entry point. Existing models,
migration modules, and `DistKey`/`SortKey` import paths remain valid; upgrading
does not itself require a database schema migration.

## Activation and removal

`base.py` becomes a compatibility re-export of `_backend.DatabaseWrapper`.
Remove the psycopg2 adapter and vendored Django 4.0 tree. Keep `meta.py` and
`distkey.py`. The Django 4.2-only adapters remain selected by version.

## Metadata and verification

Use `redshift-connector>=2.1.14,<3`, Django `>=4.2.30,<6.2`, and version
6.0.0. Update classifiers, release notes, and CI. Database-free tests must
prove public activation, legacy removal, migration compatibility, builds, and
the supported Django/driver matrix. Live Redshift validation remains deferred.
