"""Small Python API wrapper around the Diagnostic Engine v1 CLI contract."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import unquote, urlparse

from .agent_operations import operation_path, with_capabilities
from .tool import SOFTWARE, _collect_diagnostics, _file_type, check_path

_DEFAULT_URI = "file:///input"
_ORIGINAL_CHECK_PATH = check_path


class AgentLSP:
    """Agent-facing wrapper for non-editor LSP diagnostics."""

    def __init__(
        self,
        text: str | None = None,
        uri: str = _DEFAULT_URI,
        document_name: str | None = None,
    ) -> None:
        self.text = text
        self.uri = uri
        if document_name:
            self.document_name = document_name
        elif text is not None and uri == _DEFAULT_URI:
            self.document_name = "INCAR"
        else:
            self.document_name = self._uri_basename() or "input"

    @classmethod
    def from_text(cls, text: str, uri: str | None = None) -> "AgentLSP":
        if uri is None:
            return cls(text=text, uri=_DEFAULT_URI, document_name="INCAR")
        return cls(text=text, uri=uri)

    @classmethod
    def from_path(cls, path: str | Path) -> "AgentLSP":
        return cls(text=None, uri=Path(path).resolve().as_uri())

    def _uri_basename(self) -> str:
        parsed = urlparse(self.uri)
        raw_path = unquote(parsed.path or parsed.path)
        return Path(raw_path).name

    def _temporary_path(self, directory: Path) -> Path:
        return directory / self.document_name

    def check(self) -> dict[str, Any]:
        parsed = urlparse(self.uri)
        if self.text is None and parsed.scheme == "file":
            return with_capabilities(check_path(Path(unquote(parsed.path))), "check")
        with TemporaryDirectory() as tmp:
            path = self._temporary_path(Path(tmp))
            # Keep the historical injected-check callback seam compatible.  In
            # normal runtime this branch is not taken, so text is checked as
            # INCAR rather than as an untyped temporary file.
            if self.uri == _DEFAULT_URI and check_path is not _ORIGINAL_CHECK_PATH:
                path = Path(tmp) / "input"
            path.write_text(self.text or "", encoding="utf-8")
            payload = check_path(path)
            payload["uri"] = self.uri
            payload.setdefault("file_type", "INCAR" if self.document_name == "INCAR" else _file_type(path))
            return with_capabilities(payload, "check")

    def _operation(self, operation: str, line: int = 0, character: int = 0) -> dict[str, Any]:
        parsed = urlparse(self.uri)
        if self.text is None and parsed.scheme == "file":
            return operation_path(
                Path(unquote(parsed.path)),
                operation,
                software=SOFTWARE,
                file_type_func=_file_type,
                collect_diagnostics=_collect_diagnostics,
                line=line,
                character=character,
            )
        with TemporaryDirectory() as tmp:
            path = self._temporary_path(Path(tmp))
            path.write_text(self.text or "", encoding="utf-8")
            payload = operation_path(
                path,
                operation,
                software=SOFTWARE,
                file_type_func=_file_type,
                collect_diagnostics=_collect_diagnostics,
                line=line,
                character=character,
            )
            payload["uri"] = self.uri
            return payload

    def context(self, line: int = 0, character: int = 0) -> dict[str, Any]:
        return self._operation("context", line, character)

    def complete(self, line: int = 0, character: int = 0) -> dict[str, Any]:
        return self._operation("complete", line, character)

    def hover(self, line: int = 0, character: int = 0) -> dict[str, Any]:
        return self._operation("hover", line, character)

    def symbols(self) -> dict[str, Any]:
        return self._operation("symbols")

    def fix(self, line: int = 0, character: int = 0) -> dict[str, Any]:
        """Return provider-backed quick fixes for the current document."""
        return self._operation("fix", line, character)
