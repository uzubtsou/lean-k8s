context := "sandpit"

default:
    @just --list

# Show cluster status and installed addons
status:
    @k3d cluster list
    @echo ""
    @printf "%-16s %s\n" "ADDON" "INSTALLED"
    @kubectl --context {{context}} get namespace flux-system --ignore-not-found -o name 2>/dev/null | grep -q . && printf "%-16s %s\n" "flux" "true" || printf "%-16s %s\n" "flux" "false"

# Create the sandpit cluster and set up kubeconfig
up:
    k3d cluster create --config runtimes/k3d/config.yaml
    k3d kubeconfig merge sandpit --kubeconfig-merge-default
    kubectl config rename-context k3d-sandpit {{context}}
    kubectl config use-context {{context}}

# Delete the sandpit cluster
down:
    kubectl config unset current-context
    k3d cluster delete sandpit

# Stop the sandpit cluster
stop:
    k3d cluster stop sandpit

# Start the sandpit cluster
start:
    k3d cluster start sandpit

# Install FluxCD controllers
flux-up:
    kubectl --context {{context}} apply --server-side -f addons/gitops/flux/install.yaml

# Remove FluxCD controllers
flux-down:
    kubectl --context {{context}} delete -f addons/gitops/flux/install.yaml
