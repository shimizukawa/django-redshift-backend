import inspect
from importlib.metadata import version

import pytest
import redshift_connector
from packaging.version import Version

from driver_tests.option_contract import (
    REQUIRED_DRIVER_OPTIONS,
    build_connect_kwargs,
    classify_dbshell_options,
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


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        (
            {
                "NAME": "warehouse",
                "HOST": "redshift.example",
                "USER": "app_user",
                "PASSWORD": "password-value",
            },
            {
                "database": "warehouse",
                "host": "redshift.example",
                "user": "app_user",
                "password": "password-value",
            },
        ),
        (
            {
                "NAME": "warehouse",
                "USER": "iam_user",
                "OPTIONS": {
                    "iam": True,
                    "profile": "dev",
                    "cluster_identifier": "warehouse-cluster",
                    "region": "ap-northeast-1",
                },
            },
            {
                "database": "warehouse",
                "db_user": "iam_user",
                "iam": True,
                "profile": "dev",
                "cluster_identifier": "warehouse-cluster",
                "region": "ap-northeast-1",
            },
        ),
        (
            {
                "NAME": "warehouse",
                "USER": "iam_user",
                "OPTIONS": {
                    "iam": True,
                    "cluster_identifier": "warehouse-cluster",
                    "region": "ap-northeast-1",
                },
            },
            {
                "database": "warehouse",
                "db_user": "iam_user",
                "iam": True,
                "cluster_identifier": "warehouse-cluster",
                "region": "ap-northeast-1",
            },
        ),
        (
            {
                "NAME": "warehouse",
                "USER": "iam_user",
                "OPTIONS": {
                    "iam": True,
                    "is_serverless": True,
                    "serverless_acct_id": "123456789012",
                    "serverless_work_group": "analytics",
                    "region": "ap-northeast-1",
                },
            },
            {
                "database": "warehouse",
                "db_user": "iam_user",
                "iam": True,
                "is_serverless": True,
                "serverless_acct_id": "123456789012",
                "serverless_work_group": "analytics",
                "region": "ap-northeast-1",
            },
        ),
    ],
    ids=("password", "iam-profile", "iam-provisioned", "iam-serverless"),
)
def test_authentication_modes_map_django_user_to_the_documented_driver_field(
    settings, expected
):
    assert build_connect_kwargs(settings) == expected


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        (
            {
                "NAME": "warehouse",
                "HOST": "redshift.example",
                "OPTIONS": {
                    "credentials_provider": "IdpTokenAuthPlugin",
                    "token": "identity-center-subject-token",
                    "token_type": "SUBJECT_TOKEN",
                },
            },
            {
                "database": "warehouse",
                "host": "redshift.example",
                "credentials_provider": "IdpTokenAuthPlugin",
                "token": "identity-center-subject-token",
                "token_type": "SUBJECT_TOKEN",
            },
        ),
        (
            {
                "NAME": "warehouse",
                "HOST": "redshift.example",
                "OPTIONS": {
                    "credentials_provider": "BrowserIdcAuthPlugin",
                    "issuer_url": "https://example.awsapps.com/start",
                    "idc_region": "ap-northeast-1",
                },
            },
            {
                "database": "warehouse",
                "host": "redshift.example",
                "credentials_provider": "BrowserIdcAuthPlugin",
                "issuer_url": "https://example.awsapps.com/start",
                "idc_region": "ap-northeast-1",
            },
        ),
        (
            {
                "NAME": "warehouse",
                "HOST": "redshift.example",
                "USER": "okta-user@example.com",
                "PASSWORD": "okta-password",
                "OPTIONS": {
                    "iam": True,
                    "cluster_identifier": "warehouse-cluster",
                    "credentials_provider": "OktaCredentialsProvider",
                    "idp_host": "example.okta.com",
                    "app_id": "app-id",
                    "app_name": "amazon_aws",
                },
            },
            {
                "database": "warehouse",
                "host": "redshift.example",
                "user": "okta-user@example.com",
                "password": "okta-password",
                "iam": True,
                "cluster_identifier": "warehouse-cluster",
                "credentials_provider": "OktaCredentialsProvider",
                "idp_host": "example.okta.com",
                "app_id": "app-id",
                "app_name": "amazon_aws",
            },
        ),
    ],
    ids=("idp-token-direct", "browser-idc", "legacy-okta-iam"),
)
def test_supported_provider_families_map_credentials_by_documented_mode(
    settings, expected
):
    assert build_connect_kwargs(settings) == expected


def test_idp_token_default_credential_chain_is_version_bounded():
    settings = {
        "NAME": "warehouse",
        "HOST": "redshift.example",
        "OPTIONS": {"credentials_provider": "IdpTokenAuthPlugin"},
    }
    if Version(version("redshift-connector")) < Version("2.1.16"):
        with pytest.raises(ValueError, match="2.1.16"):
            build_connect_kwargs(settings)
    else:
        assert build_connect_kwargs(settings) == {
            "database": "warehouse",
            "host": "redshift.example",
            "credentials_provider": "IdpTokenAuthPlugin",
        }


@pytest.mark.parametrize("missing", ["NAME", "HOST"])
def test_provider_modes_require_database_and_host_before_connect(missing):
    settings = {
        "NAME": "warehouse",
        "HOST": "redshift.example",
        "OPTIONS": {
            "credentials_provider": "IdpTokenAuthPlugin",
            "token": "subject-token",
            "token_type": "SUBJECT_TOKEN",
        },
    }
    del settings[missing]
    with pytest.raises(ValueError, match=missing):
        build_connect_kwargs(settings)


