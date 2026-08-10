"""Tests for INCAR/POTCAR/POSCAR cross-file and INCAR-internal validations.

Covers issue #1 safe subset:
  - INCAR parameter conflicts (ISMEAR/SIGMA, LCHARG/ICHARG, LWAVE/ISTART, IBRION/NSW, SMASS)
  - ENCUT production recommendation (1.3x ENMAX)
  - POTCAR functional mixing detection
  - POSCAR/POTCAR species order validation
"""

from vasp_lsp.features.diagnostics import DiagnosticsProvider
from vasp_lsp.parsers.potcar_parser import POTCARParser

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

INCAR_TEMPLATE = """SYSTEM = test
{params}
"""

POSCAR_SIMPLE = """Test System
1.0
5.0 0.0 0.0
0.0 5.0 0.0
0.0 0.0 5.0
Si O
1 1
Direct
0.0 0.0 0.0
0.5 0.5 0.5
"""

POTCAR_PBE_SI_O = """PAW_PBE Si 05Jan2001
   4.00000000
ENMAX =  245.345; ENMIN =  143.678
PAW_PBE O 08Apr2002
   3.50000000
ENMAX =  400.000; ENMIN =  225.000
"""

POTCAR_LDA_SI = """PAW LDA Si 05Jan2001
   4.00000000
ENMAX =  245.345; ENMIN =  143.678
"""

POTCAR_PBE_SI = """PAW_PBE Si 05Jan2001
   4.00000000
ENMAX =  245.345; ENMIN =  143.678
"""

POTCAR_WITH_VASP_METADATA_LINES = """TITEL  = PAW_PBE C 08Apr2002
PAW radial sets
ENMAX = 400.000; ENMIN = 300.000 eV
TITEL  = PAW_PBE Co 02Aug2007
PAW radial sets
ENMAX = 267.968; ENMIN = 200.976 eV
TITEL  = PAW_PBE H 15Jun2001
PAW radial sets
ENMAX = 250.000; ENMIN = 200.000 eV
"""

POSCAR_C_CO_H = """Test System
1.0
8.0 0.0 0.0
0.0 8.0 0.0
0.0 0.0 20.0
C Co H
1 1 1
Direct
0.0 0.0 0.0
0.5 0.5 0.5
0.1 0.1 0.1
"""


def _get_incar_diagnostics(incar_content, poscar=None, potcar=None, kpoints=None):
    """Get INCAR diagnostics with optional workspace neighbors."""
    provider = DiagnosticsProvider()
    workspace = {}
    if poscar is not None:
        workspace["file:///test/POSCAR"] = poscar
    if potcar is not None:
        workspace["file:///test/POTCAR"] = potcar
    if kpoints is not None:
        workspace["file:///test/KPOINTS"] = kpoints
    return provider.get_diagnostics(
        incar_content, "file:///test/INCAR", workspace_documents=workspace or None
    )


# ---------------------------------------------------------------------------
# INCAR internal parameter conflicts
# ---------------------------------------------------------------------------


class TestISMAR_SIGMA_Conflict:
    """Test ISMEAR < 0 with SIGMA set (SIGMA unused)."""

    def test_ismear_tetrahedron_with_sigma_info(self) -> None:
        """ISMEAR=-5 with SIGMA set produces an info diagnostic."""
        incar = "ISMEAR = -5\nSIGMA = 0.2\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message for d in diags]
        assert any("SIGMA is not used" in m for m in msgs)

    def test_ismear_tetrahedron_without_sigma_no_conflict(self) -> None:
        """ISMEAR=-5 without SIGMA produces no SIGMA-unused diagnostic."""
        incar = "ISMEAR = -5\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message for d in diags]
        assert not any("SIGMA is not used" in m for m in msgs)

    def test_ismear_gaussian_with_sigma_no_conflict(self) -> None:
        """ISMEAR=0 (Gaussian) with SIGMA produces no SIGMA-unused diagnostic."""
        incar = "ISMEAR = 0\nSIGMA = 0.2\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message for d in diags]
        assert not any("SIGMA is not used" in m for m in msgs)


