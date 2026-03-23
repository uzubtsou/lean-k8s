set shell := ["bash", "-euo", "pipefail", "-c"]

context := "sandpit"

alias st := status

# Show cluster status and installed addons
[default]
[script]
status:
    k3d cluster list
    echo ""
    if ! kubectl get nodes \
          --context {{ context }} \
          --no-headers 2>/dev/null | grep -q .; then
        echo "no cluster running"
        exit 0
    fi
    addons=$(kubectl get namespaces \
        --context {{ context }} \
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
        kubectl config rename-context k3d-sandpit {{ context }}
        kubectl config use-context {{ context }}
        kubectl apply --context {{ context }} -f runtimes/k3d/tenants.yaml
    fi

# Delete the sandpit cluster
down:
    @kubectl config unset current-context 2>/dev/null || true
    @kubectl config delete-context {{ context }} 2>/dev/null || true
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
        kubectl get namespace "$ns" \
            --context {{ context }} \
            --ignore-not-found \
            -o name \
            2>/dev/null | grep -q .
    }

    case "{{ provider }}" in
        istio)
            if addon_installed istio-system; then
                echo "istio is already installed, skipping"
                exit 0
            fi

            # install Gateway API CRDs if not present
            if ! kubectl get crd gateways.gateway.networking.k8s.io \
                    --context {{ context }} \
                    > /dev/null 2>&1; then
                kubectl apply -f \
                    https://github.com/kubernetes-sigs/gateway-api/releases/latest/download/standard-install.yaml \
                    --context {{ context }}
            fi

            helm repo add istio https://istio-release.storage.googleapis.com/charts
            helm repo update istio

            # install istio base
            helm upgrade \
                --kube-context {{ context }} \
                --install istio-base istio/base \
                --namespace istio-system \
                --create-namespace \
                --force-conflicts \
                --wait

            # install istiod
            helm upgrade \
                --kube-context {{ context }} \
                --install istiod istio/istiod \
                --namespace istio-system \
                --force-conflicts \
                --wait

            # create a namespace for istio-ingress
            kubectl create namespace istio-ingress \
                --context {{ context }}  \
                --dry-run=client -o yaml \
                | kubectl --context {{ context }} apply -f -

            # add label to easier maanage plugins for lean-k8s
            kubectl label namespace istio-ingress sand.pit.im/addon=istio  \
                --context {{ context }}  \
                --overwrite

            kubectl apply -f addons/networking/istio/gateway.yaml \
                --context {{ context }}
            ;;
        *)
            echo "unknown mesh provider '{{ provider }}' — available: istio"
            exit 1 ;;
    esac

