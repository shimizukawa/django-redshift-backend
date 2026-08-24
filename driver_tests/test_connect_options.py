import inspect

import pytest
from django.core.exceptions import ImproperlyConfigured

from django_redshift_backend.driver import (
    DBSHELL_OPTIONS,
    DEFERRED_AUTH_OPTIONS,
    REQUIRED_DRIVER_OPTIONS,
    Database,
    build_connect_kwargs,
    classify_dbshell_options,
    classify_options,
    connect,
    redact_connect_kwargs,
)

DEFERRED_AUTH_CASES = (
    ("allow_db_user_override", False),
    ("auth_profile", "default"),
    ("auto_create", False),
    ("client_id", "client-id"),
    ("client_secret", "client-secret"),
    ("db_groups", ["analytics"]),
    ("endpoint_url", "https://redshift.example"),
    ("force_lowercase", False),
    ("group_federation", False),
    ("iam", False),
    ("iam_disable_cache", False),
    ("identity_namespace", "example"),
    ("idp_partition", "aws"),
    ("idp_response_timeout", 120),
    ("idp_tenant", "tenant"),
    ("listen_port", 7890),
    ("login_to_rp", "urn:amazon:webservices"),
    ("login_url", "https://example.okta.com/login"),
    ("partner_sp_id", "urn:amazon:webservices"),
    ("preferred_role", "arn:aws:iam::123456789012:role/preferred"),
    ("principal_arn", "arn:aws:iam::123456789012:saml-provider/example"),
    ("profile", "dev"),
    ("provider_name", "example"),
    ("role_session_name", "django-redshift-backend"),
    ("scope", "openid"),
    ("ssl_insecure", False),
    ("credentials_provider", "IdpTokenAuthPlugin"),
    ("db_user", "database-user"),
    ("cluster_identifier", "warehouse-cluster"),
    ("is_serverless", False),
    ("serverless_acct_id", "123456789012"),
    ("serverless_work_group", "analytics"),
    ("access_key_id", "access-key"),
    ("secret_access_key", "secret-key"),
    ("session_token", "session-token"),
    ("role_arn", "arn:aws:iam::123456789012:role/example"),
    ("web_identity_token", "web-token"),
    ("token", "subject-token"),
    ("token_type", "SUBJECT_TOKEN"),
    ("issuer_url", "https://example.awsapps.com/start"),
    ("idc_region", "ap-northeast-1"),
    ("idc_client_display_name", "django-redshift-backend"),
    ("idp_host", "example.okta.com"),
    ("app_id", "app-id"),
    ("app_name", "amazon_aws_redshift"),
)


def test_public_connect_signature_covers_password_scope():
    parameters = set(inspect.signature(Database.connect).parameters)
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
            "password": "ignored-option-password",
            "ssl": True,
        },
    }
    assert build_connect_kwargs(settings) == {
        "database": "warehouse",
        "host": "redshift.example",
        "port": 5439,
        "user": "app_user",
        "password": "password-value",
        "ssl": True,
    }


def test_deferred_authentication_inventory_is_explicit():
    assert DEFERRED_AUTH_OPTIONS == {name for name, _ in DEFERRED_AUTH_CASES}


@pytest.mark.parametrize(("name", "value"), DEFERRED_AUTH_CASES)
def test_deferred_authentication_options_are_rejected_before_connect(name, value):
    settings = {
        "NAME": "warehouse",
        "HOST": "redshift.example",
        "USER": "app_user",
        "PASSWORD": "password-value",
        "OPTIONS": {name: value},
    }
    with pytest.raises(ImproperlyConfigured, match="username/password-only"):
        build_connect_kwargs(settings)


@pytest.mark.parametrize(
    ("settings", "missing"),
    [
        ({"NAME": "warehouse", "PASSWORD": "password-value"}, "USER"),
        ({"NAME": "warehouse", "USER": "app_user"}, "PASSWORD"),
        (
            {"NAME": "warehouse", "USER": "", "PASSWORD": "password-value"},
            "USER",
        ),
        ({"NAME": "warehouse", "USER": "app_user", "PASSWORD": ""}, "PASSWORD"),
        (
            {
                "NAME": "warehouse",
                "PASSWORD": "password-value",
                "OPTIONS": {"user": "option-user"},
            },
            "USER",
        ),
        (
            {
                "NAME": "warehouse",
                "USER": "",
                "PASSWORD": "password-value",
                "OPTIONS": {"user": "option-user"},
            },
            "USER",
        ),
        (
            {
                "NAME": "warehouse",
                "USER": "app_user",
                "OPTIONS": {"password": "option-password"},
            },
            "PASSWORD",
        ),
        (
            {
                "NAME": "warehouse",
                "USER": "app_user",
                "PASSWORD": "",
                "OPTIONS": {"password": "option-password"},
            },
            "PASSWORD",
        ),
    ],
)
def test_password_authentication_requires_nonempty_user_and_password(
    settings, missing
):
    with pytest.raises(ImproperlyConfigured, match=missing):
        build_connect_kwargs(settings)


