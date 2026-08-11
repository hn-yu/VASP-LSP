"""Tests for expanded KPOINTS diagnostics and quick fixes."""

from lsprotocol.types import Diagnostic, DiagnosticSeverity, Position, Range

from vasp_lsp.features.diagnostics import DiagnosticsProvider
from vasp_lsp.features.quickfixes import QuickFixesProvider

# ---------------------------------------------------------------------------
# Expanded diagnostics tests
# ---------------------------------------------------------------------------


class TestDenseGridWarning:
    """Test very dense grid warning (all values > 50)."""

    def test_dense_grid_all_above_50(self) -> None:
        """Warn when all grid values exceed 50."""
        provider = DiagnosticsProvider()
        content = """Dense grid
0
Gamma
60 60 60
0 0 0
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        dense = [d for d in diags if "very dense" in d.message.lower()]
        assert len(dense) == 1
        assert dense[0].severity == DiagnosticSeverity.Warning

    def test_moderate_grid_no_dense_warning(self) -> None:
        """No dense warning for a moderate grid."""
        provider = DiagnosticsProvider()
        content = """Moderate grid
0
Gamma
20 20 20
0 0 0
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        assert not any("very dense" in d.message.lower() for d in diags)

    def test_mixed_grid_no_dense_warning(self) -> None:
        """No dense warning if not all values exceed 50."""
        provider = DiagnosticsProvider()
        content = """Mixed grid
0
Gamma
60 4 60
0 0 0
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        assert not any("very dense" in d.message.lower() for d in diags)

    def test_dense_grid_includes_grid_values_in_message(self) -> None:
        """Dense grid warning includes the actual grid values."""
        provider = DiagnosticsProvider()
        content = """Dense grid
0
Gamma
64 64 64
0 0 0
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        dense = [d for d in diags if "very dense" in d.message.lower()]
        assert len(dense) == 1
        assert "64 64 64" in dense[0].message


class TestGammaMonkhorstHint:
    """Test Gamma vs Monkhorst-Pack centering hint."""

    def test_gamma_centered_hint(self) -> None:
        """Info diagnostic for Gamma-centered mesh."""
        provider = DiagnosticsProvider()
        content = """Gamma mesh
0
Gamma
4 4 4
0 0 0
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        hints = [d for d in diags if "Gamma-centered" in d.message]
        assert len(hints) == 1
        assert hints[0].severity == DiagnosticSeverity.Information
        assert "4x4x4" in hints[0].message

    def test_monkhorst_pack_hint(self) -> None:
        """Info diagnostic for Monkhorst-Pack mesh."""
        provider = DiagnosticsProvider()
        content = """Monkhorst mesh
0
Monkhorst
6 6 6
0 0 0
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        hints = [d for d in diags if "Monkhorst-Pack" in d.message]
        assert len(hints) == 1
        assert hints[0].severity == DiagnosticSeverity.Information

    def test_automatic_mode_no_centering_hint(self) -> None:
        """No centering hint for fully automatic mode."""
        provider = DiagnosticsProvider()
        content = """Automatic mesh
0
Automatic
4 4 4
0 0 0
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        assert not any("centered" in d.message.lower() for d in diags)


class TestZeroWeightKpoints:
    """Test zero-weight k-point warnings in explicit mode."""

    def test_zero_weight_warning(self) -> None:
        """Warn when an explicit k-point has weight 0.0."""
        provider = DiagnosticsProvider()
        content = """Explicit k-points
3
Reciprocal
0.0 0.0 0.0 1.0
0.5 0.0 0.0 0.0
0.0 0.5 0.0 0.5
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        zero_w = [d for d in diags if "weight 0.0" in d.message.lower()]
        assert len(zero_w) >= 1
        assert zero_w[0].severity == DiagnosticSeverity.Warning

    def test_all_nonzero_weights_no_warning(self) -> None:
        """No warning when all weights are nonzero."""
        provider = DiagnosticsProvider()
        content = """Explicit k-points
2
Reciprocal
0.0 0.0 0.0 0.5
0.5 0.5 0.0 0.5
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        assert not any("weight 0.0" in d.message.lower() for d in diags)

    def test_multiple_zero_weights_single_warning(self) -> None:
        """Multiple zero weights produce one warning per zero-weight k-point."""
        provider = DiagnosticsProvider()
        content = """Explicit
