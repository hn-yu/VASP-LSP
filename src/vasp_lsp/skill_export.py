"""Export the bundled pluggable skill specification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SKILL_SPEC_JSON = (
    '{"schema":"scientific-lsp-skill/v1","name":"vasp","software":"vasp","display'
    '_name":"VASP","description":"VASP input preflight for INCAR, POSCAR, KPOINTS'
    ', and related generated inputs.","package":{"name":"vasp-lsp","install":"pip'
    ' install vasp-lsp"},"entrypoints":{"server":"vasp-lsp","tool":"vasp-lsp-tool'
    '"},"file_patterns":["INCAR","POSCAR","KPOINTS","POTCAR","CONTCAR","OSZICAR",'
    '"OUTCAR","vasprun.xml"],"operations":["capabilities","check","context","comp'
    'lete","hover","symbols","fix"],"diagnostic_contract":"DiagnosticEnvelope/v1"'
    ',"blocking_policy":{"mode":"warning-only","description":"Use --fail-on-block'
    'ing when generated inputs must be launch-ready."},"source_provenance":[{"kin'
    'd":"official_docs","label":"VASP INCAR wiki","url":"https://www.vasp.at/wiki'
    '/INCAR"}]}'
)

SKILL_SPEC: dict[str, Any] = json.loads(SKILL_SPEC_JSON)

SKILL_MD_LINES = [
    '---',
    'name: vasp',
    (
        'description: "VASP input preflight for INCAR, POSCAR, KPOINTS, and related g'
        'enerated inputs."'
    ),
    '---',
    '',
    '# VASP LSP Skill',
    '',
    (
        'Use this skill when preparing, repairing, or reviewing VASP input files befo'
        're a run. It provides an installable language server and an agent-facing CLI'
        ' that reports machine-readable diagnostics.'
    ),
    '',
    '## Scope',
    '',
    (
        '- Input patterns: INCAR, POSCAR, KPOINTS, POTCAR, CONTCAR, OSZICAR, OUTCAR, '
        'vasprun.xml'
    ),
    '- Server command: `vasp-lsp`',
    '- Agent CLI: `vasp-lsp-tool`',
    '- Diagnostic contract: `DiagnosticEnvelope/v1`',
    '',
    '## Installing the checker',
    '',
    '```bash',
    'pip install vasp-lsp',
    '```',
    '',
    (
        'This installs the `vasp-lsp` language server and the `vasp-lsp-tool` agent C'
        'LI from the `vasp-lsp` Python package.'
    ),
    '',
    '## Useful inspection commands',
    '',
    '```bash',
    'vasp-lsp-tool capabilities',
    'vasp-lsp-tool skill-spec --format json',
    'vasp-lsp-tool skill-export --output ./skill',
    'vasp-lsp-tool check <input-file-or-dir> --format json',
    (
        'vasp-lsp-tool context <input-file-or-dir> --line 0 --character 0 --format js'
        'on'
    ),
    'vasp-lsp-tool hover <input-file-or-dir> --line 0 --character 0 --format json',
    (
        'vasp-lsp-tool complete <input-file-or-dir> --line 0 --character 0 --format j'
        'son'
    ),
    'vasp-lsp-tool symbols <input-file-or-dir> --format json',
    'vasp-lsp-tool fix <input-file-or-dir> --line 0 --character 0 --format json',
    '```',
    '',
    (
        '`fix` is advisory and must be treated as a preview. Do not blindly apply a r'
        "epair without preserving the user's scientific intent."
    ),
    '',
    '## Validation gate',
    '',
    'Before saying generated inputs are ready, run:',
    '',
    '```bash',
    'vasp-lsp-tool check <input-file-or-dir> --format json --fail-on-blocking',
    '```',
    '',
    (
        'Report `commands`, `files_checked`, `tool_available`, `diagnostics`, `blocki'
        'ng_findings`, `readiness`, and `reason`.'
    ),
    '',
    '## Repair rules',
    '',
    '1. Validate first and identify the smallest blocking issue.',
    '2. Fix syntax or schema errors with minimal edits.',
    (
        '3. Preserve scientific settings unless the user explicitly asks to redesign '
        'them.'
    ),
    '4. Re-run the checker after every edit.',
    (
        '5. Separate syntax, schema, semantic, and runtime-log diagnostics in the fin'
        'al report.'
    ),
]
SKILL_MD = "\n".join(SKILL_MD_LINES) + "\n"

REFERENCES_README_LINES = [
    '# VASP LSP Skill References',
    '',
    (
        'This directory is reserved for small examples, rule notes, and templates tha'
        't are safe to ship with the Python package. Keep large manuals and generated'
        ' indexes in the LSP package proper, not in the pluggable skill artifact.'
    ),
]
REFERENCES_README = "\n".join(REFERENCES_README_LINES) + "\n"


def _yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if (
        not text
        or any(ch in text for ch in ":#[]{},&*?")
        or text[0] in "-!@`"
        or text.endswith(" ")
        or "\n" in text
    ):
        return json.dumps(text, ensure_ascii=False)
    return text


def _to_yaml(value: object, indent: int = 0) -> str:
    pad = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.append(_to_yaml(item, indent + 2))
            else:
                lines.append(f"{pad}{key}: {_yaml_scalar(item)}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return f"{pad}[]"
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.append(_to_yaml(item, indent + 2))
            else:
                lines.append(f"{pad}- {_yaml_scalar(item)}")
        return "\n".join(lines)
    return f"{pad}{_yaml_scalar(value)}"


def skill_spec_text(output_format: str = "json") -> str:
    if output_format == "json":
        return json.dumps(SKILL_SPEC, indent=2, sort_keys=True, ensure_ascii=False)
    if output_format == "yaml":
        return _to_yaml(SKILL_SPEC) + "\n"
    raise ValueError(f"unsupported skill spec format: {output_format}")


def export_skill(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    references_dir = output_dir / "references"
    references_dir.mkdir(exist_ok=True)
    (output_dir / "skill.yaml").write_text(skill_spec_text("yaml"), encoding="utf-8")
    (output_dir / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    (references_dir / "README.md").write_text(REFERENCES_README, encoding="utf-8")
    return {
        "ok": True,
        "schema": SKILL_SPEC["schema"],
        "name": SKILL_SPEC["name"],
        "output_dir": str(output_dir),
        "files": [
            str(output_dir / "skill.yaml"),
            str(output_dir / "SKILL.md"),
            str(references_dir / "README.md"),
        ],
    }
