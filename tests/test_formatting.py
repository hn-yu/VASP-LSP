"""Tests for the formatting provider."""

import pytest
from lsprotocol.types import Range, TextEdit

from vasp_lsp.features.formatting import FormattingProvider
from vasp_lsp.schemas.incar_tags import INCAR_TAGS


@pytest.fixture
def formatter():
    """Create a formatting provider fixture."""
    return FormattingProvider()


class TestINCARFormatting:
    """Test INCAR file formatting."""

    def test_format_empty_incar(self, formatter):
        """Test formatting empty INCAR content."""
        result = formatter._format_incar("")
        assert result == []

    def test_format_simple_incar(self, formatter):
        """Test formatting simple INCAR content."""
        content = "ENCUT=500\nISMEAR=0\n"
        result = formatter._format_incar(content)
        assert len(result) == 1
        assert isinstance(result[0], TextEdit)
        assert "# VASP INCAR file" in result[0].new_text
        assert "ENCUT" in result[0].new_text
        assert "ISMEAR" in result[0].new_text

    def test_format_incar_with_groups(self, formatter):
        """Test formatting INCAR with different parameter groups."""
        content = """ENCUT=500
IBRION=2
NSW=100
ALGO=Fast
NCORE=4
"""
        result = formatter._format_incar(content)
        assert len(result) == 1
        text = result[0].new_text
        assert "# Electronic Structure" in text
        assert "# Ionic Relaxation" in text
        assert "# Mixing and Convergence" in text
        assert "# Parallelization" in text

    def test_format_incar_alignment(self, formatter):
        """Test that INCAR parameters are aligned."""
        content = "ENCUT = 500\nPREC = Accurate\n"
        result = formatter._format_incar(content)
        lines = result[0].new_text.split("\n")
        param_lines = [ln for ln in lines if "=" in ln and not ln.startswith("#")]
        assert len(param_lines) == 2

    def test_format_incar_boolean_values(self, formatter):
        """Test formatting INCAR boolean values."""
        content = "LWAVE=T\nLCHARG=.FALSE.\n"
        result = formatter._format_incar(content)
        assert ".TRUE." in result[0].new_text
        assert ".FALSE." in result[0].new_text

    def test_format_incar_array_values(self, formatter):
        """Test formatting INCAR array values."""
        content = "MAGMOM = 1 1 1\n"
        result = formatter._format_incar(content)
        assert "1 1 1" in result[0].new_text

    def test_format_incar_other_parameters(self, formatter):
        """Test formatting INCAR with unknown parameters."""
        content = "UNKNOWN_TAG = value\n"
        result = formatter._format_incar(content)
        assert "# Other Parameters" in result[0].new_text
        assert "UNKNOWN_TAG" in result[0].new_text

    def test_format_incar_places_system_first_and_uses_schema_categories(self, formatter):
        """Known schema tags should not fall into the generic Other group."""
        content = """GGA = PE
ICHARG = 2
ISTART = 0
MDALGO = 2
SYSTEM = Fe2 MD
"""

        result = formatter._format_incar(content)
        text = result[0].new_text

        assert text.splitlines()[0].startswith("SYSTEM =")
        assert text.index("SYSTEM =") < text.index("# Electronic Structure")
        assert "# Exchange-Correlation" in text
        assert "# Molecular Dynamics" in text
        assert "# Other Parameters" not in text

    def test_all_official_tags_have_explicit_non_other_display_groups(self, formatter):
        """Every schema-backed Wiki tag must have a meaningful formatter group."""
        groups = {formatter._incar_display_group(name) for name in INCAR_TAGS}

        assert "Other Parameters" not in groups
        assert formatter._incar_display_group("LANCZOSTHR") == "Many-Body Methods"
        assert formatter._incar_display_group("ELPH_DRIVER") == "Electron-Phonon"
        assert formatter._incar_display_group("ML_LMLFF") == "Machine Learning"
        assert formatter._incar_display_group("LNMRSHIELD") == "NMR"
        assert formatter._incar_display_group("LWANNIER90") == "Wannier Functions"


class TestPOSCARFormatting:
    """Test POSCAR file formatting."""

    def test_format_empty_poscar(self, formatter):
        """Test formatting empty POSCAR content."""
        result = formatter._format_poscar("")
        assert result == []

    def test_format_minimal_poscar(self, formatter):
        """Test formatting minimal POSCAR content."""
        content = """Si
1.0
1 0 0
0 1 0
0 0 1
Si
1
direct
0 0 0
"""
        result = formatter._format_poscar(content)
        assert len(result) == 1
        text = result[0].new_text
        assert "Si" in text
        assert "1.0000000000" in text
        assert "Direct" in text

    def test_format_poscar_cartesian(self, formatter):
        """Test formatting POSCAR with Cartesian coordinates."""
        content = """Si
1.0
5 0 0
0 5 0
0 0 5
Si
1
Cartesian
0 0 0
"""
        result = formatter._format_poscar(content)
        assert "Cartesian" in result[0].new_text

    def test_format_poscar_selective(self, formatter):
        """Test formatting POSCAR with selective dynamics."""
        content = """Si
1.0
5 0 0
0 5 0
0 0 5
Si
1
Direct
0 0 0 T T F
"""
        result = formatter._format_poscar(content)
        assert "T T F" in result[0].new_text

    def test_format_poscar_comments(self, formatter):
        """Test that POSCAR comments are preserved."""
        content = """Si
1.0
5 0 0
0 5 0
0 0 5
Si
1
Direct
0 0 0  # This is a comment
"""
        result = formatter._format_poscar(content)
        assert "# This is a comment" in result[0].new_text

    def test_format_poscar_short_content(self, formatter):
        """Test formatting POSCAR with less than 5 lines."""
        content = "Si\n1.0\n"
        result = formatter._format_poscar(content)
        assert result == []


