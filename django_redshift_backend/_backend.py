import django

from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.base.introspection import BaseDatabaseIntrospection
from django.db.utils import NotSupportedError

from . import driver
from .client import DatabaseClient
from .creation import DatabaseCreation
from .features import DatabaseFeatures
from .operations import DatabaseOperations
from .schema import DatabaseSchemaEditor


def schema_editor_class_for(version):
    if version[:2] == (4, 2):
        from .schema_django42 import DatabaseSchemaEditor as DatabaseSchemaEditor42

        return DatabaseSchemaEditor42
    return DatabaseSchemaEditor


class DatabaseWrapper(BaseDatabaseWrapper):
    vendor = "redshift"
    display_name = "Amazon Redshift"
    Database = driver.Database

    client_class = DatabaseClient
    creation_class = DatabaseCreation
    features_class = DatabaseFeatures
    introspection_class = BaseDatabaseIntrospection
    ops_class = DatabaseOperations
    SchemaEditorClass = schema_editor_class_for(django.VERSION)

    data_types = {
        "AutoField": "integer",
        "BigAutoField": "bigint",
        "SmallAutoField": "smallint",
        "BinaryField": "varbyte(%(max_length)s)",
        "BooleanField": "boolean",
        "CharField": "varchar(%(max_length)s)",
        "CommaSeparatedIntegerField": "varchar(%(max_length)s)",
        "DateField": "date",
        "DateTimeField": "timestamp with time zone",
        "DecimalField": "numeric(%(max_digits)s, %(decimal_places)s)",
        "DurationField": "interval",
        "EmailField": "varchar(%(max_length)s)",
        "FileField": "varchar(%(max_length)s)",
        "FilePathField": "varchar(%(max_length)s)",
        "FloatField": "double precision",
        "IntegerField": "integer",
        "BigIntegerField": "bigint",
        "IPAddressField": "varchar(15)",
        "GenericIPAddressField": "varchar(39)",
        "JSONField": "varchar",
        "OneToOneField": "integer",
        "PositiveBigIntegerField": "bigint",
        "PositiveIntegerField": "integer",
        "PositiveSmallIntegerField": "smallint",
        "SlugField": "varchar(%(max_length)s)",
        "SmallIntegerField": "smallint",
        "TextField": "varchar(max)",
        "TimeField": "time",
        "UUIDField": "varchar(36)",
    }
    data_types_suffix = {
        "AutoField": "identity(1, 1)",
        "BigAutoField": "identity(1, 1)",
        "SmallAutoField": "identity(1, 1)",
    }
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
