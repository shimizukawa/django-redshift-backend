import pytest

from app import build_config, resolve_public_ipv4


def valid_environment():
    return {
        "DB_PASSWORD": "synthesis-only-value-A1",
        "REDSHIFT_LIVE_EXPIRES_AT": "2026-08-31",
        "CDK_DEFAULT_ACCOUNT": "123456789012",
        "CDK_DEFAULT_REGION": "ap-northeast-1",
    }


def test_public_ip_lookup_returns_single_host_cidr():
    assert resolve_public_ipv4(lambda: "8.8.8.8\n") == "8.8.8.8/32"


@pytest.mark.parametrize("response", ["10.0.0.1", "::1", "invalid"])
def test_public_ip_lookup_rejects_unsafe_response(response):
    with pytest.raises(ValueError, match="public IPv4 /32"):
        resolve_public_ipv4(lambda: response)


def test_build_config_accepts_supported_four_rpu_region():
    config = build_config(valid_environment(), fetch_ip=lambda: "8.8.8.8")
    assert config.region == "ap-northeast-1"
    assert config.allowed_cidr == "8.8.8.8/32"


def test_build_config_rejects_region_without_four_rpu_support():
    environ = valid_environment()
    environ["CDK_DEFAULT_REGION"] = "eu-west-2"
    with pytest.raises(ValueError, match="4 RPU"):
        build_config(environ, fetch_ip=lambda: "8.8.8.8")


def test_missing_password_error_does_not_include_other_environment_values():
    environ = valid_environment()
    del environ["DB_PASSWORD"]
    with pytest.raises(ValueError) as raised:
        build_config(environ, fetch_ip=lambda: "8.8.8.8")
    assert str(raised.value) == "DB_PASSWORD is required"
    assert "synthesis-only" not in str(raised.value)
