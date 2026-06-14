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

#: vasp.incar.invalid_value — error on a known INCAR tag whose value does not
#: match the tag's declared type (integer/float/boolean/string). Upstream
#: INCAR is the authoritative schema, so the rule ships at ``error`` severity
#: per the OpenQC severity policy.
INVALID_INCAR_VALUE = _rule(
    rule_id="vasp.incar.invalid_value",
    severity="error",
    category="schema",
    confidence=1.0,
    summary=(
        "Reports INCAR tags whose value does not match the tag's declared "
        "type (e.g. a non-numeric string where the upstream schema expects "
        "an integer or float, or a string where a boolean is required). "
        "Such values are rejected or silently misinterpreted by VASP."
    ),
    manual_ref="https://www.vasp.at/wiki/index.php/INCAR",
    source="official",
    fix_hint=(
        "Replace the value with one matching the tag's declared type "
        "(see https://www.vasp.at/wiki/index.php/INCAR)."
    ),
)

#: vasp.spin.missing_magmom — warn when a spin-polarized workflow (ISPIN=2)
#: is selected without a MAGMOM tag. VASP defaults missing moments to unity,
#: which silently changes the intended magnetic state, so the rule ships at
#: ``warning`` severity per the OpenQC severity policy (upstream behavior,
#: not a hard runtime failure). Upstream reference:
#: https://www.vasp.at/wiki/index.php/MAGMOM
SPIN_MISSING_MAGMOM = _rule(
    rule_id="vasp.spin.missing_magmom",
    severity="warning",
    category="semantic consistency",
    confidence=0.9,
    summary=(
        "Reports spin-polarized calculations (ISPIN=2) that do not declare "
        "an initial set of magnetic moments via MAGMOM. Without MAGMOM, "
        "VASP defaults the moments to unity, which almost always indicates "
        "a forgotten keyword in a spin workflow."
    ),
    manual_ref="https://www.vasp.at/wiki/index.php/MAGMOM",
    source="official",
    fix_hint=(
        "Add a MAGMOM tag matching your species/atom counts "
        "(see https://www.vasp.at/wiki/index.php/MAGMOM), or set ISPIN=1 "
        "if the calculation is not meant to be spin-polarized."
    ),
)

#: vasp.smearing.ismear_sigma_mismatch — warn when the ISMEAR/SIGMA pair is
#: inconsistent. For ISMEAR >= 0 (Gaussian / Methfessel-Paxton smearing) the
#: smearing width is governed by SIGMA; leaving SIGMA unset falls back to the
#: VASP default of 0.2 eV, which is rarely the intended width. For ISMEAR < 0
#: (tetrahedron method) SIGMA is unused, so setting it is misleading. Both are
#: upstream-behavior mismatches rather than hard runtime failures, so the rule
#: ships at ``warning`` severity per the OpenQC severity policy. Upstream
#: references: https://www.vasp.at/wiki/index.php/ISMEAR and
#: https://www.vasp.at/wiki/index.php/SIGMA
SMEARING_ISMEAR_SIGMA_MISMATCH = _rule(
    rule_id="vasp.smearing.ismear_sigma_mismatch",
    severity="warning",
    category="semantic consistency",
    confidence=0.9,
    summary=(
        "Reports an inconsistency between ISMEAR and SIGMA. For ISMEAR >= 0 "
        "(Gaussian or Methfessel-Paxton smearing) SIGMA sets the smearing "
        "width and should be declared explicitly; for ISMEAR < 0 (tetrahedron "
        "method) SIGMA is unused and should be omitted. A mismatch almost "
        "always indicates a forgotten or stray keyword in the smearing setup."
    ),
    manual_ref="https://www.vasp.at/wiki/index.php/ISMEAR",
    source="official",
    fix_hint=(
        "Pair ISMEAR with an explicit SIGMA width for ISMEAR >= 0 "
        "(see https://www.vasp.at/wiki/index.php/SIGMA), or remove SIGMA "
        "when ISMEAR < 0 selects the tetrahedron method."
    ),
)

#: vasp.encut.below_enmax — warn when the INCAR ENCUT is below the largest
#: ENMAX found in the neighbouring POTCAR evidence. Each pseudopotential
#: dataset ships with a recommended plane-wave cutoff (ENMAX); running below
#: the largest of these degrades the basis set the pseudopotentials were
#: balanced for. This is an upstream-behavior mismatch rather than a hard
#: runtime failure, so the rule ships at ``warning`` severity per the OpenQC
#: severity policy. Upstream reference:
#: https://www.vasp.at/wiki/index.php/ENCUT
ENCUT_BELOW_ENMAX = _rule(
    rule_id="vasp.encut.below_enmax",
    severity="warning",
    category="semantic consistency",
    confidence=0.9,
    summary=(
        "Reports an INCAR ENCUT value below the maximum ENMAX found in the "
        "neighbouring POTCAR evidence. Each pseudopotential dataset is shipped "
        "with a recommended plane-wave cutoff (ENMAX); running ENCUT below the "
        "largest of these degrades the basis set the pseudopotentials were "
        "balanced for and almost always indicates a too-low cutoff for the "
        "calculation."
    ),
    manual_ref="https://www.vasp.at/wiki/index.php/ENCUT",
    source="official",
    fix_hint=(
        "Raise ENCUT to at least the largest POTCAR ENMAX "
        "(see https://www.vasp.at/wiki/index.php/ENCUT), or ~1.3 x ENMAX for "
        "production accuracy."
    ),
)

