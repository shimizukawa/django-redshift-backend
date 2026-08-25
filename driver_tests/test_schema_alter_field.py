import inspect

import pytest
from django.db import models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.backends.ddl_references import Columns, Statement
from django.db.migrations.operations.fields import RenameField
from django.db.migrations.state import ModelState, ProjectState
from django.db.models import Value
from django.db.utils import NotSupportedError, ProgrammingError
from django.test.utils import isolate_apps

from django_redshift_backend import DistKey, SortKey

from .schema_helpers import collect_schema_sql, make_wrapper


def _field_for(model, field, name="name"):
    field.set_attributes_from_name(name)
    field.model = model
    return field


def alter_sql(model, old_field, new_field, name="name"):
    old_field = _field_for(model, old_field, name)
    new_field = _field_for(model, new_field, name)
    return collect_schema_sql(
        lambda editor: editor.alter_field(model, old_field, new_field)
    )


def assert_preflight_failure(model, old_field, new_field, match):
    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    editor.deferred_sql = []
    old_field = _field_for(model, old_field)
    new_field = _field_for(model, new_field)
    with pytest.raises(NotSupportedError, match=match):
        editor.alter_field(model, old_field, new_field)
    assert editor.collected_sql == []
    assert editor.deferred_sql == []


def model_from_state(state, name):
    return state.apps.get_model("driver_tests", name)


def state_with_model(name, fields, options=None):
    state = ProjectState()
    state.add_model(ModelState("driver_tests", name, fields, options=options))
    return state


@isolate_apps("driver_tests")
def test_varchar_enlargement_uses_one_direct_type_statement():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    assert alter_sql(
        Pony,
        models.CharField(max_length=10, null=True),
        models.CharField(max_length=20, null=True),
    ) == ['ALTER TABLE "driver_tests_pony" ALTER COLUMN "name" TYPE varchar(20);']


@isolate_apps("driver_tests")
def test_varchar_reduction_recreates_nullable_column_in_four_statements():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    assert alter_sql(
        Pony,
        models.CharField(max_length=20, null=True),
        models.CharField(max_length=10, null=True),
    ) == [
        'ALTER TABLE "driver_tests_pony" ADD COLUMN "name_tmp" varchar(10) NULL;',
        'UPDATE "driver_tests_pony" SET "name_tmp" = "name" WHERE "name" IS NOT NULL;',
        'ALTER TABLE "driver_tests_pony" DROP COLUMN "name" CASCADE;',
        'ALTER TABLE "driver_tests_pony" RENAME COLUMN "name_tmp" TO "name";',
    ]


@isolate_apps("driver_tests")
def test_varchar_reduction_keeps_literal_default_on_nonnull_replacement():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    sql = alter_sql(
        Pony,
        models.CharField(max_length=20),
        models.CharField(max_length=10, default=""),
    )
    assert sql[:4] == [
        'ALTER TABLE "driver_tests_pony" ADD COLUMN "name_tmp" varchar(10) DEFAULT \'\' NOT NULL;',
        'UPDATE "driver_tests_pony" SET "name_tmp" = "name" WHERE "name" IS NOT NULL;',
        'ALTER TABLE "driver_tests_pony" DROP COLUMN "name" CASCADE;',
        'ALTER TABLE "driver_tests_pony" RENAME COLUMN "name_tmp" TO "name";',
    ]


@isolate_apps("driver_tests")
def test_nonnull_recreation_without_default_fails_before_sql():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    assert_preflight_failure(
        Pony,
        models.CharField(max_length=20),
        models.CharField(max_length=10),
        "non-null.*default",
    )


@isolate_apps("driver_tests")
def test_character_to_binary_recreation_uses_varbyte_cast():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    sql = alter_sql(
        Pony,
        models.CharField(max_length=16, null=True),
        models.BinaryField(max_length=16, null=True),
    )
    assert 'SET "name_tmp" = "name"::varbyte' in sql[1]


@isolate_apps("driver_tests")
def test_binary_to_character_recreation_uses_varchar_cast():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    sql = alter_sql(
        Pony,
        models.BinaryField(max_length=16, null=True),
        models.CharField(max_length=16, null=True),
    )
    assert 'SET "name_tmp" = "name"::varchar' in sql[1]


@isolate_apps("driver_tests")
def test_python_default_only_change_emits_no_sql():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    assert alter_sql(
        Pony,
        models.CharField(max_length=10, null=True, default="old"),
        models.CharField(max_length=10, null=True, default="new"),
    ) == []


