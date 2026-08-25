from datetime import date, datetime, time
from decimal import Decimal
import re
from uuid import UUID

from django.conf import settings
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


class DatabaseSchemaEditor(BaseDatabaseSchemaEditor):
    sql_create_table = "CREATE TABLE %(table)s (%(definition)s)"
    sql_delete_column = "ALTER TABLE %(table)s DROP COLUMN %(column)s CASCADE"
    sql_delete_fk = "ALTER TABLE %(table)s DROP CONSTRAINT %(name)s"

    @property
    def multiply_varchar_length(self):
        return int(getattr(settings, "REDSHIFT_VARCHAR_LENGTH_MULTIPLIER", 1))

    def column_sql(self, *args, **kwargs):
        definition, params = super().column_sql(*args, **kwargs)
        return self._multiply_bounded_varchar_lengths(definition), params

    def _multiply_bounded_varchar_lengths(self, definition):
        if definition is None:
            return None

        def replace(match):
            length = int(match.group(1)) * self.multiply_varchar_length
            return f"varchar({length})"

        return re.sub(r"varchar\((\d+)\)", replace, definition)

    def quote_value(self, value):
        if value is None:
            return "NULL"
        if value is True:
            return "TRUE"
        if value is False:
            return "FALSE"
        if isinstance(value, bytes):
            return f"to_varbyte('{value.hex()}', 'hex')"
        if isinstance(value, (date, datetime, time, UUID)):
            value = value.isoformat() if hasattr(value, "isoformat") else str(value)
            return "'{}'".format(value.replace("'", "''").replace("%", "%%"))
        if isinstance(value, str):
            return "'{}'".format(value.replace("'", "''").replace("%", "%%"))
        if isinstance(value, (int, float, Decimal)):
            return str(value)
        raise ValueError(f"Cannot render {type(value).__name__} as Redshift DDL")
