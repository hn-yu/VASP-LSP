# VASP-LSP

A Language Server Protocol (LSP) implementation for VASP (Vienna Ab initio Simulation Package) input/output files.

## Overview

VASP-LSP provides intelligent code editing features for VASP calculation input files:
- **INCAR** - Input parameters with autocomplete and validation
- **POSCAR** - Structure file syntax highlighting
- **KPOINTS** - K-point grid configuration

## Features

- 📝 **Autocomplete** - Smart completion for INCAR tags and values
- 📖 **Hover Documentation** - Instant access to VASP parameter documentation
- ⚠️ **Diagnostics** - Real-time error detection and warnings
- ✨ **Document Formatting** - Format INCAR, POSCAR, and KPOINTS files
- ✨ **Range Formatting** - Format selected lines in INCAR files
- 🔍 **Go-to-Definition** - Jump to the first definition of an INCAR tag
- 🔍 **Find References** - Find all occurrences of an INCAR tag
- 📋 **Document Symbols** - Outline view for INCAR, POSCAR, and KPOINTS
- 🔎 **Workspace Symbols** - Search symbols across open INCAR documents
- ✏️ **Rename** - Safe workspace-wide rename of INCAR tags
- 🔧 **Quick Fixes** - Automatic fixes for common issues
- ✅ **Validate/Dry-Run** - Optional VASP binary validation with diagnostics

## Installation

```bash
pip install vasp-lsp
```

### VSCode Extension

A VSCode extension is available in `editors/vscode/`. See the [extension README](editors/vscode/README.md) for installation instructions.

## Usage

### As a standalone server

```bash
vasp-lsp --stdio
```

### TCP mode (for debugging)

```bash
vasp-lsp --tcp --host 127.0.0.1 --port 2087
```

### Neovim (nvim-lspconfig)

```lua
require'lspconfig'.vasp_lsp.setup{}
```

## Features Details

### Autocomplete
Provides intelligent completions for:
- INCAR parameter names
- Parameter values (enums, booleans)
- Context-aware suggestions

### Hover Documentation
Hover over any INCAR parameter to see:
- Parameter description
- Valid values/range
- Default value
- Related parameters

### Diagnostics
Real-time validation including:
- Unknown parameter detection
- Value type checking
- Range validation
- Parameter dependency checks
- Common configuration warnings

### Document Formatting
Format your VASP input files:
- **INCAR**: Parameters grouped by category, aligned values
- **POSCAR**: Consistent coordinate precision, proper spacing
- **KPOINTS**: Normalized grid types, formatted k-point lists
- **Range Formatting**: Format only selected lines in INCAR files

### Go-to-Definition and References
Navigate INCAR tags:
- **Definition**: Jump to the first occurrence of a tag
- **References**: Find all occurrences of a tag in the document

### Rename
Safe workspace-wide rename of INCAR tags with preview validation.

### Quick Fixes
Automatic fixes for common issues:
- Add missing SIGMA when ISMEAR >= 0
- Add missing MAGMOM when ISPIN = 2
- Add missing LDAU parameters
- Remove conflicting NPAR/NCORE
- Fix common tag typos

## Diagnostic Rule Catalog (OpenQC / Diagnostic Engine v1)

VASP-LSP ships first-class diagnostic rules under stable `rule_id` codes. The
catalog is published as `rules/diagnostics.yaml` and can be consumed by OpenQC
and other tooling without importing the Python package.

| Rule ID | Severity | Category | Source | Summary |
| --- | --- | --- | --- | --- |
| `vasp.incar.invalid_tag` | error | schema | official | Unknown INCAR tag (typo or stale name). |
| `vasp.incar.invalid_value` | error | schema | official | INCAR value does not match the tag's declared type. |
| `vasp.spin.missing_magmom` | warning | semantic consistency | official | `ISPIN=2` without an explicit `MAGMOM`. |
| `vasp.smearing.ismear_sigma_mismatch` | warning | semantic consistency | official | Inconsistent `ISMEAR`/`SIGMA` pair. |
| `vasp.encut.below_enmax` | warning | cross-file reference | official | `ENCUT` below the largest POTCAR `ENMAX`. |
| `vasp.parallel.ncore_npar_conflict` | warning | preflight/runtime-risk | official | Both `NCORE` and `NPAR` declared. |
| `vasp.parallel.kpar_incompatible` | warning | semantic consistency | official | `KPAR` combined with band-level `NCORE`/`NPAR`. |
| `vasp.restart.file_mismatch` | warning | cross-file reference | official | Restart intent without the matching `WAVECAR`/`CHGCAR`. |
| `vasp.log.symmetry_failure` | error | preflight/runtime-risk | runtime | VASP log symmetry-analysis failure (`INVGRP`/`PRICEL`/`SGRCON`/`SGRGEN`). |
| `vasp.log.electronic_minimization_failed` | error | preflight/runtime-risk | runtime | VASP log electronic-minimization failure (`EDDDAV`/`EDDRMM`/`PSSYEVX`/`ZPOTRF`). |

