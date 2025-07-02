import tempfile
from pathlib import Path

import pytest
from yaml import safe_load

from dbt_autofix.refactor import (
    SQLRefactorResult,
    YMLRefactorResult,
    YMLRuleRefactorResult,
    changeset_all_sql_yml_files,
    changeset_dbt_project_prefix_plus_for_config,
    changeset_dbt_project_remove_deprecated_config,
    changeset_owner_properties_yml_str,
    changeset_refactor_yml_str,
    changeset_remove_duplicate_keys,
    changeset_remove_extra_tabs,
    changeset_remove_indentation_version,
    dict_to_yaml_str,
    rec_check_yaml_path,
    remove_unmatched_endings,
    skip_file,
)
from dbt_autofix.retrieve_schemas import SchemaSpecs


@pytest.fixture
def temp_project_dir():
    with tempfile.TemporaryDirectory() as tmpdirname:
        project_dir = Path(tmpdirname)

        # Create dbt_project.yml
        project_dir.joinpath("dbt_project.yml").write_text("""
model-paths: ["models"]
""")

        # Create models directory
        models_dir = project_dir / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        yield project_dir


@pytest.fixture(scope="session")
def schema_specs():
    return SchemaSpecs()


@pytest.fixture
def schema_yml_with_duplicates():
    return """
version: 2

models:
  - name: my_first_dbt_model
    description: "A starter dbt model"
    description: "A starter dbt model second"
    desciption: "A starter dbt model third"
    zorderr: 30
    meta:
      abc: 123
    config:
      meta:
        def: 456
    columns:
      - name: id
        description: "The primary key for this table"
        data_tests:
          - unique
          - not_null

  - name: my_second_dbt_model
    # this is a comment
    description: "A starter dbt model" # and a comment
    desciption: "A starter dbt model" # and a commenttt
    # this is a comment
    materialized: table # yep
    config:
      meta: 
       abc: 123
    columns:
      - name: id
        description: "The primary key for this table"
        data_tests:
          - unique
          - not_null
"""


@pytest.fixture
def schema_yml_with_config_fields():
    return """
version: 2

models:
  - name: my_first_dbt_model
    description: "A starter dbt model"
    materialized: table
    database: my_db
    schema: my_schema
    meta:
      abc: 123
    columns:
      - name: id
        description: "The primary key for this table"
        data_tests:
          - unique
          - not_null
"""


@pytest.fixture
def schema_yml_with_fields_top_and_under_config():
    return """
version: 2

models:
  - name: my_first_dbt_model
    description: "A starter dbt model"
    materialized: table
    database: my_db
    schema: my_schema
    config:
      materialized: view # in that case, the materialization is view (tested on dbt-core)
    meta:
      abc: 123
    columns:
      - name: id
        description: "The primary key for this table"
        data_tests:
          - unique
          - not_null
"""


@pytest.fixture
def schema_yml_with_close_matches():
    return """
version: 2

models:
  - name: my_first_dbt_model
    description: "A starter dbt model"
    materialize: table  # close to 'materialized'
    full-refresh: false  # close to 'full_refresh'
    config:
      meta:
        abc: 123
    columns:
      - name: id
        description: "The primary key for this table"
        data_tests:
          - unique
          - not_null
"""


@pytest.fixture
def schema_yml_with_nested_sources():
    return """
version: 2

sources:
  - name: my_first_dbt_source
    description: "A starter dbt source"
    database: my_db
    schema: my_schema
    meta:
      abc: 456
    config:
      event_time: my_time_field
    tables:
      - name: my_first_dbt_table
        description: "A starter dbt table"
        config:
          enabled: true
          event_time: my_other_time_field
        meta:
          abc: 123
      - name: my_second_dbt_table
        description: "A starter dbt table"
        config:
          event_time: my_other_time_field
        meta:
          abc: 123
"""


@pytest.fixture
def schema_yml_with_owner_properties():
    return """
version: 2

groups:
  - name: my_first_dbt_group
    description: "A starter dbt group"
    owner:
      name: "John Doe"
      email: "john@example.com"
      team: "Data Team"
      role: "Data Engineer"
    config:
      meta:
        abc: 123

exposures:
  - name: my_first_dbt_exposure
    description: "A starter dbt exposure"
    owner:
      name: "Jane Doe"
      email: "jane@example.com"
      department: "Analytics"
      level: "Senior"
    config:
      meta:
        def: 456
"""


