"""Rule manifest registry for VASP-LSP (Diagnostic Engine v1).

This module is the executable source of truth for first-class LSP/OpenQC
diagnostic rules. Each rule carries the stable ``rule_id`` that the
diagnostics provider attaches to ``Diagnostic.code`` (and therefore to the
``code`` field of the agent-facing rich JSON contract).

The same registry is exported to ``rules/diagnostics.yaml`` so that OpenQC
and other external consumers can read the rule manifest without importing
the Python package. The two representations are kept in sync: the YAML file
is the published export, this module is what the linter consults at runtime.

See https://www.vasp.at/wiki/index.php/INCAR for upstream tag reference.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

DIAGNOSTIC_ENGINE_VERSION = "1.0"
SOFTWARE = "vasp"
MANIFEST_RELATIVE_PATH = "rules/diagnostics.yaml"


def _rule(
    *,
    rule_id: str,
    severity: str,
    category: str,
    confidence: float,
    summary: str,
    manual_ref: str,
    source: str = "official",
    fix_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a rule manifest entry with stable key ordering."""
    entry: Dict[str, Any] = {
        "rule_id": rule_id,
        "software": SOFTWARE,
        "severity": severity,
        "category": category,
        "confidence": confidence,
        "source": source,
        "summary": summary,
        "manual_ref": manual_ref,
    }
    if fix_hint is not None:
        entry["fix_hint"] = fix_hint
    return entry


# ---------------------------------------------------------------------------
# Registered rules
# ---------------------------------------------------------------------------

#: vasp.incar.invalid_tag — error on INCAR tags that are not part of the
#: upstream VASP INCAR schema. Upstream reference is authoritative, so the
#: rule ships at ``error`` severity per the OpenQC severity policy.
INVALID_INCAR_TAG = _rule(
    rule_id="vasp.incar.invalid_tag",
    severity="error",
    category="schema",
    confidence=1.0,
    summary=(
        "Reports INCAR tags that are not part of the upstream VASP INCAR "
        "schema. Such tags are silently ignored by VASP and almost always "
        "indicate a typo or a stale parameter name."
    ),
    manual_ref="https://www.vasp.at/wiki/index.php/INCAR",
    source="official",
    fix_hint=(
        "Remove the unknown tag or replace it with a valid INCAR tag "
        "(see https://www.vasp.at/wiki/index.php/INCAR)."
    ),
)

#: Ordered registry of all first-class rules exported by VASP-LSP.
RULES_MANIFEST: Dict[str, Dict[str, Any]] = {
    INVALID_INCAR_TAG["rule_id"]: INVALID_INCAR_TAG,
}


def get_rule(rule_id: str) -> Optional[Dict[str, Any]]:
    """Return a copy of the rule manifest entry, or ``None`` if unknown."""
    rule = RULES_MANIFEST.get(rule_id)
    return dict(rule) if rule is not None else None


def get_rule_fix_hint(rule_id: str) -> Optional[str]:
    """Return the canonical fix hint for a rule, if any."""
    rule = RULES_MANIFEST.get(rule_id)
    if rule is None:
        return None
    return rule.get("fix_hint")


def all_rules() -> List[Dict[str, Any]]:
    """Return a deterministically ordered list of all rule entries."""
    return [dict(rule) for rule in RULES_MANIFEST.values()]


def export_manifest() -> Dict[str, Any]:
    """Return the top-level manifest envelope consumed by OpenQC/tooling."""
    return {
        "diagnostic_engine": DIAGNOSTIC_ENGINE_VERSION,
        "software": SOFTWARE,
        "rules": all_rules(),
    }


def manifest_yaml_path() -> Path:
    """Resolve the on-disk ``rules/diagnostics.yaml`` export path."""
    here = Path(__file__).resolve().parent
    # src/vasp_lsp -> repo root is three parents up
    return here.parent.parent / MANIFEST_RELATIVE_PATH


def read_exported_yaml_manifest() -> Dict[str, Any]:
    """Read the exported ``rules/diagnostics.yaml`` as JSON.

    The YAML manifest intentionally uses a JSON-compatible subset so it can
    be parsed without a YAML dependency. Falls back to the in-memory
    registry if the file is absent (e.g. in an installed wheel).
    """
    path = manifest_yaml_path()
    if not path.exists():
        return export_manifest()
    text = path.read_text(encoding="utf-8")
    # The manifest is hand-authored as strict JSON-in-YAML, so json.loads
    # works on the embedded document. We strip any leading comment lines.
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    stripped = "\n".join(lines).strip()
    if not stripped:
        return export_manifest()
    loaded = json.loads(stripped)
    return loaded if isinstance(loaded, dict) else export_manifest()
