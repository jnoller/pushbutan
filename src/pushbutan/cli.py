import click
from .pushbutan import Pushbutan, PushbutanError, InstanceType
from typing import Optional

@click.group()
def cli():
    """Pushbutan CLI - Manage GPU instances in rocket-platform"""
    pass

@cli.command()
def list():
    """List available workflows"""
    try:
        pb = Pushbutan()
        workflows = pb.list_workflows()
        click.echo("\nAvailable workflows:")
        for workflow in workflows:
            click.echo(f"- {workflow.name} (ID: {workflow.id})")
    except PushbutanError as e:
        click.echo(f"Error: {e}", err=True)
        exit(1)

@cli.command()
@click.option('--instance-type', type=click.Choice(['g4dn.4xlarge', 'p3.2xlarge']), 
              default='g4dn.4xlarge', help='EC2 instance type')
@click.option('--lifetime', default='24', help='Instance lifetime in hours')
@click.option('--windows/--linux', default=False, help='Create Windows instance instead of Linux')
@click.option('--save-logs', is_flag=True, help='Save workflow logs to disk for debugging')
def start(instance_type: InstanceType, lifetime: str, windows: bool, save_logs: bool):
    """Start a new GPU instance"""
    try:
        pb = Pushbutan()
        
        if windows:
            click.echo("\nStarting Windows GPU instance...")
            result = pb.trigger_windows_gpu_instance(
                instance_type=instance_type,
                lifetime=lifetime
            )
        else:
            click.echo("\nStarting Linux GPU instance...")
            result = pb.trigger_linux_gpu_instance(
                instance_type=instance_type,
                lifetime=lifetime
            )
        
        # Wait for the instance
        instance = pb.wait_for_instance(result["run_id"], parse_logs=True, save_logs=save_logs)
        
        click.echo("\nInstance ready!")
        click.echo(f"Instance ID: {instance['instance_id']}")
        click.echo(f"IP Address: {instance['ip_address']}")
        click.echo(f"Instance Type: {instance['instance_type']}")
        
    except PushbutanError as e:
        click.echo(f"Error: {e}", err=True)
        exit(1)

@cli.command()
@click.argument('instance-id')
def stop(instance_id: str):
    """Stop a running instance"""
    try:
        pb = Pushbutan()
        
        click.echo(f"\nStopping instance {instance_id}...")
        stop_result = pb.stop_instance(instance_id)
        
        # Wait for stop completion without parsing logs
        pb.wait_for_instance(stop_result["run_id"], parse_logs=False)
        click.echo("\nInstance stop workflow completed!")
        
    except PushbutanError as e:
        click.echo(f"Error: {e}", err=True)
        exit(1)

@cli.command()
@click.option('--inspect', is_flag=True, help='Show workflow details and expected inputs')
@click.option('--cert', type=click.Choice(['prod', 'dev']), default='prod', 
              help='Which certificate to use')
@click.option('--channel', required=True, help='The anaconda.org channel to search')
@click.option('--package', help='Package spec to search for (empty for all packages)')
@click.option('--generate-repodata', is_flag=True, help='Generate repodata files')
@click.option('--download-dir', help='Directory to save signed packages')
@click.option('--save-logs', is_flag=True, help='Save workflow logs for debugging')
def codesign(inspect: bool, cert: str, channel: str, package: Optional[str], 
            generate_repodata: bool, download_dir: Optional[str], save_logs: bool):
    """Trigger Windows package codesigning workflow"""
    try:
        pb = Pushbutan()
        
        if inspect:
            details = pb.inspect_codesign_workflow()
            click.echo("\nCodesign Workflow Details:")
            click.echo(f"Name: {details['name']}")
            click.echo(f"ID: {details['id']}")
            click.echo("\nWorkflow Content:")
            click.echo(details['content'])
        else:
            click.echo("\nTriggering codesign workflow...")
            result = pb.trigger_codesign(
                cert=cert,
                org_channel=channel,
                package_spec=package,
                generate_repodata=generate_repodata
            )
            
            # Wait for workflow completion
            run_id = result["run_id"]
            click.echo(f"Workflow triggered successfully (Run ID: {run_id})")
            
            # Wait for completion
            pb.wait_for_instance(run_id, parse_logs=False, save_logs=save_logs)
            click.echo("\nCodesign workflow completed!")
            
            # Download artifacts if requested
            if download_dir:
                artifact_path = pb.download_workflow_artifact(
                    run_id=run_id,
                    artifact_name="signed-packages",
                    download_dir=download_dir
                )
                click.echo(f"\nSigned packages downloaded to: {artifact_path}")
        
    except PushbutanError as e:
        click.echo(f"Error: {e}", err=True)
        exit(1)

def main():
    """CLI entry point"""
    cli()

if __name__ == "__main__":
    main() 