set shell := ["bash", "-euo", "pipefail", "-c"]

context := "sandpit"
runtime := ""
_runtime_flag := if runtime != "" { "--runtime " + runtime } else { "" }

alias st := status

# Show cluster status and installed addons
[default]
status:
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} status

# Create the sandpit cluster and set up kubeconfig (idempotent)
up:
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} up

# Delete the sandpit cluster
down:
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} down

# Stop the sandpit cluster
stop:
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} stop

# Start the sandpit cluster
start:
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} start

# Install service mesh: just mesh istio
mesh provider="istio":
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} mesh {{ provider }}

# Install auth provider: just auth dex
auth provider="dex":
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} auth {{ provider }}

# Install gitops provider: just gitops argocd|flux-operator
gitops provider="flux":
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} gitops {{ provider }}

# Sync (upgrade) all installed addons to their latest versions
sync:
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} sync

# Install full stack: mesh + gitops
stack:
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} stack
