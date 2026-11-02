import datetime

from django.db import models
from django.db.models import DateTimeField, Value
from django.db.models.functions import Trunc
from django.db.models.sql.compiler import SQLCompiler
from django.db.models.sql.query import Query

from django_redshift_backend._backend import DatabaseWrapper


class Event(models.Model):
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


def test_trunc_expression_compiles_through_django_orm():
    wrapper = DatabaseWrapper(settings_dict(), "issue-171")
    query = Query(Event)
    compiler = SQLCompiler(query, wrapper, "issue-171")
    value = datetime.datetime(2026, 8, 25, 12, 30)
    expression = Trunc(
        Value(value, output_field=DateTimeField()),
        "day",
        output_field=DateTimeField(),
    ).resolve_expression(query)

    sql, params = compiler.compile(expression)

    assert sql == "DATE_TRUNC(%s, %s)"
    assert tuple(params) == ("day", str(value))
