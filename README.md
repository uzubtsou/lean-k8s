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

Addons are grouped by category. Each category has a default provider.

```bash
just mesh              # install Istio (default mesh provider)
just gitops argocd     # install ArgoCD
just stack             # install everything: mesh + gitops
```

Only one GitOps provider can be active at a time — installing a second one will print an error. To switch providers, recreate the cluster:

```bash
just down && just up
just gitops flux
```

When Istio is installed, `just gitops argocd` automatically detects it and configures an HTTPRoute so ArgoCD is reachable at `http://argocd.sand.pit.im`.

## Configurations

### Runtimes

- [k3d](./runtimes/k3d/) - Lightweight Kubernetes in Docker

### Addons

**Networking / Mesh**

- [Istio](./addons/networking/istio/) - Service mesh with Gateway API (`just mesh istio`)

**GitOps**

- [FluxCD](./addons/gitops/flux/) - GitOps continuous delivery (`just gitops flux`)
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