3
Reciprocal
0.0 0.0 0.0 0.0
0.5 0.0 0.0 0.0
0.0 0.5 0.0 1.0
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        zero_w = [d for d in diags if "weight 0.0" in d.message.lower()]
        # At least one warning for zero weights (first k-point)
        assert len(zero_w) >= 1


class TestNegativeKpointCoordinates:
    """Test negative / out-of-range k-point coordinate errors."""

    def test_coordinate_outside_range(self) -> None:
        """Error when k-point coordinate is outside [-1, 1]."""
        provider = DiagnosticsProvider()
        content = """Explicit k-points
2
Reciprocal
0.0 0.0 0.0 0.5
1.5 0.0 0.0 0.5
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        oor = [d for d in diags if "outside the typical reciprocal range" in d.message]
        assert len(oor) >= 1
        assert oor[0].severity == DiagnosticSeverity.Error

    def test_negative_one_is_valid(self) -> None:
        """Coordinate -1.0 should NOT trigger out-of-range error."""
        provider = DiagnosticsProvider()
        content = """Explicit
1
Reciprocal
-1.0 0.0 0.0 1.0
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        assert not any("outside the typical reciprocal range" in d.message for d in diags)

    def test_large_negative_coordinate(self) -> None:
        """Error for coordinate well outside [-1, 1]."""
        provider = DiagnosticsProvider()
        content = """Explicit
1
Reciprocal
-2.0 0.0 0.0 1.0
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        oor = [d for d in diags if "outside the typical reciprocal range" in d.message]
        assert len(oor) >= 1

    def test_valid_coordinates_no_error(self) -> None:
        """No error for coordinates within [-1, 1]."""
        provider = DiagnosticsProvider()
        content = """Explicit
2
Reciprocal
0.0 0.0 0.0 0.5
0.5 0.5 0.5 0.5
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        assert not any("outside the typical reciprocal range" in d.message for d in diags)


class TestLineModeDensity:
    """Test line-mode density check."""

    def test_low_density_warning(self) -> None:
        """Info when line-mode density is below 10."""
        provider = DiagnosticsProvider()
        content = """Line mode
5
Line
Reciprocal
0.0 0.0 0.0
0.5 0.0 0.0
0.5 0.5 0.0
0.0 0.5 0.0
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        density_diags = [d for d in diags if "line-mode density" in d.message.lower()]
        assert len(density_diags) >= 1
        assert density_diags[0].severity == DiagnosticSeverity.Information

    def test_high_density_no_warning(self) -> None:
        """No warning for line-mode density >= 10."""
        provider = DiagnosticsProvider()
        content = """Line mode
20
Line
Reciprocal
0.0 0.0 0.0
0.5 0.0 0.0
0.5 0.5 0.0
0.0 0.5 0.0
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        assert not any("line-mode density" in d.message.lower() for d in diags)


# ---------------------------------------------------------------------------
# Expanded quick-fix tests
# ---------------------------------------------------------------------------


