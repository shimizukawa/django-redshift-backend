==========
References
==========

.. contents::
   :local:

Redshift SQL differences
========================

Type mapping:

* 'integer identity(1, 1)' for AutoField
* 'bigint identity(1, 1)' for BigAutoField
* 'timestamp with time zone' for DateTimeField
* 'varchar(max)' for TextField
* 'varchar(32)' for UUIDField
* Possibility to multiply VARCHAR length to support utf-8 string, using
  `REDSHIFT_VARCHAR_LENGTH_MULTIPLIER` setting.

Stop using:

* RETURNING (single insert and bulk insert)
* SELECT FOR UPDATE
* SELECT DISTINCT ON
* SET CONSTRAINTS
* INDEX
* DEFERRABLE INITIALLY DEFERRED
* CONSTRAINT
* CHECK
* DROP DEFAULT

To support migration:

* To add column to existent table on Redshift, column must be nullable
* To support modify column, add new column -> data migration -> drop old column -> rename

Please note that the migration support for redshift is not perfect yet.


Note and Limitation
--------------------

Amazon Redshift doesn't support RETURNING, so ``last_insert_id`` method retrieve MAX(pk) after insertion as a workaround.

refs:

* https://stackoverflow.com/q/19428860
* https://stackoverflow.com/q/25638539

In some case, MAX(pk) workaround does not work correctly.
Bulk insertion makes non-contiguous IDs like: 1, 4, 7, 10, ...
and single insertion after such bulk insertion generates strange id value like 2 (smallest non-used id).


Django Settings
===============

settings.DATABASES
--------------------

:ENGINE:
   Set 'django_redshift_backend'.

:NAME:
   Set '<your database name>'.

:USER:
   Set '<your database username>'.

:PASSWORD:
   Set '<your database password>'.

:HOST:
   Set '<your database hostname>'.

:PORT:
   Set your Redshift server port number. Maybe '5439'.


settings.REDSHIFT_VARCHAR_LENGTH_MULTIPLIER
-------------------------------------------

Possibility to multiply VARCHAR length to support utf-8 string. Default is 1.

See also: https://docs.aws.amazon.com/redshift/latest/dg/r_Character_types.html#r_Character_types-storage-and-ranges


Django Models
=============

Using sortkey
-------------

There is built-in support for this option for Django >= 1.9. To use `sortkey`, define an `ordering` on the model
meta with the custom sortkey type `django_redshift_backend.SortKey` as follow::

  class MyModel(models.Model):
      ...

      class Meta:
          ordering = [SortKey('col2')]

`SortKey` in `ordering` are also valid as ordering in Django.

N.B.: there is no validation of this option, instead we let Redshift validate it for you. Be sure to refer to the `documentation <https://docs.aws.amazon.com/redshift/latest/dg/r_CREATE_TABLE_examples.html>`_.

Using distkey
-------------

There is built-in support for this option for Django >= 1.11. To use `distkey`, define an index on the model
meta with the custom index type `django_redshift_backend.DistKey` with `fields` naming a single field::

  class MyModel(models.Model):
      ...

      class Meta:
          indexes = [DistKey(fields=['customer_id'])]

Redshift doesn't have conventional indexes, and we don't generate SQL for them. We merely use
`indexes` as a convenient place in the Meta to identify the `distkey`.

You will likely encounter the following complication:

Inlining Index Migrations
~~~~~~~~~~~~~~~~~~~~~~~~~
Django's `makemigrations` generates a migration file that first applies a `CreateModel` operation without the
`indexes` option, and then adds the index in a separate `AddIndex` operation.

However Redshift requires that the `distkey` be specified at table creation. As a result, you may need to
manually edit your migration files to move the index creation into the initial `CreateModel`.

That is, to go from::

    operations = [
        ...
        migrations.CreateModel(
            name='FactTable',
            fields=[
                ('distkeycol', models.CharField()),
                ('measure1', models.IntegerField()),
                ('measure2', models.IntegerField())
                ...
            ]
        ),
       ...
       migrations.AddIndex(
            model_name='facttable',
            index=django_redshift_backend.DistKey(fields=['distkeycol'], name='...'),
        ),
    ]

To::

    operations = [
        ...
        migrations.CreateModel(
            name='FactTable',
            fields=[
                ('distkeycol', models.CharField()),
                ('measure1', models.IntegerField()),
                ('measure2', models.IntegerField())
                ...
            ],
            options={
                'indexes': [django_redshift_backend.DistKey(fields=['distkeycol'], name='...')],
            },
        ),
       ...
    ]


Inlining ForeignKey Migrations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
It is common to distribute fact tables on a foreign key column referencing the primary key of a dimension table.

In this case you may also encounter the following added complication:

Django's `makemigrations` generates a migration file that first applies a `CreateModel` operation without the
`ForeignKey` column, and then adds the `ForeignKey` column in a separate `AddField` operation.  It does this to
avoid attempts to create foreign key constraints against tables that haven't been created yet.

However Redshift requires that the `distkey` be specified at table creation. As a result, you may need to
manually edit your migration files to move the ForeignKey column into the initial `CreateModel`, while also
ensuring that the referenced table appears *before* the referencing table in the file.

That is, to go from::

    operations = [
        ...
        migrations.CreateModel(
            name='FactTable',
            fields=[
                ('measure1', models.IntegerField()),
                ('measure2', models.IntegerField())
                ...
            ]
        ),
       ...
       migrations.CreateModel(
            name='Dimension1Table',
            fields=[
                ...
            ]
        ),
        ...
        migrations.AddField(
            model_name='facttable',
            name='dim1',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='myapp.Dimension1Table'),
        ),
        ...
    ]

To::

    operations = [
       migrations.CreateModel(
            name='Dimension1Table',
            fields=[
                ...
            ]
        ),
        ...
        migrations.CreateModel(
            name='FactTable',
            fields=[
                ('measure1', models.IntegerField()),
                ('measure2', models.IntegerField()),
                ('dim1', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='myapp.Dimension1Table'))
                ...
            ]
        ),
        ...
    ]

