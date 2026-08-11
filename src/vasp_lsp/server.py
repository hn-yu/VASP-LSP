"""Main LSP server for VASP input files.

This module implements the Language Server Protocol for VASP files,
providing features like autocomplete, hover documentation, and diagnostics.
"""

import argparse
import json
import logging
import os
import re
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from lsprotocol.types import (
    TEXT_DOCUMENT_CODE_ACTION,
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_DEFINITION,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_CLOSE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    TEXT_DOCUMENT_DOCUMENT_SYMBOL,
    TEXT_DOCUMENT_FORMATTING,
    TEXT_DOCUMENT_HOVER,
    TEXT_DOCUMENT_PREPARE_RENAME,
    TEXT_DOCUMENT_RANGE_FORMATTING,
    TEXT_DOCUMENT_REFERENCES,
    TEXT_DOCUMENT_RENAME,
    WORKSPACE_SYMBOL,
    CodeActionOptions,
    CodeActionParams,
    CompletionOptions,
    CompletionParams,
    DefinitionParams,
    Diagnostic,
    DidChangeTextDocumentParams,
    DidCloseTextDocumentParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    DocumentFormattingParams,
    DocumentRangeFormattingParams,
    DocumentSymbolParams,
    ExecuteCommandParams,
    HoverParams,
    InitializeParams,
    InitializeResult,
    Position,
    PrepareRenameParams,
    Range,
    ReferenceParams,
    RenameParams,
    ServerCapabilities,
    TextDocumentSyncKind,
    TextDocumentSyncOptions,
    TextEdit,
    WorkspaceEdit,
    WorkspaceSymbolParams,
)
from pygls.server import LanguageServer

from . import __version__
from .features.completion import CompletionProvider
from .features.diagnostics import DiagnosticsProvider
from .features.formatting import FormattingProvider
from .features.hover import HoverProvider
from .features.navigation import DocumentSymbolsProvider
from .features.quickfixes import QuickFixesProvider
from .workspace import document_kind

# Set up logging
# Keep the stdio server and simple CLI flags quiet by default.  In particular,
# pygls emits feature-registration messages at INFO during module import; they
# are useful only when a caller explicitly configures logging and otherwise
# make ``vasp-lsp --version`` look like a failed command.
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class VASPLanguageServer(LanguageServer):
    """VASP Language Server implementation."""

    def __init__(self):
        # pygls uses this value when it builds the actual initialize response.
        # Keeping it explicit is important: the custom initialize handler below
        # is not the handler used by pygls's built-in protocol initializer.
        super().__init__(
            name="vasp-lsp",
            version=__version__,
            text_document_sync_kind=TextDocumentSyncKind.Full,
        )
        self.completion_provider = CompletionProvider()
        self.hover_provider = HoverProvider()
        self.diagnostics_provider = DiagnosticsProvider()
        self.formatting_provider = FormattingProvider()
        self.quickfixes_provider = QuickFixesProvider()
        self.navigation_provider = DocumentSymbolsProvider()

        # Document cache
        self.documents: Dict[str, str] = {}
        self.document_versions: Dict[str, int] = {}
        self.diagnostic_versions: Dict[str, int] = {}
        self.document_diagnostics: Dict[str, List[Diagnostic]] = {}

    def get_document_content(self, uri: str) -> Optional[str]:
        """Get document content from cache or workspace."""
        return self.documents.get(uri)

    def set_document_content(self, uri: str, content: str) -> None:
        """Cache document content."""
        self.documents[uri] = content

    def set_document_diagnostics(self, uri: str, diagnostics: List[Diagnostic]) -> None:
        """Cache document diagnostics for code actions."""
        self.document_diagnostics[uri] = diagnostics

    def get_document_diagnostics(self, uri: str) -> List[Diagnostic]:
        """Get cached document diagnostics."""
        return self.document_diagnostics.get(uri, [])


# Create server instance
server = VASPLanguageServer()


