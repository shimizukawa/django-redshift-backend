import inspect

import pytest
from django.db import models
from django.db.utils import NotSupportedError
from django.test.utils import isolate_apps

from django_redshift_backend import DistKey

from .schema_helpers import collect_schema_sql, make_wrapper


def _check_constraint(*, name, condition):
    keyword = (
        "condition"
        if "condition" in inspect.signature(models.CheckConstraint).parameters
        else "check"
    )
    return models.CheckConstraint(name=name, **{keyword: condition})


def _unsupported_constraints():
    constraints = [
        _check_constraint(name="value_check", condition=models.Q(value__gte=0)),
        models.UniqueConstraint(
            models.functions.Lower("value"), name="lower_value_uniq"
        ),
        models.UniqueConstraint(
            fields=["value"],
            condition=models.Q(value__isnull=False),
            name="conditional_value_uniq",
        ),
        models.UniqueConstraint(
            fields=["value"], include=["other"], name="included_value_uniq"
        ),
        models.UniqueConstraint(
            fields=["value"], opclasses=["text_ops"], name="opclass_value_uniq"
        ),
    ]
    if "nulls_distinct" in inspect.signature(models.UniqueConstraint).parameters:
        constraints.append(
            models.UniqueConstraint(
                fields=["value"], nulls_distinct=False, name="nulls_value_uniq"
            )
        )
    return constraints


@isolate_apps("driver_tests")
def test_add_distkey_uses_physical_column_with_alter_distkey():
    class Event(models.Model):
        customer = models.ForeignKey("Customer", models.CASCADE)

        class Meta:
            app_label = "driver_tests"

    index = DistKey(fields=["customer"], name="event_customer_distkey")
    sql = collect_schema_sql(lambda editor: editor.add_index(Event, index))
    assert sql == ['ALTER TABLE "driver_tests_event" ALTER DISTKEY "customer_id";']


@isolate_apps("driver_tests")
def test_remove_distkey_returns_table_to_auto_distribution():
    class Event(models.Model):
        customer = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    index = DistKey(fields=["customer"], name="event_customer_distkey")
    sql = collect_schema_sql(lambda editor: editor.remove_index(Event, index))
    assert sql == ['ALTER TABLE "driver_tests_event" ALTER DISTSTYLE AUTO;']


@pytest.mark.parametrize("method", ["add_index", "remove_index"])
@pytest.mark.parametrize("fields", [[], ["first", "second"]])
@isolate_apps("driver_tests")
def test_distkey_operations_require_exactly_one_field(method, fields):
    class Event(models.Model):
        first = models.IntegerField()
        second = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    index = DistKey(fields=["first"], name="event_distkey")
    index.fields = fields
    with pytest.raises(ValueError, match="exactly one field"):
        collect_schema_sql(lambda editor: getattr(editor, method)(Event, index))


@pytest.mark.parametrize("method", ["add_index", "remove_index"])
@isolate_apps("driver_tests")
def test_explicit_ordinary_index_operation_fails_with_name(method):
    class Event(models.Model):
        value = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    index = models.Index(fields=["value"], name="event_value_idx")
    with pytest.raises(NotSupportedError, match="event_value_idx"):
        collect_schema_sql(lambda editor: getattr(editor, method)(Event, index))


@isolate_apps("driver_tests")
def test_simple_unique_constraint_is_informational_ddl():
    class Event(models.Model):
        code = models.CharField(max_length=20)

        class Meta:
            app_label = "driver_tests"

    constraint = models.UniqueConstraint(fields=["code"], name="event_code_uniq")
    sql = collect_schema_sql(lambda editor: editor.add_constraint(Event, constraint))
    assert sql == [
        'ALTER TABLE "driver_tests_event" ADD CONSTRAINT "event_code_uniq" UNIQUE ("code");'
    ]


@pytest.mark.skipif(
    not hasattr(models, "Deferrable"),
    reason="Django does not expose deferrable constraints",
)
@pytest.mark.parametrize("method", ["add_constraint", "remove_constraint"])
@isolate_apps("driver_tests")
def test_deferrable_unique_constraint_fails_before_sql(method):
    class Event(models.Model):
        value = models.CharField(max_length=20)

        class Meta:
            app_label = "driver_tests"

    constraint = models.UniqueConstraint(
        fields=["value"],
        name="deferred_value_uniq",
        deferrable=models.Deferrable.DEFERRED,
    )
    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    editor.deferred_sql = []
    with pytest.raises(NotSupportedError, match=constraint.name):
        getattr(editor, method)(Event, constraint)
    assert editor.collected_sql == []
    assert editor.deferred_sql == []


@pytest.mark.skipif(
    not hasattr(models, "Deferrable"),
    reason="Django does not expose deferrable constraints",
)
@isolate_apps("driver_tests")
def test_create_model_rejects_deferrable_unique_constraint_before_sql():
    class Event(models.Model):
        value = models.CharField(max_length=20)

        class Meta:
            app_label = "driver_tests"
            constraints = [
                models.UniqueConstraint(
                    fields=["value"],
                    name="deferred_value_uniq",
                    deferrable=models.Deferrable.DEFERRED,
                )
            ]

    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    editor.deferred_sql = []
    with pytest.raises(NotSupportedError, match="deferred_value_uniq"):
        editor.create_model(Event)
    assert editor.collected_sql == []
    assert editor.deferred_sql == []


@pytest.mark.parametrize(
    "constraint",
    _unsupported_constraints(),
)
@pytest.mark.parametrize("method", ["add_constraint", "remove_constraint"])
@isolate_apps("driver_tests")
def test_unsupported_constraints_fail_explicitly_before_sql(method, constraint):
    class Event(models.Model):
        value = models.CharField(max_length=20)
        other = models.CharField(max_length=20)

        class Meta:
            app_label = "driver_tests"

    with pytest.raises(NotSupportedError, match=constraint.name):
        collect_schema_sql(lambda editor: getattr(editor, method)(Event, constraint))


@isolate_apps("driver_tests")
def test_create_model_rejects_unsupported_constraint_before_collecting_sql():
    class Event(models.Model):
        value = models.IntegerField()

        class Meta:
            app_label = "driver_tests"
            constraints = [
                _check_constraint(name="value_check", condition=models.Q(value__gte=0))
            ]

    editor = make_wrapper().schema_editor(collect_sql=True, atomic=False)
    editor.deferred_sql = []
    with pytest.raises(NotSupportedError, match="value_check"):
        editor.create_model(Event)
    assert editor.collected_sql == []
    assert editor.deferred_sql == []


@isolate_apps("driver_tests")
def test_create_model_validates_constraints_before_ordinary_indexes():
    class Event(models.Model):
        value = models.IntegerField()

        class Meta:
            app_label = "driver_tests"
            constraints = [
                _check_constraint(name="value_check", condition=models.Q(value__gte=0))
            ]
            indexes = [models.Index(fields=["value"], name="value_idx")]

    with pytest.raises(NotSupportedError, match="value_check"):
        collect_schema_sql(lambda editor: editor.create_model(Event))


@isolate_apps("driver_tests")
def test_alter_index_together_rejects_changes_and_keeps_equal_sets_as_noop():
    class Event(models.Model):
        value = models.IntegerField()

        class Meta:
            app_label = "driver_tests"

    assert (
        collect_schema_sql(
            lambda editor: editor.alter_index_together(
                Event, {("value",)}, {("value",)}
            )
        )
        == []
    )
    with pytest.raises(NotSupportedError, match="driver_tests.Event"):
        collect_schema_sql(
            lambda editor: editor.alter_index_together(Event, set(), {("value",)})
        )
