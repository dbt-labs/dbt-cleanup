import difflib
import io
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import yamllint.config
import yamllint.linter
from rich.console import Console
from ruamel.yaml import YAML
from ruamel.yaml.compat import StringIO
from yaml import safe_load

from dbt_autofix.retrieve_schemas import (
    DbtProjectSpecs,
    SchemaSpecs,
)

NUM_SPACES_TO_REPLACE_TAB = 2

console = Console()
error_console = Console(stderr=True)

config = """
rules:
  key-duplicates: enable
"""

yaml_config = yamllint.config.YamlLintConfig(config)


class DbtYAML(YAML):
    """dbt-compatible YAML class."""

    def __init__(self):
        super().__init__(typ=["rt", "string"])
        self.preserve_quotes = True
        self.width = 4096
        self.indent(mapping=2, sequence=4, offset=2)
        self.default_flow_style = False

    def dump(self, data, stream=None, **kw):
        inefficient = False
        if stream is None:
            inefficient = True
            stream = StringIO()
        super().dump(data, stream, **kw)
        if inefficient:
            return stream.getvalue()

    def dump_to_string(self, data: Any, add_final_eol: bool = False) -> str:
        buf = io.BytesIO()
        self.dump(data, buf)
        if add_final_eol:
            return buf.getvalue().decode("utf-8")
        else:
            return buf.getvalue()[:-1].decode("utf-8")


def read_file(path: Path) -> Dict:
    yaml = DbtYAML()
    return yaml.load(path)


def dict_to_yaml_str(content: Dict[str, Any]) -> str:
    """Write a dict value to a YAML string"""
    yaml = DbtYAML()
    file_text = yaml.dump_to_string(content)  # type: ignore
    return file_text


@dataclass
class YMLRuleRefactorResult:
    rule_name: str
    refactored: bool
    refactored_yaml: str
    original_yaml: str
    refactor_logs: list[str]
    dbt_deprecation_classes: list[str]

    def to_dict(self) -> dict:
        ret_dict = {
            "rule_name": self.rule_name,
            "refactor_logs": self.refactor_logs,
            "dbt_deprecation_classes": self.dbt_deprecation_classes,
        }
        return ret_dict


@dataclass
class YMLRefactorResult:
    dry_run: bool
    file_path: Path
    refactored: bool
    refactored_yaml: str
    original_yaml: str
    refactors: list[YMLRuleRefactorResult]

    def update_yaml_file(self) -> None:
        """Update the YAML file with the refactored content"""
        Path(self.file_path).write_text(self.refactored_yaml)

    def print_to_console(self, json_output: bool = True):
        if not self.refactored:
            return

        if json_output:
            to_print = {
                "mode": "dry_run" if self.dry_run else "applied",
                "file_path": str(self.file_path),
                "refactors": [refactor.to_dict() for refactor in self.refactors if refactor.refactored],
            }
            print(json.dumps(to_print))  # noqa: T201
            return

        console.print(
            f"\n{'DRY RUN - NOT APPLIED: ' if self.dry_run else ''}Refactored {self.file_path}:",
            style="green",
        )
        for refactor in self.refactors:
            if refactor.refactored:
                console.print(f"  {refactor.rule_name}", style="yellow")
                for log in refactor.refactor_logs:
                    console.print(f"    {log}")


@dataclass
class SQLRuleRefactorResult:
    rule_name: str
    refactored: bool
    refactored_content: str
    original_content: str
    refactor_logs: list[str]
    dbt_deprecation_classes: list[str]

    def to_dict(self) -> dict:
        ret_dict = {
            "rule_name": self.rule_name,
            "refactor_logs": self.refactor_logs,
        }
        return ret_dict


@dataclass
class SQLRefactorResult:
    dry_run: bool
    file_path: Path
    refactored: bool
    refactored_content: str
    original_content: str
    refactors: list[SQLRuleRefactorResult]

    def update_sql_file(self) -> None:
        """Update the SQL file with the refactored content"""
        Path(self.file_path).write_text(self.refactored_content)

    def print_to_console(self, json_output: bool = True):
        if not self.refactored:
            return

        if json_output:
            to_print = {
                "mode": "dry_run" if self.dry_run else "applied",
                "file_path": str(self.file_path),
                "refactors": [refactor.to_dict() for refactor in self.refactors if refactor.refactored],
            }
            print(json.dumps(to_print))  # noqa: T201
            return

        console.print(
            f"\n{'DRY RUN - NOT APPLIED: ' if self.dry_run else ''}Refactored {self.file_path}:",
            style="green",
        )
        for refactor in self.refactors:
            if refactor.refactored:
                console.print(f"  {refactor.rule_name}", style="yellow")


