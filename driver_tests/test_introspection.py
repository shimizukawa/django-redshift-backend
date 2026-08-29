from unittest import mock

from django_redshift_backend import _backend
from django_redshift_backend.introspection import (
    DatabaseIntrospection,
    FieldInfo,
    TableInfo,
)


def test_internal_backend_registers_redshift_introspection():
    assert _backend.DatabaseWrapper.introspection_class.__module__ == (
        "django_redshift_backend.introspection"
    )


def test_table_list_uses_driver_metadata_and_preserves_comments():
    cursor = mock.Mock()
    cursor.get_tables.return_value = (
        ("dev", "public", "orders", "TABLE", "order facts"),
        ("dev", "public", "order_summary", "VIEW", "summary"),
    )

    tables = DatabaseIntrospection(mock.Mock()).get_table_list(cursor)

    assert tables == [
        TableInfo("orders", "t", "order facts"),
        TableInfo("order_summary", "v", "summary"),
    ]
    cursor.get_tables.assert_called_once_with(types=["TABLE", "VIEW"])


def test_column_description_maps_identity_and_nullability():
    cursor = mock.Mock()
    cursor.get_columns.return_value = (
        (
            "dev",
            "public",
            "orders",
            "id",
            4,
            "int4",
            10,
            None,
            0,
            10,
            0,
            "primary key",
            "identity(1,1)",
            4,
            None,
            None,
            1,
            "NO",
            None,
            None,
            None,
            None,
            "YES",
            "NO",
            None,
            0,
            0,
            "az64",
            None,
        ),
    )

    columns = DatabaseIntrospection(mock.Mock()).get_table_description(
        cursor, "orders"
    )

    assert columns == [
        FieldInfo(
            "id",
            "int4",
            10,
            None,
            10,
            0,
            False,
            "identity(1,1)",
            None,
            True,
            "primary key",
        )
    ]
    cursor.get_columns.assert_called_once_with(tablename_pattern="orders")
