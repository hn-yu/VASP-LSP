"""INCAR file parser for VASP-LSP."""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union


@dataclass
class INCARParameter:
    """Represents a parsed INCAR parameter."""

    name: str
    value: Any
    line_number: int
    column_start: int
    column_end: int
    raw_line: str


class INCARParser:
    """Parser for VASP INCAR input files."""

    # Regular expression for parsing INCAR lines
    # Matches: TAG = value  or  TAG= value  or  TAG =value  or  TAG=value
    # Also handles comments starting with # or !
    PARAM_REGEX = re.compile(
        r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_/]*)\s*=\s*(?P<value>[^#!]*)", re.IGNORECASE
    )

    # Comment patterns
    COMMENT_REGEX = re.compile(r"[#!].*$")

    def __init__(self, content: str):
        """Initialize parser with INCAR file content.

        Args:
            content: The full content of the INCAR file.
        """
        self.content = content
        self.lines = content.split("\n")
        self.parameters: Dict[str, INCARParameter] = {}
        self.errors: List[Dict[str, Any]] = []

    def parse(self) -> Dict[str, INCARParameter]:
        """Parse the INCAR file content.

        Returns:
            Dictionary mapping parameter names to INCARParameter objects.
        """
        self.parameters = {}
        self.errors = []

        for line_num, line in enumerate(self.lines, start=1):
            try:
                param = self._parse_line(line, line_num)
                if param:
                    if param.name.upper() in self.parameters:
                        self.errors.append(
                            {
                                "message": f"Duplicate parameter: {param.name}",
                                "line": line_num,
                                "column": param.column_start,
                                "severity": "warning",
                            }
                        )
                    self.parameters[param.name.upper()] = param
            except Exception as e:
                self.errors.append(
                    {
                        "message": f"Parse error: {str(e)}",
                        "line": line_num,
                        "column": 0,
                        "severity": "error",
                    }
                )

        return self.parameters

    def _parse_line(self, line: str, line_num: int) -> Optional[INCARParameter]:
        """Parse a single INCAR line.

        Args:
            line: The line content.
            line_num: The line number (1-indexed).

        Returns:
            INCARParameter if a parameter is found, None otherwise.
        """
        # Skip empty lines and comment-only lines
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("!"):
            return None

        # Try to match parameter pattern
        match = self.PARAM_REGEX.match(line)
        if not match:
            # Check if it looks like a parameter (contains letters)
            if re.search(r"[A-Za-z]", stripped):
                self.errors.append(
                    {
                        "message": f"Invalid parameter format: {stripped}",
                        "line": line_num,
                        "column": 0,
                        "severity": "error",
                    }
                )
            return None

        name = match.group("name").upper()
        value_str = match.group("value").strip()

        # Remove trailing comments
        value_str = self.COMMENT_REGEX.sub("", value_str).strip()

        # Parse value
        value = self._parse_value(value_str)

        return INCARParameter(
            name=name,
            value=value,
            line_number=line_num,
            column_start=match.start("name"),
            column_end=match.end("value"),
            raw_line=line,
        )

    def _parse_value(self, value_str: str) -> Any:
        """Parse an INCAR parameter value.

        Args:
            value_str: The value string.

        Returns:
            Parsed value (int, float, bool, or string).
        """
        value_upper = value_str.upper()

        # Handle boolean values
        if value_upper in [".TRUE.", "T", "TRUE"]:
            return True
        if value_upper in [".FALSE.", "F", "FALSE"]:
            return False

        # Try integer
        try:
            return int(value_str)
        except ValueError:
            pass

        # Try float
        try:
            return float(value_str)
        except ValueError:
            pass

        # Handle array values (space-separated)
        if " " in value_str:
            parts = value_str.split()
            # A whitespace-separated value is an array only when every token
            # is numeric (or uses VASP's n*value repetition syntax). This keeps
            # documented multi-word strings such as ``ALGO = Old Fast`` and
            # normal SYSTEM labels intact while preserving MAGMOM arrays.
            numeric_or_repeated = re.compile(
                r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$"
            )
            repeated_numeric = re.compile(
                r"^\d+\*[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$"
            )
            if not all(
                numeric_or_repeated.fullmatch(part) or repeated_numeric.fullmatch(part)
                for part in parts
            ):
                return value_str
            parsed_parts: List[Union[int, float, str]] = []
            for part in parts:
                try:
                    parsed_parts.append(int(part))
                except ValueError:
                    try:
                        parsed_parts.append(float(part))
                    except ValueError:
                        parsed_parts.append(part)
            return parsed_parts

        # Return as string
        return value_str

    def get_parameter(self, name: str) -> Optional[INCARParameter]:
        """Get a parameter by name.

        Args:
            name: Parameter name (case-insensitive).

        Returns:
            INCARParameter if found, None otherwise.
        """
        return self.parameters.get(name.upper())

    def has_parameter(self, name: str) -> bool:
        """Check if a parameter exists.

        Args:
            name: Parameter name (case-insensitive).

        Returns:
            True if parameter exists.
        """
        return name.upper() in self.parameters

    def get_all_parameters(self) -> Dict[str, INCARParameter]:
        """Get all parsed parameters.

        Returns:
            Dictionary of all parameters.
        """
        return self.parameters.copy()

    def get_errors(self) -> List[Dict[str, Any]]:
        """Get all parse errors and warnings.

        Returns:
            List of error dictionaries.
        """
        return self.errors
