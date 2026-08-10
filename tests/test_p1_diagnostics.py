"""Tests for P1 diagnostic features: #18, #20, #21.

#18 — Live diagnostics snapshots for agent feedback loops
#20 — Schema-aware static checks as LSP diagnostics
#21 — Validate VASP keyword value types, enums, units, and required sections
"""

import json

from vasp_lsp.features.diagnostics import DiagnosticsProvider
from vasp_lsp.schemas.incar_tags import get_tag_info

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROVIDER = DiagnosticsProvider()


def _incar_diags(content, poscar=None, potcar=None, kpoints=None):
    workspace = {}
    if poscar is not None:
        workspace["file:///test/POSCAR"] = poscar
    if potcar is not None:
        workspace["file:///test/POTCAR"] = potcar
    if kpoints is not None:
        workspace["file:///test/KPOINTS"] = kpoints
    return PROVIDER.get_diagnostics(
        content, "file:///test/INCAR", workspace_documents=workspace or None
    )


def _incar_snapshot(content, poscar=None, potcar=None, kpoints=None):
    workspace = {}
    if poscar is not None:
        workspace["file:///test/POSCAR"] = poscar
    if potcar is not None:
        workspace["file:///test/POTCAR"] = potcar
    if kpoints is not None:
        workspace["file:///test/KPOINTS"] = kpoints
    return PROVIDER.get_diagnostics_snapshot(
        content, "file:///test/INCAR", workspace_documents=workspace or None
    )


# ---------------------------------------------------------------------------
# #18: Diagnostic snapshot for agent feedback loops
# ---------------------------------------------------------------------------


class TestDiagnosticSnapshot:
    """Tests for the structured diagnostic snapshot API (#18)."""

    def test_snapshot_returns_dict(self):
        snap = _incar_snapshot("SYSTEM = test\n")
        assert isinstance(snap, dict)
        assert "uri" in snap
        assert "file_type" in snap
        assert "diagnostics" in snap
        assert "summary" in snap

    def test_snapshot_file_type(self):
        snap = _incar_snapshot("SYSTEM = test\n")
        assert snap["file_type"] == "INCAR"

    def test_snapshot_includes_tags(self):
        snap = _incar_snapshot("ENCUT = 500\nISMEAR = 0\nSIGMA = 0.1\n")
        assert "tags" in snap
        assert "ENCUT" in snap["tags"]
        assert snap["tags"]["ENCUT"]["value"] == 500

    def test_encut_hint_explains_potcar_enmax_source(self):
        potcar = """PAW_PBE Fe 06Sep2000
 ENMAX = 400.000; ENMIN = 300.000 eV
End of Dataset
"""
        diagnostics = _incar_diags("ENCUT = 500\n", potcar=potcar)
        messages = [diagnostic.message for diagnostic in diagnostics]

        assert any(
            "max POTCAR ENMAX=400" in message
            and "not an INCAR tag" in message
            for message in messages
        )

    def test_snapshot_summary_counts_severities(self):
        snap = _incar_snapshot("FOOBAR = 1\n")
        assert "summary" in snap
        assert isinstance(snap["summary"], dict)
        assert "error" in snap["summary"]
        assert "warning" in snap["summary"]

    def test_snapshot_diagnostics_have_required_fields(self):
        snap = _incar_snapshot("FOOBAR = 1\n")
        if snap["diagnostics"]:
            d = snap["diagnostics"][0]
            assert "message" in d
            assert "severity" in d
            assert "line" in d
            assert "character" in d
            assert "source" in d

    def test_snapshot_calculation_mode_detected(self):
        snap = _incar_snapshot("IBRION = 2\nNSW = 100\nEDIFFG = -0.01\n")
        assert "calculation_mode" in snap
        assert snap["calculation_mode"]["name"] == "relaxation"

    def test_snapshot_json_serializable(self):
        snap = _incar_snapshot("ENCUT = 500\n")
        json_str = json.dumps(snap, default=str)
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["file_type"] == "INCAR"

    def test_snapshot_poscar_file(self):
        poscar = """Test
1.0
5.0 0.0 0.0
0.0 5.0 0.0
0.0 0.0 5.0
Si
1
Direct
0.0 0.0 0.0
"""
        snap = PROVIDER.get_diagnostics_snapshot(poscar, "file:///test/POSCAR")
        assert snap["file_type"] == "POSCAR"
        assert "diagnostics" in snap
        assert "tags" not in snap  # tags only for INCAR

    def test_snapshot_empty_unknown_file(self):
        snap = PROVIDER.get_diagnostics_snapshot("hello", "file:///test/README")
        assert snap["file_type"] == "UNKNOWN"
        assert snap["diagnostics"] == []

    def test_line_numbers_are_1_based_in_snapshot(self):
        snap = _incar_snapshot("ENCUT = 500\nFOOBAR = 1\n")
        if snap["diagnostics"]:
            for d in snap["diagnostics"]:
                assert d["line"] >= 1

    def test_snapshot_includes_end_positions(self):
        snap = _incar_snapshot("FOOBAR = 1\n")
        if snap["diagnostics"]:
            d = snap["diagnostics"][0]
            assert "end_line" in d
            assert "end_character" in d
            assert d["end_line"] >= d["line"]


