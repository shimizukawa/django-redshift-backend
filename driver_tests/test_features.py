import pytest
from django.db.backends.base.features import BaseDatabaseFeatures

from django_redshift_backend._backend import DatabaseWrapper
from django_redshift_backend.features import DatabaseFeatures


def settings_dict():
    return {
        "NAME": "warehouse",
        "HOST": "example.test",
        "PORT": "5439",
        "USER": "alice",
        "PASSWORD": "secret",
        "OPTIONS": {},
        "TIME_ZONE": None,
        "CONN_MAX_AGE": 0,
        "CONN_HEALTH_CHECKS": False,
        "AUTOCOMMIT": True,
    }


def test_features_use_public_base_class():
    assert issubclass(DatabaseFeatures, BaseDatabaseFeatures)


def test_internal_wrapper_registers_redshift_features():
    wrapper = DatabaseWrapper(settings_dict(), "feature-contract")
    assert wrapper.features_class is DatabaseFeatures
    assert isinstance(wrapper.features, DatabaseFeatures)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("supports_transactions", True),
        ("uses_savepoints", False),
        ("can_release_savepoints", False),
        ("can_return_columns_from_insert", False),
        ("can_return_rows_from_bulk_insert", False),
        ("can_return_rows_from_update", False),
        ("has_bulk_insert", True),
        ("supports_ignore_conflicts", False),
        ("supports_update_conflicts", False),
        ("supports_update_conflicts_with_target", False),
        ("has_select_for_update", False),
        ("has_select_for_update_nowait", False),
        ("has_select_for_update_skip_locked", False),
        ("has_select_for_update_of", False),
        ("has_select_for_no_key_update", False),
        ("can_distinct_on_fields", False),
        ("allows_group_by_selected_pks", False),
        ("allows_group_by_select_index", True),
        ("has_real_datatype", True),
        ("has_native_uuid_field", False),
        ("has_native_duration_field", True),
        ("supports_temporal_subtraction", True),
        ("supports_aggregate_filter_clause", False),
        ("supports_over_clause", True),
        ("supports_frame_range_fixed_distance", False),
        ("only_supports_unbounded_with_preceding_and_following", False),
        ("supports_json_field", True),
        ("has_native_json_field", False),
        ("can_introspect_json_field", False),
        ("has_json_object_function", False),
        ("supports_primitives_in_json_field", True),
        ("has_json_operators", False),
        ("supports_json_field_contains", False),
        ("supports_json_negative_indexing", False),
        ("supports_foreign_keys", False),
        ("can_create_inline_fk", False),
        ("can_defer_constraint_checks", False),
        ("supports_deferrable_unique_constraints", False),
        ("supports_nullable_unique_constraints", False),
        ("supports_partially_nullable_unique_constraints", False),
        ("supports_column_check_constraints", False),
        ("supports_table_check_constraints", False),
        ("can_introspect_default", False),
        ("can_introspect_foreign_keys", False),
        ("can_introspect_check_constraints", False),
        ("supports_tablespaces", False),
        ("supports_index_column_ordering", False),
        ("supports_index_on_text_field", False),
        ("supports_partial_indexes", False),
        ("supports_functions_in_partial_indexes", False),
        ("supports_covering_indexes", False),
        ("supports_expression_indexes", False),
        ("supports_expression_defaults", False),
        ("supports_stored_generated_columns", False),
        ("supports_virtual_generated_columns", False),
        ("indexes_foreign_keys", False),
        ("can_rename_index", False),
        ("supports_sequence_reset", False),
        ("can_rollback_ddl", False),
        ("supports_atomic_references_rename", False),
        ("supports_combined_alters", False),
        ("supports_collation_on_charfield", False),
        ("supports_collation_on_textfield", False),
        ("supports_non_deterministic_collations", False),
        ("supports_comments", False),
        ("supports_comments_inline", False),
        ("supports_default_keyword_in_insert", True),
        ("supports_default_keyword_in_bulk_insert", True),
        ("supports_nulls_distinct_unique_constraints", False),
        ("supports_tuple_lookups", False),
        ("supports_tuple_comparison_against_subquery", False),
        ("supports_on_delete_db_cascade", False),
        ("supports_on_delete_db_default", False),
        ("supports_on_delete_db_null", False),
        ("supports_paramstyle_pyformat", False),
        ("supports_select_for_update_with_limit", False),
        ("supports_inspectdb", False),
        ("nulls_order_largest", True),
        ("delete_can_self_reference_subquery", True),
    ],
)
def test_redshift_feature_contract(name, expected):
    wrapper = DatabaseWrapper(settings_dict(), "feature-contract")
    assert getattr(wrapper.features, name) is expected


def test_redshift_explain_formats_are_text_only():
    wrapper = DatabaseWrapper(settings_dict(), "feature-contract")
    assert wrapper.features.supported_explain_formats == set()
