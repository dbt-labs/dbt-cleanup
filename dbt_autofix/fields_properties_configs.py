import csv
from dataclasses import dataclass

from rich import print


@dataclass
class AllowedConfig:
    allowed_config_fields: set[str]
    allowed_properties: set[str]

    def __post_init__(self):
        self.allowed_config_fields_without_meta = self.allowed_config_fields - {"meta"}
        # in case we forgot to remove meta from the allowed properties
        self.allowed_properties = self.allowed_properties - {"meta"}


models_allowed_config = AllowedConfig(
    allowed_config_fields=set(
        [
            # model specific
            "materialized",
            "sql_header",
            "on_configuration_change",
            "unique_key",
            "incremental_strategy",  # was missing at first
            "on_schema_change",  # was missing at first
            "batch_size",
            "begin",
            "lookback",
            "concurrent_batches",
            # general
            "enabled",
            "tags",
            "pre_hook",
            "post_hook",
            "database",
            "schema",
            "alias",
            "persist_docs",
            "meta",
            "grants",
            "contract",
            "event_time",
            # Snowflake: https://github.com/dbt-labs/dbt-adapters/blob/af33935b119347cc021554ea854884bce986ef8d/dbt-snowflake/src/dbt/adapters/snowflake/impl.py#L42-L58
            "transient",
            "cluster_by",
            "automatic_clustering",
            "secure",
            "copy_grants",
            "snowflake_warehouse",
            "query_tag",
            "tmp_relation_type",
            "merge_update_columns",
            "target_lag",
            "table_format",
            "external_volume",
            "base_location_root",
            "base_location_subpath",
            # BQ: https://github.com/dbt-labs/dbt-adapters/blob/af33935b119347cc021554ea854884bce986ef8d/dbt-bigquery/src/dbt/adapters/bigquery/impl.py#L98
            "dataset",
            "project",
            "cluster_by",
            "partition_by",
            "kms_key_name",
            "labels",
            "partitions",
            "grant_access_to",
            "hours_to_expiration",
            "require_partition_filter",
            "partition_expiration_days",
            "merge_update_columns",
            "enable_refresh",
            "refresh_interval_minutes",
            "max_staleness",
            "enable_list_inference",
            "intermediate_format",
            "submission_method",
            # Postgres
            "unlogged",
            "indexes",
            # Redshift
            "sort_type",
            "dist",
            "sort",
            "bind",
            "backup",
            "auto_refresh",
            # DBX: https://github.com/databricks/dbt-databricks/blob/fde68588d45e8a299a83318acdca6c97081088e8/dbt/adapters/databricks/impl.py#L105
            "file_format",
            "table_format",
            "location_root",
            "include_full_name_in_path",
            "partition_by",
            "clustered_by",
            "liquid_clustered_by",
            "auto_liquid_cluster",
            "buckets",
            "options",
            "merge_update_columns",
            "merge_exclude_columns",
            "databricks_tags",
            "tblproperties",
            "zorder",
            "unique_tmp_table_suffix",
            "skip_non_matched_step",
            "skip_matched_step",
            "matched_condition",
            "not_matched_condition",
            "not_matched_by_source_action",
            "not_matched_by_source_condition",
            "target_alias",
            "source_alias",
            "merge_with_schema_evolution",
            # moved from property
            "docs",
            "access",
            "group",
            # new
            "freshness",
        ]
    ),
    allowed_properties=set(
        [
            "name",
            "description",
            "latest_version",
            "deprecation_date",
            "config",
            "constraints",
            "data_tests",
            "tests",
            "columns",
            "time_spine",
            "versions",
        ]
    ),
)
sources_allowed_config = AllowedConfig(
    allowed_config_fields=set(["enabled", "event_time", "meta", "freshness", "tags"]),
    allowed_properties=set(
        [
            "name",
            "description",
            "database",
            "schema",
            "loader",
            "loaded_at_field",
            "quoting",
            "tables",
            "config",
        ]
    ),
)
snapshots_allowed_config = AllowedConfig(
    allowed_config_fields=set(
        [
            # snapshot specific
            "database",
            "schema",
            "unique_key",
            "strategy",
            "updated_at",
            "check_cols",
            "snapshot_meta_column_names",
            "hard_deletes",
            "dbt_valid_to_current",
            # general
            "enabled",
            "tags",
            "alias",
            "pre_hook",
            "post_hook",
            "persist_docs",
            "grants",
            "event_time",
            # moved from property
            "docs",
            # not in docs for config
            "meta",
        ]
    ),
    allowed_properties=set(
        [
            "name",
            "description",
            "config",
            "tests",
            "columns",
        ]
    ),
)
seeds_allowed_config = AllowedConfig(
    allowed_config_fields=set(
        [
            # seed specific
            "quote_columns",
            "column_types",
            "delimiter",
            # general
            "enabled",
            "tags",
            "pre_hook",
            "post_hook",
            "database",
            "schema",
            "alias",
            "persist_docs",
            "full_refresh",
            "meta",
            "grants",
            "event_time",
            # moved from property
            "docs",
        ]
    ),
    allowed_properties=set(
        [
            "name",
            "description",
            "config",
            "tests",
            "columns",
        ]
    ),
)