#: vasp.parallel.ncore_npar_conflict — warn when both NCORE and NPAR are set
#: in INCAR. The two flags are mutually-exclusive parallelism controls:
#: NCORE governs the number of cores working on a single orbital, while NPAR
#: governs the number of parallel band groups; VASP derives one from the
#: other, so declaring both is contradictory and almost always indicates a
#: copy-paste from two different parallelization recipes. Upstream behavior,
#: not a hard runtime failure, so the rule ships at ``warning`` severity per
#: the OpenQC severity policy. Upstream references:
#: https://www.vasp.at/wiki/index.php/NCORE and
#: https://www.vasp.at/wiki/index.php/NPAR
PARALLEL_NCORE_NPAR_CONFLICT = _rule(
    rule_id="vasp.parallel.ncore_npar_conflict",
    severity="warning",
    category="semantic consistency",
    confidence=0.9,
    summary=(
        "Reports INCAR files that declare both NCORE and NPAR. The two flags "
        "are mutually-exclusive parallelism controls: NCORE sets the number of "
        "cores working on a single orbital and NPAR sets the number of parallel "
        "band groups; VASP derives one from the other, so declaring both is "
        "contradictory and almost always indicates a copy-paste from two "
        "different parallelization recipes."
    ),
    manual_ref="https://www.vasp.at/wiki/index.php/NCORE",
    source="official",
    fix_hint=(
        "Remove NPAR and keep NCORE for parallelization control "
        "(see https://www.vasp.at/wiki/index.php/NCORE and "
        "https://www.vasp.at/wiki/index.php/NPAR); VASP derives NPAR from "
        "NCORE automatically."
    ),
)

#: vasp.parallel.kpar_incompatible — warn when KPAR > 1 is combined with a
#: band-level parallelization flag (NCORE > 1 or NPAR > 1) in INCAR. KPAR
#: partitions the MPI ranks into k-point groups, while NCORE/NPAR govern how
#: the remaining ranks within each group share a band/orbital; the two flag
#: families operate on different MPI partitioning axes, so declaring both
#: leaves the combined layout undefined without an externally-supplied total
#: MPI rank count. This is the canonical incompatible parallelization
#: combination documented on the VASP wiki. Upstream behavior, not a hard
#: runtime failure, so the rule ships at ``warning`` severity per the OpenQC
#: severity policy. Upstream references:
#: https://www.vasp.at/wiki/index.php/KPAR and
#: https://www.vasp.at/wiki/index.php/NCORE
PARALLEL_KPAR_INCOMPATIBLE = _rule(
    rule_id="vasp.parallel.kpar_incompatible",
    severity="warning",
    category="semantic consistency",
    confidence=0.9,
    summary=(
        "Reports INCAR files that combine KPAR > 1 with a band-level "
        "parallelization flag (NCORE > 1 or NPAR > 1). KPAR partitions the MPI "
        "ranks into k-point groups while NCORE/NPAR partition the remaining "
        "ranks within each group over bands/orbitals; the two flag families "
        "operate on different MPI partitioning axes, so declaring both leaves "
        "the combined layout undefined and almost always indicates a "
        "copy-paste from two different parallelization recipes."
    ),
    manual_ref="https://www.vasp.at/wiki/index.php/KPAR",
    source="official",
    fix_hint=(
        "Pick a single parallelization axis: keep KPAR for k-point "
        "parallelization and drop the band-level flag, or remove KPAR and "
        "keep NCORE for band parallelization "
        "(see https://www.vasp.at/wiki/index.php/KPAR and "
        "https://www.vasp.at/wiki/index.php/NCORE)."
    ),
)

#: Ordered registry of all first-class rules exported by VASP-LSP.
RULES_MANIFEST: Dict[str, Dict[str, Any]] = {
    INVALID_INCAR_TAG["rule_id"]: INVALID_INCAR_TAG,
    INVALID_INCAR_VALUE["rule_id"]: INVALID_INCAR_VALUE,
    SPIN_MISSING_MAGMOM["rule_id"]: SPIN_MISSING_MAGMOM,
    SMEARING_ISMEAR_SIGMA_MISMATCH["rule_id"]: SMEARING_ISMEAR_SIGMA_MISMATCH,
    ENCUT_BELOW_ENMAX["rule_id"]: ENCUT_BELOW_ENMAX,
    PARALLEL_NCORE_NPAR_CONFLICT["rule_id"]: PARALLEL_NCORE_NPAR_CONFLICT,
    PARALLEL_KPAR_INCOMPATIBLE["rule_id"]: PARALLEL_KPAR_INCOMPATIBLE,
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
