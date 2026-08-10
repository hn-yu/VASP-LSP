"""Completion provider for VASP-LSP."""

from typing import List

from lsprotocol.types import (
    CompletionItem,
    CompletionItemKind,
    CompletionList,
    CompletionParams,
)

from ..schemas.incar_tags import INCAR_TAG_LIST, INCAR_TAGS


class CompletionProvider:
    """Provides autocomplete functionality for VASP files."""

    def __init__(self):
        """Initialize completion provider."""
        self.incar_tags = sorted(INCAR_TAG_LIST)

    def get_completions(
        self, params: CompletionParams, document_content: str, document_uri: str
    ) -> CompletionList:
        """Get completion items for the current cursor position.

        Args:
            params: Completion parameters from LSP client.
            document_content: Full document content.
            document_uri: Document URI to determine file type.

        Returns:
            CompletionList with relevant items.
        """
        file_type = self._get_file_type(document_uri)
        position = params.position

        # Get the current line and word being typed
        lines = document_content.split("\n")
        if position.line >= len(lines):
            return CompletionList(is_incomplete=False, items=[])

        current_line = lines[position.line]
        line_prefix = current_line[: position.character]

        if file_type == "INCAR":
            items = self._get_incar_completions(line_prefix, current_line)
        elif file_type == "POSCAR":
            items = self._get_poscar_completions(position.line)
        elif file_type == "KPOINTS":
            items = self._get_kpoints_completions(position.line)
        else:
            items = []

        return CompletionList(is_incomplete=False, items=items)

    def _get_file_type(self, uri: str) -> str:
        """Determine file type from URI.

        Args:
            uri: Document URI.

        Returns:
            File type string (INCAR, POSCAR, KPOINTS, or UNKNOWN).
        """
        filename = uri.split("/")[-1].upper()

        # Check for exact matches
        if filename in ["INCAR", "INCAR.", "INCAR.VASP"]:
            return "INCAR"
        if filename in ["POSCAR", "POSCAR.", "CONTCAR", "CONTCAR."]:
            return "POSCAR"
        if filename in ["KPOINTS", "KPOINTS.", "KPOINTS.VASP"]:
            return "KPOINTS"

        # Check for prefixes
        if filename.startswith("INCAR"):
            return "INCAR"
        if filename.startswith("POSCAR") or filename.startswith("CONTCAR"):
            return "POSCAR"
        if filename.startswith("KPOINTS"):
            return "KPOINTS"

        return "UNKNOWN"

    def _get_incar_completions(self, line_prefix: str, current_line: str) -> List[CompletionItem]:
        """Get completion items for INCAR files.

        Args:
            line_prefix: Text before cursor on current line.
            current_line: Full current line.

        Returns:
            List of completion items.
        """
        items = []

        # Check if we're typing a tag name (before '=' or at start of line)
        if "=" not in line_prefix:
            # Get the partial word being typed
            words = line_prefix.strip().split()
            partial = words[-1] if words else ""

            # Prefer tags that start with the query.  Substring matching is
            # still useful for less familiar tags (for example, ELPH_ISMEAR),
            # but it should not hide the direct ISMEAR match.
            partial_upper = partial.upper()
            prefix_matches = [tag for tag in self.incar_tags if tag.startswith(partial_upper)]
            if prefix_matches:
                matching_tags = [(0, tag) for tag in prefix_matches]
            else:
                matching_tags = [
                    (1, tag) for tag in self.incar_tags if partial_upper in tag
                ]
            matching_tags.sort()

            for match_rank, tag_name in matching_tags[:50]:  # Limit to 50 results
                tag = INCAR_TAGS.get(tag_name)
                if tag:
                    item = CompletionItem(
                        label=tag_name,
                        kind=CompletionItemKind.Keyword,
                        detail=f"{tag.type} (default: {tag.default})",
                        documentation=(
                            tag.description[:200] + "..."
                            if len(tag.description) > 200
                            else tag.description
                        ),
                        insert_text=f"{tag_name} = ",
                        sort_text=f"{match_rank}:{tag_name}",
                    )
                    items.append(item)

        else:
            # We're after '=', provide value completions
            tag_name = line_prefix.split("=")[0].strip().upper()
            tag = INCAR_TAGS.get(tag_name)

            if tag and tag.enum_values:
                for value in tag.enum_values:
                    item = CompletionItem(
                        label=value,
                        kind=CompletionItemKind.EnumMember,
                        detail=f"Valid value for {tag_name}",
                        insert_text=value,
                    )
                    items.append(item)

            elif tag and tag.type == "boolean":
                for value in [".TRUE.", ".FALSE."]:
                    item = CompletionItem(
                        label=value,
                        kind=CompletionItemKind.EnumMember,
                        insert_text=value,
                    )
                    items.append(item)

        return items

    def _get_poscar_completions(self, line_number: int) -> List[CompletionItem]:
        """Get completion items for POSCAR files.

        Args:
            line_number: Current line number.

        Returns:
            List of completion items.
        """
        items = []

        # Line-specific completions for POSCAR
        if line_number == 0:
            # System comment
            item = CompletionItem(
                label="System description",
                kind=CompletionItemKind.Text,
                detail="System comment",
                insert_text="System name",
            )
            items.append(item)

        elif line_number == 1:
            # Scale factor
            item = CompletionItem(
                label="1.0",
                kind=CompletionItemKind.Value,
                detail="Scale factor (unity)",
                insert_text="1.0",
            )
            items.append(item)

        elif line_number in [2, 3, 4]:
            # Lattice vectors
            item = CompletionItem(
                label="1.0 0.0 0.0",
                kind=CompletionItemKind.Snippet,
                detail=f"Lattice vector {line_number - 1}",
                insert_text="1.0 0.0 0.0",
            )
            items.append(item)

        elif line_number == 5:
            # Atom types
            item = CompletionItem(
                label="H He Li",
                kind=CompletionItemKind.Snippet,
                detail="Example atom types",
                insert_text="H He Li",
            )
            items.append(item)

        elif line_number == 6:
            # Atom counts
            item = CompletionItem(
                label="2 4 1",
                kind=CompletionItemKind.Snippet,
                detail="Example atom counts",
                insert_text="2 4 1",
            )
            items.append(item)

        return items

    def _get_kpoints_completions(self, line_number: int) -> List[CompletionItem]:
        """Get completion items for KPOINTS files.

        Args:
            line_number: Current line number.

        Returns:
            List of completion items.
        """
        items = []

        if line_number == 1:
            # Number of k-points or mode
            items.extend(
                [
                    CompletionItem(
                        label="0",
                        kind=CompletionItemKind.Value,
                        detail="Automatic mode (requires 3x3x3 grid)",
                        insert_text="0",
                    ),
                    CompletionItem(
                        label="Gamma",
                        kind=CompletionItemKind.EnumMember,
                        detail="Gamma-centered grid",
                        insert_text="Gamma\n4 4 4\n0 0 0",
                    ),
                    CompletionItem(
                        label="Monkhorst",
                        kind=CompletionItemKind.EnumMember,
                        detail="Monkhorst-Pack grid",
                        insert_text="Monkhorst\n4 4 4\n0 0 0",
                    ),
                    CompletionItem(
                        label="Line-mode",
                        kind=CompletionItemKind.Snippet,
                        detail="Line mode for band structure",
                        insert_text="Line-mode\n20\nReciprocal",
                    ),
                ]
            )

        elif line_number == 2:
            items.extend(
                [
                    CompletionItem(
                        label="4 4 4",
                        kind=CompletionItemKind.Snippet,
                        detail="4x4x4 k-point grid",
                        insert_text="4 4 4",
                    ),
                    CompletionItem(
                        label="6 6 6",
                        kind=CompletionItemKind.Snippet,
                        detail="6x6x6 k-point grid",
                        insert_text="6 6 6",
                    ),
                    CompletionItem(
                        label="8 8 8",
                        kind=CompletionItemKind.Snippet,
                        detail="8x8x8 k-point grid",
                        insert_text="8 8 8",
                    ),
                ]
            )

        return items