def _utf16_character_to_index(line: str, character: int) -> int:
    """Convert an LSP UTF-16 character offset to a Python string index."""
    if character <= 0:
        return 0

    utf16_units = 0
    for index, value in enumerate(line):
        next_units = utf16_units + (2 if ord(value) > 0xFFFF else 1)
        if next_units > character:
            return index
        utf16_units = next_units
        if utf16_units == character:
            return index + 1

    return len(line)


def _position_to_offset(content: str, position: Position) -> int:
    """Convert an LSP position into a Python string offset."""
    line_number = max(position.line, 0)
    lines = content.splitlines(keepends=True)
    if line_number >= len(lines):
        return len(content)

    line_start = sum(len(line) for line in lines[:line_number])
    line = lines[line_number]
    return line_start + _utf16_character_to_index(line, position.character)


def _apply_content_changes(content: str, content_changes: List[Any]) -> str:
    """Apply full-document and incremental LSP changes in notification order.

    LSP clients are allowed to send either a complete replacement (no range)
    or one or more range-based changes.  The latter is what Neovim sends when
    its client sees ``textDocumentSync.change = Incremental``.
    """
    for change in content_changes:
        replacement = getattr(change, "text", "")
        change_range = getattr(change, "range", None)

        # Type2 changes have no range and replace the whole document.  The
        # isinstance check also keeps compatibility with simple test doubles.
        if not isinstance(change_range, Range):
            content = replacement
            continue

        start = _position_to_offset(content, change_range.start)
        end = _position_to_offset(content, change_range.end)
        if end < start:
            logger.warning("Ignoring invalid LSP change range: %s", change_range)
            continue
        content = content[:start] + replacement + content[end:]

    return content


@server.feature("initialize")
def initialize(params: InitializeParams) -> InitializeResult:
    """Handle server initialization."""
    logger.info("Initializing VASP-LSP v%s", __version__)
    logger.info(f"Client: {params.client_info.name if params.client_info else 'Unknown'}")

    capabilities = ServerCapabilities(
        text_document_sync=TextDocumentSyncOptions(
            open_close=True,
            change=TextDocumentSyncKind.Full,
        ),
        completion_provider=CompletionOptions(
            resolve_provider=False,
            trigger_characters=["=", " ", "."],
        ),
        hover_provider=True,
        document_formatting_provider=True,
        document_range_formatting_provider=True,
        document_symbol_provider=True,
        definition_provider=True,
        references_provider=True,
        rename_provider={"prepareProvider": True},
        workspace_symbol_provider=True,
        code_action_provider=CodeActionOptions(
            code_action_kinds=[
                "quickfix",
                "source",
            ]
        ),
        execute_command_provider={
            "commands": [
                "vasp-lsp.diagnosticSnapshot",
                "vasp-lsp.validate",
            ],
        },
    )

    return InitializeResult(capabilities=capabilities)


@server.feature(TEXT_DOCUMENT_DID_OPEN)
def text_document_did_open(params: DidOpenTextDocumentParams):
    """Handle document open."""
    uri = params.text_document.uri
    content = params.text_document.text
    server.set_document_content(uri, content)
    version = _normalise_document_version(getattr(params.text_document, "version", None))
    if version is None:
        version = 0
    server.document_versions[uri] = version

    # Publish diagnostics
    _publish_diagnostics(uri, content, version)


@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def text_document_did_change(params: DidChangeTextDocumentParams):
    """Handle document change."""
    uri = params.text_document.uri
    if params.content_changes:
        previous_content = server.get_document_content(uri) or ""
        content = _apply_content_changes(previous_content, params.content_changes)
        server.set_document_content(uri, content)
        version = _normalise_document_version(
            getattr(params.text_document, "version", None)
        )
        if version is None:
            version = server.document_versions.get(uri, 0) + 1
        server.document_versions[uri] = version
        _publish_diagnostics(uri, content, version)


@server.feature(TEXT_DOCUMENT_DID_CLOSE)
def text_document_did_close(params: DidCloseTextDocumentParams):
    """Release all server state for a closed document."""
    uri = params.text_document.uri
    server.documents.pop(uri, None)
    server.document_versions.pop(uri, None)
    server.diagnostic_versions.pop(uri, None)
    server.document_diagnostics.pop(uri, None)


