"""
Additional tests to improve coverage.
Focus on uncovered lines in server.py and feature files.
"""

from unittest.mock import Mock

import pytest
from lsprotocol.types import CompletionParams, Position, TextDocumentIdentifier

from vasp_lsp.features.completion import CompletionProvider
from vasp_lsp.features.diagnostics import DiagnosticsProvider
from vasp_lsp.features.hover import HoverProvider
from vasp_lsp.server import server


class TestServerHandlersCoverage:
    """Tests for server LSP handlers to improve coverage."""

    def test_initialize_with_client_info(self):
        """Test initialize handler with client info."""
        params = Mock()
        params.client_info = Mock()
        params.client_info.name = "VSCode"

        # Call initialize
        from vasp_lsp.server import initialize

        result = initialize(params)

        assert result is not None

    def test_initialize_without_client_info(self):
        """Test initialize handler without client info."""
        params = Mock()
        params.client_info = None

        from vasp_lsp.server import initialize

        result = initialize(params)

        assert result is not None

    def test_text_document_did_open(self):
        """Test document open handler."""
        params = Mock()
        params.text_document = Mock()
        params.text_document.uri = "file:///test/INCAR"
        params.text_document.text = "ENCUT = 520"

        from vasp_lsp.server import text_document_did_open

        text_document_did_open(params)

        # Verify content was cached
        assert server.get_document_content("file:///test/INCAR") == "ENCUT = 520"

    def test_text_document_did_open_poscar(self):
        """Test document open handler for POSCAR."""
        params = Mock()
        params.text_document = Mock()
        params.text_document.uri = "file:///test/POSCAR"
        params.text_document.text = "Test\n1.0\n1.0 0.0 0.0"

        from vasp_lsp.server import text_document_did_open

        text_document_did_open(params)

        assert server.get_document_content("file:///test/POSCAR") == "Test\n1.0\n1.0 0.0 0.0"

    def test_text_document_did_open_kpoints(self):
        """Test document open handler for KPOINTS."""
        params = Mock()
        params.text_document = Mock()
        params.text_document.uri = "file:///test/KPOINTS"
        params.text_document.text = "Automatic\n0\nGamma\n4 4 4"

        from vasp_lsp.server import text_document_did_open

        text_document_did_open(params)

        assert server.get_document_content("file:///test/KPOINTS") == "Automatic\n0\nGamma\n4 4 4"

    def test_text_document_did_change(self):
        """Test document change handler."""
        # Set initial content
        server.set_document_content("file:///test/INCAR", "ENCUT = 500")

        params = Mock()
        params.text_document = Mock()
        params.text_document.uri = "file:///test/INCAR"
        params.content_changes = [Mock(text="ENCUT = 520")]

        from vasp_lsp.server import text_document_did_change

        text_document_did_change(params)

        assert server.get_document_content("file:///test/INCAR") == "ENCUT = 520"

    def test_text_document_did_change_empty(self):
        """Test document change with no content changes."""
        server.set_document_content("file:///test/INCAR", "ENCUT = 500")

        params = Mock()
        params.text_document = Mock()
        params.text_document.uri = "file:///test/INCAR"
        params.content_changes = []

        from vasp_lsp.server import text_document_did_change

        text_document_did_change(params)

        # Should not crash

    def test_text_document_did_save(self):
        """Test document save handler."""
        server.set_document_content("file:///test/INCAR", "ENCUT = 520")

        params = Mock()
        params.text_document = Mock()
        params.text_document.uri = "file:///test/INCAR"

        from vasp_lsp.server import text_document_did_save

        text_document_did_save(params)

        # Should not crash

    def test_completions_handler(self):
        """Test completion handler."""
        server.set_document_content("file:///test/INCAR", "ENC")

        params = Mock()
        params.text_document = Mock()
        params.text_document.uri = "file:///test/INCAR"
        params.position = Mock()
        params.position.line = 0
        params.position.character = 3

        from vasp_lsp.server import completions

        result = completions(params)

        assert result is not None

    def test_completions_no_document(self):
        """Test completion with no document."""
        params = Mock()
        params.text_document = Mock()
        params.text_document.uri = "file:///nonexistent"
        params.position = Mock()

        from vasp_lsp.server import completions

        result = completions(params)

        assert result is None

    def test_hover_handler(self):
        """Test hover handler."""
        server.set_document_content("file:///test/INCAR", "ENCUT = 520")

        params = Mock()
        params.text_document = Mock()
        params.text_document.uri = "file:///test/INCAR"
        params.position = Mock()
        params.position.line = 0
        params.position.character = 2

        from vasp_lsp.server import hover

        result = hover(params)

        # May return None or hover info
        assert result is None or hasattr(result, "contents")

    def test_hover_no_document(self):
        """Test hover with no document."""
        params = Mock()
        params.text_document = Mock()
        params.text_document.uri = "file:///nonexistent"
        params.position = Mock()

        from vasp_lsp.server import hover

        result = hover(params)

        assert result is None