class TestLCHARG_ICHARG_Conflict:
    """Test LCHARG=.TRUE. with ICHARG=11 conflict."""

    def test_lcharg_true_icharg_11_warning(self) -> None:
        """LCHARG=.TRUE. with ICHARG=11 produces a warning."""
        incar = "LCHARG = .TRUE.\nICHARG = 11\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message.lower() for d in diags]
        assert any("lcharg" in m and "icharg" in m for m in msgs)

    def test_lcharg_false_icharg_11_no_warning(self) -> None:
        """LCHARG=.FALSE. with ICHARG=11 produces no LCHARG warning."""
        incar = "LCHARG = .FALSE.\nICHARG = 11\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message.lower() for d in diags]
        assert not any("lcharg" in m and "icharg" in m for m in msgs)

    def test_lcharg_true_icharg_0_no_warning(self) -> None:
        """LCHARG=.TRUE. with ICHARG=0 produces no LCHARG/ICHARG conflict."""
        incar = "LCHARG = .TRUE.\nICHARG = 0\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message.lower() for d in diags]
        assert not any("lcharg" in m and "icharg" in m for m in msgs)


class TestLWAVE_ISTART_Conflict:
    """Test LWAVE=.TRUE. with ISTART=0 conflict."""

    def test_lwave_true_istart_0_info(self) -> None:
        """LWAVE=.TRUE. with ISTART=0 produces an info diagnostic."""
        incar = "LWAVE = .TRUE.\nISTART = 0\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message.lower() for d in diags]
        assert any("lwave" in m and "istart" in m for m in msgs)

    def test_lwave_false_istart_0_no_info(self) -> None:
        """LWAVE=.FALSE. with ISTART=0 produces no LWAVE/ISTART info."""
        incar = "LWAVE = .FALSE.\nISTART = 0\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message.lower() for d in diags]
        assert not any("lwave" in m and "istart" in m for m in msgs)

    def test_lwave_true_istart_1_no_info(self) -> None:
        """LWAVE=.TRUE. with ISTART=1 produces no LWAVE/ISTART info."""
        incar = "LWAVE = .TRUE.\nISTART = 1\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message.lower() for d in diags]
        assert not any("lwave" in m and "istart" in m for m in msgs)


class TestIBRION_NSW_Conflict:
    """Test IBRION=0 (MD) with NSW=0 conflict."""

    def test_ibrion_0_nsw_0_warning(self) -> None:
        """IBRION=0 with NSW=0 produces a warning."""
        incar = "IBRION = 0\nNSW = 0\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message.lower() for d in diags]
        assert any("ibrion" in m and "nsw" in m for m in msgs)

    def test_ibrion_0_nsw_100_no_warning(self) -> None:
        """IBRION=0 with NSW=100 produces no conflict."""
        incar = "IBRION = 0\nNSW = 100\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message.lower() for d in diags]
        assert not any("ibrion" in m and "nsw" in m for m in msgs)

    def test_ibrion_2_nsw_0_warning(self) -> None:
        """IBRION=2 with NSW=0 warns that no ionic step will run."""
        incar = "IBRION = 2\nNSW = 0\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message.lower() for d in diags]
        assert any("ibrion" in m and "nsw" in m for m in msgs)


class TestSMASS_Usage:
    """Test SMASS without appropriate IBRION."""

    def test_smass_without_ibrion_info(self) -> None:
        """SMASS without IBRION produces an info."""
        incar = "SMASS = 1.0\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message.lower() for d in diags]
        assert any("smass" in m and "ibrion" in m for m in msgs)

    def test_smass_with_ibrion_0_no_info(self) -> None:
        """SMASS with IBRION=0 produces no info."""
        incar = "SMASS = 1.0\nIBRION = 0\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message.lower() for d in diags]
        assert not any("smass" in m and "ibrion" in m for m in msgs)

    def test_smass_with_ibrion_3_no_info(self) -> None:
        """SMASS with IBRION=3 produces no info."""
        incar = "SMASS = 1.0\nIBRION = 3\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message.lower() for d in diags]
        assert not any("smass" in m and "ibrion" in m for m in msgs)

    def test_smass_with_ibrion_2_info(self) -> None:
        """SMASS with IBRION=2 (CG) produces an info."""
        incar = "SMASS = 1.0\nIBRION = 2\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message.lower() for d in diags]
        assert any("smass" in m and "ibrion" in m for m in msgs)


# ---------------------------------------------------------------------------
# ENCUT / POTCAR cross-file validations
# ---------------------------------------------------------------------------


