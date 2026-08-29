from django.test import override_settings

from django_redshift_backend._backend import DatabaseWrapper
from django_redshift_backend.operations import DatabaseOperations


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


def operations():
    return DatabaseWrapper(settings_dict(), "datetime-contract").ops


def test_internal_wrapper_registers_redshift_operations():
    wrapper = DatabaseWrapper(settings_dict(), "datetime-contract")
    assert wrapper.ops_class is DatabaseOperations
    assert isinstance(wrapper.ops, DatabaseOperations)


def test_date_extract_preserves_params():
    sql, params = operations().date_extract_sql("month", "event_time + %s", (7,))
    assert sql == "EXTRACT(MONTH FROM event_time + %s)"
    assert params == (7,)


def test_django_weekday_numbering_uses_documented_dow():
    sql, params = operations().date_extract_sql("week_day", "event_time", ())
    assert sql == "EXTRACT(DOW FROM event_time) + 1"
    assert params == ()


def test_iso_weekday_uses_documented_dow_composition():
    sql, params = operations().date_extract_sql("iso_week_day", "event_time", ())
    assert sql == "MOD(EXTRACT(DOW FROM event_time) + 6, 7) + 1"
    assert params == ()


def test_iso_year_uses_week_thursday():
    sql, params = operations().date_extract_sql("iso_year", "event_time", ())
    assert sql == (
        "EXTRACT(YEAR FROM DATE_TRUNC('week', event_time) + INTERVAL '3 day')"
    )
    assert params == ()


def test_date_extract_rejects_untrusted_lookup():
    try:
        operations().date_extract_sql("year); DROP TABLE x; --", "event_time", ())
    except ValueError as error:
        assert str(error) == "Unsupported date part identifier."
    else:
        raise AssertionError("invalid date part was accepted")


def test_date_trunc_parameterizes_date_part():
    sql, params = operations().date_trunc_sql("day", "event_time + %s", (7,))
    assert sql == "DATE_TRUNC(%s, event_time + %s)"
    assert params == ("day", 7)


@override_settings(USE_TZ=True)
def test_datetime_trunc_parameterizes_timezone():
    sql, params = operations().datetime_trunc_sql(
        "hour", "event_time + %s", (7,), "Asia/Tokyo"
    )
    assert sql == "DATE_TRUNC(%s, event_time + %s AT TIME ZONE %s)"
    assert params == ("hour", 7, "Asia/Tokyo")


@override_settings(USE_TZ=True)
def test_datetime_casts_preserve_timezone_params():
    ops = operations()
    date_sql, date_params = ops.datetime_cast_date_sql(
        "event_time", (), "Asia/Tokyo"
    )
    time_sql, time_params = ops.datetime_cast_time_sql(
        "event_time", (), "Asia/Tokyo"
    )
    assert date_sql == "(event_time AT TIME ZONE %s)::date"
    assert date_params == ("Asia/Tokyo",)
    assert time_sql == "(event_time AT TIME ZONE %s)::time"
    assert time_params == ("Asia/Tokyo",)


def test_time_extract_and_trunc_use_modern_signatures():
    ops = operations()
    extract_sql, extract_params = ops.time_extract_sql("minute", "event_time", ())
    trunc_sql, trunc_params = ops.time_trunc_sql("minute", "event_time", ())
    assert extract_sql == "EXTRACT(MINUTE FROM event_time)"
    assert extract_params == ()
    assert trunc_sql == "DATE_TRUNC(%s, event_time)::time"
    assert trunc_params == ("minute",)