def remove_unmatched_endings(sql_content: str) -> Tuple[str, List[str]]:  # noqa: PLR0912
    """Remove unmatched {% endmacro %} and {% endif %} tags from SQL content.

    Handles:
    - Multi-line tags
    - Whitespace control variants ({%- and -%})
    - Nested blocks

    Args:
        sql_content: The SQL content to process

    Returns:
        Tuple containing:
        - The processed SQL content
        - List of removal messages
    """
    # Regex patterns for Jinja tag matching
    JINJA_TAG_PATTERN = re.compile(r"{%-?\s*((?s:.*?))\s*-?%}", re.DOTALL)
    MACRO_START = re.compile(r"^macro\s+([^\s(]+)")  # Captures macro name
    IF_START = re.compile(r"^if[(\s]+.*")  # if blocks can also be {% if(...) %}
    MACRO_END = re.compile(r"^endmacro")
    IF_END = re.compile(r"^endif")

    logs: List[str] = []
    # Track macro and if states with their positions
    macro_stack: List[Tuple[int, int, str]] = []  # [(start_pos, end_pos, macro_name), ...]
    if_stack: List[Tuple[int, int]] = []  # [(start_pos, end_pos), ...]

    # Track positions to remove
    to_remove: List[Tuple[int, int]] = []  # [(start_pos, end_pos), ...]

    # Find all Jinja tags
    for match in JINJA_TAG_PATTERN.finditer(sql_content):
        tag_content = match.group(1)
        start_pos = match.start()
        end_pos = match.end()

        # Check for macro start
        macro_match = MACRO_START.match(tag_content)
        if macro_match:
            macro_name = macro_match.group(1)
            macro_stack.append((start_pos, end_pos, macro_name))
            continue

        # Check for if start
        if IF_START.match(tag_content):
            if_stack.append((start_pos, end_pos))
            continue

        # Handle endmacro
        if MACRO_END.match(tag_content):
            if not macro_stack:
                to_remove.append((start_pos, end_pos))
                # Count lines, adjusting for content before first newline
                prefix = sql_content[:start_pos]
                first_newline = prefix.find("\n")
                if first_newline == -1:
                    line_num = 1
                else:
                    line_num = prefix.count("\n", first_newline) + 1
                logs.append(f"Removed unmatched {{% endmacro %}} near line {line_num}")
            else:
                macro_stack.pop()
            continue

        # Handle endif
        if IF_END.match(tag_content):
            if not if_stack:
                to_remove.append((start_pos, end_pos))
                # Count lines, adjusting for content before first newline
                prefix = sql_content[:start_pos]
                first_newline = prefix.find("\n")
                if first_newline == -1:
                    line_num = 1
                else:
                    line_num = prefix.count("\n", first_newline) + 1
                logs.append(f"Removed unmatched {{% endif %}} near line {line_num}")
            else:
                if_stack.pop()

    # Remove the unmatched tags from end to start to maintain correct positions
    result = sql_content
    for start, end in sorted(to_remove, reverse=True):
        result = result[:start] + result[end:]

    return result, logs


def restructure_owner_properties(
    node: Dict[str, Any], node_type: str, schema_specs: SchemaSpecs
) -> Tuple[Dict[str, Any], bool, List[str]]:
    """Restructure owner properties according to dbt conventions.

    Args:
        node: The node dictionary to process
        node_type: The type of node to process
        schema_specs: The schema specifications to use

    Returns:
        Tuple containing:
        - The processed node dictionary
        - Boolean indicating if changes were made
        - List of refactor logs
    """
    refactored = False
    refactor_logs: List[str] = []
    pretty_node_type = node_type[:-1].title()

    if "owner" in node and isinstance(node["owner"], dict):
        owner = node["owner"]
        owner_copy = owner.copy()

        for field in owner_copy:
            if field not in schema_specs.owner_properties:
                refactored = True
                if "config" not in node:
                    node["config"] = {"meta": {}}
                if "meta" not in node["config"]:
                    node["config"]["meta"] = {}
                node["config"]["meta"][field] = owner[field]
                del owner[field]
                refactor_logs.append(
                    f"{pretty_node_type} '{node['name']}' - Owner field '{field}' moved under config.meta."
                )

    return node, refactored, refactor_logs


def changeset_remove_tab_only_lines(yml_str: str) -> YMLRuleRefactorResult:
    """Remove lines that contain only tabs from YAML files.

    Args:
        yml_str: The YAML string to process

    Returns:
        YMLRuleRefactorResult containing the refactored YAML and any changes made
    """
    refactored = False
    refactor_logs: List[str] = []

    # Process each line
    lines = yml_str.splitlines()
    new_lines = []
    for i, line in enumerate(lines):
        if "\t" in line and line.strip() == "":
            refactored = True
            refactor_logs.append(f"Removed line containing only tabs on line {i + 1}")
            new_lines.append("")
        else:
            new_lines.append(line)

    refactored_yaml = "\n".join(new_lines) if refactored else yml_str

    return YMLRuleRefactorResult(
        rule_name="remove_tab_only_lines",
        dbt_deprecation_classes=[],
        refactored=refactored,
        refactored_yaml=refactored_yaml,
        original_yaml=yml_str,
        refactor_logs=refactor_logs,
    )


