import sys
from importlib.metadata import metadata, version

import redshift_connector
from packaging.specifiers import SpecifierSet
from packaging.version import Version


DRIVER_RANGE = SpecifierSet(">=2.1.14,<3")
DBAPI_EXCEPTIONS = (
    "Error",
    "InterfaceError",
    "DatabaseError",
    "DataError",
    "OperationalError",
    "IntegrityError",
    "InternalError",
    "ProgrammingError",
    "NotSupportedError",
)


def test_installed_driver_is_in_proposed_range():
    assert Version(version("redshift-connector")) in DRIVER_RANGE


def test_driver_metadata_supports_running_python():
    requires_python = SpecifierSet(metadata("redshift-connector")["Requires-Python"])
    running = ".".join(map(str, sys.version_info[:3]))
    assert requires_python.contains(running)


def test_dbapi_module_constants_match_django_sql_contract():
    assert redshift_connector.apilevel == "2.0"
    assert redshift_connector.paramstyle == "format"
    assert redshift_connector.threadsafety == 1


def test_dbapi_exception_namespace_is_complete():
    for name in DBAPI_EXCEPTIONS:
        exception = getattr(redshift_connector, name)
        assert issubclass(exception, Exception)
    assert issubclass(redshift_connector.InterfaceError, redshift_connector.Error)
    assert issubclass(redshift_connector.DatabaseError, redshift_connector.Error)
    for name in DBAPI_EXCEPTIONS[2:]:
        assert issubclass(getattr(redshift_connector, name), redshift_connector.DatabaseError)


def test_dbapi_value_constructors_are_public():
    for name in (
        "Binary",
        "Date",
        "Time",
        "Timestamp",
        "DateFromTicks",
        "TimeFromTicks",
        "TimestampFromTicks",
    ):
        assert callable(getattr(redshift_connector, name))