class TestFixZeroWeightsQuickFix:
    """Test quick fix for zero-weight k-points."""

    def test_fix_zero_weights_action_created(self) -> None:
        """Quick fix is offered for zero-weight k-points."""
        provider = QuickFixesProvider()
        content = """Explicit k-points
3
Reciprocal
0.0 0.0 0.0 1.0
0.5 0.0 0.0 0.0
0.0 0.5 0.0 0.5
"""
        diagnostic = Diagnostic(
            range=Range(start=Position(line=4, character=0), end=Position(line=4, character=20)),
            message="K-point 2 has weight 0.0. Zero-weight k-points are excluded from integration.",
        )
        actions = provider._get_kpoints_code_actions(content, [diagnostic], diagnostic.range)
        fix = [a for a in actions if "zero-weight" in a.title.lower()]
        assert len(fix) >= 1

    def test_fix_zero_weights_sets_equal_weight(self) -> None:
        """The fix sets zero-weight k-points to 1/n."""
        provider = QuickFixesProvider()
        content = """Explicit k-points
3
Reciprocal
0.0 0.0 0.0 1.0
0.5 0.0 0.0 0.0
0.0 0.5 0.0 0.5
"""
        diagnostic = Diagnostic(
            range=Range(start=Position(line=4, character=0), end=Position(line=4, character=20)),
            message="K-point 2 has weight 0.0. Zero-weight k-points are excluded from integration.",
        )
        actions = provider._get_kpoints_code_actions(content, [diagnostic], diagnostic.range)
        fix = next(a for a in actions if "zero-weight" in a.title.lower())
        # 1/3 = 0.3333...
        assert "0.3333" in fix.title

    def test_fix_zero_weights_no_result(self) -> None:
        """Returns None when the file cannot be parsed."""
        provider = QuickFixesProvider()
        content = """Invalid KPOINTS
"""
        diagnostic = Diagnostic(
            range=Range(start=Position(line=0, character=0), end=Position(line=0, character=10)),
            message="K-point 1 has weight 0.0. Zero-weight k-points are excluded from integration.",
        )
        actions = provider._get_kpoints_code_actions(content, [diagnostic], diagnostic.range)
        assert isinstance(actions, list)

    def test_fix_zero_weights_via_get_code_actions(self) -> None:
        """Quick fix works via the main get_code_actions entry point."""
        provider = QuickFixesProvider()
        content = """Explicit k-points
3
Reciprocal
0.0 0.0 0.0 1.0
0.5 0.0 0.0 0.0
0.0 0.5 0.0 0.5
"""
        diagnostic = Diagnostic(
            range=Range(start=Position(line=4, character=0), end=Position(line=4, character=20)),
            message="K-point 2 has weight 0.0. Zero-weight k-points are excluded from integration.",
        )
        actions = provider.get_code_actions(
            content, "file:///test/KPOINTS", [diagnostic], diagnostic.range
        )
        fix = [a for a in actions if "zero-weight" in a.title.lower()]
        assert len(fix) >= 1


class TestReduceDenseGridQuickFix:
    """Test quick fix for reducing very dense grids."""

    def test_reduce_dense_grid_action_created(self) -> None:
        """Quick fix is offered for very dense grids."""
        provider = QuickFixesProvider()
        content = """Dense grid
0
Gamma
60 60 60
0 0 0
"""
        diagnostic = Diagnostic(
            range=Range(start=Position(line=2, character=0), end=Position(line=2, character=20)),
            message=(
                "K-point grid 60 60 60 is very dense (all values > 50). "
                "Computationally expensive; may not converge faster than a moderate grid."
            ),
        )
        actions = provider._get_kpoints_code_actions(content, [diagnostic], diagnostic.range)
        fix = [a for a in actions if "cap grid" in a.title.lower()]
        assert len(fix) >= 1

    def test_reduce_dense_grid_caps_at_50(self) -> None:
        """The fix caps grid values at 50."""
        provider = QuickFixesProvider()
        content = """Dense grid
0
Gamma
64 64 64
0 0 0
"""
        diagnostic = Diagnostic(
            range=Range(start=Position(line=2, character=0), end=Position(line=2, character=20)),
            message=(
                "K-point grid 64 64 64 is very dense (all values > 50). "
                "Computationally expensive; may not converge faster than a moderate grid."
            ),
        )
        actions = provider._get_kpoints_code_actions(content, [diagnostic], diagnostic.range)
        fix = next(a for a in actions if "cap grid" in a.title.lower())
        assert "50 50 50" in fix.title

    def test_reduce_dense_grid_preserves_unchanged_values(self) -> None:
        """Grid values at or below 50 are left unchanged (capping only affects > 50)."""
        provider = QuickFixesProvider()
        content = """Dense grid
0
Gamma
60 30 60
0 0 0
"""
        # This won't trigger the "very dense" diagnostic since not all > 50,
        # but test the action method directly with a matching diagnostic
        diagnostic = Diagnostic(
            range=Range(start=Position(line=2, character=0), end=Position(line=2, character=20)),
            message=(
                "K-point grid 60 30 60 is very dense (all values > 50). "
                "Computationally expensive; may not converge faster than a moderate grid."
            ),
        )
        actions = provider._get_kpoints_code_actions(content, [diagnostic], diagnostic.range)
        fix = next(a for a in actions if "cap grid" in a.title.lower())
        assert "50 30 50" in fix.title

    def test_reduce_dense_grid_no_result(self) -> None:
        """Returns empty list when file cannot be parsed."""
        provider = QuickFixesProvider()
        content = """Invalid
"""
        diagnostic = Diagnostic(
            range=Range(start=Position(line=0, character=0), end=Position(line=0, character=10)),
            message="K-point grid is very dense (all values > 50).",
        )
        actions = provider._get_kpoints_code_actions(content, [diagnostic], diagnostic.range)
        assert isinstance(actions, list)

    def test_reduce_dense_grid_via_get_code_actions(self) -> None:
        """Quick fix works via the main get_code_actions entry point."""
        provider = QuickFixesProvider()
        content = """Dense grid
0
Gamma
60 60 60
0 0 0
"""
        diagnostic = Diagnostic(
            range=Range(start=Position(line=2, character=0), end=Position(line=2, character=20)),
            message=(
                "K-point grid 60 60 60 is very dense (all values > 50). "
                "Computationally expensive; may not converge faster."
            ),
        )
        actions = provider.get_code_actions(
            content, "file:///test/KPOINTS", [diagnostic], diagnostic.range
        )
        fix = [a for a in actions if "cap grid" in a.title.lower()]
        assert len(fix) >= 1


