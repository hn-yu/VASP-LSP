# VASP_Input_Validation

> Type: concept
> Domain: VASP input preparation
> Sources: `rules/diagnostics.yaml`, `tests/fixtures/valid/`, `tests/fixtures/invalid/`

## Definition

VASP input validation checks the consistency and syntax of input files such as INCAR, KPOINTS, POSCAR, and related simulation metadata before a calculation is run.

## Agent Use

Agents should treat diagnostics as actionable feedback, apply minimal fixes, and rerun validation before considering an input ready.

## Related Pages

- [[VASP_LSP]]
- [[Agent_Workflow]]

## Sources

- https://www.vasp.at/wiki/index.php/INCAR — upstream INCAR schema
- `tests/fixtures/rules/` — per-rule valid/invalid goldens with provenance
- `raw/assets/asset-manifest.json` — captured docs and rule digest metadata
