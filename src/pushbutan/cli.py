import click
from .pushbutan import Pushbutan, PushbutanError, InstanceType

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

def main():
    """CLI entry point"""
    cli()

if __name__ == "__main__":
    main() 