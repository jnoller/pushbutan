import os
import json
from typing import Optional, Literal
from datetime import datetime, timezone
from githubkit import GitHub
from githubkit.utils import Unset
import time
import io
import zipfile

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
    DEV_INSTANCE_WORKFLOW_ID = 31526128
    
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
    
    def trigger_dev_instance(self, 
                           arch: ArchType,
                           instance_type: InstanceType,
                           cuda_version: CudaVersion,
                           image_id: str = "latest",
                           branch: str = "main",
                           lifetime: str = "24") -> dict:
        """
        Base method to trigger creation of a dev instance
        """
        inputs = {
            "arch": arch,
            "instance_type": instance_type,
            "cuda_version": cuda_version,
            "image_id": image_id,
            "branch": branch,
            "lifetime": lifetime
        }
        
        try:
            # Create timezone-aware UTC datetime
            start_time = datetime.now(timezone.utc)
            print(f"Start time: {start_time.strftime('%Y-%m-%dT%H:%M:%SZ')}")
            print(f"Current user: {self.username}")
            
            print(f"Triggering workflow with inputs: {json.dumps(inputs, indent=2)}")
            
            # Trigger the workflow
            response = self.gh.request(
                "POST",
                f"/repos/{self.REPO_OWNER}/{self.REPO_NAME}/actions/workflows/{self.DEV_INSTANCE_WORKFLOW_ID}/dispatches",
                json={
                    "ref": "main",
                    "inputs": inputs
                }
            )
            
            print(f"Response status: {response.status_code}")
            print("Waiting for workflow to start", end="", flush=True)
            
            # Initial sleep to give GitHub time to register the workflow
            for _ in range(5):
                time.sleep(1)
                print(".", end="", flush=True)
            
            # Retry loop to find the new run
            max_attempts = 20
            attempt = 0
            while attempt < max_attempts:
                attempt += 1
                print(".", end="", flush=True)
                
                # Get recent runs
                runs = self.gh.rest.actions.list_workflow_runs(
                    owner=self.REPO_OWNER,
                    repo=self.REPO_NAME,
                    workflow_id=self.DEV_INSTANCE_WORKFLOW_ID
                ).parsed_data.workflow_runs
                
                # Filter runs manually since the API filtering isn't reliable
                for run in runs:
                    if (run.actor.login == self.username and 
                        run.created_at >= start_time):  # Now comparing timezone-aware datetimes
                        print("\nFound workflow run after", attempt, "attempts")
                        return {"run_id": run.id}
                
                time.sleep(2)
            
            print("\n")  # End the progress line
            
            # If we get here, show all runs to help debug
            print("\nAll recent workflow runs:")
            all_runs = self.gh.rest.actions.list_workflow_runs(
                owner=self.REPO_OWNER,
                repo=self.REPO_NAME,
                workflow_id=self.DEV_INSTANCE_WORKFLOW_ID
            ).parsed_data.workflow_runs
            
            print(f"Found {len(all_runs)} total runs:")
            for run in all_runs[:5]:
                print(f"- Run ID: {run.id}")
                print(f"  Created: {run.created_at}")
                print(f"  Status: {run.status}")
                print(f"  Actor: {run.actor.login if run.actor else 'None'}")
            
            raise PushbutanError("Could not find the triggered workflow run after multiple attempts")
            
        except Exception as e:
            print(f"Request failed with inputs: {json.dumps(inputs, indent=2)}")
            if hasattr(e, 'response'):
                print(f"Response status: {e.response.status_code}")
                print(f"Response body: {e.response.text}")
            raise PushbutanError(f"Failed to trigger workflow: {e}")

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
        return self.trigger_dev_instance(
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
        return self.trigger_dev_instance(
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
    
    def get_run_logs(self, run_id: int) -> str:
        """Get the logs for a specific workflow run"""
        try:
            # Download the logs (returns zip file content)
            response = self.gh.rest.actions.download_workflow_run_logs(
                owner=self.REPO_OWNER,
                repo=self.REPO_NAME,
                run_id=run_id
            )
            
            # Create a logs directory if it doesn't exist
            os.makedirs('logs', exist_ok=True)
            
            # Save the zip file
            zip_path = f'logs/run_{run_id}.zip'
            with open(zip_path, 'wb') as f:
                f.write(response.content)
            print(f"\nSaved zip file to: {zip_path}")
            
            # Create a BytesIO object from the response content
            zip_bytes = io.BytesIO(response.content)
            
            # Extract all text files from the zip
            all_logs = []
            with zipfile.ZipFile(zip_bytes) as zip_file:
                # Save each log file individually
                for file_name in zip_file.namelist():
                    if file_name.endswith('.txt'):
                        log_content = zip_file.read(file_name).decode('utf-8')
                        all_logs.append(log_content)
                        
                        # Save individual log file
                        log_path = f'logs/run_{run_id}_{file_name.replace("/", "_")}'
                        with open(log_path, 'w') as f:
                            f.write(log_content)
                        print(f"Saved log file to: {log_path}")
            
            # Save combined logs
            combined_logs = '\n'.join(all_logs)
            combined_path = f'logs/run_{run_id}_combined.txt'
            with open(combined_path, 'w') as f:
                f.write(combined_logs)
            print(f"Saved combined logs to: {combined_path}")
            
            return combined_logs
            
        except Exception as e:
            raise PushbutanError(f"Failed to get workflow run logs: {e}")
    
    def extract_instance_details(self, logs: str) -> dict:
        """Extract instance details from workflow logs"""
        import re
        
        print("\nSearching logs for instance details...")
        
        # Look for all instance details in the logs
        instance_id_match = re.search(r'INSTANCE_IDS: (i-[a-f0-9]+)', logs)
        ip_match = re.search(r'\[ "(\d+\.\d+\.\d+\.\d+)" \]', logs)
        platform_match = re.search(r'PLATFORM: (\S+)', logs)
        instance_type_match = re.search(r'INSTANCE_TYPE: (\S+)', logs)
        
        # Print debug info for each pattern
        print("\nDebug info:")
        print(f"Instance ID pattern: {'found' if instance_id_match else 'not found'}")
        print(f"IP pattern: {'found' if ip_match else 'not found'}")
        print(f"Platform pattern: {'found' if platform_match else 'not found'}")
        print(f"Instance type pattern: {'found' if instance_type_match else 'not found'}")
        
        if not instance_id_match:
            print("Could not find instance ID in logs")
            raise PushbutanError("Could not find instance ID in workflow logs")
            
        if not ip_match:
            print("Could not find IP address in logs")
            raise PushbutanError("Could not find IP address in workflow logs")
            
        if not instance_type_match:
            print("Could not find instance type in logs")
            raise PushbutanError("Could not find instance type in workflow logs")
            
        instance_id = instance_id_match.group(1)
        ip_address = ip_match.group(1)
        platform = platform_match.group(1)
        instance_type = instance_type_match.group(1)
        
        print(f"\nFound instance details:")
        print(f"- Instance ID: {instance_id}")
        print(f"- IP Address: {ip_address}")
        print(f"- Platform: {platform}")
        print(f"- Instance Type: {instance_type}")
            
        return {
            "instance_id": instance_id,
            "ip_address": ip_address,
            "arch": platform,
            "instance_type": instance_type
        }
    
    def wait_for_instance(self, run_id: int, timeout_minutes: int = 15) -> dict:
        """
        Wait for the instance to be ready and return its details
        
        Args:
            run_id: The workflow run ID to monitor
            timeout_minutes: How long to wait before giving up
            
        Returns:
            Dict with instance_id and ip_address
        """
        print(f"\nWaiting for instance to be ready (run ID: {run_id})...")
        start_time = time.time()
        timeout = timeout_minutes * 60
        
        while time.time() - start_time < timeout:
            run = self.get_workflow_run(run_id)
            status = run.status
            conclusion = run.conclusion
            
            print(f"Status: {status} ({conclusion if conclusion else 'in progress'})")
            
            if status == "completed":
                if conclusion == "success":
                    # Get and parse the logs to extract instance details
                    logs = self.get_run_logs(run_id)
                    return self.extract_instance_details(logs)
                else:
                    raise PushbutanError(f"Workflow failed with conclusion: {conclusion}")
            
            time.sleep(30)  # Check every 30 seconds
            
        raise PushbutanError(f"Timed out after {timeout_minutes} minutes")

def main():
    """Main entry point"""
    try:
        pb = Pushbutan()
        
        # List available workflows
        workflows = pb.list_workflows()
        print("\nAvailable workflows:")
        for workflow in workflows:
            print(f"- {workflow.name} (ID: {workflow.id})")
        
        # Trigger a Linux GPU instance
        print("\nTriggering Linux GPU instance creation...")
        result = pb.trigger_linux_gpu_instance(
            instance_type="g4dn.4xlarge",
            lifetime="24"
        )
        
        # Wait for instance and get details
        instance = pb.wait_for_instance(result["run_id"])
        print("\nInstance ready!")
        print(f"Instance ID: {instance['instance_id']}")
        print(f"IP Address: {instance['ip_address']}")
        print(f"Instance Type: {instance['instance_type']}")
        
    except PushbutanError as e:
        print(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