# Install gitops provider: just gitops argocd|flux-operator
[script]
gitops provider="flux": up
    addon_installed() {
        local ns="$1"
        kubectl --context {{ context }} get namespace "$ns" \
            --ignore-not-found \
            -o name \
            2>/dev/null | grep -q .
    }

    case "{{ provider }}" in
        flux)
            if addon_installed argocd; then
                echo "argocd is already installed"
                exit 0
            fi
            if addon_installed flux-system; then
                echo "flux is already installed, skipping"
            else
                kubectl --context {{ context }} apply \
                    --server-side \
                    -f addons/gitops/flux/install.yaml
            fi
            ;;
        argocd)
            if addon_installed flux-system; then
                echo "flux is already installed"
                exit 0
            fi
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

                helm --kube-context {{ context }} upgrade --install argocd argo/argo-cd \
                    --namespace argocd \
                    --create-namespace \
                    $VALUES \
                    --wait
                kubectl --context {{ context }} label namespace argocd \
                    sand.pit.im/addon=argocd --overwrite

                PASS=$(kubectl --context {{ context }} -n argocd \
                    get secret argocd-initial-admin-secret \
                    -o jsonpath="{.data.password}" | base64 -d)
                echo ""
                echo "argocd is ready!"
                echo "  url:      http://argocd.sand.pit.im"
                echo "  user:     admin"
                echo "  password: $PASS"
            fi
            ;;
        flux-operator)
            if addon_installed argocd; then
                echo "argocd is already installed"
                exit 0
            fi
            if helm --kube-context {{ context }} status flux-operator \
                    --namespace flux-system > /dev/null 2>&1; then
                echo "flux-operator is already installed, skipping helm install"
            else
                helm upgrade --install flux-operator \
                    oci://ghcr.io/controlplaneio-fluxcd/charts/flux-operator \
                    --kube-context {{ context }} \
                    --namespace flux-system \
                    --create-namespace \
                    --values addons/gitops/flux-operator/values.yaml \
                    --wait
                kubectl --context {{ context }} label namespace flux-system \
                    sand.pit.im/addon=flux-operator --overwrite
            fi
            if kubectl --context {{ context }} get fluxinstance flux \
                    --namespace flux-system > /dev/null 2>&1; then
                echo "fluxinstance flux is already installed, skipping"
            else
                kubectl --context {{ context }} apply \
                    --server-side \
                    -f addons/gitops/flux-operator/instance.yaml
            fi
            kubectl --context {{ context }} apply \
                -f addons/gitops/flux-operator/rbac.yaml \
                -f addons/tenants/flux-operator.yaml
            if addon_installed istio-system; then
                echo "istio detected, enabling HTTPRoute for flux-operator"
                kubectl --context {{ context }} apply \
                    -f addons/gitops/flux-operator/httproute.yaml
            fi
            ;;
        *)
            echo "unknown gitops provider '{{ provider }}' — available: flux, argocd, flux-operator"
            exit 1
            ;;
    esac

# Sync (upgrade) all installed addons to their latest versions
[script]
sync:
    addon_installed() {
        local ns="$1"
        kubectl --context {{ context }} get namespace "$ns" \
            --ignore-not-found \
            -o name \
            2>/dev/null | grep -q .
    }

    if addon_installed istio-system; then
        echo "syncing istio..."
        helm repo update istio
        helm upgrade \
            --kube-context {{ context }} \
            --install istio-base istio/base \
            --namespace istio-system \
            --force-conflicts \
            --wait
        helm upgrade \
            --kube-context {{ context }} \
            --install istiod istio/istiod \
            --namespace istio-system \
            --force-conflicts \
            --wait
        kubectl apply -f addons/networking/istio/gateway.yaml \
            --context {{ context }}
        echo "istio synced"
    fi

    if addon_installed argocd; then
        echo "syncing argocd..."
        helm repo update argo
        VALUES="--values addons/gitops/argocd/values.yaml"
        if addon_installed istio-system; then
            VALUES="$VALUES --values addons/gitops/argocd/values-mesh.yaml"
        fi
        helm --kube-context {{ context }} upgrade --install argocd argo/argo-cd \
            --namespace argocd \
            $VALUES \
            --wait
        echo "argocd synced"
    fi

    if addon_installed flux-system; then
        if helm --kube-context {{ context }} status flux-operator \
                --namespace flux-system > /dev/null 2>&1; then
            echo "syncing flux-operator..."
            helm upgrade --install flux-operator \
                oci://ghcr.io/controlplaneio-fluxcd/charts/flux-operator \
                --kube-context {{ context }} \
                --namespace flux-system \
                --values addons/gitops/flux-operator/values.yaml \
                --wait
            kubectl --context {{ context }} apply \
                --server-side \
                -f addons/gitops/flux-operator/instance.yaml
            kubectl --context {{ context }} apply \
                -f addons/gitops/flux-operator/rbac.yaml \
                -f addons/tenants/flux-operator.yaml
            if addon_installed istio-system; then
                kubectl --context {{ context }} apply \
                    -f addons/gitops/flux-operator/httproute.yaml
            fi
            echo "flux-operator synced"
        else
            echo "syncing flux..."
            kubectl --context {{ context }} apply \
                --server-side \
                -f addons/gitops/flux/install.yaml
            echo "flux synced"
        fi
    fi

# Install full stack: mesh + gitops
stack: (mesh "istio") (gitops "argocd")
