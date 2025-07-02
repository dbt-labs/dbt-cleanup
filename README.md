# dbt-autofix

dbt-autofix automatically scans your dbt project for deprecated configurations and updates them to align with the latest best practices. This makes it easier to resolve deprecation warnings introduced in dbt v1.10 as well as prepare for migration to the dbt Fusion engine.


| Deprecation Code in dbt Core      | Files             | Handling                                                                                         | Support |
| --------------------------------- | ----------------- | ------------------------------------------------------------------------------------------------ | ------- |
| `CustomKeyInObjectDeprecation` / `PropertyMovedToConfigDeprecation`    | YAML files        | Move all models configs under `config:` in YAML files       |   Full  |
| `CustomKeyInObjectDeprecation`    | YAML files        | Move all models extra config (not valid or custom) under `meta:` and `meta` under `config:`      |   Full  |
| `DuplicateYAMLKeysDeprecation`    | YAML files        | Remove duplicate keys in YAML files, keeping the second one to keep the same behaviour           |   Full  |
| `PropertyMovedToConfigDeprecation`| YAML files        | Only allow email and name as properties for groups and exposures owners                          |   Full  |
| `UnexpectedJinjaBlockDeprecation` | SQL files         | Remove extra `{% endmacro %}` and `{% endif %}` that don't have corresponding opening statements |   Full  |
| `GenericJSONSchemaValidationDeprecation` | `dbt_project.yml` | Prefix all configs for models/tests etc... with a `+`                                     | Partial |
| `ConfigDataPathDeprecation`       | `dbt_project.yml` | Remove deprecated config for data path (now seed)                                                |   Full  |
| `ConfigLogPathDeprecation`        | `dbt_project.yml` | Remove deprecated config for log path                                                            |   Full  |
| `ConfigSourcePathDeprecation`     | `dbt_project.yml` | Remove deprecated config for source path                                                         |   Full  |
| `ConfigTargetPathDeprecation`     | `dbt_project.yml` | Remove deprecated config for target path                                                         |   Full  |

## Installation

### From PyPi

#### With uv (recommended)

We recommend using `uv`/`uvx` to run the package.
If you don't have `uv` installed, you can install `uv` and `uvx`, [following the instructions on the offical website](https://docs.astral.sh/uv/getting-started/installation/).

- to run the latest version of the tool: `uvx dbt-autofix`
- to run a specific version of the tool: `uvx dbt-autofix@0.1.2`
- to install the tool as a dedicated CLI: `uv tool install dbt-autofix`

#### With pip

You can also use `pip` if you prefer, but we then recommend installing the tool in its own Python virtual environment. Once in a venv, install the tool with `pip install dbt-autofix` and then run `dbt-autofix ...` 

### From the source repo

To run it from the git repo directly, install `uv` [following those instructions](https://docs.astral.sh/uv/getting-started/installation/) and then:

run the tool directly
```sh
uvx --from git+https://github.com/dbt-labs/dbt-autofix.git dbt-autofix --help
```

or install it so that it can be run with `dbt-cleanup` in the future
```sh
uv tool install --from git+https://github.com/dbt-labs/dbt-autofix.git dbt-autofix
```

## Usage

### `deprecations` - the main one

- `dbt-autofix deprecations`: refactor YAML and SQL files to fix some deprecations
  - add `--path <mypath>` to configure the path of the dbt project (defaults to `.`)
  - add `--dry-run` for running in dry run mode
  - add `--json` to get resulting data in a JSONL format
  - add `--json-schema-version v2.0.0-beta.4` to get the JSON schema from a specific Fusion release (by default we pick the latest)
  - add `--select <path>` to only select files in a given path (by default the tool will look at all files of the dbt project)

Each JSON object will have the following keys:

- "mode": "applied" or "dry_run" 
- "file_path": the full path of the file modified. Each file will appear only once
- "refactors": the list of refactoring rules applied

Calling `deprecations` without `--dry-run` should be safe if your dbt code is part of a git repo. 

Please review the suggested changes to your dbt project before merging to `main` and make those changes go through your typical CI/CD process.


### `jobs`

`dbt-autofix jobs`: update dbt platform jobs steps to use `-s`/`--select` selectors instead of `-m`/`--models`/`--model` which are deprecated in the Fusion engine

Run `dbt-autofix jobs --help` to see the required parameters and supported arguments.

This tool requires connecting to the dbt Admin API to retrieve and update jobs which means that the user token or service token used need to have Read and Write access to jobs

Running with `--dry-run`/`d` will output what changes would have been triggered without triggering them