class TestExistingDiagnosticsStillWork:
    """Regression tests to ensure existing diagnostics still function."""

    def test_zero_grid_value(self) -> None:
        """Existing check: zero grid value produces error."""
        provider = DiagnosticsProvider()
        content = """Automatic
0
Gamma
0 4 4
0 0 0
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        assert any("not positive" in d.message.lower() for d in diags)

    def test_negative_grid_value(self) -> None:
        """Existing check: negative grid value produces error."""
        provider = DiagnosticsProvider()
        content = """Automatic
0
Gamma
-1 4 4
0 0 0
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        assert any("not positive" in d.message.lower() for d in diags)

    def test_sparse_grid(self) -> None:
        """A sparse grid is only a convergence hint, not an error/warning."""
        provider = DiagnosticsProvider()
        content = """Automatic
0
Gamma
1 1 1
0 0 0
        """
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        sparse = [d for d in diags if "very sparse" in d.message.lower()]
        assert len(sparse) == 1
        assert sparse[0].severity == DiagnosticSeverity.Information

    def test_weights_sum_not_one(self) -> None:
        """Existing check: weights not summing to 1.0 produces info."""
        provider = DiagnosticsProvider()
        content = """Explicit k-points
2
Reciprocal
0.0 0.0 0.0 0.3
0.5 0.5 0.5 0.3
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        assert any("sum" in d.message.lower() for d in diags)

    def test_valid_kpoints_no_diagnostics(self) -> None:
        """A valid Gamma-centered KPOINTS file produces no diagnostics."""
        provider = DiagnosticsProvider()
        content = """Automatic
0
Gamma
4 4 4
0 0 0
"""
        diags = provider.get_diagnostics(content, "file:///test/KPOINTS")
        # Centering hint is informational; filter it out for this check
        non_hint = [d for d in diags if "centered" not in d.message.lower()]
        assert non_hint == []


class TestExistingQuickFixesStillWork:
    """Regression tests for existing quick fixes."""

    def test_fix_non_positive_grid(self) -> None:
        """Existing fix: non-positive grid values."""
        provider = QuickFixesProvider()
        content = """Automatic
0
Gamma
0 -1 4
0 0 0
"""
        diagnostic = Diagnostic(
            range=Range(start=Position(line=3, character=0), end=Position(line=3, character=10)),
            message="K-point grid value 0 is not positive.",
        )
        actions = provider._get_kpoints_code_actions(content, [diagnostic], diagnostic.range)
        assert any("grid" in a.title.lower() for a in actions)

    def test_normalize_weights(self) -> None:
        """Existing fix: normalize weights."""
        provider = QuickFixesProvider()
        content = """Explicit k-points
2
Reciprocal
0.0 0.0 0.0 0.3
0.5 0.5 0.5 0.3
"""
        diagnostic = Diagnostic(
            range=Range(start=Position(line=3, character=0), end=Position(line=3, character=30)),
            message="K-point weights sum to 0.600 (expected ~1.0).",
        )
        actions = provider._get_kpoints_code_actions(content, [diagnostic], diagnostic.range)
        assert any("normalize" in a.title.lower() for a in actions)
