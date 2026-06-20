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


if __name__ == "__main__":
    test_provider_arguments()
