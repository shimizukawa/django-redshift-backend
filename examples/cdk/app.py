from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from urllib.request import urlopen

from aws_cdk import App, Environment

from cdk_app.config import ValidationConfig, validate_allowed_cidr
from cdk_app.stack import LiveValidationStack

FOUR_RPU_REGIONS = frozenset(
    {
        "ap-northeast-1",
        "ap-south-1",
        "ap-southeast-1",
        "ap-southeast-2",
        "eu-north-1",
        "eu-west-1",
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2",
    }
)


def resolve_public_ipv4(fetch: Callable[[], str]) -> str:
    return validate_allowed_cidr(f"{fetch().strip()}/32")


def build_config(
    environ: Mapping[str, str],
    *,
    fetch_ip: Callable[[], str],
) -> ValidationConfig:
    region = environ.get("CDK_DEFAULT_REGION", "").strip()
    if region and region not in FOUR_RPU_REGIONS:
        raise ValueError(f"Redshift Serverless 4 RPU is not supported in {region}")
    return ValidationConfig.from_environment(
        environ,
        allowed_cidr=resolve_public_ipv4(fetch_ip),
    )


def fetch_public_ipv4() -> str:
    with urlopen("https://checkip.amazonaws.com", timeout=10) as response:
        return response.read().decode("ascii")


def main() -> None:
    config = build_config(os.environ, fetch_ip=fetch_public_ipv4)
    app = App()
    LiveValidationStack(
        app,
        "DjangoRedshiftLiveValidation",
        config=config,
        env=Environment(account=config.account, region=config.region),
    )
    app.synth()


if __name__ == "__main__":
    main()
