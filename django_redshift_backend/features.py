from django.db.backends.base.features import BaseDatabaseFeatures


class DatabaseFeatures(BaseDatabaseFeatures):
    supports_transactions = True
    uses_savepoints = False
    can_release_savepoints = False

    can_return_columns_from_insert = False
    can_return_rows_from_bulk_insert = False
    can_return_rows_from_update = False
    has_bulk_insert = True
    supports_ignore_conflicts = False
    supports_update_conflicts = False
    supports_update_conflicts_with_target = False

    has_select_for_update = False
    has_select_for_update_nowait = False
    has_select_for_update_skip_locked = False
    has_select_for_update_of = False
    has_select_for_no_key_update = False
    supports_select_for_update_with_limit = False

    can_distinct_on_fields = False
    allows_group_by_selected_pks = False
    allows_group_by_select_index = True

    has_real_datatype = True
    has_native_uuid_field = False
    has_native_duration_field = True
    supports_temporal_subtraction = True

    supports_aggregate_filter_clause = False
    supports_over_clause = True
    supports_frame_range_fixed_distance = False
    only_supports_unbounded_with_preceding_and_following = False

    supports_json_field = True
    has_native_json_field = False
    can_introspect_json_field = False
    supports_primitives_in_json_field = True
    has_json_operators = False
    supports_json_field_contains = False

    supports_foreign_keys = False
    can_create_inline_fk = False
    can_defer_constraint_checks = False
    supports_deferrable_unique_constraints = False
    supports_nullable_unique_constraints = False
    supports_partially_nullable_unique_constraints = False
    supports_column_check_constraints = False
    supports_table_check_constraints = False
    can_introspect_check_constraints = False

    supports_tablespaces = False
    supports_index_column_ordering = False
    supports_index_on_text_field = False
    supports_partial_indexes = False
    supports_functions_in_partial_indexes = False
    supports_covering_indexes = False
    supports_expression_indexes = False
    indexes_foreign_keys = False
    can_rename_index = False

    supports_sequence_reset = False
    can_rollback_ddl = False
    supports_atomic_references_rename = False
    supports_combined_alters = False

    supports_collation_on_charfield = False
    supports_collation_on_textfield = False
    supports_non_deterministic_collations = False
    supports_comments = False
    supports_comments_inline = False

    supports_default_keyword_in_insert = True
    supports_default_keyword_in_bulk_insert = True
    supports_nulls_distinct_unique_constraints = False
    supports_paramstyle_pyformat = False
    supports_inspectdb = False

    supported_explain_formats = set()
    nulls_order_largest = True
    delete_can_self_reference_subquery = True
