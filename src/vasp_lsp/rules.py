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

#: vasp.magnetism.noncollinear_ispin_conflict — warn when a collinear spin
#: switch is combined with a non-collinear calculation. VASP ignores ISPIN in
#: non-collinear mode; current VASP versions also reject some ISPIN=2 plus
#: MAGMOM combinations in that mode. Upstream references:
#: https://www.vasp.at/wiki/ISPIN and https://www.vasp.at/wiki/LNONCOLLINEAR
NONCOLLINEAR_ISPIN_CONFLICT = _rule(
    rule_id="vasp.magnetism.noncollinear_ispin_conflict",
    severity="warning",
    category="semantic consistency",
    confidence=0.95,
    summary=(
        "Reports ISPIN=2 combined with a non-collinear calculation. ISPIN is "
        "ignored in non-collinear mode, and current VASP versions reject some "
        "ISPIN=2/MAGMOM combinations when LNONCOLLINEAR is enabled."
    ),
    manual_ref="https://www.vasp.at/wiki/LNONCOLLINEAR",
    source="official",
    fix_hint=(
        "Remove ISPIN from a non-collinear calculation and provide the initial "
        "three-component moments through MAGMOM if needed "
        "(see https://www.vasp.at/wiki/LNONCOLLINEAR and "
        "https://www.vasp.at/wiki/MAGMOM)."
    ),
)

#: vasp.magnetism.magmom_shape_mismatch — warn when MAGMOM does not have one
#: scalar per atom in a collinear calculation or three components per atom in
#: a non-collinear calculation. Upstream reference:
#: https://www.vasp.at/wiki/MAGMOM
MAGMOM_SHAPE_MISMATCH = _rule(
    rule_id="vasp.magnetism.magmom_shape_mismatch",
    severity="warning",
    category="cross-file reference",
    confidence=0.98,
    summary=(
        "Reports a MAGMOM list whose length does not match the atoms in POSCAR: "
        "one value per atom for collinear spin and three values per atom for "
        "non-collinear spin."
    ),
    manual_ref="https://www.vasp.at/wiki/MAGMOM",
    source="official",
    fix_hint=(
        "Match MAGMOM to POSCAR atom count, using three Cartesian components "
        "per atom when LNONCOLLINEAR or LSORBIT is enabled "
        "(see https://www.vasp.at/wiki/MAGMOM)."
    ),
)

#: vasp.smearing.ismear_sigma_mismatch — warn when the ISMEAR/SIGMA pair is
#: inconsistent. For ISMEAR >= 0 (Gaussian / Methfessel-Paxton smearing) the
#: smearing width is governed by SIGMA; leaving SIGMA unset falls back to the
#: VASP default of 0.2 eV, which is rarely the intended width. SIGMA is unused
#: only for the fixed-occupation and no-smearing modes ISMEAR=-2, -3, -4, and
#: -5. These are upstream-behavior mismatches rather than hard runtime
#: failures, so the rule
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
        "width and should be declared explicitly; SIGMA is unused only for the "
        "fixed-occupation and no-smearing modes ISMEAR=-2, -3, -4, and -5. "
        "A mismatch almost "
        "always indicates a forgotten or stray keyword in the smearing setup."
    ),
    manual_ref="https://www.vasp.at/wiki/index.php/ISMEAR",
    source="official",
    fix_hint=(
        "Pair ISMEAR with an explicit SIGMA width when that mode uses smearing "
        "(see https://www.vasp.at/wiki/index.php/SIGMA), or remove SIGMA for "
        "the fixed-occupation/no-smearing modes -2, -3, -4, and -5."
    ),
)