# ---------------------------------------------------------------------------
# #20: Schema-aware static checks
# ---------------------------------------------------------------------------


class TestCaseSensitiveEnumValidation:
    """Tests for case-sensitive enum validation in schema (#20)."""

    def test_algo_wrong_case_error(self):
        """ALGO is case-sensitive; lowercase should produce an error."""
        diags = _incar_diags("ALGO = normal\n")
        msgs = [d.message for d in diags]
        assert any("case-sensitive" in m and "ALGO" in m for m in msgs)

    def test_algo_correct_case_no_error(self):
        """ALGO = Normal is a valid case-sensitive value."""
        diags = _incar_diags("ALGO = Normal\n")
        msgs = [d.message for d in diags]
        assert not any("case-sensitive" in m for m in msgs)

    def test_prec_wrong_case_error(self):
        """PREC is case-sensitive; lowercase should produce an error."""
        diags = _incar_diags("PREC = accurate\n")
        msgs = [d.message for d in diags]
        assert any("case-sensitive" in m and "PREC" in m for m in msgs)

    def test_prec_correct_case_no_error(self):
        """PREC = Accurate is a valid case-sensitive value."""
        diags = _incar_diags("PREC = Accurate\n")
        msgs = [d.message for d in diags]
        assert not any("case-sensitive" in m for m in msgs)

    def test_precfock_wrong_case_error(self):
        diags = _incar_diags("LHFCALC = .TRUE.\nPRECFOCK = low\n")
        msgs = [d.message for d in diags]
        assert any("case-sensitive" in m and "PRECFOCK" in m for m in msgs)

    def test_precfock_correct_case_no_error(self):
        diags = _incar_diags("LHFCALC = .TRUE.\nPRECFOCK = Low\n")
        msgs = [d.message for d in diags]
        assert not any("case-sensitive" in m and "PRECFOCK" in m for m in msgs)


class TestSchemaConflicts:
    """Tests for schema-declared conflict detection (#20)."""

    def test_ncore_npar_conflict_via_schema(self):
        diags = _incar_diags("NCORE = 4\nNPAR = 4\n")
        msgs = [d.message.lower() for d in diags]
        assert any("ncore" in m and "npar" in m for m in msgs)


class TestUnitMetadata:
    """Verify unit metadata is present on key tags (#20)."""

    def test_encut_has_unit(self):
        tag = get_tag_info("ENCUT")
        assert tag.unit == "eV"

    def test_sigma_has_unit(self):
        tag = get_tag_info("SIGMA")
        assert tag.unit == "eV"

    def test_ediff_has_unit(self):
        tag = get_tag_info("EDIFF")
        assert tag.unit == "eV"

    def test_ediffg_has_unit(self):
        tag = get_tag_info("EDIFFG")
        assert tag.unit is not None
        assert "eV" in tag.unit

    def test_potim_has_unit(self):
        tag = get_tag_info("POTIM")
        assert tag.unit is not None

    def test_kspacing_has_unit(self):
        tag = get_tag_info("KSPACING")
        assert tag.unit is not None

    def test_hfscreen_has_unit(self):
        tag = get_tag_info("HFSCREEN")
        assert tag.unit is not None

    def test_range_validation_includes_unit_hint(self):
        """When a value is below the valid range, the unit should appear in the message."""
        diags = _incar_diags("ENCUT = -1\n")
        msgs = [d.message for d in diags]
        assert any("eV" in m and "ENCUT" in m and "below" in m for m in msgs)


