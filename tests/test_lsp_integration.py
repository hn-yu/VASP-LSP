"""Integration tests for VASP-LSP server through pygls protocol messages.

These tests exercise the full LSP server lifecycle: initialize, document
synchronization, diagnostics, completion, hover, formatting, and code actions.
They create fresh server instances and call handler functions directly,
validating the end-to-end data flow through the LSP layer.
"""

from typing import Dict, List, Optional
from unittest.mock import Mock

import pytest
from lsprotocol.types import (
    CodeActionContext,
    CodeActionParams,
    CompletionParams,
    DefinitionParams,
    Diagnostic,
    DiagnosticSeverity,
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    DocumentFormattingParams,
    DocumentRangeFormattingParams,
    DocumentSymbolParams,
    FormattingOptions,
    HoverParams,
    InitializeParams,
    Position,
    PrepareRenameParams,
    Range,
    ReferenceParams,
    RenameParams,
    TextDocumentContentChangeEvent_Type1,
    TextDocumentContentChangeEvent_Type2,
    TextDocumentIdentifier,
    TextDocumentItem,
    TextDocumentSyncKind,
    VersionedTextDocumentIdentifier,
    WorkspaceSymbolParams,
)

from vasp_lsp.server import (
    VASPLanguageServer,
    code_action,
    completions,
    definition,
    document_symbol,
    formatting,
    hover,
    initialize,
    prepare_rename,
    range_formatting,
    references,
    rename,
    text_document_did_change,
    text_document_did_close,
    text_document_did_open,
    text_document_did_save,
    workspace_symbol,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

INCAR_URI = "file:///workspace/INCAR"
POSCAR_URI = "file:///workspace/POSCAR"
POTCAR_URI = "file:///workspace/POTCAR"
KPOINTS_URI = "file:///workspace/KPOINTS"


class _CaptureServer(VASPLanguageServer):
    """A VASPLanguageServer subclass that captures publish_diagnostics calls."""

    def __init__(self) -> None:
        super().__init__()
        self.published_diagnostics: Dict[str, List[Diagnostic]] = {}
        self.published_versions: Dict[str, Optional[int]] = {}

    def publish_diagnostics(
        self, uri: str, diagnostics: Optional[List[Diagnostic]] = None, **kwargs: object
    ) -> None:
        """Override to capture published diagnostics instead of sending over transport."""
        self.published_diagnostics[uri] = diagnostics or []
        version = kwargs.get("version")
        self.published_versions[uri] = version if isinstance(version, int) else None


@pytest.fixture()
def server() -> _CaptureServer:
    """Create a fresh server instance for each test."""
    srv = _CaptureServer()
    return srv


@pytest.fixture(autouse=True)
def _patch_global_server(server: _CaptureServer, monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the module-level ``server`` object used by handler functions."""
    import vasp_lsp.server as server_mod

    monkeypatch.setattr(server_mod, "server", server)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_init_params() -> InitializeParams:
    return InitializeParams(
        root_uri="file:///workspace",
        capabilities={},
        client_info=Mock(name="test-client"),
    )


def _make_did_open(uri: str, content: str, version: int = 1) -> DidOpenTextDocumentParams:
    return DidOpenTextDocumentParams(
        text_document=TextDocumentItem(
            uri=uri, language_id="plaintext", version=version, text=content
        ),
    )


def _make_did_change(uri: str, new_content: str, version: int = 2) -> DidChangeTextDocumentParams:
    return DidChangeTextDocumentParams(
        text_document=VersionedTextDocumentIdentifier(uri=uri, version=version),
        content_changes=[TextDocumentContentChangeEvent_Type2(text=new_content)],
    )


def _make_did_save(uri: str) -> DidSaveTextDocumentParams:
    return DidSaveTextDocumentParams(text_document=TextDocumentIdentifier(uri=uri))


def _make_completion_params(uri: str, line: int, character: int) -> CompletionParams:
    return CompletionParams(
        text_document=TextDocumentIdentifier(uri=uri),
        position=Position(line=line, character=character),
    )


def _make_hover_params(uri: str, line: int, character: int) -> HoverParams:
    return HoverParams(
        text_document=TextDocumentIdentifier(uri=uri),
        position=Position(line=line, character=character),
    )


def _make_formatting_params(uri: str) -> DocumentFormattingParams:
    return DocumentFormattingParams(
        text_document=TextDocumentIdentifier(uri=uri),
        options=FormattingOptions(tab_size=4, insert_spaces=True),
    )


def _make_code_action_params(
    uri: str,
    line: int,
    diagnostics: List[Diagnostic],
) -> CodeActionParams:
    return CodeActionParams(
        text_document=TextDocumentIdentifier(uri=uri),
        range=Range(
            start=Position(line=line, character=0),
            end=Position(line=line + 1, character=0),
        ),
        context=CodeActionContext(diagnostics=diagnostics),
    )


# ===========================================================================
# 1. Server lifecycle
# ===========================================================================


@pytest.mark.integration
class TestServerLifecycle:
    """Tests for server initialization and shutdown."""

    def test_initialize_returns_capabilities(self, server: _CaptureServer) -> None:
        """Initialize returns an InitializeResult with correct capabilities."""
        result = initialize(_make_init_params())

        assert result.capabilities is not None
        caps = result.capabilities
        assert caps.hover_provider is True
        assert caps.document_formatting_provider is True

        # Text document sync
        sync = caps.text_document_sync
        assert sync.open_close is True
        assert sync.change == TextDocumentSyncKind.Full
        assert server._text_document_sync_kind == TextDocumentSyncKind.Full

        # Completion provider
        assert caps.completion_provider is not None
        assert "=" in caps.completion_provider.trigger_characters
        assert " " in caps.completion_provider.trigger_characters

    def test_initialize_has_code_action_provider(self, server: _CaptureServer) -> None:
        """Initialize advertises code action support."""
        result = initialize(_make_init_params())
        assert result.capabilities.code_action_provider is not None

    def test_server_has_all_providers(self, server: _CaptureServer) -> None:
        """Server instance initializes all feature providers."""
        assert server.completion_provider is not None
        assert server.hover_provider is not None
        assert server.diagnostics_provider is not None
        assert server.formatting_provider is not None
        assert server.quickfixes_provider is not None

    def test_server_name_and_version(self, server: _CaptureServer) -> None:
        """Server reports correct name."""
        assert server.name == "vasp-lsp"


# ===========================================================================
# 2. Document synchronization
# ===========================================================================


@pytest.mark.integration
class TestDocumentSynchronization:
    """Tests for textDocument/didOpen, didChange, didSave."""

    def test_did_open_caches_content(self, server: _CaptureServer) -> None:
        """didOpen stores document content in server cache."""
        content = "ENCUT = 520\nISMEAR = 0\nSIGMA = 0.05"
        text_document_did_open(_make_did_open(INCAR_URI, content))

        assert server.get_document_content(INCAR_URI) == content

    def test_did_open_publishes_diagnostics(self, server: _CaptureServer) -> None:
        """didOpen triggers diagnostic publication."""
        content = "UNKNOWN_TAG = 42"
        text_document_did_open(_make_did_open(INCAR_URI, content))

        assert INCAR_URI in server.published_diagnostics
        diags = server.published_diagnostics[INCAR_URI]
        assert any("Unknown INCAR tag" in d.message for d in diags)

    def test_did_change_updates_content(self, server: _CaptureServer) -> None:
        """didChange updates the cached document content."""
        original = "ENCUT = 500"
        text_document_did_open(_make_did_open(INCAR_URI, original))

        updated = "ENCUT = 520\nISMEAR = 0"
        text_document_did_change(_make_did_change(INCAR_URI, updated))

        assert server.get_document_content(INCAR_URI) == updated

    def test_did_change_recomputes_diagnostics(self, server: _CaptureServer) -> None:
        """didChange republishes diagnostics for the new content."""
        text_document_did_open(_make_did_open(INCAR_URI, "ENCUT = 500"))

        # Introduce an error
        text_document_did_change(_make_did_change(INCAR_URI, "BADTAG = 1"))

        diags = server.published_diagnostics.get(INCAR_URI, [])
        assert any("Unknown INCAR tag" in d.message for d in diags)

    def test_incremental_did_change_preserves_document_and_diagnostics(
        self, server: _CaptureServer
    ) -> None:
        """A range edit must be applied to the cached full document."""
        original = "LREAL = .FALSE.\n"
        text_document_did_open(_make_did_open(INCAR_URI, original))

        change = DidChangeTextDocumentParams(
            text_document=VersionedTextDocumentIdentifier(uri=INCAR_URI, version=2),
            content_changes=[
                TextDocumentContentChangeEvent_Type1(
                    range=Range(
                        start=Position(line=0, character=8),
                        end=Position(line=0, character=15),
                    ),
                    text="maybe",
                )
            ],
        )
        text_document_did_change(change)

        assert server.get_document_content(INCAR_URI) == "LREAL = maybe\n"
        diags = server.published_diagnostics.get(INCAR_URI, [])
        assert any("Invalid value for LREAL" in diagnostic.message for diagnostic in diags)

    def test_diagnostics_follow_full_document_edit_version_and_range(
        self, server: _CaptureServer
    ) -> None:
        """Formatting-like full edits publish diagnostics for the new document."""
        original = "BADTAG = 1\nENCUT = 500"
        text_document_did_open(_make_did_open(INCAR_URI, original, version=1))
        assert server.published_versions[INCAR_URI] == 1

        # A formatter commonly moves the offending line while replacing the
        # whole document.  The diagnostic must follow that new document.
        formatted = "ENCUT = 500\nBADTAG = 1"
        text_document_did_change(_make_did_change(INCAR_URI, formatted, version=2))

        diagnostics = server.published_diagnostics[INCAR_URI]
        badtag = next(d for d in diagnostics if "Unknown INCAR tag" in d.message)
        assert badtag.range.start.line == 1
        assert server.published_versions[INCAR_URI] == 2

    def test_did_save_republishes_diagnostics(self, server: _CaptureServer) -> None:
        """didSave republishes diagnostics from cached content."""
        text_document_did_open(_make_did_open(INCAR_URI, "ENCUT = 520"))

        # Clear diagnostics to verify didSave republishes
        server.published_diagnostics.clear()
        text_document_did_save(_make_did_save(INCAR_URI))

        assert INCAR_URI in server.published_diagnostics

    def test_did_save_with_no_content(self, server: _CaptureServer) -> None:
        """didSave on a document with no cached content does not crash."""
        server.published_diagnostics.clear()
        text_document_did_save(_make_did_save("file:///workspace/other"))
        # Should not raise and should not publish for unknown URIs
        assert "file:///workspace/other" not in server.published_diagnostics

    def test_did_save_republishes_empty_cached_document(self, server: _CaptureServer) -> None:
        """Saving an empty buffer must clear diagnostics instead of keeping stale signs."""
        text_document_did_open(_make_did_open(INCAR_URI, "BADTAG = 1"))
        server.set_document_content(INCAR_URI, "")
        server.set_document_diagnostics(
            INCAR_URI,
            [
                Diagnostic(
                    range=Range(
                        start=Position(line=0, character=0),
                        end=Position(line=0, character=1),
                    ),
                    message="stale",
                )
            ],
        )
        server.published_diagnostics.clear()

        text_document_did_save(_make_did_save(INCAR_URI))

        assert INCAR_URI in server.published_diagnostics
        assert server.published_diagnostics[INCAR_URI] == []

    def test_did_close_clears_document_state(self, server: _CaptureServer) -> None:
        """Closing a document releases its content, version, and diagnostics."""
        text_document_did_open(_make_did_open(INCAR_URI, "BADTAG = 1", version=4))
        assert server.get_document_content(INCAR_URI) is not None

        text_document_did_close(
            DidCloseTextDocumentParams(text_document=TextDocumentIdentifier(uri=INCAR_URI))
        )

        assert server.get_document_content(INCAR_URI) is None
        assert server.get_document_diagnostics(INCAR_URI) == []
        assert INCAR_URI not in server.document_versions


# ===========================================================================
# 3. Diagnostics
# ===========================================================================


@pytest.mark.integration
class TestDiagnostics:
    """Tests for diagnostic publication on INCAR files."""

    def test_unknown_tag_diagnostic(self, server: _CaptureServer) -> None:
        """Unknown INCAR tags produce a vasp.incar.invalid_tag error diagnostic."""
        content = "FAKETAG = 123"
        text_document_did_open(_make_did_open(INCAR_URI, content))

        diags = server.published_diagnostics[INCAR_URI]
        matching = [d for d in diags if "Unknown INCAR tag" in d.message]
        assert len(matching) >= 1
        assert matching[0].severity == DiagnosticSeverity.Error
        assert matching[0].source == "vasp-lsp"
        assert matching[0].code == "vasp.incar.invalid_tag"

    def test_type_mismatch_diagnostic(self, server: _CaptureServer) -> None:
        """Type mismatch produces an error diagnostic."""
        # ENCUT is float; assigning a string-like boolean is a type mismatch
        # ISPIN is integer; assigning a string is an error
        content = "ISPIN = .TRUE."
        text_document_did_open(_make_did_open(INCAR_URI, content))

        diags = server.published_diagnostics[INCAR_URI]
        messages = [d.message for d in diags]
        assert any("integer" in m for m in messages)

    def test_valid_incar_no_errors(self, server: _CaptureServer) -> None:
        """A well-formed INCAR with no issues produces no error-level diagnostics."""
        content = "ENCUT = 520\nISMEAR = 0\nSIGMA = 0.05"
        text_document_did_open(_make_did_open(INCAR_URI, content))

        diags = server.published_diagnostics[INCAR_URI]
        errors = [d for d in diags if d.severity == DiagnosticSeverity.Error]
        assert errors == []

    def test_missing_sigma_warning(self, server: _CaptureServer) -> None:
        """ISMEAR >= 0 without SIGMA produces a vasp.smearing.ismear_sigma_mismatch warning."""
        content = "ISMEAR = 1"
        text_document_did_open(_make_did_open(INCAR_URI, content))

        diags = server.published_diagnostics[INCAR_URI]
        matching = [d for d in diags if "SIGMA" in d.message and "ISMEAR" in d.message]
        assert len(matching) >= 1
        assert matching[0].severity == DiagnosticSeverity.Warning

    def test_ncore_npar_conflict(self, server: _CaptureServer) -> None:
        """Setting both NCORE and NPAR produces a warning."""
        content = "NCORE = 4\nNPAR = 4"
        text_document_did_open(_make_did_open(INCAR_URI, content))

        diags = server.published_diagnostics[INCAR_URI]
        matching = [d for d in diags if "NPAR" in d.message and "NCORE" in d.message]
        assert len(matching) >= 1

    def test_poscar_diagnostics_via_did_open(self, server: _CaptureServer) -> None:
        """Opening a POSCAR triggers diagnostics."""
        content = "Test\n1.0\n0 0 0\n0 0 0\n0 0 0\nSi\n1\nDirect\n0.0 0.0 0.0\n"
        text_document_did_open(_make_did_open(POSCAR_URI, content))

        diags = server.published_diagnostics.get(POSCAR_URI, [])
        # Zero-length lattice vectors should produce errors
        assert any("zero" in d.message.lower() for d in diags)

    def test_potcar_diagnostics_via_did_open(self, server: _CaptureServer) -> None:
        """Opening a POTCAR reports parser errors instead of staying silent."""
        text_document_did_open(_make_did_open(POTCAR_URI, "not a POTCAR dataset\n"))

        diags = server.published_diagnostics.get(POTCAR_URI, [])
        assert any("potcar parse error" in d.message.lower() for d in diags)

    def test_kpoints_diagnostics_via_did_open(self, server: _CaptureServer) -> None:
        """Opening a KPOINTS file triggers diagnostics."""
        content = "Test\n0\nGamma\n0 0 0\n0 0 0\n"
        text_document_did_open(_make_did_open(KPOINTS_URI, content))

        diags = server.published_diagnostics.get(KPOINTS_URI, [])
        # Zero grid value should produce an error
        assert any("not positive" in d.message for d in diags)


# ===========================================================================
# 4. Completion
# ===========================================================================


@pytest.mark.integration
class TestCompletion:
    """Tests for textDocument/completion."""

    def test_incar_tag_completions(self, server: _CaptureServer) -> None:
        """Requesting completions in an INCAR returns known tags."""
        content = "EN"
        server.set_document_content(INCAR_URI, content)

        params = _make_completion_params(INCAR_URI, line=0, character=2)
        result = completions(params)

        assert result is not None
        labels = [item.label for item in result.items]
        assert "ENCUT" in labels

    def test_incar_value_completions_after_equals(self, server: _CaptureServer) -> None:
        """After '=' on an enum tag, completions include valid values."""
        content = "ISMEAR = "
        server.set_document_content(INCAR_URI, content)

        params = _make_completion_params(INCAR_URI, line=0, character=len(content))
        result = completions(params)

        assert result is not None
        labels = [item.label for item in result.items]
        # ISMEAR has enum values
        assert len(labels) > 0

    def test_boolean_value_completions(self, server: _CaptureServer) -> None:
        """After '=' on a boolean tag, completions include .TRUE. and .FALSE."""
        content = "LWAVE = "
        server.set_document_content(INCAR_URI, content)

        params = _make_completion_params(INCAR_URI, line=0, character=len(content))
        result = completions(params)

        assert result is not None
        labels = [item.label for item in result.items]
        assert ".TRUE." in labels
        assert ".FALSE." in labels

    def test_completion_returns_none_without_content(self, server: _CaptureServer) -> None:
        """Completion returns None when no document is cached."""
        params = _make_completion_params("file:///missing", line=0, character=0)
        result = completions(params)
        assert result is None

    def test_completion_for_unknown_file_type(self, server: _CaptureServer) -> None:
        """Completions for a non-VASP file return empty items."""
        uri = "file:///workspace/random.txt"
        server.set_document_content(uri, "hello")
        params = _make_completion_params(uri, line=0, character=0)
        result = completions(params)

        assert result is not None
        assert result.items == []


# ===========================================================================
# 5. Hover
# ===========================================================================


@pytest.mark.integration
class TestHover:
    """Tests for textDocument/hover."""

    def test_hover_on_encut(self, server: _CaptureServer) -> None:
        """Hovering over ENCUT returns documentation."""
        content = "ENCUT = 520"
        server.set_document_content(INCAR_URI, content)

        params = _make_hover_params(INCAR_URI, line=0, character=2)
        result = hover(params)

        assert result is not None
        assert result.contents is not None
        # Contents should include ENCUT info
        text = result.contents.value
        assert "ENCUT" in text
        assert "float" in text

    def test_hover_on_unknown_tag(self, server: _CaptureServer) -> None:
        """Hovering over an unknown tag returns None."""
        content = "FOOBAR = 123"
        server.set_document_content(INCAR_URI, content)

        params = _make_hover_params(INCAR_URI, line=0, character=2)
        result = hover(params)

        assert result is None

    def test_hover_returns_none_without_content(self, server: _CaptureServer) -> None:
        """Hover returns None when document is not cached."""
        params = _make_hover_params("file:///missing", line=0, character=0)
        result = hover(params)
        assert result is None

    def test_hover_on_poscar_line(self, server: _CaptureServer) -> None:
        """Hover on POSCAR lines returns line-specific documentation."""
        content = "Test system\n1.0\n1.0 0.0 0.0\n0.0 1.0 0.0\n0.0 0.0 1.0\nSi\n1\nDirect\n"
        server.set_document_content(POSCAR_URI, content)

        params = _make_hover_params(POSCAR_URI, line=1, character=0)
        result = hover(params)

        assert result is not None
        assert "Scale Factor" in result.contents.value

    def test_hover_on_kpoints_line(self, server: _CaptureServer) -> None:
        """Hover on KPOINTS lines returns line-specific documentation."""
        content = "K-points\n0\nGamma\n4 4 4\n0 0 0\n"
        server.set_document_content(KPOINTS_URI, content)

        params = _make_hover_params(KPOINTS_URI, line=0, character=0)
        result = hover(params)

        assert result is not None
        assert "Comment" in result.contents.value


# ===========================================================================
# 6. Formatting
# ===========================================================================


@pytest.mark.integration
class TestFormatting:
    """Tests for textDocument/formatting."""

    def test_format_incar_returns_text_edits(self, server: _CaptureServer) -> None:
        """Formatting a messy INCAR returns TextEdits."""
        content = "ENCUT=500\nISMEAR=0"
        server.set_document_content(INCAR_URI, content)

        params = _make_formatting_params(INCAR_URI)
        result = formatting(params)

        assert result is not None
        assert len(result) >= 1
        edit = result[0]
        assert edit.new_text != ""
        assert "ENCUT" in edit.new_text
        # Formatted output should have consistent spacing
        assert "= " in edit.new_text

    def test_format_incar_groups_parameters(self, server: _CaptureServer) -> None:
        """Formatted INCAR groups parameters by category."""
        content = "NCORE = 4\nENCUT = 520\nIBRION = 2"
        server.set_document_content(INCAR_URI, content)

        params = _make_formatting_params(INCAR_URI)
        result = formatting(params)

        assert result is not None
        text = result[0].new_text
        # Should contain group headers
        assert "Electronic Structure" in text or "Parallelization" in text

    def test_format_returns_none_without_content(self, server: _CaptureServer) -> None:
        """Formatting returns None when document is not cached."""
        params = _make_formatting_params("file:///missing")
        result = formatting(params)
        assert result is None

    def test_format_poscar(self, server: _CaptureServer) -> None:
        """Formatting a POSCAR returns TextEdits."""
        content = "Test\n1.0\n1.0 0.0 0.0\n0.0 1.0 0.0\n0.0 0.0 1.0\nSi\n1\nDirect\n0.0 0.0 0.0\n"
        server.set_document_content(POSCAR_URI, content)

        params = _make_formatting_params(POSCAR_URI)
        result = formatting(params)

        assert result is not None
        assert len(result) >= 1

    def test_format_kpoints(self, server: _CaptureServer) -> None:
        """Formatting a KPOINTS returns TextEdits."""
        content = "Auto\n0\nGamma\n4 4 4\n0 0 0\n"
        server.set_document_content(KPOINTS_URI, content)

        params = _make_formatting_params(KPOINTS_URI)
        result = formatting(params)

        assert result is not None
        assert len(result) >= 1

    def test_format_unknown_file_returns_empty(self, server: _CaptureServer) -> None:
        """Formatting an unknown file type returns empty list."""
        uri = "file:///workspace/random.txt"
        server.set_document_content(uri, "some text")
        params = _make_formatting_params(uri)
        result = formatting(params)

        assert result == []


# ===========================================================================
# 7. Code actions (quick fixes)
# ===========================================================================


@pytest.mark.integration
class TestCodeActions:
    """Tests for textDocument/codeAction."""

    def test_add_sigma_quickfix(self, server: _CaptureServer) -> None:
        """ISMEAR without SIGMA triggers an 'Add SIGMA' quickfix."""
        content = "ISMEAR = 1"
        text_document_did_open(_make_did_open(INCAR_URI, content))

        diags = server.published_diagnostics[INCAR_URI]
        sigma_diags = [d for d in diags if "SIGMA" in d.message]

        if not sigma_diags:
            pytest.skip("No SIGMA diagnostic produced for this content")

        params = _make_code_action_params(INCAR_URI, line=0, diagnostics=sigma_diags)
        actions = code_action(params)

        assert actions is not None
        titles = [a.title for a in actions]
        assert any("SIGMA" in t for t in titles)

    def test_typo_quickfix(self, server: _CaptureServer) -> None:
        """Unknown tag that looks like a typo triggers a fix suggestion."""
        content = "ENCUTT = 500"
        text_document_did_open(_make_did_open(INCAR_URI, content))

        diags = server.published_diagnostics[INCAR_URI]
        typo_diags = [d for d in diags if "Unknown INCAR tag" in d.message]

        if not typo_diags:
            pytest.skip("No unknown tag diagnostic produced")

        params = _make_code_action_params(INCAR_URI, line=0, diagnostics=typo_diags)
        actions = code_action(params)

        assert actions is not None
        titles = [a.title for a in actions]
        assert any("ENCUT" in t for t in titles)

    def test_remove_npar_quickfix(self, server: _CaptureServer) -> None:
        """NCORE + NPAR conflict triggers a 'Remove NPAR' quickfix."""
        content = "NCORE = 4\nNPAR = 4"
        text_document_did_open(_make_did_open(INCAR_URI, content))

        diags = server.published_diagnostics[INCAR_URI]
        conflict_diags = [d for d in diags if "NPAR" in d.message and "NCORE" in d.message]

        if not conflict_diags:
            pytest.skip("No NCORE/NPAR conflict diagnostic produced")

        # The NPAR line is line 1
        params = _make_code_action_params(INCAR_URI, line=1, diagnostics=conflict_diags)
        actions = code_action(params)

        assert actions is not None
        titles = [a.title for a in actions]
        assert any("NPAR" in t for t in titles)

    def test_code_action_returns_none_without_content(self, server: _CaptureServer) -> None:
        """Code action returns None when no document is cached."""
        params = _make_code_action_params("file:///missing", line=0, diagnostics=[])
        result = code_action(params)
        assert result is None

    def test_code_action_with_empty_diagnostics(self, server: _CaptureServer) -> None:
        """Code action with no diagnostics returns an empty list."""
        content = "ENCUT = 520"
        server.set_document_content(INCAR_URI, content)

        params = _make_code_action_params(INCAR_URI, line=0, diagnostics=[])
        actions = code_action(params)

        assert actions is not None
        assert actions == []


# ===========================================================================
# End-to-end workflow
# ===========================================================================


@pytest.mark.integration
class TestEndToEndWorkflow:
    """Full workflow tests that exercise multiple LSP features in sequence."""

    def test_open_edit_format_workflow(self, server: _CaptureServer) -> None:
        """Simulates a realistic editing workflow: open -> edit -> format."""
        # 1. Open document
        initial_content = "ENCUT=500"
        text_document_did_open(_make_did_open(INCAR_URI, initial_content))
        assert server.get_document_content(INCAR_URI) == initial_content

        # 2. Edit: add ISMEAR
        edited = "ENCUT=500\nISMEAR = 1"
        text_document_did_change(_make_did_change(INCAR_URI, edited))
        assert server.get_document_content(INCAR_URI) == edited

        # 3. Check diagnostics were published for ISMEAR without SIGMA
        diags = server.published_diagnostics.get(INCAR_URI, [])
        assert any("SIGMA" in d.message for d in diags)

        # 4. Request completions
        comp_params = _make_completion_params(INCAR_URI, line=2, character=0)
        comp_result = completions(comp_params)
        assert comp_result is not None

        # 5. Request hover
        hover_params = _make_hover_params(INCAR_URI, line=0, character=2)
        hover_result = hover(hover_params)
        assert hover_result is not None
        assert "ENCUT" in hover_result.contents.value

        # 6. Format
        fmt_params = _make_formatting_params(INCAR_URI)
        fmt_result = formatting(fmt_params)
        assert fmt_result is not None
        assert len(fmt_result) >= 1

    def test_diagnostics_to_code_action_pipeline(self, server: _CaptureServer) -> None:
        """Diagnostics from didOpen feed directly into code actions."""
        # Open an INCAR with both ISMEAR and SIGMA issues
        content = "ISMEAR = 1"
        text_document_did_open(_make_did_open(INCAR_URI, content))

        diags = server.published_diagnostics[INCAR_URI]
        assert len(diags) > 0

        # Request code actions for the full document
        params = _make_code_action_params(INCAR_URI, line=0, diagnostics=diags)
        actions = code_action(params)

        assert actions is not None
        # Should have at least one fix for SIGMA
        assert len(actions) > 0

    def test_save_triggers_refreshed_diagnostics(self, server: _CaptureServer) -> None:
        """Saving triggers diagnostic refresh from cached content."""
        # Open a clean INCAR
        text_document_did_open(_make_did_open(INCAR_URI, "ENCUT = 520"))

        # Edit to introduce an issue
        text_document_did_change(_make_did_change(INCAR_URI, "BADTAG = 1"))

        # Save
        text_document_did_save(_make_did_save(INCAR_URI))

        # Diagnostics after save should reflect the bad tag
        diags = server.published_diagnostics.get(INCAR_URI, [])
        assert any("Unknown INCAR tag" in d.message for d in diags)


# ---------------------------------------------------------------------------
# Helper factories for new handlers
# ---------------------------------------------------------------------------


def _make_range_formatting_params(
    uri: str, start_line: int, end_line: int
) -> DocumentRangeFormattingParams:
    return DocumentRangeFormattingParams(
        text_document=TextDocumentIdentifier(uri=uri),
        range=Range(
            start=Position(line=start_line, character=0),
            end=Position(line=end_line, character=100),
        ),
        options=FormattingOptions(tab_size=4, insert_spaces=True),
    )


def _make_definition_params(uri: str, line: int, character: int) -> DefinitionParams:
    return DefinitionParams(
        text_document=TextDocumentIdentifier(uri=uri),
        position=Position(line=line, character=character),
    )


def _make_references_params(uri: str, line: int, character: int) -> ReferenceParams:
    from lsprotocol.types import ReferenceContext

    return ReferenceParams(
        text_document=TextDocumentIdentifier(uri=uri),
        position=Position(line=line, character=character),
        context=ReferenceContext(include_declaration=True),
    )


def _make_prepare_rename_params(uri: str, line: int, character: int) -> PrepareRenameParams:
    return PrepareRenameParams(
        text_document=TextDocumentIdentifier(uri=uri),
        position=Position(line=line, character=character),
    )


def _make_rename_params(uri: str, line: int, character: int, new_name: str) -> RenameParams:
    return RenameParams(
        text_document=TextDocumentIdentifier(uri=uri),
        position=Position(line=line, character=character),
        new_name=new_name,
    )


def _make_workspace_symbol_params(query: str) -> WorkspaceSymbolParams:
    return WorkspaceSymbolParams(query=query)


def _make_document_symbol_params(uri: str) -> DocumentSymbolParams:
    return DocumentSymbolParams(text_document=TextDocumentIdentifier(uri=uri))


# ===========================================================================
# Range formatting handler tests
# ===========================================================================


@pytest.mark.integration
class TestRangeFormattingHandler:
    """Integration tests for the range formatting handler."""

    def test_range_format_returns_edits(self, server: _CaptureServer) -> None:
        """Range formatting returns edits for INCAR files."""
        text_document_did_open(_make_did_open(INCAR_URI, "encut = 400\nismear = 0"))
        params = _make_range_formatting_params(INCAR_URI, 0, 0)
        result = range_formatting(params)
        assert result is not None
        assert len(result) == 1

    def test_range_format_returns_none_for_missing_doc(self, server: _CaptureServer) -> None:
        """Range formatting returns None for uncached documents."""
        params = _make_range_formatting_params("file:///missing", 0, 0)
        result = range_formatting(params)
        assert result is None


# ===========================================================================
# Definition handler tests
# ===========================================================================


@pytest.mark.integration
class TestDefinitionHandler:
    """Integration tests for the definition handler."""

    def test_definition_returns_location(self, server: _CaptureServer) -> None:
        """Definition returns a Location for an INCAR tag."""
        text_document_did_open(_make_did_open(INCAR_URI, "ENCUT = 400\nISMEAR = 0"))
        params = _make_definition_params(INCAR_URI, 0, 1)
        result = definition(params)
        assert result is not None
        assert result.range.start.line == 0

    def test_definition_returns_none_for_missing_doc(self, server: _CaptureServer) -> None:
        """Definition returns None for uncached documents."""
        params = _make_definition_params("file:///missing", 0, 0)
        result = definition(params)
        assert result is None


# ===========================================================================
# References handler tests
# ===========================================================================


@pytest.mark.integration
class TestReferencesHandler:
    """Integration tests for the references handler."""

    def test_references_returns_all(self, server: _CaptureServer) -> None:
        """References returns all occurrences of an INCAR tag."""
        text_document_did_open(_make_did_open(INCAR_URI, "ENCUT = 400\nISMEAR = 0\nENCUT = 500"))
        params = _make_references_params(INCAR_URI, 0, 1)
        result = references(params)
        assert result is not None
        assert len(result) == 2

    def test_references_returns_empty_for_missing_doc(self, server: _CaptureServer) -> None:
        """References returns empty list for uncached documents."""
        params = _make_references_params("file:///missing", 0, 0)
        result = references(params)
        assert result == []


# ===========================================================================
# Workspace symbol handler tests
# ===========================================================================


@pytest.mark.integration
class TestWorkspaceSymbolHandler:
    """Integration tests for the workspace symbol handler."""

    def test_workspace_symbol_returns_incar_tags(self, server: _CaptureServer) -> None:
        """Workspace symbol returns INCAR tags from open documents."""
        text_document_did_open(_make_did_open(INCAR_URI, "ENCUT = 400\nISMEAR = 0\nSIGMA = 0.2"))
        params = _make_workspace_symbol_params("ENC")
        result = workspace_symbol(params)
        assert result is not None
        assert any(s.name == "ENCUT" for s in result)

    def test_workspace_symbol_empty_query(self, server: _CaptureServer) -> None:
        """Workspace symbol with empty query returns all symbols."""
        text_document_did_open(_make_did_open(INCAR_URI, "ENCUT = 400\nISMEAR = 0"))
        params = _make_workspace_symbol_params("")
        result = workspace_symbol(params)
        assert result is not None
        assert len(result) >= 2


# ===========================================================================
# Document symbol handler tests
# ===========================================================================


@pytest.mark.integration
class TestDocumentSymbolHandler:
    """Integration tests for the document symbol handler."""

    def test_document_symbol_returns_incar_tags(self, server: _CaptureServer) -> None:
        """Document symbol returns INCAR tags."""
        text_document_did_open(_make_did_open(INCAR_URI, "ENCUT = 400\nISMEAR = 0"))
        params = _make_document_symbol_params(INCAR_URI)
        result = document_symbol(params)
        assert result is not None
        assert len(result) == 2

    def test_document_symbol_returns_empty_for_missing(self, server: _CaptureServer) -> None:
        """Document symbol returns empty list for uncached documents."""
        params = _make_document_symbol_params("file:///missing")
        result = document_symbol(params)
        assert result == []


# ===========================================================================
# Prepare rename handler tests
# ===========================================================================


@pytest.mark.integration
class TestPrepareRenameHandler:
    """Integration tests for the prepare rename handler."""

    def test_prepare_rename_returns_range(self, server: _CaptureServer) -> None:
        """Prepare rename returns a range for an INCAR tag."""
        text_document_did_open(_make_did_open(INCAR_URI, "ENCUT = 400"))
        params = _make_prepare_rename_params(INCAR_URI, 0, 1)
        result = prepare_rename(params)
        assert result is not None
        assert result.start.line == 0

    def test_prepare_rename_returns_none_for_missing(self, server: _CaptureServer) -> None:
        """Prepare rename returns None for uncached documents."""
        params = _make_prepare_rename_params("file:///missing", 0, 0)
        result = prepare_rename(params)
        assert result is None


# ===========================================================================
# Rename handler tests
# ===========================================================================


@pytest.mark.integration
class TestRenameHandler:
    """Integration tests for the rename handler."""

    def test_rename_returns_workspace_edit(self, server: _CaptureServer) -> None:
        """Rename returns a workspace edit for an INCAR tag."""
        text_document_did_open(_make_did_open(INCAR_URI, "ENCUT = 400\nISMEAR = 0\nENCUT = 500"))
        params = _make_rename_params(INCAR_URI, 0, 1, "CUTOFF")
        result = rename(params)
        assert result is not None
        assert result.changes is not None
        assert INCAR_URI in result.changes
        assert len(result.changes[INCAR_URI]) == 2

    def test_rename_returns_none_for_missing(self, server: _CaptureServer) -> None:
        """Rename returns None for uncached documents."""
        params = _make_rename_params("file:///missing", 0, 0, "NEW")
        result = rename(params)
        assert result is None

    def test_rename_returns_none_for_non_inc(self, server: _CaptureServer) -> None:
        """Rename returns None for non-INCAR files."""
        text_document_did_open(_make_did_open(POSCAR_URI, "Si\n1.0"))
        params = _make_rename_params(POSCAR_URI, 0, 0, "NEW")
        result = rename(params)
        assert result is None
