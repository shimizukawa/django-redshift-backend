import datetime

import pytest
from django.db import models
from django.db.models import DateField, DateTimeField, TimeField, Value
from django.db.models.sql.compiler import SQLCompiler
from django.db.models.sql.query import Query

from django_redshift_backend._backend import DatabaseWrapper


class TemporalEvent(models.Model):
    class Meta:
        app_label = "driver_contract"
        managed = False


def settings_dict():
    return {
        "NAME": "warehouse",
        "HOST": "example.test",
        "PORT": "5439",
        "USER": "alice",
        "PASSWORD": "secret",
        "OPTIONS": {},
        "TIME_ZONE": None,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "AUTOCOMMIT": True,
    }


def compile_subtraction(lhs_value, lhs_field, rhs_value, rhs_field):
    wrapper = DatabaseWrapper(settings_dict(), "temporal-subtraction")
    query = Query(TemporalEvent)
    compiler = SQLCompiler(query, wrapper, "temporal-subtraction")
    expression = (
        Value(lhs_value, output_field=lhs_field)
        - Value(rhs_value, output_field=rhs_field)
    ).resolve_expression(query)
    sql, params = compiler.compile(expression)
    return sql, tuple(params)


@pytest.mark.parametrize(
    ("lhs_value", "rhs_value", "field", "expected_params"),
    [
        (
            datetime.date(2026, 8, 25),
            datetime.date(2026, 8, 24),
            DateField,
            ("2026-08-24", "2026-08-25"),
        ),
        (
            datetime.datetime(2026, 8, 25, 12, 30, 45, 123456),
            datetime.datetime(2026, 8, 24, 10, 15, 30, 654321),
            DateTimeField,
            ("2026-08-24 10:15:30.654321", "2026-08-25 12:30:45.123456"),
        ),
        (
            datetime.time(12, 30, 45, 123456),
            datetime.time(10, 15, 30, 654321),
            TimeField,
            ("10:15:30.654321", "12:30:45.123456"),
        ),
    ],
    ids=["date", "datetime", "time"],
)
def test_same_type_temporal_subtraction_compiles_to_interval(
    lhs_value, rhs_value, field, expected_params
):
    sql, params = compile_subtraction(
        lhs_value,
        field(),
        rhs_value,
        field(),
    )

    assert sql == ("(INTERVAL '1 microsecond' * DATEDIFF(microsecond, (%s), (%s)))")
    assert params == expected_params


@pytest.mark.parametrize(
    ("lhs_value", "lhs_field", "rhs_value", "rhs_field", "expected_params"),
    [
        (
            datetime.date(2026, 8, 25),
            DateField,
            datetime.datetime(2026, 8, 24, 10, 15, 30),
            DateTimeField,
            ("2026-08-25", "2026-08-24 10:15:30"),
        ),
        (
            datetime.datetime(2026, 8, 25, 12, 30, 45),
            DateTimeField,
            datetime.date(2026, 8, 24),
            DateField,
            ("2026-08-25 12:30:45", "2026-08-24"),
        ),
    ],
    ids=["date-minus-datetime", "datetime-minus-date"],
)
def test_mixed_temporal_subtraction_exposes_deferred_compiler_limitation(
    lhs_value, lhs_field, rhs_value, rhs_field, expected_params
):
    """Characterize Django's pass-through SQL; don't claim runtime correctness."""
    sql, params = compile_subtraction(
        lhs_value,
        lhs_field(),
        rhs_value,
        rhs_field(),
    )

    assert sql == "(%s - %s)"
    assert params == expected_params
