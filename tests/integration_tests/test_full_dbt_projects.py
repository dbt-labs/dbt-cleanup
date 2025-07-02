import difflib
import filecmp
import json
import os
import shutil
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from dbt_autofix.main import refactor_yml

dbt_projects_dir_name = "dbt_projects"
postfix_expected = "_expected"


def get_project_folders():
    dbt_projects_dir = os.path.join(os.path.dirname(__file__), dbt_projects_dir_name)
    return [
        folder
        for folder in os.listdir(dbt_projects_dir)
        if os.path.isdir(os.path.join(dbt_projects_dir, folder)) and not folder.endswith(postfix_expected)
    ]


def compare_dirs(dir1, dir2):
    comparison = filecmp.dircmp(dir1, dir2)

    # Check for files that exist in only one directory
    if comparison.left_only or comparison.right_only:
        pytest.fail(
            f"Files differ between {dir1} and {dir2}\n"
            f"Only in actual: {comparison.left_only}\n"
            f"Only in expected: {comparison.right_only}"
        )

    # Check for files that differ
    if comparison.diff_files:
        real_diffs = False
        diff_message = "Content differs in files:\n"
        for file in comparison.diff_files:
            file1 = os.path.join(dir1, file)
            file2 = os.path.join(dir2, file)
            with open(file1) as f1, open(file2) as f2:
                # we remove lines with only spaces to avoid false positives
                actual = [line for line in f1.readlines() if line.strip()]
                expected = [line for line in f2.readlines() if line.strip()]
                if actual == expected:
                    continue
                real_diffs = True
                diff_message += f"\n{file}:\n"
                diff_message += "".join(
                    difflib.unified_diff(
                        actual, expected, fromfile=f"actual/{file}", tofile=f"expected/{file}", lineterm=""
                    )
                )
        if real_diffs:
            pytest.fail(diff_message)

    # Recursively check subdirectories
    for subdir in comparison.common_dirs:
        compare_dirs(os.path.join(dir1, subdir), os.path.join(dir2, subdir))


def compare_json_logs(logs_io: StringIO, path: Path):
    ignore_keys = ["file_path"]

    logs = logs_io.getvalue()
    if os.getenv("GOLDIE_UPDATE"):
        with open(path, "w") as f:
            f.write(logs)

    logs = logs.strip().split("\n")
    log_dicts = [json.loads(log) for log in logs]
    log_dicts_filtered = [{k: v for k, v in log_dict.items() if k not in ignore_keys} for log_dict in log_dicts]

    expected_logs = open(path).read().strip().split("\n")
    expected_log_dicts = [json.loads(log) for log in expected_logs]
    expected_log_dicts_filtered = [{k: v for k, v in log_dict.items() if k not in ignore_keys} for log_dict in expected_log_dicts]

    for log_dict in log_dicts_filtered:
        assert log_dict in expected_log_dicts_filtered

@pytest.mark.parametrize("project_folder", get_project_folders())
def test_project_refactor(project_folder, request):
    dbt_projects_dir = os.path.join(os.path.dirname(__file__), dbt_projects_dir_name)
    source_dir = os.path.join(dbt_projects_dir, project_folder)

    # Create a temporary directory for the project
    temp_dir = tempfile.mkdtemp(prefix=f"dbt_autofix_test_{project_folder}_")

    # Copy the project files to the temporary directory
    project_path = os.path.join(temp_dir, project_folder)
    shutil.copytree(source_dir, project_path, dirs_exist_ok=True)
    print(f"Copied project '{project_folder}' to temporary directory: {temp_dir}")

    # Run refactor_yml on the project
    refactor_logs_io = StringIO()
    with redirect_stdout(refactor_logs_io):
        refactor_yml(path=Path(project_path), dry_run=False, json_output=True)

    # Compare with expected output
    expected_dir = os.path.join(dbt_projects_dir, f"{project_folder}{postfix_expected}")
    if not os.path.exists(expected_dir):
        pytest.fail(f"Expected output directory not found: {expected_dir}")

    compare_dirs(project_path, expected_dir)

    expected_logs_path = Path(dbt_projects_dir, "project1_expected.stdout")
    compare_json_logs(refactor_logs_io, expected_logs_path)

    # Clean up temporary directory after test
    def cleanup_temp_dir():
        try:
            shutil.rmtree(temp_dir)
            print(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            print(f"Failed to clean up {temp_dir}: {e}")

    request.addfinalizer(cleanup_temp_dir)
