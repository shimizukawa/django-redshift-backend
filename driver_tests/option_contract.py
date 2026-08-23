import inspect
from importlib.metadata import version

import redshift_connector
from packaging.version import Version

STANDARD_SETTING_MAP = {
    "NAME": "database",
    "HOST": "host",
    "PORT": "port",
}
DRIVER_SSLMODES = {"verify-ca", "verify-full"}
DBSHELL_SSLMODES = {"disable", "allow", "prefer", "require", *DRIVER_SSLMODES}
IDC_PROVIDERS = {"IdpTokenAuthPlugin", "BrowserIdcAuthPlugin"}
LEGACY_IAM_PROVIDERS = {"OktaCredentialsProvider"}
SUPPORTED_CREDENTIALS_PROVIDERS = IDC_PROVIDERS | LEGACY_IAM_PROVIDERS
IDC_TOKEN_OPTIONS = {
    "token",
    "token_type",
    "access_key_id",
    "secret_access_key",
    "session_token",
}
BROWSER_IDC_OPTIONS = {"issuer_url", "idc_region", "idc_client_display_name"}
OKTA_OPTIONS = {"idp_host", "app_id", "app_name"}
PROVIDER_ONLY_OPTIONS = {"token", "token_type"} | BROWSER_IDC_OPTIONS | OKTA_OPTIONS
REQUIRED_DRIVER_OPTIONS = {
    "user",
    "database",
    "password",
    "port",
    "host",
    "ssl",
    "sslmode",
    "timeout",
    "application_name",
    "access_key_id",
    "secret_access_key",
    "session_token",
    "profile",
    "credentials_provider",
    "region",
    "cluster_identifier",
    "iam",
    "db_user",
    "role_arn",
    "is_serverless",
    "serverless_acct_id",
    "serverless_work_group",
    "web_identity_token",
    "token",
}
DBSHELL_OPTIONS = {
    "passfile",
    "service",
    "sslmode",
    "sslrootcert",
    "sslcert",
    "sslkey",
}
REJECTED_LEGACY_OPTIONS = {
    "options",
    "isolation_level",
    "cursor_factory",
    "connection_factory",
    "client_encoding",
}
SENSITIVE_OPTIONS = {
    "password",
    "access_key_id",
    "secret_access_key",
    "session_token",
    "client_secret",
    "web_identity_token",
    "token",
}


def classify_options(options):
    public_driver_options = set(inspect.signature(redshift_connector.connect).parameters)
    driver = {}
    dbshell = {}
    for name, value in options.items():
        if name in REJECTED_LEGACY_OPTIONS:
            raise ValueError(f"Unsupported legacy psycopg2 option: {name}")
        if name == "sslmode" and value not in DRIVER_SSLMODES:
            raise ValueError(
                f"Unsupported redshift_connector sslmode: {value}; "
                "expected verify-ca or verify-full"
            )
        consumed = False
        if name in public_driver_options:
            driver[name] = value
            consumed = True
        if name in DBSHELL_OPTIONS:
            dbshell[name] = value
            consumed = True
        if not consumed:
            raise ValueError(f"Unknown database option: {name}")
    return driver, dbshell


def classify_dbshell_options(options):
    dbshell = {name: value for name, value in options.items() if name in DBSHELL_OPTIONS}
    sslmode = dbshell.get("sslmode")
    if sslmode is not None and sslmode not in DBSHELL_SSLMODES:
        raise ValueError(f"Unsupported psql sslmode: {sslmode}")
    return dbshell


def _require_nonempty(settings, name):
    value = settings.get(name)
    if value in (None, ""):
        raise ValueError(f"{name} is required for the selected authentication mode")
    return value


def _reject_nonempty(driver, names, provider):
    conflicts = sorted(name for name in names if driver.get(name) not in (None, ""))
    if conflicts:
        raise ValueError(
            f"{provider} does not accept option(s): {', '.join(conflicts)}"
        )


