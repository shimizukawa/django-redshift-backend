from datetime import date, datetime, time
from decimal import Decimal
import re
from uuid import UUID

from django.conf import settings
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.core.exceptions import FieldDoesNotExist
from django.db.utils import NotSupportedError

from .meta import DistKey, SortKey


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

    def _column_name(self, model, field_name):
        normalized = field_name.removeprefix("-")
        try:
            field = model._meta.get_field(normalized)
        except FieldDoesNotExist:
            column = normalized
        else:
            column = field.get_attname_column()[1]
        return self.quote_name(column)

    def _validate_field_ddl(self, field):
        unsupported = {
            "tablespace": getattr(field, "db_tablespace", None),
            "comment": getattr(field, "db_comment", None),
            "collation": getattr(field, "db_collation", None),
            "generated column": getattr(field, "generated", False),
        }
        for label, value in unsupported.items():
            if value:
                raise NotSupportedError(
                    f"Amazon Redshift does not support {label} on {field.name}."
                )

    def _validate_model_ddl(self, model):
        if model._meta.db_tablespace:
            raise NotSupportedError(
                f"Amazon Redshift does not support tablespace on {model._meta.label}."
            )
        if getattr(model._meta, "db_table_comment", None):
            raise NotSupportedError(
                f"Amazon Redshift does not support table comments on {model._meta.label}."
            )
        for field in model._meta.local_fields:
            self._validate_field_ddl(field)

    def _validate_create_options(self, model):
        distkeys = [index for index in model._meta.indexes if isinstance(index, DistKey)]
        if len(distkeys) > 1:
            raise ValueError(f"Model {model.__name__} has more than one DistKey.")
        distkey_column = None
        if distkeys:
            if len(distkeys[0].fields) != 1:
                raise ValueError(
                    f"DistKey on model {model.__name__} must have exactly one field."
                )
            distkey_column = self._column_name(model, distkeys[0].fields[0])
        sortkeys = [
            self._column_name(model, value)
            for value in model._meta.ordering
            if isinstance(value, SortKey)
        ]
        return distkey_column, sortkeys

    def _get_create_options(self, model):
        distkey_column, sortkeys = self._validate_create_options(model)
        options = []
        if distkey_column:
            options.append(f"DISTKEY({distkey_column})")
        if sortkeys:
            options.append(f"SORTKEY({', '.join(sortkeys)})")
        return " ".join(options)

    def table_sql(self, model):
        sql, params = super().table_sql(model)
        options = self._get_create_options(model)
        if options:
            sql = f"{sql} {options}"
        return sql, params

    def _validate_model_indexes(self, model):
        for index in model._meta.indexes:
            if not isinstance(index, DistKey):
                raise NotSupportedError(
                    f"Amazon Redshift does not support index {index.name!r}."
                )

    def _model_indexes_sql(self, model):
        self._validate_model_indexes(model)
        return []

    def _informational_fk_sql(self, model, field):
        return self._create_fk_sql(
            model,
            field,
            "_fk_%(to_table)s_%(to_column)s",
        )

    def create_model(self, model):
        self._validate_model_ddl(model)
        self._validate_model_indexes(model)
        self._validate_create_options(model)
        super().create_model(model)
        for field in model._meta.local_fields:
            if field.remote_field and field.db_constraint:
                self.deferred_sql.append(self._informational_fk_sql(model, field))

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
