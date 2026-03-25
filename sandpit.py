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
  2. Optionally wire it in justfile: `just <name>:  @python3 sandpit.py <name>`
  No other changes are needed.
"""

import base64
import os
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


def die(msg):
    """Print an error message to stderr and exit 1."""
    click.echo(f"error: {msg}", err=True)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Shared implementation functions
# Called by Click commands and by each other (e.g. mesh calls _do_up).
# ---------------------------------------------------------------------------


def _do_up(context):
    result = subprocess.run(["k3d", "cluster", "get", "sandpit"], capture_output=True)
    if result.returncode == 0:
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


def _do_mesh(context, provider):
    _do_up(context)

    if provider == "istio":
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

        run(
            [
                "kubectl",
                "label",
                "namespace",
                "istio-ingress",
                "sand.pit.im/addon=istio",
                "--context",
                context,
                "--overwrite",
            ]
        )
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
    else:
        die(f"unknown mesh provider '{provider}' — available: istio")


def _do_auth(context, provider):
    _do_up(context)

    if provider == "dex":
        if not addon_installed("istio-system", context):
            die("no mesh installed — run 'just mesh' first")
        if addon_installed("dex", context):
            click.echo("dex is already installed, skipping")
            return

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
        run(
            [
                "kubectl",
                "--context",
                context,
                "label",
                "namespace",
                "dex",
                "sand.pit.im/addon=dex",
                "--overwrite",
            ]
        )
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
    else:
        die(f"unknown auth provider '{provider}' — available: dex")


def _do_gitops(context, provider):
    _do_up(context)

    if provider == "flux":
        if addon_installed("argocd", context):
            click.echo("argocd is already installed")
            sys.exit(0)
        if addon_installed("flux-system", context):
            click.echo("flux is already installed, skipping")
            return
        run(
            [
                "kubectl",
                "--context",
                context,
                "apply",
                "--server-side",
                "-f",
                _path("addons/gitops/flux/install.yaml"),
            ]
        )

    elif provider == "argocd":
        if addon_installed("flux-system", context):
            click.echo("flux is already installed")
            sys.exit(0)
        if addon_installed("argocd", context):
            click.echo("argocd is already installed, skipping")
            return

        run(["helm", "repo", "add", "argo", "https://argoproj.github.io/argo-helm"])
        run(["helm", "repo", "update", "argo"])

        values_args = ["--values", _path("addons/gitops/argocd/values.yaml")]
        if addon_installed("istio-system", context):
            click.echo("istio detected, enabling HTTPRoute for argocd")
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
        run(
            [
                "kubectl",
                "--context",
                context,
                "label",
                "namespace",
                "argocd",
                "sand.pit.im/addon=argocd",
                "--overwrite",
            ]
        )

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
        if addon_installed("argocd", context):
            click.echo("argocd is already installed")
            sys.exit(0)

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
        if helm_check.returncode != 0:
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
            run(
                [
                    "kubectl",
                    "--context",
                    context,
                    "label",
                    "namespace",
                    "flux-system",
                    "sand.pit.im/addon=flux-operator",
                    "--overwrite",
                ]
            )
        else:
            click.echo("flux-operator is already installed, skipping helm install")

        fi_check = subprocess.run(
            [
                "kubectl",
                "--context",
                context,
                "get",
                "fluxinstance",
                "flux",
                "--namespace",
                "flux-system",
            ],
            capture_output=True,
        )
        if fi_check.returncode != 0:
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
        else:
            click.echo("fluxinstance flux is already installed, skipping")

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
    else:
        die(
            f"unknown gitops provider '{provider}'"
            " — available: flux, argocd, flux-operator"
        )


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
@click.pass_context
def cli(ctx, context):
    ctx.ensure_object(dict)
    ctx.obj["context"] = context


# ---------------------------------------------------------------------------
# Cluster lifecycle
# ---------------------------------------------------------------------------


@cli.command()
@click.pass_context
def status(ctx):
    """Show cluster state and installed addons."""
    context = ctx.obj["context"]

    run(["k3d", "cluster", "list"], check=False)
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
            r"-o=custom-columns=:.metadata.labels.sand\.pit\.im/addon",
        ]
    )
    addons = sorted(set(a for a in addons_raw.splitlines() if a.strip()))
    if addons:
        click.echo(f"{'ADDONS':<16}")
        for name in addons:
            click.echo(f"  {name}")
    else:
        click.echo("no addons installed")


@cli.command()
@click.pass_context
def up(ctx):
    """Create the sandpit cluster and set up kubeconfig (idempotent)."""
    _do_up(ctx.obj["context"])


@cli.command()
@click.pass_context
def down(ctx):
    """Delete the sandpit cluster."""
    context = ctx.obj["context"]
    subprocess.run(
        ["kubectl", "config", "unset", "current-context"],
        capture_output=True,
    )
    subprocess.run(
        ["kubectl", "config", "delete-context", context],
        capture_output=True,
    )
    run(["k3d", "cluster", "delete", "sandpit"])


@cli.command()
def stop():
    """Stop the sandpit cluster."""
    run(["k3d", "cluster", "stop", "sandpit"])


@cli.command()
def start():
    """Start a stopped sandpit cluster."""
    run(["k3d", "cluster", "start", "sandpit"])


# ---------------------------------------------------------------------------
# Addons
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("provider", default="istio")
@click.pass_context
def mesh(ctx, provider):
    """Install service mesh (default: istio). Implies up."""
    _do_mesh(ctx.obj["context"], provider)


@cli.command()
@click.argument("provider", default="dex")
@click.pass_context
def auth(ctx, provider):
    """Install auth provider (default: dex). Requires mesh."""
    _do_auth(ctx.obj["context"], provider)


@cli.command()
@click.argument("provider", default="flux")
@click.pass_context
def gitops(ctx, provider):
    """Install GitOps provider (default: flux). Mutually exclusive."""
    _do_gitops(ctx.obj["context"], provider)


@cli.command()
@click.pass_context
def sync(ctx):
    """Upgrade all installed addons to their latest versions."""
    context = ctx.obj["context"]

    if addon_installed("istio-system", context):
        click.echo("syncing istio...")
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
        click.echo("istio synced")

    if addon_installed("dex", context):
        click.echo("syncing dex...")
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
                "--values",
                _path("addons/auth/dex/values.yaml"),
                "--wait",
            ]
        )
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
        click.echo("dex synced")

    if addon_installed("argocd", context):
        click.echo("syncing argocd...")
        run(["helm", "repo", "update", "argo"])
        values_args = ["--values", _path("addons/gitops/argocd/values.yaml")]
        if addon_installed("istio-system", context):
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
            ]
            + values_args
            + ["--wait"]
        )
        click.echo("argocd synced")

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
                    "--values",
                    _path("addons/gitops/flux-operator/values.yaml"),
                    "--wait",
                ]
            )
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
            click.echo("flux-operator synced")
        else:
            click.echo("syncing flux...")
            run(
                [
                    "kubectl",
                    "--context",
                    context,
                    "apply",
                    "--server-side",
                    "-f",
                    _path("addons/gitops/flux/install.yaml"),
                ]
            )
            click.echo("flux synced")


@cli.command()
@click.pass_context
def stack(ctx):
    """Install full stack: mesh (istio) + gitops (argocd). Implies up."""
    context = ctx.obj["context"]
    _do_mesh(context, "istio")
    _do_gitops(context, "argocd")


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
