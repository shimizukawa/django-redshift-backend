from .schema import DatabaseSchemaEditor as CommonDatabaseSchemaEditor


class DatabaseSchemaEditor(CommonDatabaseSchemaEditor):
    """Django 4.2-only deletion boundary.

    Remove this module, the selector branch in _backend.py, and the
    test_django42_selection_is_one_deletion_oriented_branch test together when
    Django 4.2 support is dropped. Common Redshift behavior does not belong
    here.
    """
