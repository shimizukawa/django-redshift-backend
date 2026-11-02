import pytest
import redshift_connector
from django import db
from django.db.utils import DatabaseErrorWrapper

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


class Wrapper:
    Database = redshift_connector
    errors_occurred = False


@pytest.mark.parametrize("name", EXCEPTION_NAMES)
def test_django_translates_public_driver_exception(name):
    wrapper = Wrapper()
    driver_exception = getattr(redshift_connector, name)
    django_exception = getattr(db, name)
    with pytest.raises(django_exception), DatabaseErrorWrapper(wrapper):
        raise driver_exception("contract probe")
    assert wrapper.errors_occurred is (name not in {"DataError", "IntegrityError"})
