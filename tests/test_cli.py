import pytest
import subprocess
import sys
from click.testing import CliRunner

from transformez.cli import transformez_cli

# CMD will run Transformez
CMD = [sys.executable, "-m", "transformez.cli.__init__"]


@pytest.fixture
def runner():
    """Fixture to provide a Click CliRunner for all tests."""

    return CliRunner()


def test_cli_base_help(runner):
    """Ensure the base command runs and all subcommands are registered."""

    result = runner.invoke(transformez_cli, ["--help"])

    assert result.exit_code == 0
    assert (
        "Build vertical datum shift grids and transform elevation data."
        in result.output
    )

    expected_commands = [
        "build",
        "shift",
        "list",
        "prefetch",
        "plan",
        "htdp",
        "vdatum",
    ]
    for cmd in expected_commands:
        assert cmd in result.output, f"Missing '{cmd}' command in CLI help!"


def run_transformez(args):
    """Run transformez and return result."""

    result = subprocess.run(CMD + args, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"CLI CRASHED!\nSTDERR:\n{result.stderr}")
    result.check_returncode()
    return result


def test_help():
    """Does the help menu work?"""

    result = run_transformez(["--help"])
    assert result.returncode == 0


def test_version():
    """Does version print?"""

    result = run_transformez(["--version"])
    assert result.returncode == 0


def test_list_modules():
    """Can we list references without crashing?"""

    result = run_transformez(["list", "references"])
    assert result.returncode == 0
    assert "global:lat" in result.stdout
    assert "vdatum:mllw" in result.stdout


if __name__ == "__main__":
    transformez_cli()
