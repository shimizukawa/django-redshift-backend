import ipaddress
import json
import uuid
from types import SimpleNamespace

import pytest
from django.core.management.color import no_style
from django.db.models import IntegerField
from django.db.utils import NotSupportedError

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


def operations():
    return DatabaseWrapper(settings_dict(), "operations-contract").ops


class FakeCursor:
    def __init__(self, row=(42,)):
        self.row = row
        self.calls = []

    def execute(self, sql):
        self.calls.append(sql)

    def fetchone(self):
        return self.row


def test_quote_name_quotes_once():
    ops = operations()
    assert ops.quote_name("event") == '"event"'
    assert ops.quote_name('"event"') == '"event"'


def test_plain_distinct_is_supported():
    assert operations().distinct_sql([], []) == (["DISTINCT"], [])


def test_field_specific_distinct_remains_unsupported():
    with pytest.raises(NotSupportedError, match="DISTINCT ON fields"):
        operations().distinct_sql(['"event"."kind"'], [[]])


def test_last_insert_id_preserves_quoted_max_workaround():
    cursor = FakeCursor()
    result = operations().last_insert_id(cursor, "event table", "event id")
    assert result == 42
    assert cursor.calls == ['SELECT MAX("event id") FROM "event table"']


def test_select_for_update_is_explicitly_unsupported():
    with pytest.raises(NotSupportedError, match="SELECT FOR UPDATE"):
        operations().for_update_sql(
            nowait=True,
            skip_locked=True,
            of=('"event"',),
            no_key=True,
        )


def test_sequence_and_deferrable_operations_are_empty():
    ops = operations()
    assert ops.sequence_reset_sql(no_style(), []) == []
    assert ops.sequence_reset_by_name_sql(no_style(), []) == []
    assert ops.deferrable_sql() == ""


def test_compatibility_name_limit_is_preserved():
    assert operations().max_name_length() == 63


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, value):
        if isinstance(value, set):
            return sorted(value)
        return super().default(value)


def test_json_integer_and_ip_values_use_driver_neutral_types():
    ops = operations()
    assert ops.adapt_integerfield_value(7, "IntegerField") == 7
    assert ops.adapt_json_value({"values": {2, 1}}, CustomJSONEncoder) == (
        '{"values": [1, 2]}'
    )
    assert ops.adapt_ipaddressfield_value(ipaddress.ip_address("192.0.2.1")) == (
        "192.0.2.1"
    )
    assert ops.adapt_ipaddressfield_value("") is None


def test_uuid_converter_accepts_text_uuid_and_none():
    ops = operations()
    value = uuid.uuid4()
    expression = SimpleNamespace(
        output_field=SimpleNamespace(get_internal_type=lambda: "UUIDField")
    )
    converters = ops.get_db_converters(expression)
    assert ops.convert_uuidfield_value in converters
    assert ops.convert_uuidfield_value(str(value), expression, ops.connection) == value
    assert ops.convert_uuidfield_value(value, expression, ops.connection) == value
    assert ops.convert_uuidfield_value(None, expression, ops.connection) is None


def test_non_uuid_expression_has_no_redshift_converter():
    expression = SimpleNamespace(output_field=IntegerField())
    assert operations().get_db_converters(expression) == []


def test_bulk_insert_uses_multi_row_values_without_conflict_clause():
    sql = operations().bulk_insert_sql(
        [],
        [["%s", "%s"], ["%s", "%s"]],
    )
    assert sql == "VALUES (%s, %s), (%s, %s)"
    assert "CONFLICT" not in sql


def test_flush_uses_one_redshift_statement_per_table():
    sql = operations().sql_flush(
        no_style(),
        ["event", "event detail"],
        reset_sequences=True,
        allow_cascade=True,
    )
    assert sql == [
        'TRUNCATE TABLE "event";',
        'TRUNCATE TABLE "event detail";',
    ]
    assert all("RESTART IDENTITY" not in statement for statement in sql)
    assert all("CASCADE" not in statement for statement in sql)


def test_explain_supports_only_plain_and_verbose():
    ops = operations()
    assert ops.explain_query_prefix() == "EXPLAIN"
    assert ops.explain_query_prefix(verbose=True) == "EXPLAIN VERBOSE"
    with pytest.raises(ValueError, match="does not support any formats"):
        ops.explain_query_prefix(format="JSON")
    with pytest.raises(ValueError, match="Unknown options: ANALYZE"):
        ops.explain_query_prefix(analyze=True)


@pytest.mark.parametrize("internal_type", ["DateField", "DateTimeField", "TimeField"])
def test_temporal_subtraction_uses_microsecond_datediff(internal_type):
    ops = operations()
    sql, params = ops.subtract_temporals(
        internal_type,
        ("lhs_value + %s", (1,)),
        ("rhs_value + %s", (2,)),
    )
    assert sql == (
        "(INTERVAL '1 microsecond' * "
        "DATEDIFF(microsecond, (rhs_value + %s), (lhs_value + %s)))"
    )
    assert params == (2, 1)


def test_join_preparation_does_not_add_postgresql_casts():
    ops = operations()
    lhs_field = IntegerField()
    rhs_field = IntegerField()
    lhs, rhs = ops.prepare_join_on_clause("lhs", lhs_field, "rhs", rhs_field)
    assert lhs.alias == "lhs"
    assert lhs.target is lhs_field
    assert rhs.alias == "rhs"
    assert rhs.target is rhs_field


def test_default_compiler_remains_in_use():
    assert operations().compiler_module == "django.db.models.sql.compiler"
