import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import re

import httpx
from rich.console import Console

console = Console()
HTTP_ERROR_CODE = 400


def job_dict_to_payload(job_dict: dict) -> dict:
    """
    Convert a job dictionary to a payload dictionary.
    """

    fields_to_remove = {
        "raw_dbt_version",
        "created_at",
        "updated_at",
        "deactivated",
        "run_failure_count",
        "lifecycle_webhooks",
        "lifecycle_webhooks_url",
        "is_deferrable",
        "generate_sources",
        "cron_humanized",
        "next_run",
        "next_run_humanized",
        "is_system",
        "account",
        "project",
        "environment",
        "most_recent_run",
        "most_recent_completed_run",
        "identifier",
    }

    payload = {}
    for key, value in job_dict.items():
        if key not in fields_to_remove:
            payload[key] = value

    return payload


def job_steps_updated(job_dict: dict) -> tuple[bool, List[str]]:
    """
    Check if the job steps need to be updated.
    """

    exec_steps = job_dict.get("execute_steps", [])

    # Create a copy of the steps to avoid modifying the original
    updated_steps = exec_steps.copy()
    steps_changed = False

    update_step_rules = [
        step_regex_replace_m_with_s,
        step_remove_output,
    ]

    for i, step in enumerate(updated_steps):
        if isinstance(step, str):

            for update_step_fn in update_step_rules:
                new_step = update_step_fn(step)

                if new_step != step:
                    steps_changed = True
                    updated_steps[i] = new_step

    return steps_changed, updated_steps


def step_regex_replace_m_with_s(step: str) -> str:
    """
    Replace -m with -s and --model/--models with --select.
    """
    step = re.sub(r"(\s)-m(\s)", r"\1-s\2", step)
    step = re.sub(r"(\s)--model[s]?(\s)", r"\1--select\2", step)
    return step

def step_remove_output(step: str) -> str:
    """
    Remove --output in source freshness commands.
    """
    if step.startswith("dbt source freshness"):
        step = re.sub(r"(\s)-o(\s+)\S+", "", step)
        step = re.sub(r"(\s)--output(\s+)\S+", "", step)
    return step


class DBTClient:
    """A minimalistic API client for fetching dbt data via the Admin API."""

    def __init__(
        self,
        account_id: int,
        api_key: Optional[str],
        base_url: str = "https://cloud.getdbt.com",
        disable_ssl_verification: bool = False,
    ) -> None:
        self.account_id = account_id
        self._api_key = api_key

        self.base_url = base_url
        self._headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "dbt-autofix",
        }
        self._verify = not disable_ssl_verification
        if not self._verify:
            self._client = httpx.Client(verify=False)
        else:
            self._client = httpx.Client()

    def update_job(self, job: dict) -> dict:
        """Update an existing dbt Cloud job using a new JobDefinition"""

        logging.debug(f"Updating {job['name']}")

        response = self._client.post(
            url=f"{self.base_url}/api/v2/accounts/{self.account_id}/jobs/{job['id']}/",
            headers=self._headers,
            json=job_dict_to_payload(job),
        )

        if response.status_code >= HTTP_ERROR_CODE:
            logging.error(response.json())
            raise Exception(f"Error updating job {job['name']} - {response.json()}")
        else:
            logging.info(f"Job '{job['id']} - {job['name']}' updated successfully.")

        return response.json()["data"]

    def get_jobs(
        self,
        project_ids: Optional[List[int]] = None,
        environment_ids: Optional[List[int]] = None,
    ) -> List[dict]:
        """Return a list of Jobs for all the dbt Cloud jobs in an environment."""

        self._check_for_creds()
        project_ids = project_ids or []
        environment_ids = environment_ids or []

        jobs: List[dict] = []
        if len(environment_ids) > 1:
            for env_id in environment_ids:
                jobs.extend(self._fetch_jobs(project_ids, env_id))
        elif len(environment_ids) == 1:
            jobs = self._fetch_jobs(project_ids, environment_ids[0])
        else:
            jobs = self._fetch_jobs(project_ids, None)

        return jobs

    def _fetch_jobs(self, project_ids: List[int], environment_id: Optional[int]) -> List[dict]:
        offset = 0
        jobs: List[dict] = []

        while True:
            parameters = self._build_parameters(project_ids, environment_id, offset)
            job_data = self._make_request(parameters)

            if not job_data:
                return []

            jobs.extend(job_data["data"])

            if (
                job_data["extra"]["filters"]["limit"] + job_data["extra"]["filters"]["offset"]
                >= job_data["extra"]["pagination"]["total_count"]
            ):
                break

            offset += job_data["extra"]["filters"]["limit"]

        return jobs

    def _build_parameters(self, project_ids: List[int], environment_id: Optional[int], offset) -> dict[str, Any]:
        parameters = {"offset": offset}

        if len(project_ids) == 1:
            parameters["project_id"] = project_ids[0]
        elif len(project_ids) > 1:
            project_id_str = [str(i) for i in project_ids]
            parameters["project_id__in"] = f"[{','.join(project_id_str)}]"

        if environment_id is not None:
            parameters["environment_id"] = environment_id

        logging.debug(f"Request parameters {parameters}")
        return parameters

    def _make_request(self, parameters: dict[str, Any]):
        response = self._client.get(
            url=f"{self.base_url}/api/v2/accounts/{self.account_id}/jobs/",
            params=parameters,
            headers=self._headers,
        )

        if response.status_code >= HTTP_ERROR_CODE:
            error_data = response.json()
            logging.error(error_data)
            return None

        return response.json()

    def _check_for_creds(self):
        """Confirm the presence of credentials"""
        if not self._api_key:
            raise Exception("An API key is required to get dbt Cloud jobs.")

        if not self.account_id:
            raise Exception("An account_id is required to get dbt Cloud jobs.")


