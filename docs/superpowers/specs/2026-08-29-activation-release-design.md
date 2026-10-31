# Activation and 6.0 Release Design

Activate the official Redshift driver behind the existing public ENGINE and publish the 6.0 compatibility and migration guidance.

## Design at a glance

| Area | Policy |
| --- | --- |
| Activation | Re-export the internal wrapper through `base.py`; retain historical key and migration imports. |
| Removal | Remove psycopg2 and the vendored backend; keep focused Redshift components and Django 4.2 adapters. |
| Dependencies | Declare `django>=4.2` and `redshift-connector>=2.1.14,<3`; test supported Django/Python combinations and driver targets. |
| Upgrade behavior | Do not create/apply migrations or modify existing tables automatically; preserve the password-only authentication scope. |

## Read the details

- **Review activation and removal:** [Activation and removal](#activation-and-removal).
- **Check release requirements:** [Metadata and verification](#metadata-and-verification).

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

Use `redshift-connector>=2.1.14,<3`, Django `>=4.2`, and version 6.0.0. Update
classifiers, release notes, and CI. Database-free tests must prove public
activation, legacy removal, migration compatibility, builds, and the supported
Django/driver matrix. The release gate was additionally completed against
Redshift Serverless with both example projects.
