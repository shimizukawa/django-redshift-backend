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


@dataclass(frozen=True)
class ValidationConfig:
    password: str
    expires_at: str
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
        return cls(
            password=_required(environ, "DB_PASSWORD"),
            expires_at=_required(environ, "REDSHIFT_LIVE_EXPIRES_AT"),
            account=_required(environ, "CDK_DEFAULT_ACCOUNT"),
            region=_required(environ, "CDK_DEFAULT_REGION"),
            allowed_cidr=validate_allowed_cidr(allowed_cidr),
        )
