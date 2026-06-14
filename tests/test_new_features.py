"""Tests for new LSP features added by issues #19, #22, #23, #24, #27."""

from lsprotocol.types import (
    Position,
    Range,
    SymbolKind,
)

from vasp_lsp.features.formatting import FormattingProvider
from vasp_lsp.features.navigation import DocumentSymbolsProvider
from vasp_lsp.features.quickfixes import QuickFixesProvider

# ---------------------------------------------------------------------------
# #19: Range formatting
# ---------------------------------------------------------------------------


class TestRangeFormatting:
    """Range formatting for INCAR files."""

    def setup_method(self):
        self.provider = FormattingProvider()

    def test_range_format_incar_uppercase(self):
        content = "encut = 400\nismear = 0\nsigma = 0.2"
        rng = Range(start=Position(line=0, character=0), end=Position(line=0, character=100))
        edits = self.provider.format_range(content, "file://INCAR", rng)
        assert len(edits) == 1
        assert edits[0].new_text == "ENCUT = 400"

    def test_range_format_incar_preserves_others(self):
        content = "encut = 400\nismear = 0\nsigma = 0.2"
        rng = Range(start=Position(line=1, character=0), end=Position(line=1, character=100))
        edits = self.provider.format_range(content, "file://INCAR", rng)
        assert len(edits) == 1
        assert edits[0].new_text == "ISMEAR = 0"

    def test_range_format_skips_comments(self):
        content = "# comment\nencut = 400"
        rng = Range(start=Position(line=0, character=0), end=Position(line=1, character=100))
        edits = self.provider.format_range(content, "file://INCAR", rng)
        assert len(edits) == 1
        assert edits[0].new_text == "ENCUT = 400"

    def test_range_format_skips_non_inc(self):
        content = "encut = 400"
        rng = Range(start=Position(line=0, character=0), end=Position(line=0, character=11))
        edits = self.provider.format_range(content, "file://POSCAR", rng)
        assert edits == []

    def test_range_format_strips_trailing_comment(self):
        content = "encut = 400 # cutoff"
        rng = Range(start=Position(line=0, character=0), end=Position(line=0, character=100))
        edits = self.provider.format_range(content, "file://INCAR", rng)
        assert len(edits) == 1
        assert edits[0].new_text == "ENCUT = 400"

    def test_range_format_empty_content(self):
        rng = Range(start=Position(line=0, character=0), end=Position(line=0, character=0))
        edits = self.provider.format_range("", "file://INCAR", rng)
        assert edits == []

    def test_range_format_no_change_needed(self):
        content = "ENCUT = 400"
        rng = Range(start=Position(line=0, character=0), end=Position(line=0, character=11))
        edits = self.provider.format_range(content, "file://INCAR", rng)
        assert edits == []


# ---------------------------------------------------------------------------
# #23: Definition, references
# ---------------------------------------------------------------------------


class TestNavigationDefinition:
    """Go-to-definition for INCAR tags."""

    def setup_method(self):
        self.provider = DocumentSymbolsProvider()

    def test_definition_finds_first_occurrence(self):
        content = "ENCUT = 400\nISMEAR = 0\nENCUT = 500"
        pos = Position(line=2, character=1)
        loc = self.provider.get_definition(content, "file://INCAR", pos)
        assert loc is not None
        assert loc.range.start.line == 0

    def test_definition_returns_none_for_unknown_file(self):
        content = "ENCUT = 400"
        pos = Position(line=0, character=1)
        loc = self.provider.get_definition(content, "file://POSCAR", pos)
        assert loc is None

    def test_definition_returns_none_for_comment(self):
        content = "# ENCUT = 400"
        pos = Position(line=0, character=2)
        loc = self.provider.get_definition(content, "file://INCAR", pos)
        assert loc is None

    def test_references_finds_all_occurrences(self):
        content = "ENCUT = 400\nISMEAR = 0\nENCUT = 500"
        pos = Position(line=0, character=1)
        refs = self.provider.get_references(content, "file://INCAR", pos)
        assert len(refs) == 2
        assert refs[0].range.start.line == 0
        assert refs[1].range.start.line == 2

    def test_references_empty_for_non_inc(self):
        content = "ENCUT = 400"
        pos = Position(line=0, character=1)
        refs = self.provider.get_references(content, "file://POSCAR", pos)
        assert refs == []


# ---------------------------------------------------------------------------
# #24: prepareRename
# ---------------------------------------------------------------------------


