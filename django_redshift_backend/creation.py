from django.db.backends.base.creation import BaseDatabaseCreation
from django.db.utils import NotSupportedError


class DatabaseCreation(BaseDatabaseCreation):
    def create_test_db(
        self, verbosity=1, autoclobber=False, serialize=None, keepdb=False
    ):
        raise NotSupportedError("create_test_db is not supported by Amazon Redshift.")

    def clone_test_db(self, suffix, verbosity=1, autoclobber=False, keepdb=False):
        raise NotSupportedError("clone_test_db is not supported by Amazon Redshift.")

    def destroy_test_db(
        self, old_database_name=None, verbosity=1, keepdb=False, suffix=None
    ):
        raise NotSupportedError("destroy_test_db is not supported by Amazon Redshift.")