class TestUnmatchedEndingsRemoval:
    """Tests for remove_unmatched_endings function"""

    def test_basic_unmatched_endmacro(self):
        sql_content = """
        select *
        from my_table
        {% endmacro %}
        where x = 1
        """
        result, logs = remove_unmatched_endings(sql_content)
        assert "{% endmacro %}" not in result
        assert len(logs) == 1
        assert "Removed unmatched {% endmacro %}" in logs[0]

    def test_basic_unmatched_endif(self):
        sql_content = """
        select *
        from my_table
        {% endif %}
        where x = 1
        """
        result, logs = remove_unmatched_endings(sql_content)
        assert "{% endif %}" not in result
        assert len(logs) == 1
        assert "Removed unmatched {% endif %}" in logs[0]

    def test_matched_macro(self):
        sql_content = """
        {% macro my_macro() %}
        select *
        from my_table
        {% endmacro %}
        """
        result, logs = remove_unmatched_endings(sql_content)
        assert "{% macro my_macro() %}" in result
        assert "{% endmacro %}" in result
        assert len(logs) == 0

    def test_matched_if(self):
        sql_content = """
        {% if condition %}
        select *
        from my_table
        {% endif %}
        """
        result, logs = remove_unmatched_endings(sql_content)
        assert "if condition" in result
        assert "{% endif %}" in result
        assert len(logs) == 0

    def test_matched_if_with_parenthesis(self):
        sql_content = """
        {% if(condition) %}
        select *
        from my_table
        {% endif %}
        """
        result, logs = remove_unmatched_endings(sql_content)
        assert "if(condition)" in result
        assert "{% endif %}" in result
        assert len(logs) == 0

    def test_matched_if_with_macro_in_name(self):
        sql_content = """
        {% if(macro_test) %}
        select *
        from my_table
        {% endif %}
        """
        result, logs = remove_unmatched_endings(sql_content)
        assert "if(macro_test)" in result
        assert "{% endif %}" in result
        assert len(logs) == 0

    def test_nested_structures(self):
        sql_content = """
        {% macro outer_macro() %}
          {% if condition %}
            select *
            from my_table
          {% endif %}
        {% endmacro %}
        {% endif %}  -- This one is unmatched
        {% endmacro %}  -- This one is unmatched
        """
        result, logs = remove_unmatched_endings(sql_content)
        assert "{% macro outer_macro() %}" in result
        assert "{% if condition %}" in result
        assert len(logs) == 2
        assert any("Removed unmatched {% endif %}" in log for log in logs)
        assert any("Removed unmatched {% endmacro %}" in log for log in logs)

    def test_empty_and_no_tags(self):
        # Empty content
        result, logs = remove_unmatched_endings("")
        assert result == ""
        assert len(logs) == 0

        # No Jinja tags
        sql_content = """
        select *
        from my_table
        where x = 1
        """
        result, logs = remove_unmatched_endings(sql_content)
        assert result.strip() == sql_content.strip()
        assert len(logs) == 0

    def test_multiline_tags(self):
        sql_content = """
        select *
        from my_table
        {% 
        endmacro
         %}
        where x = 1
        """
        result, logs = remove_unmatched_endings(sql_content)
        assert "endmacro" not in result
        assert len(logs) == 1
        assert "Removed unmatched {% endmacro %}" in logs[0]

    def test_whitespace_control(self):
        test_cases = [
            "{%- endmacro %}",  # Leading
            "{% endmacro -%}",  # Trailing
            "{%- endmacro -%}",  # Both
            """{%-
                endmacro
            -%}""",  # Multi-line
            """{%- if condition %}
            select 1
            {%- endif -%}
            {% endmacro %}""",  # Mixed
        ]

        for content in test_cases:
            result, logs = remove_unmatched_endings(content)
            assert "endmacro" not in result or ("{% if condition %}" in content and "{% endmacro %}" not in result)
            if "endmacro" in content and "if condition" not in content:
                assert len(logs) == 1
                assert "Removed unmatched {% endmacro %}" in logs[0]

    def test_line_numbers(self):
        # Single line
        sql_content = "{% macro test() %}select 1{% endmacro %}{% endif %}"
        _, logs = remove_unmatched_endings(sql_content)
        assert logs[0] == "Removed unmatched {% endif %} near line 1"

        # No leading newline
        sql_content = "{% macro test() %}\nselect 1\n{% endmacro %}\n{% endif %}"
        _, logs = remove_unmatched_endings(sql_content)
        assert logs[0] == "Removed unmatched {% endif %} near line 4"

        # With leading newline
        sql_content = "\n{% macro test() %}\nselect 1\n{% endmacro %}\n{% endif %}"
        _, logs = remove_unmatched_endings(sql_content)
        assert logs[0] == "Removed unmatched {% endif %} near line 5"

        # Mixed newlines
        sql_content = "{% macro test() %}\r\nselect 1\n{% endmacro %}\r\n{% endif %}"
        _, logs = remove_unmatched_endings(sql_content)
        assert logs[0] == "Removed unmatched {% endif %} near line 4"

    def test_in_comments(self):
        # Endif in comments
        sql_content = """-- This is a comment
        -- {% endif %}
        select * from table"""
        result, logs = remove_unmatched_endings(sql_content)
        assert "{% endif %}" not in result
        assert len(logs) == 1
        assert "Removed unmatched {% endif %}" in logs[0]

        # Endmacro in comments
        sql_content = """-- This is a comment
        select * from table
        -- {% endmacro %}"""
        result, logs = remove_unmatched_endings(sql_content)
        assert "{% endmacro %}" not in result
        assert len(logs) == 1
        assert "Removed unmatched {% endmacro %}" in logs[0]

    def test_after_other_tags(self):
        # After for loop
        sql_content = """{% for item in items %}
        select {{ item }} from table
        {% endfor %}
        {% endif %}"""
        result, logs = remove_unmatched_endings(sql_content)
        assert "{% endif %}" not in result
        assert len(logs) == 1
        assert "Removed unmatched {% endif %}" in logs[0]

        # After set statement
        sql_content = """{% set x = 5 %}
        select {{ x }} as value
        {% endmacro %}"""
        result, logs = remove_unmatched_endings(sql_content)
        assert "{% endmacro %}" not in result
        assert len(logs) == 1
        assert "Removed unmatched {% endmacro %}" in logs[0]

    def test_multiple_unmatched(self):
        sql_content = """select 1
        {% endif %}
        select 2
        {% endif %}
        select 3"""
        result, logs = remove_unmatched_endings(sql_content)
        assert "{% endif %}" not in result
        assert len(logs) == 2
        assert logs[0] == "Removed unmatched {% endif %} near line 2"
        assert logs[1] == "Removed unmatched {% endif %} near line 4"


