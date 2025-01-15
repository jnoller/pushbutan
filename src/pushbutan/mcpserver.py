# mcpserver.py - a simple MCP server for executing pushbutan commands

from mcp.server.fastmcp import FastMCP
from mcp import types
from .pushbutan import Pushbutan, PushbutanError, InstanceType
import os
import json

mcp = FastMCP("Pushbutan")

@mcp.tool()
def list_gpu_instance_types():
    """ List all available GPU instance types 
    
    Returns:
        JSON string containing the list of available GPU instance types
    """
    return json.dumps(list(InstanceType.__args__))

@mcp.tool()
def list_workflows():
    """ List all available workflows on the rocket-platform repo 
    
    Returns:
        String representation of the available GitHub Actions workflows
    """
    pb = Pushbutan()
    workflows = pb.list_workflows()
    workflows = {workflow.name: workflow.id for workflow in workflows}
    return json.dumps(workflows)

@mcp.tool()
def start_linux_gpu_instance(instance_type: InstanceType, branch: str = "main", lifetime: int = 24):
    """ Start a new Linux GPU instance 
    
        Trigger creation of a Linux GPU instance
        
        Args:
            instance_type: EC2 GPU instance type (g4dn.4xlarge, p3.2xlarge)
            branch: Git branch to use for the job (default: "main")
            lifetime: Hours before instance termination (default: 24)
            
        Returns:
            String representation of the workflow information. Use get_instance_status 
            with the returned run_id to check instance status.
    """
    pb = Pushbutan()
    response = pb.trigger_linux_gpu_instance(instance_type, branch, str(lifetime))
    return json.dumps(response)

@mcp.tool()
def stop_instance(instance_id: str):
    """ Stop the current instance 
    
    Args:
        instance_id: ID of the instance to stop
        
    Returns:
        String representation of the workflow information. Use get_instance_status 
        with the returned run_id to check stop status.
    """
    pb = Pushbutan()
    response = pb.stop_instance(instance_id=instance_id)
    return json.dumps(response)

@mcp.tool()
def get_instance_details(run_id: int):
    """ Get the instance details from the job logs 
    
    Args:
        run_id: The workflow run ID to check
        
    Returns:
        String representation of the instance details (ID, IP, etc)
        Will raise an error if logs cannot be parsed or instance details not found
    """
    pb = Pushbutan()
    logs = pb.get_run_logs(run_id)
    instance_info = pb.extract_instance_details(logs)
    return json.dumps(instance_info)

@mcp.tool()
def get_job_status(run_id: int):
    """ Get the status of a workflow run
    
    Args:
        run_id: The workflow run ID to check
        
    Returns:
        String representation of the workflow status.
        Status will be one of: "ready", "in_progress", or "failed"
    """
    pb = Pushbutan()
    try:
        run = pb.get_workflow_run(run_id)
        
        if run.status == "completed":
            if run.conclusion == "success":
                return json.dumps({
                    "status": "ready",
                    "message": "Workflow completed successfully"
                })
            else:
                return json.dumps({
                    "status": "failed",
                    "error": f"Workflow failed with conclusion: {run.conclusion}"
                })
        else:
            return json.dumps({
                "status": "in_progress",
                "workflow_status": run.status,
                "workflow_conclusion": run.conclusion
            })
            
    except PushbutanError as e:
        return json.dumps({
            "status": "failed",
            "error": str(e)
        })

def run_mcp_server():
    """Entry point for the MCP server"""
    mcp.run()