import re

from django.conf import settings
from django.db.backends.base.operations import BaseDatabaseOperations
from django.db.backends.utils import split_tzname_delta


class DatabaseOperations(BaseDatabaseOperations):
    _extract_format_re = re.compile(r"[A-Z_]+\Z")

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
                "EXTRACT(YEAR FROM "
                f"DATE_TRUNC('week', {sql}) + INTERVAL '3 day')",
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