@server.feature(TEXT_DOCUMENT_DID_SAVE)
def text_document_did_save(params: DidSaveTextDocumentParams):
    """Handle document save."""
    uri = params.text_document.uri
    content = server.get_document_content(uri)
    if content is not None:
        _publish_diagnostics(uri, content, server.document_versions.get(uri))


@server.feature(
    TEXT_DOCUMENT_COMPLETION,
    CompletionOptions(
        resolve_provider=False,
        trigger_characters=["=", " ", "."],
    ),
)
def completions(params: CompletionParams):
    """Handle completion request."""
    uri = params.text_document.uri
    content = server.get_document_content(uri)

    if content is None:
        return None

    return server.completion_provider.get_completions(params, content, uri)


@server.feature(TEXT_DOCUMENT_HOVER)
def hover(params: HoverParams):
    """Handle hover request."""
    uri = params.text_document.uri
    content = server.get_document_content(uri)

    if content is None:
        return None

    return server.hover_provider.get_hover(params, content, uri)


@server.feature(TEXT_DOCUMENT_FORMATTING)
def formatting(params: DocumentFormattingParams):
    """Handle document formatting request."""
    uri = params.text_document.uri
    content = server.get_document_content(uri)

    if content is None:
        return None

    options = {
        "tabSize": params.options.tab_size,
        "insertSpaces": params.options.insert_spaces,
    }

    return server.formatting_provider.format_document(content, uri, options)


@server.feature(TEXT_DOCUMENT_RANGE_FORMATTING)
def range_formatting(params: DocumentRangeFormattingParams):
    """Handle range formatting request."""
    uri = params.text_document.uri
    content = server.get_document_content(uri)

    if content is None:
        return None

    options = {
        "tabSize": params.options.tab_size,
        "insertSpaces": params.options.insert_spaces,
    }

    return server.formatting_provider.format_range(content, uri, params.range, options)


@server.feature(TEXT_DOCUMENT_CODE_ACTION)
def code_action(params: CodeActionParams):
    """Handle code action request."""
    uri = params.text_document.uri
    content = server.get_document_content(uri)

    if content is None:
        return None

    # Get diagnostics for this document
    diagnostics = server.get_document_diagnostics(uri)

    # Filter diagnostics to those in the requested range
    range = params.range

    return server.quickfixes_provider.get_code_actions(content, uri, diagnostics, range)