@pytest.mark.parametrize(
    ("options", "standard", "message"),
    [
        ({"credentials_provider": "ArbitraryPlugin"}, {}, "ArbitraryPlugin"),
        (
            {"credentials_provider": "IdpTokenAuthPlugin", "iam": True},
            {},
            "iam",
        ),
        (
            {
                "credentials_provider": "IdpTokenAuthPlugin",
                "token": "subject-token",
            },
            {},
            "token_type",
        ),
        (
            {
                "credentials_provider": "IdpTokenAuthPlugin",
                "token": "subject-token",
                "token_type": "ACCESS_TOKEN",
            },
            {},
            "SUBJECT_TOKEN",
        ),
        (
            {
                "credentials_provider": "IdpTokenAuthPlugin",
                "token": "subject-token",
                "token_type": "SUBJECT_TOKEN",
            },
            {"USER": "conflict"},
            "USER",
        ),
        (
            {
                "credentials_provider": "BrowserIdcAuthPlugin",
                "idc_region": "ap-northeast-1",
            },
            {},
            "issuer_url",
        ),
        (
            {
                "credentials_provider": "BrowserIdcAuthPlugin",
                "issuer_url": "https://example.awsapps.com/start",
                "idc_region": "ap-northeast-1",
                "token": "wrong-family",
            },
            {},
            "token",
        ),
        (
            {
                "credentials_provider": "OktaCredentialsProvider",
                "cluster_identifier": "warehouse-cluster",
                "idp_host": "example.okta.com",
                "app_id": "app-id",
                "app_name": "amazon_aws",
            },
            {"USER": "okta-user", "PASSWORD": "okta-password"},
            "iam",
        ),
        (
            {
                "credentials_provider": "OktaCredentialsProvider",
                "iam": True,
                "cluster_identifier": "warehouse-cluster",
                "app_id": "app-id",
                "app_name": "amazon_aws",
            },
            {"USER": "okta-user", "PASSWORD": "okta-password"},
            "idp_host",
        ),
        (
            {
                "credentials_provider": "OktaCredentialsProvider",
                "iam": True,
                "cluster_identifier": "warehouse-cluster",
                "idp_host": "example.okta.com",
                "app_id": "app-id",
                "app_name": "amazon_aws",
                "token": "wrong-family",
            },
            {"USER": "okta-user", "PASSWORD": "okta-password"},
            "token",
        ),
        ({"token": "orphan-token"}, {}, "credentials_provider"),
    ],
)
def test_incomplete_or_cross_family_provider_settings_fail_before_connect(
    options, standard, message
):
    settings = {
        "NAME": "warehouse",
        "HOST": "redshift.example",
        "OPTIONS": options,
        **standard,
    }
    with pytest.raises(ValueError, match=message):
        build_connect_kwargs(settings)


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"NAME": "warehouse", "PASSWORD": "secret"}, "USER"),
        ({"NAME": "warehouse", "USER": "app_user"}, "PASSWORD"),
        (
            {
                "NAME": "warehouse",
                "USER": "iam_user",
                "PASSWORD": "conflict",
                "OPTIONS": {
                    "iam": True,
                    "cluster_identifier": "cluster",
                    "region": "ap-northeast-1",
                },
            },
            "PASSWORD",
        ),
        (
            {
                "NAME": "warehouse",
                "USER": "iam_user",
                "OPTIONS": {"iam": True, "region": "ap-northeast-1"},
            },
            "cluster_identifier",
        ),
        (
            {
                "NAME": "warehouse",
                "USER": "iam_user",
                "OPTIONS": {"profile": "dev"},
            },
            "profile",
        ),
        (
            {
                "NAME": "warehouse",
                "USER": "iam_user",
                "OPTIONS": {
                    "iam": True,
                    "is_serverless": True,
                    "serverless_work_group": "analytics",
                    "region": "ap-northeast-1",
                },
            },
            "serverless_acct_id",
        ),
        (
            {
                "NAME": "warehouse",
                "USER": "iam_user",
                "OPTIONS": {
                    "iam": True,
                    "is_serverless": True,
                    "serverless_acct_id": "123456789012",
                    "serverless_work_group": "analytics",
                    "cluster_identifier": "conflict",
                    "region": "ap-northeast-1",
                },
            },
            "cluster_identifier",
        ),
    ],
)
def test_incomplete_or_conflicting_authentication_modes_fail_before_connect(
    settings, message
):
    with pytest.raises(ValueError, match=message):
        build_connect_kwargs(settings)


def test_dbshell_and_driver_options_are_classified_by_consumer():
    driver, dbshell = classify_options(
        {"sslmode": "verify-full", "passfile": "pgpass", "profile": "dev"}
    )
    assert driver == {"sslmode": "verify-full", "profile": "dev"}
    assert dbshell == {"sslmode": "verify-full", "passfile": "pgpass"}


@pytest.mark.parametrize("sslmode", ["disable", "allow", "prefer", "require"])
def test_legacy_sslmode_is_rejected_by_driver_option_validation(sslmode):
    with pytest.raises(ValueError, match=sslmode):
        classify_options({"sslmode": sslmode})


@pytest.mark.parametrize(
    "sslmode", ["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]
)
def test_dbshell_preserves_the_full_psql_sslmode_domain(sslmode):
    assert classify_dbshell_options({"sslmode": sslmode}) == {"sslmode": sslmode}


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