def process_yaml_files_except_dbt_project(
    root_path: Path,
    model_paths: Iterable[str],
    schema_specs: SchemaSpecs,
    dry_run: bool = False,
    select: Optional[List[str]] = None,
    behavior_change: bool = False,
) -> List[YMLRefactorResult]:
    """Process all YAML files in the project

    Args:
        path: Project root path
        model_paths: Paths to process
        schema_specs: The schema specifications to use
        dry_run: Whether to perform a dry run
        select: Optional list of paths to select
        behavior_change: Whether to apply only resource name space replacement changes
    """
    yaml_results: List[YMLRefactorResult] = []

    for model_path in model_paths:
        yaml_files = set((root_path / Path(model_path)).resolve().glob("**/*.yml")).union(
            set((root_path / Path(model_path)).resolve().glob("**/*.yaml"))
        )
        for yml_file in yaml_files:
            if skip_file(yml_file, select):
                continue

            yml_str = yml_file.read_text()
            yml_refactor_result = YMLRefactorResult(
                dry_run=dry_run,
                file_path=yml_file,
                refactored=False,
                refactored_yaml=yml_str,
                original_yaml=yml_str,
                refactors=[],
            )

            # Define the changesets to apply in order
            if behavior_change:
                changesets = [
                    (changeset_replace_spaces_underscores_in_name_values, schema_specs),
                ]
            else:
                changesets = [
                    (changeset_remove_tab_only_lines, None),
                    (changeset_remove_indentation_version, None),
                    (changeset_remove_extra_tabs, None),
                    (changeset_remove_duplicate_keys, None),
                    (changeset_replace_spaces_underscores_in_name_values, schema_specs),
                    (changeset_refactor_yml_str, schema_specs),
                    (changeset_owner_properties_yml_str, schema_specs),
                ]

            # Apply each changeset in sequence
            try:
                for changeset_func, changeset_args in changesets:
                    if changeset_args is None:
                        changeset_result = changeset_func(yml_refactor_result.refactored_yaml)
                    else:
                        changeset_result = changeset_func(yml_refactor_result.refactored_yaml, changeset_args)

                    if changeset_result.refactored:
                        yml_refactor_result.refactors.append(changeset_result)
                        yml_refactor_result.refactored = True
                        yml_refactor_result.refactored_yaml = changeset_result.refactored_yaml

                yaml_results.append(yml_refactor_result)

            except Exception as e:
                error_console.print(f"Error processing YAML at path {yml_file}: {e}", style="bold red")
                raise e

    return yaml_results


def process_dbt_project_yml(
    root_path: Path, schema_specs: SchemaSpecs, dry_run: bool = False, exclude_dbt_project_keys: bool = False
) -> YMLRefactorResult:
    """Process dbt_project.yml"""
    if not (root_path / "dbt_project.yml").exists():
        error_console.print(f"Error: dbt_project.yml not found in {root_path}", style="red")
        return YMLRefactorResult(
            dry_run=dry_run,
            file_path=root_path / "dbt_project.yml",
            refactored=False,
            refactored_yaml="",
            original_yaml="",
            refactors=[],
        )

    yml_str = (root_path / "dbt_project.yml").read_text()
    yml_refactor_result = YMLRefactorResult(
        dry_run=dry_run,
        file_path=root_path / "dbt_project.yml",
        refactored=False,
        refactored_yaml=yml_str,
        original_yaml=yml_str,
        refactors=[],
    )

    changesets = [
        (changeset_remove_duplicate_keys, None),
        (changeset_dbt_project_remove_deprecated_config, exclude_dbt_project_keys),
        (changeset_dbt_project_prefix_plus_for_config, root_path, schema_specs),
    ]

    for changeset_func, *changeset_args in changesets:
        if changeset_args[0] is None:
            changeset_result = changeset_func(yml_refactor_result.refactored_yaml)
        elif len(changeset_args) == 1:
            changeset_result = changeset_func(yml_refactor_result.refactored_yaml, changeset_args[0])
        else:
            changeset_result = changeset_func(yml_refactor_result.refactored_yaml, *changeset_args)

        if changeset_result.refactored:
            yml_refactor_result.refactors.append(changeset_result)
            yml_refactor_result.refactored = True
            yml_refactor_result.refactored_yaml = changeset_result.refactored_yaml

    return yml_refactor_result


def skip_file(file_path: Path, select: Optional[List[str]] = None) -> bool:
    """Skip a file if a select list is provided and the file is not in the select list"""
    if select:
        return not any([Path(select_path).resolve().as_posix() in file_path.as_posix() for select_path in select])
    else:
        return False


def process_sql_files(
    path: Path, sql_paths: Iterable[str], dry_run: bool = False, select: Optional[List[str]] = None
) -> List[SQLRefactorResult]:
    """Process all SQL files in the given paths for unmatched endings.

    Args:
        path: Base project path
        sql_paths: Set of paths relative to project root where SQL files are located
        dry_run: Whether to perform a dry run
        select: Optional list of paths to select

    Returns:
        List of SQLRefactorResult for each processed file
    """
    results: List[SQLRefactorResult] = []

    for sql_path in sql_paths:
        full_path = (path / sql_path).resolve()
        if not full_path.exists():
            error_console.print(f"Warning: Path {full_path} does not exist", style="yellow")
            continue

        sql_files = full_path.glob("**/*.sql")
        for sql_file in sql_files:
            if skip_file(full_path, select):
                continue

            try:
                content = sql_file.read_text()
                new_content, logs = remove_unmatched_endings(content)

                results.append(
                    SQLRefactorResult(
                        dry_run=dry_run,
                        file_path=sql_file,
                        refactored=new_content != content,
                        refactored_content=new_content,
                        original_content=content,
                        refactors=[
                            SQLRuleRefactorResult(
                                rule_name="remove_unmatched_endings",
                                refactored=new_content != content,
                                refactored_content=new_content,
                                original_content=content,
                                refactor_logs=logs,
                                dbt_deprecation_classes=["UnexpectedJinjaBlockDeprecation"],
                            )
                        ],
                    )
                )
            except Exception as e:
                error_console.print(f"Error processing {sql_file}: {e}", style="bold red")

    return results


