# VASP-LSP

A Language Server Protocol (LSP) implementation for VASP (Vienna Ab initio Simulation Package) input/output files.

## Overview

VASP-LSP provides intelligent code editing and preflight diagnostics for VASP
calculation files:
- **INCAR** - Official-Wiki-backed keyword schema, autocomplete, hover, and validation
- **POSCAR/CONTCAR** - Structure parsing, diagnostics, and formatting
- **KPOINTS** - K-point parsing, diagnostics, and formatting
- **POTCAR** - Read-only pseudopotential metadata and POSCAR/POTCAR checks
- **VASP runtime logs** - Diagnostics for selected OUTCAR/stdout/stderr/Slurm logs

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
- ✏️ **Rename** - Previewed rename across open INCAR documents
- 🔧 **Quick Fixes** - Automatic fixes for common issues
- ✅ **Validate/Dry-Run** - Optional editor execute-command integration with a VASP binary

## Installation

```bash
pip install vasp-lsp
```

To install this fork instead, use `uv tool install
git+https://github.com/hn-yu/VASP-LSP.git` or run `uv tool install --force .`
from a local clone.

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

### Neovim (native LSP, 0.11+)

Neovim 0.11 uses its native vim.lsp.config/vim.lsp.enable API. Copy the
bundled configuration and enable it once:

The VASP-LSP setup does not require nvim-lspconfig by itself.

~~~bash
mkdir -p ~/.config/nvim/lsp
cp editors/neovim/lsp/vasp_lsp.lua ~/.config/nvim/lsp/vasp_lsp.lua
~~~

~~~lua
vim.lsp.enable("vasp_lsp")
~~~

See [the Neovim setup guide](editors/neovim/README.md) for optional log
filetypes and troubleshooting. The legacy
require("lspconfig").vasp_lsp.setup{} form is not the recommended setup for
Neovim 0.11+.

### Feature scope and boundaries

The native LSP server is the primary integration surface. Its core providers
are diagnostics, completion, hover, formatting, document symbols, code actions,
and document synchronization for the supported VASP file kinds. Cross-file
diagnostics use a small calculation workspace: an unsaved open buffer takes
precedence over the same file on disk, and recognized neighboring inputs are
read from the calculation directory when needed.

Some navigation features are intentionally narrower than their LSP names may
suggest:

| Feature | Actual scope | Maturity |
| --- | --- | --- |
| `textDocument/definition` | First matching INCAR assignment in the current document | Experimental navigation |
| `textDocument/references` | Matching INCAR assignments in the current document | Experimental navigation |
| `workspace/symbol` | Symbols from INCAR documents currently open in this server process | Experimental, open-buffer only |
| `textDocument/rename` | INCAR assignments in currently open buffers; returns a `WorkspaceEdit` | Experimental, open-buffer only |

These operations do not scan every file on disk and should not be described as
workspace-wide rename or workspace-wide references. They remain available for
existing users, but the boundaries above are part of the public contract.

The repository also contains compatibility adapters for agent integrations.
They are useful for existing callers, but new integrations should use the
documented CLI envelopes or the native LSP server rather than depending on the
legacy Python wrapper.

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
- **References**: Find all occurrences of a tag in the current document

### Rename
Previewed rename of INCAR tags in the open buffers known to the server. It does
not rewrite unopened files on disk.

### Quick Fixes
Automatic fixes for common issues:
- Add missing SIGMA when the selected ISMEAR mode uses smearing
- Add missing MAGMOM when ISPIN = 2
- Add missing LDAU parameters
- Remove conflicting NPAR/NCORE
- Fix common tag typos

## Diagnostic Rule Catalog (OpenQC / Diagnostic Engine v1)

VASP-LSP ships first-class diagnostic rules under stable `rule_id` codes. The
catalog is published as `rules/diagnostics.yaml` and can be consumed by OpenQC
and other tooling without importing the Python package.

The current catalog contains 21 conservative semantic/runtime rules. The
separate INCAR schema contains 611 recognized tags, including 610 imported
from the official VASP Wiki tag category; an unrecognized tag remains an
Error rather than being downgraded to hide schema gaps.

