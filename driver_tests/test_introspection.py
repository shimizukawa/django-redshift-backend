from django_redshift_backend import _backend


def test_internal_backend_registers_redshift_introspection():
    assert _backend.DatabaseWrapper.introspection_class.__module__ == (
        "django_redshift_backend.introspection"
    )
