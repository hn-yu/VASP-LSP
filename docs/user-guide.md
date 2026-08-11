# VASP-LSP User Guide

Complete guide for using VASP-LSP Language Server Protocol implementation for VASP input files.

## Installation

### Python Package

```bash
pip install vasp-lsp
```

### Development Installation

```bash
git clone https://github.com/newtontech/VASP-LSP.git
cd VASP-LSP
pip install -e ".[dev]"
```

## Quick Start

### Running as Standalone Server

```bash
# Standard I/O mode
vasp-lsp --stdio

# TCP mode (for debugging)
vasp-lsp --tcp --host 127.0.0.1 --port 2087
```

### Neovim Configuration

For Neovim 0.11 or newer, copy the native configuration shipped with this
repository:

The VASP-LSP setup does not require nvim-lspconfig by itself.

~~~bash
mkdir -p ~/.config/nvim/lsp
cp editors/neovim/lsp/vasp_lsp.lua ~/.config/nvim/lsp/vasp_lsp.lua
~~~

Enable it once from init.lua:

~~~lua
vim.lsp.enable("vasp_lsp")
~~~

See [editors/neovim/README.md](../editors/neovim/README.md) for optional VASP
log filetypes and troubleshooting. The legacy
require("lspconfig").vasp_lsp.setup{} form is not the recommended setup for
Neovim 0.11+.

## Supported File Types

- **INCAR**: Main input file with the official Wiki catalog plus reviewed local metadata
- **POSCAR**: Structure file with lattice and coordinates
- **KPOINTS**: K-point grid specification
- **POTCAR**: Pseudopotential metadata (parsed for ENMAX/ENMIN cross-file checks)
- **VASP logs**: OUTCAR, OSZICAR, STDOUT/STDERR, and Slurm captures
- **VASP runtime logs**: OUTCAR / stdout / stderr / slurm captures (parsed for runtime diagnostics)

## Features

### Autocomplete
- Parameter name suggestions
- Valid values for enums
- Boolean values (.TRUE./.FALSE.)

### Hover Documentation
- Parameter descriptions
- Valid values/ranges
- Default values

### Diagnostics
- Unknown parameter warnings
- Invalid value errors
- Missing required parameters
- Parameter conflicts
- First-class rule codes (see `rules/diagnostics.yaml`)

### Quick Fixes
- Add missing SIGMA when ISMEAR >= 0
- Add MAGMOM when ISPIN = 2
- Fix negative scale factors
- Wrap out-of-range coordinates

### Document Formatting
- Group INCAR parameters by category
- Align parameter values
- Normalize coordinate precision

### Rename / Navigation
- LSP `textDocument/rename` for INCAR tags
- LSP `textDocument/documentSymbol` for INCAR/POSCAR/KPOINTS
- LSP `textDocument/hover`, `definition`, and `references` providers

### Agent JSON API (Diagnostic Engine v1)
- `vasp-lsp-check path/to/calc --format json --fail-on-blocking`
- `vasp-lsp-explain path/to/run.out --format json`
- `vasp-lsp-describe`, `vasp-lsp-schema ENCUT`, `vasp-lsp-schema-audit`, `vasp-lsp-examples static`
- `vasp-lsp-tool rules` exports the rule catalog

## License

MIT License
