import inspect

import redshift_connector


STANDARD_SETTING_MAP = {
    "NAME": "database",
    "HOST": "host",
    "PORT": "port",
    "USER": "user",
    "PASSWORD": "password",
}
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


def build_connect_kwargs(settings_dict):
    driver, _ = classify_options(settings_dict.get("OPTIONS", {}))
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