def test_dbshell_and_driver_options_are_classified_by_consumer():
    driver, dbshell = classify_options(
        {
            "sslmode": "verify-full",
            "passfile": "pgpass",
            "application_name": "django",
            "region": "ap-northeast-1",
        }
    )
    assert driver == {
        "sslmode": "verify-full",
        "application_name": "django",
        "region": "ap-northeast-1",
    }
    assert dbshell == {"sslmode": "verify-full", "passfile": "pgpass"}


@pytest.mark.parametrize("sslmode", ["disable", "allow", "prefer", "require"])
def test_legacy_sslmode_is_rejected_by_driver_option_validation(sslmode):
    with pytest.raises(ImproperlyConfigured, match="sslmode") as error:
        classify_options({"sslmode": sslmode})
    assert "verify-ca" in str(error.value)
    assert "verify-full" in str(error.value)
    assert sslmode not in str(error.value)


def test_invalid_driver_sslmode_error_does_not_echo_its_value():
    invalid_sslmode = "distinctive-invalid-driver-sslmode"

    with pytest.raises(ImproperlyConfigured, match="sslmode") as error:
        classify_options({"sslmode": invalid_sslmode})

    assert "verify-ca" in str(error.value)
    assert "verify-full" in str(error.value)
    assert invalid_sslmode not in str(error.value)


@pytest.mark.parametrize("sslmode", [42, []])
def test_non_string_driver_sslmode_is_a_configuration_error(sslmode):
    with pytest.raises(ImproperlyConfigured, match="sslmode"):
        classify_options({"sslmode": sslmode})


@pytest.mark.parametrize(
    "sslmode", ["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]
)
def test_dbshell_preserves_the_full_psql_sslmode_domain(sslmode):
    assert classify_dbshell_options({"sslmode": sslmode}) == {"sslmode": sslmode}


def test_invalid_dbshell_sslmode_error_does_not_echo_its_value():
    invalid_sslmode = "distinctive-invalid-dbshell-sslmode"

    with pytest.raises(ImproperlyConfigured, match="sslmode") as error:
        classify_dbshell_options({"sslmode": invalid_sslmode})

    assert "disable" in str(error.value)
    assert "verify-full" in str(error.value)
    assert invalid_sslmode not in str(error.value)


@pytest.mark.parametrize("sslmode", [42, []])
def test_non_string_dbshell_sslmode_is_a_configuration_error(sslmode):
    with pytest.raises(ImproperlyConfigured, match="sslmode"):
        classify_dbshell_options({"sslmode": sslmode})


@pytest.mark.parametrize(
    "name",
    ["options", "isolation_level", "cursor_factory", "connection_factory", "client_encoding"],
)
def test_legacy_psycopg2_options_are_rejected(name):
    with pytest.raises(ImproperlyConfigured, match=name):
        classify_options({name: "value"})


def test_unknown_options_are_rejected():
    with pytest.raises(ImproperlyConfigured, match="unknown_option"):
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


def test_connect_delegates_only_validated_keyword_arguments(monkeypatch):
    calls = []
    expected = object()

    def fake_connect(**kwargs):
        calls.append(kwargs)
        return expected

    monkeypatch.setattr("django_redshift_backend.driver.Database.connect", fake_connect)

    result = connect(user="alice", password="secret", host="example.test")

    assert result is expected
    assert calls == [{"user": "alice", "password": "secret", "host": "example.test"}]


def test_invalid_port_is_a_redacted_configuration_error():
    settings = {
        "USER": "alice",
        "PASSWORD": "secret",
        "PORT": "not-a-port",
        "OPTIONS": {},
    }
    with pytest.raises(ImproperlyConfigured, match="PORT must be an integer") as error:
        build_connect_kwargs(settings)
    assert "not-a-port" not in str(error.value)