class TestStringTypeValidation:
    """Tests for string type validation (#20)."""

    def test_string_tag_accepts_a_multiword_value(self):
        """Whitespace in a documented string value must not create a fake array."""
        diags = _incar_diags("SYSTEM = hello world foo\n")
        msgs = [d.message for d in diags]
        assert not any("expects a single string value" in m for m in msgs)


# ---------------------------------------------------------------------------
# #21: Required sections and calculation modes
# ---------------------------------------------------------------------------


class TestCalculationModeDetection:
    """Tests for calculation-mode detection and required-tag warnings (#21)."""

    def test_relaxation_mode_detected(self):
        diags = _incar_diags("IBRION = 2\nNSW = 100\nEDIFFG = -0.01\n")
        msgs = [d.message.lower() for d in diags]
        # Should not warn about missing IBRION/NSW/EDIFFG since all are present
        assert not any("relaxation" in m and "missing" in m for m in msgs)

    def test_relaxation_mode_missing_EDIFFG(self):
        diags = _incar_diags("IBRION = 2\nNSW = 100\n")
        msgs = [d.message.lower() for d in diags]
        assert any("relaxation" in m and "ediffg" in m for m in msgs)

    def test_molecular_dynamics_mode_missing_POTIM(self):
        diags = _incar_diags("IBRION = 0\nNSW = 1000\n")
        msgs = [d.message.lower() for d in diags]
        assert any("molecular_dynamics" in m and "potim" in m for m in msgs)

    def test_static_mode_no_missing_required(self):
        """Static mode has no required tags (empty list), so no missing-tag warning."""
        diags = _incar_diags("NSW = 0\nIBRION = -1\n")
        msgs = [d.message.lower() for d in diags]
        assert not any("static" in m and "missing" in m for m in msgs)

    def test_band_structure_mode_detected(self):
        diags = _incar_diags("ICHARG = 11\n")
        msgs = [d.message.lower() for d in diags]
        assert any("band_structure" in m for m in msgs)

    def test_phonon_mode_missing_potim(self):
        diags = _incar_diags("IBRION = 5\n")
        msgs = [d.message.lower() for d in diags]
        assert any("phonon" in m and "potim" in m for m in msgs)

    def test_hybrid_mode_detected(self):
        diags = _incar_diags("LHFCALC = .TRUE.\n")
        msgs = [d.message.lower() for d in diags]
        assert any("hybrid" in m for m in msgs)

    def test_dft_u_mode_detected(self):
        diags = _incar_diags("LDAU = .TRUE.\n")
        msgs = [d.message.lower() for d in diags]
        assert any("dft_u" in m for m in msgs)


class TestCalculationModeRecommendedTags:
    """Tests that recommended tags are suggested as hints (#21)."""

    def test_relaxation_recommends_encut_isif(self):
        diags = _incar_diags("IBRION = 2\nNSW = 100\nEDIFFG = -0.01\n")
        msgs = [d.message.lower() for d in diags]
        # Should recommend ISIF, POTIM, EDIFF, ENCUT
        assert any("relaxation" in m and "isif" in m for m in msgs)

    def test_band_structure_recommends_lorbit(self):
        diags = _incar_diags("ICHARG = 11\n")
        msgs = [d.message.lower() for d in diags]
        assert any("band_structure" in m and "lorbit" in m for m in msgs)


