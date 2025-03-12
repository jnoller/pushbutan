import os
import json
from typing import Optional, Literal
from datetime import datetime, timezone
from githubkit import GitHub
from githubkit.utils import Unset
import time
import io
import zipfile
import logging

log = logging.getLogger("pushbutan")

class PushbutanError(Exception):
    """Base exception class for Pushbutan errors"""
    pass

class GitHubEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle GitHub API response types"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Unset):
            return None
        return super().default(obj)

ArchType = Literal["win-64", "linux-64"]
InstanceType = Literal["g4dn.4xlarge", "p3.2xlarge"]
CudaVersion = Literal["none", "12.4"]

class Pushbutan:
    """
    Tool to interact with rocket-platform GitHub Actions
    """

    REPO_OWNER = "anaconda-distribution"
    REPO_NAME = "rocket-platform"
    DEV_INSTANCE_WORKFLOW_ID = 31526128  # Agents: Start dev instance
    STOP_INSTANCE_WORKFLOW_ID = 31526129  # Agents: Stop instance
    CODESIGN_WORKFLOW_ID = 93334270  # Codesign Windows Package

    def __init__(self, token: Optional[str] = None):
        """Initialize Pushbutan with GitHub token"""
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise PushbutanError("GitHub token not provided and GITHUB_TOKEN env var not set")

        self.gh = GitHub(self.token)

        # Get current user's login
        try:
            response = self.gh.rest.users.get_authenticated()
            self.username = response.parsed_data.login
        except Exception as e:
            raise PushbutanError(f"Failed to get authenticated user: {e}")

    def start_dev_instance(self, arch: ArchType, instance_type: InstanceType,
                          cuda_version: CudaVersion, image_id: str = "latest",
                          branch: str = "main", lifetime: str = "24") -> dict:
        """Base method to trigger creation of a dev instance"""
        inputs = {
            "arch": arch,
            "instance_type": instance_type,
            "cuda_version": cuda_version,
            "image_id": image_id,
            "branch": branch,
            "lifetime": lifetime
        }

        try:
            start_time = datetime.now(timezone.utc)

            # Trigger the workflow
            response = self.gh.request(
                "POST",
                f"/repos/{self.REPO_OWNER}/{self.REPO_NAME}/actions/workflows/{self.DEV_INSTANCE_WORKFLOW_ID}/dispatches",
                json={
                    "ref": "main",
                    "inputs": inputs
                }
            )

            # Find the new run
            for attempt in range(20):
                time.sleep(2)
                runs = self.gh.rest.actions.list_workflow_runs(
                    owner=self.REPO_OWNER,
                    repo=self.REPO_NAME,
                    workflow_id=self.DEV_INSTANCE_WORKFLOW_ID
                ).parsed_data.workflow_runs

                for run in runs:
                    if (run.actor.login == self.username and
                        run.created_at >= start_time):
                        return {
                            "run_id": run.id,
                            "status": run.status,
                            "created_at": run.created_at.isoformat(),
                            "html_url": run.html_url
                        }

            raise PushbutanError("Could not find the triggered workflow run after multiple attempts")

        except Exception as e:
            raise PushbutanError(f"Failed to trigger workflow: {str(e)}")

    def trigger_linux_gpu_instance(self,
                                 instance_type: InstanceType = "g4dn.4xlarge",
                                 branch: str = "main",
                                 lifetime: str = "24") -> dict:
        """
        Trigger creation of a Linux GPU instance

        Args:
            instance_type: EC2 GPU instance type (g4dn.4xlarge, p3.2xlarge)
            branch: Git branch to use
            lifetime: Hours before instance termination

        Returns:
            Dict containing the workflow run information
        """
        return self.start_dev_instance(
            arch="linux-64",
            instance_type=instance_type,
            cuda_version="12.4",  # Linux GPU instances require CUDA
            branch=branch,
            lifetime=lifetime
        )

    def trigger_windows_gpu_instance(self,
                                   instance_type: InstanceType = "g4dn.4xlarge",
                                   branch: str = "main",
                                   lifetime: str = "24") -> dict:
        """
        Trigger creation of a Windows GPU instance

        Args:
            instance_type: EC2 GPU instance type (g4dn.4xlarge, p3.2xlarge)
            branch: Git branch to use
            lifetime: Hours before instance termination

        Returns:
            Dict containing the workflow run information
        """
        return self.start_dev_instance(
            arch="win-64",
            instance_type=instance_type,
            cuda_version="none",  # Windows instances handle CUDA differently
            branch=branch,
            lifetime=lifetime
        )

    def list_workflows(self):
        """List all available workflows in the repository"""
        try:
            workflows = self.gh.rest.actions.list_repo_workflows(
                owner=self.REPO_OWNER,
                repo=self.REPO_NAME
            )
            return workflows.parsed_data.workflows
        except Exception as e:
            raise PushbutanError(f"Failed to list workflows: {e}")

    def get_workflow_run(self, run_id: int):
        """Get details about a specific workflow run"""
        try:
            response = self.gh.rest.actions.get_workflow_run(
                owner=self.REPO_OWNER,
                repo=self.REPO_NAME,
                run_id=run_id
            )
            return response.parsed_data
        except Exception as e:
            raise PushbutanError(f"Failed to get workflow run: {e}")

    def get_latest_workflow_run(self):
        """Get the most recent workflow run for our workflow"""
        try:
            response = self.gh.rest.actions.list_workflow_runs(
                owner=self.REPO_OWNER,
                repo=self.REPO_NAME,
                workflow_id=self.DEV_INSTANCE_WORKFLOW_ID
            )
            runs = response.parsed_data.workflow_runs
            if not runs:
                raise PushbutanError("No workflow runs found")
            return runs[0]  # Most recent run
        except Exception as e:
            raise PushbutanError(f"Failed to list workflow runs: {e}")

    def get_run_logs(self, run_id: int, save_logs: bool = False) -> str:
        """
        Get the logs for a specific workflow run

        Args:
            run_id: The workflow run ID
            save_logs: Whether to save logs to disk (default: False)

        Returns:
            Combined log content as string
        """
        try:
            # Download the logs (returns zip file content)
            response = self.gh.rest.actions.download_workflow_run_logs(
                owner=self.REPO_OWNER,
                repo=self.REPO_NAME,
                run_id=run_id
            )

            # Create a BytesIO object from the response content
            zip_bytes = io.BytesIO(response.content)

            # Extract all text files from the zip
            all_logs = []
            with zipfile.ZipFile(zip_bytes) as zip_file:
                for file_name in zip_file.namelist():
                    if file_name.endswith('.txt'):
                        log_content = zip_file.read(file_name).decode('utf-8')
                        all_logs.append(log_content)

                        # Save individual log files only if requested
                        if save_logs:
                            # Create logs directory if needed
                            os.makedirs('logs', exist_ok=True)

                            # Save individual log file
                            log_path = f'logs/run_{run_id}_{file_name.replace("/", "_")}'
                            with open(log_path, 'w') as f:
                                f.write(log_content)
                            log.info(f"Saved log file to: {log_path}")

            # Combine all logs
            combined_logs = '\n'.join(all_logs)

            # Save combined logs if requested
            if save_logs:
                combined_path = f'logs/run_{run_id}_combined.txt'
                with open(combined_path, 'w') as f:
                    f.write(combined_logs)
                log.info(f"Saved combined logs to: {combined_path}")

                # Save the original zip file
                zip_path = f'logs/run_{run_id}.zip'
                with open(zip_path, 'wb') as f:
                    f.write(response.content)
                log.info(f"Saved zip file to: {zip_path}")

            return combined_logs

        except Exception as e:
            raise PushbutanError(f"Failed to get workflow run logs: {e}")

    def extract_instance_details(self, logs: str) -> dict:
        """Extract instance details from workflow logs"""
        import re

        log.info("Searching logs for instance details...")

        # Look for all instance details in the logs, ignoring timestamps
        instance_id_match = re.search(r'.*INSTANCE_IDS:\s+(i-[a-f0-9]+)', logs, re.MULTILINE)
        ip_match = re.search(r'.*\[ "(\d+\.\d+\.\d+\.\d+)" \]', logs, re.MULTILINE)
        platform_match = re.search(r'.*PLATFORM:\s+(linux-64|win-64)', logs, re.MULTILINE)
        instance_type_match = re.search(r'.*INSTANCE_TYPE:\s+(g4dn\.4xlarge|p3\.2xlarge)', logs, re.MULTILINE)

        if not instance_id_match:
            log.error("Could not find instance ID in logs")
            raise PushbutanError("Could not find instance ID in workflow logs")

        if not ip_match:
            log.error("Could not find IP address in logs")
            raise PushbutanError("Could not find IP address in workflow logs")

        if not platform_match:
            log.error("Could not find platform in logs")
            raise PushbutanError("Could not find platform in workflow logs")

        if not instance_type_match:
            log.error("Could not find instance type in logs")
            raise PushbutanError("Could not find instance type in workflow logs")

        instance_id = instance_id_match.group(1)
        ip_address = ip_match.group(1)
        platform = platform_match.group(1)
        instance_type = instance_type_match.group(1)


        return {
            "instance_id": instance_id,
            "ip_address": ip_address,
            "arch": platform,
            "instance_type": instance_type
        }

    def wait_for_instance(self, run_id: int, timeout_minutes: int = 15, parse_logs: bool = True, save_logs: bool = False) -> dict:
        """
        Wait for a workflow run to complete

        Args:
            run_id: The workflow run ID to monitor
            timeout_minutes: How long to wait before giving up
            parse_logs: Whether to parse logs for instance details (default: True)
            save_logs: Whether to save logs to disk for debugging (default: False)

        Returns:
            Dict with workflow results (instance details for start, success status for stop)
        """
        log.info(f"Waiting for workflow run {run_id} to complete...")
        start_time = time.time()
        timeout = timeout_minutes * 60

        while time.time() - start_time < timeout:
            run = self.get_workflow_run(run_id)
            status = run.status
            conclusion = run.conclusion

            log.info(f"Status: {status} ({conclusion if conclusion else 'in progress'})")

            if status == "completed":
                if conclusion == "success":
                    if parse_logs:
                        # Get and parse the logs to extract instance details
                        logs = self.get_run_logs(run_id, save_logs=save_logs)
                        return self.extract_instance_details(logs)
                    else:
                        return {"success": True}
                else:
                    raise PushbutanError(f"Workflow failed with conclusion: {conclusion}")

            time.sleep(30)  # Check every 30 seconds

        raise PushbutanError(f"Timed out after {timeout_minutes} minutes")

    def stop_instance(self, instance_id: str) -> dict:
        """
        Trigger workflow to stop a dev instance

        Args:
            instance_id: The EC2 instance ID to stop (e.g., 'i-1234567890abcdef0')

        Returns:
            Dict containing the workflow run information
        """
        try:
            log.info(f"Triggering stop workflow for instance: {instance_id}")

            # Trigger the workflow
            response = self.gh.request(
                "POST",
                f"/repos/{self.REPO_OWNER}/{self.REPO_NAME}/actions/workflows/{self.STOP_INSTANCE_WORKFLOW_ID}/dispatches",
                json={
                    "ref": "main",
                    "inputs": {
                        "instance_ids": instance_id
                    }
                }
            )

            log.info(f"Response status: {response.status_code}")

            # Get the run ID using similar logic to start_dev_instance
            start_time = datetime.now(timezone.utc)
            log.info("Waiting for workflow to start...")

            # Initial sleep to give GitHub time to register the workflow
            for _ in range(5):
                time.sleep(1)

            # Retry loop to find the new run
            max_attempts = 20
            attempt = 0
            while attempt < max_attempts:
                attempt += 1

                runs = self.gh.rest.actions.list_workflow_runs(
                    owner=self.REPO_OWNER,
                    repo=self.REPO_NAME,
                    workflow_id=self.STOP_INSTANCE_WORKFLOW_ID
                ).parsed_data.workflow_runs

                for run in runs:
                    if (run.actor.login == self.username and
                        run.created_at >= start_time):
                        log.info(f"Found workflow run after {attempt} attempts")
                        return {"run_id": run.id}

                time.sleep(2)

            raise PushbutanError("Could not find the triggered workflow run after multiple attempts")

        except Exception as e:
            log.error(f"Failed to stop instance: {instance_id}")
            if hasattr(e, 'response'):
                log.error(f"Response status: {e.response.status_code}")
                log.error(f"Response body: {e.response.text}")
            raise PushbutanError(f"Failed to trigger stop workflow: {e}")

    def get_workflow_details(self, workflow_id: int):
        """Get details about a specific workflow"""
        try:
            # First get the workflow metadata
            workflow = self.gh.rest.actions.get_workflow(
                owner=self.REPO_OWNER,
                repo=self.REPO_NAME,
                workflow_id=workflow_id
            ).parsed_data

            log.info(f"Workflow path: {workflow.path}")

            # Then get the actual workflow file content
            content = self.gh.rest.repos.get_content(
                owner=self.REPO_OWNER,
                repo=self.REPO_NAME,
                path=workflow.path
            ).parsed_data

            # Content is base64 encoded
            import base64
            decoded_content = base64.b64decode(content.content).decode('utf-8')

            return {
                "id": workflow.id,
                "name": workflow.name,
                "path": workflow.path,
                "content": decoded_content
            }

        except Exception as e:
            log.error(f"Error details: {e}")
            if hasattr(e, 'response'):
                log.error(f"Response status: {e.response.status_code}")
                log.error(f"Response body: {e.response.text}")
            raise PushbutanError(f"Failed to get workflow details: {e}")

    def inspect_codesign_workflow(self) -> dict:
        """
        Get details about the codesign workflow and its expected inputs
        """
        try:
            details = self.get_workflow_details(self.CODESIGN_WORKFLOW_ID)
            return details
        except Exception as e:
            raise PushbutanError(f"Failed to inspect codesign workflow: {e}")

    def trigger_codesign(self, cert: str, org_channel: str, package_spec: Optional[str] = None,
                        generate_repodata: bool = False) -> dict:
        """
        Trigger Windows package codesigning workflow

        Args:
            cert: Which certificate to use ('prod' or 'dev')
            org_channel: The anaconda.org channel to search
            package_spec: Package spec to search for (optional)
            generate_repodata: Whether to generate repodata files (default: False)

        Returns:
            Dict containing the workflow run information
        """
        inputs = {
            "cert": cert,
            "org_channel": org_channel,
            "package_spec": package_spec or "",
            "generate_repodata_files": generate_repodata
        }

        try:
            # Create timezone-aware UTC datetime
            start_time = datetime.now(timezone.utc)
            log.info(f"Start time: {start_time.strftime('%Y-%m-%dT%H:%M:%SZ')}")
            log.info(f"Current user: {self.username}")

            log.info(f"Triggering workflow with inputs: {json.dumps(inputs, indent=2)}")

            # Trigger the workflow
            response = self.gh.request(
                "POST",
                f"/repos/{self.REPO_OWNER}/{self.REPO_NAME}/actions/workflows/{self.CODESIGN_WORKFLOW_ID}/dispatches",
                json={
                    "ref": "main",
                    "inputs": inputs
                }
            )

            log.info(f"Response status: {response.status_code}")
            log.info("Waiting for workflow to start")

            # Initial sleep to give GitHub time to register the workflow
            for _ in range(5):
                time.sleep(1)

            # Retry loop to find the new run
            max_attempts = 20
            attempt = 0
            while attempt < max_attempts:
                attempt += 1

                # Get recent runs
                runs = self.gh.rest.actions.list_workflow_runs(
                    owner=self.REPO_OWNER,
                    repo=self.REPO_NAME,
                    workflow_id=self.CODESIGN_WORKFLOW_ID
                ).parsed_data.workflow_runs

                # Filter runs manually since the API filtering isn't reliable
                for run in runs:
                    if (run.actor.login == self.username and
                        run.created_at >= start_time):  # Now comparing timezone-aware datetimes
                        log.info(f"Found workflow run after {attempt} attempts")
                        return {"run_id": run.id}

                time.sleep(2)

            # If we get here, show all runs to help debug
            log.info("All recent workflow runs:")
            all_runs = self.gh.rest.actions.list_workflow_runs(
                owner=self.REPO_OWNER,
                repo=self.REPO_NAME,
                workflow_id=self.CODESIGN_WORKFLOW_ID
            ).parsed_data.workflow_runs

            log.info(f"Found {len(all_runs)} total runs:")
            for run in all_runs[:5]:
                log.info(f"Run ID: {run.id}")
                log.info(f"Created: {run.created_at}")
                log.info(f"Status: {run.status}")
                log.info(f"Actor: {run.actor.login if run.actor else 'None'}")

            raise PushbutanError("Could not find the triggered workflow run after multiple attempts")

        except Exception as e:
            log.error(f"Request failed with inputs: {json.dumps(inputs, indent=2)}")
            if hasattr(e, 'response'):
                log.error(f"Response status: {e.response.status_code}")
                log.error(f"Response body: {e.response.text}")
            raise PushbutanError(f"Failed to trigger workflow: {e}")

    def download_workflow_artifact(self, run_id: int, artifact_name: str, download_dir: str) -> str:
        """
        Download an artifact from a workflow run

        Args:
            run_id: The workflow run ID
            artifact_name: Name of the artifact to download
            download_dir: Directory to save the artifact

        Returns:
            Path to the downloaded artifact
        """
        try:
            # List artifacts for the run
            artifacts = self.gh.rest.actions.list_workflow_run_artifacts(
                owner=self.REPO_OWNER,
                repo=self.REPO_NAME,
                run_id=run_id
            ).parsed_data.artifacts

            # Find our artifact
            artifact = next((a for a in artifacts if a.name == artifact_name), None)
            if not artifact:
                raise PushbutanError(f"Could not find artifact '{artifact_name}' in workflow run")

            # Download the artifact
            log.info(f"Downloading {artifact_name} ({artifact.size_in_bytes/1024/1024:.1f} MB)...")
            response = self.gh.rest.actions.download_artifact(
                owner=self.REPO_OWNER,
                repo=self.REPO_NAME,
                artifact_id=artifact.id,
                archive_format="zip"
            )

            # Create download directory
            os.makedirs(download_dir, exist_ok=True)

            # Save the artifact
            artifact_path = os.path.join(download_dir, f"{artifact_name}.zip")
            with open(artifact_path, 'wb') as f:
                f.write(response.content)

            log.info(f"Saved artifact to: {artifact_path}")
            return artifact_path

        except Exception as e:
            raise PushbutanError(f"Failed to download artifact: {e}")