@server.feature(TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(params: DocumentSymbolParams):
    """Handle document symbol request."""
    uri = params.text_document.uri
    content = server.get_document_content(uri)

    if content is None:
        return []

    return server.navigation_provider.get_symbols(content, uri)


@server.feature(TEXT_DOCUMENT_DEFINITION)
def definition(params: DefinitionParams):
    """Handle go-to-definition requests."""
    uri = params.text_document.uri
    content = server.get_document_content(uri)

    if content is None:
        return None

    return server.navigation_provider.get_definition(content, uri, params.position)


@server.feature(TEXT_DOCUMENT_REFERENCES)
def references(params: ReferenceParams):
    """Handle find-references requests."""
    uri = params.text_document.uri
    content = server.get_document_content(uri)

    if content is None:
        return []

    return server.navigation_provider.get_references(content, uri, params.position)


@server.feature(WORKSPACE_SYMBOL)
def workspace_symbol(params: WorkspaceSymbolParams):
    """Handle workspace symbol queries across open INCAR documents."""
    query = (params.query or "").strip().upper()
    symbols = []
    for uri, content in server.documents.items():
        if _get_file_type(uri) != "INCAR":
            continue
        for document_symbol in server.navigation_provider.get_symbols(content, uri):
            if not query or query in document_symbol.name.upper():
                symbols.append(document_symbol)
    return symbols


@server.feature(TEXT_DOCUMENT_PREPARE_RENAME)
def prepare_rename(params: PrepareRenameParams):
    """Validate rename targets before applying workspace edits."""
    uri = params.text_document.uri
    content = server.get_document_content(uri)

    if content is None:
        return None

    return server.navigation_provider.prepare_rename(content, uri, params.position)


@server.feature(TEXT_DOCUMENT_RENAME)
def rename(params: RenameParams):
    """Handle rename request for INCAR parameters."""
    uri = params.text_document.uri
    content = server.get_document_content(uri)

    if content is None:
        return None

    file_type = _get_file_type(uri)
    if file_type != "INCAR":
        return None

    new_name = params.new_name.upper()
    position = params.position
    lines = content.split("\n")

    if position.line >= len(lines):
        return None

    line = lines[position.line]

    # Find the tag name under cursor
    match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
    if not match:
        return None

    old_name = match.group(1)

    # Check that new_name is a valid INCAR tag or at least a valid identifier
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", new_name):
        return None

    # Rename all occurrences of the tag across open INCAR documents.
    changes: Dict[str, List[TextEdit]] = {}
    for doc_uri, doc_content in server.documents.items():
        if _get_file_type(doc_uri) != "INCAR":
            continue
        doc_lines = doc_content.split("\n")
        doc_edits: List[TextEdit] = []
        for line_idx, doc_line in enumerate(doc_lines):
            tag_match = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=", doc_line)
            if tag_match and tag_match.group(2).upper() == old_name.upper():
                start_char = tag_match.start(2)
                end_char = tag_match.end(2)
                doc_edits.append(
                    TextEdit(
                        range=Range(
                            start=Position(line=line_idx, character=start_char),
                            end=Position(line=line_idx, character=end_char),
                        ),
                        new_text=new_name,
                    )
                )
        if doc_edits:
            changes[doc_uri] = doc_edits

    if not changes:
        return None

    return WorkspaceEdit(changes=changes)


# ---------------------------------------------------------------------------
# Execute command: diagnostic snapshot for agent feedback loops (#18)
# Execute command: optional VASP validate/dry-run (#25)
# ---------------------------------------------------------------------------

# Default timeout for VASP validate/dry-run (seconds).
_DEFAULT_VALIDATE_TIMEOUT = 30


@server.feature("workspace/executeCommand")
def execute_command(params: ExecuteCommandParams):
    """Handle execute command requests.

    Supports:
      - ``vasp-lsp.diagnosticSnapshot``: returns a JSON string with a structured
        diagnostic snapshot for the requested document URI.
      - ``vasp-lsp.validate``: run an optional VASP validate/dry-run command
        and return structured diagnostics.  When no solver binary is
        configured the result contains a clear configuration error.  The
        command respects a caller-supplied ``timeout`` (default 30 s) and
        cleans up any child process on cancellation.
    """
    command = params.command
    arguments = params.arguments or []

    if command == "vasp-lsp.diagnosticSnapshot":
        if not arguments:
            return None
        uri = arguments[0]
        content = server.get_document_content(uri)
        if content is None:
            return None
        snapshot = server.diagnostics_provider.get_diagnostics_snapshot(
            content, uri, server.documents
        )
        return json.dumps(snapshot, default=str)

    if command == "vasp-lsp.validate":
        return _handle_validate(arguments)

    return None


def _handle_validate(arguments: List[Any]) -> str:
    """Run VASP validate/dry-run and return structured JSON diagnostics.

    Arguments:
      [0] document URI
      [1] (optional) path to VASP binary
      [2] (optional) timeout in seconds (default 30)

    Returns a JSON string with keys:
      - status: "success" | "configuration_error" | "timeout" | "error"
      - message: human-readable summary
      - diagnostics: list of diagnostic dicts (when available)
    """
    if not arguments:
        return json.dumps(
            {
                "status": "configuration_error",
                "message": "No document URI provided.",
                "diagnostics": [],
            }
        )

    uri = arguments[0]
    binary_path: Optional[str] = arguments[1] if len(arguments) > 1 else None
    timeout: int = int(arguments[2]) if len(arguments) > 2 else _DEFAULT_VALIDATE_TIMEOUT

    if not binary_path:
        binary_path = os.environ.get("VASP_BINARY") or os.environ.get("VASP_LSP_VASP_BINARY")

    if not binary_path or not os.path.isfile(binary_path):
        return json.dumps(
            {
                "status": "configuration_error",
                "message": (
                    "VASP binary not configured. Set the VASP_BINARY environment "
                    "variable or pass the binary path as the second argument to "
                    "vasp-lsp.validate."
                ),
                "diagnostics": [],
            }
        )

    content = server.get_document_content(uri)
    if content is None:
        return json.dumps(
            {
                "status": "configuration_error",
                "message": f"Document not open: {uri}",
                "diagnostics": [],
            }
        )

    file_type = _get_file_type(uri)
    if file_type == "UNKNOWN":
        return json.dumps(
            {
                "status": "configuration_error",
                "message": "Validate only supports INCAR, POSCAR, and KPOINTS files.",
                "diagnostics": [],
            }
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write the document content to a temp file matching the expected name.
        ext_map = {"INCAR": "INCAR", "POSCAR": "POSCAR", "KPOINTS": "KPOINTS"}
        tmpfile = os.path.join(tmpdir, ext_map.get(file_type, "INCAR"))
        with open(tmpfile, "w") as fh:
            fh.write(content)

        try:
            result = subprocess.run(
                [binary_path, "--dry-run", "--read-from", tmpfile],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
            )
        except subprocess.TimeoutExpired:
            return json.dumps(
                {
                    "status": "timeout",
                    "message": f"VASP validate timed out after {timeout}s.",
                    "diagnostics": [],
                }
            )
        except Exception as exc:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Failed to run VASP binary: {exc}",
                    "diagnostics": [],
                }
            )

    diagnostics = _parse_vasp_output_to_diagnostics(result.stdout, result.stderr, file_type)
    return json.dumps(
        {
            "status": "success",
            "message": f"VASP validate completed with exit code {result.returncode}.",
            "diagnostics": diagnostics,
            "exit_code": result.returncode,
        }
    )


