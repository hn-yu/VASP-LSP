"""POTCAR parser for cross-file VASP diagnostics."""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class POTCAREntry:
    """One pseudopotential dataset inside a POTCAR file."""

    title: str
    element: str
    enmax: Optional[float] = None
    enmin: Optional[float] = None


@dataclass
class POTCARData:
    """Parsed POTCAR data."""

    entries: List[POTCAREntry]


class POTCARParser:
    """Parse enough POTCAR metadata for static validation."""

    TITEL_REGEX = re.compile(r"^\s*TITEL\s*=\s*(?P<title>.+?)\s*$", re.IGNORECASE)
    ENMAX_REGEX = re.compile(r"ENMAX\s*=\s*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE)
    ENMIN_REGEX = re.compile(r"ENMIN\s*=\s*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE)

    def __init__(self, content: str):
        """Initialize parser with POTCAR content."""
        self.content = content
        self.lines = content.splitlines()
        self.errors: List[Dict[str, Any]] = []

    def parse(self) -> Optional[POTCARData]:
        """Parse POTCAR dataset titles and cutoff metadata."""
        self.errors = []
        entries: List[POTCAREntry] = []
        current: Optional[POTCAREntry] = None
        has_explicit_titles = any(self.TITEL_REGEX.match(line) for line in self.lines)

        for line_num, line in enumerate(self.lines, start=1):
            stripped = line.strip()
            title_match = self.TITEL_REGEX.match(line)
            if title_match or (not has_explicit_titles and self._looks_like_title(stripped)):
                if current:
                    entries.append(current)
                title = title_match.group("title").strip() if title_match else stripped
                current = POTCAREntry(title=title, element=self._extract_element(title))
                continue

            if current:
                enmax_match = self.ENMAX_REGEX.search(line)
                if enmax_match:
                    current.enmax = float(enmax_match.group(1))

                enmin_match = self.ENMIN_REGEX.search(line)
                if enmin_match:
                    current.enmin = float(enmin_match.group(1))

        if current:
            entries.append(current)

        if not entries and self.content.strip():
            self.errors.append(
                {
                    "message": "No POTCAR datasets found",
                    "line": 1,
                    "severity": "error",
                }
            )
            return None

        return POTCARData(entries=entries)

    def _looks_like_title(self, line: str) -> bool:
        if not line:
            return False
        if len(line.split()) < 2:
            return False
        upper = line.upper()
        if not upper.startswith(("PAW", "US", "LDA", "PBE")) or "ENMAX" in upper:
            return False
        return self._extract_element(line) != "Unknown"

    def _extract_element(self, title: str) -> str:
        parts = title.split()
        ignored = {"PAW", "PBE", "LDA", "GGA", "US", "USPP", "AE"}
        for part in parts[1:]:
            token = part.split("_")[0]
            if token in ignored:
                continue
            if re.fullmatch(r"[A-Z][a-z]?", token):
                return token
        if len(parts) == 1:
            match = re.match(r"([A-Z][a-z]?)", parts[0].split("_")[0])
            if match:
                return match.group(1)
        return "Unknown"

    def get_errors(self) -> List[Dict[str, Any]]:
        """Get parser errors."""
        return self.errors
