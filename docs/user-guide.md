# VASP-LSP User Guide

VASP-LSP is a native Language Server Protocol server for VASP input files,
selected pseudopotential metadata, and selected VASP runtime logs. The native
server is the recommended editor integration; the JSON CLI is the recommended
automation integration.

## Installation

### Install this fork

The fork is not the same distribution as the original
[newtontech/VASP-LSP](https://github.com/newtontech/VASP-LSP). Install the fork
directly from GitHub:

```bash
uv tool install git+https://github.com/hn-yu/VASP-LSP.git
vasp-lsp --version
```

For a local checkout:

```bash
uv tool install --force .
```

The package does not need a VASP installation for static parsing, schema
validation, completion, or runtime-log pattern recognition. A VASP executable
is needed only for the optional editor dry-run command described below.

### Development installation

```bash
git clone https://github.com/hn-yu/VASP-LSP.git
cd VASP-LSP
uv sync --extra dev
```

## Quick start

### Standalone server

```bash
vasp-lsp --stdio
```

TCP mode is available for debugging clients:

```bash
vasp-lsp --tcp --host 127.0.0.1 --port 2087
```

### Neovim 0.11+

Copy the native configuration shipped with this repository:

```bash
mkdir -p ~/.config/nvim/lsp
cp editors/neovim/lsp/vasp_lsp.lua ~/.config/nvim/lsp/vasp_lsp.lua
```

Enable it once from `init.lua`:

```lua
vim.lsp.enable("vasp_lsp")
```

The bundled configuration registers the standard VASP filenames, including
INCAR, POSCAR, CONTCAR, KPOINTS, POTCAR, OUTCAR, OSZICAR, and common Slurm log
names. `nvim-lspconfig` is not required for this setup. If another plugin
overwrites filetype detection, inspect `:set filetype?` and restore the
mapping before enabling the server.

The older `require("lspconfig").vasp_lsp.setup{}` path remains a compatibility
option for older configurations, but it is not the recommended Neovim 0.11+
setup.

### VSCode

Build or install the extension under `editors/vscode/`. The extension selects
the same VASP file kinds as the Neovim configuration and starts `vasp-lsp
--stdio`. Set `vasp-lsp.serverPath` if the executable is not on VSCode's PATH.
See [the VSCode guide](../editors/vscode/README.md) for packaging details.

## Supported file kinds

| File kind | What the server provides | Important boundary |
| --- | --- | --- |
| `INCAR` | Schema validation, completion, hover, formatting, diagnostics, code actions | Unknown tags remain errors; the server does not silently accept arbitrary keywords |
| `POSCAR` | Structure parsing, diagnostics, hover, completion, formatting, symbols | VASP 4 files use `TypeN` placeholders when species names are absent |
| `CONTCAR` | POSCAR-style parsing and diagnostics, including legal velocity/MD sections | It is classified as a POSCAR document, not a separate keyword language |
| `KPOINTS` | Grid/line-mode parsing, diagnostics, hover, completion, formatting | Sparse-grid messages are advisory; convergence remains a scientific decision |
| `POTCAR` | Species/order checks, selected metadata diagnostics, `ENMAX`/`ENMIN` hover | Metadata is read-only and is not INCAR completion; `POTCAR.spec` is not treated as POTCAR |
| VASP runtime logs | Selected failure-pattern diagnostics | No input completion or formatting; this is not a complete VASP log interpreter |

## Core editor features

The native LSP providers cover:

- INCAR keyword and value completion, including boolean and enum values;
- hover documentation for INCAR schema entries and supported structure/POTCAR
  locations;
- syntax, type, range, cross-file, and semantic diagnostics;
- formatting for INCAR, POSCAR/CONTCAR, and KPOINTS;
- document symbols for INCAR, POSCAR/CONTCAR, and KPOINTS;
- diagnostic code actions where a safe fix hint exists.

Cross-file checks use the calculation directory around the current document.
An open unsaved buffer takes precedence over the same file on disk. Depending
on the anchor file, checks can use POSCAR or CONTCAR, KPOINTS, POTCAR,
WAVECAR/CHGCAR existence, and selected configuration files. The CLI and the
editor use the same overlay-before-disk rule.

The severity of a genuinely unknown INCAR tag is `Error`. Schema gaps are fixed
by adding reviewed metadata; they are not hidden by downgrading the diagnostic.

## Navigation boundaries

The server advertises several navigation methods, but their scopes differ:

| Operation | Scope |
| --- | --- |
| Document symbols | Current supported document |
| Definition | First matching INCAR assignment in the current document |
| References | Matching INCAR assignments in the current document |
| Workspace symbols | INCAR documents currently open in this server process |
| Rename | Matching INCAR assignments in currently open buffers |

Rename returns a `WorkspaceEdit`, but it does not scan or edit unopened files on
disk. These navigation methods are retained for existing users and should be
treated as experimental/open-buffer features rather than a repository-wide
symbol index or workspace-wide rename service.

## Agent and automation CLI

### Calculation and runtime checks

```bash
# Check one file or an entire calculation directory.
vasp-lsp-check path/to/calc --format json --fail-on-blocking

# Explain selected VASP runtime logs.
vasp-lsp-explain path/to/OUTCAR --format json
```

### Single-file operations and catalog commands

```bash
vasp-lsp-tool check path/to/INCAR --format json
vasp-lsp-tool context path/to/INCAR --line 5 --format json
vasp-lsp-tool complete path/to/INCAR --format json
vasp-lsp-tool hover path/to/INCAR --line 0 --character 2 --format json
vasp-lsp-tool symbols path/to/INCAR --format json
vasp-lsp-tool fix path/to/INCAR --format json

vasp-lsp-tool rules
vasp-lsp-tool schema ENCUT
vasp-lsp-tool schema-audit
vasp-lsp-tool describe
vasp-lsp-tool examples static
vasp-lsp-tool next-tokens ISMEAR
```

The two diagnostic families intentionally use different top-level JSON
envelopes:

- `vasp-lsp-tool` operation payloads use the `DiagnosticEnvelope/v1` shape:
  `operation`, `uri`, `diagnostics`, `summary`, and `capabilities`.
- `vasp-lsp-check` and `vasp-lsp-explain` use
  `vasp-lsp.plan24.v1`: `schema_version`, `source`, `diagnostics`, and
  `summary`.

The diagnostic items are related, but consumers should inspect the envelope
identifier instead of assuming that fields from one family exist in the
other.

For completion, symbols, hover, and fix operations, the agent adapter first
looks for optional provider hooks. If no hook is available, it returns a
deterministic generic fallback based on assignments, diagnostics, and manual
references. The payload reports its operation status/source. This fallback is
useful for automation but is not a replacement for the native editor provider.

`vasp_lsp.agent_lsp.AgentLSP` is retained as a compatibility wrapper for
existing Python callers. New integrations should use the native LSP or the
documented CLI commands; the wrapper is not a second server and should not be
the basis of new provider implementations.

## Optional VASP dry-run

The native server exposes `workspace/executeCommand` command
`vasp-lsp.validate`. It operates on an open editor document and invokes a VASP
binary with `--dry-run`. Supply the binary path as the command argument or set
`VASP_BINARY`/`VASP_LSP_VASP_BINARY`.

This is an editor command, not a `vasp-lsp-tool validate` CLI operation. Static
LSP diagnostics and JSON checks never execute VASP implicitly.

## Troubleshooting

If no diagnostics or completion appear:

1. Check that the executable is visible to the editor: `which vasp-lsp`.
2. Check the active filetype in Neovim with `:set filetype?` or inspect the
   VSCode language mode.
3. Check the client attachment with `:LspInfo` and `:checkhealth vim.lsp`.
4. Confirm that the current filename is a supported VASP name and that the
   calculation neighbors are in the same directory.

For stale signs after formatting, make sure the editor is using the bundled
configuration and that it has not replaced the server's full-document sync or
diagnostic handler.

## References

- [Architecture and implementation boundaries](architecture.md)
- [Validation contract](validation-contract.md)
- [VASP Wiki](https://www.vasp.at/wiki/)
- [Original upstream repository](https://github.com/newtontech/VASP-LSP)
- [This fork](https://github.com/hn-yu/VASP-LSP)
