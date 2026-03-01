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

Addons are installed into a running cluster with `just add <addon>`. Only one GitOps provider can be active at a time — installing a second one will print an error and exit cleanly.

```bash
just add flux    # install FluxCD
just add argocd  # install ArgoCD
```

To switch providers, recreate the cluster:

```bash
just down && just up
just add argocd
```

## Configurations

### Runtimes

- [k3d](./runtimes/k3d/) - Lightweight Kubernetes in Docker

### Addons

- [FluxCD](./addons/gitops/flux/) - GitOps continuous delivery
- [ArgoCD](./addons/gitops/argocd/) - GitOps continuous delivery (installed via Helm)

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

The config creates a cluster named `lean-k8s` with 1 server, 2 agent nodes, and ports 80/443 exposed via the load balancer. Kubeconfig is updated automatically.