| Rule ID | Severity | Category | Source | Summary |
| --- | --- | --- | --- | --- |
| `vasp.incar.invalid_tag` | error | schema | official | Unknown INCAR tag (typo or stale name). |
| `vasp.incar.invalid_value` | error | schema | official | INCAR value does not match the tag's declared type. |
| `vasp.spin.missing_magmom` | warning | semantic consistency | official | `ISPIN=2` without an explicit `MAGMOM`. |
| `vasp.magnetism.noncollinear_ispin_conflict` | warning | semantic consistency | official | `ISPIN=2` combined with non-collinear spin. |
| `vasp.magnetism.magmom_shape_mismatch` | warning | cross-file reference | official | `MAGMOM` shape does not match POSCAR and spin mode. |
| `vasp.smearing.ismear_sigma_mismatch` | warning | semantic consistency | official | Inconsistent `ISMEAR`/`SIGMA` pair. |
| `vasp.smearing.tetrahedron_requires_gamma` | warning | cross-file reference | official | Tetrahedron smearing with a shifted Monkhorst-Pack mesh. |
| `vasp.encut.below_enmax` | warning | cross-file reference | official | `ENCUT` below the largest POTCAR `ENMAX`. |
| `vasp.dftu.parameters_incomplete` | warning | semantic consistency | official | `LDAU=.TRUE.` without explicit `LDAUTYPE`/`LDAUL`/`LDAUU`; `LDAUJ` remains optional. |
| `vasp.dftu.lmaxmix_for_fixed_charge` | warning | semantic consistency | official | DFT+U fixed-charge mode without sufficient `LMAXMIX`. |
| `vasp.ionic.md_missing_potim` | error | preflight/runtime-risk | official | `IBRION=0` without the required MD timestep `POTIM`. |
| `vasp.ionic.ibrion_nsw_mismatch` | warning | semantic consistency | official | `IBRION` and `NSW` request incompatible ionic work. |
| `vasp.ionic.mdalgo_requires_md` | warning | semantic consistency | official | `MDALGO` used outside `IBRION=0` molecular dynamics. |
| `vasp.electrostatics.missing_idipol` | warning | semantic consistency | official | `LDIPOL=.TRUE.` without `IDIPOL`. |
| `vasp.hybrid.veryfast_incompatible` | warning | preflight/runtime-risk | official | `ALGO=VeryFast` with a hybrid functional. |
| `vasp.symmetry.md_isym_zero` | warning | semantic consistency | official | MD without the recommended `ISYM=0`. |
| `vasp.parallel.ncore_npar_conflict` | warning | preflight/runtime-risk | official | Both `NCORE` and `NPAR` declared. |
| `vasp.parallel.kpar_incompatible` | warning | semantic consistency | official | `KPAR` combined with band-level `NCORE`/`NPAR`. |
| `vasp.restart.file_mismatch` | warning | cross-file reference | official | Restart intent without the matching `WAVECAR`/`CHGCAR`. |
| `vasp.log.symmetry_failure` | error | preflight/runtime-risk | runtime | VASP log symmetry-analysis failure (`INVGRP`/`PRICEL`/`SGRCON`/`SGRGEN`). |
| `vasp.log.electronic_minimization_failed` | error | preflight/runtime-risk | runtime | VASP log electronic-minimization failure (`EDDDAV`/`EDDRMM`/`PSSYEVX`/`ZPOTRF`). |

Run `vasp-lsp-tool rules` to export the catalog as JSON. Add `--fail-on-blocking`
to `vasp-lsp-check` for non-zero exit on blocking diagnostics.

## Agent JSON API and compatibility surfaces

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
vasp-lsp-schema-audit
vasp-lsp-examples static
vasp-lsp-tool next-tokens ISMEAR

# Single-file agent queries (context, complete, hover, symbols, and fix).
vasp-lsp-tool check path/to/INCAR
vasp-lsp-tool context path/to/INCAR --line 5
vasp-lsp-tool hover path/to/INCAR --line 0 --character 2
vasp-lsp-tool symbols path/to/INCAR
vasp-lsp-tool fix path/to/INCAR
```

There are two intentionally different JSON envelopes:

| Envelope | Entry points | Identifying fields | Use |
| --- | --- | --- | --- |
| `DiagnosticEnvelope/v1` | `vasp-lsp-tool check/context/complete/hover/symbols/fix` | `operation`, `uri`, `diagnostics`, `summary`, `capabilities` | Single-file agent operations and provider-shaped responses |
| `vasp-lsp.plan24.v1` | `vasp-lsp-check`, `vasp-lsp-explain` | `schema_version`, `source`, `diagnostics`, `summary` | Calculation-directory checks and runtime-log explanations |

The envelopes are related but not interchangeable. Consumers should dispatch
on `schema_version` or `capabilities.operation` instead of assuming that every
payload has the same top-level fields. Every agent payload also exposes a
`capabilities` block where that CLI surface supports it.

The agent operation adapter first looks for optional module-level provider
hooks. If a hook is unavailable, it deliberately returns a generic fallback:
text-based symbols/completions, diagnostic-derived hover text, or diagnostic
fix hints. The fallback is deterministic and useful for automation, but it is
not equivalent to the native editor providers and is reported through the
operation status/source metadata.

`vasp_lsp.agent_lsp.AgentLSP` remains as a compatibility wrapper for existing
Python callers that use `from_text`/`from_path`. It delegates to the agent
operation and diagnostic contracts; it is not a second LSP server and it does
not provide disk-wide navigation. New integrations should use
`vasp-lsp-tool`/`vasp-lsp-check` or connect to `vasp-lsp --stdio` directly.

VASP dry-run is available only through the native LSP
`workspace/executeCommand` command `vasp-lsp.validate`. The editor must have
the document open, and a VASP binary must be supplied as the command argument
or through `VASP_BINARY`/`VASP_LSP_VASP_BINARY`. It is not an operation of
`vasp-lsp-tool`.

## Development

```bash
git clone https://github.com/hn-yu/VASP-LSP.git
cd VASP-LSP
uv sync --extra dev
```

The original upstream repository is
[newtontech/VASP-LSP](https://github.com/newtontech/VASP-LSP). This fork is
[hn-yu/VASP-LSP](https://github.com/hn-yu/VASP-LSP).

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

Before releasing a schema update, run the offline provenance audit:

```bash
vasp-lsp-schema-audit
```

The audit does not access the network. To refresh the checked-in catalog from
the official Wiki, use `python scripts/update_incar_wiki_schema.py`, review
the generated diff, and then run the audit and test suite.


## Code Quality

The project maintains high code quality through:
- **95%+ enforced coverage** - All new code paths are tested; the threshold is enforced in CI.
- **Code cleanup** - Dead code and unreachable branches removed.
- **Static analysis** - Linting with Ruff, formatting with Black, type checking with mypy.
- **Type hints** - Full type annotations for better IDE support.
- **1,100+ tests** covering formatting, diagnostics, completion, hover, navigation, rename, code actions, schema integrity, workspace context, and validate commands.

## License

MIT License

## Acknowledgments

- Inspired by [cp2k-language-server](https://github.com/cp2k/cp2k-input-tools)
- Built with [pygls](https://github.com/openlawlibrary/pygls)
