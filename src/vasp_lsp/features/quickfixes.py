"""Quick fixes provider for VASP-LSP.

Provides code actions to automatically fix common VASP input file issues.
"""

import re
from typing import List, Optional

from lsprotocol.types import (
    CodeAction,
    CodeActionKind,
    Diagnostic,
    Position,
    Range,
    TextEdit,
    WorkspaceEdit,
)

from ..parsers.incar_parser import INCARParser
from ..schemas.incar_tags import INCAR_TAGS
from ..workspace import document_kind


class QuickFixesProvider:
    """Provides quick fixes (code actions) for VASP files."""

    def __init__(self):
        """Initialize quick fixes provider."""
        pass

    def get_code_actions(
        self,
        document_content: str,
        document_uri: str,
        diagnostics: List[Diagnostic],
        range: Range,
    ) -> List[CodeAction]:
        """Get available code actions for the given diagnostics.

        Args:
            document_content: Full document content.
            document_uri: Document URI to determine file type.
            diagnostics: List of diagnostics in the document.
            range: The range for which code actions are requested.

        Returns:
            List of available code actions.
        """
        file_type = self._get_file_type(document_uri)

        if file_type == "INCAR":
            return self._get_incar_code_actions(document_content, diagnostics, range)
        elif file_type == "POSCAR":
            return self._get_poscar_code_actions(document_content, diagnostics, range)
        elif file_type == "KPOINTS":
            return self._get_kpoints_code_actions(document_content, diagnostics, range)

        return []

    def _get_file_type(self, uri: str) -> str:
        """Determine file type from URI."""
        return document_kind(uri).value

    def _get_incar_code_actions(
        self, content: str, diagnostics: List[Diagnostic], range: Range
    ) -> List[CodeAction]:
        """Get code actions for INCAR files."""
        actions = []
        parser = INCARParser(content)
        parser.parse()
        lines = content.split("\n")

        # Track which fixes we've added to avoid duplicates
        added_fixes = set()

        for diagnostic in diagnostics:
            message = diagnostic.message.lower()
            runtime_action_titles = self._extract_safe_runtime_action_titles(diagnostic)

            # Runtime recovery actions from VASP logs. Only safe text edits are
            # materialized here; guarded file operations stay informational.
            for param_name, value in (
                ("ISYM", "0"),
                ("SYMPREC", "1E-6"),
                ("ALGO", "Normal"),
            ):
                title = f"Set {param_name} = {value}"
                fix_key = f"runtime_set_{param_name.lower()}_{value.lower()}"
                if (
                    title in runtime_action_titles or title.lower() in message
                ) and fix_key not in added_fixes:
                    action = self._create_set_incar_param_action(
                        lines, diagnostic, param_name, value
                    )
                    if action:
                        actions.append(action)
                        added_fixes.add(fix_key)

            # Fix 1: Add missing SIGMA when ISMEAR >= 0
            if "sigma" in message and "ismear" in message:
                fix_key = "add_sigma"
                if fix_key not in added_fixes:
                    action = self._create_add_sigma_action(lines, diagnostic)
                    if action:
                        actions.append(action)
                        added_fixes.add(fix_key)

            # Fix 2: Remove NPAR when NCORE is set
            if "npar" in message and "ncore" in message:
                fix_key = "remove_npar"
                if fix_key not in added_fixes:
                    action = self._create_remove_line_action(
                        lines,
                        diagnostic,
                        "Remove NPAR (use NCORE instead)",
                        "Use NCORE instead of NPAR for parallelization control",
                    )
                    if action:
                        actions.append(action)
                        added_fixes.add(fix_key)

            # Fix 3: Add MAGMOM when ISPIN=2
            if "magmom" in message and "ispin" in message:
                fix_key = "add_magmom"
                if fix_key not in added_fixes:
                    action = self._create_add_magmom_action(lines, diagnostic)
                    if action:
                        actions.append(action)
                        added_fixes.add(fix_key)

            if "magmom has" in message and "poscar contains" in message:
                fix_key = "replace_magmom_count"
                if fix_key not in added_fixes:
                    action = self._create_replace_magmom_count_action(lines, diagnostic)
                    if action:
                        actions.append(action)
                        added_fixes.add(fix_key)

            if "encut=" in message and "potcar enmax" in message:
                fix_key = "raise_encut"
                if fix_key not in added_fixes:
                    action = self._create_raise_encut_action(lines, diagnostic)
                    if action:
                        actions.append(action)
                        added_fixes.add(fix_key)

            if "kspacing is set" in message and "kpoints" in message:
                fix_key = "remove_kspacing"
                if fix_key not in added_fixes:
                    action = self._create_remove_line_action(
                        lines,
                        diagnostic,
                        "Remove KSPACING (use KPOINTS instead)",
                        "Avoid conflicting k-point settings",
                    )
                    if action:
                        actions.append(action)
                        added_fixes.add(fix_key)

            # Fix 4: Add missing LDAU parameters
            if "ldau" in message and "ldautype" in message:
                fix_key = "add_ldautype"
                if fix_key not in added_fixes:
                    action = self._create_add_ldau_param_action(lines, diagnostic, "LDAUTYPE", "2")
                    if action:
                        actions.append(action)
                        added_fixes.add(fix_key)

            if "ldau" in message and "ldaul" in message:
                fix_key = "add_ldaul"
                if fix_key not in added_fixes:
                    action = self._create_add_ldau_param_action(
                        lines, diagnostic, "LDAUL", "-1 -1 -1"
                    )
                    if action:
                        actions.append(action)
                        added_fixes.add(fix_key)

            if "ldau" in message and "ldauu" in message:
                fix_key = "add_ldauu"
                if fix_key not in added_fixes:
                    action = self._create_add_ldau_param_action(lines, diagnostic, "LDAUU", "0 0 0")
                    if action:
                        actions.append(action)
                        added_fixes.add(fix_key)

            # Fix 5: Fix common typos in INCAR tags
            if "unknown incar tag" in message:
                action = self._create_fix_typo_action(lines, diagnostic, content)
                if action:
                    actions.append(action)

        return actions

    def _extract_safe_runtime_action_titles(self, diagnostic: Diagnostic) -> List[str]:
        """Extract safe suggested runtime actions carried in Diagnostic.data."""
        data = getattr(diagnostic, "data", None)
        if not isinstance(data, dict):
            return []
        actions = data.get("suggested_actions", [])
        if not isinstance(actions, list):
            return []
        titles: List[str] = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            if action.get("safe_to_auto_apply", True) is not True:
                continue
            title = action.get("title")
            if isinstance(title, str):
                titles.append(title)
        return titles

    def _create_set_incar_param_action(
        self,
        lines: List[str],
        diagnostic: Diagnostic,
        param_name: str,
        value: str,
    ) -> Optional[CodeAction]:
        """Create action to set or append an INCAR parameter."""
        replacement = f"{param_name} = {value}"
        title = f"Set {replacement}"
        param_regex = re.compile(rf"^\s*{re.escape(param_name)}\s*=", re.IGNORECASE)

        for line_num, line in enumerate(lines):
            if param_regex.match(line):
                return CodeAction(
                    title=title,
                    kind=CodeActionKind.QuickFix,
                    diagnostics=[diagnostic],
                    edit=WorkspaceEdit(
                        changes={
                            "document": [
                                TextEdit(
                                    range=Range(
                                        start=Position(line=line_num, character=0),
                                        end=Position(line=line_num, character=len(line)),
                                    ),
                                    new_text=replacement,
                                )
                            ]
                        }
                    ),
                )

        if lines and lines[-1] == "":
            insert_line = len(lines) - 1
            insert_character = 0
            new_text = f"{replacement}\n"
        elif lines:
            insert_line = len(lines) - 1
            insert_character = len(lines[-1])
            new_text = f"\n{replacement}"
        else:
            insert_line = 0
            insert_character = 0
            new_text = f"{replacement}\n"

        return CodeAction(
            title=title,
            kind=CodeActionKind.QuickFix,
            diagnostics=[diagnostic],
            edit=WorkspaceEdit(
                changes={
                    "document": [
                        TextEdit(
                            range=Range(
                                start=Position(line=insert_line, character=insert_character),
                                end=Position(line=insert_line, character=insert_character),
                            ),
                            new_text=new_text,
                        )
                    ]
                }
            ),
        )

    def _create_add_sigma_action(
        self, lines: List[str], diagnostic: Diagnostic
    ) -> Optional[CodeAction]:
        """Create action to add SIGMA parameter."""
        line_num = diagnostic.range.start.line

        # Find the end of ISMEAR line
        insert_line = line_num + 1

        return CodeAction(
            title="Add SIGMA=0.2",
            kind=CodeActionKind.QuickFix,
            diagnostics=[diagnostic],
            edit=WorkspaceEdit(
                changes={
                    "document": [
                        TextEdit(
                            range=Range(
                                start=Position(line=insert_line, character=0),
                                end=Position(line=insert_line, character=0),
                            ),
                            new_text="SIGMA = 0.2  # Default for ISMEAR >= 0\\n",
                        )
                    ]
                }
            ),
        )

    def _create_remove_line_action(
        self, lines: List[str], diagnostic: Diagnostic, title: str, description: str
    ) -> Optional[CodeAction]:
        """Create action to remove a line."""
        line_num = diagnostic.range.start.line

        return CodeAction(
            title=title,
            kind=CodeActionKind.QuickFix,
            diagnostics=[diagnostic],
            edit=WorkspaceEdit(
                changes={
                    "document": [
                        TextEdit(
                            range=Range(
                                start=Position(line=line_num, character=0),
                                end=Position(line=line_num + 1, character=0),
                            ),
                            new_text="",
                        )
                    ]
                }
            ),
        )

    def _create_add_magmom_action(
        self, lines: List[str], diagnostic: Diagnostic
    ) -> Optional[CodeAction]:
        """Create action to add MAGMOM parameter."""
        line_num = diagnostic.range.start.line
        insert_line = line_num + 1

        return CodeAction(
            title="Add MAGMOM (default for all atoms)",
            kind=CodeActionKind.QuickFix,
            diagnostics=[diagnostic],
            edit=WorkspaceEdit(
                changes={
                    "document": [
                        TextEdit(
                            range=Range(
                                start=Position(line=insert_line, character=0),
                                end=Position(line=insert_line, character=0),
                            ),
                            new_text="MAGMOM = 1.0  # Default initial magnetic moment\\n",
                        )
                    ]
                }
            ),
        )

    def _create_add_ldau_param_action(
        self,
        lines: List[str],
        diagnostic: Diagnostic,
        param_name: str,
        default_value: str,
    ) -> Optional[CodeAction]:
        """Create action to add LDAU parameter."""
        line_num = diagnostic.range.start.line
        insert_line = line_num + 1

        return CodeAction(
            title=f"Add {param_name}={default_value}",
            kind=CodeActionKind.QuickFix,
            diagnostics=[diagnostic],
            edit=WorkspaceEdit(
                changes={
                    "document": [
                        TextEdit(
                            range=Range(
                                start=Position(line=insert_line, character=0),
                                end=Position(line=insert_line, character=0),
                            ),
                            new_text=f"{param_name} = {default_value}\\n",
                        )
                    ]
                }
            ),
        )

    def _create_replace_magmom_count_action(
        self, lines: List[str], diagnostic: Diagnostic
    ) -> Optional[CodeAction]:
        """Create action to replace MAGMOM with one default moment per atom."""
        count_match = re.search(r"POSCAR contains (\d+) atoms", diagnostic.message)
        if not count_match:
            return None
        count = int(count_match.group(1))
        line_num = diagnostic.range.start.line
        if line_num >= len(lines):
            return None
        line = lines[line_num]
        moments = " ".join(["1.0"] * count)

        return CodeAction(
            title=f"Replace MAGMOM with {count} default moments",
            kind=CodeActionKind.QuickFix,
            diagnostics=[diagnostic],
            edit=WorkspaceEdit(
                changes={
                    "document": [
                        TextEdit(
                            range=Range(
                                start=Position(line=line_num, character=0),
                                end=Position(line=line_num, character=len(line)),
                            ),
                            new_text=f"MAGMOM = {moments}",
                        )
                    ]
                }
            ),
        )

    def _create_raise_encut_action(
        self, lines: List[str], diagnostic: Diagnostic
    ) -> Optional[CodeAction]:
        """Create action to raise ENCUT to the maximum POTCAR ENMAX."""
        enmax_match = re.search(r"ENMAX=([-+]?\d+(?:\.\d+)?)", diagnostic.message)
        if not enmax_match:
            return None
        enmax = float(enmax_match.group(1))
        line_num = diagnostic.range.start.line
        if line_num >= len(lines):
            return None
        line = lines[line_num]
        value_text = f"{enmax:g}"

        return CodeAction(
            title=f"Set ENCUT to {value_text} eV",
            kind=CodeActionKind.QuickFix,
            diagnostics=[diagnostic],
            edit=WorkspaceEdit(
                changes={
                    "document": [
                        TextEdit(
                            range=Range(
                                start=Position(line=line_num, character=0),
                                end=Position(line=line_num, character=len(line)),
                            ),
                            new_text=f"ENCUT = {value_text}",
                        )
                    ]
                }
            ),
        )

    def _create_fix_typo_action(
        self, lines: List[str], diagnostic: Diagnostic, content: str
    ) -> Optional[CodeAction]:
        """Create action to fix common typos in INCAR tags."""
        # Extract the unknown tag name
        message = diagnostic.message
        if "Unknown INCAR tag:" not in message:
            return None

        tag_name = message.split("Unknown INCAR tag:")[-1].strip()

        # Common typo mappings
        typo_fixes = {
            "ENCUTT": "ENCUT",
            "ENCO": "ENCUT",
            "ISMER": "ISMEAR",
            "ISMAER": "ISMEAR",
            "SIGM": "SIGMA",
            "SIG": "SIGMA",
            "PRECission": "PREC",
            "ALGOO": "ALGO",
            "IBRIO": "IBRION",
            "IBRIONN": "IBRION",
            "NSWW": "NSW",
            "EDIF": "EDIFF",
            "EDIFFG": "EDIFFG",  # Valid but might be typo
            "LREAL": "LREAL",
            "LWAV": "LWAVE",
            "LCHARGG": "LCHARG",
        }

        # Find closest match
        upper_tag = tag_name.upper()
        fixed_tag: Optional[str]
        if upper_tag in typo_fixes:
            fixed_tag = typo_fixes[upper_tag]
        else:
            # Try to find similar tags using simple string similarity
            fixed_tag = self._find_similar_tag(tag_name)

        if not fixed_tag or fixed_tag.upper() == tag_name.upper():
            return None

        # Create the fix
        line_num = diagnostic.range.start.line
        line = lines[line_num]

        # Find the tag in the line
        start_col = line.upper().find(tag_name.upper())
        if start_col == -1:
            return None

        end_col = start_col + len(tag_name)

        return CodeAction(
            title=f"Change '{tag_name}' to '{fixed_tag}'",
            kind=CodeActionKind.QuickFix,
            diagnostics=[diagnostic],
            edit=WorkspaceEdit(
                changes={
                    "document": [
                        TextEdit(
                            range=Range(
                                start=Position(line=line_num, character=start_col),
                                end=Position(line=line_num, character=end_col),
                            ),
                            new_text=fixed_tag,
                        )
                    ]
                }
            ),
        )

    def _find_similar_tag(self, tag_name: str) -> Optional[str]:
        """Find a similar valid tag for a potentially misspelled one."""
        tag_name_upper = tag_name.upper()

        # Simple similarity check: count matching characters
        best_match = None
        best_score: float = 0.0

        for valid_tag in INCAR_TAGS.keys():
            # Calculate simple similarity
            score = self._similarity_score(tag_name_upper, valid_tag.upper())
            if score > best_score and score >= 0.7:  # 70% similarity threshold
                best_score = score
                best_match = valid_tag

        return best_match

    def _similarity_score(self, s1: str, s2: str) -> float:
        """Calculate similarity score between two strings."""
        if not s1 or not s2:
            return 0.0

        # Simple character-based similarity
        len1, len2 = len(s1), len(s2)
        max_len = max(len1, len2)
        matches = sum(c1 == c2 for c1, c2 in zip(s1, s2))

        return matches / max_len

    def _get_poscar_code_actions(
        self, content: str, diagnostics: List[Diagnostic], range: Range
    ) -> List[CodeAction]:
        """Get code actions for POSCAR files."""
        from ..parsers.poscar_parser import POSCARParser

        actions = []
        parser = POSCARParser(content)
        parser.parse()
        lines = content.split("\n")

        for diagnostic in diagnostics:
            message = diagnostic.message.lower()

            # Fix 1: Fix negative scale factor
            if "negative scale factor" in message:
                action = self._create_fix_negative_scale_action(lines, diagnostic, parser)
                if action:
                    actions.append(action)

            # Fix 2: Wrap out-of-range direct coordinates
            if "outside typical range" in message:
                action = self._create_wrap_coordinates_action(lines, diagnostic)
                if action:
                    actions.append(action)

            # Fix 3: Replace extreme scale factor with 1.0
            if "extreme magnitude" in message:
                action = self._create_fix_extreme_scale_action(lines, diagnostic)
                if action:
                    actions.append(action)

            # Fix 4: Remove duplicate coordinate rows
            if "identical coordinates" in message:
                action = self._create_remove_duplicate_atoms_action(lines, diagnostic, parser)
                if action:
                    actions.append(action)

        return actions

    def _get_kpoints_code_actions(
        self, content: str, diagnostics: List[Diagnostic], range: Range
    ) -> List[CodeAction]:
        """Get code actions for KPOINTS files."""
        from ..parsers.kpoints_parser import KPOINTSParser

        actions: List[CodeAction] = []
        parser = KPOINTSParser(content)
        result = parser.parse()
        lines = content.split("\n")

        for diagnostic in diagnostics:
            message = diagnostic.message.lower()

            # Fix 1: Fix non-positive grid values
            if "not positive" in message and "grid" in message:
                action = self._create_fix_grid_action(lines, diagnostic, result)
                if action:
                    actions.append(action)

            # Fix 2: Normalize k-point weights
            if "weights sum" in message:
                action = self._create_normalize_weights_action(lines, diagnostic, result)
                if action:
                    actions.append(action)

            # Fix 3: Fix zero-weight k-points
            if "weight 0.0" in message:
                action = self._create_fix_zero_weights_action(lines, diagnostic, result)
                if action:
                    actions.append(action)

            # Fix 4: Reduce very dense grid
            if "very dense" in message and ">" in message:
                action = self._create_reduce_dense_grid_action(lines, diagnostic, result)
                if action:
                    actions.append(action)

        return actions

    def _create_fix_negative_scale_action(
        self, lines: List[str], diagnostic: Diagnostic, parser
    ) -> Optional[CodeAction]:
        """Create action to fix negative scale factor."""
        # Scale factor is on line 1 (index 1)
        line_num = 1
        line = lines[line_num]

        # Extract the value and make it positive
        try:
            scale = float(line.strip())
            new_scale = abs(scale)
        except ValueError:
            return None

        return CodeAction(
            title=f"Change scale factor to {new_scale}",
            kind=CodeActionKind.QuickFix,
            diagnostics=[diagnostic],
            edit=WorkspaceEdit(
                changes={
                    "document": [
                        TextEdit(
                            range=Range(
                                start=Position(line=line_num, character=0),
                                end=Position(line=line_num, character=len(line)),
                            ),
                            new_text=f"{new_scale}",
                        )
                    ]
                }
            ),
        )

    def _create_wrap_coordinates_action(
        self, lines: List[str], diagnostic: Diagnostic
    ) -> Optional[CodeAction]:
        """Create action to wrap coordinates to [0, 1] range."""
        line_num = diagnostic.range.start.line
        line = lines[line_num]
        parts = line.strip().split()

        if len(parts) < 3:
            return None

        try:
            new_coords = []
            for i in range(3):
                val = float(parts[i])
                # Wrap to [0, 1] range
                wrapped = val - int(val)
                if wrapped < 0:
                    wrapped += 1.0
                new_coords.append(f"{wrapped:.6f}")
        except ValueError:
            return None

        new_line = " ".join(new_coords)
        if len(parts) > 3:
            new_line += " " + " ".join(parts[3:])

        return CodeAction(
            title="Wrap coordinates to [0, 1] range",
            kind=CodeActionKind.QuickFix,
            diagnostics=[diagnostic],
            edit=WorkspaceEdit(
                changes={
                    "document": [
                        TextEdit(
                            range=Range(
                                start=Position(line=line_num, character=0),
                                end=Position(line=line_num, character=len(line)),
                            ),
                            new_text=new_line,
                        )
                    ]
                }
            ),
        )

    def _create_fix_extreme_scale_action(
        self, lines: List[str], diagnostic: Diagnostic
    ) -> Optional[CodeAction]:
        """Create action to replace extreme scale factor with 1.0."""
        line_num = 1  # Scale factor is always on line 1 (0-indexed)
        if line_num >= len(lines):
            return None
        return CodeAction(
            title="Replace extreme scale factor with 1.0",
            kind=CodeActionKind.QuickFix,
            diagnostics=[diagnostic],
            edit=WorkspaceEdit(
                changes={
                    "document": [
                        TextEdit(
                            range=Range(
                                start=Position(line=line_num, character=0),
                                end=Position(line=line_num, character=len(lines[line_num])),
                            ),
                            new_text="1.0",
                        )
                    ]
                }
            ),
        )

    def _create_remove_duplicate_atoms_action(
        self, lines: List[str], diagnostic: Diagnostic, parser
    ) -> Optional[CodeAction]:
        """Create action to remove duplicate coordinate rows (keep first occurrence)."""
        if not parser.data:
            return None

        result = parser.data
        coords = result.coordinates
        tolerance = 1e-6
        tol_sq = tolerance * tolerance

        duplicate_indices: List[int] = []
        seen: List[List[float]] = []

        for i, coord in enumerate(coords):
            is_dup = False
            for seen_coord in seen:
                dist_sq = sum((a - b) ** 2 for a, b in zip(coord, seen_coord))
                if dist_sq < tol_sq:
                    is_dup = True
                    break
            if is_dup:
                duplicate_indices.append(i)
            else:
                seen.append(coord)

        if not duplicate_indices:
            return None

        # Build edits: remove duplicate lines in reverse order
        edits: List[TextEdit] = []
        for idx in reversed(duplicate_indices):
            line_num = max(result.coordinate_start_line - 1 + idx, 0)
            if line_num < len(lines):
                end_line = line_num + 1
                end_char = 0
                if end_line < len(lines):
                    end_char = 0
                else:
                    end_char = len(lines[line_num])
                edits.append(
                    TextEdit(
                        range=Range(
                            start=Position(line=line_num, character=0),
                            end=Position(line=end_line, character=end_char),
                        ),
                        new_text="",
                    )
                )

        if not edits:
            return None

        return CodeAction(
            title=f"Remove {len(duplicate_indices)} duplicate atom(s)",
            kind=CodeActionKind.QuickFix,
            diagnostics=[diagnostic],
            edit=WorkspaceEdit(changes={"document": edits}),
        )

    def _create_fix_grid_action(
        self, lines: List[str], diagnostic: Diagnostic, result
    ) -> Optional[CodeAction]:
        """Create action to fix non-positive grid values."""
        if not result or not result.grid:
            return None

        line_num = 2  # Grid line
        line = lines[line_num]

        # Fix grid values to be at least 1
        new_grid = [max(1, g) for g in result.grid]
        new_line = " ".join(str(g) for g in new_grid)

        return CodeAction(
            title=f"Set grid to {' '.join(str(g) for g in new_grid)}",
            kind=CodeActionKind.QuickFix,
            diagnostics=[diagnostic],
            edit=WorkspaceEdit(
                changes={
                    "document": [
                        TextEdit(
                            range=Range(
                                start=Position(line=line_num, character=0),
                                end=Position(line=line_num, character=len(line)),
                            ),
                            new_text=new_line,
                        )
                    ]
                }
            ),
        )

    def _create_normalize_weights_action(
        self, lines: List[str], diagnostic: Diagnostic, result
    ) -> Optional[CodeAction]:
        """Create action to normalize k-point weights to sum to 1.0."""
        if not result or not result.weights:
            return None

        total_weight = sum(result.weights)
        if total_weight == 0:
            return None

        # Normalize weights
        normalized = [w / total_weight for w in result.weights]

        # Find the lines with k-point weights
        actions = []
        for i, weight in enumerate(normalized):
            # Line numbers for explicit k-points start after header
            # This is approximate; actual line depends on file format
            line_num = 3 + i
            if line_num < len(lines):
                line = lines[line_num]
                parts = line.strip().split()
                if len(parts) >= 4:
                    # Replace the weight (4th column)
                    try:
                        # Validate that parts[3] is a valid float
                        float(parts[3])
                        new_line = line.replace(parts[3], f"{weight:.6f}")
                        actions.append(
                            CodeAction(
                                title="Normalize k-point weights (sum=1.0)",
                                kind=CodeActionKind.QuickFix,
                                diagnostics=[diagnostic],
                                edit=WorkspaceEdit(
                                    changes={
                                        "document": [
                                            TextEdit(
                                                range=Range(
                                                    start=Position(line=line_num, character=0),
                                                    end=Position(
                                                        line=line_num,
                                                        character=len(line),
                                                    ),
                                                ),
                                                new_text=new_line,
                                            )
                                        ]
                                    }
                                ),
                            )
                        )
                        break  # Only add one action
                    except ValueError:
                        continue

        return actions[0] if actions else None

    def _create_fix_zero_weights_action(
        self, lines: List[str], diagnostic: Diagnostic, result
    ) -> Optional[CodeAction]:
        """Create action to fix zero-weight k-points by distributing equal weight."""
        if not result or not result.weights:
            return None

        n_kpoints = len(result.weights)
        if n_kpoints == 0:
            return None

        equal_weight = 1.0 / n_kpoints
        edits = []
        for i, weight in enumerate(result.weights):
            if weight == 0.0:
                line_num = 3 + i  # k-points start at line 4 (0-indexed: 3)
                if line_num >= len(lines):
                    continue
                line = lines[line_num]
                parts = line.strip().split()
                if len(parts) >= 4:
                    try:
                        float(parts[3])  # Validate current weight is numeric
                        new_line = line.replace(parts[3], f"{equal_weight:.6f}")
                        edits.append(
                            TextEdit(
                                range=Range(
                                    start=Position(line=line_num, character=0),
                                    end=Position(line=line_num, character=len(line)),
                                ),
                                new_text=new_line,
                            )
                        )
                    except ValueError:
                        continue

        if not edits:
            return None

        return CodeAction(
            title=f"Set zero-weight k-points to {equal_weight:.4f} (1/{n_kpoints})",
            kind=CodeActionKind.QuickFix,
            diagnostics=[diagnostic],
            edit=WorkspaceEdit(changes={"document": edits}),
        )

    def _create_reduce_dense_grid_action(
        self, lines: List[str], diagnostic: Diagnostic, result
    ) -> Optional[CodeAction]:
        """Create action to reduce a very dense grid by capping at max_value while preserving ratios."""
        if not result or not result.grid:
            return None

        max_cap = 50
        grid = result.grid

        # Cap values while preserving ratios
        capped = [min(g, max_cap) for g in grid]
        new_line = " ".join(str(g) for g in capped)
        line_num = 2  # Grid is on line 3 (0-indexed: 2)

        if line_num >= len(lines):
            return None

        return CodeAction(
            title=f"Cap grid to {' '.join(str(g) for g in capped)} (max {max_cap})",
            kind=CodeActionKind.QuickFix,
            diagnostics=[diagnostic],
            edit=WorkspaceEdit(
                changes={
                    "document": [
                        TextEdit(
                            range=Range(
                                start=Position(line=line_num, character=0),
                                end=Position(line=line_num, character=len(lines[line_num])),
                            ),
                            new_text=new_line,
                        )
                    ]
                }
            ),
        )