def restructure_yaml_keys_for_node(
    node: Dict[str, Any], node_type: str, schema_specs: SchemaSpecs
) -> Tuple[Dict[str, Any], bool, List[str]]:
    """Restructure YAML keys according to dbt conventions.

    Args:
        node: The node dictionary to process
        node_type: The type of node to process
        schema_specs: The schema specifications to use

    Returns:
        Tuple containing:
        - The processed model dictionary
        - Boolean indicating if changes were made
        - List of refactor logs
    """
    refactored = False
    refactor_logs: List[str] = []
    existing_meta = node.get("meta", {}).copy()
    pretty_node_type = node_type[:-1].title()

    # we can not loop node and modify it at the same time
    copy_node = node.copy()

    for field in copy_node:
        if field in schema_specs.yaml_specs_per_node_type[node_type].allowed_properties:
            continue

        if field in schema_specs.yaml_specs_per_node_type[node_type].allowed_config_fields_without_meta:
            refactored = True
            node_config = node.get("config", {})

            # if the field is not under config, move it under config
            if field not in node_config:
                node_config.update({field: node[field]})
                refactor_logs.append(
                    f"{pretty_node_type} '{node.get('name', '')}' - Field '{field}' moved under config."
                )
                node["config"] = node_config

            # if the field is already under config, it will take precedence there, so we remove it from the top level
            else:
                refactor_logs.append(
                    f"{pretty_node_type} '{node.get('name', '')}' - Field '{field}' is already under config, it has been removed from the top level."
                )
            del node[field]

        if field not in schema_specs.yaml_specs_per_node_type[node_type].allowed_config_fields:
            refactored = True
            closest_match = difflib.get_close_matches(
                field,
                schema_specs.yaml_specs_per_node_type[node_type].allowed_config_fields.union(
                    set(schema_specs.yaml_specs_per_node_type[node_type].allowed_properties)
                ),
                1,
            )
            if closest_match:
                refactor_logs.append(
                    f"{pretty_node_type} '{node.get('name', '')}' - Field '{field}' is not allowed, but '{closest_match[0]}' is. Moved as-is under config.meta but you might want to rename it and move it under config."
                )
            else:
                refactor_logs.append(
                    f"{pretty_node_type} '{node.get('name', '')}' - Field '{field}' is not an allowed config - Moved under config.meta."
                )
            node_meta = node.get("config", {}).get("meta", {})
            node_meta.update({field: node[field]})
            node["config"] = {"meta": node_meta}
            del node[field]

    if existing_meta:
        refactored = True
        refactor_logs.append(
            f"{pretty_node_type} '{node.get('name', '')}' - Moved all the meta fields under config.meta and merged with existing config.meta."
        )
        if "config" not in node:
            node["config"] = {"meta": {}}
        if "meta" not in node["config"]:
            node["config"]["meta"] = {}
        for key, value in existing_meta.items():
            node["config"]["meta"].update({key: value})
        del node["meta"]

    return node, refactored, refactor_logs


def restructure_yaml_keys_for_test(
    test: Dict[str, Any], schema_specs: SchemaSpecs
) -> Tuple[Dict[str, Any], bool, List[str]]:
    """Restructure YAML keys for tests according to dbt conventions.
    Tests are separated from other nodes because
    - they don't support meta
    - they can be either a string or a dict
    - when they are a dict, the top level ist just the test name

    Args:
        test: The test dictionary to process
        schema_specs: The schema specifications to use

    Returns:
        Tuple containing:
        - The processed test dictionary
        - Boolean indicating if changes were made
        - List of refactor logs
    """
    refactored = False
    refactor_logs: List[str] = []
    pretty_node_type = "Test"

    # if the test is a string, we leave it as is
    if isinstance(test, str):
        return test, False, []

    test_name = next(iter(test.keys()))
    copy_test = deepcopy(test)

    for field in copy_test[test_name]:
        if field in schema_specs.yaml_specs_per_node_type["tests"].allowed_config_fields_without_meta:
            refactored = True
            node_config = test[test_name].get("config", {})

            # if the field is not under config, move it under config
            if field not in node_config:
                node_config.update({field: test[test_name][field]})
                refactor_logs.append(f"{pretty_node_type} '{test_name}' - Field '{field}' moved under config.")
                test[test_name]["config"] = node_config

            # if the field is already under config, overwrite it and remove from top level
            else:
                node_config[field] = test[test_name][field]
                refactor_logs.append(
                    f"{pretty_node_type} '{test_name}' - Field '{field}' is already under config, it has been overwritten and removed from the top level."
                )
                test[test_name]["config"] = node_config
            del test[test_name][field]

    return test, refactored, refactor_logs


def changeset_owner_properties_yml_str(yml_str: str, schema_specs: SchemaSpecs) -> YMLRuleRefactorResult:
    """Generates a refactored YAML string from a single YAML file
    - moves all the owner fields that are not in owner_properties under config.meta
    """
    refactored = False
    refactor_logs: List[str] = []
    yml_dict = DbtYAML().load(yml_str) or {}

    for node_type in schema_specs.nodes_with_owner:
        if node_type in yml_dict:
            for i, node in enumerate(yml_dict[node_type]):
                processed_node, node_refactored, node_refactor_logs = restructure_owner_properties(
                    node, node_type, schema_specs
                )
                if node_refactored:
                    refactored = True
                    yml_dict[node_type][i] = processed_node
                    refactor_logs.extend(node_refactor_logs)

    return YMLRuleRefactorResult(
        rule_name="restructure_owner_properties",
        dbt_deprecation_classes=["CustomKeyInObjectDeprecation"],
        refactored=refactored,
        refactored_yaml=dict_to_yaml_str(yml_dict) if refactored else yml_str,
        original_yaml=yml_str,
        refactor_logs=refactor_logs,
    )


