from pathlib import Path
from typing import List, Optional

import typer
from rich import print
from rich.console import Console
from typing_extensions import Annotated

from dbt_autofix.dbt_api import update_jobs
from dbt_autofix.duplicate_keys import find_duplicate_keys, print_duplicate_keys
from dbt_autofix.fields_properties_configs import print_matrix
from dbt_autofix.refactor import apply_changesets, changeset_all_sql_yml_files
from dbt_autofix.retrieve_schemas import SchemaSpecs

console = Console()
error_console = Console(stderr=True)

app = typer.Typer(
    help="A tool to help clean up dbt projects",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)

current_dir = Path.cwd()


@app.command(name="list-yaml-duplicates")
def identify_duplicate_keys(
    path: Annotated[Path, typer.Option("--path", "-p", help="The path to the dbt project")] = current_dir,
):
    print(f"[green]Identifying duplicates in {path}[/green]\n")
    project_duplicates, package_duplicates = find_duplicate_keys(path)
    print_duplicate_keys(project_duplicates, package_duplicates)


@app.command(name="deprecations")
def refactor_yml(  # noqa: PLR0913
    path: Annotated[Path, typer.Option("--path", "-p", help="The path to the dbt project")] = current_dir,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-d", help="In dry run mode, do not apply changes")] = False,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output in JSON format")] = False,
    exclude_dbt_project_keys: Annotated[
        bool, typer.Option("--exclude-dbt-project-keys", "-e", help="Exclude specific dbt project keys", hidden=True)
    ] = False,
    json_schema_version: Annotated[
        Optional[str], typer.Option("--json-schema-version", help="Specific version of the JSON schema to use")
    ] = None,
    select: Annotated[
        Optional[List[str]], typer.Option("--select", "-s", help="Select specific paths to refactor")
    ] = None,
    include_packages: Annotated[
        bool, typer.Option("--include-packages", "-i", help="Include packages in the refactoring")
    ] = False,
):
    schema_specs = SchemaSpecs(json_schema_version)

    changesets = changeset_all_sql_yml_files(
        path, schema_specs, dry_run, exclude_dbt_project_keys, select, include_packages
    )
    yaml_results, sql_results = changesets
    if dry_run:
        if not json_output:
            error_console.print("[red]-- Dry run mode, not applying changes --[/red]")
        for changeset in yaml_results:
            if changeset.refactored:
                changeset.print_to_console(json_output)
        for changeset in sql_results:
            if changeset.refactored:
                changeset.print_to_console(json_output)
    else:
        apply_changesets(yaml_results, sql_results, json_output)


@app.command(name="jobs")
def jobs(  # noqa: PLR0913
    account_id: Annotated[
        int, typer.Option("--account-id", "-a", help="The account ID to use", envvar="DBT_ACCOUNT_ID")
    ],
    api_key: Annotated[
        str, typer.Option("--api-key", "-k", help="The user token or service token to use", envvar="DBT_API_KEY")
    ],
    base_url: Annotated[
        str, typer.Option("--base-url", "-b", help="The base URL to use", envvar="DBT_BASE_URL")
    ] = "https://cloud.getdbt.com",
    disable_ssl_verification: Annotated[
        bool, typer.Option("--disable-ssl-verification", "-s", help="Disable SSL verification", hidden=True)
    ] = False,
    project_ids: Annotated[
        Optional[List[int]], typer.Option("--project-ids", "-p", help="The project IDs to use")
    ] = None,
    environment_ids: Annotated[
        Optional[List[int]], typer.Option("--environment-ids", "-e", help="The environment IDs to use")
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-d", help="In dry run mode, do not apply changes")] = False,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output in JSON format")] = False,
):
    update_jobs(
        account_id, api_key, base_url, disable_ssl_verification, project_ids, environment_ids, dry_run, json_output
    )


@app.command(hidden=True)
def print_fields_matrix(
    json_schema_version: Annotated[
        Optional[str], typer.Option("--json-schema-version", help="Specific version of the JSON schema to use")
    ] = None,
):
    print_matrix(json_schema_version)


if __name__ == "__main__":
    app()


@app.callback()
def main(
    debug: bool = typer.Option(
        False, "--debug", help="Enable debug mode with pretty exceptions", envvar="DBT_AUTOFIX_DEBUG"
    ),
):
    if debug:
        app.pretty_exceptions_enable = True
