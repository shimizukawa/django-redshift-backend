import signal

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db.backends.base.client import BaseDatabaseClient

from django_redshift_backend.client import DatabaseClient


def test_psql_arguments_and_environment_preserve_existing_contract():
    settings = {
        "NAME": "warehouse",
        "HOST": "example.test",
        "PORT": 5439,
        "USER": "alice",
        "PASSWORD": "secret",
        "OPTIONS": {
            "passfile": "/tmp/pgpass",
            "service": "analytics",
            "sslmode": "require",
            "sslrootcert": "/tmp/root.crt",
            "sslcert": "/tmp/client.crt",
            "sslkey": "/tmp/client.key",
        },
    }

    args, env = DatabaseClient.settings_to_cmd_args_env(settings, ["-c", "SELECT 1"])

    assert args == [
        "psql",
        "-U",
        "alice",
        "-h",
        "example.test",
        "-p",
        "5439",
        "-c",
        "SELECT 1",
        "warehouse",
    ]
    assert env == {
        "PGPASSWORD": "secret",
        "PGPASSFILE": "/tmp/pgpass",
        "PGSERVICE": "analytics",
        "PGSSLMODE": "require",
        "PGSSLROOTCERT": "/tmp/root.crt",
        "PGSSLCERT": "/tmp/client.crt",
        "PGSSLKEY": "/tmp/client.key",
    }


def test_service_omits_default_database_and_empty_environment_is_none():
    args, env = DatabaseClient.settings_to_cmd_args_env(
        {
            "NAME": "",
            "HOST": "",
            "PORT": "",
            "USER": "",
            "PASSWORD": "",
            "OPTIONS": {"service": "analytics"},
        },
        [],
    )
    assert args == ["psql"]
    assert env == {"PGSERVICE": "analytics"}


def test_missing_name_and_service_uses_postgres_database():
    args, env = DatabaseClient.settings_to_cmd_args_env(
        {
            "NAME": "",
            "HOST": "",
            "PORT": "",
            "USER": "",
            "PASSWORD": "",
            "OPTIONS": {},
        },
        [],
    )
    assert args == ["psql", "postgres"]
    assert env is None


def test_invalid_psql_sslmode_is_rejected():
    with pytest.raises(ImproperlyConfigured, match="Unsupported psql sslmode"):
        DatabaseClient.settings_to_cmd_args_env(
            {"NAME": "warehouse", "OPTIONS": {"sslmode": "invalid"}}, []
        )


def test_runshell_ignores_sigint_for_the_superclass_call_and_restores_it(monkeypatch):
    calls = []
    original_handler = object()

    monkeypatch.setattr(
        signal,
        "getsignal",
        lambda signal_number: calls.append(("getsignal", signal_number)) or original_handler,
    )
    monkeypatch.setattr(
        signal,
        "signal",
        lambda signal_number, handler: calls.append(("signal", signal_number, handler)),
    )
    monkeypatch.setattr(
        BaseDatabaseClient,
        "runshell",
        lambda self, parameters: calls.append(("runshell", parameters)),
    )

    DatabaseClient(None).runshell(["-c", "SELECT 1"])

    assert calls == [
        ("getsignal", signal.SIGINT),
        ("signal", signal.SIGINT, signal.SIG_IGN),
        ("runshell", ["-c", "SELECT 1"]),
        ("signal", signal.SIGINT, original_handler),
    ]


def test_runshell_restores_sigint_when_the_superclass_raises(monkeypatch):
    calls = []
    original_handler = object()

    monkeypatch.setattr(
        signal,
        "getsignal",
        lambda signal_number: calls.append(("getsignal", signal_number)) or original_handler,
    )
    monkeypatch.setattr(
        signal,
        "signal",
        lambda signal_number, handler: calls.append(("signal", signal_number, handler)),
    )

    def raise_from_runshell(self, parameters):
        calls.append(("runshell", parameters))
        raise RuntimeError("superclass failed")

    monkeypatch.setattr(BaseDatabaseClient, "runshell", raise_from_runshell)

    with pytest.raises(RuntimeError, match="superclass failed"):
        DatabaseClient(None).runshell([])

    assert calls == [
        ("getsignal", signal.SIGINT),
        ("signal", signal.SIGINT, signal.SIG_IGN),
        ("runshell", []),
        ("signal", signal.SIGINT, original_handler),
    ]