def changeset_refactor_yml_str(yml_str: str, schema_specs: SchemaSpecs) -> YMLRuleRefactorResult:  # noqa: PLR0912,PLR0915
    """Generates a refactored YAML string from a single YAML file
    - moves all the config fields under config
    - moves all the meta fields under config.meta and merges with existing config.meta
    - moves all the unknown fields under config.meta
    - provide some information if some fields don't exist but are similar to allowed fields
    """
    refactored = False
    refactor_logs: List[str] = []
    yml_dict = DbtYAML().load(yml_str) or {}

    for node_type in schema_specs.yaml_specs_per_node_type:
        if node_type in yml_dict:
            for i, node in enumerate(yml_dict[node_type]):
                processed_node, node_refactored, node_refactor_logs = restructure_yaml_keys_for_node(
                    node, node_type, schema_specs
                )
                if node_refactored:
                    refactored = True
                    yml_dict[node_type][i] = processed_node
                    refactor_logs.extend(node_refactor_logs)

                if "columns" in processed_node:
                    for column_i, column in enumerate(node["columns"]):
                        processed_column, column_refactored, column_refactor_logs = restructure_yaml_keys_for_node(
                            column, "columns", schema_specs
                        )
                        if column_refactored:
                            refactored = True
                            yml_dict[node_type][i]["columns"][column_i] = processed_column
                            refactor_logs.extend(column_refactor_logs)

                        # there might be some tests, but they can be called tests or data_tests
                        some_tests = {"tests", "data_tests"} & set(processed_column)
                        if some_tests:
                            test_key = next(iter(some_tests))
                            for test_i, test in enumerate(node["columns"][column_i][test_key]):
                                processed_test, test_refactored, test_refactor_logs = restructure_yaml_keys_for_test(
                                    test, schema_specs
                                )
                                if test_refactored:
                                    refactored = True
                                    yml_dict[node_type][i]["columns"][column_i][test_key][test_i] = processed_test
                                    refactor_logs.extend(test_refactor_logs)

                # if there are tests, we need to restructure them
                some_tests = {"tests", "data_tests"} & set(processed_node)
                if some_tests:
                    test_key = next(iter(some_tests))
                    for test_i, test in enumerate(node[test_key]):
                        processed_test, test_refactored, test_refactor_logs = restructure_yaml_keys_for_test(
                            test, schema_specs
                        )
                        if test_refactored:
                            refactored = True
                            yml_dict[node_type][i][test_key][test_i] = processed_test
                            refactor_logs.extend(test_refactor_logs)

    # for sources, the config can be set at the table level as well, which is one level lower
    if "sources" in yml_dict:
        for i, source in enumerate(yml_dict["sources"]):
            if "tables" in source:
                for j, table in enumerate(source["tables"]):
                    processed_source_table, source_table_refactored, source_table_refactor_logs = (
                        restructure_yaml_keys_for_node(table, "tables", schema_specs)
                    )
                    if source_table_refactored:
                        refactored = True
                        yml_dict["sources"][i]["tables"][j] = processed_source_table
                        refactor_logs.extend(source_table_refactor_logs)

                    some_tests = {"tests", "data_tests"} & set(processed_source_table)
                    if some_tests:
                        test_key = next(iter(some_tests))
                        for test_i, test in enumerate(source["tables"][j][test_key]):
                            processed_test, test_refactored, test_refactor_logs = restructure_yaml_keys_for_test(
                                test, schema_specs
                            )
                            if test_refactored:
                                refactored = True
                                yml_dict["sources"][i]["tables"][j][test_key][test_i] = processed_test
                                refactor_logs.extend(test_refactor_logs)

                    if "columns" in processed_source_table:
                        for table_column_i, table_column in enumerate(table["columns"]):
                            processed_table_column, table_column_refactored, table_column_refactor_logs = (
                                restructure_yaml_keys_for_node(table_column, "columns", schema_specs)
                            )
                            if table_column_refactored:
                                refactored = True
                                yml_dict["sources"][i]["tables"][j]["columns"][table_column_i] = processed_table_column
                                refactor_logs.extend(table_column_refactor_logs)

                            some_tests = {"tests", "data_tests"} & set(processed_table_column)
                            if some_tests:
                                test_key = next(iter(some_tests))
                                for test_i, test in enumerate(table_column[test_key]):
                                    processed_test, test_refactored, test_refactor_logs = (
                                        restructure_yaml_keys_for_test(test, schema_specs)
                                    )
                                    if test_refactored:
                                        refactored = True
                                        yml_dict["sources"][i]["tables"][j]["columns"][table_column_i][test_key][
                                            test_i
                                        ] = processed_test
                                        refactor_logs.extend(test_refactor_logs)

    return YMLRuleRefactorResult(
        rule_name="restructure_yaml_keys",
        dbt_deprecation_classes=["CustomKeyInConfigDeprecation"],
        refactored=refactored,
        refactored_yaml=dict_to_yaml_str(yml_dict) if refactored else yml_str,
        original_yaml=yml_str,
        refactor_logs=refactor_logs,
    )