Run `vasp-lsp-tool rules` to export the catalog as JSON. Add `--fail-on-blocking`
to `vasp-lsp-check` for non-zero exit on blocking diagnostics.

## Agent JSON API (Diagnostic Engine v1)

VASP-LSP ships a documented agent CLI surface for Claude Code, OpenCode, and
Codex workflows:

```bash
# Live diagnostics for a calculation directory.
vasp-lsp-check path/to/calc --format json --fail-on-blocking

# Parse VASP runtime logs (OUTCAR/stdout/stderr/slurm*.out) into diagnostics.
vasp-lsp-explain path/to/run.out --format json

# Inspect the rule catalog or a single rule.
vasp-lsp-tool rules
vasp-lsp-tool rules vasp.encut.below_enmax
vasp-lsp-tool explain vasp.log.symmetry_failure

# DSL overview, keyword schema, minimal examples, and next-token guidance.
vasp-lsp-describe
vasp-lsp-schema ENCUT
vasp-lsp-examples static
vasp-lsp-tool next-tokens ISMEAR

# Single-file agent queries (context, complete, hover, symbols, fix, validate).
vasp-lsp-tool check path/to/INCAR
vasp-lsp-tool context path/to/INCAR --line 5
vasp-lsp-tool hover path/to/INCAR --line 0 --character 2
vasp-lsp-tool symbols path/to/INCAR
vasp-lsp-tool fix path/to/INCAR
vasp-lsp-tool validate path/to/INCAR --binary /path/to/vasp
```

Every payload includes a `capabilities` block listing the available operations,
so callers can probe support without parsing free text.

## Development

```bash
git clone https://github.com/newtontech/VASP-LSP.git
cd VASP-LSP
pip install -e ".[dev]"
```

## Testing

Run tests with:

```bash
pytest --cov=src/vasp_lsp --cov-report=term-missing
```

To verify current coverage, run the command above and check the TOTAL line in the report.
Coverage thresholds are enforced in CI (see `.github/workflows/ci.yml`).

### Release verification

Releases are published from `v*` tag pushes by `.github/workflows/release.yml`.
The workflow checks that the tag, Python package, VS Code extension, `VERSION`,
and OpenQC capability manifest agree, then builds the distributions and installs
the wheel into a new virtual environment. The isolated smoke verifies
`vasp-lsp --help`, the agent JSON CLI, and the valid, invalid, and runtime-log
fixtures before the OIDC-enabled `pypi` environment can publish. No long-lived
PyPI token is used.

GitHub Release finalization runs independently after the verified wheel smoke
and attaches that exact build artifact. A PyPI outage or trusted-publisher
misconfiguration can therefore fail PyPI without suppressing the native GitHub
Release; the finalizer also proves that the checkout and tag equal
`GITHUB_SHA` before creating the release.

Maintainers can exercise the same artifact smoke before creating a tag:

```bash
python -m pip install build
python -m build
python scripts/verify_release.py --tag v0.4.5
python scripts/smoke_test_wheel.py --wheel dist/vasp_lsp-0.4.5-py3-none-any.whl
```


## Code Quality

The project maintains high code quality through:
- **95%+ enforced coverage** - All new code paths are tested; the threshold is enforced in CI.
- **Code cleanup** - Dead code and unreachable branches removed.
- **Static analysis** - Linting with Ruff, formatting with Black, type checking with mypy.
- **Type hints** - Full type annotations for better IDE support.
- **992 tests** covering formatting, diagnostics, completion, hover, navigation, rename, code actions, and validate commands.

## License

MIT License

## Acknowledgments

- Inspired by [cp2k-language-server](https://github.com/cp2k/cp2k-input-tools)
- Built with [pygls](https://github.com/openlawlibrary/pygls)
