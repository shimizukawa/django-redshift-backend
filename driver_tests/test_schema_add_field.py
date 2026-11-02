import inspect

import pytest
from django.db import models
from django.db.models import Value
from django.db.utils import NotSupportedError
from django.test.utils import isolate_apps

from .schema_helpers import collect_schema_sql, make_wrapper


def _field_for(model, field):
    field.set_attributes_from_name("name")
    field.model = model
    return field


@isolate_apps("driver_tests")
def test_add_nullable_field_is_direct():
    class Pony(models.Model):
        weight = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    field = _field_for(Pony, models.CharField(max_length=10, null=True))
    assert collect_schema_sql(lambda editor: editor.add_field(Pony, field)) == [
        'ALTER TABLE "driver_tests_pony" ADD COLUMN "name" varchar(10) NULL;'
    ]


@isolate_apps("driver_tests")
def test_add_nonnull_field_keeps_literal_python_default_as_database_default():
    class Pony(models.Model):
        weight = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    field = _field_for(Pony, models.CharField(max_length=10, default="unknown"))
    assert collect_schema_sql(lambda editor: editor.add_field(Pony, field)) == [
        'ALTER TABLE "driver_tests_pony" ADD COLUMN "name" varchar(10) DEFAULT \'unknown\' NOT NULL;'
    ]


@isolate_apps("driver_tests")
def test_add_nonnull_field_without_default_fails_without_sql_state():
    class Pony(models.Model):
        weight = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    editor.deferred_sql = []
    field = _field_for(Pony, models.CharField(max_length=10))
    with pytest.raises(NotSupportedError, match="non-null.*default"):
        editor.add_field(Pony, field)
    assert editor.collected_sql == []
    assert editor.deferred_sql == []


@isolate_apps("driver_tests")
def test_add_callable_default_fails_without_freezing_value_or_sql_state():
    class Pony(models.Model):
        weight = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    editor.deferred_sql = []
    field = _field_for(Pony, models.IntegerField(default=lambda: 7))
    with pytest.raises(NotSupportedError, match="callable default"):
        editor.add_field(Pony, field)
    assert editor.collected_sql == []
    assert editor.deferred_sql == []


@isolate_apps("driver_tests")
def test_add_nullable_callable_default_fails_without_freezing_value_or_sql_state():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    editor.deferred_sql = []
    field = _field_for(Pony, models.IntegerField(null=True, default=lambda: 7))
    with pytest.raises(NotSupportedError, match="callable default"):
        editor.add_field(Pony, field)
    assert editor.collected_sql == []
    assert editor.deferred_sql == []


@isolate_apps("driver_tests")
def test_add_unique_field_separates_column_and_constraint():
    class Pony(models.Model):
        weight = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    field = _field_for(Pony, models.CharField(max_length=10, default="", unique=True))
    sql = collect_schema_sql(lambda editor: editor.add_field(Pony, field))
    assert " UNIQUE" not in sql[0]
    assert "ADD CONSTRAINT" in sql[1]
    assert "UNIQUE" in sql[1]


@isolate_apps("driver_tests")
def test_add_primary_key_field_strips_unsupported_inline_primary_key():
    class Pony(models.Model):
        weight = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    field = _field_for(Pony, models.IntegerField(default=0, primary_key=True))
    sql = collect_schema_sql(lambda editor: editor.add_field(Pony, field))
    assert "PRIMARY KEY" not in sql[0]
    assert any("PRIMARY KEY" in statement for statement in sql[1:])
    assert not any(" UNIQUE" in statement for statement in sql[1:])


@isolate_apps("driver_tests")
def test_add_relation_separates_column_and_informational_fk():
    class Owner(models.Model):
        class Meta:
            app_label = "driver_tests"

    class Pony(models.Model):
        weight = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    field = _field_for(Pony, models.ForeignKey(Owner, models.CASCADE, null=True))
    sql = collect_schema_sql(lambda editor: editor.add_field(Pony, field))
    assert "REFERENCES" not in sql[0]
    assert " UNIQUE" not in sql[0]
    assert 'FOREIGN KEY ("name_id")' in sql[1]
    assert 'REFERENCES "driver_tests_owner" ("id")' in sql[1]


