"""Diagnostics provider for VASP-LSP."""

import json
import math
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

from lsprotocol.types import Diagnostic, DiagnosticSeverity, Position, Range

from ..parsers.incar_parser import INCARParser
from ..parsers.kpoints_parser import KPOINTSMode, KPOINTSParser
from ..parsers.poscar_parser import POSCARParser
from ..parsers.potcar_parser import POTCARParser
from ..parsers.vasp_log_parser import VASPLogDiagnostic, VASPLogParser
from ..rules import (
    ENCUT_BELOW_ENMAX,
    INVALID_INCAR_TAG,
    INVALID_INCAR_VALUE,
    PARALLEL_KPAR_INCOMPATIBLE,
    PARALLEL_NCORE_NPAR_CONFLICT,
    SMEARING_ISMEAR_SIGMA_MISMATCH,
    SPIN_MISSING_MAGMOM,
    get_rule_fix_hint,
)
from ..schemas.incar_tags import CALCULATION_MODES, CalculationMode, get_tag_info


class DiagnosticsProvider:
    """Provides diagnostics (error checking) for VASP files."""

    def __init__(self):
        """Initialize diagnostics provider."""
        pass

    def get_diagnostics(
        self,
        document_content: str,
        document_uri: str,
        workspace_documents: Optional[Dict[str, str]] = None,
    ) -> List[Diagnostic]:
        """Get diagnostics for the document.

        Args:
            document_content: Full document content.
            document_uri: Document URI to determine file type.

        Returns:
            List of diagnostic messages.
        """
        file_type = self._get_file_type(document_uri)

        if file_type == "INCAR":
            return self._get_incar_diagnostics(document_content, document_uri, workspace_documents)
        elif file_type == "POSCAR":
            return self._get_poscar_diagnostics(document_content)
        elif file_type == "KPOINTS":
            return self._get_kpoints_diagnostics(document_content)
        elif file_type == "VASP_LOG":
            return self._get_vasp_log_diagnostics(document_content, document_uri)

        return []

    # ------------------------------------------------------------------
    # Diagnostic snapshot for agent feedback loops (#18)
    # ------------------------------------------------------------------

    def get_diagnostics_snapshot(
        self,
        document_content: str,
        document_uri: str,
        workspace_documents: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Return a structured snapshot of diagnostics suitable for agent consumption.

        Issue #18: live diagnostics snapshots.

        Returns a dict with keys:
          - uri: the document URI
          - file_type: INCAR, POSCAR, KPOINTS, or UNKNOWN
          - diagnostics: list of dicts (message, severity, line, character, source)
          - summary: counts by severity
          - calculation_mode: detected mode (if INCAR)
          - tags: parsed tag-value pairs (if INCAR)
        """
        file_type = self._get_file_type(document_uri)
        diagnostics = self.get_diagnostics(document_content, document_uri, workspace_documents)

        diag_dicts: List[Dict[str, Any]] = []
        severity_counts: Dict[str, int] = {
            "error": 0,
            "warning": 0,
            "information": 0,
            "hint": 0,
        }

        for d in diagnostics:
            sev = self._severity_to_str(d.severity)
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            diag_dict: Dict[str, Any] = {
                "message": d.message,
                "severity": sev,
                "line": d.range.start.line + 1,  # 1-based for agents
                "character": d.range.start.character,
                "end_line": d.range.end.line + 1,
                "end_character": d.range.end.character,
                "source": d.source,
            }
            code = getattr(d, "code", None)
            if code is not None:
                diag_dict["code"] = str(code)
            data = getattr(d, "data", None)
            if isinstance(data, dict):
                for key in (
                    "confidence",
                    "category",
                    "related_files",
                    "suggested_actions",
                    "safe_to_auto_apply",
                ):
                    if key in data:
                        diag_dict[key] = data[key]
            diag_dicts.append(diag_dict)

        snapshot: Dict[str, Any] = {
            "uri": document_uri,
            "file_type": file_type,
            "diagnostics": diag_dicts,
            "summary": severity_counts,
        }

        # Add INCAR-specific metadata
        if file_type == "INCAR":
            parser = INCARParser(document_content)
            parser.parse()
            tags = {}
            for name, param in parser.get_all_parameters().items():
                tags[name] = {
                    "value": param.value,
                    "line": param.line_number,
                }
            snapshot["tags"] = tags

            # Detect calculation mode
            all_params = parser.get_all_parameters()
            for mode in CALCULATION_MODES:
                if self._is_mode_active(mode, all_params):
                    snapshot["calculation_mode"] = {
                        "name": mode.name,
                        "description": mode.description,
                    }
                    break

        return snapshot

    @staticmethod
    def _severity_to_str(severity) -> str:
        """Convert lsprotocol DiagnosticSeverity to string."""
        if severity == DiagnosticSeverity.Error:
            return "error"
        elif severity == DiagnosticSeverity.Warning:
            return "warning"
        elif severity == DiagnosticSeverity.Information:
            return "information"
        elif severity == DiagnosticSeverity.Hint:
            return "hint"
        return "unknown"

    def _get_file_type(self, uri: str) -> str:
        """Determine file type from URI."""
        path = unquote(urlparse(uri).path) if "://" in uri else uri
        filename = path.split("/")[-1]
        upper_filename = filename.upper()

        if "INCAR" in upper_filename:
            return "INCAR"
        if "POSCAR" in upper_filename or "CONTCAR" in upper_filename:
            return "POSCAR"
        if "KPOINTS" in upper_filename:
            return "KPOINTS"
        if self._is_vasp_log_filename(filename):
            return "VASP_LOG"

        return "UNKNOWN"

    def _is_vasp_log_filename(self, filename: str) -> bool:
        """Return whether a filename is a VASP runtime log."""
        upper_filename = filename.upper()
        if upper_filename in {"OUTCAR", "OSZICAR", "STDOUT", "STDERR", "VASP.OUT"}:
            return True
        if upper_filename.startswith("SLURM-") and upper_filename.endswith(".OUT"):
            return True
        return upper_filename.endswith(".LOG")

    def _get_vasp_log_diagnostics(self, content: str, document_uri: str) -> List[Diagnostic]:
        """Get diagnostics for VASP runtime logs."""
        return [
            self._runtime_log_diagnostic_to_lsp(runtime_diagnostic)
            for runtime_diagnostic in VASPLogParser(content, document_uri).parse()
        ]

    def _runtime_log_diagnostic_to_lsp(self, runtime_diagnostic: VASPLogDiagnostic) -> Diagnostic:
        action_titles = [action.title for action in runtime_diagnostic.suggested_actions]
        action_suffix = ""
        if action_titles:
            action_suffix = f" Suggested actions: {', '.join(action_titles)}."
        line_text = runtime_diagnostic.line_text.strip()
        end_character = max(len(runtime_diagnostic.line_text), 1)
        return Diagnostic(
            range=Range(
                start=Position(line=runtime_diagnostic.line_index, character=0),
                end=Position(line=runtime_diagnostic.line_index, character=end_character),
            ),
            message=(
                f"{runtime_diagnostic.id}: VASP runtime log matched '{line_text}'."
                f"{action_suffix}"
            ),
            severity=self._runtime_severity_to_lsp(runtime_diagnostic.severity),
            source="vasp-lsp-runtime",
            code=runtime_diagnostic.id,
            data={
                "confidence": runtime_diagnostic.confidence,
                "category": runtime_diagnostic.category,
                "related_files": list(runtime_diagnostic.related_files),
                "suggested_actions": [
                    {
                        "title": action.title,
                        "safe_to_auto_apply": action.safe_to_auto_apply,
                        "target_file": action.target_file,
                    }
                    for action in runtime_diagnostic.suggested_actions
                ],
                "safe_to_auto_apply": all(
                    action.safe_to_auto_apply for action in runtime_diagnostic.suggested_actions
                ),
            },
        )

    def _runtime_severity_to_lsp(self, severity: str) -> DiagnosticSeverity:
        if severity == "error":
            return DiagnosticSeverity.Error
        if severity == "warning":
            return DiagnosticSeverity.Warning
        if severity == "hint":
            return DiagnosticSeverity.Hint
        return DiagnosticSeverity.Information

    def _get_incar_diagnostics(
        self,
        content: str,
        document_uri: str = "",
        workspace_documents: Optional[Dict[str, str]] = None,
    ) -> List[Diagnostic]:
        """Get diagnostics for INCAR files."""
        diagnostics = []

        # Parse the INCAR file
        parser = INCARParser(content)
        parser.parse()

        # Report parse errors
        for error in parser.get_errors():
            severity = (
                DiagnosticSeverity.Error
                if error["severity"] == "error"
                else DiagnosticSeverity.Warning
            )

            diagnostic = Diagnostic(
                range=Range(
                    start=Position(line=error["line"] - 1, character=error.get("column", 0)),
                    end=Position(line=error["line"] - 1, character=error.get("column", 0) + 1),
                ),
                message=error["message"],
                severity=severity,
                source="vasp-lsp",
            )
            diagnostics.append(diagnostic)

        # Check for unknown tags -> vasp.incar.invalid_tag (#51).
        # Upstream INCAR is the authoritative schema, so unknown tags ship at
        # error severity with the rule's stable code and metadata.
        for param_name, param in parser.get_all_parameters().items():
            if get_tag_info(param_name) is None:
                diagnostics.append(self._invalid_incar_tag_diagnostic(param_name, param))
            else:
                tag = get_tag_info(param_name)
                value_diagnostics = self._validate_incar_value(tag, param, content)
                diagnostics.extend(value_diagnostics)

        # Check for parameter dependencies and conflicts
        diagnostics.extend(self._check_incar_dependencies(parser))
        diagnostics.extend(
            self._check_workspace_consistency(parser, document_uri, workspace_documents)
        )

        # Schema-aware checks: calculation-mode required tags (#21)
        diagnostics.extend(self._check_calculation_modes(parser))

        # Schema-aware checks: tag conflicts via metadata (#20)
        diagnostics.extend(self._check_schema_conflicts(parser))

        return diagnostics

    def _invalid_incar_tag_diagnostic(self, tag_name: str, param) -> Diagnostic:
        """Build the vasp.incar.invalid_tag diagnostic for an unknown INCAR tag.

        The range underlines just the tag name (not the whole assignment) so
        editors can render a precise squiggle. Rule metadata (category,
        confidence, manual_ref, fix_hint) travels on ``Diagnostic.data`` so
        the agent-facing rich JSON contract surfaces it.
        """
        name_start = max(int(param.column_start), 0)
        name_end = max(name_start + len(tag_name), name_start + 1)
        line_index = param.line_number - 1
        fix_hint = get_rule_fix_hint(INVALID_INCAR_TAG["rule_id"])
        return Diagnostic(
            range=Range(
                start=Position(line=line_index, character=name_start),
                end=Position(line=line_index, character=name_end),
            ),
            message=f"Unknown INCAR tag: {tag_name}",
            severity=DiagnosticSeverity.Error,
            source="vasp-lsp",
            code=INVALID_INCAR_TAG["rule_id"],
            data={
                "category": INVALID_INCAR_TAG["category"],
                "confidence": INVALID_INCAR_TAG["confidence"],
                "manual_ref": INVALID_INCAR_TAG["manual_ref"],
                "fix_hints": [fix_hint] if fix_hint else [],
            },
        )

    def _spin_missing_magmom_diagnostic(self, ispin) -> Diagnostic:
        """Build the vasp.spin.missing_magmom diagnostic for ISPIN=2 without MAGMOM.

        The range underlines the whole ISPIN assignment (the keyword the user
        must reconcile with a MAGMOM entry). Rule metadata (category,
        confidence, manual_ref, fix_hint) travels on ``Diagnostic.data`` so
        the agent-facing rich JSON contract surfaces it.
        """
        line_index = ispin.line_number - 1
        line_end = max(len(ispin.raw_line), 1)
        fix_hint = get_rule_fix_hint(SPIN_MISSING_MAGMOM["rule_id"])
        return Diagnostic(
            range=Range(
                start=Position(line=line_index, character=0),
                end=Position(line=line_index, character=line_end),
            ),
            message="ISPIN=2 (spin-polarized) should have MAGMOM set for initial magnetic moments.",
            severity=DiagnosticSeverity.Warning,
            source="vasp-lsp",
            code=SPIN_MISSING_MAGMOM["rule_id"],
            data={
                "category": SPIN_MISSING_MAGMOM["category"],
                "confidence": SPIN_MISSING_MAGMOM["confidence"],
                "manual_ref": SPIN_MISSING_MAGMOM["manual_ref"],
                "fix_hints": [fix_hint] if fix_hint else [],
            },
        )

    def _ismear_sigma_missing_diagnostic(self, ismear) -> Diagnostic:
        """Build the vasp.smearing.ismear_sigma_mismatch diagnostic for ISMEAR >= 0 without SIGMA.

        For Gaussian / Methfessel-Paxton smearing (ISMEAR >= 0) SIGMA sets the
        width; leaving it unset falls back to the VASP default of 0.2 eV. The
        range underlines the whole ISMEAR assignment (the keyword the user must
        reconcile with a SIGMA entry). Rule metadata (category, confidence,
        manual_ref, fix_hint) travels on ``Diagnostic.data`` so the
        agent-facing rich JSON contract surfaces it.
        """
        line_index = ismear.line_number - 1
        line_end = max(len(ismear.raw_line), 1)
        fix_hint = get_rule_fix_hint(SMEARING_ISMEAR_SIGMA_MISMATCH["rule_id"])
        return Diagnostic(
            range=Range(
                start=Position(line=line_index, character=0),
                end=Position(line=line_index, character=line_end),
            ),
            message="ISMEAR >= 0 should have SIGMA set. Default SIGMA=0.2 may not be appropriate.",
            severity=DiagnosticSeverity.Warning,
            source="vasp-lsp",
            code=SMEARING_ISMEAR_SIGMA_MISMATCH["rule_id"],
            data={
                "category": SMEARING_ISMEAR_SIGMA_MISMATCH["category"],
                "confidence": SMEARING_ISMEAR_SIGMA_MISMATCH["confidence"],
                "manual_ref": SMEARING_ISMEAR_SIGMA_MISMATCH["manual_ref"],
                "fix_hints": [fix_hint] if fix_hint else [],
            },
        )

    def _ismear_sigma_unused_diagnostic(self, sigma) -> Diagnostic:
        """Build the vasp.smearing.ismear_sigma_mismatch diagnostic for SIGMA set with ISMEAR < 0.

        For the tetrahedron method (ISMEAR < 0) SIGMA is unused, so declaring
        it is misleading. The range underlines the whole SIGMA assignment (the
        keyword the user should reconcile or remove). Rule metadata (category,
        confidence, manual_ref, fix_hint) travels on ``Diagnostic.data`` so the
        agent-facing rich JSON contract surfaces it.
        """
        line_index = sigma.line_number - 1
        line_end = max(len(sigma.raw_line), 1)
        fix_hint = get_rule_fix_hint(SMEARING_ISMEAR_SIGMA_MISMATCH["rule_id"])
        return Diagnostic(
            range=Range(
                start=Position(line=line_index, character=0),
                end=Position(line=line_index, character=line_end),
            ),
            message=(
                "SIGMA is set but ISMEAR < 0 (tetrahedron method). "
                "SIGMA is not used with the tetrahedron method."
            ),
            severity=DiagnosticSeverity.Warning,
            source="vasp-lsp",
            code=SMEARING_ISMEAR_SIGMA_MISMATCH["rule_id"],
            data={
                "category": SMEARING_ISMEAR_SIGMA_MISMATCH["category"],
                "confidence": SMEARING_ISMEAR_SIGMA_MISMATCH["confidence"],
                "manual_ref": SMEARING_ISMEAR_SIGMA_MISMATCH["manual_ref"],
                "fix_hints": [fix_hint] if fix_hint else [],
            },
        )

    def _encut_below_enmax_diagnostic(self, encut, max_enmax: float) -> Diagnostic:
        """Build the vasp.encut.below_enmax diagnostic for ENCUT < max POTCAR ENMAX.

        Each pseudopotential dataset is shipped with a recommended plane-wave
        cutoff (ENMAX); running ENCUT below the largest ENMAX degrades the
        basis set the pseudopotentials were balanced for. The range underlines
        the whole ENCUT assignment (the keyword the user should reconcile with
        the POTCAR evidence). Rule metadata (category, confidence, manual_ref,
        fix_hint) travels on ``Diagnostic.data`` so the agent-facing rich JSON
        contract surfaces it.
        """
        line_index = encut.line_number - 1
        line_end = max(len(encut.raw_line), 1)
        fix_hint = get_rule_fix_hint(ENCUT_BELOW_ENMAX["rule_id"])
        return Diagnostic(
            range=Range(
                start=Position(line=line_index, character=0),
                end=Position(line=line_index, character=line_end),
            ),
            message=f"ENCUT={encut.value:g} is below max POTCAR ENMAX={max_enmax:g} eV.",
            severity=DiagnosticSeverity.Warning,
            source="vasp-lsp",
            code=ENCUT_BELOW_ENMAX["rule_id"],
            data={
                "category": ENCUT_BELOW_ENMAX["category"],
                "confidence": ENCUT_BELOW_ENMAX["confidence"],
                "manual_ref": ENCUT_BELOW_ENMAX["manual_ref"],
                "fix_hints": [fix_hint] if fix_hint else [],
            },
        )

    def _ncore_npar_conflict_diagnostic(self, npar) -> Diagnostic:
        """Build the vasp.parallel.ncore_npar_conflict diagnostic.

        NCORE and NPAR are mutually-exclusive parallelism controls: NCORE
        sets the cores per orbital and NPAR sets the parallel band groups;
        VASP derives one from the other, so declaring both is contradictory.
        The range underlines the whole NPAR assignment (the keyword the user
        should remove in favour of NCORE). Rule metadata (category,
        confidence, manual_ref, fix_hint) travels on ``Diagnostic.data`` so
        the agent-facing rich JSON contract surfaces it. The message keeps
        both ``NPAR`` and ``NCORE`` substrings so the existing quickfix
        (remove NPAR) still anchors on this diagnostic.
        """
        line_index = npar.line_number - 1
        line_end = max(len(npar.raw_line), 1)
        fix_hint = get_rule_fix_hint(PARALLEL_NCORE_NPAR_CONFLICT["rule_id"])
        return Diagnostic(
            range=Range(
                start=Position(line=line_index, character=0),
                end=Position(line=line_index, character=line_end),
            ),
            message="NPAR and NCORE should not be set together. Prefer NCORE.",
            severity=DiagnosticSeverity.Warning,
            source="vasp-lsp",
            code=PARALLEL_NCORE_NPAR_CONFLICT["rule_id"],
            data={
                "category": PARALLEL_NCORE_NPAR_CONFLICT["category"],
                "confidence": PARALLEL_NCORE_NPAR_CONFLICT["confidence"],
                "manual_ref": PARALLEL_NCORE_NPAR_CONFLICT["manual_ref"],
                "fix_hints": [fix_hint] if fix_hint else [],
            },
        )

    def _kpar_incompatible_diagnostic(self, band_param, band_name: str) -> Diagnostic:
        """Build the vasp.parallel.kpar_incompatible diagnostic.

        KPAR partitions the MPI ranks into k-point groups while NCORE/NPAR
        partition the remaining ranks within each group over bands/orbitals;
        the two flag families operate on different MPI partitioning axes, so
        declaring KPAR > 1 together with a band-level flag (NCORE > 1 or
        NPAR > 1) leaves the combined layout undefined. The range underlines
        the whole band-parallelism assignment (the keyword the user should
        reconcile with the k-point parallelization). Rule metadata travels on
        ``Diagnostic.data`` so the agent-facing rich JSON contract surfaces it.
        The message keeps both ``KPAR`` and the band flag substring so
        quickfixes still anchor on this diagnostic.
        """
        line_index = band_param.line_number - 1
        line_end = max(len(band_param.raw_line), 1)
        fix_hint = get_rule_fix_hint(PARALLEL_KPAR_INCOMPATIBLE["rule_id"])
        return Diagnostic(
            range=Range(
                start=Position(line=line_index, character=0),
                end=Position(line=line_index, character=line_end),
            ),
            message=(
                f"KPAR and {band_name} operate on different parallelization "
                f"axes and should not be set together."
            ),
            severity=DiagnosticSeverity.Warning,
            source="vasp-lsp",
            code=PARALLEL_KPAR_INCOMPATIBLE["rule_id"],
            data={
                "category": PARALLEL_KPAR_INCOMPATIBLE["category"],
                "confidence": PARALLEL_KPAR_INCOMPATIBLE["confidence"],
                "manual_ref": PARALLEL_KPAR_INCOMPATIBLE["manual_ref"],
                "fix_hints": [fix_hint] if fix_hint else [],
            },
        )

    def _validate_incar_value(self, tag, param, content) -> List[Diagnostic]:
        """Validate a single INCAR parameter value against schema metadata.

        Checks: type, enum membership (with case sensitivity), valid range,
        and reports expected unit for numeric tags.
        """
        diagnostics = []
        value = param.value
        expected_type = tag.type

        # --- Type checking ---
        if expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            diagnostics.append(
                self._value_type_diagnostic(param, f"{tag.name} expects an integer value.")
            )
        elif expected_type == "float" and (
            not isinstance(value, (int, float)) or isinstance(value, bool)
        ):
            diagnostics.append(
                self._value_type_diagnostic(param, f"{tag.name} expects a float value.")
            )
        elif expected_type == "boolean" and not isinstance(value, bool):
            diagnostics.append(
                self._value_type_diagnostic(param, f"{tag.name} expects a boolean value.")
            )
        elif expected_type == "string" and isinstance(value, list):
            diagnostics.append(
                self._value_type_diagnostic(param, f"{tag.name} expects a single string value.")
            )
        # Array-valued INCAR tags may legitimately contain one scalar value when
        # the structure has one species or one atom, so their length is checked
        # with workspace context instead of treated as a scalar type error here.

        # --- Enum validation ---
        if tag.enum_values and value is not None:
            if tag.case_sensitive:
                # Case-sensitive enum check: exact match required
                str_value = str(value)
                if str_value not in tag.enum_values:
                    diagnostics.append(
                        Diagnostic(
                            range=Range(
                                start=Position(
                                    line=param.line_number - 1,
                                    character=param.column_start,
                                ),
                                end=Position(
                                    line=param.line_number - 1,
                                    character=param.column_end,
                                ),
                            ),
                            message=(
                                f"Invalid value '{str_value}' for {tag.name}. "
                                f"Allowed (case-sensitive): {', '.join(tag.enum_values)}"
                            ),
                            severity=DiagnosticSeverity.Error,
                            source="vasp-lsp",
                        )
                    )
            else:
                # Case-insensitive enum check (legacy behavior)
                str_value = str(value).upper()
                valid_values = [v.upper() for v in tag.enum_values]
                if str_value not in valid_values:
                    # Try to match as number
                    try:
                        num_value = float(value)
                        if str(int(num_value)) not in valid_values:
                            diagnostics.append(
                                Diagnostic(
                                    range=Range(
                                        start=Position(
                                            line=param.line_number - 1,
                                            character=param.column_start,
                                        ),
                                        end=Position(
                                            line=param.line_number - 1,
                                            character=param.column_end,
                                        ),
                                    ),
                                    message=(
                                        f"Invalid value for {tag.name}. "
                                        f"Allowed: {', '.join(tag.enum_values)}"
                                    ),
                                    severity=DiagnosticSeverity.Warning,
                                    source="vasp-lsp",
                                )
                            )
                    except (ValueError, TypeError):
                        diagnostics.append(
                            Diagnostic(
                                range=Range(
                                    start=Position(
                                        line=param.line_number - 1,
                                        character=param.column_start,
                                    ),
                                    end=Position(
                                        line=param.line_number - 1,
                                        character=param.column_end,
                                    ),
                                ),
                                message=(
                                    f"Invalid value for {tag.name}. "
                                    f"Allowed: {', '.join(tag.enum_values)}"
                                ),
                                severity=DiagnosticSeverity.Warning,
                                source="vasp-lsp",
                            )
                        )

        # --- Range validation for numeric values ---
        if tag.valid_range and isinstance(value, (int, float)):
            min_val, max_val = tag.valid_range
            unit_hint = f" ({tag.unit})" if tag.unit else ""
            if min_val is not None and value < min_val:
                diagnostics.append(
                    Diagnostic(
                        range=Range(
                            start=Position(
                                line=param.line_number - 1, character=param.column_start
                            ),
                            end=Position(line=param.line_number - 1, character=param.column_end),
                        ),
                        message=(
                            f"Value {value} is below minimum {min_val} for {tag.name}{unit_hint}."
                        ),
                        severity=DiagnosticSeverity.Warning,
                        source="vasp-lsp",
                    )
                )
            if max_val is not None and value > max_val:
                diagnostics.append(
                    Diagnostic(
                        range=Range(
                            start=Position(
                                line=param.line_number - 1, character=param.column_start
                            ),
                            end=Position(line=param.line_number - 1, character=param.column_end),
                        ),
                        message=(
                            f"Value {value} is above maximum {max_val} for {tag.name}{unit_hint}."
                        ),
                        severity=DiagnosticSeverity.Warning,
                        source="vasp-lsp",
                    )
                )

        return diagnostics

    def _value_type_diagnostic(self, param, message: str) -> Diagnostic:
        return self._invalid_incar_value_diagnostic(param, message)

    def _value_token_range(self, param) -> Range:
        """Compute a range that underlines just the value token.

        The parser stores ``column_start`` at the tag name and ``column_end``
        at the end of the parsed value group, which spans the whole
        ``name = value`` assignment. For the vasp.incar.invalid_value rule we
        want a precise squiggle over the offending value, so we re-locate the
        value token from ``raw_line`` and fall back to the assignment range.
        """
        line_index = param.line_number - 1
        raw_line = getattr(param, "raw_line", "") or ""
        equals = raw_line.find("=")
        if equals == -1:
            return Range(
                start=Position(line=line_index, character=param.column_start),
                end=Position(line=line_index, character=param.column_end),
            )
        value_start = equals + 1
        # Skip whitespace between '=' and the value token.
        while value_start < len(raw_line) and raw_line[value_start].isspace():
            value_start += 1
        value_end = max(value_start + 1, param.column_end)
        return Range(
            start=Position(line=line_index, character=value_start),
            end=Position(line=line_index, character=value_end),
        )

    def _invalid_incar_value_diagnostic(self, param, message: str) -> Diagnostic:
        """Build the vasp.incar.invalid_value diagnostic for a wrong-type value.

        The range underlines just the value token so editors can render a
        precise squiggle on the offending value. Rule metadata (category,
        confidence, manual_ref, fix_hint) travels on ``Diagnostic.data`` so
        the agent-facing rich JSON contract surfaces it.
        """
        fix_hint = get_rule_fix_hint(INVALID_INCAR_VALUE["rule_id"])
        return Diagnostic(
            range=self._value_token_range(param),
            message=message,
            severity=DiagnosticSeverity.Error,
            source="vasp-lsp",
            code=INVALID_INCAR_VALUE["rule_id"],
            data={
                "category": INVALID_INCAR_VALUE["category"],
                "confidence": INVALID_INCAR_VALUE["confidence"],
                "manual_ref": INVALID_INCAR_VALUE["manual_ref"],
                "fix_hints": [fix_hint] if fix_hint else [],
            },
        )

    def _check_incar_dependencies(self, parser: INCARParser) -> List[Diagnostic]:
        """Check for parameter dependencies and conflicts."""
        diagnostics = []

        # Check ISMEAR and SIGMA relationship -> vasp.smearing.ismear_sigma_mismatch (#54).
        # For ISMEAR >= 0 (Gaussian / Methfessel-Paxton) SIGMA sets the smearing
        # width; without it VASP falls back to the 0.2 eV default, which is rarely
        # the intended width. Upstream behavior, not a hard runtime failure, so the
        # rule ships at warning severity with the rule's stable code and metadata.
        ismear = parser.get_parameter("ISMEAR")
        sigma = parser.get_parameter("SIGMA")

        if ismear and not sigma:
            if isinstance(ismear.value, int) and ismear.value >= 0:
                diagnostics.append(self._ismear_sigma_missing_diagnostic(ismear))

        # Check NCORE and NPAR conflict -> vasp.parallel.ncore_npar_conflict
        # (#56). NCORE (cores per orbital) and NPAR (parallel band groups) are
        # mutually-exclusive parallelism controls; VASP derives one from the
        # other, so declaring both is contradictory. Upstream behavior, not a
        # hard runtime failure, so the rule ships at warning severity with the
        # rule's stable code and metadata. The schema-driven conflicts_with
        # check (NPAR.conflicts_with = [NCORE]) would otherwise double-fire
        # the same condition without the rule id, so the pair is owned here
        # and skipped in ``_check_schema_conflicts``.
        ncore = parser.get_parameter("NCORE")
        npar = parser.get_parameter("NPAR")

        if ncore and npar:
            diagnostics.append(self._ncore_npar_conflict_diagnostic(npar))

        # Check KPAR combined with a band-level parallelization flag ->
        # vasp.parallel.kpar_incompatible (#57). KPAR partitions the MPI ranks
        # into k-point groups, while NCORE/NPAR partition the remaining ranks
        # within each group over bands/orbitals; the two flag families operate
        # on different MPI partitioning axes, so declaring KPAR > 1 together
        # with a band-level flag (NCORE > 1 or NPAR > 1) leaves the combined
        # layout undefined. Upstream behavior, not a hard runtime failure, so
        # the rule ships at warning severity with the rule's stable code and
        # metadata. The diagnostic anchors on the band-parallelism flag (the
        # keyword the user should reconcile with the k-point parallelization);
        # NCORE is preferred over NPAR as the anchor when both are present,
        # since NCORE is the recommended band-level flag.
        kpar = parser.get_parameter("KPAR")
        if kpar and isinstance(kpar.value, int) and kpar.value > 1:
            kpar_band_param = None
            kpar_band_name: Optional[str] = None
            ncore_value = self._integer_param_value(ncore) if ncore else None
            if ncore and ncore_value is not None and ncore_value > 1:
                kpar_band_param = ncore
                kpar_band_name = "NCORE"
            else:
                npar_value = self._integer_param_value(npar) if npar else None
                if npar and npar_value is not None and npar_value > 1:
                    kpar_band_param = npar
                    kpar_band_name = "NPAR"
            if kpar_band_param is not None and kpar_band_name is not None:
                diagnostics.append(
                    self._kpar_incompatible_diagnostic(kpar_band_param, kpar_band_name)
                )

        # Check LDAU requirements
        ldau = parser.get_parameter("LDAU")
        if ldau and ldau.value:
            if not parser.get_parameter("LDAUTYPE"):
                diagnostics.append(
                    Diagnostic(
                        range=Range(
                            start=Position(line=ldau.line_number - 1, character=0),
                            end=Position(line=ldau.line_number - 1, character=len(ldau.raw_line)),
                        ),
                        message="LDAU=.TRUE. requires LDAUTYPE to be set.",
                        severity=DiagnosticSeverity.Warning,
                        source="vasp-lsp",
                    )
                )
            if not parser.get_parameter("LDAUL"):
                diagnostics.append(
                    Diagnostic(
                        range=Range(
                            start=Position(line=ldau.line_number - 1, character=0),
                            end=Position(line=ldau.line_number - 1, character=len(ldau.raw_line)),
                        ),
                        message="LDAU=.TRUE. requires LDAUL to be set.",
                        severity=DiagnosticSeverity.Warning,
                        source="vasp-lsp",
                    )
                )
            if not parser.get_parameter("LDAUU"):
                diagnostics.append(
                    Diagnostic(
                        range=Range(
                            start=Position(line=ldau.line_number - 1, character=0),
                            end=Position(line=ldau.line_number - 1, character=len(ldau.raw_line)),
                        ),
                        message="LDAU=.TRUE. requires LDAUU to be set.",
                        severity=DiagnosticSeverity.Warning,
                        source="vasp-lsp",
                    )
                )

        # Check hybrid functional requirements
        lhf = parser.get_parameter("LHFCALC")
        if lhf and lhf.value:
            if not parser.get_parameter("HFSCREEN"):
                pass  # Has default, so optional
            if not parser.get_parameter("PRECFOCK"):
                pass  # Has default

        # Check spin-polarization and MAGMOM -> vasp.spin.missing_magmom (#53).
        # A spin-polarized workflow (ISPIN=2) needs an initial set of magnetic
        # moments via MAGMOM; without it VASP defaults the moments to unity.
        # Upstream behavior, not a hard runtime failure, so the rule ships at
        # warning severity with the rule's stable code and metadata.
        ispin = parser.get_parameter("ISPIN")
        magmom = parser.get_parameter("MAGMOM")

        if ispin and isinstance(ispin.value, int) and ispin.value == 2 and not magmom:
            diagnostics.append(self._spin_missing_magmom_diagnostic(ispin))

        # Check ISMEAR=-5 (tetrahedron) with SIGMA set -> same rule (#54):
        # the tetrahedron method does not use SIGMA, so a stray SIGMA entry is a
        # mismatch. Warning severity with the rule's stable code and metadata.
        if ismear and isinstance(ismear.value, int) and ismear.value < 0 and sigma:
            diagnostics.append(self._ismear_sigma_unused_diagnostic(sigma))

        # Check LCHARG with ICHARG conflict
        lcharg = parser.get_parameter("LCHARG")
        icharg = parser.get_parameter("ICHARG")
        if (
            lcharg
            and lcharg.value
            and icharg
            and isinstance(icharg.value, int)
            and icharg.value == 11
        ):
            diagnostics.append(
                self._parameter_warning(
                    lcharg,
                    "LCHARG=.TRUE. with ICHARG=11: the charge density will be overwritten "
                    "on each step, making the output CHGCAR unreliable.",
                )
            )

        # Check LWAVE with ISTART conflict
        lwave = parser.get_parameter("LWAVE")
        istart = parser.get_parameter("ISTART")
        if lwave and lwave.value and istart and isinstance(istart.value, int) and istart.value == 0:
            diagnostics.append(
                self._parameter_info(
                    lwave,
                    "LWAVE=.TRUE. with ISTART=0: wavefunctions will be written but not "
                    "read on restart. Consider whether LWAVE is needed.",
                )
            )

        # Check IBRION=0 (MD) with NSW=0 (no ionic steps)
        ibrion = parser.get_parameter("IBRION")
        nsw = parser.get_parameter("NSW")
        if (
            ibrion
            and isinstance(ibrion.value, int)
            and ibrion.value == 0
            and nsw
            and isinstance(nsw.value, int)
            and nsw.value == 0
        ):
            diagnostics.append(
                self._parameter_warning(
                    ibrion,
                    "IBRION=0 (molecular dynamics) with NSW=0: no MD steps will be performed.",
                )
            )

        # Check SMASS without IBRION=0 or IBRION=3
        smass = parser.get_parameter("SMASS")
        if smass:
            if not ibrion or not isinstance(ibrion.value, int) or ibrion.value not in (0, 3):
                diagnostics.append(
                    self._parameter_info(
                        smass,
                        "SMASS is typically used with IBRION=0 (MD) or IBRION=3 (damped MD).",
                    )
                )

        return diagnostics

    def _check_workspace_consistency(
        self,
        parser: INCARParser,
        document_uri: str,
        workspace_documents: Optional[Dict[str, str]],
    ) -> List[Diagnostic]:
        """Check INCAR against POSCAR, KPOINTS, and POTCAR in the same calculation."""
        diagnostics: List[Diagnostic] = []
        poscar = self._parse_neighbor_poscar(document_uri, workspace_documents)
        kpoints = self._parse_neighbor_kpoints(document_uri, workspace_documents)
        potcar = self._parse_neighbor_potcar(document_uri, workspace_documents)

        poscar_data = poscar.parse() if poscar else None
        kpoints_data = kpoints.parse() if kpoints else None
        potcar_data = potcar.parse() if potcar else None

        if poscar_data:
            total_atoms = sum(poscar_data.atom_counts)
            species_count = len(poscar_data.atom_counts)

            magmom = parser.get_parameter("MAGMOM")
            if magmom:
                magmom_count = self._expanded_array_length(magmom.value)
                if magmom_count not in (0, total_atoms):
                    diagnostics.append(
                        self._parameter_warning(
                            magmom,
                            f"MAGMOM has {magmom_count} entries but POSCAR contains {total_atoms} atoms.",
                        )
                    )

            for name in ("LDAUL", "LDAUU", "LDAUJ"):
                param = parser.get_parameter(name)
                if param:
                    count = self._expanded_array_length(param.value)
                    if count not in (0, species_count):
                        diagnostics.append(
                            self._parameter_warning(
                                param,
                                f"{name} has {count} entries but POSCAR defines {species_count} species.",
                            )
                        )

        if parser.get_parameter("KSPACING") and kpoints_data:
            diagnostics.append(
                self._parameter_warning(
                    parser.get_parameter("KSPACING"),
                    "KSPACING is set while a KPOINTS file exists. VASP uses one k-point generation path; remove one source of k-point settings.",
                )
            )

        if potcar_data and poscar_data:
            potcar_species = [entry.element for entry in potcar_data.entries]
            if (
                poscar_data.atom_types
                and poscar_data.atom_types != potcar_species[: len(poscar_data.atom_types)]
            ):
                first_param = next(iter(parser.get_all_parameters().values()), None)
                diagnostics.append(
                    self._workspace_warning(
                        first_param,
                        "POSCAR species order "
                        f"{', '.join(poscar_data.atom_types)} differs from POTCAR order {', '.join(potcar_species)}.",
                    )
                )

            # Check for POTCAR functional mixing (e.g., PBE + LDA)
            if len(potcar_data.entries) > 1:
                functionals = set()
                for entry in potcar_data.entries:
                    title = entry.title.upper()
                    for prefix in ("PBE", "LDA", "PW91", "LDA_K"):
                        if prefix in title:
                            functionals.add(prefix)
                            break
                if len(functionals) > 1:
                    first_param = next(iter(parser.get_all_parameters().values()), None)
                    diagnostics.append(
                        self._workspace_warning(
                            first_param,
                            f"POTCAR mixes functionals: {', '.join(sorted(functionals))}. "
                            "Inconsistent pseudopotentials may produce unreliable results.",
                        )
                    )

        encut = parser.get_parameter("ENCUT")
        if encut and isinstance(encut.value, (int, float)) and potcar_data:
            enmax_values = [entry.enmax for entry in potcar_data.entries if entry.enmax is not None]
            if enmax_values:
                max_enmax = max(enmax_values)
                if float(encut.value) < max_enmax:
                    # ENCUT below the largest POTCAR ENMAX -> vasp.encut.below_enmax (#55).
                    # Each pseudopotential is shipped with a recommended cutoff (ENMAX); running
                    # below it degrades the basis set the pseudopotentials were balanced for.
                    # Upstream behavior, not a hard runtime failure, so the rule ships at warning
                    # severity with the rule's stable code and metadata.
                    diagnostics.append(self._encut_below_enmax_diagnostic(encut, max_enmax))
                elif float(encut.value) < 1.3 * max_enmax:
                    recommended = round(1.3 * max_enmax)
                    diagnostics.append(
                        self._parameter_info(
                            encut,
                            f"For production calculations, ENCUT={recommended:g} eV (1.3 x ENMAX) is recommended.",
                        )
                    )

        icharg = parser.get_parameter("ICHARG")
        if icharg and icharg.value in (1, 11):
            chgcar_content = self._read_neighbor(document_uri, "CHGCAR", workspace_documents)
            if chgcar_content is None:
                diagnostics.append(
                    self._parameter_info(
                        icharg,
                        f"ICHARG={icharg.value} usually requires a precomputed CHGCAR in the calculation directory.",
                    )
                )

        if kpoints_data and kpoints_data.mode == KPOINTSMode.LINE_MODE:
            icharg = parser.get_parameter("ICHARG")
            if not icharg or icharg.value not in (11, 12):
                anchor = icharg or next(iter(parser.get_all_parameters().values()), None)
                diagnostics.append(
                    self._workspace_info(
                        anchor,
                        "Line-mode KPOINTS is normally used for band structures with ICHARG=11 or 12 after a charge-density calculation.",
                    )
                )

        diagnostics.extend(
            self._check_parallel_restart_preflight(
                parser,
                document_uri,
                workspace_documents,
                kpoints,
                kpoints_data,
                poscar,
                poscar_data,
            )
        )

        return diagnostics

    def _check_parallel_restart_preflight(
        self,
        parser: INCARParser,
        document_uri: str,
        workspace_documents: Optional[Dict[str, str]],
        kpoints: Optional[KPOINTSParser],
        kpoints_data,
        poscar: Optional[POSCARParser],
        poscar_data,
    ) -> List[Diagnostic]:
        """Check high-value runtime-risk settings before a VASP run."""
        diagnostics: List[Diagnostic] = []

        lhfcalc = parser.get_parameter("LHFCALC")
        algo = parser.get_parameter("ALGO")
        if lhfcalc and lhfcalc.value is True and algo and str(algo.value).upper() == "VERYFAST":
            diagnostics.append(
                self._parameter_warning(
                    algo,
                    "LHFCALC=.TRUE. with ALGO=VeryFast is a runtime-risk combination; "
                    "hybrid calculations should use ALGO=Normal or a safer preconverged setup.",
                )
            )

        diagnostics.extend(self._check_nkred_divisibility(parser, kpoints_data))
        diagnostics.extend(self._check_parallel_layout(parser, document_uri, workspace_documents))
        diagnostics.extend(self._check_restart_files(parser, document_uri, workspace_documents))
        diagnostics.extend(self._check_dimer_context(parser, poscar, poscar_data))

        return diagnostics

    def _check_nkred_divisibility(self, parser: INCARParser, kpoints_data) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        if not kpoints_data or not kpoints_data.grid:
            return diagnostics

        checks: List[tuple[str, int, Any]] = []
        nkred = parser.get_parameter("NKRED")
        if nkred:
            checks.extend((("NKRED", axis, nkred) for axis in range(3)))
        for name, axis in (("NKREDX", 0), ("NKREDY", 1), ("NKREDZ", 2)):
            param = parser.get_parameter(name)
            if param:
                checks.append((name, axis, param))

        for name, axis, param in checks:
            value = self._integer_param_value(param)
            if value is None or value <= 0:
                continue
            mesh = kpoints_data.grid[axis]
            if mesh % value != 0:
                diagnostics.append(
                    self._parameter_warning(
                        param,
                        f"{name}={value} does not divide KPOINTS mesh dimension {mesh}.",
                    )
                )
        return diagnostics

    def _check_parallel_layout(
        self,
        parser: INCARParser,
        document_uri: str,
        workspace_documents: Optional[Dict[str, str]],
    ) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        config = self._read_plan24_config(document_uri, workspace_documents)
        mpi_ranks = config.get("mpi_ranks")
        if not isinstance(mpi_ranks, int) or mpi_ranks <= 0:
            return diagnostics

        kpar = parser.get_parameter("KPAR")
        kpar_value = self._integer_param_value(kpar) if kpar else None
        ranks_per_kpar = mpi_ranks
        if kpar and kpar_value and kpar_value > 0:
            if mpi_ranks % kpar_value != 0:
                diagnostics.append(
                    self._parameter_warning(
                        kpar,
                        f"KPAR={kpar_value} does not divide mpi_ranks={mpi_ranks}.",
                    )
                )
            else:
                ranks_per_kpar = mpi_ranks // kpar_value

        ncore = parser.get_parameter("NCORE")
        ncore_value = self._integer_param_value(ncore) if ncore else None
        if ncore and ncore_value and ncore_value > 0 and ranks_per_kpar % ncore_value != 0:
            diagnostics.append(
                self._parameter_warning(
                    ncore,
                    f"NCORE={ncore_value} does not divide ranks per KPAR group {ranks_per_kpar}.",
                )
            )

        return diagnostics

    def _check_restart_files(
        self,
        parser: INCARParser,
        document_uri: str,
        workspace_documents: Optional[Dict[str, str]],
    ) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        istart = parser.get_parameter("ISTART")
        if istart and istart.value in (1, 2):
            wavecar_content = self._read_neighbor(document_uri, "WAVECAR", workspace_documents)
            if wavecar_content is None:
                diagnostics.append(
                    self._parameter_info(
                        istart,
                        f"ISTART={istart.value} usually requires WAVECAR in the calculation directory.",
                    )
                )
        return diagnostics

    def _check_dimer_context(
        self, parser: INCARParser, poscar: Optional[POSCARParser], poscar_data
    ) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        ibrion = parser.get_parameter("IBRION")
        if not ibrion or ibrion.value != 44 or not poscar or not poscar_data:
            return diagnostics
        if not self._poscar_has_dimer_vector(poscar, poscar_data):
            diagnostics.append(
                self._parameter_warning(
                    ibrion,
                    "IBRION=44 dimer mode requires a dimer direction vector block after POSCAR coordinates.",
                )
            )
        return diagnostics

    def _poscar_has_dimer_vector(self, poscar: POSCARParser, poscar_data) -> bool:
        coordinate_end = poscar_data.coordinate_start_line + len(poscar_data.coordinates)
        for line in poscar.lines[coordinate_end:]:
            parts = line.strip().split()
            if len(parts) < 3:
                continue
            try:
                [float(part) for part in parts[:3]]
            except ValueError:
                continue
            return True
        return False

    def _read_plan24_config(
        self,
        document_uri: str,
        workspace_documents: Optional[Dict[str, str]],
    ) -> Dict[str, Any]:
        content = self._read_neighbor(document_uri, "vasp-lsp.json", workspace_documents)
        if content is None:
            return {}
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _integer_param_value(self, param) -> Optional[int]:
        value = getattr(param, "value", None)
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return None

    # ------------------------------------------------------------------
    # Schema-aware static checks (#20, #21)
    # ------------------------------------------------------------------

    def _check_calculation_modes(self, parser: INCARParser) -> List[Diagnostic]:
        """Detect the active VASP calculation mode and warn about missing required tags.

        Issue #21: validate required sections.
        """
        diagnostics: List[Diagnostic] = []
        all_params = parser.get_all_parameters()

        for mode in CALCULATION_MODES:
            if not self._is_mode_active(mode, all_params):
                continue
            # Mode is active — check for missing required tags
            missing = [tag for tag in mode.required_tags if tag not in all_params]
            if missing:
                anchor = next(iter(all_params.values()), None)
                tag_list = ", ".join(missing)
                diagnostics.append(
                    self._parameter_diagnostic(
                        anchor,
                        f"Detected {mode.name} mode ({mode.description}). "
                        f"Missing recommended tags: {tag_list}",
                        DiagnosticSeverity.Information,
                    )
                )

            # Also warn about recommended tags that are not set
            missing_recommended = [tag for tag in mode.recommended_tags if tag not in all_params]
            if missing_recommended:
                anchor = next(iter(all_params.values()), None)
                tag_list = ", ".join(missing_recommended)
                diagnostics.append(
                    self._parameter_diagnostic(
                        anchor,
                        f"For {mode.name} mode, consider setting: {tag_list}",
                        (
                            DiagnosticSeverity.Hint
                            if hasattr(DiagnosticSeverity, "Hint")
                            else DiagnosticSeverity.Information
                        ),
                    )
                )
            break  # Only report the first matching mode

        return diagnostics

    def _is_mode_active(self, mode: CalculationMode, all_params: dict) -> bool:
        """Return True if the given calculation mode is likely active."""
        for tag_name, expected_values in mode.detector_tags.items():
            if tag_name not in all_params:
                return False
            if expected_values is not None:
                val = all_params[tag_name].value
                # Handle boolean True
                if isinstance(expected_values, list) and True in expected_values:
                    if val is True:
                        continue
                if isinstance(expected_values, list):
                    try:
                        if isinstance(val, bool):
                            return False
                        if int(val) not in [int(v) for v in expected_values if v is not True]:
                            return False
                    except (ValueError, TypeError):
                        return False
        # At least one detector tag must be present
        return bool(mode.detector_tags)

    def _check_schema_conflicts(self, parser: INCARParser) -> List[Diagnostic]:
        """Check for tag conflicts declared in schema metadata.

        Issue #20: schema-aware static checks.
        """
        diagnostics: List[Diagnostic] = []
        all_params = parser.get_all_parameters()

        for tag_name, param in all_params.items():
            tag = get_tag_info(tag_name)
            if tag is None or not tag.conflicts_with:
                continue
            for conflict_name in tag.conflicts_with:
                conflict_param = all_params.get(conflict_name)
                if conflict_param is None:
                    continue
                # The NCORE/NPAR pair is owned by vasp.parallel.ncore_npar_conflict
                # (#56) in ``_check_incar_dependencies`` so the diagnostic carries
                # the stable rule id and metadata; skip the generic duplicate here.
                if {tag_name, conflict_name} == {"NCORE", "NPAR"}:
                    continue
                # Use the *later* parameter as the diagnostic anchor
                if param.line_number > conflict_param.line_number:
                    anchor = param
                else:
                    anchor = conflict_param
                diagnostics.append(
                    Diagnostic(
                        range=Range(
                            start=Position(line=anchor.line_number - 1, character=0),
                            end=Position(
                                line=anchor.line_number - 1,
                                character=len(anchor.raw_line),
                            ),
                        ),
                        message=f"{tag_name} conflicts with {conflict_name}. Prefer NCORE.",
                        severity=DiagnosticSeverity.Warning,
                        source="vasp-lsp",
                    )
                )
        return diagnostics

    def _parameter_warning(self, param, message: str) -> Diagnostic:
        return self._parameter_diagnostic(param, message, DiagnosticSeverity.Warning)

    def _parameter_info(self, param, message: str) -> Diagnostic:
        return self._parameter_diagnostic(param, message, DiagnosticSeverity.Information)

    def _parameter_diagnostic(self, param, message: str, severity) -> Diagnostic:
        return Diagnostic(
            range=Range(
                start=Position(line=param.line_number - 1, character=0),
                end=Position(line=param.line_number - 1, character=len(param.raw_line)),
            ),
            message=message,
            severity=severity,
            source="vasp-lsp",
        )

    def _workspace_warning(self, param, message: str) -> Diagnostic:
        return self._workspace_diagnostic(param, message, DiagnosticSeverity.Warning)

    def _workspace_info(self, param, message: str) -> Diagnostic:
        return self._workspace_diagnostic(param, message, DiagnosticSeverity.Information)

    def _workspace_diagnostic(self, param, message: str, severity) -> Diagnostic:
        if param:
            return self._parameter_diagnostic(param, message, severity)
        return Diagnostic(
            range=Range(start=Position(line=0, character=0), end=Position(line=0, character=1)),
            message=message,
            severity=severity,
            source="vasp-lsp",
        )

    def _expanded_array_length(self, value) -> int:
        if value is None:
            return 0
        values = value if isinstance(value, list) else [value]
        count = 0
        for item in values:
            if isinstance(item, str):
                match = re.fullmatch(r"(\d+)\*[-+]?\d+(?:\.\d+)?", item.strip())
                if match:
                    count += int(match.group(1))
                    continue
            count += 1
        return count

    def _parse_neighbor_poscar(
        self, document_uri: str, workspace_documents: Optional[Dict[str, str]]
    ) -> Optional[POSCARParser]:
        content = self._read_neighbor(document_uri, "POSCAR", workspace_documents)
        if content is None:
            content = self._read_neighbor(document_uri, "CONTCAR", workspace_documents)
        return POSCARParser(content) if content is not None else None

    def _parse_neighbor_kpoints(
        self, document_uri: str, workspace_documents: Optional[Dict[str, str]]
    ) -> Optional[KPOINTSParser]:
        content = self._read_neighbor(document_uri, "KPOINTS", workspace_documents)
        return KPOINTSParser(content) if content is not None else None

    def _parse_neighbor_potcar(
        self, document_uri: str, workspace_documents: Optional[Dict[str, str]]
    ) -> Optional[POTCARParser]:
        content = self._read_neighbor(document_uri, "POTCAR", workspace_documents)
        return POTCARParser(content) if content is not None else None

    def _read_neighbor(
        self,
        document_uri: str,
        filename: str,
        workspace_documents: Optional[Dict[str, str]],
    ) -> Optional[str]:
        if workspace_documents:
            base_dir = os.path.dirname(self._uri_to_path(document_uri) or "")
            for uri, content in workspace_documents.items():
                path = self._uri_to_path(uri)
                if not path:
                    continue
                if (
                    os.path.dirname(path) == base_dir
                    and os.path.basename(path).upper() == filename.upper()
                ):
                    return content

        path = self._uri_to_path(document_uri)
        if not path:
            return None
        neighbor = os.path.join(os.path.dirname(path), filename)
        if not os.path.exists(neighbor):
            return None
        try:
            with open(neighbor, encoding="utf-8", errors="ignore") as handle:
                return handle.read()
        except OSError:
            return None

    def _uri_to_path(self, uri: str) -> Optional[str]:
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            return None
        return unquote(parsed.path)

    def _get_poscar_diagnostics(self, content: str) -> List[Diagnostic]:
        """Get diagnostics for POSCAR files."""
        diagnostics = []
        parser = POSCARParser(content)
        result = parser.parse()

        # Report parse errors
        for error in parser.get_errors():
            severity = (
                DiagnosticSeverity.Error
                if error["severity"] == "error"
                else DiagnosticSeverity.Warning
            )
            diagnostics.append(
                Diagnostic(
                    range=Range(
                        start=Position(line=error["line"] - 1, character=error.get("column", 0)),
                        end=Position(line=error["line"] - 1, character=error.get("column", 0) + 1),
                    ),
                    message=error["message"],
                    severity=severity,
                    source="vasp-lsp",
                )
            )

        # Additional validation if parsing succeeded
        if result:
            diagnostics.extend(self._check_poscar_structure(result))

            # Check for negative scale factor (use exact line from parser)
            if result.scale_factor < 0:
                diagnostics.append(
                    Diagnostic(
                        range=Range(
                            start=Position(line=result.scale_factor_line, character=0),
                            end=Position(
                                line=result.scale_factor_line,
                                character=len(str(result.scale_factor)),
                            ),
                        ),
                        message="Negative scale factor detected. This inverts the lattice.",
                        severity=DiagnosticSeverity.Warning,
                        source="vasp-lsp",
                    )
                )

            # Check for zero atom counts (use exact line from parser)
            total_atoms = sum(result.atom_counts)
            if total_atoms == 0:
                diagnostics.append(
                    Diagnostic(
                        range=Range(
                            start=Position(line=result.atom_counts_line, character=0),
                            end=Position(
                                line=result.atom_counts_line,
                                character=len(" ".join(str(c) for c in result.atom_counts)),
                            ),
                        ),
                        message="No atoms specified in POSCAR.",
                        severity=DiagnosticSeverity.Error,
                        source="vasp-lsp",
                    )
                )

            # Check coordinate ranges for direct coordinates (use exact lines)
            if result.coordinate_type == "Direct":
                for i, coord in enumerate(result.coordinates):
                    for j, val in enumerate(coord):
                        if val < -0.5 or val > 1.5:
                            line_num = max(result.coordinate_start_line - 1 + i, 0)
                            coord_str = " ".join(f"{v:.6g}" for v in coord)
                            diagnostics.append(
                                Diagnostic(
                                    range=Range(
                                        start=Position(line=line_num, character=0),
                                        end=Position(line=line_num, character=len(coord_str)),
                                    ),
                                    message=f"Direct coordinate {val:.3f} is outside typical range [0, 1].",
                                    severity=DiagnosticSeverity.Information,
                                    source="vasp-lsp",
                                )
                            )
                            break

            # Check for extreme scale factor magnitude
            diagnostics.extend(self._check_scale_factor_magnitude(result))

            # Check lattice vector angles for nearly degenerate cell
            diagnostics.extend(self._check_lattice_angles(result))

            # Check coordinate count matches atom counts
            diagnostics.extend(self._check_coordinate_count(result))

            # Check for duplicate atom positions
            diagnostics.extend(self._check_duplicate_positions(result))

            # Check for very close atoms (potential overlap)
            if result.coordinate_type == "Cartesian":
                diagnostics.extend(self._check_close_atoms_cartesian(result))
            else:
                diagnostics.extend(self._check_close_atoms_direct(result))

        return diagnostics

    def _check_poscar_structure(self, result) -> List[Diagnostic]:
        diagnostics: List[Diagnostic] = []
        for index, vector in enumerate(result.lattice_vectors):
            length_sq = sum(component * component for component in vector)
            if length_sq == 0:
                diagnostics.append(
                    Diagnostic(
                        range=Range(
                            start=Position(line=2 + index, character=0),
                            end=Position(line=2 + index, character=40),
                        ),
                        message="Lattice vector length is zero.",
                        severity=DiagnosticSeverity.Error,
                        source="vasp-lsp",
                    )
                )

        volume = self._cell_volume(result.lattice_vectors) * (result.scale_factor**3)
        if abs(volume) < 1e-12:
            diagnostics.append(
                Diagnostic(
                    range=Range(
                        start=Position(line=2, character=0), end=Position(line=4, character=40)
                    ),
                    message="POSCAR cell volume is zero; lattice vectors are linearly dependent.",
                    severity=DiagnosticSeverity.Error,
                    source="vasp-lsp",
                )
            )

        invalid_elements = [
            element for element in result.atom_types if not re.fullmatch(r"[A-Z][a-z]?", element)
        ]
        if invalid_elements and not all(element.startswith("Type") for element in invalid_elements):
            diagnostics.append(
                Diagnostic(
                    range=Range(
                        start=Position(line=5, character=0), end=Position(line=5, character=80)
                    ),
                    message=f"Invalid element symbols in POSCAR: {', '.join(invalid_elements)}.",
                    severity=DiagnosticSeverity.Warning,
                    source="vasp-lsp",
                )
            )

        return diagnostics

    def _cell_volume(self, lattice_vectors: List[List[float]]) -> float:
        a, b, c = lattice_vectors
        return (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        )

    def _check_scale_factor_magnitude(self, result) -> List[Diagnostic]:
        """Warn if scale factor magnitude is too small or too large."""
        diagnostics: List[Diagnostic] = []
        abs_scale = abs(result.scale_factor)
        if abs_scale < 0.01 or abs_scale > 100:
            diagnostics.append(
                Diagnostic(
                    range=Range(
                        start=Position(line=1, character=0), end=Position(line=1, character=20)
                    ),
                    message=f"Scale factor {result.scale_factor:g} has extreme magnitude "
                    f"(|scale| = {abs_scale:g}). Consider using 1.0.",
                    severity=DiagnosticSeverity.Warning,
                    source="vasp-lsp",
                )
            )
        return diagnostics

    def _check_lattice_angles(self, result) -> List[Diagnostic]:
        """Warn if any angle between lattice vectors is < 10 or > 170 degrees."""
        diagnostics: List[Diagnostic] = []
        vecs = result.lattice_vectors
        pairs = [(0, 1, "a", "b"), (0, 2, "a", "c"), (1, 2, "b", "c")]
        for i, j, name_i, name_j in pairs:
            vi = vecs[i]
            vj = vecs[j]
            len_i = math.sqrt(sum(c * c for c in vi))
            len_j = math.sqrt(sum(c * c for c in vj))
            if len_i < 1e-12 or len_j < 1e-12:
                continue
            dot = sum(a * b for a, b in zip(vi, vj))
            cos_angle = max(-1.0, min(1.0, dot / (len_i * len_j)))
            angle_deg = math.degrees(math.acos(cos_angle))
            if angle_deg < 10 or angle_deg > 170:
                diagnostics.append(
                    Diagnostic(
                        range=Range(
                            start=Position(line=2 + i, character=0),
                            end=Position(line=2 + j, character=40),
                        ),
                        message=f"Angle between lattice vectors {name_i} and {name_j} is "
                        f"{angle_deg:.1f} degrees, indicating a nearly degenerate cell.",
                        severity=DiagnosticSeverity.Warning,
                        source="vasp-lsp",
                    )
                )
        return diagnostics

    def _check_coordinate_count(self, result) -> List[Diagnostic]:
        """Error if number of coordinate rows does not match sum of atom_counts."""
        diagnostics: List[Diagnostic] = []
        expected = sum(result.atom_counts)
        actual = len(result.coordinates)
        if actual != expected:
            diagnostics.append(
                Diagnostic(
                    range=Range(
                        start=Position(line=max(result.coordinate_start_line - 1, 0), character=0),
                        end=Position(
                            line=max(
                                result.coordinate_start_line - 1 + max(actual, expected) - 1, 0
                            ),
                            character=40,
                        ),
                    ),
                    message=f"Expected {expected} coordinate rows but found {actual}.",
                    severity=DiagnosticSeverity.Error,
                    source="vasp-lsp",
                )
            )
        return diagnostics

    def _check_duplicate_positions(self, result) -> List[Diagnostic]:
        """Warn when two atoms have identical coordinates (within tolerance 1e-6)."""
        diagnostics: List[Diagnostic] = []
        tolerance = 1e-6
        seen: List[int] = []
        for i, coord_i in enumerate(result.coordinates):
            if i in seen:
                continue
            for j in range(i + 1, len(result.coordinates)):
                if j in seen:
                    continue
                dist_sq = sum((a - b) ** 2 for a, b in zip(coord_i, result.coordinates[j]))
                if dist_sq < tolerance * tolerance:
                    line_j = max(result.coordinate_start_line - 1 + j, 0)
                    diagnostics.append(
                        Diagnostic(
                            range=Range(
                                start=Position(line=line_j, character=0),
                                end=Position(line=line_j, character=40),
                            ),
                            message=f"Atoms {i + 1} and {j + 1} have identical coordinates.",
                            severity=DiagnosticSeverity.Warning,
                            source="vasp-lsp",
                        )
                    )
                    seen.append(j)
                    break
        return diagnostics

    def _check_close_atoms_cartesian(self, result) -> List[Diagnostic]:
        """Warn if any two Cartesian atoms are closer than 0.5 Angstrom."""
        diagnostics: List[Diagnostic] = []
        min_dist = 0.5
        coords = result.coordinates
        for i in range(len(coords)):
            for j in range(i + 1, len(coords)):
                diff = [coords[i][k] - coords[j][k] for k in range(3)]
                dist = math.sqrt(sum(d * d for d in diff))
                if 0 < dist < min_dist:
                    line_j = max(result.coordinate_start_line - 1 + j, 0)
                    diagnostics.append(
                        Diagnostic(
                            range=Range(
                                start=Position(line=line_j, character=0),
                                end=Position(line=line_j, character=40),
                            ),
                            message=f"Atoms {i + 1} and {j + 1} are {dist:.3f} Angstrom apart "
                            f"(below minimum {min_dist} Angstrom).",
                            severity=DiagnosticSeverity.Warning,
                            source="vasp-lsp",
                        )
                    )
        return diagnostics

    def _check_close_atoms_direct(self, result) -> List[Diagnostic]:
        """Warn if any two Direct atoms are closer than 0.5 Angstrom."""
        diagnostics: List[Diagnostic] = []
        min_dist = 0.5
        coords = result.coordinates
        scale = result.scale_factor
        vecs = result.lattice_vectors
        for i in range(len(coords)):
            for j in range(i + 1, len(coords)):
                diff_frac = [coords[i][k] - coords[j][k] for k in range(3)]
                diff_cart = [
                    scale * sum(vecs[r][k] * diff_frac[r] for r in range(3)) for k in range(3)
                ]
                dist = math.sqrt(sum(d * d for d in diff_cart))
                if 0 < dist < min_dist:
                    line_j = max(result.coordinate_start_line - 1 + j, 0)
                    diagnostics.append(
                        Diagnostic(
                            range=Range(
                                start=Position(line=line_j, character=0),
                                end=Position(line=line_j, character=40),
                            ),
                            message=f"Atoms {i + 1} and {j + 1} are {dist:.3f} Angstrom apart "
                            f"(below minimum {min_dist} Angstrom).",
                            severity=DiagnosticSeverity.Warning,
                            source="vasp-lsp",
                        )
                    )
        return diagnostics

    def _get_kpoints_diagnostics(self, content: str) -> List[Diagnostic]:
        """Get diagnostics for KPOINTS files."""
        from ..parsers.kpoints_parser import KPOINTSMode, KPOINTSParser

        diagnostics: List[Diagnostic] = []
        parser = KPOINTSParser(content)
        result = parser.parse()
        lines = content.split("\n")

        # Report parse errors
        for error in parser.get_errors():
            severity = (
                DiagnosticSeverity.Error
                if error["severity"] == "error"
                else DiagnosticSeverity.Warning
            )
            diagnostics.append(
                Diagnostic(
                    range=Range(
                        start=Position(line=error["line"] - 1, character=error.get("column", 0)),
                        end=Position(line=error["line"] - 1, character=error.get("column", 0) + 1),
                    ),
                    message=error["message"],
                    severity=severity,
                    source="vasp-lsp",
                )
            )

        if result is None:
            return diagnostics

        # Grid-based checks (automatic, gamma/monkhorst modes)
        if result.grid:
            diagnostics.extend(self._check_kpoints_grid(result, lines))

        # Gamma vs Monkhorst-Pack hint
        if result.mode == KPOINTSMode.GAMMA_MONKHORST:
            diagnostics.extend(self._check_kpoints_centering(result, lines))

        # Explicit k-point checks (weights, coordinates)
        if result.mode == KPOINTSMode.EXPLICIT:
            diagnostics.extend(self._check_kpoints_explicit(result, lines))

        # Line-mode density check
        if result.mode == KPOINTSMode.LINE_MODE:
            diagnostics.extend(self._check_kpoints_line_mode(result, lines))

        return diagnostics

    def _check_kpoints_grid(self, result, lines: List[str]) -> List[Diagnostic]:
        """Check k-point grid values for sparsity, density, and validity."""
        diagnostics: List[Diagnostic] = []

        # Use exact grid line from parser when available
        grid_line = result.grid_line_idx if result.grid_line_idx is not None else 2
        grid_text = lines[grid_line].strip() if grid_line < len(lines) else ""
        grid_end_char = len(grid_text)

        # Check for zero or negative grid values
        for grid_val in result.grid:
            if grid_val <= 0:
                diagnostics.append(
                    Diagnostic(
                        range=Range(
                            start=Position(line=grid_line, character=0),
                            end=Position(line=grid_line, character=grid_end_char),
                        ),
                        message=f"K-point grid value {grid_val} is not positive.",
                        severity=DiagnosticSeverity.Error,
                        source="vasp-lsp",
                    )
                )
                break

        # Check for very sparse grids
        if all(g < 2 for g in result.grid):
            diagnostics.append(
                Diagnostic(
                    range=Range(
                        start=Position(line=grid_line, character=0),
                        end=Position(line=grid_line, character=grid_end_char),
                    ),
                    message="K-point grid is very sparse (all values < 2).",
                    severity=DiagnosticSeverity.Warning,
                    source="vasp-lsp",
                )
            )

        # Check for very dense grids
        if all(g > 50 for g in result.grid):
            grid_str = " ".join(str(g) for g in result.grid)
            diagnostics.append(
                Diagnostic(
                    range=Range(
                        start=Position(line=grid_line, character=0),
                        end=Position(line=grid_line, character=grid_end_char),
                    ),
                    message=(
                        f"K-point grid {grid_str} is very dense (all values > 50). "
                        "Computationally expensive; may not converge faster than a moderate grid."
                    ),
                    severity=DiagnosticSeverity.Warning,
                    source="vasp-lsp",
                )
            )

        # Check explicit k-point weights sum
        if result.weights:
            total_weight = sum(result.weights)
            if abs(total_weight - 1.0) > 0.01 and total_weight > 0:
                diagnostics.append(
                    Diagnostic(
                        range=Range(
                            start=Position(line=3, character=0),
                            end=Position(line=3, character=30),
                        ),
                        message=f"K-point weights sum to {total_weight:.3f} (expected ~1.0).",
                        severity=DiagnosticSeverity.Information,
                        source="vasp-lsp",
                    )
                )

        return diagnostics

    def _check_kpoints_centering(self, result, lines: List[str]) -> List[Diagnostic]:
        """Provide a hint about Gamma vs Monkhorst-Pack centering."""
        diagnostics: List[Diagnostic] = []

        # Line 3 (0-indexed) contains the generation type for Gamma/Monkhorst mode
        if len(lines) > 2:
            line3 = lines[2].strip().lower()
            if line3.startswith("g"):
                centering = "Gamma-centered"
            elif line3.startswith("m"):
                centering = "Monkhorst-Pack"
            else:
                return diagnostics

            grid_str = "x".join(str(g) for g in (result.grid or []))
            diagnostics.append(
                Diagnostic(
                    range=Range(
                        start=Position(line=2, character=0),
                        end=Position(line=2, character=30),
                    ),
                    message=(
                        f"Using {centering} mesh with grid {grid_str}. "
                        "Gamma-centered includes the Gamma point; "
                        "Monkhorst-Pack shifts the mesh off Gamma."
                    ),
                    severity=DiagnosticSeverity.Information,
                    source="vasp-lsp",
                )
            )

        return diagnostics

    def _check_kpoints_explicit(self, result, lines: List[str]) -> List[Diagnostic]:
        """Check explicit k-points for zero weights and unreasonable coordinates."""
        diagnostics: List[Diagnostic] = []

        if not result.weights or not result.kpoints:
            return diagnostics

        # Use exact start line from parser when available
        kpt_start = (
            result.kpoints_start_line_idx if result.kpoints_start_line_idx is not None else 3
        )

        # Check for zero-weight k-points
        zero_weight_indices = [i for i, w in enumerate(result.weights) if w == 0.0]
        if zero_weight_indices:
            first_idx = zero_weight_indices[0]
            kpoint_line = kpt_start + first_idx
            kpt_text = lines[kpoint_line].strip() if kpoint_line < len(lines) else ""
            diagnostics.append(
                Diagnostic(
                    range=Range(
                        start=Position(line=kpoint_line, character=0),
                        end=Position(line=kpoint_line, character=len(kpt_text)),
                    ),
                    message=(
                        f"K-point {first_idx + 1} has weight 0.0. "
                        "Zero-weight k-points are excluded from integration."
                    ),
                    severity=DiagnosticSeverity.Warning,
                    source="vasp-lsp",
                )
            )

        # Check for unreasonable k-point coordinates (outside [-1, 1] for reciprocal)
        for i, kpoint in enumerate(result.kpoints):
            for coord in kpoint:
                if abs(coord) > 1.0:
                    kpoint_line = kpt_start + i
                    coord_str = " ".join(f"{c:.4f}" for c in kpoint)
                    diagnostics.append(
                        Diagnostic(
                            range=Range(
                                start=Position(line=kpoint_line, character=0),
                                end=Position(line=kpoint_line, character=len(coord_str)),
                            ),
                            message=(
                                f"K-point coordinates ({coord_str}) are outside the "
                                "typical reciprocal range [-1, 1]. "
                                "Verify coordinates are in fractional reciprocal space."
                            ),
                            severity=DiagnosticSeverity.Error,
                            source="vasp-lsp",
                        )
                    )
                    break  # One diagnostic per k-point line is enough

        # Check weights sum (also applies to explicit mode)
        total_weight = sum(result.weights)
        if abs(total_weight - 1.0) > 0.01 and total_weight > 0:
            diagnostics.append(
                Diagnostic(
                    range=Range(
                        start=Position(line=3, character=0),
                        end=Position(line=3, character=30),
                    ),
                    message=f"K-point weights sum to {total_weight:.3f} (expected ~1.0).",
                    severity=DiagnosticSeverity.Information,
                    source="vasp-lsp",
                )
            )

        return diagnostics

    def _check_kpoints_line_mode(self, result, lines: List[str]) -> List[Diagnostic]:
        """Check line-mode k-point density."""
        diagnostics: List[Diagnostic] = []

        if result.line_density is not None and result.line_density < 10:
            diagnostics.append(
                Diagnostic(
                    range=Range(
                        start=Position(line=1, character=0),
                        end=Position(line=1, character=20),
                    ),
                    message=(
                        f"Line-mode density is {result.line_density} (< 10). "
                        "Low point density may miss band structure features."
                    ),
                    severity=DiagnosticSeverity.Information,
                    source="vasp-lsp",
                )
            )

        return diagnostics
