"""
Test for running the server module as a script.
This covers the if __name__ == "__main__" block.
"""

import runpy
import subprocess
import sys
from unittest.mock import patch

from vasp_lsp import __version__


def test_main_script_help():
    """Test that the server can be run as a script with --help."""
    # Run the module as a script with --help
    result = subprocess.run(
        [sys.executable, "-m", "vasp_lsp.server", "--help"],
        capture_output=True,
        text=True,
        timeout=5,
    )

    # Should exit cleanly
    assert result.returncode == 0
    assert "VASP Language Server" in result.stdout


def test_main_script_version():
    """Test that the server can be run as a script with --version."""
    # Run the module as a script with --version
    result = subprocess.run(
        [sys.executable, "-m", "vasp_lsp.server", "--version"],
        capture_output=True,
        text=True,
        timeout=5,
    )

    # Should exit cleanly
    assert result.returncode == 0
    assert __version__ in result.stdout
    assert "Registered builtin" not in result.stderr


def test_run_as_main():
    """Test running the module as __main__ using runpy."""
    import sys

    # Mock sys.argv to prevent actual server start
    with patch.object(sys, "argv", ["vasp-lsp", "--help"]):
        try:
            runpy.run_module("vasp_lsp.server", run_name="__main__")
        except SystemExit:
            # Expected when --help is provided
            pass