@isolate_apps("driver_tests")
def test_add_identity_column_fails_without_sql_state():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    editor.deferred_sql = []
    field = _field_for(Pony, models.AutoField())
    with pytest.raises(NotSupportedError, match="IDENTITY"):
        editor.add_field(Pony, field)
    assert editor.collected_sql == []
    assert editor.deferred_sql == []


@pytest.mark.skipif(
    "db_default" not in inspect.signature(models.Field.__init__).parameters,
    reason="Django does not expose db_default",
)
@isolate_apps("driver_tests")
def test_add_nonnull_field_keeps_literal_db_default():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    field = _field_for(Pony, models.IntegerField(db_default=Value(4)))
    assert collect_schema_sql(lambda editor: editor.add_field(Pony, field)) == [
        'ALTER TABLE "driver_tests_pony" ADD COLUMN "name" integer DEFAULT 4 NOT NULL;'
    ]


@pytest.mark.skipif(
    "db_default" not in inspect.signature(models.Field.__init__).parameters,
    reason="Django does not expose db_default",
)
@isolate_apps("driver_tests")
def test_add_nonnull_field_with_null_literal_db_default_fails_without_sql_state():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    editor.deferred_sql = []
    field = _field_for(Pony, models.IntegerField(db_default=Value(None)))
    with pytest.raises(NotSupportedError, match="non-null.*default"):
        editor.add_field(Pony, field)
    assert editor.collected_sql == []
    assert editor.deferred_sql == []


@pytest.mark.skipif(
    "db_default" not in inspect.signature(models.Field.__init__).parameters,
    reason="Django does not expose db_default",
)
@isolate_apps("driver_tests")
def test_add_expression_db_default_fails_without_sql_state():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    editor.deferred_sql = []
    field = _field_for(Pony, models.IntegerField(db_default=models.F("weight")))
    with pytest.raises(NotSupportedError, match="expression db_default"):
        editor.add_field(Pony, field)
    assert editor.collected_sql == []
    assert editor.deferred_sql == []


@pytest.mark.skipif(
    not hasattr(models, "GeneratedField"),
    reason="Django does not expose GeneratedField",
)
@isolate_apps("driver_tests")
def test_add_generated_field_fails_without_sql_state():
    class Pony(models.Model):
        weight = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    editor.deferred_sql = []
    field = _field_for(
        Pony,
        models.GeneratedField(
            expression=models.F("weight"),
            output_field=models.IntegerField(),
            db_persist=True,
        ),
    )
    with pytest.raises(NotSupportedError, match="generated column"):
        editor.add_field(Pony, field)
    assert editor.collected_sql == []
    assert editor.deferred_sql == []


@pytest.mark.parametrize(
    ("label", "factory"),
    [
        ("tablespace", lambda: models.CharField(max_length=10, db_tablespace="cold")),
        ("comment", lambda: models.CharField(max_length=10, db_comment="note")),
        ("collation", lambda: models.CharField(max_length=10, db_collation="C")),
    ],
)
@isolate_apps("driver_tests")
def test_add_unsupported_field_ddl_fails_without_sql_state(label, factory):
    parameter = {
        "tablespace": "db_tablespace",
        "comment": "db_comment",
        "collation": "db_collation",
    }[label]
    if parameter not in inspect.signature(models.Field.__init__).parameters:
        pytest.skip(f"Django does not expose {parameter}")

    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    editor.deferred_sql = []
    field = _field_for(Pony, factory())
    with pytest.raises(NotSupportedError, match=label):
        editor.add_field(Pony, field)
    assert editor.collected_sql == []
    assert editor.deferred_sql == []
