# Agent_Workflow

> Created: 2026-06-12
> Sources: `lsp-capabilities.json`, `vasp-lsp-tool`, `scripts/wiki_lint.py`

## Core Workflow

1. Read or generate VASP input files.
2. Run the VASP-LSP diagnostic interface.
3. Convert diagnostics into targeted edits.
4. Rerun diagnostics until no blocking issue remains.

## Related Pages

- [[VASP_LSP]]
- [[VASP_Input_Validation]]

## Sources

- `vasp-lsp-tool check|rules|explain` — agent JSON CLI (`DiagnosticEnvelope/v1`)
- `tests/fixtures/valid/` and `tests/fixtures/invalid/` — closed-loop gate fixtures
- `python scripts/wiki_lint.py` — provenance and manifest refresh verifier
