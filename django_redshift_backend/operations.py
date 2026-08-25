import json
import re
import uuid

from django.conf import settings
from django.db.backends.base.operations import BaseDatabaseOperations
from django.db.backends.utils import split_tzname_delta
from django.db.models.expressions import Col
from django.db.utils import NotSupportedError


class DatabaseOperations(BaseDatabaseOperations):
    explain_prefix = "EXPLAIN"
    _extract_format_re = re.compile(r"[A-Z_]+\Z")

    def quote_name(self, name):
        if name.startswith('"') and name.endswith('"'):
            return name
        return f'"{name}"'

    def distinct_sql(self, fields, params):
        if fields:
            raise NotSupportedError(
                "DISTINCT ON fields is not supported by this database backend"
            )
        return ["DISTINCT"], []

    def last_insert_id(self, cursor, table_name, pk_name):
        """Return MAX(pk), preserving the existing non-concurrency-safe contract."""
        cursor.execute(
            f"SELECT MAX({self.quote_name(pk_name)}) "
            f"FROM {self.quote_name(table_name)}"
        )
        return cursor.fetchone()[0]

    def for_update_sql(self, nowait=False, skip_locked=False, of=(), no_key=False):
        raise NotSupportedError(
            "SELECT FOR UPDATE is not implemented for this database backend"
        )

    def sequence_reset_sql(self, style, model_list):
        return []

    def sequence_reset_by_name_sql(self, style, sequences):
        return []

    def deferrable_sql(self):
        return ""

    def max_name_length(self):
        return 63

    def get_db_converters(self, expression):
        converters = super().get_db_converters(expression)
        if expression.output_field.get_internal_type() == "UUIDField":
            converters.append(self.convert_uuidfield_value)
        return converters

    def convert_uuidfield_value(self, value, expression, connection):
        if value is not None and not isinstance(value, uuid.UUID):
            value = uuid.UUID(value)
        return value

    def adapt_integerfield_value(self, value, internal_type):
        return value

    def adapt_json_value(self, value, encoder):
        return json.dumps(value, cls=encoder)

    def adapt_ipaddressfield_value(self, value):
        return str(value) if value else None

    def bulk_insert_sql(self, fields, placeholder_rows):
        rows = (", ".join(row) for row in placeholder_rows)
        return "VALUES " + ", ".join(f"({row})" for row in rows)

    def sql_flush(self, style, tables, *, reset_sequences=False, allow_cascade=False):
        return [
            f"{style.SQL_KEYWORD('TRUNCATE TABLE')} "
            f"{style.SQL_FIELD(self.quote_name(table))};"
            for table in tables
        ]

    def explain_query_prefix(self, format=None, **options):
        if format:
            return super().explain_query_prefix(format=format, **options)
        normalized = {name.upper(): value for name, value in options.items()}
        unknown = sorted(set(normalized) - {"VERBOSE"})
        if unknown:
            raise ValueError(f"Unknown options: {', '.join(unknown)}")
        if normalized.get("VERBOSE"):
            return "EXPLAIN VERBOSE"
        return "EXPLAIN"

    def subtract_temporals(self, internal_type, lhs, rhs):
        lhs_sql, lhs_params = lhs
        rhs_sql, rhs_params = rhs
        params = (*lhs_params, *rhs_params)
        difference = f"({lhs_sql}) - ({rhs_sql})"
        if internal_type == "DateField":
            return f"(INTERVAL '1 day' * ({difference}))", params
        return f"({difference})", params

    def prepare_join_on_clause(self, lhs_table, lhs_field, rhs_table, rhs_field):
        return Col(lhs_table, lhs_field), Col(rhs_table, rhs_field)

    def _validated_date_part(self, lookup_type):
        date_part = lookup_type.upper()
        if not self._extract_format_re.fullmatch(date_part):
            raise ValueError("Unsupported date part identifier.")
        return date_part

    def _prepare_tzname_delta(self, tzname):
        tzname, sign, offset = split_tzname_delta(tzname)
        if offset:
            sign = "-" if sign == "+" else "+"
            return f"{tzname}{sign}{offset}"
        return tzname

    def _convert_sql_to_tz(self, sql, params, tzname):
        if tzname and settings.USE_TZ:
            return (
                f"{sql} AT TIME ZONE %s",
                (*params, self._prepare_tzname_delta(tzname)),
            )
        return sql, tuple(params)

    def date_extract_sql(self, lookup_type, sql, params):
        if lookup_type == "week_day":
            return f"EXTRACT(DOW FROM {sql}) + 1", params
        if lookup_type == "iso_week_day":
            return f"MOD(EXTRACT(DOW FROM {sql}) + 6, 7) + 1", params
        if lookup_type == "iso_year":
            return (
                "EXTRACT(YEAR FROM " f"DATE_TRUNC('week', {sql}) + INTERVAL '3 day')",
                params,
            )
        date_part = self._validated_date_part(lookup_type)
        return f"EXTRACT({date_part} FROM {sql})", params

    def date_trunc_sql(self, lookup_type, sql, params, tzname=None):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return f"DATE_TRUNC(%s, {sql})", (lookup_type, *params)

    def datetime_cast_date_sql(self, sql, params, tzname):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return f"({sql})::date", params

    def datetime_cast_time_sql(self, sql, params, tzname):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return f"({sql})::time", params

    def datetime_extract_sql(self, lookup_type, sql, params, tzname):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return self.date_extract_sql(lookup_type, sql, params)

    def datetime_trunc_sql(self, lookup_type, sql, params, tzname):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return f"DATE_TRUNC(%s, {sql})", (lookup_type, *params)

    def time_extract_sql(self, lookup_type, sql, params):
        return self.date_extract_sql(lookup_type, sql, params)

    def time_trunc_sql(self, lookup_type, sql, params, tzname=None):
        sql, params = self._convert_sql_to_tz(sql, params, tzname)
        return f"DATE_TRUNC(%s, {sql})::time", (lookup_type, *params)
