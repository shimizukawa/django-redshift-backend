from django_redshift_backend import base
from django_redshift_backend import _backend


def test_existing_engine_entry_point_is_not_activated():
    assert base.DatabaseWrapper is not _backend.DatabaseWrapper
