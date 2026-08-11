"""OpenQC smoke contracts for VASP-LSP (#61, #63, #19, #22, #23, #24, #25, #27, #28, #70).

These tests exercise the agent-facing JSON and LSP capability surface that
OpenQC and the broader bohrium_skills fleet rely on. They are intentionally
protocol-level so the smoke does not depend on a running editor.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from lsprotocol.types import (
    Position,
    Range,
    RenameParams,
    TextDocumentIdentifier,
)

from vasp_lsp import server as server_module
from vasp_lsp import tool
from vasp_lsp.features.diagnostics import DiagnosticsProvider
from vasp_lsp.features.formatting import FormattingProvider
from vasp_lsp.features.navigation import DocumentSymbolsProvider
from vasp_lsp.features.quickfixes import QuickFixesProvider
from vasp_lsp.rich_diagnostics import serialize_diagnostics
from vasp_lsp.rules import RULES_MANIFEST, export_manifest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _setup_server(server, uri: str, content: str) -> None:
    server.set_document_content(uri, content)


def test_openqc_smoke_rule_manifest_exports_all_rules() -> None:
    """OpenQC reads ``rules/diagnostics.yaml`` as the canonical catalog (#61, #70)."""
    manifest = export_manifest()
    assert manifest["diagnostic_engine"] == "1.0"
    assert manifest["software"] == "vasp"
    rule_ids = {rule["rule_id"] for rule in manifest["rules"]}
    # All registry rules are exported, including the new closeout rules.
    assert rule_ids == set(RULES_MANIFEST)
    # Every rule has the OpenQC envelope fields.
    for rule in manifest["rules"]:
        assert {
            "rule_id",
            "software",
            "severity",
            "category",
            "confidence",
            "source",
            "summary",
            "manual_ref",
        } <= set(rule)


def test_openqc_smoke_yaml_manifest_on_disk_matches_registry() -> None:
    """The published YAML file must match the in-memory registry exactly (#28, #61)."""
    yaml_path = REPO_ROOT / "rules" / "diagnostics.yaml"
    assert yaml_path.exists(), "rules/diagnostics.yaml must exist"
    text = yaml_path.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    on_disk = json.loads("\n".join(lines).strip())
    assert on_disk == export_manifest()


def test_openqc_smoke_agent_cli_commands_smoke() -> None:
    """The agent CLI surface must respond deterministically (#26, #36, #61)."""
    result = subprocess.run(
        [sys.executable, "-m", "vasp_lsp.tool", "rules"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["operation"] == "rules"
    assert payload["software"] == "vasp"
    assert payload["rule_count"] == len(RULES_MANIFEST)


def test_openqc_smoke_diagnostic_envelope_v1() -> None:
    """Diagnostics must serialize to DiagnosticEnvelope/v1 fields (#70)."""
    text = "FOOBAZ = 1\n"
    provider = DiagnosticsProvider()
    diagnostics = provider.get_diagnostics(text, "file:///INCAR", {})
    serialized = serialize_diagnostics(
        diagnostics, software="vasp", path="INCAR", file_type="INCAR"
    )
    assert serialized, "expected at least one diagnostic"
    item = serialized[0]
    # Required envelope fields per the contract.
    for required in (
        "code",
        "severity",
        "category",
        "confidence",
        "source",
        "range",
        "software",
        "file_type",
        "path",
        "blocking",
        "fix_hints",
        "message",
    ):
        assert required in item, f"missing envelope field {required!r}"
    assert item["code"] == "vasp.incar.invalid_tag"


def _apply_edits(text: str, edits) -> str:
    """Apply LSP TextEdits to a document string (helper for tests).

    Formatting providers typically emit a single full-document replace edit
    whose end position sits one line past the last source line. We model the
    document as a flat string and translate edit ranges to character offsets
    so out-of-range end positions are handled cleanly.
    """
    line_starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            line_starts.append(index + 1)
    # Add a sentinel start for a virtual line just past the end of the text
    # so edits whose end position is line == len(lines) still resolve.
    line_starts.append(len(text) + 1)

    def _offset(line: int, character: int) -> int:
        if line >= len(line_starts):
            return len(text)
        return min(line_starts[line] + character, len(text))

    out = text
    for edit in sorted(
        edits,
        key=lambda e: (e.range.start.line, e.range.start.character),
        reverse=True,
    ):
        start = _offset(edit.range.start.line, edit.range.start.character)
        end = _offset(edit.range.end.line, edit.range.end.character)
        end = max(end, start)
        out = out[:start] + edit.new_text + out[end:]
    return out


def test_format_capability_is_idempotent_on_incar() -> None:
    """Document formatting must be idempotent on INCAR fixtures (#19, #63)."""
    provider = FormattingProvider()
    raw = "ENCUT=520\nISMEAR=0\nSIGMA=0.05\n"
    first_edits = provider.format_document(raw, "file:///INCAR", {})
    first = _apply_edits(raw, first_edits)
    # The internal INCAR formatter is idempotent: feeding the formatted
    # output back through the formatter must not change the text.
    second_edits = provider._format_incar(first)
    second = _apply_edits(first, second_edits)
    assert first == second, f"formatting is not idempotent\nfirst={first!r}\nsecond={second!r}"


def test_format_capability_handles_poscar_and_kpoints() -> None:
    """Format capability must cover POSCAR/KPOINTS (#19, #63)."""
    provider = FormattingProvider()
    poscar = "Si\n1.0\n1.0 0.0 0.0\n0.0 1.0 0.0\n0.0 0.0 1.0\n" "Si\n1\nDirect\n0.0 0.0 0.0\n"
    poscar_edits = provider.format_document(poscar, "file:///POSCAR", {})
    assert poscar_edits
    formatted_poscar = _apply_edits(poscar, poscar_edits)
    assert formatted_poscar
    kpoints = "Automatic mesh\n0\nGamma\n4 4 4\n0 0 0\n"
    kpoints_edits = provider.format_document(kpoints, "file:///KPOINTS", {})
    assert kpoints_edits
    formatted_kpoints = _apply_edits(kpoints, kpoints_edits)
    assert formatted_kpoints


def test_code_action_capability_returns_safe_quickfix() -> None:
    """Code actions must surface safe quick-fix candidates (#22, #27)."""
    text = "ENCUT = 520\nISPIN = 2\n"
    provider = DiagnosticsProvider()
    quickfixes = QuickFixesProvider()
    diagnostics = provider.get_diagnostics(text, "file:///INCAR", {})
    assert diagnostics, "expected at least one diagnostic"
    actions = quickfixes.get_code_actions(
        text,
        "file:///INCAR",
        diagnostics,
        Range(start=Position(line=1, character=0), end=Position(line=1, character=10)),
    )
    assert actions


def test_navigation_capability_returns_document_symbols() -> None:
    """Document symbols must be returned for INCAR fixtures (#23)."""
    text = "ENCUT = 520\nISMEAR = 0\n"
    provider = DocumentSymbolsProvider()
    symbols = provider.get_symbols(text, "file:///INCAR")
    assert symbols
    names = {symbol.name for symbol in symbols}
    assert "ENCUT" in names


def test_lsp_rename_capability_returns_workspace_edit() -> None:
    """Rename must return a WorkspaceEdit for opened INCAR references (#24)."""
    # The LSP feature handlers close over the module-level server instance.
    text = "ENCUT = 520\nENCUT = 530\n"
    uri = "file:///INCAR"
    _setup_server(server_module.server, uri, text)
    try:
        params = RenameParams(
            text_document=TextDocumentIdentifier(uri=uri),
            position=Position(line=0, character=2),
            new_name="EDIFF",
        )
        result = server_module.rename(params)
        assert result is not None
        changes = result.changes
        assert uri in changes
        assert len(changes[uri]) == 2
    finally:
        server_module.server.documents.pop(uri, None)


def test_lsp_rename_rejects_unknown_incar_schema_names() -> None:
    """Rename must not manufacture a tag that diagnostics classify as unknown."""
    text = "ENCUT = 520\n"
    uri = "file:///INCAR"
    _setup_server(server_module.server, uri, text)
    try:
        params = RenameParams(
            text_document=TextDocumentIdentifier(uri=uri),
            position=Position(line=0, character=2),
            new_name="NOT_A_VASP_TAG",
        )
        assert server_module.rename(params) is None
    finally:
        server_module.server.documents.pop(uri, None)


def test_lsp_rename_scope_is_open_documents_only() -> None:
    """Rename must not scan or edit unopened files on disk (#24)."""
    uri = "file:///workspace/INCAR"
    other_open_uri = "file:///workspace/other/INCAR"
    unopened_uri = "file:///workspace/closed/INCAR"
    _setup_server(server_module.server, uri, "ENCUT = 520\n")
    _setup_server(server_module.server, other_open_uri, "ENCUT = 400\n")
    try:
        params = RenameParams(
            text_document=TextDocumentIdentifier(uri=uri),
            position=Position(line=0, character=2),
            new_name="EDIFF",
        )
        result = server_module.rename(params)
        assert result is not None
        assert set(result.changes) == {uri, other_open_uri}
        assert unopened_uri not in result.changes
    finally:
        server_module.server.documents.pop(uri, None)
        server_module.server.documents.pop(other_open_uri, None)


def test_test_runner_capability_maps_captured_solver_output() -> None:
    """Captured VASP solver output must map to diagnostics via vasp-lsp-explain (#25, #37)."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".out", delete=False) as handle:
        handle.write("ERROR: SUBSPACE MATRIX IS SINGULAR\n")
        handle.write("INVGRP: inverse of rotation matrix was not found\n")
        log_path = Path(handle.name)

    try:
        exit_code = tool.explain_main([str(log_path), "--format", "json"])
        assert exit_code == 0
    finally:
        log_path.unlink(missing_ok=True)


def test_universal_preflight_envelope_includes_blocking_flag() -> None:
    """Universal preflight payloads must expose ``blocking`` for every diagnostic (#70)."""
    text = "FOOBAZ = 1\n"
    provider = DiagnosticsProvider()
    diagnostics = provider.get_diagnostics(text, "file:///INCAR", {})
    payload = {
        "diagnostics": serialize_diagnostics(
            diagnostics, software="vasp", path="INCAR", file_type="INCAR"
        )
    }
    assert payload["diagnostics"]
    for item in payload["diagnostics"]:
        assert "blocking" in item
        assert isinstance(item["blocking"], bool)
