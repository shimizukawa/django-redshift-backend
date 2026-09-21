from unittest.mock import patch

import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.utils import NotSupportedError
from django.db import models
from django.db.models import F, IntegerField, Q, Value
from django.db.models.lookups import Exact
from django.db.models.sql.compiler import SQLCompiler
from django.db.models.sql.query import Query

from django_redshift_backend import driver
from django_redshift_backend._backend import DatabaseWrapper
from django_redshift_backend.client import DatabaseClient
from django_redshift_backend.creation import DatabaseCreation
from django_redshift_backend.features import DatabaseFeatures
from django_redshift_backend.operations import DatabaseOperations


class PatternModel(models.Model):
    left = models.CharField(max_length=100)
    right = models.CharField(max_length=100)

    class Meta:
        app_label = "driver_contract"
        managed = False


class FakeCursor:
    def __init__(self, error=None, rows=()):
        self.error = error
        self.executed = []
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, sql, params=None):
        if self.error:
            raise self.error
        self.executed.append((sql, params))

    def fetchmany(self, size=None):
        return tuple(self.rows[:size])


class FakeConnection:
    def __init__(self, cursor, timezone="UTC"):
        self._cursor = cursor
        self.autocommit = False
        self.parameter_statuses = [(b"TimeZone", timezone.encode())]
        self.commits = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1


def settings_dict(**overrides):
    values = {
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
    values.update(overrides)
    return values


def test_wrapper_uses_public_base_backend():
    assert issubclass(DatabaseWrapper, BaseDatabaseWrapper)
    assert DatabaseWrapper.vendor == "redshift"
    assert DatabaseWrapper.Database is driver.Database
    assert DatabaseWrapper.client_class is DatabaseClient


def test_wrapper_registers_foundation_components():
    wrapper = DatabaseWrapper(settings_dict(), "default")
    assert wrapper.client.__class__.__name__ == "DatabaseClient"
    assert isinstance(wrapper.creation, DatabaseCreation)
    assert isinstance(wrapper.features, DatabaseFeatures)
    assert isinstance(wrapper.ops, DatabaseOperations)


def test_wrapper_compiles_exact_lookup_through_django_orm():
    wrapper = DatabaseWrapper(settings_dict(), "lookup-test")
    compiler = SQLCompiler(None, wrapper, "lookup-test")
    lookup = Exact(
        Value(1, output_field=IntegerField()),
        Value(1, output_field=IntegerField()),
    )

    sql, params = compiler.compile(lookup)

    assert sql in {"%s = %s", "%s = (%s)"}
    assert tuple(params) == (1, 1)


@pytest.mark.parametrize(
    ("lookup", "expected"),
    [
        ("contains", "LIKE '%' ||"),
        ("icontains", "LIKE '%' || UPPER("),
        ("startswith", "LIKE"),
        ("istartswith", "LIKE UPPER("),
        ("endswith", "LIKE '%' ||"),
        ("iendswith", "LIKE '%' || UPPER("),
    ],
)
def test_wrapper_compiles_expression_pattern_lookups(lookup, expected):
    wrapper = DatabaseWrapper(settings_dict(), "pattern-lookup-test")
    query = Query(PatternModel)
    query.add_q(Q(**{f"left__{lookup}": F("right")}))
    compiler = SQLCompiler(query, wrapper, "pattern-lookup-test")

    sql, params = compiler.as_sql()

    assert expected in sql
    assert "CHR(92)" in sql
    assert "E'" not in sql
    assert params == ()


def test_connection_params_use_password_contract():
    wrapper = DatabaseWrapper(settings_dict(), "default")
    assert wrapper.get_connection_params() == {
        "database": "warehouse",
        "host": "example.test",
        "port": 5439,
        "user": "alice",
        "password": "secret",
    }


def test_new_connection_delegates_to_driver(monkeypatch):
    wrapper = DatabaseWrapper(settings_dict(), "default")
    expected = object()
    calls = []
    monkeypatch.setattr(
        driver, "connect", lambda **kwargs: calls.append(kwargs) or expected
    )
    params = {"user": "alice", "password": "secret"}
    assert wrapper.get_new_connection(params) is expected
    assert calls == [params]


def test_create_cursor_rejects_named_cursor():
    wrapper = DatabaseWrapper(settings_dict(), "default")
    wrapper.connection = FakeConnection(FakeCursor())
    assert wrapper.create_cursor() is wrapper.connection._cursor
    with pytest.raises(NotSupportedError, match="named cursor"):
        wrapper.create_cursor(name="server-side")


@pytest.mark.parametrize("factory", ["make_cursor", "make_debug_cursor"])
def test_cursor_fetchmany_returns_django_list_sentinel(factory):
    wrapper = DatabaseWrapper(settings_dict(), "default")
    cursor = getattr(wrapper, factory)(FakeCursor(rows=[]))

    assert cursor.fetchmany(100) == []


def test_autocommit_uses_public_driver_attribute():
    wrapper = DatabaseWrapper(settings_dict(), "default")
    wrapper.connection = FakeConnection(FakeCursor())
    wrapper._set_autocommit(True)
    assert wrapper.connection.autocommit is True


def test_init_connection_state_leaves_matching_timezone_unchanged():
    wrapper = DatabaseWrapper(settings_dict(), "foundation-test")
    wrapper.connection = FakeConnection(FakeCursor())
    wrapper.__dict__["timezone_name"] = "UTC"
    with patch.object(BaseDatabaseWrapper, "init_connection_state") as initialize:
        wrapper.init_connection_state()
    initialize.assert_called_once_with()
    assert wrapper.connection._cursor.executed == []


@pytest.mark.parametrize(
    ("autocommit", "expected_commits"),
    [(False, 1), (True, 0)],
)
def test_init_connection_state_sets_mismatched_timezone(autocommit, expected_commits):
    wrapper = DatabaseWrapper(settings_dict(), "foundation-test")
    wrapper.connection = FakeConnection(FakeCursor(), timezone="UTC")
    wrapper.__dict__["timezone_name"] = "Asia/Tokyo"
    wrapper.autocommit = autocommit

    wrapper.init_connection_state()

    assert wrapper.connection._cursor.executed == [
        ("SELECT set_config(%s, %s, false)", ["timezone", "Asia/Tokyo"])
    ]
    assert wrapper.connection.commits == expected_commits


def test_is_usable_executes_health_query():
    cursor = FakeCursor()
    wrapper = DatabaseWrapper(settings_dict(), "default")
    wrapper.connection = FakeConnection(cursor)
    assert wrapper.is_usable() is True
    assert cursor.executed == [("SELECT 1", None)]


def test_is_usable_swallows_driver_error():
    cursor = FakeCursor(driver.Database.OperationalError("offline"))
    wrapper = DatabaseWrapper(settings_dict(), "default")
    wrapper.connection = FakeConnection(cursor)
    assert wrapper.is_usable() is False
