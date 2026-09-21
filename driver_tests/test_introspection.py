from unittest import mock

from django_redshift_backend import _backend
from django_redshift_backend.introspection import (
    DatabaseIntrospection,
    FieldInfo,
    TableInfo,
)


def test_internal_backend_registers_redshift_introspection():
    assert issubclass(
        _backend.DatabaseWrapper.introspection_class,
        DatabaseIntrospection,
    )


def test_table_list_queries_redshift_catalog_and_preserves_comments():
    cursor = mock.Mock()
    cursor.fetchall.return_value = (
        ("orders", "BASE TABLE", "order facts"),
        ("spectrum_orders", "EXTERNAL TABLE", "external order facts"),
        ("order_summary", "VIEW", "summary"),
    )

    tables = DatabaseIntrospection(mock.Mock()).get_table_list(cursor)

    assert tables == [
        TableInfo("orders", "t", "order facts"),
        TableInfo("spectrum_orders", "t", "external order facts"),
        TableInfo("order_summary", "v", "summary"),
    ]
    sql = " ".join(cursor.execute.call_args.args[0].split())
    assert "FROM svv_tables" in sql
    assert "table_schema = current_schema()" in sql
    assert "table_type IN ('BASE TABLE', 'EXTERNAL TABLE', 'VIEW')" in sql


def test_column_description_maps_identity_and_nullability():
    cursor = mock.Mock()
    cursor.fetchone.return_value = ("analytics",)
    cursor.get_columns.return_value = (
        (
            "dev",
            "analytics",
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
    analytics_column = cursor.get_columns.return_value[0]
    cursor.get_columns.return_value = (
        (analytics_column[0], "public", *analytics_column[2:]),
        analytics_column,
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
    cursor.get_columns.assert_called_once_with(
        schema_pattern="analytics", tablename_pattern="orders"
    )
    cursor.execute.assert_called_once_with("SELECT current_schema()")


def test_constraints_group_primary_foreign_and_unique_metadata():
    cursor = mock.Mock()
    cursor.fetchone.return_value = ("analytics",)
    cursor.get_primary_keys.return_value = (
        ("dev", "analytics", "orders", "id", 1, "orders_pkey"),
    )
    cursor.get_imported_keys.return_value = (
        (
            "dev",
            "analytics",
            "customer",
            "id",
            "dev",
            "analytics",
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
    cursor.get_primary_keys.assert_called_once_with(schema="analytics", table="orders")
    cursor.get_imported_keys.assert_called_once_with(schema="analytics", table="orders")
    assert cursor.execute.call_args_list[0].args == ("SELECT current_schema()",)
    unique_sql, unique_params = cursor.execute.call_args_list[-1].args
    assert "tc.constraint_schema = %s" in " ".join(unique_sql.split())
    assert unique_params == ["analytics", "orders"]


def test_relations_include_no_on_delete_value_on_modern_django():
    cursor = mock.Mock()
    cursor.fetchone.return_value = ("analytics",)
    cursor.get_imported_keys.return_value = (
        (
            "dev",
            "analytics",
            "customer",
            "id",
            "dev",
            "analytics",
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
    cursor.get_imported_keys.assert_called_once_with(schema="analytics", table="orders")
    cursor.execute.assert_called_once_with("SELECT current_schema()")


def test_django42_selector_uses_removable_relation_adapter():
    assert _backend.introspection_class_for((4, 2)).__module__ == (
        "django_redshift_backend.introspection_django42"
    )
