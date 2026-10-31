import inspect

import redshift_connector


def parameter_names(member):
    return tuple(inspect.signature(member).parameters)


def test_connection_exposes_required_synchronous_methods():
    connection = redshift_connector.Connection
    assert parameter_names(connection.cursor) == ("self",)
    assert parameter_names(connection.commit) == ("self",)
    assert parameter_names(connection.rollback) == ("self",)
    assert parameter_names(connection.close) == ("self",)
    assert parameter_names(connection.__enter__) == ("self",)
    assert parameter_names(connection.__exit__) == (
        "self",
        "exc_type",
        "exc_value",
        "traceback",
    )


def test_cursor_exposes_required_dbapi_surface():
    cursor = redshift_connector.Cursor
    assert parameter_names(cursor.execute)[:3] == ("self", "operation", "args")
    assert parameter_names(cursor.executemany) == ("self", "operation", "param_sets")
    assert parameter_names(cursor.fetchone) == ("self",)
    assert parameter_names(cursor.fetchmany) == ("self", "num")
    assert parameter_names(cursor.fetchall) == ("self",)
    assert parameter_names(cursor.close) == ("self",)
    assert parameter_names(cursor.__enter__) == ("self",)
    assert parameter_names(cursor.__exit__) == (
        "self",
        "exc_type",
        "exc_value",
        "traceback",
    )
    assert isinstance(cursor.description, property)
    assert isinstance(cursor.rowcount, property)


def test_named_server_side_cursor_is_not_a_public_driver_contract():
    assert "name" not in inspect.signature(redshift_connector.Connection.cursor).parameters