class TestENCUTProductionRecommendation:
    """Test ENCUT production recommendation (1.3x ENMAX)."""

    def test_encut_between_enmax_and_1_3x_info(self) -> None:
        """ENCUT above ENMAX but below 1.3x ENMAX produces a recommendation info."""
        # ENMAX = 400, ENCUT = 450 (between 400 and 520)
        incar = "ENCUT = 450\n"
        diags = _get_incar_diagnostics(incar, potcar=POTCAR_PBE_SI_O)
        msgs = [d.message for d in diags]
        assert any("production" in m.lower() and "1.3" in m for m in msgs)

    def test_encut_below_enmax_warning(self) -> None:
        """ENCUT below ENMAX produces a warning (existing behavior)."""
        incar = "ENCUT = 300\n"
        diags = _get_incar_diagnostics(incar, potcar=POTCAR_PBE_SI_O)
        msgs = [d.message.lower() for d in diags]
        assert any("below max potcar enmax" in m for m in msgs)

    def test_encut_above_1_3x_no_diagnostics(self) -> None:
        """ENCUT above 1.3x ENMAX produces no ENCUT diagnostics."""
        # ENMAX = 400, 1.3x = 520, ENCUT = 550
        incar = "ENCUT = 550\n"
        diags = _get_incar_diagnostics(incar, potcar=POTCAR_PBE_SI_O)
        msgs = [d.message.lower() for d in diags]
        assert not any("encut" in m for m in msgs)

    def test_encut_without_potcar_no_diagnostics(self) -> None:
        """ENCUT without POTCAR in workspace produces no ENCUT diagnostics."""
        incar = "ENCUT = 450\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message.lower() for d in diags]
        assert not any("encut" in m for m in msgs)


# ---------------------------------------------------------------------------
# POTCAR functional mixing
# ---------------------------------------------------------------------------


class TestPOTCARFunctionalMixing:
    """Test detection of POTCAR functional mixing (e.g., PBE + LDA)."""

    def test_mixed_functionals_warning(self) -> None:
        """POTCAR with PBE and LDA entries produces a warning."""
        mixed_potcar = (
            "PAW_PBE Si 05Jan2001\n"
            "   4.00000000\n"
            "ENMAX =  245.345; ENMIN =  143.678\n"
            "PAW LDA O 08Apr2002\n"
            "   3.50000000\n"
            "ENMAX =  400.000; ENMIN =  225.000\n"
        )
        incar = "SYSTEM = test\n"
        diags = _get_incar_diagnostics(incar, poscar=POSCAR_SIMPLE, potcar=mixed_potcar)
        msgs = [d.message.lower() for d in diags]
        assert any("mixes functionals" in m for m in msgs)

    def test_single_functional_no_warning(self) -> None:
        """POTCAR with only PBE entries produces no mixing warning."""
        incar = "SYSTEM = test\n"
        diags = _get_incar_diagnostics(incar, poscar=POSCAR_SIMPLE, potcar=POTCAR_PBE_SI_O)
        msgs = [d.message.lower() for d in diags]
        assert not any("mixes functionals" in m for m in msgs)


class TestPOTCARDatasetParsing:
    """POTCAR metadata lines must not become phantom pseudopotential entries."""

    def test_paw_radial_sets_are_not_species(self) -> None:
        data = POTCARParser(POTCAR_WITH_VASP_METADATA_LINES).parse()
        assert data is not None
        assert [entry.element for entry in data.entries] == ["C", "Co", "H"]

    def test_realistic_potcar_metadata_keeps_species_order_check_clean(self) -> None:
        diagnostics = _get_incar_diagnostics(
            "ENCUT = 520\n",
            poscar=POSCAR_C_CO_H,
            potcar=POTCAR_WITH_VASP_METADATA_LINES,
        )
        assert not any("species order" in diagnostic.message.lower() for diagnostic in diagnostics)

    def test_single_species_no_mixing_check(self) -> None:
        """Single-species POTCAR never triggers mixing check."""
        incar = "SYSTEM = test\n"
        diags = _get_incar_diagnostics(incar, poscar=POSCAR_SIMPLE, potcar=POTCAR_PBE_SI)
        msgs = [d.message.lower() for d in diags]
        assert not any("mixes functionals" in m for m in msgs)


# ---------------------------------------------------------------------------
# POSCAR/POTCAR species order
# ---------------------------------------------------------------------------


