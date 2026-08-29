from collections import namedtuple

from django.db.backends.base.introspection import (
    BaseDatabaseIntrospection,
)
from django.db.backends.base.introspection import (
    FieldInfo as BaseFieldInfo,
)
from django.db.backends.base.introspection import (
    TableInfo as BaseTableInfo,
)

FieldInfo = namedtuple("FieldInfo", [*BaseFieldInfo._fields, "is_autofield", "comment"])
TableInfo = namedtuple("TableInfo", [*BaseTableInfo._fields, "comment"])


class DatabaseIntrospection(BaseDatabaseIntrospection):
    data_types_reverse = {
        "bool": "BooleanField",
        "boolean": "BooleanField",
        "int2": "SmallIntegerField",
        "smallint": "SmallIntegerField",
        "int4": "IntegerField",
        "integer": "IntegerField",
        "int8": "BigIntegerField",
        "bigint": "BigIntegerField",
        "float4": "FloatField",
        "real": "FloatField",
        "float8": "FloatField",
        "double precision": "FloatField",
        "char": "CharField",
        "character": "CharField",
        "bpchar": "CharField",
        "varchar": "CharField",
        "character varying": "CharField",
        "text": "TextField",
        "numeric": "DecimalField",
        "decimal": "DecimalField",
        "date": "DateField",
        "time": "TimeField",
        "timetz": "TimeField",
        "timestamp": "DateTimeField",
        "timestamptz": "DateTimeField",
        "intervaly2m": "DurationField",
        "intervald2s": "DurationField",
        "interval": "DurationField",
        "varbyte": "BinaryField",
    }

    def get_field_type(self, data_type, description):
        field_type = super().get_field_type(data_type, description)
        if description.is_autofield:
            if field_type == "IntegerField":
                return "AutoField"
            if field_type == "BigIntegerField":
                return "BigAutoField"
            if field_type == "SmallIntegerField":
                return "SmallAutoField"
        return field_type

    def get_table_list(self, cursor):
        table_types = {"TABLE": "t", "VIEW": "v"}
        return [
            TableInfo(row[2], table_types[row[3]], row[4])
            for row in cursor.get_tables(types=["TABLE", "VIEW"])
            if row[3] in table_types
        ]

    def get_table_description(self, cursor, table_name):
        return [
            FieldInfo(
                row[3],
                row[5],
                row[6],
                row[15],
                row[6],
                row[8],
                row[17] == "YES",
                row[12],
                row[28],
                row[22] == "YES",
                row[11],
            )
            for row in cursor.get_columns(tablename_pattern=table_name)
        ]

    @staticmethod
    def _constraint(columns, *, primary_key=False, unique=False, foreign_key=None):
        return {
            "columns": columns,
            "primary_key": primary_key,
            "unique": unique,
            "foreign_key": foreign_key,
            "check": False,
            "index": False,
            "definition": None,
            "options": None,
        }

    def _primary_key_constraints(self, cursor, table_name):
        constraints = {}
        for (
            _catalog,
            _schema,
            _table,
            column,
            position,
            name,
        ) in cursor.get_primary_keys(table=table_name):
            constraints.setdefault(name, []).append((position, column))
        return {
            name: self._constraint(
                [column for _position, column in sorted(columns)],
                primary_key=True,
                unique=True,
            )
            for name, columns in constraints.items()
        }

    def _foreign_key_rows(self, cursor, table_name):
        return cursor.get_imported_keys(table=table_name)

    def _foreign_key_constraints(self, cursor, table_name):
        constraints = {}
        for row in self._foreign_key_rows(cursor, table_name):
            target_table, target_column = row[2], row[3]
            column, position, name = row[7], row[8], row[11]
            constraints.setdefault(name, []).append(
                (position, column, target_table, target_column)
            )
        return {
            name: self._constraint(
                [column for _position, column, _table, _target in sorted(columns)],
                foreign_key=(columns[0][2], columns[0][3]),
            )
            for name, columns in constraints.items()
        }

    def _unique_constraints(self, cursor, table_name):
        cursor.execute(
            """
            SELECT tc.constraint_name, kcu.column_name, kcu.ordinal_position
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_catalog = kcu.constraint_catalog
             AND tc.constraint_schema = kcu.constraint_schema
             AND tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = %s AND tc.constraint_type = 'UNIQUE'
            ORDER BY tc.constraint_name, kcu.ordinal_position
            """,
            [table_name],
        )
        constraints = {}
        for name, column, position in cursor.fetchall():
            constraints.setdefault(name, []).append((position, column))
        return {
            name: self._constraint(
                [column for _position, column in sorted(columns)], unique=True
            )
            for name, columns in constraints.items()
        }

    def get_constraints(self, cursor, table_name):
        constraints = self._primary_key_constraints(cursor, table_name)
        constraints.update(self._foreign_key_constraints(cursor, table_name))
        constraints.update(self._unique_constraints(cursor, table_name))
        return constraints

    def get_relations(self, cursor, table_name):
        return {
            row[7]: (row[3], row[2], None)
            for row in self._foreign_key_rows(cursor, table_name)
        }

    def get_sequences(self, cursor, table_name, table_fields=()):
        return []