#: vasp.smearing.tetrahedron_requires_gamma — warn when a tetrahedron method
#: is paired with an explicitly shifted Monkhorst-Pack mesh. Upstream
#: reference: https://www.vasp.at/wiki/ISMEAR
SMEARING_TETRAHEDRON_REQUIRES_GAMMA = _rule(
    rule_id="vasp.smearing.tetrahedron_requires_gamma",
    severity="warning",
    category="cross-file reference",
    confidence=0.92,
    summary=(
        "Reports tetrahedron smearing with a shifted Monkhorst-Pack mesh. "
        "The VASP Wiki recommends a Gamma-centered mesh for the tetrahedron "
        "methods."
    ),
    manual_ref="https://www.vasp.at/wiki/ISMEAR",
    source="official",
    fix_hint=(
        "Use a Gamma-centered KPOINTS mesh for tetrahedron smearing, or choose "
        "a smearing method appropriate for the current mesh "
        "(see https://www.vasp.at/wiki/ISMEAR)."
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

#: vasp.dftu.parameters_incomplete — warn when DFT+U is enabled without the
#: explicit method/species parameters normally needed to express the intended
#: calculation. LDAUJ is deliberately not required: the Wiki documents its
#: default as zero. Upstream reference: https://www.vasp.at/wiki/LDAU
DFTU_PARAMETERS_INCOMPLETE = _rule(
    rule_id="vasp.dftu.parameters_incomplete",
    severity="warning",
    category="semantic consistency",
    confidence=0.9,
    summary=(
        "Reports LDAU=.TRUE. without explicit LDAUTYPE, LDAUL, or LDAUU. "
        "LDAUJ is optional because its documented default is zero; the other "
        "parameters should be made explicit to avoid silently running a "
        "different DFT+U setup than intended."
    ),
    manual_ref="https://www.vasp.at/wiki/LDAU",
    source="official",
    fix_hint=(
        "Set LDAUTYPE, one LDAUL value per POTCAR species, and one LDAUU value "
        "per species. Add LDAUJ only when the chosen formulation needs a "
        "non-zero J (see https://www.vasp.at/wiki/LDAU)."
    ),
)

#: vasp.dftu.lmaxmix_for_fixed_charge — warn when a fixed-charge calculation
#: uses DFT+U without enough angular-momentum components in CHGCAR. Upstream
#: references: https://www.vasp.at/wiki/ICHARG and
#: https://www.vasp.at/wiki/LMAXMIX
DFTU_LMAXMIX_FIXED_CHARGE = _rule(
    rule_id="vasp.dftu.lmaxmix_for_fixed_charge",
    severity="warning",
    category="semantic consistency",
    confidence=0.92,
    summary=(
        "Reports DFT+U fixed-charge calculations (ICHARG=11 or 12) that omit "
        "LMAXMIX or leave it below the Wiki's d-element recommendation of 4. "
        "f-element calculations may require 6."
    ),
    manual_ref="https://www.vasp.at/wiki/LMAXMIX",
    source="official",
    fix_hint=(
        "Set LMAXMIX=4 for d elements or LMAXMIX=6 for f elements when using "
        "DFT+U with ICHARG=11/12 "
        "(see https://www.vasp.at/wiki/LMAXMIX)."
    ),
)

#: vasp.ionic.md_missing_potim — error when ab-initio MD omits POTIM. The
#: official Wiki says VASP crashes immediately after starting in this case.
#: Upstream reference: https://www.vasp.at/wiki/POTIM
IONIC_MD_MISSING_POTIM = _rule(
    rule_id="vasp.ionic.md_missing_potim",
    severity="error",
    category="preflight/runtime-risk",
    confidence=1.0,
    summary=(
        "Reports IBRION=0 molecular dynamics without POTIM. VASP requires the "
        "MD time step and crashes immediately when it is omitted."
    ),
    manual_ref="https://www.vasp.at/wiki/POTIM",
    source="official",
    fix_hint=(
        "Set POTIM to the intended MD time step in femtoseconds "
        "(see https://www.vasp.at/wiki/POTIM)."
    ),
)

#: vasp.ionic.ibrion_nsw_mismatch — warn when IBRION and NSW describe
#: incompatible ionic work. Upstream references:
#: https://www.vasp.at/wiki/IBRION and https://www.vasp.at/wiki/NSW
IONIC_IBRION_NSW_MISMATCH = _rule(
    rule_id="vasp.ionic.ibrion_nsw_mismatch",
    severity="warning",
    category="semantic consistency",
    confidence=0.97,
    summary=(
        "Reports an ionic-update mode with no ionic steps, or IBRION=-1 with "
        "NSW>0. In the latter case VASP repeats the same structure instead of "
        "updating it."
    ),
    manual_ref="https://www.vasp.at/wiki/IBRION",
    source="official",
    fix_hint=(
        "Use NSW>0 for MD/relaxation modes, or set IBRION=-1 together with "
        "NSW=0 for a static calculation "
        "(see https://www.vasp.at/wiki/IBRION and "
        "https://www.vasp.at/wiki/NSW)."
    ),
)

#: vasp.ionic.mdalgo_requires_md — warn when a molecular-dynamics thermostat
#: selector is used outside the MD mode. Upstream reference:
#: https://www.vasp.at/wiki/MDALGO
IONIC_MDALGO_REQUIRES_MD = _rule(
    rule_id="vasp.ionic.mdalgo_requires_md",
    severity="warning",
    category="semantic consistency",
    confidence=1.0,
    summary=(
        "Reports MDALGO when the effective ionic mode is not IBRION=0. The "
        "VASP Wiki defines MDALGO for molecular-dynamics calculations, so it "
        "does not configure a thermostat for static, relaxation, or phonon runs."
    ),
    manual_ref="https://vasp.at/wiki/MDALGO",
    source="official",
    fix_hint=(
        "Set IBRION=0 for molecular dynamics, or remove MDALGO when the run is "
        "not an MD calculation (see https://vasp.at/wiki/MDALGO)."
    ),
)

#: vasp.electrostatics.missing_idipol — warn when LDIPOL is enabled without
#: the direction selector that the official Wiki requires. Upstream reference:
#: https://www.vasp.at/wiki/LDIPOL
ELECTROSTATICS_MISSING_IDIPOL = _rule(
    rule_id="vasp.electrostatics.missing_idipol",
    severity="warning",
    category="semantic consistency",
    confidence=1.0,
    summary=(
        "Reports LDIPOL=.TRUE. without IDIPOL. The dipole-correction direction "
        "must be selected explicitly for the correction to be defined."
    ),
    manual_ref="https://www.vasp.at/wiki/LDIPOL",
    source="official",
    fix_hint=(
        "Set IDIPOL=1, 2, or 3 for a slab normal, or IDIPOL=4 for an isolated "
        "molecule (see https://www.vasp.at/wiki/IDIPOL)."
    ),
)

#: vasp.hybrid.veryfast_incompatible — warn when the VASP Wiki-prohibited
#: VeryFast algorithm is selected for a hybrid functional. Upstream references:
#: https://www.vasp.at/wiki/ALGO and https://www.vasp.at/wiki/LHFCALC
HYBRID_VERYFAST_INCOMPATIBLE = _rule(
    rule_id="vasp.hybrid.veryfast_incompatible",
    severity="warning",
    category="preflight/runtime-risk",
    confidence=1.0,
    summary=(
        "Reports ALGO=VeryFast with LHFCALC=.TRUE.; the VASP Wiki states that "
        "VeryFast is not supported for hybrid functionals."
    ),
    manual_ref="https://www.vasp.at/wiki/ALGO",
    source="official",
    fix_hint=(
        "Use ALGO=Normal or another hybrid-compatible algorithm "
        "(see https://www.vasp.at/wiki/ALGO)."
    ),
)

#: vasp.symmetry.md_isym_zero — warn when MD leaves symmetry enabled. The
#: official Wiki specifically recommends ISYM=0 for IBRION=0. Upstream
#: reference: https://www.vasp.at/wiki/ISYM
SYMMETRY_MD_ISYM_ZERO = _rule(
    rule_id="vasp.symmetry.md_isym_zero",
    severity="warning",
    category="semantic consistency",
    confidence=0.95,
    summary=(
        "Reports molecular dynamics without ISYM=0. Symmetry operations can "
        "constrain or alter an MD trajectory, so the VASP Wiki recommends "
        "disabling symmetry for IBRION=0."
    ),
    manual_ref="https://www.vasp.at/wiki/ISYM",
    source="official",
    fix_hint=(
        "Set ISYM=0 for molecular dynamics unless symmetry is deliberately part "
        "of the workflow (see https://www.vasp.at/wiki/ISYM)."
    ),
)

#: vasp.restart.file_mismatch — warn when the INCAR restart settings imply
#: reading a restart file (WAVECAR for ISTART >= 1, or CHGCAR for ICHARG in
#: {1, 11}) but no compatible restart file is present in the calculation
#: directory. VASP restart files carry run-specific metadata (ENCUT, NBANDS,
#: FFT mesh, parallelization layout); a restart-implying setting combined with
#: a missing restart file leaves the run incompatible with the available
#: evidence, since VASP would silently fall back to a fresh start or refuse to
#: read the expected coefficients. This is an upstream-behavior mismatch rather
#: than a hard runtime failure, so the rule ships at ``warning`` severity per
#: the OpenQC severity policy. Upstream references:
#: https://www.vasp.at/wiki/index.php/ISTART and
#: https://www.vasp.at/wiki/index.php/ICHARG
RESTART_FILE_MISMATCH = _rule(
    rule_id="vasp.restart.file_mismatch",
    severity="warning",
    category="semantic consistency",
    confidence=0.9,
    summary=(
        "Reports INCAR files whose restart settings imply reading a restart "
        "file that is not present in the calculation directory. ISTART >= 1 "
        "reads plane-wave coefficients from a pre-existing WAVECAR, and ICHARG "
        "in {1, 11} reads a precomputed charge density from CHGCAR; both "
        "require a compatible restart file matching the current run's ENCUT, "
        "NBANDS, FFT mesh, and parallelization layout. A restart-implying "
        "setting combined with a missing restart file is incompatible with the "
        "available evidence and almost always indicates a forgotten restart "
        "artifact or a stale restart workflow."
    ),
    manual_ref="https://www.vasp.at/wiki/index.php/ISTART",
    source="official",
    fix_hint=(
        "Provide a compatible restart file alongside the INCAR, or switch to a "
        "from-scratch start: set ISTART = 0 if no WAVECAR is intended "
        "(see https://www.vasp.at/wiki/index.php/ISTART), or set ICHARG = 0 / 2 "
        "to compute the charge density internally "
        "(see https://www.vasp.at/wiki/index.php/ICHARG)."
    ),
)

#: vasp.log.symmetry_failure — error on a VASP runtime log that records a
#: symmetry analysis failure (INVGRP, PRICEL, SGRCON, SGRGEN families). VASP
#: stops the run when these patterns fire, so the rule ships at ``error``
#: severity with ``source=runtime`` per the OpenQC severity policy. Upstream
#: reference: https://www.vasp.at/wiki/index.php/ISYM
LOG_SYMMETRY_FAILURE = _rule(
    rule_id="vasp.log.symmetry_failure",
    severity="error",
    category="preflight/runtime-risk",
    confidence=0.9,
    summary=(
        "Reports a VASP runtime log line that records a symmetry-analysis "
        "failure (INVGRP/PRICEL/SGRCON/SGRGEN families). VASP aborts the run "
        "when these patterns fire, so any matching log entry should block "
        "automated resubmission until ISYM/SYMPREC or the POSCAR is corrected."
    ),
    manual_ref="https://www.vasp.at/wiki/index.php/ISYM",
    source="runtime",
    fix_hint=(
        "Set ISYM=0 to disable symmetry analysis, tighten SYMPREC (e.g. "
        "1E-6), or correct the POSCAR lattice/sites "
        "(see https://www.vasp.at/wiki/index.php/ISYM)."
    ),
)

#: vasp.log.electronic_minimization_failed — error on a VASP runtime log that
#: records an electronic-minimization failure (EDDDAV/ZHEGV, EDDRMM/ZHEGV,
#: PSSYEVX, ZPOTRF families). VASP aborts the SCF cycle when these patterns
#: fire, so the rule ships at ``error`` severity with ``source=runtime`` per
#: the OpenQC severity policy. Upstream reference:
#: https://www.vasp.at/wiki/index.php/ALGO
LOG_ELECTRONIC_MINIMIZATION_FAILED = _rule(
    rule_id="vasp.log.electronic_minimization_failed",
    severity="error",
    category="preflight/runtime-risk",
    confidence=0.88,
    summary=(
        "Reports a VASP runtime log line that records an electronic-"
        "minimization failure (EDDDAV/ZHEGV, EDDRMM/ZHEGV, PSSYEVX, ZPOTRF "
        "families). VASP aborts the SCF cycle when these patterns fire, so "
        "any matching log entry should block automated resubmission until "
        "ALGO/POTIM or the charge-density restart is corrected."
    ),
    manual_ref="https://www.vasp.at/wiki/index.php/ALGO",
    source="runtime",
    fix_hint=(
        "Switch to ALGO=Normal, lower POTIM for geometry optimizations, or "
        "remove a stale WAVECAR/CHGCAR before retrying "
        "(see https://www.vasp.at/wiki/index.php/ALGO)."
    ),
)

#: Mapping from a VASP runtime log ``category`` (see
#: :mod:`vasp_lsp.schemas.vasp_error_patterns`) to the first-class rule id
#: that aggregates the category's runtime patterns. ``None`` means the
#: category has no first-class rule yet and the runtime pattern id stays the
#: diagnostic code.
RUNTIME_CATEGORY_RULE_MAP: Dict[str, str] = {
    "symmetry": LOG_SYMMETRY_FAILURE["rule_id"],
    "electronic_minimization": LOG_ELECTRONIC_MINIMIZATION_FAILED["rule_id"],
}

#: Ordered registry of all first-class rules exported by VASP-LSP.
RULES_MANIFEST: Dict[str, Dict[str, Any]] = {
    INVALID_INCAR_TAG["rule_id"]: INVALID_INCAR_TAG,
    INVALID_INCAR_VALUE["rule_id"]: INVALID_INCAR_VALUE,
    SPIN_MISSING_MAGMOM["rule_id"]: SPIN_MISSING_MAGMOM,
    NONCOLLINEAR_ISPIN_CONFLICT["rule_id"]: NONCOLLINEAR_ISPIN_CONFLICT,
    MAGMOM_SHAPE_MISMATCH["rule_id"]: MAGMOM_SHAPE_MISMATCH,
    SMEARING_ISMEAR_SIGMA_MISMATCH["rule_id"]: SMEARING_ISMEAR_SIGMA_MISMATCH,
    SMEARING_TETRAHEDRON_REQUIRES_GAMMA["rule_id"]: SMEARING_TETRAHEDRON_REQUIRES_GAMMA,
    ENCUT_BELOW_ENMAX["rule_id"]: ENCUT_BELOW_ENMAX,
    DFTU_PARAMETERS_INCOMPLETE["rule_id"]: DFTU_PARAMETERS_INCOMPLETE,
    DFTU_LMAXMIX_FIXED_CHARGE["rule_id"]: DFTU_LMAXMIX_FIXED_CHARGE,
    IONIC_MD_MISSING_POTIM["rule_id"]: IONIC_MD_MISSING_POTIM,
    IONIC_IBRION_NSW_MISMATCH["rule_id"]: IONIC_IBRION_NSW_MISMATCH,
    IONIC_MDALGO_REQUIRES_MD["rule_id"]: IONIC_MDALGO_REQUIRES_MD,
    ELECTROSTATICS_MISSING_IDIPOL["rule_id"]: ELECTROSTATICS_MISSING_IDIPOL,
    HYBRID_VERYFAST_INCOMPATIBLE["rule_id"]: HYBRID_VERYFAST_INCOMPATIBLE,
    SYMMETRY_MD_ISYM_ZERO["rule_id"]: SYMMETRY_MD_ISYM_ZERO,
    PARALLEL_NCORE_NPAR_CONFLICT["rule_id"]: PARALLEL_NCORE_NPAR_CONFLICT,
    PARALLEL_KPAR_INCOMPATIBLE["rule_id"]: PARALLEL_KPAR_INCOMPATIBLE,
    RESTART_FILE_MISMATCH["rule_id"]: RESTART_FILE_MISMATCH,
    LOG_SYMMETRY_FAILURE["rule_id"]: LOG_SYMMETRY_FAILURE,
    LOG_ELECTRONIC_MINIMIZATION_FAILED["rule_id"]: LOG_ELECTRONIC_MINIMIZATION_FAILED,
}


def rule_id_for_runtime_category(category: str) -> Optional[str]:
    """Return the rule id that aggregates a runtime log category, if any."""
    return RUNTIME_CATEGORY_RULE_MAP.get(category)


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
