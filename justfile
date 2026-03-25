set shell := ["bash", "-euo", "pipefail", "-c"]

context := "sandpit"

alias st := status

# Show cluster status and installed addons
[default]
status:
    @uv run sandpit.py --context {{ context }} status

# Create the sandpit cluster and set up kubeconfig (idempotent)
up:
    @uv run sandpit.py --context {{ context }} up

# Delete the sandpit cluster
down:
    @uv run sandpit.py --context {{ context }} down

# Stop the sandpit cluster
stop:
    @uv run sandpit.py --context {{ context }} stop

# Start the sandpit cluster
start:
    @uv run sandpit.py --context {{ context }} start

# Install service mesh: just mesh istio
mesh provider="istio":
    @uv run sandpit.py --context {{ context }} mesh {{ provider }}

# Install auth provider: just auth dex
auth provider="dex":
    @uv run sandpit.py --context {{ context }} auth {{ provider }}

# Install gitops provider: just gitops argocd|flux-operator
gitops provider="flux":
    @uv run sandpit.py --context {{ context }} gitops {{ provider }}

# Sync (upgrade) all installed addons to their latest versions
sync:
    @uv run sandpit.py --context {{ context }} sync

# Install full stack: mesh + gitops
stack:
    @uv run sandpit.py --context {{ context }} stack
