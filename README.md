# Pushbutan
<img src="docs/butan.jpg" alt="Sisyphus" width="40%" height="40%"/>

A tool to manage GPU instances in the rocket-platform GitHub Actions environment.

## Installation

```bash
git clone https://github.com/jnoller/pushbutan
cd pushbutan
conda create -n pushbutan
conda activate pushbutan
pip install -e .
```

## Usage

First, set your GitHub token:
```bash
export GITHUB_TOKEN=your_github_token
```
The token can be a classic Github Token but must have `actions` scope, and be SSO authenticated.

### CLI Commands

List available workflows:
```bash
pushbutan list
```

Start a Linux GPU instance (default):
```bash
pushbutan start
```

Start with specific options:
```bash
# Choose instance type
pushbutan start --instance-type p3.2xlarge

# Set instance lifetime
pushbutan start --lifetime 48

# Start a Windows instance
pushbutan start --windows

# Save logs for debugging
pushbutan start --save-logs

# Combine multiple options
pushbutan start --instance-type p3.2xlarge --lifetime 48 --windows --save-logs
```

Stop an instance:
```bash
pushbutan stop i-1234567890abcdef0
```

Sign Windows packages:
```bash
# Basic usage - sign all packages in a channel
pushbutan codesign --channel jnoller/label/jnoller --package "llama.cpp=*" \
    --download-dir win-64-signed

# Sign specific package with options
pushbutan codesign \
    --cert prod \
    --channel jnoller/label/jnoller \
    --package "llama.cpp=*" \
    --generate-repodata \
    --download-dir win-64-signed \
    --save-logs \
    --timeout 180  # Wait up to 3 hours
```

### Python API

```python
from pushbutan import Pushbutan

pb = Pushbutan()

# Create a Linux GPU instance
result = pb.trigger_linux_gpu_instance(
    instance_type="g4dn.4xlarge",  # or "p3.2xlarge"
    lifetime="24"  # hours
)

# Wait for instance and get details
instance = pb.wait_for_instance(result["run_id"])
print(f"Instance ID: {instance['instance_id']}")
print(f"IP Address: {instance['ip_address']}")
print(f"Instance Type: {instance['instance_type']}")

# Create a Windows GPU instance
result = pb.trigger_windows_gpu_instance(
    instance_type="g4dn.4xlarge",
    lifetime="24"
)
```

### Available Instance Types

- `g4dn.4xlarge`
- `p3.2xlarge`

### Available Architectures

- `linux-64`: Linux with CUDA 12.4
- `win-64`: Windows (CUDA handled differently)

## Development

```bash
git clone https://github.com/your-username/pushbutan.git
cd pushbutan
pip install -e .
```

## Using the Presbutn MCP Server with Claude Desktop

```bash
git clone https://github.com/jnoller/pushbutan
cd pushbutan
conda create -n pushbutan
conda activate pushbutan
pip install -e .
```

Modify your Claude Desktop Configuration file (claude_desktop_config.json) to launch the MCP server:

* Set the `command` to the path to your conda binary
* Set the `GITHUB_TOKEN` to your GitHub token

```json
{
    "Presbutan": {
      "command": "<path_to_conda_binary>",
      "args": ["run", "-n", "pushbutan", "--no-capture-output", "mcpserver"],
      "env": {
        "GITHUB_TOKEN": "<your_github_token>"
      } 
    }
  }
}
```