@pytest.mark.skipif(
    "db_default" not in inspect.signature(models.Field.__init__).parameters,
    reason="Django does not expose db_default",
)
@isolate_apps("driver_tests")
def test_nullable_literal_db_default_change_recreates_with_new_default():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    sql = alter_sql(
        Pony,
        models.IntegerField(null=True, db_default=Value(1)),
        models.IntegerField(null=True, db_default=Value(2)),
    )
    assert sql[0] == 'ALTER TABLE "driver_tests_pony" ADD COLUMN "name_tmp" integer DEFAULT 2 NULL;'


@pytest.mark.skipif(
    "db_default" not in inspect.signature(models.Field.__init__).parameters,
    reason="Django does not expose db_default",
)
@isolate_apps("driver_tests")
def test_nullable_literal_db_default_drop_recreates_without_default():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    sql = alter_sql(
        Pony,
        models.IntegerField(null=True, db_default=Value(1)),
        models.IntegerField(null=True),
    )
    assert sql[0] == 'ALTER TABLE "driver_tests_pony" ADD COLUMN "name_tmp" integer NULL;'


@pytest.mark.skipif(
    "db_default" not in inspect.signature(models.Field.__init__).parameters,
    reason="Django does not expose db_default",
)
@isolate_apps("driver_tests")
def test_nonnull_literal_db_default_drop_fails_before_sql():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    assert_preflight_failure(
        Pony,
        models.IntegerField(db_default=Value(1)),
        models.IntegerField(),
        "non-null.*default",
    )


@isolate_apps("driver_tests")
def test_nullable_to_nonnull_recreates_with_literal_default():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    sql = alter_sql(
        Pony,
        models.IntegerField(null=True),
        models.IntegerField(default=4),
    )
    assert sql[0] == 'ALTER TABLE "driver_tests_pony" ADD COLUMN "name_tmp" integer DEFAULT 4 NOT NULL;'


@isolate_apps("driver_tests")
def test_nullable_to_nonnull_without_default_fails_before_sql():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    assert_preflight_failure(
        Pony,
        models.IntegerField(null=True),
        models.IntegerField(),
        "non-null.*default",
    )


@isolate_apps("driver_tests")
def test_nonnull_to_nullable_recreates_without_default():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    sql = alter_sql(
        Pony,
        models.IntegerField(default=4),
        models.IntegerField(null=True),
    )
    assert sql[0] == 'ALTER TABLE "driver_tests_pony" ADD COLUMN "name_tmp" integer NULL;'


@isolate_apps("driver_tests")
def test_rename_uses_base_redshift_sql_and_updates_deferred_references():
    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    old_field = _field_for(Pony, models.CharField(max_length=10, null=True), "old")
    new_field = _field_for(
        Pony, models.CharField(max_length=10, null=True), "new"
    )
    deferred = Statement(
        "ALTER TABLE %(table)s ADD CONSTRAINT fake UNIQUE (%(columns)s)",
        table=editor.quote_name(Pony._meta.db_table),
        columns=Columns(Pony._meta.db_table, ["old"], editor.quote_name),
    )
    editor.deferred_sql = [deferred]
    editor.alter_field(Pony, old_field, new_field)
    assert editor.collected_sql == [
        'ALTER TABLE "driver_tests_pony" RENAME COLUMN "old" TO "new";'
    ]
    assert '"new"' in str(deferred)
    assert '"old"' not in str(deferred)


@isolate_apps("driver_tests")
@pytest.mark.parametrize(
    "meta_option",
    [
        {"ordering": [SortKey("name")]},
        {"indexes": [DistKey(fields=["name"], name="pony_name_distkey")]},
    ],
)
def test_recreation_of_table_key_field_fails_before_sql(meta_option):
    class Pony(models.Model):
        name = models.CharField(max_length=20, null=True)

        class Meta:
            app_label = "driver_tests"

    for option, value in meta_option.items():
        setattr(Pony._meta, option, value)

    assert_preflight_failure(
        Pony,
        models.CharField(max_length=20, null=True),
        models.CharField(max_length=10, null=True),
        "table-key",
    )


@isolate_apps("driver_tests")
def test_recreation_rebuilds_state_known_unique_constraints():
    class Pony(models.Model):
        name = models.CharField(max_length=20, null=True)
        herd = models.IntegerField()

        class Meta:
            app_label = "driver_tests"
            unique_together = [("name", "herd")]
            constraints = [
                models.UniqueConstraint(fields=["name"], name="pony_name_unique")
            ]

    sql = alter_sql(
        Pony,
        models.CharField(max_length=20, null=True),
        models.CharField(max_length=10, null=True, unique=True),
    )
    assert " UNIQUE" not in sql[0]
    assert any('UNIQUE ("name")' in statement for statement in sql[4:])
    assert any('UNIQUE ("name", "herd")' in statement for statement in sql[4:])
    assert any('CONSTRAINT "pony_name_unique" UNIQUE ("name")' in statement for statement in sql[4:])


