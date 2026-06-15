---
name: vasp
description: "VASP input preflight for INCAR, POSCAR, KPOINTS, and related generated inputs."
---

# VASP LSP Skill

Use this skill when preparing, repairing, or reviewing VASP input files before a run. It provides an installable language server and an agent-facing CLI that reports machine-readable diagnostics.

## Scope

- Input patterns: INCAR, POSCAR, KPOINTS, POTCAR, CONTCAR, OSZICAR, OUTCAR, vasprun.xml
- Server command: `vasp-lsp`
- Agent CLI: `vasp-lsp-tool`
- Diagnostic contract: `DiagnosticEnvelope/v1`

## Installing the checker

```bash
pip install vasp-lsp
```

This installs the `vasp-lsp` language server and the `vasp-lsp-tool` agent CLI from the `vasp-lsp` Python package.

## Useful inspection commands

```bash
vasp-lsp-tool capabilities
vasp-lsp-tool skill-spec --format json
vasp-lsp-tool skill-export --output ./skill
vasp-lsp-tool check <input-file-or-dir> --format json
vasp-lsp-tool context <input-file-or-dir> --line 0 --character 0 --format json
vasp-lsp-tool hover <input-file-or-dir> --line 0 --character 0 --format json
vasp-lsp-tool complete <input-file-or-dir> --line 0 --character 0 --format json
vasp-lsp-tool symbols <input-file-or-dir> --format json
vasp-lsp-tool fix <input-file-or-dir> --line 0 --character 0 --format json
```

`fix` is advisory and must be treated as a preview. Do not blindly apply a repair without preserving the user's scientific intent.

## Validation gate

Before saying generated inputs are ready, run:

```bash
vasp-lsp-tool check <input-file-or-dir> --format json --fail-on-blocking
```

Report `commands`, `files_checked`, `tool_available`, `diagnostics`, `blocking_findings`, `readiness`, and `reason`.

## Repair rules

1. Validate first and identify the smallest blocking issue.
2. Fix syntax or schema errors with minimal edits.
3. Preserve scientific settings unless the user explicitly asks to redesign them.
4. Re-run the checker after every edit.
5. Separate syntax, schema, semantic, and runtime-log diagnostics in the final report.
