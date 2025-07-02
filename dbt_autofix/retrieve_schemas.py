import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import httpx


@dataclass
class YAMLSpecs:
    allowed_config_fields: set[str]
    allowed_properties: set[str]
    renamed_config_fields: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        self.allowed_config_fields_without_meta = self.allowed_config_fields - {"meta"}


@dataclass
class DbtProjectSpecs:
    allowed_config_fields_dbt_project_with_plus: set[str]
    renamed_config_fields_dbt_project: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        self.allowed_config_fields_dbt_project = set(
            [conf[1:] for conf in self.allowed_config_fields_dbt_project_with_plus]
        )


class SchemaSpecs:
    def __init__(self, version: Optional[str] = None):
        self.yaml_specs_per_node_type, self.dbtproject_specs_per_node_type = self._get_specs(version)
        self.owner_properties = ["name", "email"]
        self.nodes_with_owner = ["groups", "exposures"]

    def _get_specs(self, version: Optional[str] = None) -> tuple[dict[str, YAMLSpecs], dict[str, DbtProjectSpecs]]:
        if os.getenv("DEBUG"):
            logging.basicConfig(level=logging.INFO)

        if version is None:
            version = get_fusion_latest_version()
        yml_schema = get_fusion_yml_schema(version)
        dbt_project_schema = get_fusion_dbt_project_schema(version)

        model_property_field_name, model_config_field_name = self._get_yml_schema_fields(yml_schema, "models")
        yaml_specs_models = YAMLSpecs(
            allowed_config_fields=set(yml_schema["definitions"][model_config_field_name]["properties"]),
            allowed_properties=set(yml_schema["definitions"][model_property_field_name]["properties"]),
        )
        source_property_field_name, source_config_field_name = self._get_yml_schema_fields(yml_schema, "sources")
        yaml_specs_sources = YAMLSpecs(
            allowed_config_fields=set(yml_schema["definitions"][source_config_field_name]["properties"]),
            allowed_properties=set(yml_schema["definitions"][source_property_field_name]["properties"]),
        )
        snapshot_property_field_name, snapshot_config_field_name = self._get_yml_schema_fields(yml_schema, "snapshots")
        yaml_specs_snapshots = YAMLSpecs(
            allowed_config_fields=set(yml_schema["definitions"][snapshot_config_field_name]["properties"]),
            allowed_properties=set(yml_schema["definitions"][snapshot_property_field_name]["properties"]),
            renamed_config_fields={"target_schema": "schema", "target_database": "database"},
        )
        seed_property_field_name, seed_config_field_name = self._get_yml_schema_fields(yml_schema, "seeds")
        yaml_specs_seeds = YAMLSpecs(
            allowed_config_fields=set(yml_schema["definitions"][seed_config_field_name]["properties"]),
            allowed_properties=set(yml_schema["definitions"][seed_property_field_name]["properties"]),
        )
        exposure_property_field_name, exposure_config_field_name = self._get_yml_schema_fields(yml_schema, "exposures")
        yaml_specs_exposures = YAMLSpecs(
            allowed_config_fields=set(yml_schema["definitions"][exposure_config_field_name]["properties"]),
            allowed_properties=set(yml_schema["definitions"][exposure_property_field_name]["properties"]),
        )
        table_property_field_name, table_config_field_name = self._get_yml_schema_subfields(
            yml_schema, source_property_field_name, "tables"
        )
        yaml_specs_tables = YAMLSpecs(
            allowed_config_fields=set(yml_schema["definitions"][table_config_field_name]["properties"]),
            allowed_properties=set(yml_schema["definitions"][table_property_field_name]["properties"]),
        )
        column_property_field_name, column_config_field_name = self._get_yml_schema_subfields(
            yml_schema, model_property_field_name, "columns"
        )
        columns = YAMLSpecs(
            allowed_config_fields=set(yml_schema["definitions"][column_config_field_name]["properties"]),
            allowed_properties=set(yml_schema["definitions"][column_property_field_name]["properties"]),
        )
        test_property_field_name, test_config_field_name = self._get_yml_schema_fields(yml_schema, "tests")
        yaml_specs_tests = YAMLSpecs(
            allowed_config_fields=set(yml_schema["definitions"][test_config_field_name]["properties"]),
            allowed_properties=set(yml_schema["definitions"][test_property_field_name]["properties"]),
        )
        model_property_field_name_dbt_project = self._get_dbt_project_schema_fields(dbt_project_schema, "models")
        dbtproject_specs_models = DbtProjectSpecs(
            allowed_config_fields_dbt_project_with_plus=set(
                dbt_project_schema["definitions"][model_property_field_name_dbt_project]["properties"]
            ),
        )
        source_property_field_name_dbt_project = self._get_dbt_project_schema_fields(dbt_project_schema, "sources")
        dbtproject_specs_sources = DbtProjectSpecs(
            allowed_config_fields_dbt_project_with_plus=set(
                dbt_project_schema["definitions"][source_property_field_name_dbt_project]["properties"]
            ),
        )
        snapshot_property_field_name_dbt_project = self._get_dbt_project_schema_fields(dbt_project_schema, "snapshots")
        dbtproject_specs_snapshots = DbtProjectSpecs(
            allowed_config_fields_dbt_project_with_plus=set(
                dbt_project_schema["definitions"][snapshot_property_field_name_dbt_project]["properties"]
            ),
            renamed_config_fields_dbt_project={"target_schema": "+schema", "target_database": "+database"},
        )
        seed_property_field_name_dbt_project = self._get_dbt_project_schema_fields(dbt_project_schema, "seeds")
        dbtproject_specs_seeds = DbtProjectSpecs(
            allowed_config_fields_dbt_project_with_plus=set(
                dbt_project_schema["definitions"][seed_property_field_name_dbt_project]["properties"]
            ),
        )
        test_property_field_name_dbt_project = self._get_dbt_project_schema_fields(dbt_project_schema, "tests")
        dbtproject_specs_tests = DbtProjectSpecs(
            allowed_config_fields_dbt_project_with_plus=set(
                dbt_project_schema["definitions"][test_property_field_name_dbt_project]["properties"]
            ),
        )
        metric_property_field_name_dbt_project = self._get_dbt_project_schema_fields(dbt_project_schema, "metrics")
        dbtproject_specs_metrics = DbtProjectSpecs(
            allowed_config_fields_dbt_project_with_plus=set(
                dbt_project_schema["definitions"][metric_property_field_name_dbt_project]["properties"]
            ),
        )
        saved_query_property_field_name_dbt_project = self._get_dbt_project_schema_fields(
            dbt_project_schema, "saved-queries"
        )
        dbtproject_specs_saved_queries = DbtProjectSpecs(
            allowed_config_fields_dbt_project_with_plus=set(
                dbt_project_schema["definitions"][saved_query_property_field_name_dbt_project]["properties"]
            ),
        )
        # dbtproject_specs_exposures = DbtProjectSpecs(
        #     allowed_config_fields_dbt_project_with_plus=set(
        #         dbt_project_schema["definitions"]["ProjectExposuresConfig"]["properties"]
        #     ),
        # )

        return (
            {
                "models": yaml_specs_models,
                "seeds": yaml_specs_seeds,
                "sources": yaml_specs_sources,
                "snapshots": yaml_specs_snapshots,
                "tests": yaml_specs_tests,  # tests can be at the top level, or nested under nodes or nested under nodes columns
                "data_tests": yaml_specs_tests,  # data_tests can be at the top level, or nested under nodes or nested under nodes columns
                "exposures": yaml_specs_exposures,
                "tables": yaml_specs_tables,  # tables is nested under sources
                "columns": columns,  # columns is nested under models
            },
            {
                "metrics": dbtproject_specs_metrics,
                "models": dbtproject_specs_models,
                "seeds": dbtproject_specs_seeds,
                # "semantic-models": dbtproject_specs_saved_queries, -- there is an issue with those specs in 165
                "saved-queries": dbtproject_specs_saved_queries,
                "snapshots": dbtproject_specs_snapshots,
                "sources": dbtproject_specs_sources,
                "tests": dbtproject_specs_tests,
                "data_tests": dbtproject_specs_tests,
                # "exposures": dbtproject_specs_exposures, -- doesn't exist for exposure right now...
            },
        )

    def _get_yml_schema_fields(self, yml_schema: dict, node_type: str) -> tuple[str, str]:
        property_field_name = yml_schema["properties"][node_type]["items"]["$ref"].split("/")[-1]
        config_field_name = yml_schema["definitions"][property_field_name]["properties"]["config"]["anyOf"][0][
            "$ref"
        ].split("/")[-1]
        return property_field_name, config_field_name

    def _get_yml_schema_subfields(self, yml_schema: dict, definition: str, node_type: str) -> tuple[str, str]:
        property_field_name = yml_schema["definitions"][definition]["properties"][node_type]["items"]["$ref"].split(
            "/"
        )[-1]
        config_field_name = yml_schema["definitions"][property_field_name]["properties"]["config"]["anyOf"][0][
            "$ref"
        ].split("/")[-1]
        return property_field_name, config_field_name

    def _get_dbt_project_schema_fields(self, yml_schema: dict, node_type: str) -> str:
        property_field_name = yml_schema["properties"][node_type]["anyOf"][0]["$ref"].split("/")[-1]
        return property_field_name


def get_fusion_latest_version() -> str:
    latest_versions_url = "https://public.cdn.getdbt.com/fs/latest.json"
    resp = httpx.get(latest_versions_url)
    resp.raise_for_status()
    return resp.json()["tag"]


def get_fusion_yml_schema(version: str) -> dict:
    yml_schema_url = f"https://public.cdn.getdbt.com/fs/schemas/fs-schema-dbt-yaml-files-{version}.json"

    logging.info(f"Getting fusion yml schema for version {version}: {yml_schema_url}")
    response = httpx.get(yml_schema_url)
    response.raise_for_status()

    # for some reason we have 2 different schemas now in the response
    response_split = response.text.split("----------------------------------------------")
    return json.loads(response_split[-1])


def get_fusion_dbt_project_schema(version: str) -> dict:
    dbt_project_schema_url = f"https://public.cdn.getdbt.com/fs/schemas/fs-schema-dbt-project-{version}.json"

    logging.info(f"Getting fusion dbt project schema for version {version}: {dbt_project_schema_url}")
    response = httpx.get(dbt_project_schema_url)
    response.raise_for_status()

    return response.json()
