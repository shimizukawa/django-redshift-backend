"""Django 4.2-only introspection compatibility.

Remove this module and the selector in ``_backend.py`` when Django 4.2 support
is removed. Django 4.2's inspectdb expects relation values without an
``on_delete`` slot.
"""

from .introspection import DatabaseIntrospection as BaseDatabaseIntrospection


class DatabaseIntrospection(BaseDatabaseIntrospection):
    def get_relations(self, cursor, table_name):
        return {
            column: (target_column, target_table)
            for column, (target_column, target_table, _on_delete) in super()
            .get_relations(cursor, table_name)
            .items()
        }