class TestKPOINTSFormatting:
    """Test KPOINTS file formatting."""

    def test_format_empty_kpoints(self, formatter):
        """Test formatting empty KPOINTS content."""
        result = formatter._format_kpoints("")
        assert result == []

    def test_format_minimal_kpoints(self, formatter):
        """Test formatting minimal KPOINTS content."""
        content = """Automatic mesh
0
Gamma
4 4 4
"""
        result = formatter._format_kpoints(content)
        assert len(result) == 1
        text = result[0].new_text
        assert "Automatic mesh" in text
        assert "Gamma" in text
        assert "4 4 4" in text

    def test_format_kpoints_monkhorst(self, formatter):
        """Test formatting KPOINTS with Monkhorst-Pack."""
        content = """k-points
0
Monkhorst-Pack
4 4 4 0 0 0
"""
        result = formatter._format_kpoints(content)
        text = result[0].new_text
        assert "Monkhorst-Pack" in text

    def test_format_kpoints_line_mode(self, formatter):
        """Test formatting KPOINTS in line mode."""
        content = """k-points along high symmetry lines
20
Line-mode
Reciprocal
0 0 0 1
0.5 0 0 1
"""
        result = formatter._format_kpoints(content)
        text = result[0].new_text
        assert "Line-mode" in text

    def test_format_kpoints_explicit(self, formatter):
        """Test formatting KPOINTS with explicit k-points."""
        content = """Explicit k-points
4
Cartesian
0 0 0 0.25
0.5 0 0 0.25
"""
        result = formatter._format_kpoints(content)
        text = result[0].new_text
        assert "0.250000" in text or "0.25" in text

    def test_format_kpoints_short_content(self, formatter):
        """Test formatting KPOINTS with less than 4 lines."""
        content = "k-points\n0\n"
        result = formatter._format_kpoints(content)
        assert result == []


class TestFormattingProvider:
    """Test the main FormattingProvider class."""

    def test_get_file_type_incar(self, formatter):
        """Test file type detection for INCAR."""
        assert formatter._get_file_type("file:///path/INCAR") == "INCAR"
        assert formatter._get_file_type("file:///path/INCAR_test") == "INCAR"

    def test_get_file_type_poscar(self, formatter):
        """Test file type detection for POSCAR."""
        assert formatter._get_file_type("file:///path/POSCAR") == "POSCAR"
        assert formatter._get_file_type("file:///path/CONTCAR") == "POSCAR"

    def test_get_file_type_kpoints(self, formatter):
        """Test file type detection for KPOINTS."""
        assert formatter._get_file_type("file:///path/KPOINTS") == "KPOINTS"

    def test_get_file_type_unknown(self, formatter):
        """Test file type detection for unknown files."""
        assert formatter._get_file_type("file:///path/unknown.txt") == "UNKNOWN"

    def test_format_document_incar(self, formatter):
        """Test format_document for INCAR."""
        content = "ENCUT=500\n"
        result = formatter.format_document(content, "file:///INCAR")
        assert len(result) == 1

    def test_format_document_poscar(self, formatter):
        """Test format_document for POSCAR."""
        content = """Si
1.0
1 0 0
0 1 0
0 0 1
Si
1
Direct
0 0 0
"""
        result = formatter.format_document(content, "file:///POSCAR")
        assert len(result) == 1

    def test_format_document_kpoints(self, formatter):
        """Test format_document for KPOINTS."""
        content = """Automatic
0
Gamma
4 4 4
"""
        result = formatter.format_document(content, "file:///KPOINTS")
        assert len(result) == 1

    def test_format_document_unknown(self, formatter):
        """Test format_document for unknown file type."""
        result = formatter.format_document("content", "file:///unknown.txt")
        assert result == []

    def test_format_document_with_options(self, formatter):
        """Test format_document with options parameter."""
        content = "ENCUT=500\n"
        options = {"tabSize": 2, "insertSpaces": True}
        result = formatter.format_document(content, "file:///INCAR", options)
        assert len(result) == 1

    def test_format_value_boolean_true(self, formatter):
        """Test _format_value with True."""
        assert formatter._format_value(True) == ".TRUE."

    def test_format_value_boolean_false(self, formatter):
        """Test _format_value with False."""
        assert formatter._format_value(False) == ".FALSE."

    def test_format_value_list(self, formatter):
        """Test _format_value with list."""
        assert formatter._format_value([1, 2, 3]) == "1 2 3"

    def test_format_value_tuple(self, formatter):
        """Test _format_value with tuple."""
        assert formatter._format_value((1, 2, 3)) == "1 2 3"

    def test_format_value_number(self, formatter):
        """Test _format_value with number."""
        assert formatter._format_value(500) == "500"
        assert formatter._format_value(500.5) == "500.5"

    def test_format_value_string(self, formatter):
        """Test _format_value with string."""
        assert formatter._format_value("Normal") == "Normal"