def changeset_remove_extra_tabs(yml_str: str) -> YMLRuleRefactorResult:
    """Removes extra tabs in the YAML files"""
    refactored = False
    refactor_logs: List[str] = []

    current_yaml = yml_str

    while True:
        found_tab_error = False
        for p in yamllint.linter.run(current_yaml, yaml_config):
            if "found character '\\t' that cannot start any token" in p.desc:
                found_tab_error = True
                refactored = True
                refactor_logs.append(f"Found extra tabs: line {p.line} - column {p.column}")
                lines = current_yaml.split("\n")
                if p.line <= len(lines):
                    line = lines[p.line - 1]  # Convert to 0-based index
                    if p.column <= len(line):
                        # Replace tab character with NUM_SPACES_TO_REPLACE_TAB spaces
                        new_line = line[: p.column - 1] + " " * NUM_SPACES_TO_REPLACE_TAB + line[p.column :]
                        lines[p.line - 1] = new_line
                        current_yaml = "\n".join(lines)
                        break  # Exit the yamllint loop to restart with updated content

        if not found_tab_error:
            refactored_yaml = current_yaml
            break

    return YMLRuleRefactorResult(
        rule_name="remove_extra_tabs",
        dbt_deprecation_classes=[],
        refactored=refactored,
        refactored_yaml=refactored_yaml,
        original_yaml=yml_str,
        refactor_logs=refactor_logs,
    )


def changeset_remove_duplicate_keys(yml_str: str) -> YMLRuleRefactorResult:
    """Removes duplicate keys in the YAML files, keeping the first occurence only
    The drawback of keeping the first occurence is that we need to use PyYAML and then lose all the comments that were in the file
    """
    refactored = False
    refactor_logs: List[str] = []

    for p in yamllint.linter.run(yml_str, yaml_config):
        if p.rule == "key-duplicates":
            refactored = True
            refactor_logs.append(f"Found duplicate keys: line {p.line} - {p.desc}")

    if refactored:
        import yaml

        # we use dump from ruamel to keep indentation style but this loses quite a bit of formatting though
        refactored_yaml = DbtYAML().dump_to_string(yaml.safe_load(yml_str))  # type: ignore
    else:
        refactored_yaml = yml_str

    return YMLRuleRefactorResult(
        rule_name="remove_duplicate_keys",
        dbt_deprecation_classes=["DuplicateYAMLKeysDeprecation"],
        refactored=refactored,
        refactored_yaml=refactored_yaml,
        original_yaml=yml_str,
        refactor_logs=refactor_logs,
    )

def changeset_replace_spaces_underscores_in_name_values(yml_str: str, schema_specs: SchemaSpecs) -> YMLRuleRefactorResult:
    refactored = False
    refactor_logs: List[str] = []
    yml_dict = DbtYAML().load(yml_str) or {}

    for node_type in schema_specs.yaml_specs_per_node_type:
        if node_type in yml_dict:
            for i, node in enumerate(yml_dict[node_type]):
                processed_node, node_refactored, node_refactor_logs = replace_node_name_spaces_with_underscores(
                    node, node_type
                )
                if node_refactored:
                    refactored = True
                    yml_dict[node_type][i] = processed_node
                    refactor_logs.extend(node_refactor_logs)

    refactored_yaml = DbtYAML().dump_to_string(yml_dict) if refactored else yml_str

    return YMLRuleRefactorResult(
        rule_name="remove_spaces_in_resource_names",
        dbt_deprecation_classes=["ResourceNamesWithSpacesDeprecation", "ExposureNameDeprecation"],
        refactored=refactored,
        refactored_yaml=refactored_yaml,
        original_yaml=yml_str,
        refactor_logs=refactor_logs,
    )


def replace_node_name_spaces_with_underscores(node: dict[str, str], node_type: str):
    node_refactor_logs = []
    node_copy = node.copy()
    pretty_node_type = node_type[:-1].title()

    for key, value in node.items():
        if key == "name" and " " in value:
            new_value = value.replace(" ", "_")
            node_copy[key] = new_value
            node_refactor_logs.append(f"{pretty_node_type} '{node['name']} - Updated 'name' from '{value}' to '{new_value}'.")

    refactored = len(node_refactor_logs) != 0

    return node_copy, refactored, node_refactor_logs


def changeset_remove_indentation_version(yml_str: str) -> YMLRuleRefactorResult:
    """Standardizes the format of 'version: 2' in YAML files.

    This function looks for any variations of whitespace around 'version: 2' and
    standardizes them to the format 'version: 2'.

    Args:
        yml_str: The YAML string to process

    Returns:
        YMLRuleRefactorResult containing the refactored YAML and any changes made
    """
    refactored = False
    refactor_logs: List[str] = []

    # Pattern to match any whitespace around 'version: 2'
    pattern = r"^\s*version\s*:\s*2"
    replacement = "version: 2"

    # Process each line
    lines = yml_str.splitlines()
    for i, line in enumerate(lines):
        if re.match(pattern, line):
            if line != replacement:
                refactored = True
                lines[i] = replacement
                refactor_logs.append(f"Removed the extra indentation around 'version: 2' on line {i + 1}")

    refactored_yaml = "\n".join(lines) if refactored else yml_str

    return YMLRuleRefactorResult(
        rule_name="removed_extra_indentation",
        dbt_deprecation_classes=[],
        refactored=refactored,
        refactored_yaml=refactored_yaml,
        original_yaml=yml_str,
        refactor_logs=refactor_logs,
    )


