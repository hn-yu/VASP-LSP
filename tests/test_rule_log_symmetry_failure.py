"""Focused fixture/golden test for the vasp.log.symmetry_failure rule (#58)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from vasp_lsp.features.diagnostics import DiagnosticsProvider
from vasp_lsp.rich_diagnostics import diagnostic_to_dict
from vasp_lsp.rules import RULES_MANIFEST, get_rule

LOG_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "logs"
GOLDEN_PATH = Path(__file__).parent / "fixtures" / "rules" / "log_symmetry_failure.json"

RULE_ID = "vasp.log.symmetry_failure"


def _load_golden() -> Dict[str, Any]:
    loaded = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"golden must be a JSON object, got {type(loaded)!r}"
    return loaded


def _check_fixture(fixture_path: Path) -> list[dict]:
    provider = DiagnosticsProvider()
    text = fixture_path.read_text(encoding="utf-8")
    diagnostics = provider.get_diagnostics(text, fixture_path.resolve().as_uri(), {})
    return [
        diagnostic_to_dict(d, software="vasp", path=str(fixture_path), file_type="VASP_LOG")
        for d in diagnostics
    ]


def test_rule_is_registered_in_manifest() -> None:
    """The rule must be exported by the rule manifest at error severity."""
    assert RULE_ID in RULES_MANIFEST
    rule = get_rule(RULE_ID)
    assert rule is not None
    assert rule["rule_id"] == RULE_ID
    assert rule["severity"] == "error"
    assert rule["category"] == "preflight/runtime-risk"
    assert rule["software"] == "vasp"
    assert rule["source"] == "runtime"


def test_invalid_fixture_emits_exactly_this_rule() -> None:
    """The symmetry-failure log must produce at least one vasp.log.symmetry_failure diagnostic."""
    golden = _load_golden()
    items = _check_fixture(LOG_FIXTURE_DIR / "symmetry_failure.out")

    matching = [item for item in items if item["code"] == RULE_ID]
    assert (
        len(matching) >= 1
    ), f"expected at least one {RULE_ID} diagnostic, got codes={[i['code'] for i in items]}"
    item = matching[0]

    assert item["severity"] == golden["severity"]
    assert item["category"] == golden["category"]
    assert item["confidence"] == golden["confidence"]
    assert golden["message_contains"] in item["message"]
    assert any(
        golden["fix_hints_contains"] in hint for hint in item["fix_hints"]
    ), f"fix_hints missing {golden['fix_hints_contains']!r}: {item['fix_hints']}"
    assert item["blocking"] is golden["blocking"]
    # Detailed runtime pattern id is preserved on the rich JSON for traceability.
    assert "pattern_id" in item
    assert item["pattern_id"].startswith("vasp.runtime.")


def test_valid_fixture_does_not_trigger_rule() -> None:
    """A clean log must not emit the rule."""
    items = _check_fixture(LOG_FIXTURE_DIR / "symmetry_failure_valid.out")
    matching = [item for item in items if item["code"] == RULE_ID]
    assert matching == [], f"valid fixture unexpectedly emitted {RULE_ID}: {matching}"
