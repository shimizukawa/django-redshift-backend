import pytest
from django.db.backends.base.creation import BaseDatabaseCreation
from django.db.utils import NotSupportedError

from django_redshift_backend.creation import DatabaseCreation


class ConnectionThatMustNotBeUsed:
    settings_dict = {"NAME": "warehouse"}

    def cursor(self):
        raise AssertionError("test database rejection must happen before SQL")

    def close(self):
        raise AssertionError("test database rejection must happen before close")


@pytest.mark.parametrize(
    ("method_name", "args"),
    [
        ("create_test_db", ()),
        ("clone_test_db", ("worker-1",)),
        ("destroy_test_db", ()),
    ],
)
def test_test_database_operations_are_rejected_before_connection_use(method_name, args):
    creation = DatabaseCreation(ConnectionThatMustNotBeUsed())
    assert isinstance(creation, BaseDatabaseCreation)
    with pytest.raises(NotSupportedError, match=method_name):
        getattr(creation, method_name)(*args)
