"""Focused fixture/golden test for the vasp.encut.below_enmax rule (#55).

This test is the single source of truth for the rule's stable identity,
severity, range, category, source, and fix hint. The golden file lives next
to the fixtures so OpenQC and other consumers can read the same contract:

- ``tests/fixtures/rules/encut_below_enmax/INCAR``       -> invalid INCAR fixture
- ``tests/fixtures/rules/encut_below_enmax/POTCAR``      -> neighbour POTCAR evidence
- ``tests/fixtures/rules/encut_below_enmax/valid_INCAR``  -> valid non-triggering INCAR
- ``tests/fixtures/rules/encut_below_enmax/valid_POTCAR`` -> neighbour POTCAR evidence
- ``tests/fixtures/rules/encut_below_enmax.json``        -> golden assertions

Unlike the single-file rules, ENCUT-vs-ENMAX is a cross-file check, so the
helper pairs each INCAR with its neighbour POTCAR via ``workspace_documents``
(the same channel the production diagnostics provider uses).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from vasp_lsp.features.diagnostics import DiagnosticsProvider
from vasp_lsp.rich_diagnostics import diagnostic_to_dict
from vasp_lsp.rules import RULES_MANIFEST, get_rule

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "rules" / "encut_below_enmax"
GOLDEN_PATH = Path(__file__).parent / "fixtures" / "rules" / "encut_below_enmax.json"

RULE_ID = "vasp.encut.below_enmax"


def _load_golden() -> Dict[str, Any]:
    loaded = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"golden must be a JSON object, got {type(loaded)!r}"
    return loaded


def _check_fixture(incar_path: Path, potcar_path: Path) -> list[dict]:
    """Run diagnostics on ``incar_path`` paired with its neighbour POTCAR.

    The POTCAR is injected through ``workspace_documents`` keyed to a URI in
    the same directory as the INCAR, mirroring how the production provider
    reads sibling POTCAR evidence.
    """
    provider = DiagnosticsProvider()
    text = incar_path.read_text(encoding="utf-8")
    incar_uri = incar_path.resolve().as_uri()
    potcar_uri = potcar_path.resolve().as_uri()
    diagnostics = provider.get_diagnostics(
        text, incar_uri, workspace_documents={potcar_uri: potcar_path.read_text(encoding="utf-8")}
    )
    return [
        diagnostic_to_dict(d, software="vasp", path=str(incar_path), file_type="INCAR")
        for d in diagnostics
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
    """ENCUT below max POTCAR ENMAX must produce exactly one rule diagnostic."""
    golden = _load_golden()
    items = _check_fixture(FIXTURE_DIR / "INCAR", FIXTURE_DIR / "POTCAR")

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
    """ENCUT at or above max POTCAR ENMAX must not emit the rule."""
    items = _check_fixture(FIXTURE_DIR / "valid_INCAR", FIXTURE_DIR / "valid_POTCAR")
    matching = [item for item in items if item["code"] == RULE_ID]
    assert matching == [], f"valid fixture unexpectedly emitted {RULE_ID}: {matching}"


def test_missing_potcar_does_not_trigger_rule(tmp_path: Path) -> None:
    """Without POTCAR evidence the rule must stay silent (nothing to compare to).

    The fixture INCAR physically sits next to a POTCAR file, which the
    production provider reads as on-disk neighbour evidence. To exercise the
    no-POTCAR path we drop a standalone INCAR into an isolated temp directory
    that has no POTCAR sibling.
    """
    provider = DiagnosticsProvider()
    standalone = tmp_path / "INCAR"
    standalone.write_text("ENCUT = 200\n", encoding="utf-8")
    uri = standalone.resolve().as_uri()
    diagnostics = provider.get_diagnostics(
        standalone.read_text(encoding="utf-8"), uri, workspace_documents={}
    )
    items = [
        diagnostic_to_dict(d, software="vasp", path=str(standalone), file_type="INCAR")
        for d in diagnostics
    ]
    matching = [item for item in items if item["code"] == RULE_ID]
    assert matching == [], f"rule fired without POTCAR evidence: {matching}"
