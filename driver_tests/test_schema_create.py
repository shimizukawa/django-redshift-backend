import inspect

import pytest
import django
from django.db import models
from django.db.utils import NotSupportedError
from django.test.utils import isolate_apps, override_settings

from django_redshift_backend import DistKey, SortKey

from .schema_helpers import collect_schema_sql


@isolate_apps("driver_tests")
def test_create_model_emits_redshift_types_keys_and_informational_fk():
    class Referenced(models.Model):
        id = models.IntegerField(primary_key=True)

        class Meta:
            app_label = "driver_tests"

    class Event(models.Model):
        customer = models.ForeignKey(Referenced, models.CASCADE)
        created_at = models.DateTimeField()
        body = models.TextField()
        payload = models.BinaryField(max_length=16)

        class Meta:
            app_label = "driver_tests"
            indexes = [DistKey(fields=["customer"])]
            ordering = [SortKey("created_at"), SortKey("-id")]

    joined = " ".join(collect_schema_sql(lambda editor: editor.create_model(Event)))
    assert 'CREATE TABLE "driver_tests_event"' in joined
    assert '"id" integer' in joined or '"id" bigint' in joined
    assert "identity(1, 1)" in joined
    assert '"body" varchar(max)' in joined
    assert '"payload" varbyte(16)' in joined
    assert 'DISTKEY("customer_id")' in joined
    assert 'SORTKEY("created_at", "id")' in joined
    assert 'FOREIGN KEY ("customer_id")' in joined
    assert 'REFERENCES "driver_tests_referenced" ("id")' in joined


@override_settings(REDSHIFT_VARCHAR_LENGTH_MULTIPLIER=3)
@isolate_apps("driver_tests")
def test_create_model_applies_varchar_byte_multiplier_once():
    class Label(models.Model):
        value = models.CharField(max_length=100)

        class Meta:
            app_label = "driver_tests"

    sql = collect_schema_sql(lambda editor: editor.create_model(Label))
    assert '"value" varchar(300)' in " ".join(sql)


@pytest.mark.parametrize("fields", [[], ["id", "name"]])
@isolate_apps("driver_tests")
def test_distkey_requires_exactly_one_field(fields):
    class InvalidKey(models.Model):
        name = models.CharField(max_length=20)

        class Meta:
            app_label = "driver_tests"
            indexes = [DistKey(fields=["name"], name="invalid_distkey")]

    InvalidKey._meta.indexes[0].fields = fields

    with pytest.raises(ValueError, match="exactly one field"):
        collect_schema_sql(lambda editor: editor.create_model(InvalidKey))


@isolate_apps("driver_tests")
def test_create_model_rejects_more_than_one_distkey():
    class DuplicateKey(models.Model):
        first = models.IntegerField()
        second = models.IntegerField()

        class Meta:
            app_label = "driver_tests"
            indexes = [
                DistKey(fields=["first"], name="first_distkey"),
                DistKey(fields=["second"], name="second_distkey"),
            ]

    with pytest.raises(ValueError, match="more than one DistKey"):
        collect_schema_sql(lambda editor: editor.create_model(DuplicateKey))


@isolate_apps("driver_tests")
def test_create_model_rejects_ordinary_model_index_before_collecting_sql():
    class Indexed(models.Model):
        value = models.IntegerField()

        class Meta:
            app_label = "driver_tests"
            indexes = [models.Index(fields=["value"], name="ordinary_idx")]

    with pytest.raises(NotSupportedError, match="ordinary_idx"):
        collect_schema_sql(lambda editor: editor.create_model(Indexed))


@isolate_apps("driver_tests")
def test_db_index_is_an_implicit_noop_not_create_index_sql():
    class Indexed(models.Model):
        value = models.IntegerField(db_index=True)

        class Meta:
            app_label = "driver_tests"

    sql = collect_schema_sql(lambda editor: editor.create_model(Indexed))
    assert "CREATE INDEX" not in " ".join(sql)


@pytest.mark.skipif(
    not hasattr(models, "CompositePrimaryKey"),
    reason="Django does not expose CompositePrimaryKey",
)
@isolate_apps("driver_tests")
def test_create_model_emits_composite_primary_key_when_supported():
    class TenantCode(models.Model):
        tenant = models.IntegerField()
        code = models.CharField(max_length=12)
        pk = models.CompositePrimaryKey("tenant", "code")

        class Meta:
            app_label = "driver_tests"

    sql = collect_schema_sql(lambda editor: editor.create_model(TenantCode))
    assert 'PRIMARY KEY ("tenant", "code")' in " ".join(sql)


def _unsupported_field(factory, label):
    @isolate_apps("driver_tests")
    def check():
        class Unsupported(models.Model):
            value = factory()

            class Meta:
                app_label = "driver_tests"

        with pytest.raises(NotSupportedError, match=label):
            collect_schema_sql(lambda editor: editor.create_model(Unsupported))

    return check


@pytest.mark.parametrize(
    ("label", "factory"),
    [
        ("tablespace", lambda: models.CharField(max_length=10, db_tablespace="cold")),
        ("comment", lambda: models.CharField(max_length=10, db_comment="note")),
        ("collation", lambda: models.CharField(max_length=10, db_collation="C")),
    ],
)
def test_create_model_rejects_unsupported_field_ddl(label, factory):
    if {
        "tablespace": "db_tablespace",
        "comment": "db_comment",
        "collation": "db_collation",
    }[label] not in inspect.signature(models.Field.__init__).parameters:
        pytest.skip(f"Django does not expose field {label}")
    _unsupported_field(factory, label)()


@isolate_apps("driver_tests")
def test_create_model_rejects_model_tablespace_before_collecting_sql():
    class Unsupported(models.Model):
        value = models.IntegerField()

        class Meta:
            app_label = "driver_tests"
            db_tablespace = "cold"

    with pytest.raises(NotSupportedError, match="tablespace"):
        collect_schema_sql(lambda editor: editor.create_model(Unsupported))


@isolate_apps("driver_tests")
def test_create_model_rejects_model_comment_before_collecting_sql():
    if django.VERSION < (5, 2):
        pytest.skip("Django does not expose model comments")

    class Unsupported(models.Model):
        value = models.IntegerField()

        class Meta:
            app_label = "driver_tests"
            db_table_comment = "note"

    with pytest.raises(NotSupportedError, match="table comments"):
        collect_schema_sql(lambda editor: editor.create_model(Unsupported))


@pytest.mark.skipif(
    not hasattr(models, "GeneratedField"), reason="Django does not expose GeneratedField"
)
@isolate_apps("driver_tests")
def test_create_model_rejects_generated_field_before_collecting_sql():
    class Unsupported(models.Model):
        value = models.IntegerField()
        derived = models.GeneratedField(
            expression=models.F("value"),
            output_field=models.IntegerField(),
            db_persist=True,
        )

        class Meta:
            app_label = "driver_tests"

    with pytest.raises(NotSupportedError, match="generated column"):
        collect_schema_sql(lambda editor: editor.create_model(Unsupported))
