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
