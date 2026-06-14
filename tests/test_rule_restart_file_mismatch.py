"""Focused fixture/golden test for the vasp.restart.file_mismatch rule (#60).

This test is the single source of truth for the rule's stable identity,
severity, range, category, source, and fix hint. The golden file lives next
to the fixtures so OpenQC and other consumers can read the same contract:

- ``tests/fixtures/rules/restart_file_mismatch/INCAR``       -> invalid fixture (ISTART = 1, no WAVECAR)
- ``tests/fixtures/rules/restart_file_mismatch/valid_INCAR`` -> valid non-triggering fixture (ISTART = 0)
- ``tests/fixtures/rules/restart_file_mismatch.json``        -> golden assertions

ISTART (https://www.vasp.at/wiki/index.php/ISTART) governs whether VASP
restarts from an existing WAVECAR. ISTART >= 1 means VASP reads the
plane-wave coefficients from a pre-existing WAVECAR, which must be present
and compatible with the current run (matching ENCUT, NBANDS, FFT mesh, and
parallelization layout). When the restart-implying setting is combined with
a missing restart file the run is incompatible with the available evidence,
so the rule warns. ICHARG in {1, 11} (https://www.vasp.at/wiki/index.php/ICHARG)
follows the same contract for CHGCAR.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from vasp_lsp.features.diagnostics import DiagnosticsProvider
from vasp_lsp.rich_diagnostics import diagnostic_to_dict
from vasp_lsp.rules import RULES_MANIFEST, get_rule

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "rules" / "restart_file_mismatch"
GOLDEN_PATH = Path(__file__).parent / "fixtures" / "rules" / "restart_file_mismatch.json"

RULE_ID = "vasp.restart.file_mismatch"


def _load_golden() -> Dict[str, Any]:
    loaded = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"golden must be a JSON object, got {type(loaded)!r}"
    return loaded


def _check_fixture(fixture_path: Path) -> list[dict]:
    provider = DiagnosticsProvider()
    text = fixture_path.read_text(encoding="utf-8")
    diagnostics = provider.get_diagnostics(text, fixture_path.resolve().as_uri(), {})
    return [
        diagnostic_to_dict(d, software="vasp", path=str(fixture_path), file_type="INCAR")
        for d in diagnostics
    ]


def _check_text(text: str, workspace: Dict[str, str] | None = None) -> list[dict]:
    provider = DiagnosticsProvider()
    diagnostics = provider.get_diagnostics(text, "file:///INCAR", workspace)
    return [
        diagnostic_to_dict(d, software="vasp", path="INCAR", file_type="INCAR") for d in diagnostics
    ]


def test_rule_is_registered_in_manifest() -> None:
    """The rule must be exported by the rule manifest at warning severity."""
    assert RULE_ID in RULES_MANIFEST
    rule = get_rule(RULE_ID)
    assert rule is not None
    assert rule["rule_id"] == RULE_ID
    assert rule["severity"] == "warning"
    assert rule["category"] == "semantic consistency"
    assert rule["software"] == "vasp"
    assert rule["source"] == "official"


def test_invalid_fixture_emits_exactly_this_rule() -> None:
    """ISTART = 1 without a neighbouring WAVECAR must produce exactly one rule diagnostic."""
    golden = _load_golden()
    items = _check_fixture(FIXTURE_DIR / "INCAR")

    matching = [item for item in items if item["code"] == RULE_ID]
    assert (
        len(matching) == 1
    ), f"expected exactly one {RULE_ID} diagnostic, got codes={[i['code'] for i in items]}"
    item = matching[0]

    assert item["severity"] == golden["severity"]
    assert item["category"] == golden["category"]
    assert item["confidence"] == golden["confidence"]
    assert item["source"] == golden["source"]
    assert item["manual_ref"] == golden["manual_ref"]
    assert golden["message_contains"] in item["message"]
    assert item["range"] == golden["range"]
    assert any(
        golden["fix_hints_contains"] in hint for hint in item["fix_hints"]
    ), f"fix_hints missing {golden['fix_hints_contains']!r}: {item['fix_hints']}"
    assert item["blocking"] is golden["blocking"]


def test_valid_fixture_does_not_trigger_rule() -> None:
    """An INCAR with ISTART = 0 (no restart implied) must not emit the rule."""
    items = _check_fixture(FIXTURE_DIR / "valid_INCAR")
    matching = [item for item in items if item["code"] == RULE_ID]
    assert matching == [], f"valid fixture unexpectedly emitted {RULE_ID}: {matching}"


def test_istart_with_wavecar_present_does_not_trigger_rule() -> None:
    """ISTART = 1 with a neighbouring WAVECAR present is a compatible restart."""
    workspace = {"file:///WAVECAR": "fake wavecar bytes"}
    items = _check_text("ISTART = 1\n", workspace=workspace)
    matching = [item for item in items if item["code"] == RULE_ID]
    assert matching == [], f"ISTART=1 with WAVECAR unexpectedly emitted {RULE_ID}: {matching}"


def test_icharg_without_chgcar_triggers_rule() -> None:
    """ICHARG in {1, 11} reads a precomputed CHGCAR; missing it must warn."""
    items = _check_text("ICHARG = 11\n")
    matching = [item for item in items if item["code"] == RULE_ID]
    assert (
        len(matching) == 1
    ), f"ICHARG=11 without CHGCAR must trigger {RULE_ID}: codes={[i['code'] for i in items]}"


def test_icharg_zero_does_not_trigger_rule() -> None:
    """ICHARG = 0 computes the charge density from scratch; no CHGCAR is required."""
    items = _check_text("ICHARG = 0\n")
    matching = [item for item in items if item["code"] == RULE_ID]
    assert matching == [], f"ICHARG=0 unexpectedly emitted {RULE_ID}: {matching}"


def test_istart_zero_does_not_trigger_rule() -> None:
    """ISTART = 0 starts from scratch; no WAVECAR is required."""
    items = _check_text("ISTART = 0\n")
    matching = [item for item in items if item["code"] == RULE_ID]
    assert matching == [], f"ISTART=0 unexpectedly emitted {RULE_ID}: {matching}"


def test_message_mentions_istart() -> None:
    """The message must name the restart-implying flag so quickfixes can anchor on it."""
    items = _check_fixture(FIXTURE_DIR / "INCAR")
    matching = [item for item in items if item["code"] == RULE_ID]
    assert matching, "rule did not fire on the invalid fixture"
    message = matching[0]["message"]
    assert "ISTART" in message, message
