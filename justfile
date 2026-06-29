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

# Install Istio service mesh
mesh:
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} mesh

# Install Dex auth provider
auth:
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} auth

# Install gitops provider: just gitops flux|argocd|flux-operator
gitops provider="flux":
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} gitops {{ provider }}

# Install Flagger progressive delivery
progressive:
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} progressive

# Install Prometheus observability
prometheus:
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} prometheus

# Install Prometheus observability (old alias)
observability:
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} observability

# Install Kiali service mesh UI
kiali:
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} kiali

# Sync (upgrade) all installed addons to their latest versions
sync:
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} sync

# Install full stack: mesh + gitops
stack:
    @uv run sandpit.py --context {{ context }} {{ _runtime_flag }} stack
