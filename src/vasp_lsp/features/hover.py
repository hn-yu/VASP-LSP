"""Hover documentation provider for VASP-LSP."""

import re
from typing import Optional

from lsprotocol.types import Hover, HoverParams, MarkupContent, MarkupKind, Position

from ..schemas.incar_tags import get_tag_info

_POTCAR_TAG_DOCS = {
    "ENMAX": (
        "https://vasp.at/wiki/POTCAR",
        "Recommended plane-wave cutoff for this pseudopotential in eV. "
        "For a POTCAR containing multiple species, VASP uses the maximum "
        "ENMAX as the default cutoff. ENMAX is read-only POTCAR metadata, "
        "not an INCAR tag; set ENCUT in INCAR to override the default.",
    ),
    "ENMIN": (
        "https://vasp.at/wiki/POTCAR",
        "Minimum viable plane-wave cutoff for this pseudopotential in eV. "
        "For a POTCAR containing multiple species, VASP uses the maximum "
        "ENMIN. ENMIN is read-only POTCAR metadata, not an INCAR tag.",
    ),
}
_POTCAR_VALUE_RE = re.compile(
    r"\b(?P<name>ENMAX|ENMIN)\s*=\s*(?P<value>[-+]?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


class HoverProvider:
    """Provides hover documentation for VASP files."""

    def __init__(self):
        """Initialize hover provider."""
        pass

    def get_hover(
        self, params: HoverParams, document_content: str, document_uri: str
    ) -> Optional[Hover]:
        """Get hover documentation for the current cursor position.

        Args:
            params: Hover parameters from LSP client.
            document_content: Full document content.
            document_uri: Document URI to determine file type.

        Returns:
            Hover object with documentation, or None if no relevant info.
        """
        file_type = self._get_file_type(document_uri)
        position = params.position

        if file_type == "INCAR":
            return self._get_incar_hover(document_content, position)
        elif file_type == "POTCAR":
            return self._get_potcar_hover(document_content, position)
        elif file_type == "POSCAR":
            return self._get_poscar_hover(document_content, position)
        elif file_type == "KPOINTS":
            return self._get_kpoints_hover(document_content, position)

        return None

    def _get_file_type(self, uri: str) -> str:
        """Determine file type from URI.

        Args:
            uri: Document URI.

        Returns:
            File type string.
        """
        filename = uri.split("/")[-1].upper()

        if "INCAR" in filename:
            return "INCAR"
        if "POTCAR" in filename:
            return "POTCAR"
        if "POSCAR" in filename or "CONTCAR" in filename:
            return "POSCAR"
        if "KPOINTS" in filename:
            return "KPOINTS"

        return "UNKNOWN"

    def _get_incar_hover(self, content: str, position: Position) -> Optional[Hover]:
        """Get hover info for INCAR files.

        Args:
            content: Document content.
            position: Cursor position.

        Returns:
            Hover object if a tag is found under cursor.
        """
        lines = content.split("\n")
        if position.line >= len(lines):
            return None

        line = lines[position.line]

        # Extract word under cursor
        word = self._get_word_at_position(line, position.character)
        if not word:
            return None

        # Try to get tag info
        tag = get_tag_info(word)
        if tag:
            return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=tag.to_markdown()))

        return None

    def _get_potcar_hover(self, content: str, position: Position) -> Optional[Hover]:
        """Get documentation for supported read-only POTCAR metadata tags."""
        lines = content.split("\n")
        if position.line >= len(lines):
            return None

        line = lines[position.line]
        word = self._get_word_at_position(line, position.character).upper()
        if word not in _POTCAR_TAG_DOCS:
            return None

        source_url, description = _POTCAR_TAG_DOCS[word]
        value_match = _POTCAR_VALUE_RE.search(line)
        value = value_match.group("value") if value_match else "not available on this line"
        value_text = f"Value: {value} eV" if value_match else f"Value: {value}"
        return Hover(
            contents=MarkupContent(
                kind=MarkupKind.Markdown,
                value="\n".join(
                    [
                        source_url,
                        "",
                        f"{word} (POTCAR metadata)",
                        "",
                        value_text,
                        "",
                        description,
                    ]
                ),
            )
        )

    def _get_poscar_hover(self, content: str, position: Position) -> Optional[Hover]:
        """Get hover info for POSCAR files.

        Args:
            content: Document content.
            position: Cursor position.

        Returns:
            Hover object with line-specific documentation.
        """
        line_docs = {
            0: (
                "**System Comment**",
                "A description of the system. This is written to output files.",
            ),
            1: (
                "**Scale Factor**",
                'Universal scaling factor for lattice vectors and coordinates. "1.0" for no scaling.',
            ),
            2: (
                "**Lattice Vector 1**",
                "First lattice vector in Å (scaled by scale factor).",
            ),
            3: (
                "**Lattice Vector 2**",
                "Second lattice vector in Å (scaled by scale factor).",
            ),
            4: (
                "**Lattice Vector 3**",
                "Third lattice vector in Å (scaled by scale factor).",
            ),
            5: ("**Atom Types**", "Element symbols for each species (VASP 5 format)."),
            6: ("**Atom Counts**", "Number of atoms for each species."),
            7: (
                "**Coordinate Type**",
                "Direct (fractional) or Cartesian (in Å, scaled by scale factor).",
            ),
        }

        if position.line in line_docs:
            title, description = line_docs[position.line]
            return Hover(
                contents=MarkupContent(kind=MarkupKind.Markdown, value=f"{title}\n\n{description}")
            )

        return None

    def _get_kpoints_hover(self, content: str, position: Position) -> Optional[Hover]:
        """Get hover info for KPOINTS files.

        Args:
            content: Document content.
            position: Cursor position.

        Returns:
            Hover object with line-specific documentation.
        """
        line_docs = {
            0: ("**Comment**", "A comment describing the k-point set."),
            1: (
                "**K-point Count/Mode**",
                "Number of k-points (0 for automatic), or 'A' for fully automatic, or 'Line-mode'.",
            ),
            2: (
                "**Generation Scheme**",
                "Gamma-centered (G), Monkhorst-Pack (M), Cartesian (C/K), or Reciprocal (R).",
            ),
        }

        if position.line in line_docs:
            title, description = line_docs[position.line]
            return Hover(
                contents=MarkupContent(kind=MarkupKind.Markdown, value=f"{title}\n\n{description}")
            )

        return None

    def _get_word_at_position(self, line: str, column: int) -> str:
        """Extract the word at the given column position.

        Args:
            line: The line text.
            column: Column position (0-indexed).

        Returns:
            Word at position, or empty string.
        """
        if not line or column < 0 or column >= len(line):
            return ""

        # Find word boundaries
        start = column
        end = column

        # Move left to find start
        while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
            start -= 1

        # Move right to find end
        while end < len(line) and (line[end].isalnum() or line[end] == "_"):
            end += 1

        return line[start:end].strip()