class TestEnumValidation:
    """Tests for enum value validation (#21)."""

    def test_invalid_integer_enum_error(self):
        # The VASP Wiki allows every positive integer as a
        # Methfessel-Paxton order, so use a value outside the documented
        # negative sentinels and positive-integer domain.
        diags = _incar_diags("ISMEAR = -16\n")
        msgs = [d.message.lower() for d in diags]
        assert any("invalid value" in m and "ismear" in m for m in msgs)

    def test_valid_integer_enum_no_error(self):
        diags = _incar_diags("ISMEAR = 0\n")
        msgs = [d.message for d in diags]
        assert not any("Invalid value" in m and "ISMEAR" in m for m in msgs)

    def test_invalid_algo_enum_error(self):
        diags = _incar_diags("ALGO = Bogus\n")
        msgs = [d.message for d in diags]
        assert any("ALGO" in m and "Invalid" in m for m in msgs)

    def test_valid_algo_enum_no_error(self):
        diags = _incar_diags("ALGO = Fast\n")
        msgs = [d.message for d in diags]
        assert not any("ALGO" in m and "Invalid" in m for m in msgs)

    def test_invalid_lreal_enum(self):
        diags = _incar_diags("LREAL = Maybe\n")
        msgs = [d.message for d in diags]
        assert any("LREAL" in m and ("Invalid" in m or "Allowed" in m) for m in msgs)


class TestRangeValidation:
    """Tests for numeric range validation (#21)."""

    def test_negative_encut_warning(self):
        diags = _incar_diags("ENCUT = -100\n")
        msgs = [d.message for d in diags]
        assert any("below minimum" in m and "ENCUT" in m for m in msgs)

    def test_zero_nelm_warning(self):
        diags = _incar_diags("NELM = 0\n")
        msgs = [d.message for d in diags]
        assert any("below minimum" in m and "NELM" in m for m in msgs)

    def test_amix_above_1_warning(self):
        diags = _incar_diags("AMIX = 1.5\n")
        msgs = [d.message for d in diags]
        assert any("above maximum" in m and "AMIX" in m for m in msgs)

    def test_valid_range_no_warning(self):
        diags = _incar_diags("ENCUT = 500\nNELM = 60\nAMIX = 0.4\n")
        msgs = [d.message for d in diags]
        assert not any("below minimum" in m or "above maximum" in m for m in msgs)


class TestTypeValidation:
    """Tests for value type validation (#21)."""

    def test_integer_tag_with_string_error(self):
        diags = _incar_diags("NELM = hello\n")
        msgs = [d.message for d in diags]
        assert any("expects an integer" in m for m in msgs)

    def test_float_tag_with_string_error(self):
        diags = _incar_diags("ENCUT = abc\n")
        msgs = [d.message for d in diags]
        assert any("expects a float" in m for m in msgs)

    def test_boolean_tag_with_string_error(self):
        diags = _incar_diags("LWAVE = maybe\n")
        msgs = [d.message for d in diags]
        assert any("expects a boolean" in m for m in msgs)

    def test_valid_integer_no_error(self):
        diags = _incar_diags("NELM = 100\n")
        msgs = [d.message for d in diags]
        assert not any("expects an integer" in m for m in msgs)

    def test_valid_float_no_error(self):
        diags = _incar_diags("ENCUT = 500.0\n")
        msgs = [d.message for d in diags]
        assert not any("expects a float" in m for m in msgs)

    def test_valid_boolean_no_error(self):
        diags = _incar_diags("LWAVE = .TRUE.\n")
        msgs = [d.message for d in diags]
        assert not any("expects a boolean" in m for m in msgs)


# ---------------------------------------------------------------------------
# Regression: ensure existing checks still work
# ---------------------------------------------------------------------------


class TestRegressionExistingChecks:
    """Make sure new features don't break existing diagnostic checks."""

    def test_unknown_tag_still_warned(self):
        diags = _incar_diags("TOTALLY_UNKNOWN_TAG = 1\n")
        msgs = [d.message for d in diags]
        assert any("Unknown INCAR tag" in m for m in msgs)

    def test_duplicate_tag_still_warned(self):
        diags = _incar_diags("ENCUT = 400\nENCUT = 500\n")
        msgs = [d.message for d in diags]
        assert any("Duplicate" in m for m in msgs)

    def test_dependency_checks_still_work(self):
        diags = _incar_diags("ISPIN = 2\n")
        msgs = [d.message for d in diags]
        assert any("MAGMOM" in m for m in msgs)

    def test_workspace_checks_still_work(self):
        potcar = """PAW_PBE Si 05Jan2001
   4.00000000
ENMAX =  245.345; ENMIN =  143.678
"""
        diags = _incar_diags("ENCUT = 200\n", potcar=potcar)
        msgs = [d.message.lower() for d in diags]
        assert any("below max potcar enmax" in m for m in msgs)
