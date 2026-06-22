# lean-k8s

Local Kubernetes configurations for development. This repo collects minimal, working setups for running Kubernetes locally using different tools.

## Prerequisites

- [just](https://github.com/casey/just) — `brew install just`

## Usage

```bash
just          # list all available recipes
just up       # create the sandpit cluster
just down     # delete the sandpit cluster
just stop     # stop the sandpit cluster
just start    # start a stopped cluster
just status   # show active clusters and installed addons
```

### Installing addons

Addons are grouped by category. GitOps supports multiple providers.

```bash
just mesh                   # install Istio
just auth                   # install Dex OIDC provider
just gitops argocd          # install ArgoCD
just gitops flux-operator   # install Flux Operator with web UI + OIDC via Dex
just stack                  # install everything: mesh + gitops
just sync                   # upgrade all installed addons to latest
```

#### Running Argo CD and Flux together

Argo CD and Flux can run in the same cluster. Installing the second provider asks for confirmation, and `just sync` upgrades both when both are installed:

```bash
just gitops flux
```

Keep each provider responsible for separate resources to avoid reconciliation conflicts. `flux` and `flux-operator` are alternative Flux installation modes: they do not run together, and moving from Flux to Flux Operator uses the migration confirmation instead.

When Istio is installed, gitops recipes automatically detect it and configure HTTPRoutes. For example, ArgoCD becomes reachable at `http://argocd.sand.pit.im` and the Flux Operator web UI at `http://flux.sand.pit.im`.

When Dex is installed, `just gitops flux-operator` detects it and enables OIDC authentication in the Flux web UI. Install order: `just mesh` → `just auth` → `just gitops flux-operator`.

## Configurations

### Runtimes

- [k3d](./runtimes/k3d/) - Lightweight Kubernetes in Docker

### Addons

**Networking / Mesh**

- [Istio](./addons/networking/istio/) - Service mesh with Gateway API (`just mesh`)

**Auth**

- [Dex](./addons/auth/dex/) - OIDC identity provider with static users (`just auth`)

**GitOps**

- [FluxCD](./addons/gitops/flux/) - GitOps continuous delivery (`just gitops flux`)
- [Flux Operator](./addons/gitops/flux-operator/) - Flux Operator with web UI and OIDC (`just gitops flux-operator`)
- [ArgoCD](./addons/gitops/argocd/) - GitOps continuous delivery via Helm (`just gitops argocd`)

---

## k3d

### Install on macOS

```bash
brew install k3d
```

k3d requires a Docker-compatible runtime. Common options on macOS include Docker Desktop, OrbStack, Colima, or Rancher Desktop.

### Cluster management

```bash
just up    # create cluster
just down  # delete cluster
just stop  # stop cluster
just start # start stopped cluster
```

The config creates a cluster named `sandpit` with 1 server, 2 agent nodes, and ports 80/443 exposed via the load balancer. Kubeconfig is updated automatically. DNS is handled by a Route53 wildcard record — `*.sand.pit.im` resolves to `127.0.0.1`.