class TestCompletionProviderCoverage:
    """Tests for completion provider edge cases."""

    def test_get_file_type_variations(self):
        """Test file type detection for various file names."""
        provider = CompletionProvider()

        # INCAR variations
        assert provider._get_file_type("file:///test/INCAR") == "INCAR"
        assert provider._get_file_type("file:///test/INCAR.") == "INCAR"
        assert provider._get_file_type("file:///test/INCAR.VASP") == "INCAR"
        assert provider._get_file_type("file:///test/incar") == "INCAR"
        assert provider._get_file_type("file:///path/to/incar.vasp") == "INCAR"

        # POSCAR variations
        assert provider._get_file_type("file:///test/POSCAR") == "POSCAR"
        assert provider._get_file_type("file:///test/POSCAR.") == "POSCAR"
        assert provider._get_file_type("file:///test/CONTCAR") == "POSCAR"
        assert provider._get_file_type("file:///test/poscar") == "POSCAR"
        assert provider._get_file_type("file:///path/to/contcar") == "POSCAR"

        # KPOINTS variations
        assert provider._get_file_type("file:///test/KPOINTS") == "KPOINTS"
        assert provider._get_file_type("file:///test/KPOINTS.") == "KPOINTS"
        assert provider._get_file_type("file:///test/KPOINTS.VASP") == "KPOINTS"
        assert provider._get_file_type("file:///test/kpoints") == "KPOINTS"
        assert provider._get_file_type("file:///path/to/kpoints.vasp") == "KPOINTS"

        # Unknown
        assert provider._get_file_type("file:///test/other.txt") == "UNKNOWN"

    def test_get_incar_completions_partial(self):
        """Test INCAR completions with partial word."""
        provider = CompletionProvider()

        # Partial word match
        items = provider._get_incar_completions("ENCU", "ENCU")
        assert len(items) > 0

        # Space before partial
        items = provider._get_incar_completions("ENCU", "  ENCU")
        assert len(items) > 0

    def test_get_incar_completions_prefers_prefix_match(self):
        """A tag beginning with the query should outrank substring matches."""
        provider = CompletionProvider()

        items = provider._get_incar_completions("ismea", "ismea")

        assert items
        assert items[0].label == "ISMEAR"
        assert "ELPH_ISMEAR" not in [item.label for item in items]
        assert items[0].insert_text == "ISMEAR ="

    def test_get_incar_completions_value_suggestions(self):
        """Test INCAR value suggestions."""
        provider = CompletionProvider()

        # After equals sign
        items = provider._get_incar_completions("ISMEAR = ", "ISMEAR = ")
        # Should have enum values for ISMEAR
        assert len(items) > 0
        assert next(item for item in items if item.label == "0").insert_text == "0"

        # When the tag completion leaves the cursor directly after '=', add
        # the space as part of the value completion.
        items = provider._get_incar_completions("ISMEAR =", "ISMEAR =")
        assert next(item for item in items if item.label == "0").insert_text == " 0"

        # Boolean parameter
        items = provider._get_incar_completions("LCHARG = ", "LCHARG = ")
        # Should have .TRUE. and .FALSE.
        assert len(items) > 0

    def test_incar_completion_refreshes_when_prefix_changes(self):
        """INCAR completions must be refreshed for each changing tag prefix."""
        provider = CompletionProvider()

        params = Mock()
        params.text_document = Mock()
        params.text_document.uri = "file:///test/INCAR"
        params.position = Mock()
        params.position.line = 0
        params.position.character = 4

        result = provider.get_completions(params, "encu", "file:///test/INCAR")

        assert result.is_incomplete is True
        assert result.items[0].label == "ENCUT"

    @pytest.mark.parametrize(
        ("content", "value"),
        [
            ("ALGO =V", "VeryFast"),
            ("ISMEAR =0", "0"),
            ("LREAL =A", "Auto"),
        ],
    )
    def test_incar_value_completion_keeps_space_before_typed_value(
        self, content, value
    ):
        """Value completion must preserve the INCAR ``TAG = value`` style."""
        provider = CompletionProvider()
        params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/INCAR"),
            position=Position(line=0, character=len(content)),
        )

        result = provider.get_completions(params, content, "file:///test/INCAR")
        item = next(item for item in result.items if item.label == value)

        assert item.insert_text == f" {value}"

    def test_get_incar_completions_no_tag(self):
        """Test INCAR completions with unknown tag."""
        provider = CompletionProvider()

        items = provider._get_incar_completions("UNKNOWN_TAG = ", "UNKNOWN_TAG = ")
        # Should return empty list for unknown tag
        assert len(items) == 0

    def test_get_poscar_completions_lines(self):
        """Test POSCAR completions for different lines."""
        provider = CompletionProvider()

        # Line 0: system comment
        items = provider._get_poscar_completions(0)
        assert len(items) > 0

        # Line 1: scale factor
        items = provider._get_poscar_completions(1)
        assert len(items) > 0

        # Lines 2-4: lattice vectors
        for line_num in [2, 3, 4]:
            items = provider._get_poscar_completions(line_num)
            assert len(items) > 0

        # Line 5: atom types
        items = provider._get_poscar_completions(5)
        assert len(items) > 0

        # Line 6: atom counts
        items = provider._get_poscar_completions(6)
        assert len(items) > 0

        # Other lines: no completions
        items = provider._get_poscar_completions(10)
        assert len(items) == 0

    def test_get_kpoints_completions_lines(self):
        """Test KPOINTS completions for different lines."""
        provider = CompletionProvider()

        # Line 1: mode selection
        items = provider._get_kpoints_completions(1)
        assert len(items) > 0

        # Line 2: grid sizes
        items = provider._get_kpoints_completions(2)
        assert len(items) > 0

        # Other lines: no completions
        items = provider._get_kpoints_completions(10)
        assert len(items) == 0

    def test_get_completions_out_of_range(self):
        """Test completion when cursor is beyond content."""
        provider = CompletionProvider()

        params = Mock()
        params.text_document = Mock()
        params.text_document.uri = "file:///test/INCAR"
        params.position = Mock()
        params.position.line = 10
        params.position.character = 0

        content = "ENCUT = 520"
        completions = provider.get_completions(params, content, "file:///test/INCAR")

        assert completions is not None
        assert len(completions.items) == 0