tests_allowed_config = AllowedConfig(
    allowed_config_fields=set(
        [
            # general
            "enabled",
            "tags",
            "meta",
            "database",
            "schema",
            "alias",
            # data tests
            "fail_calc",
            "limit",
            "severity",
            "error_if",
            "warn_if",
            "store_failures",
            "where",
        ]
    ),
    allowed_properties=set(
        [
            "name",
            "description",
            "config",
        ]
    ),
)

columns_allowed_config = AllowedConfig(
    allowed_config_fields=set(
        [
            "tags",
            "meta",
        ]
    ),
    allowed_properties=set(
        [
            "name",
            "description",
            "config",
            "tests",
            "data_type",
            "constraints",
            "quote",
            "granularity",
        ]
    ),
)

tables_allowed_config = AllowedConfig(
    allowed_config_fields=set(
        [
            "enabled",
            "event_time",
            "meta",
            "tags",
            "freshness"
        ]
    ),
    allowed_properties=set(
        [
            "name",
            "description",
            "identifier",
            "loaded_at_field",
            "tests",
            "quoting",
            "external",
            "columns",
        ]
    ),
)

fields_per_node_type = {
    "models": models_allowed_config,
    "seeds": seeds_allowed_config,
    "tests": tests_allowed_config,
    "sources": sources_allowed_config,
    "snapshots": snapshots_allowed_config,
    "columns": columns_allowed_config,
    "tables": tables_allowed_config,
}


def print_matrix(json_schema_version=None):  # noqa: PLR0912
    from dbt_autofix.retrieve_schemas import SchemaSpecs

    schema_specs = SchemaSpecs(json_schema_version)
    results = dict()
    for node_type, fields_config in fields_per_node_type.items():
        allowed_config_fields = fields_config.allowed_config_fields
        for field in allowed_config_fields:
            if field not in results:
                results[field] = {f"{node_type}-bestguess": "config"}
            else:
                results[field].update({f"{node_type}-bestguess": "config"})

        allowed_properties = fields_config.allowed_properties
        for property in allowed_properties:
            if property not in results:
                results[property] = {f"{node_type}-bestguess": "property"}
            else:
                results[property].update({f"{node_type}-bestguess": "property"})

    for node_type, fields_config in schema_specs.yaml_specs_per_node_type.items():
        allowed_config_fields = fields_config.allowed_config_fields
        for field in allowed_config_fields:
            if field not in results:
                results[field] = {f"{node_type}-fusion": "config"}
            else:
                results[field].update({f"{node_type}-fusion": "config"})

        allowed_properties = fields_config.allowed_properties
        for property in allowed_properties:
            if property not in results:
                results[property] = {f"{node_type}-fusion": "property"}
            else:
                results[property].update({f"{node_type}-fusion": "property"})

    # Assuming your dictionary is named 'results'
    with open("config_resources.csv", "w", newline="") as csvfile:
        # Determine all possible resource types from the data
        resource_types = sorted(
            set(resource_type for config_values in results.values() for resource_type in config_values.keys())
        )

        # Create fieldnames with 'field_name' as the first column followed by all resource types
        fieldnames = ["field_name", *resource_types]

        # Create CSV writer
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        # Write the header
        writer.writeheader()

        # Sort field_names alphabetically
        sorted_field_names = sorted(results.keys())

        # Write each row
        for field_name in sorted_field_names:
            resources = results[field_name]
            row = {"field_name": field_name}
            # Add values for each resource type
            for resource_type in resource_types:
                row[resource_type] = resources.get(resource_type, "")
            writer.writerow(row)

    print("CSV file 'config_resources.csv' has been created successfully.")
