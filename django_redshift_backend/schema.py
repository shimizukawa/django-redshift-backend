import copy
from datetime import date, datetime, time
from decimal import Decimal
import re
from uuid import UUID

from django.conf import settings
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.backends.ddl_references import Statement
from django.core.exceptions import FieldDoesNotExist
from django.db.models import NOT_PROVIDED, UniqueConstraint, Value
from django.db.utils import NotSupportedError, ProgrammingError

from .meta import DistKey, SortKey


class DatabaseSchemaEditor(BaseDatabaseSchemaEditor):
    sql_create_table = "CREATE TABLE %(table)s (%(definition)s)"
    sql_create_column = "ALTER TABLE %(table)s ADD COLUMN %(column)s %(definition)s"
    sql_delete_column = "ALTER TABLE %(table)s DROP COLUMN %(column)s CASCADE"
    sql_alter_column_type = "ALTER TABLE %(table)s ALTER COLUMN %(column)s TYPE %(type)s"
    sql_delete_fk = "ALTER TABLE %(table)s DROP CONSTRAINT %(name)s"
    sql_alter_distkey = "ALTER TABLE %(table)s ALTER DISTKEY %(column)s"
    sql_remove_distkey = "ALTER TABLE %(table)s ALTER DISTSTYLE AUTO"

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

    def _validate_distkey(self, model, index):
        if len(index.fields) != 1:
            raise ValueError(
                f"DistKey on model {model.__name__} must have exactly one field."
            )
        return self._column_name(model, index.fields[0])

    def add_index(self, model, index, concurrently=False):
        if not isinstance(index, DistKey):
            raise NotSupportedError(
                f"Amazon Redshift does not support index {index.name!r}."
            )
        self.execute(
            self.sql_alter_distkey
            % {
                "table": self.quote_name(model._meta.db_table),
                "column": self._validate_distkey(model, index),
            }
        )

    def remove_index(self, model, index, concurrently=False):
        if not isinstance(index, DistKey):
            raise NotSupportedError(
                f"Amazon Redshift does not support index {index.name!r}."
            )
        self._validate_distkey(model, index)
        self.execute(
            self.sql_remove_distkey
            % {"table": self.quote_name(model._meta.db_table)}
        )

    def _validate_supported_constraint(self, constraint):
        supported = (
            isinstance(constraint, UniqueConstraint)
            and bool(constraint.fields)
            and not constraint.expressions
            and constraint.condition is None
            and not constraint.include
            and not constraint.opclasses
            and getattr(constraint, "nulls_distinct", None) is None
        )
        if not supported:
            raise NotSupportedError(
                f"Amazon Redshift does not support constraint {constraint.name!r}."
            )

    def _validate_model_constraints(self, model):
        for constraint in model._meta.constraints:
            self._validate_supported_constraint(constraint)

    def add_constraint(self, model, constraint):
        self._validate_supported_constraint(constraint)
        super().add_constraint(model, constraint)

    def remove_constraint(self, model, constraint):
        self._validate_supported_constraint(constraint)
        super().remove_constraint(model, constraint)

    def alter_index_together(self, model, old_index_together, new_index_together):
        if set(old_index_together) != set(new_index_together):
            raise NotSupportedError(
                f"Amazon Redshift does not support index_together on {model._meta.label}."
            )

    def _informational_fk_sql(self, model, field):
        return self._create_fk_sql(
            model,
            field,
            "_fk_%(to_table)s_%(to_column)s",
        )

    def _has_db_default(self, field):
        has_db_default = getattr(field, "has_db_default", None)
        return bool(has_db_default and has_db_default())

    def _literal_db_default(self, field):
        if not self._has_db_default(field):
            return False
        return isinstance(field._db_default_expression, Value)

    def _has_usable_add_default(self, field):
        if self._literal_db_default(field):
            return field._db_default_expression.value is not None
        return (
            field.default is not NOT_PROVIDED
            and not callable(field.default)
            and self.effective_default(field) is not None
        )

    def _column_for_add(self, field):
        column_field = copy.copy(field)
        column_field._unique = False
        column_field.primary_key = False
        return column_field

    def add_field(self, model, field):
        if field.many_to_many and field.remote_field.through._meta.auto_created:
            return self.create_model(field.remote_field.through)
        if field.get_internal_type() in {"AutoField", "BigAutoField", "SmallAutoField"}:
            raise NotSupportedError("Amazon Redshift cannot add an IDENTITY column.")
        self._validate_field_ddl(field)
        if field.default is not NOT_PROVIDED and callable(field.default):
            raise NotSupportedError("Amazon Redshift cannot add a field with a callable default.")
        if self._has_db_default(field) and not self._literal_db_default(field):
            raise NotSupportedError("Amazon Redshift expression db_default is unsupported.")
        if not field.null and not self._has_usable_add_default(field):
            raise NotSupportedError(
                f"Cannot add non-null field {model._meta.label}.{field.name} "
                "without a literal default."
            )
        definition, params = self.column_sql(
            model,
            self._column_for_add(field),
            include_default=True,
        )
        self.execute(
            self.sql_create_column
            % {
                "table": self.quote_name(model._meta.db_table),
                "column": self.quote_name(field.column),
                "definition": definition,
            },
            params,
        )
        if field.unique:
            self.execute(self._create_unique_sql(model, [field]))
        if field.remote_field and field.db_constraint:
            self.execute(self._informational_fk_sql(model, field))

    _varchar_re = re.compile(r"^varchar\((\d+)\)$", re.IGNORECASE)

    def _varchar_length(self, db_type):
        match = self._varchar_re.fullmatch(db_type or "")
        return int(match.group(1)) if match else None

    def _relation_signature(self, field):
        if field.remote_field is None:
            return None
        target = field.remote_field.model
        target_meta = getattr(target, "_meta", None)
        target_label = target_meta.label_lower if target_meta else str(target)
        return target_label, field.remote_field.field_name

    def _has_constrained_incoming_fk(self, model, field):
        return any(
            relation.field.db_constraint
            and relation.field.target_field.column == field.column
            for relation in model._meta.related_objects
        )

    def _can_alter_varchar_directly(
        self,
        model,
        old_field,
        new_field,
        old_type,
        new_type,
    ):
        old_length = self._varchar_length(old_type)
        new_length = self._varchar_length(new_type)
        return (
            old_length is not None
            and new_length is not None
            and new_length >= old_length
            and old_field.null == new_field.null
            and old_field.unique == new_field.unique
            and old_field.primary_key == new_field.primary_key
            and not self._has_db_default(old_field)
            and not self._has_db_default(new_field)
            and self._relation_signature(old_field)
            == self._relation_signature(new_field)
            and getattr(old_field, "db_constraint", None)
            == getattr(new_field, "db_constraint", None)
            and not (old_field.remote_field and old_field.db_constraint)
            and not self._has_constrained_incoming_fk(model, old_field)
        )

    def _conversion_sql(self, old_field, new_field):
        old_column = self.quote_name(old_field.column)
        old_kind = old_field.get_internal_type()
        new_kind = new_field.get_internal_type()
        if old_kind == "BinaryField" and new_kind != "BinaryField":
            return f"{old_column}::varchar"
        if old_kind != "BinaryField" and new_kind == "BinaryField":
            return f"{old_column}::varbyte"
        return old_column

    def _resolve_table_key_column(self, model, declaration):
        key_name = declaration.removeprefix("-")
        for field in model._meta.local_fields:
            if key_name in {field.name, field.attname, field.column}:
                return field.column
        raise NotSupportedError(
            f"Cannot resolve Redshift table-key declaration {declaration!r} "
            f"on {model._meta.label}."
        )

    def _table_key_columns(self, model):
        declarations = [
            value
            for value in model._meta.ordering
            if isinstance(value, SortKey)
        ]
        declarations.extend(
            field_name
            for index in model._meta.indexes
            if isinstance(index, DistKey)
            for field_name in index.fields
        )
        return {
            self._resolve_table_key_column(model, declaration)
            for declaration in declarations
        }

    def _recreate_state_constraints(self, model, field):
        if field.primary_key:
            self.execute(self._create_primary_key_sql(model, field))
        elif field.unique:
            self.execute(self._create_unique_sql(model, [field]))
        for fields in model._meta.unique_together:
            if field.name in fields:
                unique_fields = [model._meta.get_field(name) for name in fields]
                self.execute(self._create_unique_sql(model, unique_fields))
        for constraint in model._meta.constraints:
            if isinstance(constraint, UniqueConstraint) and field.name in constraint.fields:
                self._validate_supported_constraint(constraint)
                self.execute(constraint.create_sql(model, self))
        if field.remote_field and field.db_constraint:
            self.execute(self._informational_fk_sql(model, field))
        for relation in model._meta.related_objects:
            related_field = relation.field
            if (
                related_field.db_constraint
                and related_field.target_field.name == field.name
            ):
                self.execute(
                    self._informational_fk_sql(relation.related_model, related_field)
                )

    def _validate_recreation(self, model, old_field, new_field):
        if getattr(new_field, "generated", False):
            raise NotSupportedError("Amazon Redshift generated fields are unsupported.")
        if self._has_db_default(new_field) and not self._literal_db_default(new_field):
            raise NotSupportedError("Amazon Redshift expression db_default is unsupported.")
        if not new_field.null and not self._has_usable_add_default(new_field):
            raise NotSupportedError(
                f"Cannot recreate non-null field {model._meta.label}.{new_field.name} "
                "without a literal default."
            )
        if old_field.column in self._table_key_columns(model):
            raise NotSupportedError(
                f"Cannot recreate Redshift table-key field "
                f"{model._meta.label}.{new_field.name}."
            )
        for constraint in model._meta.constraints:
            if isinstance(constraint, UniqueConstraint) and new_field.name in constraint.fields:
                self._validate_supported_constraint(constraint)

    def _recreate_column(self, model, old_field, new_field):
        self._validate_recreation(model, old_field, new_field)
        temporary = self._column_for_add(new_field)
        temporary.column = f"{new_field.column}_tmp"
        definition, params = self.column_sql(model, temporary, include_default=True)
        self.execute(
            self.sql_create_column
            % {
                "table": self.quote_name(model._meta.db_table),
                "column": self.quote_name(temporary.column),
                "definition": definition,
            },
            params,
        )
        self.execute(
            "UPDATE %(table)s SET %(temporary)s = %(value)s "
            "WHERE %(old)s IS NOT NULL"
            % {
                "table": self.quote_name(model._meta.db_table),
                "temporary": self.quote_name(temporary.column),
                "value": self._conversion_sql(old_field, new_field),
                "old": self.quote_name(old_field.column),
            }
        )
        self.execute(
            self.sql_delete_column
            % {
                "table": self.quote_name(model._meta.db_table),
                "column": self.quote_name(old_field.column),
            }
        )
        self.execute(
            self.sql_rename_column
            % {
                "table": self.quote_name(model._meta.db_table),
                "old_column": self.quote_name(temporary.column),
                "new_column": self.quote_name(new_field.column),
                "type": new_field.db_parameters(connection=self.connection)["type"],
            }
        )
        self._recreate_state_constraints(model, new_field)

    def _alter_field(
        self,
        model,
        old_field,
        new_field,
        old_type,
        new_type,
        old_db_params,
        new_db_params,
        strict=False,
    ):
        direct_varchar_change = self._can_alter_varchar_directly(
            model,
            old_field,
            new_field,
            old_type,
            new_type,
        )
        physical_change = (
            old_type != new_type
            or old_field.null != new_field.null
            or old_field.unique != new_field.unique
            or old_field.primary_key != new_field.primary_key
            or self._has_db_default(old_field) != self._has_db_default(new_field)
            or (
                self._has_db_default(old_field)
                and old_field.db_default != new_field.db_default
            )
            or (
                bool(old_field.remote_field) != bool(new_field.remote_field)
                or getattr(old_field, "db_constraint", None)
                != getattr(new_field, "db_constraint", None)
            )
        )
        if physical_change and not direct_varchar_change:
            self._validate_recreation(model, old_field, new_field)
        if old_field.column != new_field.column:
            self.execute(
                self._rename_field_sql(
                    model._meta.db_table,
                    old_field,
                    new_field,
                    new_type,
                )
            )
            for sql in self.deferred_sql:
                if isinstance(sql, Statement):
                    sql.rename_column_references(
                        model._meta.db_table,
                        old_field.column,
                        new_field.column,
                    )
            old_field = copy.copy(old_field)
            old_field.column = new_field.column
        if direct_varchar_change:
            if old_type != new_type:
                self.execute(
                    self.sql_alter_column_type
                    % {
                        "table": self.quote_name(model._meta.db_table),
                        "column": self.quote_name(new_field.column),
                        "type": new_type,
                    }
                )
            return
        if physical_change:
            self._recreate_column(model, old_field, new_field)

    def remove_field(self, model, field):
        try:
            return super().remove_field(model, field)
        except ProgrammingError as error:
            if "cannot drop sortkey" not in str(error).lower():
                raise
            if self.connection.errors_occurred:
                self.connection.close()
                self.connection.connect()
            self.execute(
                "ALTER TABLE %(table)s ALTER SORTKEY NONE"
                % {"table": self.quote_name(model._meta.db_table)}
            )
            return super().remove_field(model, field)

    def create_model(self, model):
        self._validate_model_ddl(model)
        self._validate_model_constraints(model)
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
