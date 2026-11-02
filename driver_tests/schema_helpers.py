import re

from django_redshift_backend._backend import DatabaseWrapper


def settings_dict():
    return {
        "NAME": "warehouse",
        "HOST": "example.test",
        "PORT": "5439",
        "USER": "alice",
        "PASSWORD": "secret",
        "OPTIONS": {},
        "TIME_ZONE": None,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "AUTOCOMMIT": True,
    }


def make_wrapper(alias="schema-contract"):
    return DatabaseWrapper(settings_dict(), alias)


def collect_schema_sql(callback):
    wrapper = make_wrapper()
    with wrapper.schema_editor(collect_sql=True, atomic=False) as editor:
        callback(editor)
    return [normalize_sql(statement) for statement in editor.collected_sql]


def normalize_sql(sql):
    return re.sub(r"\s+", " ", str(sql)).strip()
