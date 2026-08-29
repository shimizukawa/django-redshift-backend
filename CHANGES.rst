CHANGES
=======

6.0.0 (unreleased)
------------------

General:

* Switch the public backend to AWS's ``redshift-connector`` driver.
* Drop psycopg2 and the vendored Django 4.0 backend implementation.

Incompatible Changes:

* Python 3.9 and Django versions before 4.2.30 are unsupported.
* psycopg2-only connection options and direct imports of vendored backend
  modules are unsupported.

Features:

* Support Django 4.2.30, 5.2, 6.0, and 6.1.

Bug Fixes:

5.0.0 (2024/11/28)
------------------

General:

Features:

* #144 Add Python-3.13 support.
* #141 Drop Django-3.2, 4.0 support.
* #142 Drop Python-3.8 support.

Bug Fixes:

4.2.0 (2024/10/30)
------------------

General:

* #149 Added a clear message on ImportError when the psycopg2
  package cannot be found.
  Please refer to the following site for more information: 
  https://django-redshift-backend.readthedocs.io/en/master/basic.html#installation

Features:

* #143 Add Django-5.0 support.
* #152 Add Django-5.1 support.

Bug Fixes:

* fixes #12, #154 : disabling native json support. Redshift does not natively support JSON.

4.1.1 (2024/08/20)
------------------

Bug Fixes:

* #147 Broken django.db.backends.signals.connection_created signal

4.1.0 (2024/07/27)
------------------

Features:

* #140 Add Python-3.11 and 3.12 support. Thanks to Grzegorz Śliwiński.

4.0.0 (2024/07/23)
------------------

General:

Incompatible Changes:

Features:

* #116 Add Django-4.2 support.
  Special thanks to Grzegorz Śliwiński, who made a significant contribution to the development of Django-4.1 support in PR #111. Using this as a springboard, we have now made it possible to support Django-4.2.
* #83 Drop Django-2.2 support.
* #83 Drop Python-3.6 support.
* #127 Drop Python-3.7 support.
* #83 Drop Django-2.2 support.
* #134 Support adding COLUMN with UNIQUE; adding column without UNIQUE then add UNIQUE CONSTRAINT.
* #135 Support adding BinaryField.
* #132 Use 36 length for UUIDFields to support including hyphens. Thanks to kylie.

Bug Fixes:

* #134 inspectdb should suppress output 'id = AutoField(primary_key=True)'
* #134 fix for decreasing size of column with default by create-copy-drop-rename strategy.
* #118 fix constraint creation using the wrong table and column name. Thanks to BlueMagma.

3.0.0 (2022/02/27)
------------------

General:

* #87 Drop py2 wheel tag from release package file.
* Add `CODE_OF_CONDUCT.rst` The linked text which has been referred to from CONTRIBUTING.rst is now included.

Incompatible Changes:

* #97 To specify SORTKEY for Redshift, you must use `django_redshift_backend.SortKey` for
  `Model.Meta.ordering` instead of bearer string.

  **IMPORTANT**:
  With this change, existing migration files that specify ordering are not affected.
  If you want to apply SortKey to your migration files, please comment out the ordering option once and run
  makemigrations, then comment in the ordering option and run makemigrations again.

* #97 `django_redshift_backend.distkey.DistKey` is moved to `django_redshift_backend.DistKey`.
  However old name is still supported for a compatibility.

* #97 Now django-redshift-backend doesn't support `can_rollback_ddl`.
  Originally, Redshift did not support column name/type(size) changes within a transaction.
  Please refer https://github.com/jazzband/django-redshift-backend/issues/96

* #97 changed the behavior of implicit not null column addition.
  previously, adding a not null column was implicitly changed to allow null.
  now adding not null without default raises a programmingerror exception.

Features:

* #82 Add Python-3.10 support.
* #98 Add Django-4.0 support.
* #82 Drop Django-3.0 support.
* #98 Drop Django-3.1 support.
* #90,#13,#8: Support `manage.py inspectdb`, also support working with the django-sql-explorer package.
  Thanks to Matt Fisher.
* #63 Support changing a field from NOT NULL to NULL on migrate / sqlmigrate.
* #97 Support VARCHAR size changing for UNIQUE, PRIMARY KEY, FOREIGN KEY.
* #97 Support backward migration for DROP NOT NULL column wituout DEFAULT.
  One limitation is that the DEFAULT value is set to match the type. This is because the only way for
  Redshift to add NOT NULL without default is to recreate the table.

Bug Fixes:

* #92,#93: since django-3.0 sqlmigrate (and migrate) does not work.
* #37: fix Django `contenttype` migration that cause `ProgrammingError: cannot drop sortkey column
  "name"` exception.
* #64: fix Django `auth` migration that cause `NotSupportedError: column "content_type__app_label"
  specified as distkey/sortkey is not in the table "auth_permission"` exception.

2.1.0 (2021/09/23)
------------------

General:

* #76 fix test failing on django-dev with py36,py37
* #77 Mondernize setup.cfg and pyproject.toml

Features:

* #81 Add Django 3.2 support.

Bug Fixes:

* #80 uuid field doesn't work correctly with django 2.x and 3.x. Thanks to xavier-lr.

2.0.1 (2021/03/07)
------------------

Bug Fixes:

* #74: set supports_aggregate_filter_clause=False (since Django-2.0) to disable FILTER WHERE syntax. Thanks to Michael Wheeler.
* #73: fix broken feature flags since Django-3.0: can_return_columns_from_insert and can_return_rows_from_bulk_insert. Thanks to Agustín Magaña.

2.0.0 (2021/01/04)
-------------------

General:

* #70,#71,#72 Moved CI to GitHub Actions: https://github.com/jazzband/django-redshift-backend/actions
  Thkanks to Bruno Alla.

Features:

* Drop Python 2.7 and 3.5 support.
* Drop Django 1.11, 2.0 and 2.1 support.
* #68 Add Python 3.8 and 3.9 support.
* #68 Add Django 3.0 and 3.1 support.

Bug Fixes:

* #69 Let users choose between psycopg2 binary or source. Thkanks to Bruno Alla.
* #65,#66 Deprecation warning due to invalid escape sequences. Thanks to Karthikeyan Singaravelan.

Documentation:

* #67 Just a typo cleanup from refs.rst. Thanks to Kostja P.

1.1.0 (2019/08/02)
------------------

* #60 Change dependencies to support Python 3.7 Thanks to Asher Foa.

1.0.0 (2019/01/29)
------------------

General:

* The first release from Jazzband_ organization.
* Using `Development Status :: 5 - Production/Stable`.
* All GitHub/Travis/other URLs in this product has been migrated to `/jazzband/`.

New Features:

* #56 Support Django 2.1.
* #57 Support Python 3.7

Bug Fixes:

* #53,#54: UUIDField django model field will cause clash. Thanks to Corentin Dupret.

Development:

* Adopt setuptools_scm for versioning from git tag.

.. _Jazzband: https://jazzband.co/

0.9.1 (2018-09-29)
------------------

* fix trove classifier 'License' from BSD to Apache.
* Documentation: Add `Contribution Guideline`_

.. _Contribution Guideline: https://django-redshift-backend.readthedocs.io/en/master/dev.html#contribution-guideline

0.9 (2018-07-24)
----------------

* #35: Drop support for Django 1.8, 1.9 and 1.10.
* #40: Support Django 2.0.
* #42: Support DISTKEY. Thanks to Benjy Weinberger.
* Documentation: https://django-redshift-backend.rtfd.io/
* Change LICENSE from 'BSD License' to 'Apache Software License'

0.8.1 (2018-06-19)
------------------

* #38: Fix 0.8 doesn't compatible with Python 2. Thanks to Benjy Weinberger.

0.8 (2018-06-01)
----------------

Incompatible Changes:

* #23,#10: Redshift support time zones in time stamps for migration

  **IMPORTANT**:
  With this change, the newly created DateTimeField column will be timestamp
  with timezone (TIMESTAMPTZ) by migration. Therefore, the existing
  DateTimeField and the new DateTimeField will have different data types as a
  redshift schema column type.
  There are no migration feature by django-redshift-backend.
  see also: https://github.com/jazzband/django-redshift-backend/pull/23

New Features:

* #20,#26: Support for sortkey. Thanks to Maxime Vdb and Kosei Kitahara.
* #24: Add UUIDField support. Thanks to Sindri Guðmundsson.
* #14: More compat with redshift: not use SELECT DISTINCT ON.

Bug Fixes:

* #15,#21: More compat with redshift: not use CHECK. Thanks to Vasil Vangelovski.
* #18: Fix error on migration with django-1.9 or later that raises AttributeError
  of 'sql_create_table_unique'.
* #27: annotate() does not work on Django-1.9 and later. Thanks to Takayuki Hirai.


Documentation:

* Add documentation: https://django-redshift-backend.rtfd.io/


0.7 (2017-06-08)
----------------

* Drop Python-3.4
* Drop Django-1.7
* Support Python-3.6
* Support Django-1.11

0.6 (2016-12-15)
----------------

* Fix crush problem when using bulk insert.

0.5 (2016-10-05)
----------------

* Support Django-1.10
* #9: Add support for BigAutoField. Thanks to Maxime Vdb.
* Fix crush problem on sqlmigrate when field modified.

0.4 (2016-05-17)
----------------

* Support Python-3.4 and 3.5
* #7: Restore support django-1.7. Version 0.3 doesn't support django-1.7.
* #4: More compat with redshift: not use SET CONSTRAINTS. Thanks to Maxime Vdb.
* #6: More compat with redshift: not use sequence reset query. Thanks to Maxime Vdb.
* #5: Add REDSHIFT_VARCHAR_LENGTH_MULTIPLIER settings. Thanks to Maxime Vdb.
* Support column type changing on migration.

0.3 (2016-05-14)
----------------

* #3: more compat with Redshift (AutoField, DateTimeField, Index). Thanks to Maxime Vdb.
* More compat with redshift: add TextField
* More compat with redshift: not use DEFERRABLE, CONSTRAINT, DROP DEFAULT
* More compat with redshift: support modify column


0.2.1 (2016-02-01)
------------------

* "SET TIME_ZONE" warning is changed as debug log for 'django.db.backend' logger.

0.2 (2016-01-08)
----------------

* Disable "SET TIME_ZONE" SQL execution even if settings.TIME_ZONE is specified.

0.1.2 (2015-06-5)
-----------------

* Support Django-1.8

0.1.1 (2015-03-27)
------------------
* Disable "SELECT FOR UPDATE" SQL execution.

0.1 (2015-03-24)
----------------
* Support Django-1.7
* Support "INSERT INTO" SQL execution without "RETURNING" clause.

