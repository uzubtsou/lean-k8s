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
    kubectl config unset current-context 2>/dev/null || true
    kubectl config delete-context {{context}} 2>/dev/null || true
    k3d cluster delete sandpit

# Stop the sandpit cluster
stop:
    k3d cluster stop sandpit

# Start the sandpit cluster
start:
    k3d cluster start sandpit

# Install a gitops addon: just add <flux|argocd>
add addon:
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{addon}}" in
        flux)
            if kubectl --context {{context}} get namespace argocd --ignore-not-found -o name 2>/dev/null | grep -q .; then
                echo "error: argocd is already installed — recreate the cluster first with: just down && just up"
                exit 0
            fi
            kubectl --context {{context}} apply --server-side -f addons/gitops/flux/install.yaml
            ;;
        argocd)
            if kubectl --context {{context}} get namespace flux-system --ignore-not-found -o name 2>/dev/null | grep -q .; then
                echo "error: flux is already installed — recreate the cluster first with: just down && just up"
                exit 0
            fi
            helm --kube-context {{context}} upgrade --install argocd argo/argo-cd \
                --namespace argocd \
                --create-namespace \
                --labels "sand.pit.im/addon=argocd" \
                --values addons/gitops/argocd/values.yaml \
                --wait
            ;;
        *)
            echo "error: unknown addon '{{addon}}'"
            echo "available addons: flux, argocd"
            exit 1
            ;;
    esac