class TestPrepareRename:
    """prepareRename for INCAR tags."""

    def setup_method(self):
        self.provider = DocumentSymbolsProvider()

    def test_prepare_rename_returns_range(self):
        content = "ENCUT = 400"
        pos = Position(line=0, character=1)
        rng = self.provider.prepare_rename(content, "file://INCAR", pos)
        assert rng is not None
        assert rng.start.line == 0
        assert rng.start.character == 0
        assert rng.end.character == 5

    def test_prepare_rename_rejects_non_inc(self):
        content = "ENCUT = 400"
        pos = Position(line=0, character=1)
        rng = self.provider.prepare_rename(content, "file://POSCAR", pos)
        assert rng is None

    def test_prepare_rename_rejects_cursor_not_on_tag(self):
        content = "ENCUT = 400"
        pos = Position(line=0, character=8)
        rng = self.provider.prepare_rename(content, "file://INCAR", pos)
        assert rng is None

    def test_prepare_rename_rejects_out_of_range_line(self):
        content = "ENCUT = 400"
        pos = Position(line=5, character=0)
        rng = self.provider.prepare_rename(content, "file://INCAR", pos)
        assert rng is None


# ---------------------------------------------------------------------------
# #23/#27: workspace symbol
# ---------------------------------------------------------------------------


class TestWorkspaceSymbol:
    """workspace symbol via server handler (tested through navigation provider)."""

    def setup_method(self):
        self.provider = DocumentSymbolsProvider()

    def test_incar_symbols_filtered_by_query(self):
        content = "ENCUT = 400\nISMEAR = 0\nSIGMA = 0.2"
        symbols = self.provider.get_symbols(content, "file://INCAR")
        encut_syms = [s for s in symbols if s.name == "ENCUT"]
        assert len(encut_syms) == 1
        assert encut_syms[0].kind == SymbolKind.Property

    def test_poscar_symbols(self):
        content = "Si\n1.0\n5.43 0 0\n0 5.43 0\n0 0 5.43\nSi\n1\nDirect\n0 0 0"
        symbols = self.provider.get_symbols(content, "file://POSCAR")
        names = [s.name for s in symbols]
        assert "System Comment" in names
        assert "Scale Factor" in names

    def test_kpoints_symbols(self):
        content = "KPOINTS\n0\nGamma\n4 4 4"
        symbols = self.provider.get_symbols(content, "file://KPOINTS")
        names = [s.name for s in symbols]
        assert "Comment" in names
        assert "Mode" in names


# ---------------------------------------------------------------------------
# #22/#27: Code actions
# ---------------------------------------------------------------------------


class TestCodeActions:
    """Code actions for common VASP input errors."""

    def setup_method(self):
        self.provider = QuickFixesProvider()

    def test_typo_fix_action(self):
        from lsprotocol.types import Diagnostic, DiagnosticSeverity

        diag = Diagnostic(
            range=Range(start=Position(line=0, character=0), end=Position(line=0, character=7)),
            message="Unknown INCAR tag: ENCUTT",
            severity=DiagnosticSeverity.Error,
            source="vasp-lsp",
        )
        content = "ENCUTT = 400"
        rng = Range(start=Position(line=0, character=0), end=Position(line=0, character=12))
        actions = self.provider.get_code_actions(content, "file://INCAR", [diag], rng)
        assert len(actions) >= 1
        assert "ENCUT" in actions[0].title

    def test_add_sigma_action(self):
        from lsprotocol.types import Diagnostic, DiagnosticSeverity

        diag = Diagnostic(
            range=Range(start=Position(line=0, character=0), end=Position(line=0, character=10)),
            message="ISMEAR >= 0 should have SIGMA set.",
            severity=DiagnosticSeverity.Warning,
            source="vasp-lsp",
        )
        content = "ISMEAR = 0"
        rng = Range(start=Position(line=0, character=0), end=Position(line=0, character=10))
        actions = self.provider.get_code_actions(content, "file://INCAR", [diag], rng)
        assert len(actions) >= 1
        assert "SIGMA" in actions[0].title

    def test_remove_npar_action(self):
        from lsprotocol.types import Diagnostic, DiagnosticSeverity

        diag = Diagnostic(
            range=Range(start=Position(line=0, character=0), end=Position(line=0, character=10)),
            message="NPAR and NCORE should not be set together.",
            severity=DiagnosticSeverity.Warning,
            source="vasp-lsp",
        )
        content = "NPAR = 4"
        rng = Range(start=Position(line=0, character=0), end=Position(line=0, character=8))
        actions = self.provider.get_code_actions(content, "file://INCAR", [diag], rng)
        assert len(actions) >= 1
        assert "NPAR" in actions[0].title

    def test_add_magmom_action(self):
        from lsprotocol.types import Diagnostic, DiagnosticSeverity

        diag = Diagnostic(
            range=Range(start=Position(line=0, character=0), end=Position(line=0, character=10)),
            message="ISPIN=2 should have MAGMOM set.",
            severity=DiagnosticSeverity.Warning,
            source="vasp-lsp",
        )
        content = "ISPIN = 2"
        rng = Range(start=Position(line=0, character=0), end=Position(line=0, character=9))
        actions = self.provider.get_code_actions(content, "file://INCAR", [diag], rng)
        assert len(actions) >= 1
        assert "MAGMOM" in actions[0].title
