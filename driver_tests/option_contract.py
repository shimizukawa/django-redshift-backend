import inspect

import redshift_connector

STANDARD_SETTING_MAP = {
    "NAME": "database",
    "HOST": "host",
    "PORT": "port",
}
DRIVER_SSLMODES = {"verify-ca", "verify-full"}
DBSHELL_SSLMODES = {"disable", "allow", "prefer", "require", *DRIVER_SSLMODES}
DEFERRED_AUTH_OPTIONS = {
    "access_key_id",
    "allow_db_user_override",
    "app_id",
    "app_name",
    "auth_profile",
    "auto_create",
    "client_id",
    "client_secret",
    "cluster_identifier",
    "credentials_provider",
    "db_groups",
    "db_user",
    "endpoint_url",
    "force_lowercase",
    "group_federation",
    "iam",
    "iam_disable_cache",
    "identity_namespace",
    "idc_client_display_name",
    "idc_region",
    "idp_host",
    "idp_partition",
    "idp_response_timeout",
    "idp_tenant",
    "is_serverless",
    "issuer_url",
    "listen_port",
    "login_to_rp",
    "login_url",
    "partner_sp_id",
    "preferred_role",
    "principal_arn",
    "profile",
    "provider_name",
    "role_arn",
    "role_session_name",
    "scope",
    "secret_access_key",
    "serverless_acct_id",
    "serverless_work_group",
    "session_token",
    "ssl_insecure",
    "token",
    "token_type",
    "web_identity_token",
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
    deferred = sorted(DEFERRED_AUTH_OPTIONS.intersection(options))
    if deferred:
        raise ValueError(
            "Authentication option(s) are unsupported because the initial "
            f"release is username/password-only: {', '.join(deferred)}"
        )
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