@isolate_apps("driver_tests")
def test_recreation_rebuilds_outgoing_and_incoming_informational_foreign_keys():
    class Parent(models.Model):
        id = models.IntegerField(primary_key=True)

        class Meta:
            app_label = "driver_tests"

    class Child(models.Model):
        parent = models.ForeignKey(Parent, models.CASCADE)

        class Meta:
            app_label = "driver_tests"

    parent_sql = alter_sql(
        Parent,
        models.IntegerField(primary_key=True),
        models.CharField(max_length=20, primary_key=True, default=""),
        name="id",
    )
    assert any('PRIMARY KEY ("id")' in statement for statement in parent_sql[4:])
    assert any('FOREIGN KEY ("parent_id")' in statement for statement in parent_sql[4:])

    class Pony(models.Model):
        class Meta:
            app_label = "driver_tests"

    outgoing_sql = alter_sql(
        Pony,
        models.IntegerField(null=True),
        models.ForeignKey(Parent, models.CASCADE, null=True),
    )
    assert any('FOREIGN KEY ("name_id")' in statement for statement in outgoing_sql)


def test_migration_state_renamed_sortkey_recreation_fails_before_sql(monkeypatch):
    from_state = state_with_model(
        "Pony",
        [
            ("id", models.AutoField(primary_key=True)),
            ("label", models.CharField(max_length=20, null=True)),
        ],
        {"ordering": [SortKey("label")]},
    )
    to_state = state_with_model(
        "Pony",
        [
            ("id", models.AutoField(primary_key=True)),
            ("renamed", models.CharField(max_length=10, null=True)),
        ],
        {"ordering": [SortKey("renamed")]},
    )
    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    editor.deferred_sql = []
    monkeypatch.setattr(RenameField, "allow_migrate_model", lambda *args: True)

    with pytest.raises(NotSupportedError, match="table-key"):
        RenameField("Pony", "label", "renamed").database_forwards(
            "driver_tests",
            editor,
            from_state,
            to_state,
        )

    assert editor.collected_sql == []
    assert editor.deferred_sql == []


@pytest.mark.parametrize(
    ("declaration", "db_column"),
    [
        ("customer", None),
        ("customer_id", None),
        ("warehouse_customer", "warehouse_customer"),
    ],
)
def test_migration_state_distkey_alias_recreation_fails_before_sql(
    declaration,
    db_column,
):
    def state_for(field_name, db_constraint, field_db_column):
        state = ProjectState()
        state.add_model(
            ModelState(
                "driver_tests",
                "Customer",
                [("id", models.AutoField(primary_key=True))],
            )
        )
        state.add_model(
            ModelState(
                "driver_tests",
                "Pony",
                [
                    ("id", models.AutoField(primary_key=True)),
                    (
                        field_name,
                            models.ForeignKey(
                                "driver_tests.Customer",
                                models.CASCADE,
                                null=True,
                                db_constraint=db_constraint,
                                db_column=field_db_column,
                            ),
                    ),
                ],
                options={
                    "indexes": [
                        DistKey(
                            fields=[declaration],
                            name="pony_customer_distkey",
                        )
                    ]
                },
            )
        )
        return state

    from_state = state_for("customer", True, db_column)
    to_state = state_for("account", False, None)
    from_model = model_from_state(from_state, "Pony")
    to_model = model_from_state(to_state, "Pony")
    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    editor.deferred_sql = []

    with pytest.raises(NotSupportedError, match="table-key"):
        editor.alter_field(
            from_model,
            from_model._meta.get_field("customer"),
            to_model._meta.get_field("account"),
        )

    assert editor.collected_sql == []
    assert editor.deferred_sql == []


def test_migration_state_unknown_table_key_fails_before_sql():
    state = state_with_model(
        "Pony",
        [
            ("id", models.AutoField(primary_key=True)),
            ("label", models.CharField(max_length=20, null=True)),
        ],
        {"ordering": [SortKey("missing")]},
    )
    model = model_from_state(state, "Pony")
    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    editor.deferred_sql = []
    old_field = model._meta.get_field("label")
    new_field = models.CharField(max_length=10, null=True)
    new_field.set_attributes_from_name("label")
    new_field.model = model

    with pytest.raises(NotSupportedError, match="resolve Redshift table-key"):
        editor.alter_field(model, old_field, new_field)

    assert editor.collected_sql == []
    assert editor.deferred_sql == []


