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
    assert nvim is not None and vasp_lsp is not None

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


@pytest.mark.integration
def test_bundled_neovim_config_advertises_completion_triggers(tmp_path: Path) -> None:
    """The real stdio initialize response must advertise completion triggers."""
    nvim = shutil.which("nvim")
    vasp_lsp = shutil.which("vasp-lsp")
    if nvim is None or vasp_lsp is None:
        pytest.skip("requires nvim and vasp-lsp on PATH")
    assert nvim is not None and vasp_lsp is not None

    incar = tmp_path / "INCAR"
    incar.write_text("ISMEAR = \n", encoding="utf-8")
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
            'local provider=clients[1] and clients[1].server_capabilities.completionProvider; '
            'local triggers=provider and provider.triggerCharacters or {}; '
            'if not vim.tbl_contains(triggers, "=") then '
            'vim.api.nvim_err_writeln("VASP_LSP_COMPLETION_TRIGGERS_MISSING"); '
            'vim.cmd("cquit 1") end'
        ),
        "-c",
        (
            'lua local client=vim.lsp.get_clients({name="vasp_lsp"})[1]; '
            'local done=false; local request_error=nil; local response=nil; '
            'client:request("textDocument/completion", '
            '{textDocument={uri=vim.uri_from_bufnr(0)}, position={line=0, character=9}, '
            'context={triggerKind=1}}, '
            'function(error, result) request_error=error; response=result; done=true end); '
            'vim.wait(4000, function() return done end, 100); '
            'local found=false; local items=response and (response.items or response) or {}; '
            'for _, item in ipairs(items) do if item.label == "0" then found=true end end; '
            'if request_error or not done or not found or response.isIncomplete ~= true then '
            'vim.api.nvim_err_writeln("VASP_LSP_ISMEAR_COMPLETION_BROKEN"); '
            'vim.cmd("cquit 1") end'
        ),
        "-c",
        "qa!",
    ]
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "VASP_LSP_COMPLETION_TRIGGERS_MISSING" not in output


@pytest.mark.integration
def test_bundled_neovim_config_discards_stale_versioned_diagnostics(
    tmp_path: Path,
) -> None:
    """An older diagnostic notification must not replace a newer one."""
    nvim = shutil.which("nvim")
    vasp_lsp = shutil.which("vasp-lsp")
    if nvim is None or vasp_lsp is None:
        pytest.skip("requires nvim and vasp-lsp on PATH")
    assert nvim is not None and vasp_lsp is not None

    incar = tmp_path / "INCAR"
    incar.write_text("BADTAG = 1\n", encoding="utf-8")
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
            'lua local client=vim.lsp.get_clients({name="vasp_lsp"})[1]; '
            'local handler=client and client.handlers["textDocument/publishDiagnostics"]; '
            'local uri=vim.uri_from_bufnr(0); '
            'if type(handler) ~= "function" then '
            'vim.api.nvim_err_writeln("VASP_LSP_DIAGNOSTIC_FILTER_MISSING"); '
            'vim.cmd("cquit 1") end; '
            'local ctx={client_id=client.id, method="textDocument/publishDiagnostics"}; '
            'handler(nil, {uri=uri, version=2, diagnostics={{'
            'range={start={line=1, character=0}, ["end"]={line=1, character=6}}, '
            'message="new diagnostic", severity=1}},}, ctx); '
            'handler(nil, {uri=uri, version=1, diagnostics={{'
            'range={start={line=0, character=0}, ["end"]={line=0, character=6}}, '
            'message="old diagnostic", severity=1}},}, ctx); '
            'local diagnostics=vim.diagnostic.get(0); '
            'if #diagnostics ~= 1 or diagnostics[1].message ~= "new diagnostic" '
            'or diagnostics[1].lnum ~= 1 then '
            'vim.api.nvim_err_writeln("VASP_LSP_STALE_DIAGNOSTIC_ACCEPTED"); '
            'vim.cmd("cquit 1") end'
        ),
        "-c",
        "qa!",
    ]
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "VASP_LSP_DIAGNOSTIC_FILTER_MISSING" not in output
    assert "VASP_LSP_STALE_DIAGNOSTIC_ACCEPTED" not in output


@pytest.mark.integration
def test_bundled_neovim_config_clears_diagnostics_after_format_edit(
    tmp_path: Path,
) -> None:
    """Formatting must not leave an old diagnostic on a deleted line."""
    nvim = shutil.which("nvim")
    vasp_lsp = shutil.which("vasp-lsp")
    if nvim is None or vasp_lsp is None:
        pytest.skip("requires nvim and vasp-lsp on PATH")
    assert nvim is not None and vasp_lsp is not None

    incar = tmp_path / "INCAR"
    incar.write_text("ENCUT = 500\n", encoding="utf-8")
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
            "lua local client=vim.lsp.get_clients({name=\"vasp_lsp\"})[1]; "
            "local namespace=vim.lsp.diagnostic.get_namespace(client.id); "
            "local test_buf=vim.api.nvim_create_buf(false, true); "
            "vim.api.nvim_buf_set_name(test_buf, \"/tmp/vasp-lsp-format-test-\"..vim.fn.getpid()); "
            "vim.api.nvim_buf_set_lines(test_buf, 0, -1, false, {\"BADTAG = 1\"}); "
            "vim.diagnostic.set(namespace, test_buf, {{"
            "lnum=0, col=0, end_lnum=0, end_col=6, severity=1, message=\"stale\"}}); "
            "local function sign_count() local placed=vim.fn.sign_getplaced("
            "vim.api.nvim_buf_get_name(test_buf), {group=\"*\"}); "
            "return #(placed[1] and placed[1].signs or {}) end; "
            "local function request(request_id, request_type) "
            "vim.api.nvim_exec_autocmds(\"LspRequest\", {buffer=test_buf, modeline=false, "
            "data={client_id=client.id, request_id=request_id, request={"
            "type=request_type, bufnr=test_buf, method=\"textDocument/formatting\"}}}) end; "
            "request(100, \"pending\"); request(100, \"complete\"); vim.wait(25); "
            "if #vim.diagnostic.get(test_buf) ~= 1 or sign_count() ~= 1 then "
            'vim.api.nvim_err_writeln("VASP_LSP_FORMAT_NOOP_CLEARED_DIAGNOSTIC"); '
            'vim.cmd("cquit 1") end; '
            "request(101, \"pending\"); "
            "vim.api.nvim_buf_set_lines(test_buf, 0, 1, false, {\"ENCUT = 500\"}); "
            "request(101, \"complete\"); vim.wait(100); "
            "if #vim.diagnostic.get(test_buf) ~= 0 or sign_count() ~= 0 then "
            'vim.api.nvim_err_writeln("VASP_LSP_FORMAT_STALE_DIAGNOSTIC_REMAINS"); '
            'vim.cmd("cquit 1") end'
        ),
        "-c",
        "qa!",
    ]
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "VASP_LSP_FORMAT_NOOP_CLEARED_DIAGNOSTIC" not in output
    assert "VASP_LSP_FORMAT_STALE_DIAGNOSTIC_REMAINS" not in output