def changeset_dbt_project_remove_deprecated_config(
    yml_str: str, exclude_dbt_project_keys: bool = False
) -> YMLRuleRefactorResult:
    """Remove deprecated keys"""
    refactored = False
    refactor_logs: List[str] = []
    dbt_deprecation_classes: List[str] = []

    dict_deprecated_fields_with_defaults = {
        "log-path": "logs",
        "target-path": "target",
    }

    dict_renamed_fields = {
        "data-paths": "seed-paths",
        "source-paths": "model-paths",
    }

    dict_fields_to_deprecation_class = {
        "log-path": "ConfigLogPathDeprecation",
        "target-path": "ConfigTargetPathDeprecation",
        "data-paths": "ConfigDataPathDeprecation",
        "source-paths": "ConfigSourcePathDeprecation",
    }

    yml_dict = DbtYAML().load(yml_str) or {}

    for deprecated_field, _ in dict_deprecated_fields_with_defaults.items():
        if deprecated_field in yml_dict:
            if not exclude_dbt_project_keys:
                # by default we remove it
                refactored = True
                refactor_logs.append(f"Removed the deprecated field '{deprecated_field}'")
                dbt_deprecation_classes.append(dict_fields_to_deprecation_class[deprecated_field])
                del yml_dict[deprecated_field]
            # with the special field, we only remove it if it's different from the default
            elif yml_dict[deprecated_field] != dict_deprecated_fields_with_defaults[deprecated_field]:
                refactored = True
                refactor_logs.append(
                    f"Removed the deprecated field '{deprecated_field}' that wasn't set to the default value"
                )
                dbt_deprecation_classes.append(dict_fields_to_deprecation_class[deprecated_field])
                del yml_dict[deprecated_field]

    # TODO: add tests for this
    for deprecated_field, new_field in dict_renamed_fields.items():
        if deprecated_field in yml_dict:
            refactored = True
            if new_field not in yml_dict:
                refactor_logs.append(f"Renamed the deprecated field '{deprecated_field}' to '{new_field}'")
                dbt_deprecation_classes.append(dict_fields_to_deprecation_class[deprecated_field])
                yml_dict[new_field] = yml_dict[deprecated_field]
            else:
                refactor_logs.append(f"Added the config of the deprecated field '{deprecated_field}' to '{new_field}'")
                dbt_deprecation_classes.append(dict_fields_to_deprecation_class[deprecated_field])
                yml_dict[new_field] = yml_dict[new_field] + yml_dict[deprecated_field]
            del yml_dict[deprecated_field]

    return YMLRuleRefactorResult(
        rule_name="remove_deprecated_config",
        dbt_deprecation_classes=dbt_deprecation_classes,
        refactored=refactored,
        refactored_yaml=DbtYAML().dump_to_string(yml_dict) if refactored else yml_str,  # type: ignore
        original_yaml=yml_str,
        refactor_logs=refactor_logs,
    )


def rec_check_yaml_path(
    yml_dict: Dict[str, Any],
    path: Path,
    node_fields: DbtProjectSpecs,
    refactor_logs: Optional[List[str]] = None,
):
    # we can't set refactor_logs as an empty list

    # TODO: what about individual models in the config there?
    # indivdual models would show up here but without the `.sql` (or `.py`)
    if not path.exists():
        return yml_dict, [] if refactor_logs is None else refactor_logs

    yml_dict_copy = yml_dict.copy() if yml_dict else {}
    for k, v in yml_dict_copy.items():
        if k in node_fields.allowed_config_fields_dbt_project and not (path / k).exists():
            new_k = f"+{k}"
            yml_dict[new_k] = v
            log_msg = f"Added '+' in front of the nested config '{k}'"
            if refactor_logs is None:
                refactor_logs = [log_msg]
            else:
                refactor_logs.append(log_msg)
            del yml_dict[k]
        elif isinstance(yml_dict[k], dict):
            new_dict, refactor_logs = rec_check_yaml_path(yml_dict[k], path / k, node_fields, refactor_logs)
            yml_dict[k] = new_dict
    return yml_dict, [] if refactor_logs is None else refactor_logs


def changeset_dbt_project_prefix_plus_for_config(
    yml_str: str, path: Path, schema_specs: SchemaSpecs
) -> YMLRuleRefactorResult:
    """Update keys for the config in dbt_project.yml under to prefix it with a `+`"""
    all_refactor_logs: List[str] = []

    yml_dict = DbtYAML().load(yml_str) or {}

    for node_type, node_fields in schema_specs.dbtproject_specs_per_node_type.items():
        for k, v in (yml_dict.get(node_type) or {}).copy().items():
            # check if this is the project name
            if k == yml_dict["name"]:
                new_dict, refactor_logs = rec_check_yaml_path(v, path / node_type, node_fields)
                yml_dict[node_type][k] = new_dict
                all_refactor_logs.extend(refactor_logs)

            # top level config
            elif k in node_fields.allowed_config_fields_dbt_project:
                all_refactor_logs.append(f"Added '+' in front of top level config '{k}'")
                new_k = f"+{k}"
                yml_dict[node_type][new_k] = v
                del yml_dict[node_type][k]

            # otherwise, treat it as a package
            # TODO: if this is not valid, we could delete it as well
            else:
                packages_path = path / Path(yml_dict.get("packages-paths", "dbt_packages"))
                new_dict, refactor_logs = rec_check_yaml_path(v, packages_path / k / node_type, node_fields)
                yml_dict[node_type][k] = new_dict
                all_refactor_logs.extend(refactor_logs)

    refactored = len(all_refactor_logs) > 0
    return YMLRuleRefactorResult(
        rule_name="prefix_plus_for_config",
        dbt_deprecation_classes=["GenericJSONSchemaValidationDeprecation"],
        refactored=refactored,
        refactored_yaml=DbtYAML().dump_to_string(yml_dict) if refactored else yml_str,  # type: ignore
        original_yaml=yml_str,
        refactor_logs=all_refactor_logs,
    )