@dataclass
class DBTCloudRefactor:
    """Represents a single refactoring operation on a dbt Cloud job."""

    rule_name: str
    original_value: Any
    new_value: Any
    refactor_logs: List[str]

    def to_dict(self) -> dict:
        """Convert the refactor to a dictionary."""
        return {
            "rule_name": self.rule_name,
            "original_value": self.original_value,
            "new_value": self.new_value,
            "refactor_logs": self.refactor_logs,
        }


@dataclass
class DBTCloudChangesetResult:
    """Represents the result of a dbt Cloud job changeset."""

    dry_run: bool
    object_type: str = "job"
    object_id: int = 0
    object_name: str = ""
    original_object: Dict[str, Any] = field(default_factory=dict)
    new_object: Dict[str, Any] = field(default_factory=dict)
    url: str = ""
    refactors: List[DBTCloudRefactor] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert the changeset result to a dictionary."""
        return {
            "dry_run": self.dry_run,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "object_name": self.object_name,
            "original_object": self.original_object,
            "new_object": self.new_object,
            "url": self.url,
            "refactors": [refactor.to_dict() for refactor in self.refactors],
        }

    def print_to_console(self, json_output: bool = False):
        """Print the changeset result to the console."""
        if not self.refactors:
            return

        if json_output:
            print(json.dumps(self.to_dict()))  # noqa: T201
            return

        console.print(
            f"\n{'DRY RUN - NOT APPLIED: ' if self.dry_run else ''}{self.object_type.title()} '{self.object_id} - {self.object_name}':",
            style="green",
        )
        for refactor in self.refactors:
            console.print(f"  {refactor.rule_name}", style="yellow")
            for log in refactor.refactor_logs:
                console.print(f"    {log}")


def update_jobs(  # noqa: PLR0913
    account_id: int,
    api_key: Optional[str],
    base_url: str = "https://cloud.getdbt.com",
    disable_ssl_verification: bool = False,
    project_ids: Optional[List[int]] = None,
    environment_ids: Optional[List[int]] = None,
    dry_run: bool = False,
    json_output: bool = False,
):
    """
    Update jobs in dbt Cloud.
    """
    dbt_cloud = DBTClient(account_id, api_key, base_url, disable_ssl_verification)
    jobs = dbt_cloud.get_jobs(project_ids, environment_ids)

    changesets: List[DBTCloudChangesetResult] = []

    for job in jobs:
        modified, updated_steps = job_steps_updated(job)
        execute_steps: List[str] = job.get("execute_steps", [])

        if modified:
            refactor = DBTCloudRefactor(
                rule_name="m_selector_deprecated",
                original_value=execute_steps,
                new_value=updated_steps,
                refactor_logs=[f"Updated steps from {execute_steps} to {updated_steps}"],
            )

            new_job = job.copy()
            new_job["execute_steps"] = updated_steps

            changeset = DBTCloudChangesetResult(
                dry_run=dry_run,
                object_id=job["id"],
                object_name=job["name"],
                original_object=job,
                new_object=new_job,
                url=f"{base_url}/deploy/{account_id}/projects/{job['project_id']}/jobs/{job['id']}/settings",
                refactors=[refactor],
            )
            changesets.append(changeset)

            if not dry_run:
                dbt_cloud.update_job(new_job)
        else:
            changeset = DBTCloudChangesetResult(
                dry_run=dry_run,
                object_id=job["id"],
                object_name=job["name"],
                original_object=job,
                new_object=job,
                url=f"{base_url}/deploy/{account_id}/projects/{job['project_id']}/jobs/{job['id']}/settings",
                refactors=[],
            )
            changesets.append(changeset)
            logging.debug(f"Job '{job['id']} - {job['name']}' does not need to be updated")

    # Print results
    for changeset in changesets:
        changeset.print_to_console(json_output)
