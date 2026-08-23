import inspect

import pytest
import redshift_connector

from driver_tests.option_contract import (
    REQUIRED_DRIVER_OPTIONS,
    build_connect_kwargs,
    classify_options,
    redact_connect_kwargs,
)


def test_public_connect_signature_covers_required_modes():
    parameters = set(inspect.signature(redshift_connector.connect).parameters)
    assert REQUIRED_DRIVER_OPTIONS <= parameters


def test_standard_settings_map_and_override_duplicate_options():
    settings = {
        "NAME": "warehouse",
        "HOST": "redshift.example",
        "PORT": "5439",
        "USER": "app_user",
        "PASSWORD": "password-value",
        "OPTIONS": {
            "database": "ignored-option-database",
            "user": "ignored-option-user",
            "ssl": True,
            "iam": False,
        },
    }
    assert build_connect_kwargs(settings) == {
        "database": "warehouse",
        "host": "redshift.example",
        "port": 5439,
        "user": "app_user",
        "password": "password-value",
        "ssl": True,
        "iam": False,
    }


def test_dbshell_and_driver_options_are_classified_by_consumer():
    driver, dbshell = classify_options(
        {"sslmode": "verify-full", "passfile": "pgpass", "profile": "dev"}
    )
    assert driver == {"sslmode": "verify-full", "profile": "dev"}
    assert dbshell == {"sslmode": "verify-full", "passfile": "pgpass"}


@pytest.mark.parametrize(
    "name",
    ["options", "isolation_level", "cursor_factory", "connection_factory", "client_encoding"],
)
def test_legacy_psycopg2_options_are_rejected(name):
    with pytest.raises(ValueError, match=name):
        classify_options({name: "value"})


def test_unknown_options_are_rejected():
    with pytest.raises(ValueError, match="unknown_option"):
        classify_options({"unknown_option": True})


def test_credentials_are_redacted_without_changing_non_secrets():
    values = {
        "user": "app_user",
        "password": "password-value",
        "access_key_id": "access-key",
        "secret_access_key": "secret-key",
        "session_token": "session-token",
        "client_secret": "client-secret",
        "web_identity_token": "web-token",
        "token": "bearer-token",
        "region": "ap-northeast-1",
    }
    assert redact_connect_kwargs(values) == {
        "user": "app_user",
        "password": "********",
        "access_key_id": "********",
        "secret_access_key": "********",
        "session_token": "********",
        "client_secret": "********",
        "web_identity_token": "********",
        "token": "********",
        "region": "ap-northeast-1",
    }
