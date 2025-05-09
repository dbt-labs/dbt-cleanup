from pathlib import Path

import typer
from rich import print
from rich.console import Console
from typing_extensions import Annotated

from dbt_autofix.duplicate_keys import find_duplicate_keys, print_duplicate_keys
from dbt_autofix.fields_properties_configs import print_matrix
from dbt_autofix.refactor import apply_changesets, changeset_all_sql_yml_files

console = Console()
error_console = Console(stderr=True)

app = typer.Typer(
    help="A tool to help clean up dbt projects",
    no_args_is_help=True,
    add_completion=False,
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
def refactor_yml(
    path: Annotated[Path, typer.Option("--path", "-p", help="The path to the dbt project")] = current_dir,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-d", help="In dry run mode, do not apply changes")] = False,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output in JSON format")] = False,
):
    changesets = changeset_all_sql_yml_files(path, dry_run)
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


@app.command(hidden=True)
def print_fields_matrix():
    print_matrix()


if __name__ == "__main__":
    app()
