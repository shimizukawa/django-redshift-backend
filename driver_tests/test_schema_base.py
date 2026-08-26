from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from django.db import models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.test import override_settings

from django_redshift_backend import _backend
from django_redshift_backend.schema import DatabaseSchemaEditor
from django_redshift_backend.schema_django42 import (
    DatabaseSchemaEditor as DatabaseSchemaEditor42,
)

from .schema_helpers import make_wrapper


SCHEMA_ROOT = Path(__file__).parents[1] / "django_redshift_backend"


class VarcharContractModel(models.Model):
    name = models.CharField(max_length=10)
    body = models.TextField()

    class Meta:
        app_label = "schema_contract"


def test_schema_editor_uses_installed_public_base_class():
    assert issubclass(DatabaseSchemaEditor, BaseDatabaseSchemaEditor)


def test_new_schema_path_has_no_vendored_or_psycopg2_dependency():
    source = "\n".join(
        (SCHEMA_ROOT / name).read_text(encoding="utf-8")
        for name in ("schema.py", "schema_django42.py", "_backend.py")
    )
    assert "_vendor" not in source
    assert "psycopg2" not in source
    assert "django.db.backends.postgresql" not in source


def test_schema_editor_does_not_copy_django_alter_field_commentary():
    source = (SCHEMA_ROOT / "schema.py").read_text(encoding="utf-8")
    assert "BASED FROM" not in source
    assert "four_way_default_alteration" not in source


def test_schema_migration_guide_checks_distribution_style_and_key():
    guide = (Path(__file__).parents[1] / "doc" / "schema-migrations.rst").read_text(
        encoding="utf-8"
    )
    assert "SVV_TABLE_INFO" in guide
    assert "diststyle" in guide
    assert "pg_table_def" in guide
    assert "distkey" in guide


def test_django42_selection_is_one_deletion_oriented_branch():
    assert _backend.schema_editor_class_for((4, 2, 30)) is DatabaseSchemaEditor42
    assert _backend.schema_editor_class_for((5, 2, 8)) is DatabaseSchemaEditor
    assert _backend.schema_editor_class_for((6, 0, 0)) is DatabaseSchemaEditor
    assert _backend.schema_editor_class_for((6, 1, 0)) is DatabaseSchemaEditor


def test_internal_wrapper_registers_selected_schema_editor():
    wrapper = make_wrapper()
    assert wrapper.SchemaEditorClass is _backend.schema_editor_class_for(
        __import__("django").VERSION
    )


def test_redshift_data_types_and_identity_suffixes_are_explicit():
    assert _backend.DatabaseWrapper.data_types["AutoField"] == "integer"
    assert _backend.DatabaseWrapper.data_types["BigAutoField"] == "bigint"
    assert _backend.DatabaseWrapper.data_types["SmallAutoField"] == "smallint"
    assert _backend.DatabaseWrapper.data_types["TextField"] == "varchar(max)"
    assert _backend.DatabaseWrapper.data_types["UUIDField"] == "varchar(36)"
    assert _backend.DatabaseWrapper.data_types["JSONField"] == "varchar"
    assert (
        _backend.DatabaseWrapper.data_types["BinaryField"] == "varbyte(%(max_length)s)"
    )
    assert _backend.DatabaseWrapper.data_types_suffix == {
        "AutoField": "identity(1, 1)",
        "BigAutoField": "identity(1, 1)",
        "SmallAutoField": "identity(1, 1)",
    }


def test_quote_value_supports_database_free_sql_collection():
    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    assert editor.quote_value(None) == "NULL"
    assert editor.quote_value(True) == "TRUE"
    assert editor.quote_value(False) == "FALSE"
    assert editor.quote_value(Decimal("1.25")) == "1.25"
    assert editor.quote_value("O'Reilly%") == "'O''Reilly%%'"
    assert editor.quote_value(b"\x80\x00") == "to_varbyte('8000', 'hex')"
    assert editor.quote_value(UUID("12345678-1234-5678-1234-567812345678")) == (
        "'12345678-1234-5678-1234-567812345678'"
    )
    assert editor.quote_value(date(2026, 8, 25)) == "'2026-08-25'"
    assert editor.quote_value(time(12, 30, 45)) == "'12:30:45'"
    assert editor.quote_value(datetime(2026, 8, 25, 12, 30, 45)) == (
        "'2026-08-25T12:30:45'"
    )


@override_settings(REDSHIFT_VARCHAR_LENGTH_MULTIPLIER=3)
def test_column_sql_multiplies_only_bounded_varchar_lengths():
    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    name_sql, _ = editor.column_sql(
        VarcharContractModel, VarcharContractModel._meta.get_field("name")
    )
    body_sql, _ = editor.column_sql(
        VarcharContractModel, VarcharContractModel._meta.get_field("body")
    )

    assert name_sql.startswith("varchar(30)")
    assert body_sql.startswith("varchar(max)")
    assert (
        editor._multiply_bounded_varchar_lengths("integer NOT NULL")
        == "integer NOT NULL"
    )
    assert editor._multiply_bounded_varchar_lengths(None) is None
