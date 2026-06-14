from lsprotocol.types import DiagnosticSeverity

from vasp_lsp.features.diagnostics import DiagnosticsProvider
from vasp_lsp.parsers.vasp_log_parser import VASPLogParser


def test_vasp_log_parser_converts_runtime_patterns_to_diagnostics() -> None:
    content = """running VASP
Error EDDDAV: Call to ZHEGV failed. Returncode = 5
more output
"""

    diagnostics = VASPLogParser(content, "file:///calc/slurm-123.out").parse()

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.id == "vasp.runtime.edddav_zhegv"
    assert diagnostic.line_index == 1
    assert diagnostic.severity == "error"
    assert diagnostic.confidence >= 0.8
    assert any("ALGO = Normal" in action.title for action in diagnostic.suggested_actions)


def test_vasp_log_parser_ignores_clean_logs() -> None:
    content = """DAV: 1 -0.111
reached required accuracy - stopping structural energy minimisation
General timing and accounting informations for this job:
"""

    assert VASPLogParser(content, "file:///calc/OUTCAR").parse() == []


def test_diagnostics_provider_handles_runtime_log_files() -> None:
    content = """Header
INVGRP: inverse of rotation matrix was not found
"""

    provider = DiagnosticsProvider()
    diagnostics = provider.get_diagnostics(content, "file:///calc/vasp.out")

    assert provider._get_file_type("file:///calc/OUTCAR") == "VASP_LOG"
    assert provider._get_file_type("file:///calc/slurm-123.out") == "VASP_LOG"
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    # Symmetry-category runtime patterns roll up to the aggregated rule id
    # vasp.log.symmetry_failure (#58). The detailed pattern id is preserved
    # on ``data.pattern_id`` for traceability.
    assert diagnostic.code == "vasp.log.symmetry_failure"
    assert diagnostic.data["pattern_id"] == "vasp.runtime.invgrp_symmetry"
    assert diagnostic.severity == DiagnosticSeverity.Error
    assert diagnostic.source == "vasp-lsp-runtime"
    assert diagnostic.range.start.line == 1
    assert diagnostic.range.end.line == 1
    assert diagnostic.data["confidence"] == 0.9
    assert "ISYM = 0" in diagnostic.message


def test_diagnostic_snapshot_includes_runtime_metadata() -> None:
    content = "PSSYEVX: not enough eigenvalues found\n"

    snapshot = DiagnosticsProvider().get_diagnostics_snapshot(content, "file:///calc/stdout")

    assert snapshot["file_type"] == "VASP_LOG"
    assert snapshot["summary"]["error"] == 1
    item = snapshot["diagnostics"][0]
    # Electronic-minimization patterns roll up to the aggregated rule id
    # vasp.log.electronic_minimization_failed (#59).
    assert item["code"] == "vasp.log.electronic_minimization_failed"
    assert item["pattern_id"] == "vasp.runtime.pssyevx_eigenvalues"
    # Aggregated rule confidence takes precedence over the pattern's
    # confidence; the original pattern confidence is preserved separately.
    assert item["confidence"] == 0.88
    assert item["pattern_confidence"] == 0.86
    assert item["category"] == "preflight/runtime-risk"
    assert item["pattern_category"] == "electronic_minimization"
    assert item["related_files"] == ["INCAR", "POSCAR", "OUTCAR", "stdout"]


def test_electronic_runtime_diagnostic_marks_restart_file_hints_unsafe() -> None:
    content = "Error EDDDAV: Call to ZHEGV failed. Returncode = 5\n"

    diagnostic = DiagnosticsProvider().get_diagnostics(content, "file:///calc/OUTCAR")[0]
    actions = diagnostic.data["suggested_actions"]

    assert any(action["title"] == "Set ALGO = Normal" for action in actions)
    assert any(
        action["title"] == "Suggest removing CHGCAR/WAVECAR after confirmation"
        and action["safe_to_auto_apply"] is False
        for action in actions
    )
