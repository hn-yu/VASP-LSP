"""POSCAR file parser for VASP-LSP."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class POSCARData:
    """Represents parsed POSCAR data."""

    system_comment: str
    scale_factor: float
    lattice_vectors: List[List[float]]  # 3x3 matrix
    atom_types: List[str]
    atom_counts: List[int]
    coordinate_type: str  # "Direct" or "Cartesian"
    coordinates: List[List[float]]
    selective_dynamics: Optional[List[List[bool]]] = None
    coordinate_start_line: int = 0
    # Line indices (0-based) for key sections, enabling exact source spans
    scale_factor_line: int = 1
    lattice_start_line: int = 2
    atom_types_line: int = 5
    atom_counts_line: int = 6
    coord_type_line: int = 7
    has_selective_dynamics: bool = False
    has_explicit_atom_types: bool = True

    def scaled_lattice_vectors(self) -> List[List[float]]:
        """Return lattice vectors after applying the POSCAR scale factor."""
        return [
            [component * self.scale_factor for component in vector]
            for vector in self.lattice_vectors
        ]

    def cartesian_coordinates(self) -> List[List[float]]:
        """Return atom coordinates in Cartesian Angstroms.

        Raw ``coordinates`` remain in the source coordinate system. This helper
        is intended for renderers and downstream tools that need canonical
        Cartesian positions.
        """
        if self.coordinate_type == "Cartesian":
            return [
                [component * self.scale_factor for component in coordinate]
                for coordinate in self.coordinates
            ]

        lattice = self.scaled_lattice_vectors()
        return [
            [
                coordinate[0] * lattice[0][axis]
                + coordinate[1] * lattice[1][axis]
                + coordinate[2] * lattice[2][axis]
                for axis in range(3)
            ]
            for coordinate in self.coordinates
        ]


class POSCARParser:
    """Parser for VASP POSCAR/CONTCAR structure files."""

    def __init__(self, content: str, *, allow_post_coordinate_data: bool = False):
        """Initialize parser with POSCAR file content.

        Args:
            content: The full content of the POSCAR file.
            allow_post_coordinate_data: Allow VASP's optional velocity and
                MD restart sections after the ionic coordinates. This is
                enabled by the LSP for POSCAR/CONTCAR documents, while the
                strict default keeps the parser useful for detecting an
                unseparated extra coordinate row.
        """
        self.content = content
        self.lines = content.split("\n")
        self.allow_post_coordinate_data = allow_post_coordinate_data
        self.data: Optional[POSCARData] = None
        self.errors: List[Dict[str, Any]] = []

    def parse(self) -> Optional[POSCARData]:
        """Parse the POSCAR file content.

        Returns:
            POSCARData object if successful, None otherwise.
        """
        self.errors = []

        try:
            line_idx = 0

            # Line 1: System comment
            system_comment = self.lines[line_idx].strip()
            line_idx += 1

            # Line 2: Scale factor
            scale_factor_line = line_idx
            try:
                scale_factor = float(self.lines[line_idx].strip())
            except (ValueError, IndexError) as e:
                self.errors.append(
                    {
                        "message": f"Invalid scale factor: {e}",
                        "line": line_idx + 1,
                        "severity": "error",
                    }
                )
                return None
            line_idx += 1

            # Lines 3-5: Lattice vectors
            lattice_start_line = line_idx
            lattice_vectors = []
            for i in range(3):
                try:
                    parts = self.lines[line_idx].strip().split()
                    if len(parts) < 3:
                        raise ValueError(f"Expected 3 values, got {len(parts)}")
                    vector = [float(parts[0]), float(parts[1]), float(parts[2])]
                    lattice_vectors.append(vector)
                except (ValueError, IndexError) as e:
                    self.errors.append(
                        {
                            "message": f"Invalid lattice vector {i + 1}: {e}",
                            "line": line_idx + 1,
                            "severity": "error",
                        }
                    )
                    return None
                line_idx += 1

            # Line 6: Atom types (optional in VASP 5 format, required in VASP 4)
            atom_types_line_idx = line_idx
            atom_types_line = self.lines[line_idx].strip()
            # Check if it's atom symbols or atom counts
            if not atom_types_line:
                self.errors.append(
                    {
                        "message": "Missing atom types or atom counts",
                        "line": line_idx + 1,
                        "severity": "error",
                    }
                )
                return None

            has_explicit_atom_types = atom_types_line[0].isalpha()
            if has_explicit_atom_types:
                atom_types = atom_types_line.split()
                line_idx += 1
            else:
                atom_types = []
                atom_types_line_idx = -1  # No explicit atom types line

            # Line 6/7: Atom counts
            atom_counts_line_idx = line_idx
            try:
                atom_counts = [int(x) for x in self.lines[line_idx].strip().split()]
                if any(count < 0 for count in atom_counts):
                    self.errors.append(
                        {
                            "message": "Atom counts must be non-negative integers",
                            "line": line_idx + 1,
                            "severity": "error",
                        }
                    )
                if atom_types and len(atom_types) != len(atom_counts):
                    self.errors.append(
                        {
                            "message": f"Mismatch between atom types ({len(atom_types)}) and counts ({len(atom_counts)})",
                            "line": line_idx + 1,
                            "severity": "error",
                        }
                    )
            except (ValueError, IndexError) as e:
                self.errors.append(
                    {
                        "message": f"Invalid atom counts: {e}",
                        "line": line_idx + 1,
                        "severity": "error",
                    }
                )
                return None
            line_idx += 1

            # If no atom types were specified, create generic ones
            if not atom_types:
                atom_types = [f"Type{i + 1}" for i in range(len(atom_counts))]

            # Check for selective dynamics line
            selective_dynamics: Optional[list] = None
            has_selective_dynamics = False
            coord_type_line_idx = line_idx
            coord_type_line = self.lines[line_idx].strip().lower()
            if coord_type_line.startswith("s"):
                selective_dynamics = []
                has_selective_dynamics = True
                line_idx += 1
                coord_type_line_idx = line_idx
                coord_type_line = self.lines[line_idx].strip().lower()

            # Coordinate type
            if coord_type_line.startswith("d"):
                coordinate_type = "Direct"
            elif coord_type_line.startswith("c") or coord_type_line.startswith("k"):
                coordinate_type = "Cartesian"
            else:
                self.errors.append(
                    {
                        "message": f"Unknown coordinate type: {coord_type_line}",
                        "line": line_idx + 1,
                        "severity": "error",
                    }
                )
                return None
            line_idx += 1

            # Read coordinates
            total_atoms = sum(atom_counts)
            coordinates = []
            coordinate_start_line = line_idx + 1
            if selective_dynamics is not None:
                selective_dynamics = []

            for i in range(total_atoms):
                try:
                    parts = self.lines[line_idx].strip().split()
                    if len(parts) < 3:
                        raise ValueError(f"Expected at least 3 values, got {len(parts)}")
                    coord = [float(parts[0]), float(parts[1]), float(parts[2])]
                    coordinates.append(coord)

                    # Parse selective dynamics flags if present
                    if selective_dynamics is not None:
                        if len(parts) >= 6:
                            invalid_flags = [
                                flag
                                for flag in parts[3:6]
                                if flag.upper() not in {"T", "F", ".TRUE.", ".FALSE."}
                            ]
                            if invalid_flags:
                                self.errors.append(
                                    {
                                        "message": "Selective dynamics flags must be T or F",
                                        "line": line_idx + 1,
                                        "severity": "error",
                                    }
                                )
                            flags = [
                                parts[3].upper() in {"T", ".TRUE."},
                                parts[4].upper() in {"T", ".TRUE."},
                                parts[5].upper() in {"T", ".TRUE."},
                            ]
                        else:
                            self.errors.append(
                                {
                                    "message": "Selective dynamics coordinates require 3 T/F flags",
                                    "line": line_idx + 1,
                                    "severity": "error",
                                }
                            )
                            flags = [True, True, True]
                        selective_dynamics.append(flags)

                except (ValueError, IndexError) as e:
                    self.errors.append(
                        {
                            "message": f"Invalid coordinate for atom {i + 1}: {e}",
                            "line": line_idx + 1,
                            "severity": "error",
                        }
                    )
                    return None
                line_idx += 1

            if not self._has_post_coordinate_data(line_idx, total_atoms):
                for extra_idx in range(line_idx, len(self.lines)):
                    extra = self.lines[extra_idx].strip()
                    if not extra or extra.startswith("#") or extra.startswith("!"):
                        continue
                    parts = extra.split()
                    if len(parts) >= 3:
                        try:
                            [float(parts[0]), float(parts[1]), float(parts[2])]
                        except ValueError:
                            continue
                        self.errors.append(
                            {
                                "message": "Extra coordinate row after expected atom count",
                                "line": extra_idx + 1,
                                "severity": "warning",
                            }
                        )

            self.data = POSCARData(
                system_comment=system_comment,
                scale_factor=scale_factor,
                lattice_vectors=lattice_vectors,
                atom_types=atom_types,
                atom_counts=atom_counts,
                coordinate_type=coordinate_type,
                coordinates=coordinates,
                selective_dynamics=selective_dynamics,
                coordinate_start_line=coordinate_start_line,
                scale_factor_line=scale_factor_line,
                lattice_start_line=lattice_start_line,
                atom_types_line=max(atom_types_line_idx, 0),
                atom_counts_line=atom_counts_line_idx,
                coord_type_line=coord_type_line_idx,
                has_selective_dynamics=has_selective_dynamics,
                has_explicit_atom_types=has_explicit_atom_types,
            )

            return self.data

        except Exception as e:
            self.errors.append(
                {
                    "message": f"Unexpected parse error: {str(e)}",
                    "line": 0,
                    "severity": "error",
                }
            )
            return None

    def _has_post_coordinate_data(self, start_line: int, total_atoms: int) -> bool:
        """Return whether the trailing lines form VASP's optional sections.

        VASP writes a blank line followed by one velocity row per atom in a
        CONTCAR produced by molecular dynamics. The optional predictor-
        corrector block follows those velocities and may contain many more
        numeric rows. POSCAR also permits an explicitly labelled velocity
        block, so the LSP accepts both forms once the coordinate block has
        been consumed.
        """
        if not self.allow_post_coordinate_data or start_line >= len(self.lines):
            return False

        line_index = start_line
        first = self.lines[line_index].strip()

        # A variable-cell MD restart may begin with the eight-line lattice
        # velocity section. Its marker is documented as "Lattice velocities
        # and vectors" and is identified by the first character in VASP.
        if first.lower().startswith("l"):
            if len(self.lines) - line_index < 8:
                return False
            line_index += 8
            if all(not line.strip() for line in self.lines[line_index:]):
                return True
            first = self.lines[line_index].strip()

        # VASP-written CONTCAR velocity blocks start with an empty line. When
        # entered manually, the velocity mode can instead be labelled Direct
        # or Cartesian (K is also accepted by VASP for Cartesian input).
        if not first:
            line_index += 1
        elif first[0].lower() in {"d", "c", "k"}:
            line_index += 1
        else:
            return False

        for _ in range(total_atoms):
            if line_index >= len(self.lines):
                return False
            parts = self.lines[line_index].split()
            if len(parts) < 3:
                return False
            try:
                [float(parts[0]), float(parts[1]), float(parts[2])]
            except ValueError:
                return False
            line_index += 1

        return True

    def get_errors(self) -> List[Dict[str, Any]]:
        """Get all parse errors.

        Returns:
            List of error dictionaries.
        """
        return self.errors