def get_dbt_files_paths(path: Path, include_packages: bool = False) -> Set[str]:
    """Get model and macro paths from dbt_project.yml

    Args:
        path: Project root path
        include_packages: Whether to include packages in the refactoring

    Returns:
        A list of paths to the models, macros, tests, analyses, and snapshots
    """

    if not (path / "dbt_project.yml").exists():
        error_console.print(f"Error: dbt_project.yml not found in {path}", style="red")
        return set()

    with open(path / "dbt_project.yml", "r") as f:
        project_config = safe_load(f)
    model_paths = project_config.get("model-paths", ["models"])
    seed_paths = project_config.get("seed-paths", ["seeds"])
    macro_paths = project_config.get("macro-paths", ["macros"])
    test_paths = project_config.get("test-paths", ["tests"])
    analysis_paths = project_config.get("analysis-paths", ["analyses"])
    snapshot_paths = project_config.get("snapshot-paths", ["snapshots"])

    all_paths = set(model_paths + seed_paths + macro_paths + test_paths + analysis_paths + snapshot_paths)

    if include_packages:
        packages_path = project_config.get("packages-paths", "dbt_packages")
        packages_dir = path / packages_path

        if packages_dir.exists():
            for package_folder in packages_dir.iterdir():
                if package_folder.is_dir():
                    package_dbt_project = package_folder / "dbt_project.yml"
                    if package_dbt_project.exists():
                        with open(package_dbt_project, "r") as f:
                            package_config = safe_load(f)

                        package_model_paths = package_config.get("model-paths", ["models"])
                        package_seed_paths = package_config.get("seed-paths", ["seeds"])
                        package_macro_paths = package_config.get("macro-paths", ["macros"])
                        package_test_paths = package_config.get("test-paths", ["tests"])
                        package_analysis_paths = package_config.get("analysis-paths", ["analyses"])
                        package_snapshot_paths = package_config.get("snapshot-paths", ["snapshots"])

                        # Combine package folder path with each path type
                        for model_path in package_model_paths:
                            all_paths.add(str(package_folder / model_path))
                        for seed_path in package_seed_paths:
                            all_paths.add(str(package_folder / seed_path))
                        for macro_path in package_macro_paths:
                            all_paths.add(str(package_folder / macro_path))
                        for test_path in package_test_paths:
                            all_paths.add(str(package_folder / test_path))
                        for analysis_path in package_analysis_paths:
                            all_paths.add(str(package_folder / analysis_path))
                        for snapshot_path in package_snapshot_paths:
                            all_paths.add(str(package_folder / snapshot_path))

    return all_paths


def get_dbt_roots_paths(root_path: Path, include_packages: bool = False) -> Set[str]:
    """Get all dbt root paths, the main one and the ones under dbt_packages directory if we want to include packages.

    Args:
        root_path: Project root path

    Returns:
        Set of package folder paths as strings
    """
    dbt_roots_paths = {str(root_path)}
    dbt_packages_path = root_path / "dbt_packages"

    if include_packages and dbt_packages_path.exists() and dbt_packages_path.is_dir():
        for package_folder in dbt_packages_path.iterdir():
            if package_folder.is_dir():
                dbt_roots_paths.add(str(package_folder))

    return dbt_roots_paths


def changeset_all_sql_yml_files(  # noqa: PLR0913
    path: Path,
    schema_specs: SchemaSpecs,
    dry_run: bool = False,
    exclude_dbt_project_keys: bool = False,
    select: Optional[List[str]] = None,
    include_packages: bool = False,
    behavior_change: bool = False,
) -> Tuple[List[YMLRefactorResult], List[SQLRefactorResult]]:
    """Process all YAML files and SQL files in the project

    Args:
        path: Project root path
        schema_specs: The schema specifications to use
        dry_run: Whether to perform a dry run
        exclude_dbt_project_keys: Whether to exclude dbt project keys
        select: List of paths to select
        include_packages: Whether to include packages in the refactoring
        behavior_change: Whether to apply only resource name space replacement changes

    Returns:
        Tuple containing:
        - List of YAML refactor results
        - List of SQL refactor results
    """
    dbt_paths = get_dbt_files_paths(path, include_packages)
    dbt_roots_paths = get_dbt_roots_paths(path, include_packages)

    sql_results = process_sql_files(path, dbt_paths, dry_run, select)

    # Process YAML files
    yaml_results = process_yaml_files_except_dbt_project(path, dbt_paths, schema_specs, dry_run, select, behavior_change)

    # Process dbt_project.yml

    dbt_project_yml_results = []
    for dbt_root_path in dbt_roots_paths:
        dbt_project_yml_results.append(
            process_dbt_project_yml(Path(dbt_root_path), schema_specs, dry_run, exclude_dbt_project_keys)
        )

    return [*yaml_results, *dbt_project_yml_results], sql_results


def apply_changesets(
    yaml_results: List[YMLRefactorResult],
    sql_results: List[SQLRefactorResult],
    json_output: bool = False,
) -> None:
    """Apply both YAML and SQL refactoring changes

    Args:
        yaml_results: List of YAML refactoring results
        sql_results: List of SQL refactoring results
    """
    # Apply YAML changes
    for yaml_result in yaml_results:
        if yaml_result.refactored:
            yaml_result.update_yaml_file()
            yaml_result.print_to_console(json_output)

    # Apply SQL changes
    for sql_result in sql_results:
        if sql_result.refactored:
            sql_result.update_sql_file()
            sql_result.print_to_console(json_output)
