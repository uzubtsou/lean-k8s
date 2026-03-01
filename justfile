context := "sandpit"

default:
    @just --list

# Show cluster status and installed addons
status:
    @k3d cluster list
    @echo ""
    @if kubectl --context {{context}} get nodes --no-headers 2>/dev/null | grep -q .; then \
        printf "%-16s %s\n" "ADDON" "INSTALLED"; \
        kubectl --context {{context}} get namespace flux-system --ignore-not-found -o name 2>/dev/null | grep -q . && printf "%-16s %s\n" "flux" "true" || printf "%-16s %s\n" "flux" "false"; \
        kubectl --context {{context}} get namespace argocd --ignore-not-found -o name 2>/dev/null | grep -q . && printf "%-16s %s\n" "argocd" "true" || printf "%-16s %s\n" "argocd" "false"; \
    else \
        echo "no cluster running — skipping addon check"; \
    fi

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
    @kubectl --context {{context}} get namespace argocd --ignore-not-found -o name 2>/dev/null | grep -q . && echo "error: argocd is already installed — remove it first with: just argocd-down" && exit 1 || true
    kubectl --context {{context}} apply --server-side -f addons/gitops/flux/install.yaml

# Remove FluxCD controllers
flux-down:
    kubectl --context {{context}} delete -f addons/gitops/flux/install.yaml

# Install ArgoCD via Helm
argocd-up:
    @kubectl --context {{context}} get namespace flux-system --ignore-not-found -o name 2>/dev/null | grep -q . && echo "error: flux is already installed — remove it first with: just flux-down" && exit 1 || true
    helm --kube-context {{context}} upgrade --install argocd argo/argo-cd \
        --namespace argocd \
        --create-namespace \
        --labels "sand.pit.im/addon=argocd" \
        --values addons/gitops/argocd/values.yaml \
        --wait

# Remove ArgoCD
argocd-down:
    helm --kube-context {{context}} uninstall argocd --namespace argocd
    kubectl --context {{context}} delete namespace argocd