def _parse_vasp_output_to_diagnostics(
    stdout: str, stderr: str, file_type: str
) -> List[Dict[str, Any]]:
    """Parse VASP validate stdout/stderr into structured diagnostic dicts."""
    diagnostics: List[Dict[str, Any]] = []
    combined = stdout + "\n" + stderr
    for line in combined.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        severity = "warning"
        if "error" in lower or "fatal" in lower:
            severity = "error"
        elif "warning" in lower or "warn" in lower:
            severity = "warning"
        elif "info" in lower:
            severity = "information"
        diagnostics.append(
            {
                "message": stripped,
                "severity": severity,
                "source": "vasp-validate",
                "file_type": file_type,
            }
        )
    return diagnostics


def _normalise_document_version(value: Any) -> Optional[int]:
    """Return an LSP document version, if the client supplied one."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _publish_diagnostics(uri: str, content: str, version: Optional[int] = None):
    """Publish diagnostics for a document snapshot and its version."""
    if version is not None:
        previous_version = server.diagnostic_versions.get(uri)
        if previous_version is not None and version < previous_version:
            logger.debug(
                "Skipping stale diagnostics for %s: version %s < %s",
                uri,
                version,
                previous_version,
            )
            return
        server.diagnostic_versions[uri] = version
    diagnostics = server.diagnostics_provider.get_diagnostics(content, uri, server.documents)
    server.set_document_diagnostics(uri, diagnostics)
    server.publish_diagnostics(uri, diagnostics, version=version)


def _get_file_type(uri: str) -> str:
    """Determine file type from URI."""
    return document_kind(uri).value


def main():
    """Main entry point for the VASP-LSP server."""
    parser = argparse.ArgumentParser(description="VASP Language Server")
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Use stdio for communication (default for LSP)",
    )
    parser.add_argument(
        "--tcp",
        action="store_true",
        help="Use TCP for communication",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host address for TCP mode (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=2087,
        help="Port for TCP mode (default: 2087)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args()

    if args.tcp:
        logger.info(f"Starting VASP-LSP server on {args.host}:{args.port}")
        server.start_tcp(args.host, args.port)
    else:
        logger.info("Starting VASP-LSP server on stdio")
        server.start_io()


if __name__ == "__main__":
    main()
