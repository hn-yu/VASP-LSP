"""Public-behaviour tests for high-confidence VASP INCAR relationships."""

from __future__ import annotations

from pathlib import Path

from lsprotocol.types import DiagnosticSeverity

from vasp_lsp.features.diagnostics import DiagnosticsProvider


def _diagnostics(tmp_path: Path, incar: str, **neighbours: str):
    """Run the public INCAR diagnostic seam against a small calculation fixture."""
    incar_path = tmp_path / "INCAR"
    incar_path.write_text(incar, encoding="utf-8")
    for name, content in neighbours.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return DiagnosticsProvider().get_diagnostics(incar, incar_path.as_uri())


def _codes(diagnostics) -> set[str]:
    return {
        str(code) for diagnostic in diagnostics if (code := diagnostic.code) is not None
    }


def test_ismear_minus_14_and_minus_15_still_use_sigma(tmp_path: Path):
    """The Wiki documents Fermi-smearing variants -14/-15 as SIGMA users."""
    for ismear in (-14, -15):
        diagnostics = _diagnostics(tmp_path, f"ISMEAR = {ismear}\nSIGMA = 0.05\n")
        assert "vasp.smearing.ismear_sigma_mismatch" not in _codes(diagnostics)


def test_ldau_parameters_are_a_first_class_rule_and_ldauj_is_optional(tmp_path: Path):
    diagnostics = _diagnostics(tmp_path, "LDAU = .TRUE.\n")
    assert "vasp.dftu.parameters_incomplete" in _codes(diagnostics)

    complete = _diagnostics(
        tmp_path,
        "LDAU = .TRUE.\nLDAUTYPE = 2\nLDAUL = 2\nLDAUU = 4\n",
    )
    assert "vasp.dftu.parameters_incomplete" not in _codes(complete)


def test_ldau_fixed_charge_restart_checks_lmaxmix(tmp_path: Path):
    diagnostics = _diagnostics(
        tmp_path,
        "LDAU = .TRUE.\nLDAUTYPE = 2\nLDAUL = 2\nLDAUU = 4\nICHARG = 11\n",
        CHGCAR="placeholder\n",
    )
    assert "vasp.dftu.lmaxmix_for_fixed_charge" in _codes(diagnostics)

    clean = _diagnostics(
        tmp_path,
        "LDAU = .TRUE.\nLDAUTYPE = 2\nLDAUL = 2\nLDAUU = 4\nICHARG = 11\nLMAXMIX = 4\n",
        CHGCAR="placeholder\n",
    )
    assert "vasp.dftu.lmaxmix_for_fixed_charge" not in _codes(clean)


def test_noncollinear_spin_does_not_use_ispin_and_requires_three_component_shape(
    tmp_path: Path,
):
    poscar = """Fe2
1.0
3 0 0
0 3 0
0 0 3
Fe
2
Direct
0 0 0
0.5 0.5 0.5
"""
    conflict = _diagnostics(
        tmp_path,
        "LNONCOLLINEAR = .TRUE.\nISPIN = 2\n",
        POSCAR=poscar,
    )
    assert "vasp.magnetism.noncollinear_ispin_conflict" in _codes(conflict)
    assert "vasp.spin.missing_magmom" not in _codes(conflict)

    valid = _diagnostics(
        tmp_path,
        "LNONCOLLINEAR = .TRUE.\nMAGMOM = 1 0 0 0 1 0\n",
        POSCAR=poscar,
    )
    assert "vasp.magnetism.magmom_shape_mismatch" not in _codes(valid)

    invalid = _diagnostics(
        tmp_path,
        "LNONCOLLINEAR = .TRUE.\nMAGMOM = 1 0 0\n",
        POSCAR=poscar,
    )
    assert "vasp.magnetism.magmom_shape_mismatch" in _codes(invalid)

    soc = _diagnostics(
        tmp_path,
        "LSORBIT = .TRUE.\nMAGMOM = 1 0 0 0 1 0\n",
        POSCAR=poscar,
    )
    assert "vasp.magnetism.magmom_shape_mismatch" not in _codes(soc)


def test_md_requires_potim_and_positive_nsw(tmp_path: Path):
    missing_potim = _diagnostics(tmp_path, "IBRION = 0\nNSW = 100\n")
    assert "vasp.ionic.md_missing_potim" in _codes(missing_potim)
    assert any(
        diagnostic.code == "vasp.ionic.md_missing_potim"
        and diagnostic.severity == DiagnosticSeverity.Error
        for diagnostic in missing_potim
    )

    no_steps = _diagnostics(tmp_path, "IBRION = 2\nNSW = 0\n")
    assert "vasp.ionic.ibrion_nsw_mismatch" in _codes(no_steps)

    static_with_steps = _diagnostics(tmp_path, "IBRION = -1\nNSW = 10\n")
    assert "vasp.ionic.ibrion_nsw_mismatch" in _codes(static_with_steps)


def test_mdalgo_is_only_active_in_molecular_dynamics(tmp_path: Path):
    relaxation = _diagnostics(tmp_path, "MDALGO = 2\nIBRION = 2\nNSW = 100\n")
    assert "vasp.ionic.mdalgo_requires_md" in _codes(relaxation)

    md = _diagnostics(tmp_path, "MDALGO = 2\nIBRION = 0\nNSW = 100\nPOTIM = 1\n")
    assert "vasp.ionic.mdalgo_requires_md" not in _codes(md)


def test_dipole_correction_requires_idipol(tmp_path: Path):
    diagnostics = _diagnostics(tmp_path, "LDIPOL = .TRUE.\n")
    assert "vasp.electrostatics.missing_idipol" in _codes(diagnostics)

    valid = _diagnostics(tmp_path, "LDIPOL = .TRUE.\nIDIPOL = 3\n")
    assert "vasp.electrostatics.missing_idipol" not in _codes(valid)


def test_tetrahedron_smearing_requires_gamma_centered_mesh(tmp_path: Path):
    kpoints = """automatic
0
Monkhorst-Pack
4 4 4
0 0 0
"""
    diagnostics = _diagnostics(
        tmp_path,
        "ISMEAR = -5\n",
        KPOINTS=kpoints,
    )
    assert "vasp.smearing.tetrahedron_requires_gamma" in _codes(diagnostics)

    gamma = """automatic
0
Gamma
4 4 4
0 0 0
"""
    valid = _diagnostics(tmp_path, "ISMEAR = -5\n", KPOINTS=gamma)
    assert "vasp.smearing.tetrahedron_requires_gamma" not in _codes(valid)


def test_hybrid_functional_does_not_use_veryfast(tmp_path: Path):
    diagnostics = _diagnostics(tmp_path, "LHFCALC = .TRUE.\nALGO = VeryFast\n")
    assert "vasp.hybrid.veryfast_incompatible" in _codes(diagnostics)


def test_restart_file_rules_cover_istart_3_without_misclassifying_icharg_12(
    tmp_path: Path,
):
    wave_restart = _diagnostics(tmp_path, "ISTART = 3\n")
    assert "vasp.restart.file_mismatch" in _codes(wave_restart)

    # ICHARG=12 is the fixed-density superposition-of-atomic-charge mode; it
    # does not read CHGCAR. ICHARG=11 is the CHGCAR-reading mode.
    fixed_atomic_charge = _diagnostics(tmp_path, "ICHARG = 12\n")
    assert "vasp.restart.file_mismatch" not in _codes(fixed_atomic_charge)

    charge_restart = _diagnostics(tmp_path, "ICHARG = 11\n")
    assert "vasp.restart.file_mismatch" in _codes(charge_restart)
