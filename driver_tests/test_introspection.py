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

    columns = DatabaseIntrospection(mock.Mock()).get_table_description(cursor, "orders")

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


def test_constraints_group_primary_foreign_and_unique_metadata():
    cursor = mock.Mock()
    cursor.get_primary_keys.return_value = (
        ("dev", "public", "orders", "id", 1, "orders_pkey"),
    )
    cursor.get_imported_keys.return_value = (
        (
            "dev",
            "public",
            "customer",
            "id",
            "dev",
            "public",
            "orders",
            "customer_id",
            1,
            3,
            3,
            "orders_customer_fk",
            "customer_pkey",
            7,
        ),
    )
    cursor.fetchall.return_value = [("orders_code_key", "code", 1)]

    constraints = DatabaseIntrospection(mock.Mock()).get_constraints(cursor, "orders")

    assert constraints["orders_pkey"]["primary_key"] is True
    assert constraints["orders_pkey"]["columns"] == ["id"]
    assert constraints["orders_customer_fk"]["foreign_key"] == ("customer", "id")
    assert constraints["orders_code_key"]["unique"] is True
    cursor.get_primary_keys.assert_called_once_with(table="orders")
    cursor.get_imported_keys.assert_called_once_with(table="orders")


def test_relations_include_no_on_delete_value_on_modern_django():
    cursor = mock.Mock()
    cursor.get_imported_keys.return_value = (
        (
            "dev",
            "public",
            "customer",
            "id",
            "dev",
            "public",
            "orders",
            "customer_id",
            1,
            3,
            3,
            "orders_customer_fk",
            "customer_pkey",
            7,
        ),
    )

    relations = DatabaseIntrospection(mock.Mock()).get_relations(cursor, "orders")

    assert relations == {"customer_id": ("id", "customer", None)}


def test_django42_selector_uses_removable_relation_adapter():
    assert _backend.introspection_class_for((4, 2)).__module__ == (
        "django_redshift_backend.introspection_django42"
    )