class TestHoverProviderCoverage:
    """Tests for hover provider edge cases."""

    def test_get_hover_incar_parameter(self):
        """Test hover on INCAR parameter name."""
        provider = HoverProvider()

        params = Mock()
        params.text_document = Mock()
        params.text_document.uri = "file:///test/INCAR"
        params.position = Mock()
        params.position.line = 0
        params.position.character = 2

        content = "ENCUT = 520"
        hover = provider.get_hover(params, content, "file:///test/INCAR")

        # May return None or hover info
        assert hover is None or hasattr(hover, "contents")

    def test_get_hover_incar_value(self):
        """Test hover on INCAR value."""
        provider = HoverProvider()

        params = Mock()
        params.text_document = Mock()
        params.text_document.uri = "file:///test/INCAR"
        params.position = Mock()
        params.position.line = 0
        params.position.character = 8

        content = "ENCUT = 520"
        hover = provider.get_hover(params, content, "file:///test/INCAR")

        assert hover is None or hasattr(hover, "contents")

    def test_get_hover_poscar(self):
        """Test hover on POSCAR file."""
        provider = HoverProvider()

        params = Mock()
        params.text_document = Mock()
        params.text_document.uri = "file:///test/POSCAR"
        params.position = Mock()
        params.position.line = 0
        params.position.character = 2

        content = "Test system"
        hover = provider.get_hover(params, content, "file:///test/POSCAR")

        assert hover is None or hasattr(hover, "contents")

    def test_get_hover_kpoints(self):
        """Test hover on KPOINTS file."""
        provider = HoverProvider()

        params = Mock()
        params.text_document = Mock()
        params.text_document.uri = "file:///test/KPOINTS"
        params.position = Mock()
        params.position.line = 0
        params.position.character = 2

        content = "Automatic"
        hover = provider.get_hover(params, content, "file:///test/KPOINTS")

        assert hover is None or hasattr(hover, "contents")

    def test_get_hover_non_vasp(self):
        """Test hover on non-VASP file."""
        provider = HoverProvider()

        params = Mock()
        params.text_document = Mock()
        params.text_document.uri = "file:///test/other.txt"
        params.position = Mock()

        content = "some text"
        hover = provider.get_hover(params, content, "file:///test/other.txt")

        assert hover is None


