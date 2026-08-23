import inspect

import redshift_connector

STANDARD_SETTING_MAP = {
    "NAME": "database",
    "HOST": "host",
    "PORT": "port",
}
DRIVER_SSLMODES = {"verify-ca", "verify-full"}
DBSHELL_SSLMODES = {"disable", "allow", "prefer", "require", *DRIVER_SSLMODES}
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


def build_connect_kwargs(settings_dict):
    driver, _ = classify_options(settings_dict.get("OPTIONS", {}))
    iam = driver.get("iam") is True
    is_serverless = driver.get("is_serverless") is True
    uses_identity_provider = driver.get("credentials_provider") not in (None, "")

    if driver.get("profile") not in (None, "") and not iam:
        raise ValueError("profile requires iam=True")
    if any(
        driver.get(name) not in (None, "")
        for name in ("serverless_acct_id", "serverless_work_group")
    ) and not is_serverless:
        raise ValueError("Serverless options require is_serverless=True")

    if iam:
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
        if uses_identity_provider:
            for setting_name, driver_name in (
                ("USER", "user"),
                ("PASSWORD", "password"),
            ):
                value = settings_dict.get(setting_name)
                if value not in (None, ""):
                    driver[driver_name] = value
        else:
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
