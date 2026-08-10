"""Smoke tests for the bundled native Neovim LSP configuration."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
NVIM_CONFIG_ROOT = REPO_ROOT / "editors" / "neovim"


@pytest.mark.integration
def test_bundled_neovim_config_attaches_to_incar(tmp_path: Path) -> None:
    """A fresh Neovim 0.11 config should attach without nvim-lspconfig setup."""
    nvim = shutil.which("nvim")
    vasp_lsp = shutil.which("vasp-lsp")
    if nvim is None or vasp_lsp is None:
        pytest.skip("requires nvim and vasp-lsp on PATH")

    incar = tmp_path / "INCAR"
    incar.write_text("LREAL = .FALSE.\n", encoding="utf-8")
    command = [
        nvim,
        "--headless",
        "-u",
        "NONE",
        "--cmd",
        f"set rtp^={NVIM_CONFIG_ROOT}",
        "-c",
        "filetype on",
        "-c",
        'lua vim.lsp.enable("vasp_lsp")',
        "-c",
        f"edit {incar}",
        "-c",
        (
            "lua vim.wait(4000, function() "
            'return #vim.lsp.get_clients({name="vasp_lsp"}) > 0 end, 100)'
        ),
        "-c",
        (
            'lua local clients=vim.lsp.get_clients({name="vasp_lsp"}); '
            'if #clients ~= 1 or clients[1].server_capabilities.textDocumentSync.change ~= 1 then '
            'vim.api.nvim_err_writeln("VASP_LSP_NOT_ATTACHED") '
            'vim.cmd("cquit 1") end'
        ),
        "-c",
        (
            "lua vim.api.nvim_buf_set_text(0, 0, 8, 0, 15, {\"maybe\"})"
        ),
        "-c",
        "lua vim.wait(3000)",
        "-c",
        (
            'lua local found=false; for _,diagnostic in ipairs(vim.diagnostic.get(0)) do '
            'if diagnostic.message:find("Invalid value for LREAL", 1, true) then '
            'found=true end end; if not found then '
            'vim.api.nvim_err_writeln("VASP_LSP_INCREMENTAL_SYNC_BROKEN"); '
            'vim.cmd("cquit 1") end'
        ),
        "-c",
        "qa!",
    ]
    environment = os.environ.copy()
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "VASP_LSP_NOT_ATTACHED" not in output
