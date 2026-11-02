import re
from importlib import import_module
from io import StringIO

import pytest
from django.apps import apps
from django.core.management import call_command
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.graph import MigrationGraph
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.operations.models import AlterField
from django.db.migrations.state import ProjectState

from django_redshift_backend import DistKey, SortKey
from django_redshift_backend._backend import DatabaseWrapper
from django_redshift_backend.distkey import DistKey as LegacyDistKey

from . import schema_helpers

EXPECTED_0001_SEMANTIC_SQL = (
    'CREATE TABLE "testapp_testmodel" ("id" integer NOT NULL PRIMARY KEY identity(1, 1), "ctime" timestamp with time zone NOT NULL, "text" varchar(max) NOT NULL, "uuid" varchar(36) NOT NULL);',
    'CREATE TABLE "testapp_testparentmodel" ("id" integer NOT NULL PRIMARY KEY identity(1, 1), "age" integer NOT NULL);',
    'CREATE TABLE "testapp_testreferencedmodel" ("id" integer NOT NULL PRIMARY KEY identity(1, 1));',
    'CREATE TABLE "testapp_testmodelwithmetakeys" ("id" integer NOT NULL PRIMARY KEY identity(1, 1), "name" varchar(100) NOT NULL, "age" integer NOT NULL, "created_at" timestamp with time zone NOT NULL, "fk_id" integer NOT NULL) SORTKEY("created_at", "id");',
    'CREATE TABLE "testapp_testchildmodel" ("id" integer NOT NULL PRIMARY KEY identity(1, 1), "age" integer NOT NULL, "parent_id" integer NOT NULL);',
    'ALTER TABLE "testapp_testmodelwithmetakeys" ALTER DISTKEY "fk_id";',
    'ALTER TABLE "testapp_testmodelwithmetakeys" ADD CONSTRAINT "testapp_testmodelwit_fk_id_<digest>_fk_testapp_t" FOREIGN KEY ("fk_id") REFERENCES "testapp_testreferencedmodel" ("id");',
    'ALTER TABLE "testapp_testchildmodel" ADD CONSTRAINT "testapp_testchildmod_parent_id_<digest>_fk_testapp_t" FOREIGN KEY ("parent_id") REFERENCES "testapp_testparentmodel" ("id");',
)


def test_existing_migration_corpus_app_is_installed_without_database():
    assert apps.get_app_config("testapp").name == "tests.testapp"


def test_historical_public_paths_remain_stable():
    assert LegacyDistKey is DistKey
    assert DistKey(fields=["customer"], name="customer_distkey").deconstruct()[0] == (
        "django_redshift_backend.DistKey"
    )
    assert SortKey("-created_at").deconstruct()[0] == (
        "django_redshift_backend.SortKey"
    )


def test_existing_migration_module_imports_unchanged():
    module = import_module("tests.testapp.migrations.0001_initial")
    migration = module.Migration("0001_initial", "testapp")
    assert migration.initial is True
    assert migration.operations


def test_loader_builds_disk_graph_without_connection():
    loader = MigrationLoader(None, ignore_no_migrations=True)
    assert ("testapp", "0001_initial") in loader.disk_migrations
    assert loader.graph.leaf_nodes("testapp") == [("testapp", "0001_initial")]


def test_unchanged_rendered_state_has_no_detected_changes():
    loader = MigrationLoader(None, ignore_no_migrations=True)
    state = loader.project_state(("testapp", "0001_initial"))
    changes = MigrationAutodetector(state, state.clone()).changes(MigrationGraph())
    assert changes == {}


def normalize_generated_name(sql):
    return re.sub(r"_[0-9a-f]{8}_(fk|uniq|pk)(?=_)", r"_<digest>_\1", sql)


def collect_migration_sql(migration):
    state = ProjectState()

    def apply(editor):
        nonlocal state
        for operation in migration.operations:
            next_state = state.clone()
            operation.state_forwards(migration.app_label, next_state)
            operation.database_forwards(
                migration.app_label,
                editor,
                state,
                next_state,
            )
            state = next_state

    return schema_helpers.collect_schema_sql(apply), state


def test_historical_migration_replays_without_connection_or_cursor(monkeypatch):
    def unexpected_database_access(*args, **kwargs):
        raise AssertionError(
            "migration compatibility replay must not use a connection or cursor"
        )

    for method in ("connect", "ensure_connection", "cursor", "create_cursor"):
        monkeypatch.setattr(DatabaseWrapper, method, unexpected_database_access)
    monkeypatch.setattr(
        schema_helpers,
        "make_wrapper",
        lambda: DatabaseWrapper(schema_helpers.settings_dict(), "default"),
    )

    module = import_module("tests.testapp.migrations.0001_initial")
    migration = module.Migration("0001_initial", "testapp")
    sql, state = collect_migration_sql(migration)
    semantic_sql = tuple(normalize_generated_name(statement) for statement in sql)

    assert (
        len(
            [
                statement
                for statement in semantic_sql
                if statement.startswith("CREATE TABLE")
            ]
        )
        == 5
    )
    assert any(
        'CREATE TABLE "testapp_testmodelwithmetakeys"' in statement
        for statement in semantic_sql
    )
    assert any('ALTER DISTKEY "fk_id"' in statement for statement in semantic_sql)
    assert any('SORTKEY("created_at", "id")' in statement for statement in semantic_sql)
    assert not any(statement.startswith("CREATE INDEX") for statement in semantic_sql)
    assert state.models["testapp", "testmodelwithmetakeys"]
    assert semantic_sql == EXPECTED_0001_SEMANTIC_SQL


def test_makemigrations_reports_only_the_preexisting_testapp_id_drift(monkeypatch):
    """Keep protected historical files unchanged while recording their one known drift."""
    output = StringIO()
    error = StringIO()

    def unexpected_database_access(*args, **kwargs):
        raise AssertionError("makemigrations compatibility check must not use a cursor")

    monkeypatch.setattr(
        "django.db.backends.dummy.base.DatabaseWrapper.cursor",
        unexpected_database_access,
    )
    with pytest.raises(SystemExit) as exit_info:
        call_command(
            "makemigrations",
            "testapp",
            check=True,
            dry_run=True,
            verbosity=1,
            stdout=output,
            stderr=error,
        )

    assert exit_info.value.code == 1
    lines = output.getvalue().splitlines()
    assert len(lines) == 3
    assert lines[0] == "Migrations for 'testapp':"
    assert lines[1].endswith("0002_alter_testreferencedmodel_id.py")
    assert re.fullmatch(r"    [-~] Alter field id on testreferencedmodel", lines[2])
    assert error.getvalue() == ""

    loader = MigrationLoader(None, ignore_no_migrations=True)
    changes = MigrationAutodetector(
        loader.project_state(),
        ProjectState.from_apps(apps),
    ).changes(
        graph=loader.graph,
        trim_to_apps={"testapp"},
        convert_apps={"testapp"},
    )
    assert list(changes) == ["testapp"]
    migration = changes["testapp"]
    assert len(migration) == 1
    assert migration[0].name == "0002_alter_testreferencedmodel_id"
    assert len(migration[0].operations) == 1
    operation = migration[0].operations[0]
    assert isinstance(operation, AlterField)
    assert operation.model_name == "testreferencedmodel"
    assert operation.name == "id"