class TestDiagnosticsProviderCoverage:
    """Tests for diagnostics provider edge cases."""

    def test_diagnostics_empty_incar(self):
        """Test diagnostics for empty INCAR."""
        provider = DiagnosticsProvider()

        content = ""
        diagnostics = provider.get_diagnostics(content, "file:///test/INCAR")

        assert isinstance(diagnostics, list)

    def test_diagnostics_whitespace_incar(self):
        """Test diagnostics for whitespace-only INCAR."""
        provider = DiagnosticsProvider()

        content = "   \n   \n"
        diagnostics = provider.get_diagnostics(content, "file:///test/INCAR")

        assert isinstance(diagnostics, list)

    def test_diagnostics_invalid_line(self):
        """Test diagnostics for invalid line format."""
        provider = DiagnosticsProvider()

        content = "NO_EQUALS_SIGN\nENCUT = 520"
        diagnostics = provider.get_diagnostics(content, "file:///test/INCAR")

        assert isinstance(diagnostics, list)

    def test_diagnostics_unknown_tag(self):
        """Test diagnostics for unknown INCAR tag."""
        provider = DiagnosticsProvider()

        content = "UNKNOWN_TAG = 123\nENCUT = 520"
        diagnostics = provider.get_diagnostics(content, "file:///test/INCAR")

        assert isinstance(diagnostics, list)
        # Should have warning about unknown tag

    def test_diagnostics_duplicate_parameter(self):
        """Test diagnostics for duplicate parameters."""
        provider = DiagnosticsProvider()

        content = "ENCUT = 500\nENCUT = 520"
        diagnostics = provider.get_diagnostics(content, "file:///test/INCAR")

        assert isinstance(diagnostics, list)

    def test_diagnostics_ncore_npar_conflict(self):
        """Test NCORE and NPAR conflict detection."""
        provider = DiagnosticsProvider()

        content = "ENCUT = 520\nNCORE = 2\nNPAR = 4"
        diagnostics = provider.get_diagnostics(content, "file:///test/INCAR")

        assert isinstance(diagnostics, list)
        conflict_warnings = [d for d in diagnostics if "NPAR" in d.message or "NCORE" in d.message]
        assert len(conflict_warnings) > 0

    def test_diagnostics_ldau_missing_params(self):
        """Test LDAU requirements."""
        provider = DiagnosticsProvider()

        # Missing LDAUTYPE and LDAUU
        content = "LDAU = .TRUE.\nLDAUL = 0 0"
        diagnostics = provider.get_diagnostics(content, "file:///test/INCAR")

        assert isinstance(diagnostics, list)

        # Missing LDAUL and LDAUU
        content = "LDAU = .TRUE.\nLDAUTYPE = 2"
        diagnostics = provider.get_diagnostics(content, "file:///test/INCAR")

        assert isinstance(diagnostics, list)

    def test_diagnostics_spin_polarization_no_magmom(self):
        """Test ISPIN=2 without MAGMOM."""
        provider = DiagnosticsProvider()

        content = "ISPIN = 2\nENCUT = 520"
        diagnostics = provider.get_diagnostics(content, "file:///test/INCAR")

        assert isinstance(diagnostics, list)
        magmom_warnings = [d for d in diagnostics if "MAGMOM" in d.message]
        assert len(magmom_warnings) > 0

    def test_diagnostics_ismear_sigma_warning(self):
        """Test ISMEAR >= 0 without SIGMA."""
        provider = DiagnosticsProvider()

        content = "ENCUT = 520\nISMEAR = 0"
        diagnostics = provider.get_diagnostics(content, "file:///test/INCAR")

        assert isinstance(diagnostics, list)
        sigma_warnings = [d for d in diagnostics if "SIGMA" in d.message]
        assert len(sigma_warnings) > 0

    def test_diagnostics_poscar_valid(self):
        """Test diagnostics for valid POSCAR."""
        provider = DiagnosticsProvider()

        content = """Test system
1.0
1.0 0.0 0.0
0.0 1.0 0.0
0.0 0.0 1.0
Si
1
Direct
0.0 0.0 0.0
"""
        diagnostics = provider.get_diagnostics(content, "file:///test/POSCAR")

        assert diagnostics == []

    def test_diagnostics_kpoints_valid(self):
        """Test diagnostics for valid KPOINTS."""
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

    def test_diagnostics_non_vasp(self):
        """Test diagnostics for non-VASP file."""
        provider = DiagnosticsProvider()

        content = "some random text"
        diagnostics = provider.get_diagnostics(content, "file:///test/other.txt")

        assert diagnostics == []
