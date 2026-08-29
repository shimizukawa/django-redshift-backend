import ast
from pathlib import Path

from django.db.backends.base.features import BaseDatabaseFeatures
from django.db.backends.base.introspection import BaseDatabaseIntrospection
from django.db.backends.base.operations import BaseDatabaseOperations

from django_redshift_backend import _backend, base
from django_redshift_backend.base import DistKey as BaseDistKey
from django_redshift_backend.base import SortKey as BaseSortKey
from django_redshift_backend.features import DatabaseFeatures
from django_redshift_backend.meta import DistKey, SortKey
from django_redshift_backend.operations import DatabaseOperations
from django_redshift_backend.schema import DatabaseSchemaEditor

REPOSITORY_ROOT = Path(__file__).parents[1]


def test_existing_engine_entry_point_activates_new_backend():
    assert base.DatabaseWrapper is _backend.DatabaseWrapper
    assert BaseDistKey is DistKey
    assert BaseSortKey is SortKey


def test_package_source_has_no_legacy_driver_or_vendored_backend():
    source_root = REPOSITORY_ROOT / "django_redshift_backend"
    assert not (source_root / "_vendor").exists()
    assert not (source_root / "psycopg2adapter.py").exists()
    for source_file in source_root.rglob("*.py"):
        module = ast.parse(source_file.read_text(encoding="utf-8"))
        imports = [
            alias.name
            for node in ast.walk(module)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        ]
        assert not any(
            name == "psycopg2" or name.startswith("psycopg2.") for name in imports
        )


def test_new_components_are_public_through_existing_entry_point():
    assert _backend.DatabaseWrapper.features_class is DatabaseFeatures
    assert _backend.DatabaseWrapper.ops_class is DatabaseOperations
    assert base.DatabaseWrapper.features_class is DatabaseFeatures
    assert base.DatabaseWrapper.ops_class is DatabaseOperations


def test_new_components_use_only_public_base_classes():
    assert issubclass(DatabaseFeatures, BaseDatabaseFeatures)
    assert issubclass(DatabaseOperations, BaseDatabaseOperations)


def test_new_introspection_is_public_through_existing_entry_point():
    assert issubclass(
        _backend.DatabaseWrapper.introspection_class, BaseDatabaseIntrospection
    )
    assert _backend.DatabaseWrapper.introspection_class.__module__.startswith(
        "django_redshift_backend.introspection"
    )
    assert base.DatabaseWrapper is _backend.DatabaseWrapper


def test_pull_request_104_compiler_copy_is_not_activated():
    assert DatabaseOperations.compiler_module == "django.db.models.sql.compiler"


def test_new_schema_editor_is_public_through_existing_entry_point():
    assert _backend.DatabaseWrapper.SchemaEditorClass.__module__.startswith(
        "django_redshift_backend.schema"
    )
    assert issubclass(base.DatabaseWrapper.SchemaEditorClass, DatabaseSchemaEditor)


def test_schema_guide_is_published_with_public_engine_activation():
    index = (REPOSITORY_ROOT / "doc" / "index.rst").read_text(encoding="utf-8")
    guide = (REPOSITORY_ROOT / "doc" / "schema-migrations.rst").read_text(
        encoding="utf-8"
    )

    assert "schema-migrations" in index
    assert "does not create or apply a Django migration" in guide


def test_live_database_example_workflow_is_deferred():
    workflow = REPOSITORY_ROOT / ".github" / "workflows" / "test-examples-proj1.yml"

    assert not workflow.exists()
