"""Formatting provider for VASP-LSP.

Provides document formatting capabilities for VASP input files.
"""

import re
from typing import List, Optional

from lsprotocol.types import Position, Range, TextEdit

from ..parsers.incar_parser import INCARParser

_INCAR_ASSIGNMENT_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


class FormattingProvider:
    """Provides document formatting for VASP files."""

    def __init__(self):
        """Initialize formatting provider."""
        pass

    def format_document(
        self, document_content: str, document_uri: str, options: Optional[dict] = None
    ) -> List[TextEdit]:
        """Format the entire document.

        Args:
            document_content: Full document content.
            document_uri: Document URI to determine file type.
            options: Formatting options (tabSize, insertSpaces, etc.).

        Returns:
            List of text edits to apply.
        """
        file_type = self._get_file_type(document_uri)

        if file_type == "INCAR":
            return self._format_incar(document_content)
        elif file_type == "POSCAR":
            return self._format_poscar(document_content)
        elif file_type == "KPOINTS":
            return self._format_kpoints(document_content)

        return []

    def format_range(
        self,
        document_content: str,
        document_uri: str,
        range_obj: Range,
        options: Optional[dict] = None,
    ) -> List[TextEdit]:
        """Format only the requested range when it can be done safely."""
        if self._get_file_type(document_uri) != "INCAR":
            return []

        lines = document_content.split("\n")
        if not lines:
            return []

        start_line = max(range_obj.start.line, 0)
        end_line = min(range_obj.end.line, len(lines) - 1)
        if start_line > end_line:
            return []

        edits: List[TextEdit] = []
        for line_idx in range(start_line, end_line + 1):
            line = lines[line_idx]
            match = _INCAR_ASSIGNMENT_RE.match(line)
            if not match:
                continue
            indent, name, value = match.groups()
            value = re.sub(r"[#!].*$", "", value).strip()
            new_line = f"{indent}{name.upper()} = {value}"
            if new_line != line:
                edits.append(
                    TextEdit(
                        range=Range(
                            start=Position(line=line_idx, character=0),
                            end=Position(line=line_idx, character=len(line)),
                        ),
                        new_text=new_line,
                    )
                )
        return edits

    def _get_file_type(self, uri: str) -> str:
        """Determine file type from URI."""
        filename = uri.split("/")[-1].upper()

        if "INCAR" in filename:
            return "INCAR"
        if "POSCAR" in filename or "CONTCAR" in filename:
            return "POSCAR"
        if "KPOINTS" in filename:
            return "KPOINTS"

        return "UNKNOWN"

    def _format_incar(self, content: str) -> List[TextEdit]:
        """Format INCAR file content.

        Formatting rules:
        - Sort parameters alphabetically within groups
        - Consistent spacing around =
        - Group related parameters
        - Align values
        """
        parser = INCARParser(content)
        params = parser.parse()

        if not params:
            return []

        formatted_lines = []
        formatted_lines.append("# VASP INCAR file")
        formatted_lines.append("")

        electronic = []
        ionic = []
        mixing = []
        parallel = []
        other = []

        electronic_tags = {
            "PREC",
            "ISPIN",
            "MAGMOM",
            "NELM",
            "NELMIN",
            "NELMDL",
            "EDIFF",
            "LREAL",
            "ENCUT",
            "ENAUG",
            "ISMEAR",
            "SIGMA",
            "LWAVE",
            "LCHARG",
            "LVTOT",
            "LVHAR",
            "LELF",
            "LORBIT",
            "NEDOS",
            "EMIN",
            "EMAX",
            "ISYM",
            "SYMPREC",
            "NBANDS",
            "NWRITE",
            "LASPH",
            "METAGGA",
            "LHFCALC",
            "HFSCREEN",
            "PRECFOCK",
            "LDAU",
            "LDAUTYPE",
            "LDAUL",
            "LDAUU",
            "LDAUJ",
        }

        ionic_tags = {
            "IBRION",
            "NSW",
            "ISIF",
            "PSTRESS",
            "EDIFFG",
            "POTIM",
            "SMASS",
            "TEBEG",
            "TEEND",
            "NFREE",
            "POMASS",
            "ZVAL",
        }

        mixing_tags = {
            "ALGO",
            "IALGO",
            "LDIAG",
            "BMIX",
            "AMIX",
            "BMIX_MAG",
            "AMIX_MAG",
            "AMIN",
            "WC",
            "INIMIX",
            "MAXMIX",
            "MIXPRE",
        }

        parallel_tags = {"NCORE", "NPAR", "KPAR", "LPLANE", "LSCALU", "NSIM"}

        for name, param in params.items():
            if name in electronic_tags:
                electronic.append(param)
            elif name in ionic_tags:
                ionic.append(param)
            elif name in mixing_tags:
                mixing.append(param)
            elif name in parallel_tags:
                parallel.append(param)
            else:
                other.append(param)

        all_params = list(params.values())
        max_tag_len = max(len(p.name) for p in all_params) if all_params else 0

        def format_group(name: str, group):
            if not group:
                return
            formatted_lines.append(f"# {name}")
            for param in sorted(group, key=lambda x: x.name):
                value_str = self._format_value(param.value)
                line = f"{param.name:<{max_tag_len}} = {value_str}"
                formatted_lines.append(line)
            formatted_lines.append("")

        format_group("Electronic Structure", electronic)
        format_group("Ionic Relaxation", ionic)
        format_group("Mixing and Convergence", mixing)
        format_group("Parallelization", parallel)
        format_group("Other Parameters", other)

        if formatted_lines and formatted_lines[-1] == "":
            formatted_lines.pop()

        formatted_content = "\n".join(formatted_lines)
        lines = content.split("\n")
        end_line = len(lines) - 1
        end_char = len(lines[end_line]) if lines else 0

        return [
            TextEdit(
                range=Range(
                    start=Position(line=0, character=0),
                    end=Position(line=end_line, character=end_char),
                ),
                new_text=formatted_content,
            )
        ]

    def _format_value(self, value) -> str:
        """Format a parameter value."""
        if isinstance(value, bool):
            return ".TRUE." if value else ".FALSE."
        elif isinstance(value, (list, tuple)):
            return " ".join(str(v) for v in value)
        return str(value)

    def _format_poscar(self, content: str) -> List[TextEdit]:
        """Format POSCAR file content.

        Formatting rules:
        - Ensure consistent column alignment
        - Proper spacing between sections
        """
        lines = content.split("\n")
        if len(lines) < 5:
            return []

        formatted_lines = []

        # Line 1: System comment
        formatted_lines.append(lines[0].strip() or "POSCAR")

        # Line 2: Scaling factor
        try:
            scale = float(lines[1].strip())
            formatted_lines.append(f"   {scale:.10f}")
        except (ValueError, IndexError):
            formatted_lines.append(lines[1] if len(lines) > 1 else "   1.0000000000")

        # Lines 3-5: Lattice vectors (ensure proper formatting)
        for i in range(2, 5):
            if i < len(lines):
                parts = lines[i].split()
                if len(parts) >= 3:
                    try:
                        v = [float(p) for p in parts[:3]]
                        formatted_lines.append(f"     {v[0]:.10f}    {v[1]:.10f}    {v[2]:.10f}")
                    except ValueError:
                        formatted_lines.append(lines[i])
                else:
                    formatted_lines.append(lines[i])

        # Line 6: Element symbols (if present)
        if len(lines) > 5:
            formatted_lines.append(lines[5].strip())

        # Line 7: Number of atoms per type
        if len(lines) > 6:
            formatted_lines.append(lines[6].strip())

        # Line 8: Coordinate type (Direct or Cartesian)
        if len(lines) > 7:
            coord_type = lines[7].strip().upper()
            if coord_type.startswith("D"):
                formatted_lines.append("Direct")
            elif coord_type.startswith("C") or coord_type.startswith("K"):
                formatted_lines.append("Cartesian")
            else:
                formatted_lines.append(coord_type)

        # Lines 9+: Coordinates
        for i in range(8, len(lines)):
            line = lines[i]
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                formatted_lines.append(stripped)
                continue

            # Extract comment if present
            comment = ""
            if "#" in line:
                parts = line.split("#", 1)
                line = parts[0]
                comment = "  #" + parts[1]

            parts = line.split()
            if len(parts) >= 3:
                try:
                    coords = [float(p) for p in parts[:3]]
                    # Handle selective dynamics flags if present
                    if len(parts) >= 6:
                        flags = " ".join(parts[3:6])
                        formatted_lines.append(
                            f"   {coords[0]:.10f}   {coords[1]:.10f}   {coords[2]:.10f}   {flags}{comment}"
                        )
                    else:
                        formatted_lines.append(
                            f"   {coords[0]:.10f}   {coords[1]:.10f}   {coords[2]:.10f}{comment}"
                        )
                except ValueError:
                    formatted_lines.append(stripped)
            else:
                formatted_lines.append(stripped)

        formatted_content = "\n".join(formatted_lines)
        end_line = len(lines) - 1
        end_char = len(lines[end_line]) if lines else 0

        return [
            TextEdit(
                range=Range(
                    start=Position(line=0, character=0),
                    end=Position(line=end_line, character=end_char),
                ),
                new_text=formatted_content,
            )
        ]

    def _format_kpoints(self, content: str) -> List[TextEdit]:
        """Format KPOINTS file content.

        Formatting rules:
        - Ensure proper section separation
        - Consistent k-point grid formatting
        """
        lines = content.split("\n")
        if len(lines) < 4:
            return []

        formatted_lines = []

        # Line 1: Comment
        formatted_lines.append(lines[0].strip() or "KPOINTS")

        # Line 2: Number of k-points (0 for automatic)
        if len(lines) > 1:
            formatted_lines.append(lines[1].strip())

        # Line 3: Grid type (Gamma, Monkhorst-Pack, etc.)
        if len(lines) > 2:
            line3 = lines[2].strip().upper()
            if line3.startswith("G"):
                formatted_lines.append("Gamma")
            elif line3.startswith("M"):
                formatted_lines.append("Monkhorst-Pack")
            elif line3 == "L":
                formatted_lines.append("Line-mode")
            elif line3 == "A":
                formatted_lines.append("Automatic")
            else:
                formatted_lines.append(lines[2].strip())

        # Line 4: Grid dimensions or k-point list
        if len(lines) > 3:
            parts = lines[3].split()
            if len(parts) == 3:
                # Automatic grid mode
                try:
                    grid = [int(p) for p in parts]
                    formatted_lines.append(f"  {grid[0]} {grid[1]} {grid[2]}")
                except ValueError:
                    formatted_lines.append(lines[3].strip())
            elif len(parts) == 6:
                # Grid with shift
                try:
                    nums = [int(p) for p in parts]
                    formatted_lines.append(
                        f"  {nums[0]} {nums[1]} {nums[2]} {nums[3]} {nums[4]} {nums[5]}"
                    )
                except ValueError:
                    formatted_lines.append(lines[3].strip())
            else:
                formatted_lines.append(lines[3].strip())

        # Lines 5+: Additional k-points for line mode or explicit listing
        for i in range(4, len(lines)):
            line = lines[i]
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                formatted_lines.append(stripped)
                continue

            # Extract comment if present
            comment = ""
            if "#" in line:
                parts = line.split("#", 1)
                line = parts[0]
                comment = "  #" + parts[1]

            parts = line.split()
            if len(parts) >= 3:
                try:
                    # Try to parse as k-point coordinates
                    k = [float(p) for p in parts[:3]]
                    weight = float(parts[3]) if len(parts) > 3 else 1.0
                    formatted_lines.append(
                        f"   {k[0]:.6f}  {k[1]:.6f}  {k[2]:.6f}   {weight}{comment}"
                    )
                except ValueError:
                    formatted_lines.append(stripped)
            else:
                formatted_lines.append(stripped)

        formatted_content = "\n".join(formatted_lines)
        end_line = len(lines) - 1
        end_char = len(lines[end_line]) if lines else 0

        return [
            TextEdit(
                range=Range(
                    start=Position(line=0, character=0),
                    end=Position(line=end_line, character=end_char),
                ),
                new_text=formatted_content,
            )
        ]
