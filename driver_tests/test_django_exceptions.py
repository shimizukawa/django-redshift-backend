import pytest
from django import db
from django.db.utils import DatabaseErrorWrapper
from django_redshift_backend._backend import DatabaseWrapper

EXCEPTION_NAMES = (
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


@pytest.mark.parametrize("name", EXCEPTION_NAMES)
def test_django_translates_public_driver_exception(name):
    wrapper = DatabaseWrapper.__new__(DatabaseWrapper)
    wrapper.errors_occurred = False
    driver_exception = getattr(DatabaseWrapper.Database, name)
    django_exception = getattr(db, name)
    with pytest.raises(django_exception), DatabaseErrorWrapper(wrapper):
        raise driver_exception("contract probe")
    assert wrapper.errors_occurred is (name not in {"DataError", "IntegrityError"})
