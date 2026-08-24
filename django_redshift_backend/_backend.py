from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.base.creation import BaseDatabaseCreation
from django.db.backends.base.features import BaseDatabaseFeatures
from django.db.backends.base.introspection import BaseDatabaseIntrospection
from django.db.backends.base.operations import BaseDatabaseOperations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.utils import NotSupportedError

from . import driver
from .client import DatabaseClient


class DatabaseWrapper(BaseDatabaseWrapper):
    vendor = "redshift"
    display_name = "Amazon Redshift"
    Database = driver.Database

    client_class = DatabaseClient
    creation_class = BaseDatabaseCreation
    features_class = BaseDatabaseFeatures
    introspection_class = BaseDatabaseIntrospection
    ops_class = BaseDatabaseOperations
    SchemaEditorClass = BaseDatabaseSchemaEditor

    data_types = {}
    data_types_suffix = {}
    data_type_check_constraints = {}

    def get_connection_params(self):
        return driver.build_connect_kwargs(self.settings_dict)

    def get_new_connection(self, conn_params):
        return driver.connect(**conn_params)

    def init_connection_state(self):
        super().init_connection_state()

    def create_cursor(self, name=None):
        if name is not None:
            raise NotSupportedError("Amazon Redshift does not support named cursors.")
        return self.connection.cursor()

    def _set_autocommit(self, autocommit):
        self.connection.autocommit = autocommit

    def is_usable(self):
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except self.Database.Error:
            return False
        return True
