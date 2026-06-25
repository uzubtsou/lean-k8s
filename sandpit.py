#!/usr/bin/env -S uv run
# /// script
# dependencies = ["click>=8.0"]
# ///
"""
sandpit.py — Python CLI for lean-k8s cluster management.

The justfile in the repo root delegates each recipe to this script via a
one-liner call, keeping the justfile as a thin pass-through. All cluster
management logic lives here.

To add a new command:
  1. Add a @cli.command() function below.
  2. Optionally wire it in justfile: `just <name>:  @uv run sandpit.py <name>`
  No other changes are needed.
"""

import abc
import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path

import click

REPO_ROOT = Path(__file__).parent.resolve()


def _path(relative):
    """Return the absolute path for a repo-relative path string."""
    return str(REPO_ROOT / relative)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def run(cmd, check=True):
    """Run a command, streaming stdout/stderr to the terminal."""
    result = subprocess.run(cmd)
    if check and result.returncode != 0:
        sys.exit(result.returncode)


def capture(cmd):
    """Run a command and return its stdout as a stripped string."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()


def addon_installed(namespace, ctx):
    """Return True if the given namespace exists in the cluster."""
    out = capture(
        [
            "kubectl",
            "--context",
            ctx,
            "get",
            "namespace",
            namespace,
            "--ignore-not-found",
            "-o",
            "name",
        ]
    )
    return bool(out)


def addons_of_type(addon_type, ctx):
    """Return addon names from namespaces carrying the given addon type label."""
    out = capture(
        [
            "kubectl",
            "--context",
            ctx,
            "get",
            "namespaces",
            f"--selector=sand.pit.im/addon-type={addon_type}",
            "--no-headers",
            r"-o=custom-columns=:.metadata.labels.sand\.pit\.im/addon",
        ]
    )
    return [name.strip() for name in out.splitlines() if name.strip()]


def addon_type_installed(addon_type, ctx):
    """Return the first installed addon of a type, if any."""
    names = addons_of_type(addon_type, ctx)
    return names[0] if names else None


def label_addon_namespace(namespace, addon, addon_type, ctx):
    """Apply sand.pit.im/addon and sand.pit.im/addon-type labels to a namespace.

    These labels cannot live in addon YAML manifests for Helm-based addons because
    Helm's --create-namespace flag creates the namespace without applying chart labels.
    Keeping the labelling here, in one place, makes the limitation explicit and ensures
    all addon types are handled consistently.
    """
    run(
        [
            "kubectl",
            "--context",
            ctx,
            "label",
            "namespace",
            namespace,
            f"sand.pit.im/addon={addon}",
            f"sand.pit.im/addon-type={addon_type}",
            "--overwrite",
        ]
    )


def die(msg):
    """Print an error message to stderr and exit 1."""
    click.echo(f"error: {msg}", err=True)
    sys.exit(1)


def _check_runtime_binary(runtime_name):
    """Verify the runtime binary is on PATH; die with an install hint if not."""
    if shutil.which(runtime_name) is None:
        die(
            f"runtime '{runtime_name}' not found on PATH"
            f" — install it first (e.g. brew install {runtime_name})"
        )


def _detect_runtime() -> str | None:
    """Return the name of the runtime that currently has the sandpit cluster running."""
    for name, cls in RUNTIMES.items():
        if shutil.which(name) is None:
            continue
        try:
            if cls().exists():
                return name
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Runtime abstraction
# ---------------------------------------------------------------------------


class Runtime(abc.ABC):
    """Abstract base class for a local Kubernetes cluster runtime."""

    name: str

    @abc.abstractmethod
    def create(self, context: str):
        """Create the cluster and configure kubeconfig."""

    @abc.abstractmethod
    def delete(self, context: str):
        """Delete the cluster and clean up kubeconfig."""

    @abc.abstractmethod
    def list(self):
        """Print a summary of running clusters (used by status)."""

    @abc.abstractmethod
    def exists(self) -> bool:
        """Return True if the sandpit cluster is already running."""

    def stop(self):
        """Pause the cluster (not supported by all runtimes)."""
        die(
            f"stop is not supported for {self.name}"
            " — use 'just down' / 'just up' to recreate the cluster"
        )

    def start(self):
        """Resume a paused cluster (not supported by all runtimes)."""
        die(
            f"start is not supported for {self.name}"
            " — use 'just down' / 'just up' to recreate the cluster"
        )


RUNTIMES: dict[str, type[Runtime]] = {}


# ---------------------------------------------------------------------------
# K3dRuntime
# ---------------------------------------------------------------------------


class K3dRuntime(Runtime):
    """Runtime implementation backed by k3d (k3s in Docker)."""

    name = "k3d"

    def exists(self) -> bool:
        return (
            subprocess.run(
                ["k3d", "cluster", "get", "sandpit"], capture_output=True
            ).returncode
            == 0
        )

    def create(self, context: str):
        if self.exists():
            click.echo("cluster sandpit already exists, skipping")
            return
        run(["k3d", "cluster", "create", "--config", _path("runtimes/k3d/config.yaml")])
        run(["k3d", "kubeconfig", "merge", "sandpit", "--kubeconfig-merge-default"])
        run(["kubectl", "config", "rename-context", "k3d-sandpit", context])
        run(["kubectl", "config", "use-context", context])
        run(
            [
                "kubectl",
                "apply",
                "--context",
                context,
                "-f",
                _path("runtimes/k3d/tenants.yaml"),
            ]
        )

    def delete(self, context: str):
        subprocess.run(
            ["kubectl", "config", "unset", "current-context"], capture_output=True
        )
        subprocess.run(
            ["kubectl", "config", "delete-context", context], capture_output=True
        )
        run(["k3d", "cluster", "delete", "sandpit"])

    def stop(self):
        run(["k3d", "cluster", "stop", "sandpit"])

    def start(self):
        run(["k3d", "cluster", "start", "sandpit"])

    def list(self):
        run(["k3d", "cluster", "list"], check=False)


# ---------------------------------------------------------------------------
# KindRuntime
# ---------------------------------------------------------------------------


class KindRuntime(Runtime):
    """Runtime implementation backed by kind (Kubernetes IN Docker)."""

    name = "kind"

    def exists(self) -> bool:
        output = capture(["kind", "get", "clusters"])
        return "sandpit" in output.splitlines()

    def create(self, context: str):
        if self.exists():
            click.echo("cluster sandpit already exists, skipping")
            return
        run(
            [
                "kind",
                "create",
                "cluster",
                "--name",
                "sandpit",
                "--config",
                _path("runtimes/kind/config.yaml"),
            ]
        )
        run(["kind", "export", "kubeconfig", "--name", "sandpit"])
        run(["kubectl", "config", "rename-context", "kind-sandpit", context])
        run(["kubectl", "config", "use-context", context])
        run(
            [
                "kubectl",
                "apply",
                "--context",
                context,
                "-f",
                _path("runtimes/kind/tenants.yaml"),
            ]
        )

    def delete(self, context: str):
        subprocess.run(
            ["kubectl", "config", "unset", "current-context"], capture_output=True
        )
        subprocess.run(
            ["kubectl", "config", "delete-context", context], capture_output=True
        )
        run(["kind", "delete", "cluster", "--name", "sandpit"])

    def list(self):
        run(["kind", "get", "clusters"], check=False)


RUNTIMES = {"k3d": K3dRuntime, "kind": KindRuntime}


# ---------------------------------------------------------------------------
# Shared implementation functions
# Called by Click commands and by each other (e.g. mesh calls _do_up).
# ---------------------------------------------------------------------------


def _do_up(context, runtime):
    for name, cls in RUNTIMES.items():
        if name == runtime.name or shutil.which(name) is None:
            continue
        try:
            if cls().exists():
                die(
                    f"a sandpit cluster is already running under '{name}'"
                    f" — run 'just down' to delete it before switching runtimes"
                )
        except Exception:
            continue
    runtime.create(context)


# ---------------------------------------------------------------------------
# Provider install functions
# Called by _do_* wrappers and sync command.
# Each function encapsulates only the install/upgrade steps — no precondition
# checks, no cluster-up guard, no mutual-exclusivity checks.
# ---------------------------------------------------------------------------


def _install_istio(context, runtime):
    """Install or upgrade Istio service mesh."""
    run(
        [
            "helm",
            "repo",
            "add",
            "istio",
            "https://istio-release.storage.googleapis.com/charts",
        ]
    )
    run(["helm", "repo", "update", "istio"])
    run(
        [
            "helm",
            "upgrade",
            "--kube-context",
            context,
            "--install",
            "istio-base",
            "istio/base",
            "--namespace",
            "istio-system",
            "--create-namespace",
            "--force-conflicts",
            "--wait",
        ]
    )
    run(
        [
            "helm",
            "upgrade",
            "--kube-context",
            context,
            "--install",
            "istiod",
            "istio/istiod",
            "--namespace",
            "istio-system",
            "--force-conflicts",
            "--wait",
        ]
    )
    # Create istio-ingress namespace (idempotent via dry-run + apply)
    ns_yaml = capture(
        [
            "kubectl",
            "create",
            "namespace",
            "istio-ingress",
            "--context",
            context,
            "--dry-run=client",
            "-o",
            "yaml",
        ]
    )
    proc = subprocess.run(
        ["kubectl", "--context", context, "apply", "-f", "-"],
        input=ns_yaml,
        text=True,
    )
    if proc.returncode != 0:
        sys.exit(proc.returncode)
    label_addon_namespace("istio-ingress", "istio", "mesh", context)
    run(
        [
            "kubectl",
            "apply",
            "-f",
            _path("addons/networking/istio/gateway.yaml"),
            "--context",
            context,
        ]
    )


def _install_dex(context, runtime):
    """Install or upgrade Dex OIDC provider."""
    run(["helm", "repo", "add", "dex", "https://charts.dexidp.io"])
    run(["helm", "repo", "update", "dex"])
    run(
        [
            "helm",
            "--kube-context",
            context,
            "upgrade",
            "--install",
            "dex",
            "dex/dex",
            "--namespace",
            "dex",
            "--create-namespace",
            "--values",
            _path("addons/auth/dex/values.yaml"),
            "--wait",
        ]
    )
    label_addon_namespace("dex", "dex", "auth", context)
    if addon_installed("istio-system", context):
        run(
            [
                "kubectl",
                "--context",
                context,
                "apply",
                "-f",
                _path("addons/auth/dex/httproute.yaml"),
            ]
        )
        if addon_installed("flux-system", context):
            dex_ip = capture(
                [
                    "kubectl",
                    "--context",
                    context,
                    "get",
                    "svc",
                    "dex",
                    "-n",
                    "dex",
                    "-o",
                    "jsonpath={.spec.clusterIP}",
                ]
            )
            with open(_path("addons/auth/dex/serviceentry.yaml")) as f:
                serviceentry = f.read().replace("DEX_CLUSTER_IP", dex_ip)
            proc = subprocess.run(
                ["kubectl", "--context", context, "apply", "-f", "-"],
                input=serviceentry,
                text=True,
            )
            if proc.returncode != 0:
                sys.exit(proc.returncode)


def _install_argocd(context, runtime):
    """Install or upgrade ArgoCD."""
    run(["helm", "repo", "add", "argo", "https://argoproj.github.io/argo-helm"])
    run(["helm", "repo", "update", "argo"])
    values_args = ["--values", _path("addons/gitops/argocd/values.yaml")]
    if addon_type_installed("mesh", context):
        click.echo("mesh detected, enabling HTTPRoute for argocd")
        values_args += [
            "--values",
            _path("addons/gitops/argocd/values-mesh.yaml"),
        ]
    run(
        [
            "helm",
            "--kube-context",
            context,
            "upgrade",
            "--install",
            "argocd",
            "argo/argo-cd",
            "--namespace",
            "argocd",
            "--create-namespace",
        ]
        + values_args
        + ["--wait"]
    )
    label_addon_namespace("argocd", "argocd", "gitops", context)


def _install_flux(context):
    """Install or upgrade Flux."""
    run(
        [
            "kubectl",
            "--context",
            context,
            "apply",
            "--server-side",
            "-f",
            "https://github.com/fluxcd/flux2/releases/latest/download/install.yaml",
        ]
    )
    label_addon_namespace("flux-system", "flux", "gitops", context)


def _install_flux_operator(context, runtime):
    """Install or upgrade Flux Operator."""
    run(
        [
            "helm",
            "upgrade",
            "--install",
            "flux-operator",
            "oci://ghcr.io/controlplaneio-fluxcd/charts/flux-operator",
            "--kube-context",
            context,
            "--namespace",
            "flux-system",
            "--create-namespace",
            "--values",
            _path("addons/gitops/flux-operator/values.yaml"),
            "--wait",
        ]
    )
    label_addon_namespace("flux-system", "flux-operator", "gitops", context)
    run(
        [
            "kubectl",
            "--context",
            context,
            "apply",
            "--server-side",
            "-f",
            _path("addons/gitops/flux-operator/instance.yaml"),
        ]
    )
    run(
        [
            "kubectl",
            "--context",
            context,
            "apply",
            "-f",
            _path("addons/gitops/flux-operator/rbac.yaml"),
            "-f",
            _path("addons/tenants/flux-operator.yaml"),
        ]
    )
    if addon_installed("istio-system", context):
        click.echo("istio detected, enabling HTTPRoute for flux-operator")
        run(
            [
                "kubectl",
                "--context",
                context,
                "apply",
                "-f",
                _path("addons/gitops/flux-operator/httproute.yaml"),
            ]
        )


def _install_flagger(context, runtime):
    """Install or upgrade Flagger."""
    run(["helm", "repo", "add", "flagger", "https://flagger.app"])
    run(["helm", "repo", "update", "flagger"])
    values_args = ["--values", _path("addons/progressive/flagger/values.yaml")]
    if addon_type_installed("observability", context):
        click.echo("observability detected, configuring Flagger with Prometheus")
        values_args += [
            "--values",
            _path("addons/progressive/flagger/values-observability.yaml"),
        ]
    run(
        [
            "helm",
            "upgrade",
            "--install",
            "flagger",
            "flagger/flagger",
            "--kube-context",
            context,
            "--namespace",
            "flagger-system",
            "--create-namespace",
        ]
        + values_args
        + ["--wait"]
    )
    label_addon_namespace("flagger-system", "flagger", "progressive", context)


def _install_prometheus(context, runtime):
    """Install or upgrade Prometheus."""
    run(
        [
            "helm",
            "repo",
            "add",
            "prometheus-community",
            "https://prometheus-community.github.io/helm-charts",
        ]
    )
    run(["helm", "repo", "update", "prometheus-community"])
    run(
        [
            "helm",
            "upgrade",
            "--install",
            "prometheus",
            "prometheus-community/prometheus",
            "--kube-context",
            context,
            "--namespace",
            "monitoring",
            "--create-namespace",
            "--values",
            _path("addons/observability/prometheus/values.yaml"),
            "--wait",
        ]
    )
    label_addon_namespace("monitoring", "prometheus", "observability", context)


def _do_mesh(context, runtime):
    _do_up(context, runtime)

    existing = addon_type_installed("mesh", context)
    if existing and existing != "istio":
        die(f"mesh addon '{existing}' is already installed")

    if addon_installed("istio-system", context):
        click.echo("istio is already installed, skipping")
        return

    # Install Gateway API CRDs if not present
    crd_check = subprocess.run(
        [
            "kubectl",
            "get",
            "crd",
            "gateways.gateway.networking.k8s.io",
            "--context",
            context,
        ],
        capture_output=True,
    )
    if crd_check.returncode != 0:
        run(
            [
                "kubectl",
                "apply",
                "-f",
                "https://github.com/kubernetes-sigs/gateway-api"
                "/releases/latest/download/standard-install.yaml",
                "--context",
                context,
            ]
        )

    _install_istio(context, runtime)


def _do_auth(context, runtime):
    _do_up(context, runtime)

    existing = addon_type_installed("auth", context)
    if existing == "dex":
        click.echo("dex is already installed, skipping")
        return
    if existing:
        die(f"auth addon '{existing}' is already installed")

    if not addon_type_installed("mesh", context):
        die("no mesh addon installed — run 'just mesh' first")

    _install_dex(context, runtime)


def _do_gitops(context, provider, runtime):
    _do_up(context, runtime)

    existing = addons_of_type("gitops", context)
    if provider in existing:
        click.echo(f"{provider} is already installed, skipping")
        return
    if existing:
        if "flux" in existing and provider == "flux-operator":
            click.confirm(
                "flux is already installed. Migrate to flux-operator?", abort=True
            )
        elif "flux-operator" in existing and provider == "flux":
            die("flux-operator is already installed")
        else:
            click.confirm(
                f"{', '.join(existing)} already installed. Install {provider} too?",
                abort=True,
            )

    if provider == "flux":
        _install_flux(context)

    elif provider == "argocd":
        _install_argocd(context, runtime)

        password_b64 = capture(
            [
                "kubectl",
                "--context",
                context,
                "-n",
                "argocd",
                "get",
                "secret",
                "argocd-initial-admin-secret",
                "-o",
                "jsonpath={.data.password}",
            ]
        )
        password = base64.b64decode(password_b64).decode()
        click.echo("")
        click.echo("argocd is ready!")
        click.echo("  url:      http://argocd.sand.pit.im")
        click.echo("  user:     admin")
        click.echo(f"  password: {password}")

    elif provider == "flux-operator":
        _install_flux_operator(context, runtime)
    else:
        die(
            f"unknown gitops provider '{provider}'"
            " — available: flux, argocd, flux-operator"
        )


def _do_progressive(context, runtime):
    _do_up(context, runtime)

    if not addon_type_installed("mesh", context):
        die("no mesh addon installed — run 'just mesh' first")

    existing = addon_type_installed("progressive", context)
    if existing:
        click.echo(f"{existing} is already installed, skipping")
        return

    if not addon_type_installed("observability", context):
        click.echo(
            "warning: no observability addon installed — canary analysis will not be available"
        )
        click.echo("         run 'just observability' to enable it")

    _install_flagger(context, runtime)


def _do_observability(context, runtime):
    _do_up(context, runtime)

    existing = addon_type_installed("observability", context)
    if existing == "prometheus":
        click.echo("prometheus is already installed, skipping")
        return
    if existing:
        die(f"observability addon '{existing}' is already installed")

    _install_prometheus(context, runtime)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.option(
    "--context",
    default=lambda: os.environ.get("SANDPIT_CONTEXT", "sandpit"),
    show_default="sandpit",
    help="kubectl context to use for all operations.",
)
@click.option(
    "--runtime",
    default="",
    show_default="auto-detect",
    help="Cluster runtime. Omit to auto-detect from running cluster (falls back to k3d).",
)
@click.pass_context
def cli(ctx, context, runtime):
    ctx.ensure_object(dict)
    ctx.obj["context"] = context
    if not runtime:
        runtime = os.environ.get("SANDPIT_RUNTIME") or _detect_runtime() or "k3d"
    if runtime not in RUNTIMES:
        die(f"unknown runtime '{runtime}' — available: {', '.join(RUNTIMES)}")
    _check_runtime_binary(runtime)
    ctx.obj["runtime"] = RUNTIMES[runtime]()


# ---------------------------------------------------------------------------
# Cluster lifecycle
# ---------------------------------------------------------------------------


@cli.command()
@click.pass_context
def status(ctx):
    """Show cluster state and installed addons."""
    context = ctx.obj["context"]

    ctx.obj["runtime"].list()
    click.echo("")

    result = subprocess.run(
        ["kubectl", "get", "nodes", "--context", context, "--no-headers"],
        capture_output=True,
        text=True,
    )
    if not result.stdout.strip():
        click.echo("no cluster running")
        return

    addons_raw = capture(
        [
            "kubectl",
            "get",
            "namespaces",
            "--context",
            context,
            "--selector=sand.pit.im/addon",
            "--no-headers",
            r"-o=custom-columns=ADDON:.metadata.labels.sand\.pit\.im/addon,TYPE:.metadata.labels.sand\.pit\.im/addon-type",
        ]
    )
    rows = sorted(set(line for line in addons_raw.splitlines() if line.strip()))
    if rows:
        click.echo(f"{'ADDON':<18}{'TYPE'}")
        for row in rows:
            parts = row.split()
            name = parts[0] if parts else ""
            addon_type = parts[1] if len(parts) > 1 else ""
            click.echo(f"  {name:<16}{addon_type}")
    else:
        click.echo("no addons installed")


@cli.command()
@click.pass_context
def up(ctx):
    """Create the sandpit cluster and set up kubeconfig (idempotent)."""
    _do_up(ctx.obj["context"], ctx.obj["runtime"])


@cli.command()
@click.pass_context
def down(ctx):
    """Delete the sandpit cluster."""
    ctx.obj["runtime"].delete(ctx.obj["context"])


@cli.command()
@click.pass_context
def stop(ctx):
    """Stop the sandpit cluster."""
    ctx.obj["runtime"].stop()


@cli.command()
@click.pass_context
def start(ctx):
    """Start a stopped sandpit cluster."""
    ctx.obj["runtime"].start()


# ---------------------------------------------------------------------------
# Addons
# ---------------------------------------------------------------------------


@cli.command()
@click.pass_context
def mesh(ctx):
    """Install Istio service mesh. Implies up."""
    _do_mesh(ctx.obj["context"], ctx.obj["runtime"])


@cli.command()
@click.pass_context
def auth(ctx):
    """Install Dex auth provider. Requires mesh."""
    _do_auth(ctx.obj["context"], ctx.obj["runtime"])


@cli.command()
@click.argument("provider", default="flux")
@click.pass_context
def gitops(ctx, provider):
    """Install a GitOps provider (default: flux)."""
    _do_gitops(ctx.obj["context"], provider, ctx.obj["runtime"])


@cli.command()
@click.pass_context
def progressive(ctx):
    """Install Flagger progressive delivery. Requires mesh."""
    _do_progressive(ctx.obj["context"], ctx.obj["runtime"])


@cli.command()
@click.pass_context
def observability(ctx):
    """Install Prometheus observability. Implies up."""
    _do_observability(ctx.obj["context"], ctx.obj["runtime"])


@cli.command()
@click.pass_context
def sync(ctx):
    """Upgrade all installed addons to their latest versions."""
    context = ctx.obj["context"]
    runtime = ctx.obj["runtime"]
    synced = False

    if addon_installed("istio-system", context):
        click.echo("syncing istio...")
        _install_istio(context, runtime)
        click.echo("istio synced")
        synced = True

    if addon_installed("dex", context):
        click.echo("syncing dex...")
        _install_dex(context, runtime)
        click.echo("dex synced")
        synced = True

    if addon_installed("argocd", context):
        click.echo("syncing argocd...")
        _install_argocd(context, runtime)
        click.echo("argocd synced")
        synced = True
    if addon_installed("flux-system", context):
        helm_check = subprocess.run(
            [
                "helm",
                "--kube-context",
                context,
                "status",
                "flux-operator",
                "--namespace",
                "flux-system",
            ],
            capture_output=True,
        )
        if helm_check.returncode == 0:
            click.echo("syncing flux-operator...")
            _install_flux_operator(context, runtime)
            click.echo("flux-operator synced")
        else:
            click.echo("syncing flux...")
            _install_flux(context)
            click.echo("flux synced")
        synced = True

    if addon_installed("monitoring", context):
        click.echo("syncing prometheus...")
        _install_prometheus(context, runtime)
        click.echo("prometheus synced")
        synced = True

    if addon_installed("flagger-system", context):
        click.echo("syncing flagger...")
        _install_flagger(context, runtime)
        click.echo("flagger synced")
        synced = True

    if not synced:
        click.echo("nothing to sync")


@cli.command()
@click.pass_context
def stack(ctx):
    """Install full stack: mesh (istio) + gitops (flux). Implies up."""
    context = ctx.obj["context"]
    _do_mesh(context, ctx.obj["runtime"])
    _do_gitops(context, "flux", ctx.obj["runtime"])


# ---------------------------------------------------------------------------
# Version — demonstrates zero-justfile-change extensibility (US2)
# ---------------------------------------------------------------------------


@cli.command()
def version():
    """Print the sandpit CLI version."""
    click.echo("sandpit 0.1.0")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
