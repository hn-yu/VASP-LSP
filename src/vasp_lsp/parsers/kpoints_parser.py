"""KPOINTS file parser for VASP-LSP."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class KPOINTSMode(Enum):
    """KPOINTS generation modes."""

    AUTOMATIC = "automatic"  # Fully automatic k-point mesh
    GAMMA_MONKHORST = "gamma_monkhorst"  # Gamma-centered or Monkhorst-Pack
    LINE_MODE = "line"  # Line-mode for band structure
    EXPLICIT = "explicit"  # Explicit k-point list


@dataclass
class KPOINTSData:
    """Represents parsed KPOINTS data."""

    comment: str
    mode: KPOINTSMode
    kpoints: List[List[float]]
    weights: Optional[List[float]] = None
    grid: Optional[List[int]] = None  # For automatic mode
    shift: Optional[List[float]] = None  # For automatic mode
    gamma_centered: Optional[bool] = None  # For Gamma/Monkhorst-Pack mode
    # Line mode specific
    n_lines: Optional[int] = None
    line_density: Optional[int] = None
    # Source spans for exact diagnostic ranges (0-based line indices)
    grid_line_idx: Optional[int] = None
    shift_line_idx: Optional[int] = None
    kpoints_start_line_idx: Optional[int] = None


class KPOINTSParser:
    """Parser for VASP KPOINTS files."""

    def __init__(self, content: str):
        """Initialize parser with KPOINTS file content.

        Args:
            content: The full content of the KPOINTS file.
        """
        self.content = content
        self.lines = content.split("\n")
        self.data: Optional[KPOINTSData] = None
        self.errors: List[Dict[str, Any]] = []
        self._parsed = False

    def parse(self) -> Optional[KPOINTSData]:
        """Parse the KPOINTS file content.

        Returns:
            KPOINTSData object if successful, None otherwise.
        """
        if self._parsed:
            return self.data
        self._parsed = True
        self.errors = []

        try:
            line_idx = 0

            # Line 1: Comment
            comment = self.lines[line_idx].strip() if self.lines else ""
            line_idx += 1

            if line_idx >= len(self.lines):
                self.errors.append(
                    {
                        "message": "KPOINTS file is too short",
                        "line": line_idx,
                        "severity": "error",
                    }
                )
                return None

            # Line 2: Number of k-points or type
            line2 = self.lines[line_idx].strip().lower()
            line_idx += 1

            # Check for automatic mode
            if line2 == "a" or line2 == "automatic":
                return self._store_data(self._parse_automatic_mode(comment, line_idx))

            # Check for line mode
            if "line" in line2:
                return self._store_data(self._parse_line_mode(comment, line_idx))

            # Try to parse as number
            try:
                nkpoints = int(line2)
            except ValueError:
                self.errors.append(
                    {
                        "message": f"Invalid k-point specification: {line2}",
                        "line": line_idx,
                        "severity": "error",
                    }
                )
                return None

            # Line 3: Generation type or Cartesian/Direct
            if line_idx >= len(self.lines):
                self.errors.append(
                    {
                        "message": "Unexpected end of file",
                        "line": line_idx,
                        "severity": "error",
                    }
                )
                return None

            line3 = self.lines[line_idx].strip().lower()
            line_idx += 1

            if "line" in line3:
                return self._store_data(self._parse_line_mode(comment, line_idx - 2))
            if line3.startswith("r"):
                # Reciprocal coordinates (standard for explicit k-points)
                return self._store_data(
                    self._parse_explicit_mode(
                        comment, nkpoints, line_idx, reciprocal=True
                    )
                )
            elif line3.startswith("c") or line3.startswith("k"):
                # Cartesian coordinates in units of 2π/a
                return self._store_data(
                    self._parse_explicit_mode(
                        comment, nkpoints, line_idx, reciprocal=False
                    )
                )
            elif line3.startswith("g"):
                # Gamma-centered
                return self._store_data(
                    self._parse_gamma_monkhorst_mode(
                        comment, nkpoints, line_idx, gamma_centered=True
                    )
                )
            elif line3.startswith("m"):
                # Monkhorst-Pack
                return self._store_data(
                    self._parse_gamma_monkhorst_mode(
                        comment, nkpoints, line_idx, gamma_centered=False
                    )
                )
            else:
                self.errors.append(
                    {
                        "message": f"Unknown coordinate/generation type: {line3}",
                        "line": line_idx,
                        "severity": "error",
                    }
                )
                return None

        except Exception as e:
            self.errors.append(
                {
                    "message": f"Unexpected parse error: {str(e)}",
                    "line": 0,
                    "severity": "error",
                }
            )
            return None

    def _store_data(self, data: Optional[KPOINTSData]) -> Optional[KPOINTSData]:
        """Store a parsed result so repeated reads return the same object."""
        self.data = data
        return self.data

    def _parse_automatic_mode(
        self, comment: str, line_idx: int
    ) -> Optional[KPOINTSData]:
        """Parse fully automatic k-point mode.

        Args:
            comment: File comment.
            line_idx: Current line index.

        Returns:
            KPOINTSData if successful.
        """
        try:
            # Line 3: Grid dimensions
            grid_line_idx = line_idx
            grid_line = self.lines[line_idx].strip().split()
            if len(grid_line) < 3:
                self.errors.append(
                    {
                        "message": "Automatic mode requires 3 grid values",
                        "line": line_idx + 1,
                        "severity": "error",
                    }
                )
                return None
            grid = [int(grid_line[0]), int(grid_line[1]), int(grid_line[2])]
            line_idx += 1

            # Line 4: Shift (optional)
            shift_line_idx = None
            shift = [0.0, 0.0, 0.0]
            if line_idx < len(self.lines):
                shift_line_idx = line_idx
                shift_line = self.lines[line_idx].strip().split()
                if len(shift_line) >= 3:
                    shift = [
                        float(shift_line[0]),
                        float(shift_line[1]),
                        float(shift_line[2]),
                    ]

            return KPOINTSData(
                comment=comment,
                mode=KPOINTSMode.AUTOMATIC,
                kpoints=[],
                grid=grid,
                shift=shift,
                grid_line_idx=grid_line_idx,
                shift_line_idx=shift_line_idx,
            )
        except (ValueError, IndexError) as e:
            self.errors.append(
                {
                    "message": f"Error parsing automatic mode: {e}",
                    "line": line_idx + 1,
                    "severity": "error",
                }
            )
            return None

    def _parse_gamma_monkhorst_mode(
        self, comment: str, nkpoints: int, line_idx: int, gamma_centered: bool
    ) -> Optional[KPOINTSData]:
        """Parse Gamma-centered or Monkhorst-Pack mode.

        Args:
            comment: File comment.
            nkpoints: Number of k-points (should be 0 for automatic mesh).
            line_idx: Current line index.
            gamma_centered: Whether to use gamma-centered grid.

        Returns:
            KPOINTSData if successful.
        """
        try:
            # Next line: Grid dimensions
            grid_line_idx = line_idx
            grid_line = self.lines[line_idx].strip().split()
            if len(grid_line) < 3:
                self.errors.append(
                    {
                        "message": "Gamma/Monkhorst mode requires 3 grid values",
                        "line": line_idx + 1,
                        "severity": "error",
                    }
                )
                return None
            grid = [int(grid_line[0]), int(grid_line[1]), int(grid_line[2])]
            line_idx += 1

            # Next line: Shift
            shift_line_idx = None
            shift = [0.0, 0.0, 0.0]
            if line_idx < len(self.lines):
                shift_line_idx = line_idx
                shift_line = self.lines[line_idx].strip().split()
                if len(shift_line) >= 3:
                    shift = [
                        float(shift_line[0]),
                        float(shift_line[1]),
                        float(shift_line[2]),
                    ]

            return KPOINTSData(
                comment=comment,
                mode=KPOINTSMode.GAMMA_MONKHORST,
                kpoints=[],
                grid=grid,
                shift=shift,
                gamma_centered=gamma_centered,
                grid_line_idx=grid_line_idx,
                shift_line_idx=shift_line_idx,
            )
        except (ValueError, IndexError) as e:
            self.errors.append(
                {
                    "message": f"Error parsing Gamma/Monkhorst mode: {e}",
                    "line": line_idx + 1,
                    "severity": "error",
                }
            )
            return None

    def _parse_explicit_mode(
        self, comment: str, nkpoints: int, line_idx: int, reciprocal: bool
    ) -> Optional[KPOINTSData]:
        """Parse explicit k-point list mode.

        Args:
            comment: File comment.
            nkpoints: Number of k-points.
            line_idx: Current line index.
            reciprocal: Whether coordinates are in reciprocal space.

        Returns:
            KPOINTSData if successful.
        """
        try:
            kpoints = []
            weights = []
            kpoints_start_line_idx = line_idx

            for i in range(nkpoints):
                if line_idx >= len(self.lines):
                    self.errors.append(
                        {
                            "message": f"Expected {nkpoints} k-points, found {i}",
                            "line": line_idx,
                            "severity": "error",
                        }
                    )
                    return None

                parts = self.lines[line_idx].strip().split()
                if len(parts) < 4:
                    self.errors.append(
                        {
                            "message": "K-point line must have at least 4 values (kx, ky, kz, w)",
                            "line": line_idx + 1,
                            "severity": "error",
                        }
                    )
                    return None

                kpoint = [float(parts[0]), float(parts[1]), float(parts[2])]
                weight = float(parts[3])
                kpoints.append(kpoint)
                weights.append(weight)
                line_idx += 1

            return KPOINTSData(
                comment=comment,
                mode=KPOINTSMode.EXPLICIT,
                kpoints=kpoints,
                weights=weights,
                kpoints_start_line_idx=kpoints_start_line_idx,
            )
        except (ValueError, IndexError) as e:
            self.errors.append(
                {
                    "message": f"Error parsing explicit k-points: {e}",
                    "line": line_idx + 1,
                    "severity": "error",
                }
            )
            return None

    def _parse_line_mode(self, comment: str, line_idx: int) -> Optional[KPOINTSData]:
        """Parse line-mode for band structure.

        Args:
            comment: File comment.
            line_idx: Current line index.

        Returns:
            KPOINTSData if successful.
        """
        try:
            # Number of points per line
            n_points_line = self.lines[line_idx].strip().split()
            line_density = int(n_points_line[0]) if n_points_line else 20
            line_idx += 1

            # Coordinate type
            self.lines[line_idx].strip().lower()
            line_idx += 1

            kpoints = []

            while line_idx < len(self.lines):
                line = self.lines[line_idx].strip()
                if not line:
                    line_idx += 1
                    continue

                parts = line.split()
                if len(parts) >= 3:
                    kpoint = [float(parts[0]), float(parts[1]), float(parts[2])]
                    kpoints.append(kpoint)
                line_idx += 1

            return KPOINTSData(
                comment=comment,
                mode=KPOINTSMode.LINE_MODE,
                kpoints=kpoints,
                line_density=line_density,
            )
        except (ValueError, IndexError) as e:
            self.errors.append(
                {
                    "message": f"Error parsing line mode: {e}",
                    "line": line_idx + 1,
                    "severity": "error",
                }
            )
            return None

    def get_errors(self) -> List[Dict[str, Any]]:
        """Get all parse errors.

        Returns:
            List of error dictionaries.
        """
        return self.errors