def test_constrained_outgoing_fk_varchar_enlargement_recreates_column():
    def state_for(field):
        state = ProjectState()
        state.add_model(
            ModelState(
                "driver_tests",
                "Customer",
                [
                    ("id", models.AutoField(primary_key=True)),
                    ("code", models.CharField(max_length=10, unique=True)),
                ],
            )
        )
        state.add_model(
            ModelState(
                "driver_tests",
                "Pony",
                [
                    ("id", models.AutoField(primary_key=True)),
                    ("customer", field),
                ],
            )
        )
        return state

    from_model = model_from_state(
        state_for(models.CharField(max_length=10, null=True)), "Pony"
    )
    to_model = model_from_state(
        state_for(
            models.ForeignKey(
                "driver_tests.Customer",
                models.CASCADE,
                to_field="code",
                null=True,
            )
        ),
        "Pony",
    )
    sql = collect_schema_sql(
        lambda editor: editor.alter_field(
            from_model,
            from_model._meta.get_field("customer"),
            to_model._meta.get_field("customer"),
        )
    )

    assert any("ADD COLUMN" in statement for statement in sql)
    assert not any("ALTER COLUMN" in statement and " TYPE " in statement for statement in sql)
    assert any('FOREIGN KEY ("customer_id")' in statement for statement in sql[4:])


def test_incoming_fk_varchar_enlargement_recreates_referenced_column():
    def state_for(max_length):
        state = ProjectState()
        state.add_model(
            ModelState(
                "driver_tests",
                "Customer",
                [
                    ("id", models.AutoField(primary_key=True)),
                    (
                        "code",
                        models.CharField(
                            max_length=max_length,
                            null=True,
                            unique=True,
                        ),
                    ),
                ],
            )
        )
        state.add_model(
            ModelState(
                "driver_tests",
                "Pony",
                [
                    ("id", models.AutoField(primary_key=True)),
                    (
                        "customer",
                        models.ForeignKey(
                            "driver_tests.Customer",
                            models.CASCADE,
                            to_field="code",
                            null=True,
                        ),
                    ),
                ],
            )
        )
        return state

    from_model = model_from_state(state_for(10), "Customer")
    to_model = model_from_state(state_for(20), "Customer")
    sql = collect_schema_sql(
        lambda editor: editor.alter_field(
            from_model,
            from_model._meta.get_field("code"),
            to_model._meta.get_field("code"),
        )
    )

    assert sql[0].startswith('ALTER TABLE "driver_tests_customer" ADD COLUMN')
    assert not any("ALTER COLUMN" in statement and " TYPE " in statement for statement in sql)
    assert any('FOREIGN KEY ("customer_id")' in statement for statement in sql[4:])


@isolate_apps("driver_tests")
def test_remove_sortkey_column_retries_only_known_redshift_error(monkeypatch):
    class Pony(models.Model):
        name = models.CharField(max_length=10)

        class Meta:
            app_label = "driver_tests"

    calls = []
    editor = make_wrapper().schema_editor(atomic=False)

    def remove_once(self, model, field):
        calls.append((model, field))
        if len(calls) == 1:
            raise ProgrammingError("cannot drop sortkey column")

    monkeypatch.setattr(BaseDatabaseSchemaEditor, "remove_field", remove_once)
    monkeypatch.setattr(editor, "execute", lambda sql, params=(): calls.append(str(sql)))
    editor.remove_field(Pony, Pony._meta.get_field("name"))
    assert any("ALTER SORTKEY NONE" in value for value in calls if isinstance(value, str))
    assert len([value for value in calls if isinstance(value, tuple)]) == 2


@isolate_apps("driver_tests")
def test_remove_sortkey_column_reconnects_when_database_error_state_is_set(monkeypatch):
    class Pony(models.Model):
        name = models.CharField(max_length=10)

        class Meta:
            app_label = "driver_tests"

    calls = []
    editor = make_wrapper().schema_editor(atomic=False)
    editor.connection.errors_occurred = True

    def remove_once(self, model, field):
        calls.append((model, field))
        if len(calls) == 1:
            raise ProgrammingError("cannot drop sortkey column")

    monkeypatch.setattr(BaseDatabaseSchemaEditor, "remove_field", remove_once)
    monkeypatch.setattr(editor.connection, "close", lambda: calls.append("close"))
    monkeypatch.setattr(editor.connection, "connect", lambda: calls.append("connect"))
    monkeypatch.setattr(editor, "execute", lambda sql, params=(): calls.append(str(sql)))
    editor.remove_field(Pony, Pony._meta.get_field("name"))
    assert calls.count("close") == 1
    assert calls.count("connect") == 1


@isolate_apps("driver_tests")
def test_remove_field_reraises_unrelated_programming_error(monkeypatch):
    class Pony(models.Model):
        name = models.CharField(max_length=10)

        class Meta:
            app_label = "driver_tests"

    editor = make_wrapper().schema_editor(atomic=False)

    def fail(self, model, field):
        raise ProgrammingError("some unrelated database problem")

    monkeypatch.setattr(BaseDatabaseSchemaEditor, "remove_field", fail)
    with pytest.raises(ProgrammingError, match="unrelated"):
        editor.remove_field(Pony, Pony._meta.get_field("name"))