def _validate_provider_mode(driver, settings_dict):
    provider = driver.get("credentials_provider")
    if provider in (None, ""):
        orphaned = sorted(
            name for name in PROVIDER_ONLY_OPTIONS if driver.get(name) not in (None, "")
        )
        if orphaned:
            raise ValueError(
                f"credentials_provider is required for option(s): {', '.join(orphaned)}"
            )
        return None
    if provider not in SUPPORTED_CREDENTIALS_PROVIDERS:
        raise ValueError(
            f"Unsupported credentials_provider for this investigation: {provider}"
        )
    for name in ("NAME", "HOST"):
        _require_nonempty(settings_dict, name)

    if provider in IDC_PROVIDERS:
        if driver.get("iam") is True:
            raise ValueError(f"{provider} requires iam=False")
        for name in ("USER", "PASSWORD"):
            if settings_dict.get(name) not in (None, ""):
                raise ValueError(f"{name} conflicts with {provider}")

    if provider == "IdpTokenAuthPlugin":
        _reject_nonempty(driver, BROWSER_IDC_OPTIONS | OKTA_OPTIONS, provider)
        explicit_aws = {
            name for name in ("access_key_id", "secret_access_key", "session_token")
            if driver.get(name) not in (None, "")
        }
        if explicit_aws:
            raise ValueError(
                "IdpTokenAuthPlugin explicit AWS credentials are not supported "
                "by this investigation"
            )
        token = driver.get("token")
        token_type = driver.get("token_type")
        if token not in (None, "") or token_type not in (None, ""):
            if token in (None, ""):
                raise ValueError("token is required when token_type is provided")
            if token_type in (None, ""):
                raise ValueError("token_type is required when token is provided")
            if token_type != "SUBJECT_TOKEN":
                raise ValueError(
                    "IdpTokenAuthPlugin direct token requires token_type=SUBJECT_TOKEN"
                )
        elif Version(version("redshift-connector")) < Version("2.1.16"):
            raise ValueError(
                "IdpTokenAuthPlugin default credential chain requires "
                "redshift-connector>=2.1.16"
            )
        return "native_idc"

    if provider == "BrowserIdcAuthPlugin":
        _reject_nonempty(driver, IDC_TOKEN_OPTIONS | OKTA_OPTIONS, provider)
        for name in ("issuer_url", "idc_region"):
            if driver.get(name) in (None, ""):
                raise ValueError(f"{name} is required for BrowserIdcAuthPlugin")
        return "native_idc"

    if driver.get("iam") is not True:
        raise ValueError(f"{provider} requires iam=True")
    _reject_nonempty(
        driver,
        IDC_TOKEN_OPTIONS | BROWSER_IDC_OPTIONS | {"profile", "db_user"},
        provider,
    )
    if driver.get("is_serverless") is True:
        raise ValueError(f"{provider} Serverless mode is not investigated")
    for name in ("cluster_identifier", "idp_host", "app_id", "app_name"):
        if driver.get(name) in (None, ""):
            raise ValueError(f"{name} is required for {provider}")
    _require_nonempty(settings_dict, "USER")
    _require_nonempty(settings_dict, "PASSWORD")
    return "legacy_iam"


def build_connect_kwargs(settings_dict):
    driver, _ = classify_options(settings_dict.get("OPTIONS", {}))
    iam = driver.get("iam") is True
    is_serverless = driver.get("is_serverless") is True
    provider_mode = _validate_provider_mode(driver, settings_dict)

    if driver.get("profile") not in (None, "") and not iam:
        raise ValueError("profile requires iam=True")
    if any(
        driver.get(name) not in (None, "")
        for name in ("serverless_acct_id", "serverless_work_group")
    ) and not is_serverless:
        raise ValueError("Serverless options require is_serverless=True")

    if provider_mode == "legacy_iam":
        driver["user"] = settings_dict["USER"]
        driver["password"] = settings_dict["PASSWORD"]
    elif provider_mode == "native_idc":
        pass
    elif iam:
        user = _require_nonempty(settings_dict, "USER")
        if settings_dict.get("PASSWORD") not in (None, ""):
            raise ValueError("PASSWORD conflicts with IAM authentication")
        if driver.get("user") not in (None, ""):
            raise ValueError("OPTIONS['user'] conflicts with IAM authentication")
        driver.pop("user", None)
        driver["db_user"] = user

        if is_serverless:
            if driver.get("cluster_identifier") not in (None, ""):
                raise ValueError(
                    "cluster_identifier conflicts with Serverless authentication"
                )
            for name in ("serverless_acct_id", "serverless_work_group"):
                if driver.get(name) in (None, ""):
                    raise ValueError(f"{name} is required for Serverless authentication")
        elif driver.get("cluster_identifier") in (None, ""):
            raise ValueError(
                "cluster_identifier is required for provisioned IAM authentication"
            )
    else:
        if is_serverless:
            raise ValueError("is_serverless=True requires iam=True")
        if driver.get("db_user") not in (None, ""):
            raise ValueError("OPTIONS['db_user'] requires IAM authentication")
        driver["user"] = _require_nonempty(settings_dict, "USER")
        driver["password"] = _require_nonempty(settings_dict, "PASSWORD")

    for setting_name, driver_name in STANDARD_SETTING_MAP.items():
        value = settings_dict.get(setting_name)
        if value not in (None, ""):
            driver[driver_name] = int(value) if setting_name == "PORT" else value
    return driver


def redact_connect_kwargs(kwargs):
    return {
        name: "********" if name in SENSITIVE_OPTIONS and value is not None else value
        for name, value in kwargs.items()
    }
