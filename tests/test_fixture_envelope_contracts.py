"""Closed-loop fixture contracts for VASP DiagnosticEnvelope/v1 (#84)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from vasp_lsp.features.diagnostics import DiagnosticsProvider
from vasp_lsp.rich_diagnostics import diagnostic_to_dict

REPO_ROOT = Path(__file__).resolve().parent.parent

ENVELOPE_FIELDS = (
    "code",
    "severity",
    "category",
    "confidence",
    "source",
    "range",
    "software",
    "path",
    "blocking",
    "fix_hints",
    "message",
)


def _run_check(target: str) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "vasp_lsp.tool", "check", target, "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode in (0, 1), result.stderr
    return cast(dict[str, Any], json.loads(result.stdout))


def test_valid_fixture_is_clean_under_agent_check() -> None:
    path = REPO_ROOT / "tests/fixtures/valid/minimal.INCAR"
    payload = _run_check(str(path))
    assert payload["diagnostic_engine"] == "1.0"
    assert payload["ok"] is True, payload["diagnostics"]
    for item in payload["diagnostics"]:
        for field in ENVELOPE_FIELDS:
            assert field in item


def test_blocking_invalid_fixture_envelope() -> None:
    path = REPO_ROOT / "tests/fixtures/invalid/blocking_invalid_tag.INCAR"
    payload = _run_check(str(path))
    assert payload["ok"] is False
    blocking = [item for item in payload["diagnostics"] if item["blocking"]]
    assert blocking
    assert blocking[0]["code"] == "vasp.incar.invalid_tag"
    assert blocking[0]["severity"] == "error"


def test_warning_fixture_envelope() -> None:
    path = REPO_ROOT / "tests/fixtures/invalid/warning_missing_magmom.INCAR"
    payload = _run_check(str(path))
    warnings = [
        item for item in payload["diagnostics"] if item["code"] == "vasp.spin.missing_magmom"
    ]
    assert warnings
    assert warnings[0]["severity"] == "warning"
    assert warnings[0]["blocking"] is False


def test_log_fixture_runtime_diagnostic_envelope() -> None:
    path = REPO_ROOT / "tests/fixtures/logs/electronic_minimization_failed.out"
    provider = DiagnosticsProvider()
    text = path.read_text(encoding="utf-8")
    diagnostics = provider.get_diagnostics(text, path.resolve().as_uri(), {})
    serialized = [
        diagnostic_to_dict(d, software="vasp", path=str(path), file_type="VASP_LOG")
        for d in diagnostics
    ]
    matching = [
        item for item in serialized if item["code"] == "vasp.log.electronic_minimization_failed"
    ]
    assert matching
    assert matching[0]["blocking"] is True
    for field in ENVELOPE_FIELDS:
        assert field in matching[0]


def test_explain_main_accepts_log_fixture() -> None:
    path = REPO_ROOT / "tests/fixtures/logs/electronic_minimization_failed.out"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from vasp_lsp.tool import explain_main; raise SystemExit(explain_main([%r, '--format', 'json']))"
            % str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode in (0, 1)
    payload = json.loads(result.stdout)
    assert payload["operation"] == "explain"
    assert payload["diagnostics"]
