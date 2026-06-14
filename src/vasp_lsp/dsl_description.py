"""VASP DSL description API for coding agents (#29, #30, #31, #26).

This module gives coding agents (Claude Code, OpenCode, Codex, ...) a stable,
deterministic JSON surface for asking the VASP LSP how the domain language is
written, what keywords/sections mean, and how to construct minimal valid
snippets without launching an editor. The output is consumed by the
``vasp-lsp-tool describe|schema|examples|next-tokens`` subcommands and by the
``vasp-lsp-describe``/``vasp-lsp-schema``/``vasp-lsp-examples`` console
scripts.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from .rules import RULES_MANIFEST, all_rules, get_rule
from .schemas.incar_tags import INCAR_TAGS, get_tag_info, search_tags

SOFTWARE = "vasp"
LANGUAGE_ID = "vasp-input"
LANGUAGE_NAME = "VASP Input DSL"

#: Top-level file types covered by the LSP today.
SUPPORTED_FILE_TYPES = (
    {
        "name": "INCAR",
        "description": "Tag = value INI-style input for VASP runtime parameters.",
        "grammar_summary": (
            "Whitespace-separated ``TAG = value`` assignments; lines starting "
            "with ``#`` are comments; tag names are case-insensitive."
        ),
        "top_level_sections": ["(flat tag list)"],
    },
    {
        "name": "POSCAR",
        "description": "Lattice + per-atom site list.",
        "grammar_summary": (
            "Comment line; scale line; three lattice vectors; element names; "
            "per-element counts; ``Direct``/``Cartesian`` mode; per-site rows."
        ),
        "top_level_sections": ["lattice", "atoms"],
    },
    {
        "name": "KPOINTS",
        "description": "K-point mesh or explicit k-point list.",
        "grammar_summary": (
            "Comment line; mode line (Automatic/Gamma/Monkhorst-Pack/Line/Explicit); "
            "grid or k-point rows depending on mode."
        ),
        "top_level_sections": ["mesh", "k-points"],
    },
    {
        "name": "POTCAR",
        "description": "Concatenated pseudopotential datasets.",
        "grammar_summary": (
            "Sequential PAW/US pseudopotential entries with TITEL/ENMAX/ENMIN " "metadata lines."
        ),
        "top_level_sections": ["datasets"],
    },
)

#: Minimal valid INCAR examples for the most common calculation types.
MINIMAL_EXAMPLES: dict[str, dict[str, Any]] = {
    "static": {
        "calculation_type": "static (single-point SCF)",
        "file_type": "INCAR",
        "snippet": (
            "SYSTEM = static-example\n"
            "ENCUT = 520\n"
            "ISMEAR = 0\n"
            "SIGMA = 0.05\n"
            "EDIFF = 1E-6\n"
            "NSW = 0\n"
            "IBRION = -1\n"
        ),
        "notes": (
            "Valid under the VASP-LSP INCAR parser and the rule manifest. "
            "Replace ENCUT with the value recommended by your POTCAR."
        ),
    },
    "relaxation": {
        "calculation_type": "structural relaxation",
        "file_type": "INCAR",
        "snippet": (
            "SYSTEM = relaxation-example\n"
            "ENCUT = 520\n"
            "ISMEAR = 0\n"
            "SIGMA = 0.05\n"
            "EDIFF = 1E-6\n"
            "EDIFFG = -1E-2\n"
            "NSW = 60\n"
            "IBRION = 2\n"
            "ISIF = 2\n"
        ),
        "notes": (
            "Converges both electronic and ionic degrees of freedom. Adjust "
            "ISIF for cell-shape relaxations."
        ),
    },
    "spin_polarized": {
        "calculation_type": "spin-polarized static",
        "file_type": "INCAR",
        "snippet": (
            "SYSTEM = spin-example\n"
            "ENCUT = 520\n"
            "ISMEAR = 0\n"
            "SIGMA = 0.05\n"
            "EDIFF = 1E-6\n"
            "ISPIN = 2\n"
            "MAGMOM = 2 * 1.0\n"
        ),
        "notes": ("Pairs ISPIN=2 with an explicit MAGMOM to satisfy " "vasp.spin.missing_magmom."),
    },
}

#: Suggested next tokens by cursor context. The cursor context is the last
#: meaningful token on the line being edited (or ``""`` for an empty file).
NEXT_TOKENS: dict[str, list[dict[str, str]]] = {
    "": [
        {"token": "SYSTEM", "description": "Human-readable calculation label."},
        {"token": "ENCUT", "description": "Plane-wave cutoff in eV."},
        {"token": "ISMEAR", "description": "Smearing scheme selection."},
        {"token": "ALGO", "description": "Electronic minimisation algorithm."},
    ],
    "ISMEAR": [
        {"token": "= 0", "description": "Gaussian smearing (metals/insulators)."},
        {"token": "= 1", "description": "Methfessel-Paxton first-order smearing."},
        {"token": "= -5", "description": "Tetrahedron method (insulators only)."},
    ],
    "ALGO": [
        {"token": "= Normal", "description": "Robust default SCF algorithm."},
        {"token": "= Fast", "description": "RMM-DIIS optimised for speed."},
        {"token": "= VeryFast", "description": "CG-fast hybrid (not for hybrids)."},
    ],
}


def describe_language() -> dict[str, Any]:
    """Return the deterministic DSL overview payload for ``domain/describeLanguage`` (#29)."""
    payload: dict[str, Any] = {
        "languageId": LANGUAGE_ID,
        "name": LANGUAGE_NAME,
        "software": SOFTWARE,
        "fileExtensions": ", ".join(str(item["name"]) for item in SUPPORTED_FILE_TYPES),
        "overview": (
            "VASP input is split across INCAR (runtime tags), POSCAR "
            "(lattice + sites), KPOINTS (k-point mesh), and POTCAR "
            "(pseudopotentials). The LSP validates each file and "
            "cross-checks INCAR against POSCAR/KPOINTS/POTCAR neighbours."
        ),
        "grammarSummary": (
            "INCAR uses ``TAG = value`` lines with ``#`` comments. POSCAR "
            "uses fixed-position rows for lattice and sites. KPOINTS uses "
            "mode-prefixed sections."
        ),
        "topLevelSections": list(SUPPORTED_FILE_TYPES),
        "commonPatterns": [
            {
                "name": "static SCF",
                "summary": "NSW=0 with IBRION=-1 and a converged ENCUT/EDIFF.",
            },
            {
                "name": "relaxation",
                "summary": "IBRION=2 with NSW and EDIFFG; ISIF selects DOF.",
            },
            {
                "name": "spin-polarized",
                "summary": "ISPIN=2 paired with an explicit MAGMOM.",
            },
        ],
        "examples": [
            {
                "name": name,
                "calculation_type": entry["calculation_type"],
                "snippet": entry["snippet"],
            }
            for name, entry in MINIMAL_EXAMPLES.items()
        ],
        "validationRules": [
            {
                "rule_id": rule["rule_id"],
                "severity": rule["severity"],
                "category": rule["category"],
                "summary": rule["summary"],
                "manual_ref": rule["manual_ref"],
            }
            for rule in all_rules()
        ],
        "references": [
            "https://www.vasp.at/wiki/index.php/INCAR",
            "https://www.vasp.at/wiki/index.php/POSCAR",
            "https://www.vasp.at/wiki/index.php/KPOINTS",
            "https://www.vasp.at/wiki/index.php/POTCAR",
        ],
    }
    return payload


def _tag_to_schema_dict(tag) -> dict[str, Any]:
    """Serialise an INCARTag to a stable agent-facing dict."""
    if is_dataclass(tag):
        data = asdict(tag)  # type: ignore[arg-type]
    else:
        data = dict(tag)
    data["name"] = str(data.get("name", "")).upper()
    return data


def describe_keyword(keyword: str) -> dict[str, Any]:
    """Return deterministic schema metadata for a single INCAR keyword (#30).

    Unknown keywords return a structured ``not_found`` payload with suggested
    neighbours so agents can recover without parsing free text.
    """
    keyword = keyword.strip()
    if not keyword:
        return {
            "operation": "describe_keyword",
            "software": SOFTWARE,
            "keyword": keyword,
            "found": False,
            "reason": "Empty keyword.",
        }
    tag = get_tag_info(keyword)
    if tag is None:
        suggestions = [
            {"name": candidate.name, "description": candidate.description}
            for candidate in search_tags(keyword)[:5]
        ]
        return {
            "operation": "describe_keyword",
            "software": SOFTWARE,
            "keyword": keyword,
            "found": False,
            "reason": f"Unknown INCAR keyword {keyword!r}.",
            "suggestions": suggestions,
        }
    schema = _tag_to_schema_dict(tag)
    schema["manual_ref"] = f"https://www.vasp.at/wiki/index.php/{tag.name}"
    return {
        "operation": "describe_keyword",
        "software": SOFTWARE,
        "keyword": keyword,
        "found": True,
        "schema": schema,
    }


def describe_section(section: str) -> dict[str, Any]:
    """Return deterministic metadata for a top-level VASP section/file type (#30)."""
    name = section.strip().upper()
    matches = [entry for entry in SUPPORTED_FILE_TYPES if entry["name"] == name]
    if not matches:
        return {
            "operation": "describe_section",
            "software": SOFTWARE,
            "section": section,
            "found": False,
            "reason": f"Unknown VASP section/file type {section!r}.",
            "known_sections": [entry["name"] for entry in SUPPORTED_FILE_TYPES],
        }
    entry = matches[0]
    return {
        "operation": "describe_section",
        "software": SOFTWARE,
        "section": entry["name"],
        "found": True,
        "description": entry["description"],
        "grammar_summary": entry["grammar_summary"],
        "top_level_sections": entry["top_level_sections"],
        "keywords": [name for name in INCAR_TAGS if name.isupper()][:50],
    }


def make_minimal_example(calculation_type: str | None = None) -> dict[str, Any]:
    """Return a deterministic minimal INCAR example (#31)."""
    if calculation_type is None:
        calculation_type = "static"
    key = calculation_type.strip().lower().replace("-", "_")
    entry = MINIMAL_EXAMPLES.get(key)
    if entry is None:
        return {
            "operation": "make_minimal_example",
            "software": SOFTWARE,
            "calculation_type": calculation_type,
            "found": False,
            "reason": f"Unknown calculation type {calculation_type!r}.",
            "available_types": sorted(MINIMAL_EXAMPLES),
        }
    return {
        "operation": "make_minimal_example",
        "software": SOFTWARE,
        "calculation_type_key": key,
        "found": True,
        **entry,
    }


def suggest_next_tokens(context: str) -> dict[str, Any]:
    """Return deterministic next-token guidance for a cursor context (#31)."""
    key = context.strip()
    tokens = NEXT_TOKENS.get(key)
    if tokens is None:
        tokens = NEXT_TOKENS[""]
    return {
        "operation": "suggest_next_tokens",
        "software": SOFTWARE,
        "context": key,
        "tokens": list(tokens),
    }


def rule_explain(rule_id: str) -> dict[str, Any]:
    """Return a deterministic explanation for a registered rule id (#26, #36)."""
    rule = get_rule(rule_id)
    if rule is None:
        return {
            "operation": "explain",
            "software": SOFTWARE,
            "rule_id": rule_id,
            "found": False,
            "known_rule_ids": sorted(RULES_MANIFEST),
        }
    return {
        "operation": "explain",
        "software": SOFTWARE,
        "rule_id": rule_id,
        "found": True,
        "rule": rule,
    }


__all__ = [
    "LANGUAGE_ID",
    "LANGUAGE_NAME",
    "SOFTWARE",
    "SUPPORTED_FILE_TYPES",
    "MINIMAL_EXAMPLES",
    "NEXT_TOKENS",
    "describe_keyword",
    "describe_language",
    "describe_section",
    "make_minimal_example",
    "rule_explain",
    "suggest_next_tokens",
]