class TestPOSCARPOTCAR_SpeciesOrder:
    """Test POSCAR/POTCAR species order mismatch detection."""

    def test_species_order_mismatch_warning(self) -> None:
        """POSCAR species order differs from POTCAR produces a warning."""
        # POSCAR has "Si O" but POTCAR has Si then O (same order, so no warning)
        # Let's use a POSCAR with different order
        poscar_reversed = """Test System
1.0
5.0 0.0 0.0
0.0 5.0 0.0
0.0 0.0 5.0
O Si
1 1
Direct
0.0 0.0 0.0
0.5 0.5 0.5
"""
        incar = "SYSTEM = test\n"
        diags = _get_incar_diagnostics(incar, poscar=poscar_reversed, potcar=POTCAR_PBE_SI_O)
        msgs = [d.message.lower() for d in diags]
        assert any("species order" in m for m in msgs)

    def test_species_order_match_no_warning(self) -> None:
        """Matching species order produces no warning."""
        incar = "SYSTEM = test\n"
        diags = _get_incar_diagnostics(incar, poscar=POSCAR_SIMPLE, potcar=POTCAR_PBE_SI_O)
        msgs = [d.message.lower() for d in diags]
        assert not any("species order" in m for m in msgs)


# ---------------------------------------------------------------------------
# Existing workspace checks still work (regression)
# ---------------------------------------------------------------------------


class TestExistingWorkspaceChecksStillWork:
    """Regression tests for existing workspace consistency checks."""

    def test_magmom_count_mismatch(self) -> None:
        """MAGMOM count mismatch with POSCAR still detected."""
        incar = "MAGMOM = 1.0 2.0 3.0\nISPIN = 2\n"
        diags = _get_incar_diagnostics(incar, poscar=POSCAR_SIMPLE)
        msgs = [d.message for d in diags]
        assert any("MAGMOM" in m and "entries" in m for m in msgs)

    def test_kspacing_with_kpoints_conflict(self) -> None:
        """KSPACING with KPOINTS file still produces a warning."""
        kpoints = """Automatic
0
Gamma
4 4 4
0 0 0
"""
        incar = "KSPACING = 0.5\n"
        diags = _get_incar_diagnostics(incar, kpoints=kpoints)
        msgs = [d.message.lower() for d in diags]
        assert any("kspacing" in m and "kpoints" in m for m in msgs)

    def test_encut_below_enmax_warning(self) -> None:
        """ENCUT below POTCAR ENMAX still produces a warning."""
        incar = "ENCUT = 300\n"
        diags = _get_incar_diagnostics(incar, potcar=POTCAR_PBE_SI_O)
        msgs = [d.message.lower() for d in diags]
        assert any("below max potcar enmax" in m for m in msgs)

    def test_ldau_count_mismatch(self) -> None:
        """LDAUU count mismatch with POSCAR species still detected."""
        incar = "LDAU = .TRUE.\nLDAUU = 3.0\nLDAUTYPE = 2\nLDAUL = 2\n"
        diags = _get_incar_diagnostics(incar, poscar=POSCAR_SIMPLE)
        msgs = [d.message for d in diags]
        assert any("LDAUU" in m and "entries" in m for m in msgs)


# ---------------------------------------------------------------------------
# Existing INCAR dependency checks still work (regression)
# ---------------------------------------------------------------------------


class TestExistingINCARDependenciesStillWork:
    """Regression tests for existing INCAR dependency checks."""

    def test_ncore_npar_conflict(self) -> None:
        """NCORE and NPAR conflict still detected."""
        incar = "NCORE = 4\nNPAR = 4\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message for d in diags]
        assert any("NCORE" in m and "NPAR" in m for m in msgs)

    def test_ldau_requires_ldautype(self) -> None:
        """LDAU=.TRUE. without LDAUTYPE still detected."""
        incar = "LDAU = .TRUE.\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message for d in diags]
        assert any("LDAUTYPE" in m for m in msgs)

    def test_ispin2_without_magmom(self) -> None:
        """ISPIN=2 without MAGMOM still detected."""
        incar = "ISPIN = 2\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message for d in diags]
        assert any("MAGMOM" in m for m in msgs)

    def test_ismear_ge0_without_sigma(self) -> None:
        """ISMEAR>=0 without SIGMA still detected."""
        incar = "ISMEAR = 1\n"
        diags = _get_incar_diagnostics(incar)
        msgs = [d.message for d in diags]
        assert any("SIGMA" in m for m in msgs)
