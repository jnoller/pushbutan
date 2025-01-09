# Pushbutan

![Pushbutan Logo](https://github.com/username/pushbutan/raw/main/doc/butan.jpg)

A CLI tool to manage GPU instances in the rocket-platform GitHub Actions environment.

## Installation

```bash
pip install pushbutan
```

## Usage

First, set your GitHub token:
```bash
export GITHUB_TOKEN=your_github_token
```
The token can be a classic Github Token but must have `actions` scope, and be SSO authenticated.

### Basic Usage

```bash
pushbutan
```

This will:
1. List available workflows
2. Create a Linux GPU instance with default settings (g4dn.4xlarge)
3. Wait for the instance to be ready
4. Display instance details (ID, IP, architecture, instance type)

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

## License

[Insert your license here]