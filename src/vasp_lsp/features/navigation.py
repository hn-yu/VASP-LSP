"""Document symbols provider for VASP-LSP.

Provides document symbol information for navigation features (outline view,
breadcrumb navigation, go-to-symbol) in LSP editors.
"""

import re
from typing import List, Optional, Tuple

from lsprotocol.types import (
    DocumentSymbol,
    Location,
    Position,
    Range,
    SymbolKind,
)

from ..workspace import document_kind

_INCAR_TAG_RE = re.compile(r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=")


class DocumentSymbolsProvider:
    """Provides document symbol information for VASP files."""

    def __init__(self):
        """Initialize document symbols provider."""
        pass

    def get_symbols(self, content: str, document_uri: str) -> List[DocumentSymbol]:
        """Get document symbols for the given content.

        Args:
            content: Full document content.
            document_uri: Document URI to determine file type.

        Returns:
            List of DocumentSymbol objects representing the document outline.
        """
        file_type = self._get_file_type(document_uri)

        if file_type == "INCAR":
            return self._get_incar_symbols(content)
        elif file_type == "POSCAR":
            return self._get_poscar_symbols(content)
        elif file_type == "KPOINTS":
            return self._get_kpoints_symbols(content)

        return []

    def _get_file_type(self, uri: str) -> str:
        """Determine file type from URI."""
        return document_kind(uri).value

    def _get_incar_symbols(self, content: str) -> List[DocumentSymbol]:
        """Get document symbols for INCAR files.

        Each parameter assignment becomes a symbol with its tag name.
        """
        symbols = []
        lines = content.split("\n")
        param_regex = re.compile(
            r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>[^#!]*)",
            re.IGNORECASE,
        )

        for line_idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("!"):
                continue

            match = param_regex.match(line)
            if match:
                name = match.group("name").upper()
                value_str = match.group("value").strip()
                # Remove trailing comments
                value_str = re.sub(r"[#!].*$", "", value_str).strip()

                symbols.append(
                    DocumentSymbol(
                        name=name,
                        kind=SymbolKind.Property,
                        range=Range(
                            start=Position(line=line_idx, character=0),
                            end=Position(line=line_idx, character=len(line)),
                        ),
                        selection_range=Range(
                            start=Position(
                                line=line_idx,
                                character=match.start("name"),
                            ),
                            end=Position(
                                line=line_idx,
                                character=match.end("name"),
                            ),
                        ),
                        detail=f"= {value_str}" if value_str else "",
                    )
                )

        return symbols

    def _get_poscar_symbols(self, content: str) -> List[DocumentSymbol]:
        """Get document symbols for POSCAR files.

        Expose structural sections: comment, scale factor, lattice, atoms, coordinates.
        """
        symbols = []
        lines = content.split("\n")

        if not lines:
            return []

        # System comment (line 0)
        if lines[0].strip():
            symbols.append(
                DocumentSymbol(
                    name="System Comment",
                    kind=SymbolKind.String,
                    range=Range(
                        start=Position(line=0, character=0),
                        end=Position(line=0, character=len(lines[0])),
                    ),
                    selection_range=Range(
                        start=Position(line=0, character=0),
                        end=Position(line=0, character=len(lines[0])),
                    ),
                    detail=lines[0].strip(),
                )
            )

        # Scale factor (line 1)
        if len(lines) > 1:
            symbols.append(
                DocumentSymbol(
                    name="Scale Factor",
                    kind=SymbolKind.Number,
                    range=Range(
                        start=Position(line=1, character=0),
                        end=Position(line=1, character=len(lines[1])),
                    ),
                    selection_range=Range(
                        start=Position(line=1, character=0),
                        end=Position(line=1, character=len(lines[1])),
                    ),
                    detail=lines[1].strip(),
                )
            )

        # Lattice vectors (lines 2-4)
        if len(lines) >= 5:
            lattice_children = []
            for i in range(2, 5):
                if i < len(lines):
                    lattice_children.append(
                        DocumentSymbol(
                            name=f"Vector {i - 1}",
                            kind=SymbolKind.Number,
                            range=Range(
                                start=Position(line=i, character=0),
                                end=Position(line=i, character=len(lines[i])),
                            ),
                            selection_range=Range(
                                start=Position(line=i, character=0),
                                end=Position(line=i, character=len(lines[i])),
                            ),
                            detail=lines[i].strip(),
                        )
                    )

            symbols.append(
                DocumentSymbol(
                    name="Lattice",
                    kind=SymbolKind.Struct,
                    range=Range(
                        start=Position(line=2, character=0),
                        end=Position(line=4, character=len(lines[4]) if 4 < len(lines) else 0),
                    ),
                    selection_range=Range(
                        start=Position(line=2, character=0),
                        end=Position(line=2, character=len(lines[2]) if 2 < len(lines) else 0),
                    ),
                    children=lattice_children,
                )
            )

        # Atom types (line 5)
        if len(lines) > 5:
            symbols.append(
                DocumentSymbol(
                    name="Atom Types",
                    kind=SymbolKind.Class,
                    range=Range(
                        start=Position(line=5, character=0),
                        end=Position(line=5, character=len(lines[5])),
                    ),
                    selection_range=Range(
                        start=Position(line=5, character=0),
                        end=Position(line=5, character=len(lines[5])),
                    ),
                    detail=lines[5].strip(),
                )
            )

        # Atom counts (line 6)
        if len(lines) > 6:
            symbols.append(
                DocumentSymbol(
                    name="Atom Counts",
                    kind=SymbolKind.Number,
                    range=Range(
                        start=Position(line=6, character=0),
                        end=Position(line=6, character=len(lines[6])),
                    ),
                    selection_range=Range(
                        start=Position(line=6, character=0),
                        end=Position(line=6, character=len(lines[6])),
                    ),
                    detail=lines[6].strip(),
                )
            )

        # Coordinate type + coordinates
        if len(lines) > 7:
            coord_line = lines[7].strip().upper()
            coord_type = "Direct" if coord_line.startswith("D") else "Cartesian"
            coord_start = 7

            # Find coordinate lines
            coord_end = 7
            for i in range(8, len(lines)):
                stripped = lines[i].strip()
                if not stripped or stripped.startswith("#"):
                    continue
                parts = stripped.split()
                if len(parts) >= 3:
                    try:
                        [float(parts[0]), float(parts[1]), float(parts[2])]
                        coord_end = i
                    except ValueError:
                        break
                else:
                    break

            if coord_end > 7:
                symbols.append(
                    DocumentSymbol(
                        name="Coordinates",
                        kind=SymbolKind.Array,
                        range=Range(
                            start=Position(line=coord_start, character=0),
                            end=Position(line=coord_end, character=len(lines[coord_end])),
                        ),
                        selection_range=Range(
                            start=Position(line=coord_start, character=0),
                            end=Position(
                                line=coord_start,
                                character=len(lines[coord_start]),
                            ),
                        ),
                        detail=coord_type,
                    )
                )

        return symbols

    def _get_kpoints_symbols(self, content: str) -> List[DocumentSymbol]:
        """Get document symbols for KPOINTS files."""
        symbols = []
        lines = content.split("\n")

        if not lines:
            return []

        # Comment (line 0)
        if lines[0].strip():
            symbols.append(
                DocumentSymbol(
                    name="Comment",
                    kind=SymbolKind.String,
                    range=Range(
                        start=Position(line=0, character=0),
                        end=Position(line=0, character=len(lines[0])),
                    ),
                    selection_range=Range(
                        start=Position(line=0, character=0),
                        end=Position(line=0, character=len(lines[0])),
                    ),
                    detail=lines[0].strip(),
                )
            )

        # Mode / count (line 1)
        if len(lines) > 1:
            line1 = lines[1].strip()
            if line1.lower() == "0":
                mode_label = "Automatic grid"
            elif line1.lower() in ("a", "automatic"):
                mode_label = "Fully automatic"
            elif "line" in line1.lower():
                mode_label = "Line-mode"
            else:
                mode_label = f"{line1} k-points"

            symbols.append(
                DocumentSymbol(
                    name="Mode",
                    kind=SymbolKind.EnumMember,
                    range=Range(
                        start=Position(line=1, character=0),
                        end=Position(line=1, character=len(lines[1])),
                    ),
                    selection_range=Range(
                        start=Position(line=1, character=0),
                        end=Position(line=1, character=len(lines[1])),
                    ),
                    detail=mode_label,
                )
            )

        # Generation scheme (line 2)
        if len(lines) > 2:
            line2 = lines[2].strip()
            symbols.append(
                DocumentSymbol(
                    name="Generation",
                    kind=SymbolKind.EnumMember,
                    range=Range(
                        start=Position(line=2, character=0),
                        end=Position(line=2, character=len(lines[2])),
                    ),
                    selection_range=Range(
                        start=Position(line=2, character=0),
                        end=Position(line=2, character=len(lines[2])),
                    ),
                    detail=line2,
                )
            )

        # Grid (line 3)
        if len(lines) > 3:
            line3 = lines[3].strip()
            symbols.append(
                DocumentSymbol(
                    name="Grid",
                    kind=SymbolKind.Number,
                    range=Range(
                        start=Position(line=3, character=0),
                        end=Position(line=3, character=len(lines[3])),
                    ),
                    selection_range=Range(
                        start=Position(line=3, character=0),
                        end=Position(line=3, character=len(lines[3])),
                    ),
                    detail=line3,
                )
            )

        # Additional k-points (lines 4+)
        if len(lines) > 4:
            kpoint_lines = []
            for i in range(4, len(lines)):
                stripped = lines[i].strip()
                if not stripped or stripped.startswith("#"):
                    continue
                parts = stripped.split()
                if len(parts) >= 3:
                    try:
                        [float(parts[0]), float(parts[1]), float(parts[2])]
                        kpoint_lines.append(i)
                    except ValueError:
                        continue

            if kpoint_lines:
                last = kpoint_lines[-1]
                symbols.append(
                    DocumentSymbol(
                        name="K-points",
                        kind=SymbolKind.Array,
                        range=Range(
                            start=Position(line=4, character=0),
                            end=Position(line=last, character=len(lines[last])),
                        ),
                        selection_range=Range(
                            start=Position(line=4, character=0),
                            end=Position(line=4, character=len(lines[4])),
                        ),
                        detail=f"{len(kpoint_lines)} points",
                    )
                )

        return symbols

    def find_incar_tag_at_position(self, content: str, position: Position) -> Optional[str]:
        """Return the INCAR tag name at ``position``, if any."""
        lines = content.split("\n")
        if position.line >= len(lines):
            return None
        match = _INCAR_TAG_RE.match(lines[position.line])
        if not match:
            return None
        start = match.start("name")
        end = match.end("name")
        if position.character < start or position.character > end:
            return None
        return match.group("name").upper()

    def find_incar_tag_occurrences(self, content: str) -> List[Tuple[str, int, int, int]]:
        """Return ``(tag, line, start, end)`` tuples for INCAR assignments."""
        occurrences: List[Tuple[str, int, int, int]] = []
        for line_idx, line in enumerate(content.split("\n")):
            match = _INCAR_TAG_RE.match(line)
            if match:
                occurrences.append(
                    (
                        match.group("name").upper(),
                        line_idx,
                        match.start("name"),
                        match.end("name"),
                    )
                )
        return occurrences

    def get_definition(
        self, content: str, document_uri: str, position: Position
    ) -> Optional[Location]:
        """Go to the first definition of an INCAR tag."""
        if self._get_file_type(document_uri) != "INCAR":
            return None
        tag = self.find_incar_tag_at_position(content, position)
        if tag is None:
            return None
        for name, line_idx, start, end in self.find_incar_tag_occurrences(content):
            if name == tag:
                return Location(
                    uri=document_uri,
                    range=Range(
                        start=Position(line=line_idx, character=start),
                        end=Position(line=line_idx, character=end),
                    ),
                )
        return None

    def get_references(self, content: str, document_uri: str, position: Position) -> List[Location]:
        """Find all references to an INCAR tag in the current document."""
        if self._get_file_type(document_uri) != "INCAR":
            return []
        tag = self.find_incar_tag_at_position(content, position)
        if tag is None:
            return []
        return [
            Location(
                uri=document_uri,
                range=Range(
                    start=Position(line=line_idx, character=start),
                    end=Position(line=line_idx, character=end),
                ),
            )
            for name, line_idx, start, end in self.find_incar_tag_occurrences(content)
            if name == tag
        ]

    def prepare_rename(
        self, content: str, document_uri: str, position: Position
    ) -> Optional[Range]:
        """Return the renameable range for an INCAR tag, if supported."""
        if self._get_file_type(document_uri) != "INCAR":
            return None
        lines = content.split("\n")
        if position.line >= len(lines):
            return None
        match = _INCAR_TAG_RE.match(lines[position.line])
        if not match:
            return None
        start = match.start("name")
        end = match.end("name")
        if position.character < start or position.character > end:
            return None
        return Range(
            start=Position(line=position.line, character=start),
            end=Position(line=position.line, character=end),
        )


# Module-level convenience function
def get_document_symbols(content: str, document_uri: str) -> List[DocumentSymbol]:
    """Get document symbols for the given content and URI.

    Args:
        content: Full document content.
        document_uri: Document URI to determine file type.

    Returns:
        List of DocumentSymbol objects.
    """
    provider = DocumentSymbolsProvider()
    return provider.get_symbols(content, document_uri)
