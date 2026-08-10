"""Tests for POSCAR and KPOINTS diagnostics coverage."""

from vasp_lsp.features.diagnostics import DiagnosticsProvider


class TestPOSCARDiagnosticsCoverage:
    """Test coverage for POSCAR diagnostics."""

    def test_contcar_md_velocity_and_predictor_blocks_are_not_extra_coordinates(self):
        """CONTCAR MD restart sections must not be diagnosed as extra positions."""
        provider = DiagnosticsProvider()
        content = """Fe2 MD restart
1.0
10.0 0.0 0.0
0.0 10.0 0.0
0.0 0.0 10.0
Fe
2
Direct
0.0 0.0 0.0
0.5 0.5 0.5

0.01 0.02 0.03
0.04 0.05 0.06

1
1.0
0.1 0.2 0.3 0.4
0.11 0.12 0.13
0.14 0.15 0.16
0.17 0.18 0.19
0.20 0.21 0.22
0.23 0.24 0.25
0.26 0.27 0.28
"""

        diagnostics = provider.get_diagnostics(content, "file:///test/CONTCAR")

        assert not any("extra coordinate row" in d.message.lower() for d in diagnostics)

    def test_poscar_extra_coordinate_without_post_section_separator_still_warns(self):
        """A real extra coordinate row must remain visible for a normal POSCAR."""
        provider = DiagnosticsProvider()
        content = """Test System
1.0
10.0 0.0 0.0
0.0 10.0 0.0
0.0 0.0 10.0
H
1
Direct
0.0 0.0 0.0
0.5 0.5 0.5
"""

        diagnostics = provider.get_diagnostics(content, "file:///test/POSCAR")

        assert any("extra coordinate row" in d.message.lower() for d in diagnostics)

    def test_poscar_parse_error_diagnostics(self):
        """Test diagnostics for POSCAR with parse errors."""
        provider = DiagnosticsProvider()

        content = """Test System
invalid_scale
1.0 0.0 0.0
0.0 1.0 0.0
0.0 0.0 1.0
H
1
Direct
0.0 0.0 0.0
"""
        diagnostics = provider.get_diagnostics(content, "file:///test/POSCAR")

        # Should have parse error
        assert len(diagnostics) >= 1
        assert any("scale factor" in d.message.lower() for d in diagnostics)

    def test_poscar_negative_scale_factor(self):
        """Test diagnostics for POSCAR with negative scale factor."""
        provider = DiagnosticsProvider()

        content = """Test System
-1.0
1.0 0.0 0.0
0.0 1.0 0.0
0.0 0.0 1.0
H
1
Direct
0.0 0.0 0.0
"""
        diagnostics = provider.get_diagnostics(content, "file:///test/POSCAR")

        # Should have warning about negative scale factor
        assert any("negative scale factor" in d.message.lower() for d in diagnostics)

    def test_poscar_zero_atoms(self):
        """Test diagnostics for POSCAR with zero atoms."""
        provider = DiagnosticsProvider()

        content = """Test System
1.0
1.0 0.0 0.0
0.0 1.0 0.0
0.0 0.0 1.0
H
0
Direct
"""
        diagnostics = provider.get_diagnostics(content, "file:///test/POSCAR")

        # Should have error about zero atoms
        assert any("no atoms" in d.message.lower() for d in diagnostics)

    def test_poscar_direct_coordinate_out_of_range(self):
        """Test diagnostics for POSCAR with out-of-range direct coordinates."""
        provider = DiagnosticsProvider()

        content = """Test System
1.0
1.0 0.0 0.0
0.0 1.0 0.0
0.0 0.0 1.0
H
1
Direct
2.5 0.0 0.0
"""
        diagnostics = provider.get_diagnostics(content, "file:///test/POSCAR")

        # Should have information about out-of-range coordinate
        assert any("outside typical range" in d.message.lower() for d in diagnostics)

    def test_poscar_valid_no_warnings(self):
        """Test diagnostics for valid POSCAR returns empty list."""
        provider = DiagnosticsProvider()

        content = """Test System
1.0
1.0 0.0 0.0
0.0 1.0 0.0
0.0 0.0 1.0
H
1
Direct
0.5 0.5 0.5
"""
        diagnostics = provider.get_diagnostics(content, "file:///test/POSCAR")

        # Should have no diagnostics for valid POSCAR
        assert diagnostics == []


class TestKPOINTSDiagnosticsCoverage:
    """Test coverage for KPOINTS diagnostics."""

    def test_kpoints_parse_error_diagnostics(self):
        """Test diagnostics for KPOINTS with parse errors."""
        provider = DiagnosticsProvider()

        content = """Automatic
invalid_number
Gamma
4 4 4
0 0 0
"""
        diagnostics = provider.get_diagnostics(content, "file:///test/KPOINTS")

        # Should have parse error
        assert len(diagnostics) >= 1

    def test_kpoints_zero_grid_value(self):
        """Test diagnostics for KPOINTS with zero grid value."""
        provider = DiagnosticsProvider()

        content = """Automatic
0
Gamma
0 4 4
0 0 0
"""
        diagnostics = provider.get_diagnostics(content, "file:///test/KPOINTS")

        # Should have error about non-positive grid
        assert any("not positive" in d.message.lower() for d in diagnostics)

    def test_kpoints_negative_grid_value(self):
        """Test diagnostics for KPOINTS with negative grid value."""
        provider = DiagnosticsProvider()

        content = """Automatic
0
Gamma
-1 4 4
0 0 0
"""
        diagnostics = provider.get_diagnostics(content, "file:///test/KPOINTS")

        # Should have error about non-positive grid
        assert any("not positive" in d.message.lower() for d in diagnostics)

    def test_kpoints_sparse_grid(self):
        """Test diagnostics for KPOINTS with very sparse grid."""
        provider = DiagnosticsProvider()

        content = """Automatic
0
Gamma
1 1 1
0 0 0
"""
        diagnostics = provider.get_diagnostics(content, "file:///test/KPOINTS")

        # Should have warning about sparse grid
        assert any("very sparse" in d.message.lower() for d in diagnostics)

    def test_kpoints_weights_not_sum_to_one(self):
        """Test diagnostics for KPOINTS with weights not summing to 1."""
        provider = DiagnosticsProvider()

        content = """Explicit k-points
2
Reciprocal
0.0 0.0 0.0 0.3
0.5 0.5 0.5 0.3
"""
        diagnostics = provider.get_diagnostics(content, "file:///test/KPOINTS")

        # Should have information about weights sum
        assert any("sum" in d.message.lower() for d in diagnostics)

    def test_kpoints_valid_no_warnings(self):
        """Test diagnostics for valid KPOINTS returns no warnings or errors."""
        provider = DiagnosticsProvider()

        content = """Automatic
0
Gamma
4 4 4
0 0 0
"""
        diagnostics = provider.get_diagnostics(content, "file:///test/KPOINTS")

        # Should have no warnings or errors (informational hints are acceptable)
        from lsprotocol.types import DiagnosticSeverity

        non_info = [d for d in diagnostics if d.severity != DiagnosticSeverity.Information]
        assert non_info == []

    def test_kpoints_contcar_file(self):
        """Test diagnostics for CONTCAR file."""
        provider = DiagnosticsProvider()

        content = """Test System
1.0
1.0 0.0 0.0
0.0 1.0 0.0
0.0 0.0 1.0
H
1
Direct
0.5 0.5 0.5
"""
        diagnostics = provider.get_diagnostics(content, "file:///test/CONTCAR")

        # Should have no diagnostics for valid CONTCAR
        assert diagnostics == []
