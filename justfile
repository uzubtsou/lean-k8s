set shell := ["bash", "-euo", "pipefail", "-c"]

context := "sandpit"

default:
    @just status

# Show cluster status and installed addons
[script]
status:
    k3d cluster list
    echo ""
    if ! kubectl --context {{context}} get nodes --no-headers 2>/dev/null | grep -q .; then
        echo "no cluster running"
        exit 0
    fi
    addons=$(kubectl --context {{context}} get namespaces \
        --selector='sand.pit.im/addon' \
        --no-headers \
        -o custom-columns=':.metadata.labels.sand\.pit\.im/addon' \
        2>/dev/null | sort -u)
    if [[ -n "$addons" ]]; then
        printf "%-16s\n" "ADDONS"
        echo "$addons" | while read -r name; do
            printf "  %s\n" "$name"
        done
    else
        echo "no addons installed"
    fi

# Create the sandpit cluster and set up kubeconfig (idempotent)
[script]
up:
    if k3d cluster get sandpit > /dev/null 2>&1; then
        echo "cluster sandpit already exists, skipping"
    else
        k3d cluster create --config runtimes/k3d/config.yaml
        k3d kubeconfig merge sandpit --kubeconfig-merge-default
        kubectl config rename-context k3d-sandpit {{context}}
        kubectl config use-context {{context}}
    fi

# Delete the sandpit cluster
down:
    @kubectl config unset current-context 2>/dev/null || true
    @kubectl config delete-context {{context}} 2>/dev/null || true
    @k3d cluster delete sandpit

# Stop the sandpit cluster
stop:
    @k3d cluster stop sandpit

# Start the sandpit cluster
start:
    @k3d cluster start sandpit

# Install service mesh: just mesh istio
[script]
mesh provider="istio": up
    addon_installed() {
        local ns="$1"
        kubectl --context {{context}} get namespace "$ns" \
            --ignore-not-found \
            -o name \
            2>/dev/null | grep -q .
    }

    case "{{provider}}" in
        istio)
            if addon_installed istio-system; then
                echo "istio is already installed, skipping"
                exit 0
            fi

            # install Gateway API CRDs if not present
            if ! kubectl --context {{context}} get crd gateways.gateway.networking.k8s.io \
                    > /dev/null 2>&1; then
                kubectl --context {{context}} apply -f \
                    https://github.com/kubernetes-sigs/gateway-api/releases/latest/download/standard-install.yaml
            fi

            helm repo add istio https://istio-release.storage.googleapis.com/charts
            helm repo update istio

            helm --kube-context {{context}} upgrade --install istio-base istio/base \
                --namespace istio-system \
                --create-namespace \
                --wait

            helm --kube-context {{context}} upgrade --install istiod istio/istiod \
                --namespace istio-system \
                --wait

            kubectl --context {{context}} create namespace istio-ingress \
                --dry-run=client -o yaml \
                | kubectl --context {{context}} apply -f -
            kubectl --context {{context}} label namespace istio-ingress \
                sand.pit.im/addon=istio --overwrite

            kubectl --context {{context}} apply -f addons/networking/istio/gateway.yaml
            ;;
        *)
            echo "unknown mesh provider '{{provider}}' — available: istio"
            exit 1
            ;;
    esac

# Install gitops provider: just gitops argocd
[script]
gitops provider="flux": up
    addon_installed() {
        local ns="$1"
        kubectl --context {{context}} get namespace "$ns" \
            --ignore-not-found \
            -o name \
            2>/dev/null | grep -q .
    }

    gitops_conflict() {
        local conflict_ns="$1" conflict_name="$2"
        if addon_installed "$conflict_ns"; then
            echo "$conflict_name is already installed — recreate the cluster first with: just down && just up"
            return 1
        fi
    }

    case "{{provider}}" in
        flux)
            gitops_conflict argocd argocd || exit 1
            if addon_installed flux-system; then
                echo "flux is already installed, skipping"
            else
                kubectl --context {{context}} apply \
                    --server-side \
                    -f addons/gitops/flux/install.yaml
            fi
            ;;
        argocd)
            gitops_conflict flux-system flux || exit 1
            if addon_installed argocd; then
                echo "argocd is already installed, skipping"
            else
                helm repo add argo https://argoproj.github.io/argo-helm
                helm repo update argo

                VALUES="--values addons/gitops/argocd/values.yaml"
                if addon_installed istio-system; then
                    echo "istio detected, enabling HTTPRoute for argocd"
                    VALUES="$VALUES --values addons/gitops/argocd/values-mesh.yaml"
                fi

                helm --kube-context {{context}} upgrade --install argocd argo/argo-cd \
                    --namespace argocd \
                    --create-namespace \
                    $VALUES \
                    --wait
                kubectl --context {{context}} label namespace argocd \
                    sand.pit.im/addon=argocd --overwrite

                PASS=$(kubectl --context {{context}} -n argocd \
                    get secret argocd-initial-admin-secret \
                    -o jsonpath="{.data.password}" | base64 -d)
                echo ""
                echo "argocd is ready!"
                echo "  url:      http://argocd.sand.pit.im"
                echo "  user:     admin"
                echo "  password: $PASS"
            fi
            ;;
        *)
            echo "unknown gitops provider '{{provider}}' — available: flux, argocd"
            exit 1
            ;;
    esac

# Install full stack: mesh + gitops
stack: (mesh "istio") (gitops "argocd")