class TestTextEditStructure:
    """Test that TextEdit structures are correctly formed."""

    def test_incar_text_edit_range(self, formatter):
        """Test INCAR text edit range."""
        content = "ENCUT=500\nISMEAR=0"
        result = formatter._format_incar(content)
        edit = result[0]
        assert isinstance(edit.range, Range)
        assert edit.range.start.line == 0
        assert edit.range.start.character == 0
        assert edit.range.end.line == 1

    def test_poscar_text_edit_range(self, formatter):
        """Test POSCAR text edit range."""
        content = """Si
1.0
1 0 0
0 1 0
0 0 1
Si
1
Direct
0 0 0
"""
        result = formatter._format_poscar(content)
        edit = result[0]
        assert isinstance(edit.range, Range)
        assert edit.range.start.line == 0

    def test_kpoints_text_edit_range(self, formatter):
        """Test KPOINTS text edit range."""
        content = """Automatic
0
Gamma
4 4 4
"""
        result = formatter._format_kpoints(content)
        edit = result[0]
        assert isinstance(edit.range, Range)
        assert edit.range.start.line == 0


class TestFormattingEdgeCases:
    """Test edge cases for formatting."""

    def test_format_incar_empty_params(self, formatter):
        """Test formatting INCAR with no parseable parameters."""
        content = "# Just a comment\n"
        result = formatter._format_incar(content)
        assert result == []

    def test_format_poscar_invalid_lattice(self, formatter):
        """Test POSCAR with invalid lattice vectors."""
        content = """Si
1.0
invalid line
0 5 0
0 0 5
Si
1
Direct
0 0 0
"""
        result = formatter._format_poscar(content)
        assert len(result) == 1
        assert "invalid line" in result[0].new_text

    def test_format_poscar_short_lattice(self, formatter):
        """Test POSCAR with short lattice lines."""
        content = """Si
1.0
1
0 5 0
0 0 5
Si
1
Direct
0 0 0
"""
        result = formatter._format_poscar(content)
        assert len(result) == 1

    def test_format_poscar_invalid_coords(self, formatter):
        """Test POSCAR with invalid coordinates."""
        content = """Si
1.0
1 0 0
0 1 0
0 0 1
Si
1
Direct
invalid coords
"""
        result = formatter._format_poscar(content)
        assert len(result) == 1
        assert "invalid coords" in result[0].new_text

    def test_format_poscar_coord_type_other(self, formatter):
        """Test POSCAR with other coordinate type."""
        content = """Si
1.0
1 0 0
0 1 0
0 0 1
Si
1
OtherType
0 0 0
"""
        result = formatter._format_poscar(content)
        assert "OTHERTYPE" in result[0].new_text

    def test_format_kpoints_line_mode_lowercase(self, formatter):
        """Test KPOINTS with lowercase line mode."""
        content = """k-points
20
l
Reciprocal
0 0 0 1
"""
        result = formatter._format_kpoints(content)
        assert "Line-mode" in result[0].new_text

    def test_format_kpoints_automatic_lowercase(self, formatter):
        """Test KPOINTS with lowercase automatic."""
        content = """k-points
0
a
4 4 4
"""
        result = formatter._format_kpoints(content)
        assert "Automatic" in result[0].new_text

    def test_format_kpoints_invalid_grid(self, formatter):
        """Test KPOINTS with invalid grid."""
        content = """k-points
0
Gamma
invalid grid
"""
        result = formatter._format_kpoints(content)
        assert "invalid grid" in result[0].new_text

    def test_format_kpoints_invalid_six_numbers(self, formatter):
        """Test KPOINTS with invalid 6-number line."""
        content = """k-points
0
Gamma
a b c d e f
"""
        result = formatter._format_kpoints(content)
        assert "a b c d e f" in result[0].new_text

    def test_format_kpoints_invalid_kpoint_line(self, formatter):
        """Test KPOINTS with invalid k-point line."""
        content = """Explicit
4
Cartesian
invalid line
"""
        result = formatter._format_kpoints(content)
        assert "invalid line" in result[0].new_text

    def test_format_poscar_short_coord(self, formatter):
        """Test POSCAR with short coordinate lines."""
        content = """Si
1.0
1 0 0
0 1 0
0 0 1
Si
1
Direct
1 2
"""
        result = formatter._format_poscar(content)
        assert len(result) == 1
