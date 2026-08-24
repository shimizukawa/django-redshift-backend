from unittest.mock import patch

import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.utils import NotSupportedError

from django_redshift_backend import driver
from django_redshift_backend._backend import DatabaseWrapper
from django_redshift_backend.client import DatabaseClient


class FakeCursor:
    def __init__(self, error=None):
        self.error = error
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, sql):
        if self.error:
            raise self.error
        self.executed.append(sql)


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.autocommit = False

    def cursor(self):
        return self._cursor


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
    monkeypatch.setattr(driver, "connect", lambda **kwargs: calls.append(kwargs) or expected)
    params = {"user": "alice", "password": "secret"}
    assert wrapper.get_new_connection(params) is expected
    assert calls == [params]


def test_create_cursor_rejects_named_cursor():
    wrapper = DatabaseWrapper(settings_dict(), "default")
    wrapper.connection = FakeConnection(FakeCursor())
    assert wrapper.create_cursor() is wrapper.connection._cursor
    with pytest.raises(NotSupportedError, match="named cursor"):
        wrapper.create_cursor(name="server-side")


def test_autocommit_uses_public_driver_attribute():
    wrapper = DatabaseWrapper(settings_dict(), "default")
    wrapper.connection = FakeConnection(FakeCursor())
    wrapper._set_autocommit(True)
    assert wrapper.connection.autocommit is True


def test_init_connection_state_delegates_without_session_sql():
    wrapper = DatabaseWrapper(settings_dict(), "foundation-test")
    wrapper.connection = FakeConnection(FakeCursor())
    with patch.object(BaseDatabaseWrapper, "init_connection_state") as initialize:
        wrapper.init_connection_state()
    initialize.assert_called_once_with()
    assert wrapper.connection._cursor.executed == []


def test_is_usable_executes_health_query():
    cursor = FakeCursor()
    wrapper = DatabaseWrapper(settings_dict(), "default")
    wrapper.connection = FakeConnection(cursor)
    assert wrapper.is_usable() is True
    assert cursor.executed == ["SELECT 1"]


def test_is_usable_swallows_driver_error():
    cursor = FakeCursor(driver.Database.OperationalError("offline"))
    wrapper = DatabaseWrapper(settings_dict(), "default")
    wrapper.connection = FakeConnection(cursor)
    assert wrapper.is_usable() is False