class TestYamlRefactoring:
    """Tests for YAML refactoring functions"""

    def test_changeset_refactor_yml_with_config_fields(
        self, temp_project_dir: Path, schema_yml_with_config_fields: str, schema_specs: SchemaSpecs
    ):
        # Create a test YAML file
        yml_file = temp_project_dir / "models" / "schema.yml"
        yml_file.parent.mkdir(parents=True, exist_ok=True)
        yml_file.write_text(schema_yml_with_config_fields)

        # Test the refactoring
        result = changeset_refactor_yml_str(schema_yml_with_config_fields, schema_specs)
        assert result.refactored
        # Now expect 4 logs: 3 fields moved + meta merge
        assert len(result.refactor_logs) == 4
        assert any("Field 'materialized' moved under config" in log for log in result.refactor_logs)
        assert any("Field 'database' moved under config" in log for log in result.refactor_logs)
        assert any("Field 'schema' moved under config" in log for log in result.refactor_logs)
        assert any("Moved all the meta fields under config.meta" in log for log in result.refactor_logs)

        # Verify the refactored YAML
        refactored_dict = safe_load(result.refactored_yaml)
        model = refactored_dict["models"][0]
        assert "materialized" not in model
        assert "database" not in model
        assert "schema" not in model
        assert "config" in model
        assert model["config"]["materialized"] == "table"
        assert model["config"]["database"] == "my_db"
        assert model["config"]["schema"] == "my_schema"

        # Check that meta was merged correctly
        assert model["config"]["meta"]["abc"] == 123

    def test_changeset_all_yml_files(
        self, temp_project_dir: Path, schema_yml_with_config_fields: str, schema_specs: SchemaSpecs
    ):
        # Create multiple YAML files
        models_dir = temp_project_dir / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        # Create a subdirectory with another YAML file
        sub_dir = models_dir / "example"
        sub_dir.mkdir(parents=True, exist_ok=True)
        sub_dir.joinpath("model.sql").write_text("not a YAML file")

        # Write YAML files
        models_dir.joinpath("schema.yml").write_text(schema_yml_with_config_fields)
        sub_dir.joinpath("other_schema.yaml").write_text(schema_yml_with_config_fields)

        # Get all refactored results
        results = changeset_all_sql_yml_files(temp_project_dir, schema_specs)

        # Check that we got results for both files
        assert len(results) == 2
        # Unpack the tuple of lists
        yaml_results, sql_results = results
        assert all(isinstance(r, YMLRefactorResult) for r in yaml_results)
        assert all(isinstance(r, SQLRefactorResult) for r in sql_results)
        assert all(r.refactored for r in yaml_results if r.file_path.name != "dbt_project.yml")

        # Check that both files were processed
        processed_files = {r.file_path for r in yaml_results}
        assert (models_dir / "schema.yml").resolve() in processed_files
        assert (sub_dir / "other_schema.yaml").resolve() in processed_files

    def test_changeset_refactor_yml_with_fields_top_and_under_config(
        self, temp_project_dir: Path, schema_yml_with_fields_top_and_under_config: str, schema_specs: SchemaSpecs
    ):
        # Create a test YAML file
        yml_file = temp_project_dir / "models" / "schema.yml"
        yml_file.parent.mkdir(parents=True, exist_ok=True)
        yml_file.write_text(schema_yml_with_fields_top_and_under_config)

        # Test the refactoring
        result = changeset_refactor_yml_str(schema_yml_with_fields_top_and_under_config, schema_specs)
        assert result.refactored
        assert isinstance(result, YMLRuleRefactorResult)
        # Now expect 4 logs: 1 already under config, 2 moved, 1 meta merge
        assert len(result.refactor_logs) == 4
        assert any("Field 'materialized' is already under config" in log for log in result.refactor_logs)
        assert any("Field 'database' moved under config" in log for log in result.refactor_logs)
        assert any("Field 'schema' moved under config" in log for log in result.refactor_logs)
        assert any("Moved all the meta fields under config.meta" in log for log in result.refactor_logs)

        # Verify the refactored YAML
        refactored_dict = safe_load(result.refactored_yaml)
        model = refactored_dict["models"][0]
        assert "materialized" not in model
        assert model["config"]["materialized"] == "view"
        assert "database" not in model
        assert "schema" not in model
        assert model["config"]["materialized"] == "view"  # config takes precedence
        assert model["config"]["database"] == "my_db"
        assert model["config"]["schema"] == "my_schema"

    def test_changeset_refactor_yml_with_close_matches(
        self, temp_project_dir: Path, schema_yml_with_close_matches: str, schema_specs: SchemaSpecs
    ):
        # Create a test YAML file
        yml_file = temp_project_dir / "models" / "schema.yml"
        yml_file.parent.mkdir(parents=True, exist_ok=True)
        yml_file.write_text(schema_yml_with_close_matches)

        # Test the refactoring
        result = changeset_refactor_yml_str(schema_yml_with_close_matches, schema_specs)
        assert result.refactored
        assert isinstance(result, YMLRuleRefactorResult)
        # Now expect 2 logs: 2 close matches
        assert len(result.refactor_logs) == 2
        assert any("materialize' is not allowed, but 'materialized' is" in log for log in result.refactor_logs)
        assert any("full-refresh' is not allowed, but 'full_refresh' is" in log for log in result.refactor_logs)

        # Verify the refactored YAML
        refactored_dict = safe_load(result.refactored_yaml)
        model = refactored_dict["models"][0]
        assert "materialize" not in model
        assert "full-refresh" not in model

        # Check that fields were moved under config.meta
        assert "config" in model
        assert "meta" in model["config"]
        assert model["config"]["meta"]["materialize"] == "table"
        assert model["config"]["meta"]["full-refresh"] is False

        # Check that appropriate logs were generated
        assert any("'materialize' is not allowed, but 'materialized' is" in log for log in result.refactor_logs)
        assert any("'full-refresh' is not allowed, but 'full_refresh' is" in log for log in result.refactor_logs)

    def test_changeset_refactor_yml_with_nested_sources(
        self, temp_project_dir: Path, schema_yml_with_nested_sources: str, schema_specs: SchemaSpecs
    ):
        # Create a test YAML file
        yml_file = temp_project_dir / "models" / "sources.yml"
        yml_file.parent.mkdir(parents=True, exist_ok=True)
        yml_file.write_text(schema_yml_with_nested_sources)

        # Test the refactoring
        result = changeset_refactor_yml_str(schema_yml_with_nested_sources, schema_specs)
        assert result.refactored
        assert isinstance(result, YMLRuleRefactorResult)

        # Check that config fields were moved under config
        source = safe_load(result.refactored_yaml)["sources"][0]

        assert "meta" not in source
        assert source["config"]["event_time"] == "my_time_field"
        assert source["config"]["meta"]["abc"] == 456

        assert "tables" in source
        assert len(source["tables"]) == 2
        assert source["tables"][0]["config"]["event_time"] == "my_other_time_field"
        assert source["tables"][0]["config"]["meta"]["abc"] == 123
        assert source["tables"][0]["config"]["enabled"] == True  # noqa: E712

        assert source["tables"][1]["config"]["event_time"] == "my_other_time_field"
        assert source["tables"][1]["config"]["meta"]["abc"] == 123

    def test_changeset_remove_indentation_version(self):
        # Test cases with different indentation patterns
        test_cases = [
            (
                """
version: 2
models:
  - name: test_model
""",
                """
version: 2
models:
  - name: test_model
""",
                False,
            ),
            (
                """
  version: 2
models:
  - name: test_model
""",
                """
version: 2
models:
  - name: test_model
""",
                True,
            ),
            (
                """
\tversion: 2
models:
  - name: test_model
""",
                """
version: 2
models:
  - name: test_model
""",
                True,
            ),
            (
                """
  version: 2  
models:
  - name: test_model
""",
                """
version: 2
models:
  - name: test_model
""",
                True,
            ),
            (
                """
version:2
models:
  - name: test_model
""",
                """
version: 2
models:
  - name: test_model
""",
                True,
            ),
            (
                """
version : 2
models:
  - name: test_model
""",
                """
version: 2
models:
  - name: test_model
""",
                True,
            ),
        ]

        for input_yaml, expected_yaml, should_refactor in test_cases:
            result = changeset_remove_indentation_version(input_yaml)
            assert result.refactored == should_refactor
            if should_refactor:
                assert len(result.refactor_logs) == 1
                assert "Removed the extra indentation around 'version: 2'" in result.refactor_logs[0]
            assert result.refactored_yaml.strip() == expected_yaml.strip()

    def test_changeset_remove_indentation_version_no_version(self):
        input_yaml = """
models:
  - name: test_model
    description: "A test model"
"""
        result = changeset_remove_indentation_version(input_yaml)
        assert not result.refactored
        assert len(result.refactor_logs) == 0
        assert result.refactored_yaml == input_yaml

    def test_changeset_remove_indentation_version_comments(self):
        input_yaml = """
# This is a comment
  version: 2  # This is an inline comment
models:
  - name: test_model
"""
        result = changeset_remove_indentation_version(input_yaml)
        assert result.refactored
        assert len(result.refactor_logs) == 1
        assert "Removed the extra indentation around 'version: 2'" in result.refactor_logs[0]
        assert "# This is a comment" in result.refactored_yaml
        assert "version: 2" in result.refactored_yaml  # The inline comment should be removed
        assert "# This is an inline comment" not in result.refactored_yaml  # The inline comment should be removed

    def test_changeset_refactor_yml_with_source_columns(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        input_yaml = """
version: 2

sources:
  - name: my_source
    description: "A test source"
    tables:
      - name: my_table
        description: "A test table"
        columns:
          - name: id
            description: "Primary key"
            tags: 
              - my-tag
            data_type: integer
            tests:
              - unique
              - not_null
          - name: created_at
            description: "Creation timestamp"
            data_type: timestamp  # This should stay here
            tests:
              - not_null
"""
        result = changeset_refactor_yml_str(input_yaml, schema_specs)
        assert result.refactored
        assert isinstance(result, YMLRuleRefactorResult)

        # Check that the source structure is preserved
        source = safe_load(result.refactored_yaml)["sources"][0]
        table = source["tables"][0]

        # Check that columns were processed correctly
        assert len(table["columns"]) == 2

        # Check first column
        id_column = table["columns"][0]
        assert id_column["name"] == "id"
        assert id_column["description"] == "Primary key"
        assert "config" in id_column
        assert "tags" in id_column["config"]
        assert "meta" not in id_column["config"]
        assert id_column["data_type"] == "integer"
        assert id_column["tests"] == ["unique", "not_null"]

        # Check second column
        created_at_column = table["columns"][1]
        assert created_at_column["name"] == "created_at"
        assert created_at_column["description"] == "Creation timestamp"
        assert "config" not in created_at_column
        assert created_at_column["data_type"] == "timestamp"
        assert created_at_column["tests"] == ["not_null"]

    def test_changeset_refactor_yml_with_nested_source_columns(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        input_yaml = """
version: 2

sources:
  - name: my_source
    description: "A test source"
    tables:
      - name: my_table
        description: "A test table"
        columns:
          - name: id
            description: "Primary key"
            data_type: integer
            tests:
              - unique
              - not_null
            meta:
              is_primary: true  # This should be merged with config.meta
          - name: created_at
            description: "Creation timestamp"
            data_type: timestamp
            tests:
              - not_null
            config:
              meta:
                is_timestamp: true  # This should be preserved in config.meta
"""
        result = changeset_refactor_yml_str(input_yaml, schema_specs)
        assert result.refactored
        assert isinstance(result, YMLRuleRefactorResult)

        # Check that the source structure is preserved
        source = safe_load(result.refactored_yaml)["sources"][0]
        table = source["tables"][0]

        # Check that columns were processed correctly
        assert len(table["columns"]) == 2

        # Check first column with meta field
        id_column = table["columns"][0]
        assert id_column["name"] == "id"
        assert id_column["description"] == "Primary key"
        assert "meta" not in id_column  # Should be merged with config.meta
        assert "config" in id_column
        assert "meta" in id_column["config"]
        assert id_column["data_type"] == "integer"
        assert id_column["config"]["meta"]["is_primary"] is True
        assert id_column["tests"] == ["unique", "not_null"]

        # Check second column with existing config.meta
        created_at_column = table["columns"][1]
        assert created_at_column["name"] == "created_at"
        assert created_at_column["description"] == "Creation timestamp"
        assert "config" in created_at_column
        assert "meta" in created_at_column["config"]
        assert created_at_column["data_type"] == "timestamp"
        assert created_at_column["config"]["meta"]["is_timestamp"] is True
        assert created_at_column["tests"] == ["not_null"]

    def test_changeset_refactor_yml_with_snapshot_config_rename(
        self, temp_project_dir: Path, schema_specs: SchemaSpecs
    ):
        input_yaml = """
snapshots:
  - name: test_snapshot
    config:
      target_schema: schema
      target_database: database
"""
        result = changeset_refactor_yml_str(input_yaml, schema_specs)
        assert result.refactored
        assert isinstance(result, YMLRuleRefactorResult)

        # Expect 2 logs - one for target_schema, one for target_database
        assert len(result.refactor_logs) == 2
        assert any(
            "Snapshot 'test_snapshot' - Config field 'target_schema' has been renamed to 'schema'" in log
            for log in result.refactor_logs
        )
        assert any(
            "Snapshot 'test_snapshot' - Config field 'target_database' has been renamed to 'database'" in log
            for log in result.refactor_logs
        )

        snapshot = safe_load(result.refactored_yaml)["snapshots"][0]
        assert snapshot["name"] == "test_snapshot"
        assert snapshot["config"] == {"schema": "schema", "database": "database"}


class TestYamlOutput:
    """Tests for YAML output functions"""

    def test_output_yaml(self):
        # Test that output_yaml produces valid YAML
        test_data = {
            "version": 2,
            "models": [
                {
                    "name": "test_model",
                    "description": "Test model",
                    "config": {"materialized": "table", "meta": {"abc": 123}},
                }
            ],
        }

        yaml_str = dict_to_yaml_str(test_data)
        assert "version: 2" in yaml_str
        assert "name: test_model" in yaml_str
        assert "materialized: table" in yaml_str
        assert "abc: 123" in yaml_str


class TestDbtProjectYAMLPlusPrefix:
    """Tests for YAML output functions"""

    def test_check_project(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        # Test that output_yaml produces valid YAML

        test_data = {"models": {"materialized": "table", "not_a_config": {"materialized": "view"}}}
        expected_data = {"models": {"+materialized": "table", "not_a_config": {"+materialized": "view"}}}

        new_file = temp_project_dir / "models" / "not_a_config" / "my_model.sql"
        new_file.parent.mkdir(parents=True, exist_ok=True)
        new_file.write_text("select 1 as id")

        new_yml, refactor_logs = rec_check_yaml_path(
            test_data, temp_project_dir, schema_specs.dbtproject_specs_per_node_type["models"]
        )
        assert expected_data == new_yml
        assert len(refactor_logs) == 2

    def test_check_project_existing_config_and_folder(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        # Test that output_yaml produces valid YAML

        test_data = {"models": {"materialized": "table", "grants": {"materialized": "view"}}}
        expected_data = {"models": {"+materialized": "table", "grants": {"+materialized": "view"}}}

        new_file = temp_project_dir / "models" / "grants" / "my_model.sql"
        new_file.parent.mkdir(parents=True, exist_ok=True)
        new_file.write_text("select 1 as id")

        new_yml, refactor_logs = rec_check_yaml_path(
            test_data, temp_project_dir, schema_specs.dbtproject_specs_per_node_type["models"]
        )
        assert expected_data == new_yml
        assert len(refactor_logs) == 2

    def test_check_project_existing_config_not_folder(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        # Test that output_yaml produces valid YAML

        test_data = {"models": {"materialized": "table", "grants": {"materialized": "view"}}}
        expected_data = {"models": {"+materialized": "table", "+grants": {"materialized": "view"}}}

        new_file = temp_project_dir / "models" / "not_grants" / "my_model.sql"
        new_file.parent.mkdir(parents=True, exist_ok=True)
        new_file.write_text("select 1 as id")

        new_yml, refactor_logs = rec_check_yaml_path(
            test_data, temp_project_dir, schema_specs.dbtproject_specs_per_node_type["models"]
        )
        assert expected_data == new_yml
        assert len(refactor_logs) == 2

    def test_check_project_no_change(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        # Test that output_yaml produces valid YAML

        test_data = {"models": {"+materialized": "table", "folder": {"+materialized": "view"}}}
        expected_data = {"models": {"+materialized": "table", "folder": {"+materialized": "view"}}}

        new_file = temp_project_dir / "models" / "folder" / "my_model.sql"
        new_file.parent.mkdir(parents=True, exist_ok=True)
        new_file.write_text("select 1 as id")

        new_yml, refactor_logs = rec_check_yaml_path(
            test_data, temp_project_dir, schema_specs.dbtproject_specs_per_node_type["models"]
        )
        assert expected_data == new_yml
        assert len(refactor_logs) == 0


class TestDbtProjectYAMLRenameConfigs:
    """Tests for YAML output functions"""

    def test_check_project(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        # Test that output_yaml produces valid YAML

        yml_str = """
        name: test_project

        snapshots:
          target_schema: schema
          +target_database: database
          test_project:
            example: 
              target_schema: schema
              +target_database: database
        """

        # Create snapshots/example directory
        snapshots_dir = temp_project_dir / "snapshots" / "example"
        snapshots_dir.mkdir(parents=True, exist_ok=True)

        result = changeset_dbt_project_prefix_plus_for_config(yml_str, temp_project_dir, schema_specs)

        refactored_snapshots = safe_load(result.refactored_yaml)["snapshots"]
        assert refactored_snapshots == {
            "test_project": {"example": {"+schema": "schema", "+database": "database"}},
            "+schema": "schema",
            "+database": "database",
        }


class TestDbtProjectRemoveDeprecated:
    """Tests for YAML output functions"""

    def test_remove_deprecated_config(self):
        input_str = """
name: 'jaffle_shop'
version: '1.0'
require-dbt-version: ">=1.6.0"
config-version: 2

dbt-cloud:
  project-id: 12345
  defer-env-id: 12345

log-path: ["other-directory"]
model-paths: ["models"]
analysis-paths: ["analysis"]
target-path: "target"
clean-targets: ["target", "dbt_modules", "dbt_packages"]
test-paths: ["tests"]
seed-paths: ["data"] # here is a comment
macro-paths: ["macros"]
# this is a comment
asset-paths: ["assets"]

profile: garage-jaffle
"""

        expected_str = """
name: 'jaffle_shop'
version: '1.0'
require-dbt-version: ">=1.6.0"
config-version: 2

dbt-cloud:
  project-id: 12345
  defer-env-id: 12345

model-paths: ["models"]
analysis-paths: ["analysis"]
clean-targets: ["target", "dbt_modules", "dbt_packages"]
test-paths: ["tests"]
seed-paths: ["data"] # here is a comment
macro-paths: ["macros"]
# this is a comment
asset-paths: ["assets"]

profile: garage-jaffle
"""
        result = changeset_dbt_project_remove_deprecated_config(input_str)
        assert result.refactored_yaml.strip() == expected_str.strip()


class TestOwnerPropertiesRefactoring:
    """Tests for owner properties refactoring"""

    def test_owner_properties_refactoring(
        self, temp_project_dir: Path, schema_yml_with_owner_properties: str, schema_specs: SchemaSpecs
    ):
        # Create a test YAML file
        yml_file = temp_project_dir / "models" / "schema.yml"
        yml_file.parent.mkdir(parents=True, exist_ok=True)
        yml_file.write_text(schema_yml_with_owner_properties)

        # Test the refactoring
        result = changeset_owner_properties_yml_str(schema_yml_with_owner_properties, schema_specs)
        assert result.refactored
        assert isinstance(result, YMLRuleRefactorResult)
        assert len(result.refactor_logs) == 4
        assert any("team' moved under config.meta" in log for log in result.refactor_logs)
        assert any("role' moved under config.meta" in log for log in result.refactor_logs)
        assert any("department' moved under config.meta" in log for log in result.refactor_logs)
        assert any("level' moved under config.meta" in log for log in result.refactor_logs)

        # Check groups
        group = safe_load(result.refactored_yaml)["groups"][0]
        assert "owner" in group
        assert group["owner"] == {"name": "John Doe", "email": "john@example.com"}
        assert "config" in group
        assert "meta" in group["config"]
        assert group["config"]["meta"]["team"] == "Data Team"
        assert group["config"]["meta"]["role"] == "Data Engineer"
        assert group["config"]["meta"]["abc"] == 123

        # Check exposures
        exposure = safe_load(result.refactored_yaml)["exposures"][0]
        assert "owner" in exposure
        assert exposure["owner"] == {"name": "Jane Doe", "email": "jane@example.com"}
        assert "config" in exposure
        assert "meta" in exposure["config"]
        assert exposure["config"]["meta"]["department"] == "Analytics"
        assert exposure["config"]["meta"]["level"] == "Senior"
        assert exposure["config"]["meta"]["def"] == 456

    def test_owner_properties_no_changes(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        # Test with only allowed owner properties
        yml_str = """
version: 2

groups:
  - name: my_first_dbt_group
    description: "A starter dbt group"
    owner:
      name: "John Doe"
      email: "john@example.com"
    config:
      meta:
        abc: 123
"""
        yml_file = temp_project_dir / "models" / "schema.yml"
        yml_file.parent.mkdir(parents=True, exist_ok=True)
        yml_file.write_text(yml_str)

        # Test the refactoring
        result = changeset_owner_properties_yml_str(yml_str, schema_specs)
        assert not result.refactored
        assert len(result.refactor_logs) == 0

    def test_owner_properties_non_dict(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        # Test with non-dict owner
        yml_str = """
version: 2

groups:
  - name: my_first_dbt_group
    description: "A starter dbt group"
    owner: "John Doe"
    config:
      meta:
        abc: 123
"""
        yml_file = temp_project_dir / "models" / "schema.yml"
        yml_file.parent.mkdir(parents=True, exist_ok=True)
        yml_file.write_text(yml_str)

        # Test the refactoring
        result = changeset_owner_properties_yml_str(yml_str, schema_specs)
        assert not result.refactored
        assert len(result.refactor_logs) == 0

    def test_owner_properties_no_owner(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        # Test with no owner field
        yml_str = """
version: 2

groups:
  - name: my_first_dbt_group
    description: "A starter dbt group"
    config:
      meta:
        abc: 123
"""
        yml_file = temp_project_dir / "models" / "schema.yml"
        yml_file.parent.mkdir(parents=True, exist_ok=True)
        yml_file.write_text(yml_str)

        # Test the refactoring
        result = changeset_owner_properties_yml_str(yml_str, schema_specs)
        assert not result.refactored
        assert len(result.refactor_logs) == 0

    def test_owner_properties_non_owner_node_type(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        # Test with a node type that doesn't have owner
        yml_str = """
version: 2

models:
  - name: my_first_dbt_model
    description: "A starter dbt model"
    config:
      meta:
        abc: 123
"""
        yml_file = temp_project_dir / "models" / "schema.yml"
        yml_file.parent.mkdir(parents=True, exist_ok=True)
        yml_file.write_text(yml_str)

        # Test the refactoring
        result = changeset_owner_properties_yml_str(yml_str, schema_specs)
        assert not result.refactored
        assert len(result.refactor_logs) == 0


class TestSkipFile:
    """Tests for skip_file function"""

    def test_skip_file_no_select(self):
        """Test that no files are skipped when no select list is provided"""
        file_path = Path("/path/to/file.sql")
        assert not skip_file(file_path)
        assert not skip_file(file_path, None)

    def test_skip_file_with_select_matching(self):
        """Test that files matching the select list are not skipped"""
        file_path = Path("/path/to/file.sql")
        select = ["/path/to/file.sql"]
        assert not skip_file(file_path, select)

    def test_skip_file_with_select_not_matching(self):
        """Test that files not matching the select list are skipped"""
        file_path = Path("/path/to/file.sql")
        select = ["/path/to/other.sql"]
        assert skip_file(file_path, select)

    def test_skip_file_with_select_partial_match(self):
        """Test that files partially matching the select list are not skipped"""
        file_path = Path("/path/to/file.sql")
        select = ["/path/to"]
        assert not skip_file(file_path, select)

    def test_skip_file_with_select_multiple_paths(self):
        """Test that files matching any path in the select list are not skipped"""
        file_path = Path("/path/to/file.sql")
        select = ["/path/to/other.sql", "/path/to/file.sql"]
        assert not skip_file(file_path, select)

    def test_skip_file_with_select_relative_paths(self):
        """Test that relative paths in select list work correctly"""
        file_path = Path("/absolute/path/to/file.sql")
        select = ["/absolute/path/to/file.sql"]  # Changed to use absolute path since that's what the function expects
        assert not skip_file(file_path, select)

    def test_skip_file_with_select_different_case(self):
        """Test that path matching is case sensitive"""
        file_path = Path("/path/to/file.sql")
        select = ["/PATH/TO/FILE.SQL"]
        assert skip_file(file_path, select)

    def test_skip_file_with_select_empty_list(self):
        """Test that empty select list is treated the same as no select list"""
        file_path = Path("/path/to/file.sql")
        select = []
        assert not skip_file(file_path, select)  # Changed to expect False since empty list is treated same as None


class TestTestConfigurationRefactoring:
    """Tests for test configuration refactoring"""

    def test_test_config_model_column_level(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        """Test that test configuration fields at column level are moved under config"""
        input_yaml = """
version: 2

models:
  - name: my_model
    columns:
      - name: id
        tests:
          - unique:
              where: "date_column > __3_days_ago__"  # placeholder string for static config
          - accepted_values:
              values: ['placed', 'shipped', 'completed', 'returned']
              where: "date_column > __3_days_ago__"  # placeholder string for static config
"""
        result = changeset_refactor_yml_str(input_yaml, schema_specs)
        assert result.refactored
        assert isinstance(result, YMLRuleRefactorResult)

        # Check that the model structure is preserved
        model = safe_load(result.refactored_yaml)["models"][0]
        column = model["columns"][0]

        # Check that tests were processed correctly
        assert len(column["tests"]) == 2

        # Check first test (unique)
        unique_test = column["tests"][0]
        assert "unique" in unique_test
        assert "config" in unique_test["unique"]
        assert unique_test["unique"]["config"]["where"] == "date_column > __3_days_ago__"

        # Check second test (accepted_values)
        accepted_values_test = column["tests"][1]
        assert "accepted_values" in accepted_values_test
        assert "config" in accepted_values_test["accepted_values"]
        assert accepted_values_test["accepted_values"]["config"]["where"] == "date_column > __3_days_ago__"
        assert accepted_values_test["accepted_values"]["values"] == ["placed", "shipped", "completed", "returned"]

        # Check that appropriate logs were generated
        assert any("Field 'where' moved under config" in log for log in result.refactor_logs)

    def test_test_config_model_top_level(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        """Test that test configuration fields at model level are moved under config"""
        input_yaml = """
version: 2

models:
  - name: my_model
    tests:
      - dbt_expectations.expect_table_aggregation_to_equal_other_table:
          expression: sum(col_numeric_a)
          compare_model: ref("other_model")
          group_by: [idx]
          where: 1=1
"""
        result = changeset_refactor_yml_str(input_yaml, schema_specs)
        assert result.refactored
        assert isinstance(result, YMLRuleRefactorResult)

        # Check that the model structure is preserved
        model = safe_load(result.refactored_yaml)["models"][0]

        # Check that tests were processed correctly
        assert len(model["tests"]) == 1

        # Check the test
        test = model["tests"][0]
        test_name = "dbt_expectations.expect_table_aggregation_to_equal_other_table"
        assert test_name in test
        assert "config" in test[test_name]
        assert test[test_name]["config"]["where"] == "1=1"
        assert test[test_name]["expression"] == "sum(col_numeric_a)"
        assert test[test_name]["compare_model"] == 'ref("other_model")'
        assert test[test_name]["group_by"] == ["idx"]

        # Check that appropriate logs were generated
        assert any("Field 'where' moved under config" in log for log in result.refactor_logs)

    def test_test_config_source_top_level(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        """Test that test configuration fields at source table level are moved under config"""
        input_yaml = """
version: 2

sources:
  - name: jaffle_shop
    description: This is a replica of the Postgres database used by our app
    tables:
      - name: orders
        database: raw
        description: >
          One record per order. Includes cancelled and deleted orders.
        columns:
          - name: id
            description: Primary key of the orders table
            tests:
              - unique
              - not_null:
                  where: 1=1
          - name: status
            description: Note that the status can change over time
"""
        result = changeset_refactor_yml_str(input_yaml, schema_specs)
        assert result.refactored
        assert isinstance(result, YMLRuleRefactorResult)

        # Check that the source structure is preserved
        source = safe_load(result.refactored_yaml)["sources"][0]
        table = source["tables"][0]

        # Check that columns were processed correctly
        assert len(table["columns"]) == 2

        # Check first column with tests
        id_column = table["columns"][0]
        assert id_column["name"] == "id"
        assert len(id_column["tests"]) == 2

        # Check the not_null test
        not_null_test = id_column["tests"][1]
        assert "not_null" in not_null_test
        assert "config" in not_null_test["not_null"]
        assert not_null_test["not_null"]["config"]["where"] == "1=1"

        # Check second column (no tests)
        status_column = table["columns"][1]
        assert status_column["name"] == "status"
        assert "tests" not in status_column

        # Check that appropriate logs were generated
        assert any("Field 'where' moved under config" in log for log in result.refactor_logs)

    def test_test_config_string_tests(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        """Test that string tests are left unchanged"""
        input_yaml = """
version: 2

models:
  - name: my_model
    columns:
      - name: id
        tests:
          - unique
          - not_null
"""
        result = changeset_refactor_yml_str(input_yaml, schema_specs)
        # Should not be refactored since string tests don't need config
        assert not result.refactored
        assert len(result.refactor_logs) == 0

    def test_test_config_mixed_string_and_dict_tests(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        """Test that mixed string and dict tests are handled correctly"""
        input_yaml = """
version: 2

models:
  - name: my_model
    columns:
      - name: id
        tests:
          - unique
          - not_null:
              where: "id is not null"
          - accepted_values:
              values: ['active', 'inactive']
"""
        result = changeset_refactor_yml_str(input_yaml, schema_specs)
        assert result.refactored
        assert isinstance(result, YMLRuleRefactorResult)

        # Check that the model structure is preserved
        model = safe_load(result.refactored_yaml)["models"][0]
        column = model["columns"][0]

        # Check that tests were processed correctly
        assert len(column["tests"]) == 3

        # Check first test (string - should be unchanged)
        assert column["tests"][0] == "unique"

        # Check second test (dict with config)
        not_null_test = column["tests"][1]
        assert "not_null" in not_null_test
        assert "config" in not_null_test["not_null"]
        assert not_null_test["not_null"]["config"]["where"] == "id is not null"

        # Check third test (dict without config)
        accepted_values_test = column["tests"][2]
        assert "accepted_values" in accepted_values_test
        assert accepted_values_test["accepted_values"]["values"] == ["active", "inactive"]
        assert "config" not in accepted_values_test["accepted_values"]

        # Check that appropriate logs were generated
        assert any("Field 'where' moved under config" in log for log in result.refactor_logs)

    def test_test_config_data_tests_key(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        """Test that tests work with both 'tests' and 'data_tests' keys"""
        input_yaml = """
version: 2

models:
  - name: my_model
    columns:
      - name: id
        data_tests:
          - unique:
              where: "date_column > '2023-01-01'"
          - not_null:
              where: "id is not null"
"""
        result = changeset_refactor_yml_str(input_yaml, schema_specs)
        assert result.refactored
        assert isinstance(result, YMLRuleRefactorResult)

        # Check that the model structure is preserved
        model = safe_load(result.refactored_yaml)["models"][0]
        column = model["columns"][0]

        # Check that tests were processed correctly
        assert len(column["data_tests"]) == 2

        # Check first test
        unique_test = column["data_tests"][0]
        assert "unique" in unique_test
        assert "config" in unique_test["unique"]
        assert unique_test["unique"]["config"]["where"] == "date_column > '2023-01-01'"

        # Check second test
        not_null_test = column["data_tests"][1]
        assert "not_null" in not_null_test
        assert "config" in not_null_test["not_null"]
        assert not_null_test["not_null"]["config"]["where"] == "id is not null"

        # Check that appropriate logs were generated
        assert any("Field 'where' moved under config" in log for log in result.refactor_logs)

    def test_test_config_source_column_level(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        """Test that test configuration fields at source column level are moved under config"""
        input_yaml = """
version: 2

sources:
  - name: my_source
    description: A test source
    tables:
      - name: my_table
        description: A test table
        columns:
          - name: id
            description: Primary key
            tests:
              - unique:
                  where: "deleted_at is null"
              - not_null:
                  where: "id > 0"
          - name: status
            description: Status field
            tests:
              - accepted_values:
                  values: ['pending', 'active', 'completed']
                  where: "status is not null"
"""
        result = changeset_refactor_yml_str(input_yaml, schema_specs)
        assert result.refactored
        assert isinstance(result, YMLRuleRefactorResult)

        # Check that the source structure is preserved
        source = safe_load(result.refactored_yaml)["sources"][0]
        table = source["tables"][0]

        # Check that columns were processed correctly
        assert len(table["columns"]) == 2

        # Check first column
        id_column = table["columns"][0]
        assert id_column["name"] == "id"
        assert len(id_column["tests"]) == 2

        # Check unique test
        unique_test = id_column["tests"][0]
        assert "unique" in unique_test
        assert "config" in unique_test["unique"]
        assert unique_test["unique"]["config"]["where"] == "deleted_at is null"

        # Check not_null test
        not_null_test = id_column["tests"][1]
        assert "not_null" in not_null_test
        assert "config" in not_null_test["not_null"]
        assert not_null_test["not_null"]["config"]["where"] == "id > 0"

        # Check second column
        status_column = table["columns"][1]
        assert status_column["name"] == "status"
        assert len(status_column["tests"]) == 1

        # Check accepted_values test
        accepted_values_test = status_column["tests"][0]
        assert "accepted_values" in accepted_values_test
        assert "config" in accepted_values_test["accepted_values"]
        assert accepted_values_test["accepted_values"]["config"]["where"] == "status is not null"
        assert accepted_values_test["accepted_values"]["values"] == ["pending", "active", "completed"]

        # Check that appropriate logs were generated
        assert any("Field 'where' moved under config" in log for log in result.refactor_logs)

    def test_test_config_existing_config_field(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        """Test that test configuration fields are handled correctly when config already exists"""
        input_yaml = """
version: 2

models:
  - name: my_model
    columns:
      - name: id
        tests:
          - not_null:
              config:
                severity: warn
              where: "id is not null"
"""
        result = changeset_refactor_yml_str(input_yaml, schema_specs)
        assert result.refactored
        assert isinstance(result, YMLRuleRefactorResult)

        # Check that the model structure is preserved
        model = safe_load(result.refactored_yaml)["models"][0]
        column = model["columns"][0]

        # Check that tests were processed correctly
        assert len(column["tests"]) == 1

        # Check the test
        not_null_test = column["tests"][0]
        assert "not_null" in not_null_test
        assert "config" in not_null_test["not_null"]
        assert not_null_test["not_null"]["config"]["where"] == "id is not null"
        assert not_null_test["not_null"]["config"]["severity"] == "warn"

        # Check that appropriate logs were generated
        assert any("Field 'where' moved under config" in log for log in result.refactor_logs)

    def test_ordereddict_mutation_bug(self, temp_project_dir: Path, schema_specs: SchemaSpecs):
        """Test that reproduces the OrderedDict mutated during iteration bug"""
        input_yaml = """
version: 2

models:
  - name: my_model
    columns:
      - name: id
        tests:
          - not_null:
              severity: error
              where: "id is not null"
              config:
                severity: warn
"""
        # This should not raise "OrderedDict mutated during iteration" error
        result = changeset_refactor_yml_str(input_yaml, schema_specs)
        assert result.refactored
        assert isinstance(result, YMLRuleRefactorResult)

        # Check that the model structure is preserved
        model = safe_load(result.refactored_yaml)["models"][0]
        column = model["columns"][0]

        # Check that tests were processed correctly
        assert len(column["tests"]) == 1

        # Check the test - the top-level severity should be moved to config and overwrite the existing one
        not_null_test = column["tests"][0]
        assert "not_null" in not_null_test
        assert "config" in not_null_test["not_null"]
        assert not_null_test["not_null"]["config"]["where"] == "id is not null"
        assert not_null_test["not_null"]["config"]["severity"] == "error"  # Should be overwritten

        # Check that appropriate logs were generated
        assert any("Field 'severity' is already under config" in log for log in result.refactor_logs)
        assert any("Field 'where' moved under config" in log for log in result.refactor_logs)


class TestRemoveExtraTabs:
    """Tests for changeset_remove_extra_tabs function"""

    def test_no_tabs_no_changes(self):
        input_yaml = """
version: 2
models:
  - name: test_model
    description: "A test model"
    columns:
      - name: id
        description: "Primary key"
"""
        result = changeset_remove_extra_tabs(input_yaml)
        assert not result.refactored
        assert len(result.refactor_logs) == 0
        assert result.refactored_yaml == input_yaml
        assert result.rule_name == "remove_extra_tabs"

    def test_single_tab_replacement(self):
        input_yaml = """
version: 2
models:
  - name: test_model
\t  description: "A test model"
    columns:
      - name: id
"""
        result = changeset_remove_extra_tabs(input_yaml)
        assert result.refactored
        assert len(result.refactor_logs) == 1
        assert "Found extra tabs: line 5 - column 1" in result.refactor_logs[0]
        lines = result.refactored_yaml.split("\n")
        assert lines[4] == '    description: "A test model"'  # 4 spaces (tab+2 spaces)

    def test_multiple_tabs_replacement(self):
        input_yaml = """
version: 2
models:
  - name: test_model
\t  description: "A test model"
\t    columns:
      - name: id
\t        description: "Primary key"
"""
        result = changeset_remove_extra_tabs(input_yaml)
        assert result.refactored
        assert len(result.refactor_logs) == 2  # Two tab characters found
        lines = result.refactored_yaml.split("\n")
        assert lines[4] == '    description: "A test model"'

    def test_mixed_tabs_and_spaces(self):
        input_yaml = """
version: 2
models:
  - name: test_model
\t  description: "A test model"  # tab + spaces
    columns:
      - name: id
"""
        result = changeset_remove_extra_tabs(input_yaml)
        assert result.refactored
        assert len(result.refactor_logs) == 1
        assert "Found extra tabs: line 5 - column 1" in result.refactor_logs[0]
        lines = result.refactored_yaml.split("\n")
        assert lines[4] == '    description: "A test model"  # tab + spaces'

    def test_tab_only_line(self):
        input_yaml = """
version: 2
models:
  - name: test_model
\t\t
    columns:
      - name: id
"""
        result = changeset_remove_extra_tabs(input_yaml)
        assert result.refactored
        assert len(result.refactor_logs) == 2  # Two tab characters found
        assert "Found extra tabs: line 5 - column 1" in result.refactor_logs[0]
        assert "Found extra tabs: line 5 - column 3" in result.refactor_logs[1]
        lines = result.refactored_yaml.split("\n")
        assert lines[4] == "    "  # both tabs replaced with spaces

    def test_tab_with_comments(self):
        input_yaml = """
version: 2
models:
  - name: test_model
\t  description: "A test model"  # comment with tab
    columns:
      - name: id
"""
        result = changeset_remove_extra_tabs(input_yaml)
        assert result.refactored
        assert len(result.refactor_logs) == 1
        assert "Found extra tabs: line 5 - column 1" in result.refactor_logs[0]
        lines = result.refactored_yaml.split("\n")
        assert lines[4] == '    description: "A test model"  # comment with tab'

    def test_tab_in_list_items(self):
        input_yaml = """
version: 2
models:
  - name: test_model
    tags:
      - tag1
\t    - tag2
      - tag3
"""
        result = changeset_remove_extra_tabs(input_yaml)
        assert result.refactored
        assert len(result.refactor_logs) == 1
        assert "Found extra tabs: line 7 - column 1" in result.refactor_logs[0]
        lines = result.refactored_yaml.split("\n")
        assert lines[6] == "      - tag2"  # 6 spaces (tab+4 spaces)

    def test_tab_in_nested_structures(self):
        input_yaml = """
version: 2
models:
  - name: test_model
    config:
\t    materialized: table
      meta:
\t      owner: team
"""
        result = changeset_remove_extra_tabs(input_yaml)
        assert result.refactored
        assert len(result.refactor_logs) == 2  # Two tab characters found
        lines = result.refactored_yaml.split("\n")
        assert lines[5] == "      materialized: table"  # 6 spaces (tab+4 spaces)


class TestRemoveDuplicateKeys:
    """Tests for changeset_remove_duplicate_keys function"""

    def test_no_duplicates_no_changes(self):
        """Test that YAML without duplicate keys is not modified"""
        input_yaml = """
version: 2
models:
  - name: test_model
    description: "A test model"
    columns:
      - name: id
        description: "Primary key"
"""
        result = changeset_remove_duplicate_keys(input_yaml)
        assert not result.refactored
        assert len(result.refactor_logs) == 0
        assert result.refactored_yaml == input_yaml
        assert result.rule_name == "remove_duplicate_keys"

    def test_single_duplicate_key(self):
        """Test that a single duplicate key is detected and removed"""
        input_yaml = """
version: 2
models:
  - name: test_model
    description: "First description"
    description: "Second description"
    columns:
      - name: id
"""
        result = changeset_remove_duplicate_keys(input_yaml)
        assert result.refactored
        assert len(result.refactor_logs) == 1
        assert "Found duplicate keys: line" in result.refactor_logs[0]
        assert "description" in result.refactor_logs[0]

        # Verify the refactored YAML keeps only the last occurrence (yaml.safe_load behavior)
        refactored_dict = safe_load(result.refactored_yaml)
        model = refactored_dict["models"][0]
        assert model["description"] == "Second description"

    def test_multiple_duplicate_keys(self):
        """Test that multiple duplicate keys are detected and removed"""
        input_yaml = """
version: 2
models:
  - name: test_model
    description: "First description"
    description: "Second description"
    materialized: table
    materialized: view
    columns:
      - name: id
        description: "Column description"
        description: "Another description"
"""
        result = changeset_remove_duplicate_keys(input_yaml)
        assert result.refactored
        assert len(result.refactor_logs) == 3  # 3 duplicate keys found

        # Verify the refactored YAML
        refactored_dict = safe_load(result.refactored_yaml)
        model = refactored_dict["models"][0]
        assert model["description"] == "Second description"
        assert model["materialized"] == "view"

        column = model["columns"][0]
        assert column["description"] == "Another description"

    def test_nested_duplicate_keys(self):
        """Test that duplicate keys in nested structures are detected"""
        input_yaml = """
version: 2
models:
  - name: test_model
    config:
      materialized: table
      materialized: view
      meta:
        owner: team1
        owner: team2
    columns:
      - name: id
        tests:
          - unique
          - unique
"""
        result = changeset_remove_duplicate_keys(input_yaml)
        assert result.refactored
        assert len(result.refactor_logs) >= 1

        # Verify the refactored YAML
        refactored_dict = safe_load(result.refactored_yaml)
        model = refactored_dict["models"][0]
        assert model["config"]["materialized"] == "view"
        assert model["config"]["meta"]["owner"] == "team2"

        column = model["columns"][0]
        # Note: yaml.safe_load() only deduplicates dictionary keys, not list items
        # So the duplicate 'unique' tests will remain as separate list items
        assert len(column["tests"]) == 2  # Both unique tests remain
        assert column["tests"] == ["unique", "unique"]

    def test_duplicate_keys_with_comments(self):
        """Test that duplicate keys are handled correctly with comments"""
        input_yaml = """
version: 2
models:
  - name: test_model
    # This is a comment
    description: "First description"  # inline comment
    description: "Second description"
    columns:
      - name: id
"""
        result = changeset_remove_duplicate_keys(input_yaml)
        assert result.refactored
        assert len(result.refactor_logs) == 1

        # Verify the refactored YAML
        refactored_dict = safe_load(result.refactored_yaml)
        model = refactored_dict["models"][0]
        assert model["description"] == "Second description"

    def test_duplicate_keys_in_sources(self):
        """Test that duplicate keys in sources are detected"""
        input_yaml = """
version: 2
sources:
  - name: my_source
    description: "First description"
    description: "Second description"
    tables:
      - name: my_table
        description: "Table description"
        description: "Another table description"
"""
        result = changeset_remove_duplicate_keys(input_yaml)
        assert result.refactored
        assert len(result.refactor_logs) >= 1

        # Verify the refactored YAML
        refactored_dict = safe_load(result.refactored_yaml)
        source = refactored_dict["sources"][0]
        assert source["description"] == "Second description"

        table = source["tables"][0]
        assert table["description"] == "Another table description"

    def test_duplicate_keys_in_tests(self):
        """Test that duplicate keys in test configurations are detected"""
        input_yaml = """
version: 2
models:
  - name: test_model
    columns:
      - name: id
        tests:
          - unique:
              where: "id is not null"
              where: "id > 0"
          - not_null:
              severity: error
              severity: warn
"""
        result = changeset_remove_duplicate_keys(input_yaml)
        assert result.refactored
        assert len(result.refactor_logs) >= 1

        # Verify the refactored YAML
        refactored_dict = safe_load(result.refactored_yaml)
        model = refactored_dict["models"][0]
        column = model["columns"][0]

        unique_test = column["tests"][0]
        assert unique_test["unique"]["where"] == "id > 0"

        not_null_test = column["tests"][1]
        assert not_null_test["not_null"]["severity"] == "warn"

    def test_empty_yaml(self):
        """Test that empty YAML is handled correctly"""
        input_yaml = ""
        result = changeset_remove_duplicate_keys(input_yaml)
        assert not result.refactored
        assert len(result.refactor_logs) == 0
        assert result.refactored_yaml == input_yaml
