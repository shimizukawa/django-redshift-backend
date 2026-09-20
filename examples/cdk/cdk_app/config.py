from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from ipaddress import IPv4Network, ip_network


def validate_allowed_cidr(value: str) -> str:
    try:
        network = ip_network(value, strict=True)
    except ValueError as error:
        raise ValueError("allowed CIDR must be a public IPv4 /32") from error
    if not isinstance(network, IPv4Network) or network.prefixlen != 32:
        raise ValueError("allowed CIDR must be a public IPv4 /32")
    if not network.is_global:
        raise ValueError("allowed CIDR must be a public IPv4 /32")
    return str(network)


def _required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def validate_db_password(value: str) -> str:
    forbidden = {"'", '"', "\\", "/", "@"}
    valid = (
        8 <= len(value) <= 64
        and any("A" <= character <= "Z" for character in value)
        and any("a" <= character <= "z" for character in value)
        and any("0" <= character <= "9" for character in value)
        and all(
            33 <= ord(character) <= 126 and character not in forbidden
            for character in value
        )
    )
    if not valid:
        raise ValueError(
            "DB_PASSWORD must be 8-64 printable ASCII characters, include an "
            "uppercase letter, a lowercase letter, and a number, and must not "
            "contain single quotes, double quotes, backslashes, slashes, or @"
        )
    return value


@dataclass(frozen=True)
class ValidationConfig:
    password: str
    account: str
    region: str
    allowed_cidr: str
    prefix: str = "django-redshift-live"
    base_capacity: int = 4
    max_capacity: int = 8
    daily_rpu_hours: int = 8

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str],
        *,
        allowed_cidr: str,
    ) -> ValidationConfig:
        password = environ.get("DB_PASSWORD", "")
        if not password:
            raise ValueError("DB_PASSWORD is required")
        return cls(
            password=validate_db_password(password),
            account=_required(environ, "CDK_DEFAULT_ACCOUNT"),
            region=_required(environ, "CDK_DEFAULT_REGION"),
            allowed_cidr=validate_allowed_cidr(allowed_cidr),
        )
