"""Shared document-kind and calculation-workspace primitives.

The LSP adapters and the command-line adapters must make the same decision
about a VASP document and must resolve neighbouring inputs in the same order:
an open, unsaved buffer wins over the file on disk.  This module is the small
interface for that shared behaviour; parsers and diagnostics stay behind it.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Mapping, Optional, Union
from urllib.parse import unquote, urlparse


class DocumentKind(str, Enum):
    """Canonical document kinds understood by VASP-LSP."""

    INCAR = "INCAR"
    POSCAR = "POSCAR"
    KPOINTS = "KPOINTS"
    POTCAR = "POTCAR"
    VASP_LOG = "VASP_LOG"
    UNKNOWN = "UNKNOWN"


PathLike = Union[str, Path]


def uri_to_path(value: PathLike) -> Optional[Path]:
    """Convert a local path or ``file://`` URI to an absolute path.

    Non-file URIs are intentionally rejected because reading neighbours from
    a remote URI would silently violate the workspace interface.
    """
    if isinstance(value, Path):
        return value.expanduser().resolve()

    parsed = urlparse(value)
    if parsed.scheme and parsed.scheme != "file":
        return None
    if parsed.scheme == "file":
        # A few older editor adapters and the project's historical tests use
        # the shorthand ``file://INCAR`` instead of the RFC-style
        # ``file:///path/INCAR``.  Treat a file URI with only a netloc as that
        # local filename; normal file URIs keep using their path component.
        if parsed.netloc and not parsed.path:
            return Path(unquote(parsed.netloc)).expanduser().resolve()
        return Path(unquote(parsed.path)).expanduser().resolve()
    return Path(value).expanduser().resolve()


def path_to_uri(path: PathLike) -> str:
    """Return a stable local file URI for a path."""
    resolved = uri_to_path(path)
    if resolved is None:
        raise ValueError(f"Expected a local path or file URI, got {path!r}")
    return resolved.as_uri()


def _filename(value: PathLike) -> str:
    path = uri_to_path(value)
    if path is not None:
        return path.name.upper()
    return str(value).rsplit("/", 1)[-1].upper()


def _is_named_variant(name: str, stem: str) -> bool:
    """Return whether *name* is a canonical VASP name or a safe variant."""
    return (
        name == stem
        or any(name.startswith(f"{stem}{separator}") for separator in ".-_")
        or name.endswith(f".{stem}")
        or name.endswith(f"_{stem}")
    )


def document_kind(value: PathLike) -> DocumentKind:
    """Classify a VASP document using one canonical filename policy.

    Suffix variants such as ``INCAR.relax`` and ``POSCAR.final`` are accepted
    because they are common in calculation directories.  ``POTCAR.spec`` is
    deliberately excluded: it is VASPKIT metadata, not a POTCAR document.
    """
    name = _filename(value)

    if _is_named_variant(name, "INCAR"):
        return DocumentKind.INCAR
    if _is_named_variant(name, "POSCAR") or _is_named_variant(name, "CONTCAR"):
        return DocumentKind.POSCAR
    if _is_named_variant(name, "KPOINTS"):
        return DocumentKind.KPOINTS
    if _is_named_variant(name, "POTCAR") and name != "POTCAR.SPEC":
        return DocumentKind.POTCAR

    if name in {"OUTCAR", "OSZICAR", "STDOUT", "STDERR", "VASP.OUT", "VASP.ERR"}:
        return DocumentKind.VASP_LOG
    if name.startswith("SLURM-") and name.endswith((".OUT", ".ERR")):
        return DocumentKind.VASP_LOG
    if name.endswith((".OUT", ".LOG")):
        return DocumentKind.VASP_LOG

    return DocumentKind.UNKNOWN


class CalculationWorkspace:
    """Resolve neighbouring calculation files for one anchor document.

    The interface is deliberately small: callers provide the anchor URI and
    currently open document overlays, then ask for a named sibling.  The
    implementation handles URI normalization, case-insensitive VASP names,
    overlay precedence, disk fallback, and unreadable/missing files.
    """

    def __init__(
        self,
        anchor: PathLike,
        open_documents: Optional[Mapping[str, str]] = None,
    ) -> None:
        anchor_path = uri_to_path(anchor)
        if anchor_path is None:
            raise ValueError(f"Workspace anchor must be local: {anchor!r}")
        self.anchor_path = anchor_path
        self.root = anchor_path.parent
        self._open_documents = {
            path_to_uri(uri): content
            for uri, content in (open_documents or {}).items()
            if uri_to_path(uri) is not None
        }

    def read(self, filename: str) -> Optional[str]:
        """Read a sibling from an open overlay first, then from disk."""
        target = (self.root / filename).resolve()
        found, content = self._open_document(filename, target)
        if found:
            return content

        if not target.is_file():
            return None
        try:
            return target.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None

    def has(self, filename: str) -> bool:
        """Return whether a sibling exists in the overlay or on disk."""
        target = (self.root / filename).resolve()
        found, _ = self._open_document(filename, target)
        return found or target.is_file()

    def _open_document(
        self, filename: str, target: Path
    ) -> tuple[bool, Optional[str]]:
        """Return an open overlay matching *filename*, including empty content."""
        target_uri = target.as_uri()
        if target_uri in self._open_documents:
            return True, self._open_documents[target_uri]

        # Preserve the old case-insensitive filename behaviour on Linux while
        # still requiring the sibling to live in the same calculation folder.
        for uri, content in self._open_documents.items():
            overlay_path = uri_to_path(uri)
            if overlay_path is None:
                continue
            if (
                overlay_path.parent == self.root
                and overlay_path.name.upper() == filename.upper()
            ):
                return True, content
        return False, None
