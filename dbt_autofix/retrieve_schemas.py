import json
from dataclasses import dataclass

import httpx


@dataclass
class YAMLSpecs:
    allowed_config_fields: set[str]
    allowed_properties: set[str]

    def __post_init__(self):
        self.allowed_config_fields_without_meta = self.allowed_config_fields - {"meta"}


@dataclass
class DbtProjectSpecs:
    allowed_config_fields_dbt_project_with_plus: set[str]

    def __post_init__(self):
        self.allowed_config_fields_dbt_project = set(
            [conf[1:] for conf in self.allowed_config_fields_dbt_project_with_plus]
        )


def get_fusion_latest_version() -> str:
    latest_versions_url = "https://public.cdn.getdbt.com/fs/latest.json"
    resp = httpx.get(latest_versions_url)
    resp.raise_for_status()
    return resp.json()["tag"]


def get_fusion_yml_schema(version: str) -> dict:
    yml_schema_url = f"https://public.cdn.getdbt.com/fs/schemas/fs-schema-dbt-yaml-files-{version}.json"

    response = httpx.get(yml_schema_url)
    response.raise_for_status()
    # print(response.text)

    # for some reason we have 2 different schemas now in the response
    response_split = response.text.split("----------------------------------------------")
    return json.loads(response_split[-1])


def get_fusion_dbt_project_schema(version: str) -> dict:
    dbt_project_schema_url = f"https://public.cdn.getdbt.com/fs/schemas/fs-schema-dbt-project-{version}.json"

    response = httpx.get(dbt_project_schema_url)
    response.raise_for_status()

    return response.json()


def get_specs_from_latest_schema() -> tuple[dict[str, YAMLSpecs], dict[str, DbtProjectSpecs]]:
    latest_version = get_fusion_latest_version()
    yml_schema = get_fusion_yml_schema(latest_version)
    dbt_project_schema = get_fusion_dbt_project_schema(latest_version)

    yaml_specs_models = YAMLSpecs(
        allowed_config_fields=set(yml_schema["definitions"]["ModelPropertiesConfigs"]["properties"]),
        allowed_properties=set(yml_schema["definitions"]["ModelProperties"]["properties"]),
    )
    yaml_specs_sources = YAMLSpecs(
        allowed_config_fields=set(yml_schema["definitions"]["SourcePropertiesConfig"]["properties"]),
        allowed_properties=set(yml_schema["definitions"]["SourceProperties"]["properties"]),
    )
    yaml_specs_snapshots = YAMLSpecs(
        allowed_config_fields=set(yml_schema["definitions"]["SnapshotsConfig"]["properties"]),
        allowed_properties=set(yml_schema["definitions"]["SnapshotProperties"]["properties"]),
    )
    yaml_specs_seeds = YAMLSpecs(
        allowed_config_fields=set(yml_schema["definitions"]["SeedsConfig"]["properties"]),
        allowed_properties=set(yml_schema["definitions"]["SeedProperties"]["properties"]),
    )

    dbtproject_specs_models = DbtProjectSpecs(
        allowed_config_fields_dbt_project_with_plus=set(
            dbt_project_schema["definitions"]["ProjectModelConfig"]["properties"]
        ),
    )
    dbtproject_specs_sources = DbtProjectSpecs(
        allowed_config_fields_dbt_project_with_plus=set(
            dbt_project_schema["definitions"]["ProjectSourceConfig"]["properties"]
        ),
    )
    dbtproject_specs_snapshots = DbtProjectSpecs(
        allowed_config_fields_dbt_project_with_plus=set(
            dbt_project_schema["definitions"]["ProjectSnapshotConfig"]["properties"]
        ),
    )
    dbtproject_specs_seeds = DbtProjectSpecs(
        allowed_config_fields_dbt_project_with_plus=set(
            dbt_project_schema["definitions"]["ProjectSeedConfig"]["properties"]
        ),
    )
    dbtproject_specs_tests = DbtProjectSpecs(
        allowed_config_fields_dbt_project_with_plus=set(
            dbt_project_schema["definitions"]["ProjectDataTestConfig"]["properties"]
        ),
    )
    dbtproject_specs_metrics = DbtProjectSpecs(
        allowed_config_fields_dbt_project_with_plus=set(
            dbt_project_schema["definitions"]["ProjectMetricConfigs"]["properties"]
        ),
    )
    dbtproject_specs_saved_queries = DbtProjectSpecs(
        allowed_config_fields_dbt_project_with_plus=set(
            dbt_project_schema["definitions"]["SavedQueriesConfig"]["properties"]
        ),
    )

    return (
        {
            "models": yaml_specs_models,
            "seeds": yaml_specs_seeds,
            "sources": yaml_specs_sources,
            "snapshots": yaml_specs_snapshots,
            # tests are not modified today as they don't support meta
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
        },
    )


yaml_specs_per_node_type, dbtproject_specs_per_node_type = get_specs_from_latest_schema()
