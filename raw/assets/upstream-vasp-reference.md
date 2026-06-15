# Upstream VASP Reference Links

**Purpose**: Concise manifest of official VASP documentation sources for LLM wiki
evidence and diagnostic rule provenance. Do not duplicate full manual content;
link to canonical upstream resources.

## VASP Manual

| Resource | URL | Description |
|----------|-----|-------------|
| VASP manual hub | https://www.vasp.at/wiki/index.php/The_VASP_Manual | Top-level manual index |
| INCAR reference | https://www.vasp.at/wiki/index.php/INCAR | Input parameter catalog |
| POSCAR format | https://www.vasp.at/wiki/index.php/POSCAR | Structure file format |
| KPOINTS | https://www.vasp.at/wiki/index.php/KPOINTS | K-point mesh specification |
| ALGO | https://www.vasp.at/wiki/index.php/ALGO | Electronic minimization algorithms |
| MAGMOM | https://www.vasp.at/wiki/index.php/MAGMOM | Initial magnetic moments |
| ENCUT | https://www.vasp.at/wiki/index.php/ENCUT | Plane-wave cutoff |
| NCORE / NPAR | https://www.vasp.at/wiki/index.php/NCORE | Parallelization controls |

## Runtime diagnostics

| Topic | URL | Rule coverage |
|-------|-----|---------------|
| Electronic minimization | https://www.vasp.at/wiki/index.php/ALGO | `vasp.log.electronic_minimization_failed` |
| Symmetry | https://www.vasp.at/wiki/index.php/SYMPREC | `vasp.log.symmetry_failure` |

---
*Manifest created: 2026-06-15*
*Evidence for issues #82-#84: docs/wiki/provenance pipeline bootstrap*
