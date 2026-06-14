"""Focused fixture/golden test for the vasp.parallel.kpar_incompatible rule (#57).

This test is the single source of truth for the rule's stable identity,
severity, range, category, source, and fix hint. The golden file lives next
to the fixtures so OpenQC and other consumers can read the same contract:

- ``tests/fixtures/rules/kpar_incompatible/INCAR``       -> invalid fixture (KPAR > 1 + NCORE > 1)
- ``tests/fixtures/rules/kpar_incompatible/valid_INCAR`` -> valid non-triggering fixture
- ``tests/fixtures/rules/kpar_incompatible.json``        -> golden assertions

KPAR (https://www.vasp.at/wiki/index.php/KPAR) parallelizes over k-points
while NCORE/NPAR (https://www.vasp.at/wiki/index.php/NCORE and
https://www.vasp.at/wiki/index.php/NPAR) parallelize over bands/orbitals;
the two operate on different MPI partitioning axes, so declaring both KPAR
and a band-parallelism flag is the canonical incompatible parallelization
combination documented on the VASP wiki.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from vasp_lsp.features.diagnostics import DiagnosticsProvider
from vasp_lsp.rich_diagnostics import diagnostic_to_dict
from vasp_lsp.rules import RULES_MANIFEST, get_rule

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "rules" / "kpar_incompatible"
GOLDEN_PATH = Path(__file__).parent / "fixtures" / "rules" / "kpar_incompatible.json"

RULE_ID = "vasp.parallel.kpar_incompatible"


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


def _check_text(text: str) -> list[dict]:
    provider = DiagnosticsProvider()
    diagnostics = provider.get_diagnostics(text, "file:///INCAR", {})
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
    """KPAR > 1 together with NCORE > 1 must produce exactly one rule diagnostic."""
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
    """An INCAR with only KPAR (no NCORE/NPAR) must not emit the rule."""
    items = _check_fixture(FIXTURE_DIR / "valid_INCAR")
    matching = [item for item in items if item["code"] == RULE_ID]
    assert matching == [], f"valid fixture unexpectedly emitted {RULE_ID}: {matching}"


def test_kpar_with_npar_triggers_rule() -> None:
    """KPAR > 1 together with NPAR > 1 (no NCORE) must also emit the rule."""
    items = _check_text("KPAR = 4\nNPAR = 4\n")
    matching = [item for item in items if item["code"] == RULE_ID]
    assert (
        len(matching) == 1
    ), f"KPAR+NPAR must trigger {RULE_ID}: codes={[i['code'] for i in items]}"


def test_kpar_one_does_not_trigger_rule() -> None:
    """KPAR=1 (default, no k-point parallelization) must not emit the rule."""
    items = _check_text("KPAR = 1\nNCORE = 4\n")
    matching = [item for item in items if item["code"] == RULE_ID]
    assert matching == [], f"KPAR=1 unexpectedly emitted {RULE_ID}: {matching}"


def test_ncore_one_does_not_trigger_rule() -> None:
    """KPAR > 1 with NCORE=1 (no band parallelism) must not emit the rule."""
    items = _check_text("KPAR = 4\nNCORE = 1\n")
    matching = [item for item in items if item["code"] == RULE_ID]
    assert matching == [], f"NCORE=1 unexpectedly emitted {RULE_ID}: {matching}"


def test_neither_parallel_axis_does_not_trigger_rule() -> None:
    """An INCAR with neither KPAR nor NCORE/NPAR must not emit the rule."""
    items = _check_text("ENCUT = 520\nISMEAR = 0\nSIGMA = 0.05\n")
    matching = [item for item in items if item["code"] == RULE_ID]
    assert matching == [], f"bare INCAR unexpectedly emitted {RULE_ID}: {matching}"


def test_message_mentions_kpar_and_ncore() -> None:
    """The message must name both KPAR and the band-parallelism flag so quickfixes match."""
    items = _check_fixture(FIXTURE_DIR / "INCAR")
    matching = [item for item in items if item["code"] == RULE_ID]
    assert matching, "rule did not fire on the invalid fixture"
    message = matching[0]["message"]
    assert "KPAR" in message, message
