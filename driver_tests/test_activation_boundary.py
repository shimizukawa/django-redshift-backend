from django.db.backends.base.features import BaseDatabaseFeatures
from django.db.backends.base.operations import BaseDatabaseOperations

from django_redshift_backend import _backend, base
from django_redshift_backend.features import DatabaseFeatures
from django_redshift_backend.operations import DatabaseOperations
from django_redshift_backend.schema import DatabaseSchemaEditor


def test_existing_engine_entry_point_is_not_activated():
    assert base.DatabaseWrapper is not _backend.DatabaseWrapper


def test_new_components_are_internal_only():
    assert _backend.DatabaseWrapper.features_class is DatabaseFeatures
    assert _backend.DatabaseWrapper.ops_class is DatabaseOperations
    assert base.DatabaseWrapper.features_class is not DatabaseFeatures
    assert base.DatabaseWrapper.ops_class is not DatabaseOperations


def test_new_components_use_only_public_base_classes():
    assert issubclass(DatabaseFeatures, BaseDatabaseFeatures)
    assert issubclass(DatabaseOperations, BaseDatabaseOperations)


def test_pull_request_104_compiler_copy_is_not_activated():
    assert DatabaseOperations.compiler_module == "django.db.models.sql.compiler"


def test_new_schema_editor_is_internal_only():
    assert _backend.DatabaseWrapper.SchemaEditorClass.__module__.startswith(
        "django_redshift_backend.schema"
    )
    assert base.DatabaseWrapper.SchemaEditorClass is not DatabaseSchemaEditor
