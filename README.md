# lean-k8s

Local Kubernetes configurations for development. This repo collects minimal, working setups for running Kubernetes locally using different tools.

## Prerequisites

- [just](https://github.com/casey/just) — `brew install just`

## Usage

```bash
just          # list all available recipes
just k3d-up   # create a k3d cluster
just k3d-down # delete the k3d cluster
```

## Configurations

### Runtimes

- [k3d](./runtimes/k3d/) - Lightweight Kubernetes in Docker

### Addons

_Coming soon._

---

## k3d

### Install on macOS

```bash
brew install k3d
```

k3d requires a Docker-compatible runtime. Common options on macOS include Docker Desktop, OrbStack, Colima, or Rancher Desktop.

### Cluster management

```bash
just k3d-up    # create cluster
just k3d-down  # delete cluster
just k3d-stop  # stop cluster
just k3d-start # start stopped cluster
```

The config creates a cluster named `lean-k8s` with 1 server, 2 agent nodes, and ports 80/443 exposed via the load balancer. Kubeconfig is updated automatically.
