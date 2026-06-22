#!/usr/bin/env -S uv run
# /// script
# dependencies = ["click>=8.0"]
# ///

from unittest.mock import patch

from click.testing import CliRunner

import sandpit


def test_provider_arguments():
    runner = CliRunner()
    commands = {
        "mesh": "istio",
        "auth": "dex",
        "progressive": "flagger",
        "observability": "prometheus",
    }
    with patch.object(sandpit, "_check_runtime_binary"):
        for command, provider in commands.items():
            with patch.object(sandpit, f"_do_{command}") as install:
                result = runner.invoke(sandpit.cli, [command])
            assert result.exit_code == 0
            install.assert_called_once()

            result = runner.invoke(sandpit.cli, [command, provider])
            assert result.exit_code == 2

        with patch.object(sandpit, "_do_gitops") as install:
            result = runner.invoke(sandpit.cli, ["gitops", "argocd"])
        assert result.exit_code == 0
        assert install.call_args.args[1] == "argocd"


def test_install_flux():
    with (
        patch.object(sandpit, "run") as run,
        patch.object(sandpit, "label_addon_namespace") as label,
    ):
        sandpit._install_flux("test-context")

    run.assert_called_once_with(
        [
            "kubectl",
            "--context",
            "test-context",
            "apply",
            "--server-side",
            "-f",
            "https://github.com/fluxcd/flux2/releases/latest/download/install.yaml",
        ]
    )
    label.assert_called_once_with("flux-system", "flux", "gitops", "test-context")


def test_install_second_gitops_provider_requires_confirmation():
    with (
        patch.object(sandpit, "_do_up"),
        patch.object(sandpit, "addons_of_type", return_value=["argocd"]),
        patch.object(sandpit.click, "confirm") as confirm,
        patch.object(sandpit, "_install_flux") as install,
    ):
        sandpit._do_gitops("test-context", "flux", object())

    confirm.assert_called_once_with(
        "argocd already installed. Install flux too?", abort=True
    )
    install.assert_called_once_with("test-context")


if __name__ == "__main__":
    test_provider_arguments()
    test_install_flux()
    test_install_second_gitops_provider_requires_confirmation()
