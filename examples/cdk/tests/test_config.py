import pytest

from cdk_app.config import ValidationConfig, validate_allowed_cidr


@pytest.mark.parametrize(
    "value",
    ["0.0.0.0/0", "203.0.113.0/24", "::1/128", "invalid"],
)
def test_allowed_cidr_requires_public_ipv4_host(value):
    with pytest.raises(ValueError, match="public IPv4 /32"):
        validate_allowed_cidr(value)


def test_environment_supplies_password_without_expiration_variable():
    environ = {
        "DB_PASSWORD": "synthesis-only-value-A1",
        "CDK_DEFAULT_ACCOUNT": "123456789012",
        "CDK_DEFAULT_REGION": "ap-northeast-1",
    }

    config = ValidationConfig.from_environment(
        environ,
        allowed_cidr="8.8.8.8/32",
    )

    assert config.allowed_cidr == "8.8.8.8/32"
    assert config.password == "synthesis-only-value-A1"
    assert config.account == "123456789012"
    assert config.region == "ap-northeast-1"
    assert config.base_capacity == 4
    assert config.max_capacity == 8
    assert config.daily_rpu_hours == 8


@pytest.mark.parametrize(
    "name",
    [
        "DB_PASSWORD",
        "CDK_DEFAULT_ACCOUNT",
        "CDK_DEFAULT_REGION",
    ],
)
def test_environment_rejects_missing_required_value(name):
    environ = {
        "DB_PASSWORD": "synthesis-only-value-A1",
        "CDK_DEFAULT_ACCOUNT": "123456789012",
        "CDK_DEFAULT_REGION": "ap-northeast-1",
    }
    del environ[name]

    with pytest.raises(ValueError, match=name):
        ValidationConfig.from_environment(environ, allowed_cidr="8.8.8.8/32")
