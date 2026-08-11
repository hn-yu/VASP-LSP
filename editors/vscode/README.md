# VASP Language Support for VSCode

VSCode extension for VASP (Vienna Ab initio Simulation Package) input files.
This fork is published under the `hn-yu` publisher identity and tracks the
repository at https://github.com/hn-yu/VASP-LSP.

## Features

- 📝 **Syntax Highlighting** for INCAR, POSCAR, and KPOINTS files
- 🔮 **Autocomplete** - Smart completion for INCAR tags and values
- 📖 **Hover Documentation** - Instant access to VASP parameter documentation
- ⚠️ **Diagnostics** - Real-time error detection and warnings
- ✨ **Document Formatting** - Format INCAR, POSCAR, and KPOINTS files
- 🔧 **Quick Fixes** - Automatic fixes for common issues

POTCAR files are also recognized by the language client. Hovering over
`ENMAX` or `ENMIN` shows the read-only pseudopotential metadata and its
official VASP Wiki reference.

## Installation

### Prerequisites

1. Install the VASP-LSP server:
```bash
# This fork:
uv tool install git+https://github.com/hn-yu/VASP-LSP.git
# Or from a local clone:
# uv tool install --force .
```

2. Verify installation:
```bash
vasp-lsp --version
```

### Install Extension

1. Download the extension `.vsix` file
2. Open VSCode
3. Go to Extensions (Ctrl+Shift+X)
4. Click "..." menu → "Install from VSIX"
5. Select the downloaded file

## Usage

The extension automatically activates when you open VASP input files:
- `INCAR` or `*.incar`
- `POSCAR`, `CONTCAR` or `*.poscar`
- `KPOINTS` or `*.kpoints`
- `POTCAR`
- `OUTCAR`, `OSZICAR`, `STDOUT`, `STDERR`, `vasp.out`, `vasp.err`, or Slurm
  captures such as `slurm-123.out`

Runtime logs use the same language-server diagnostics as the Neovim config;
the bundled extension contributes the selector, so no manual VSCode mapping is
required.

### Autocomplete

Type an INCAR tag name and get suggestions:
```
EN↓  →  ENCUT, ENAUG, EMIN, EMAX
```

Type `=` after a tag to see valid values:
```
ISMEAR = ↓  →  -5, -4, -3, -2, -1, 0, 1, 2
```

### Snippets

Type a prefix and press Tab:

| Prefix | Description |
|--------|-------------|
| `basic` | Basic SCF template |
| `relax` | Structure relaxation template |
| `bands` | Band structure template |
| `md` | Molecular dynamics template |
| `ldau` | DFT+U template |

### Hover Documentation

Hover over any INCAR tag to see:
- Parameter description
- Valid values/range
- Default value
- Related parameters

### Format Document

Press `Shift+Alt+F` to format the current file.

## Configuration

Open VSCode settings (Ctrl+,) and search for "vasp-lsp":

| Setting | Default | Description |
|---------|---------|-------------|
| `vasp-lsp.serverPath` | `vasp-lsp` | Path to the vasp-lsp executable |
| `vasp-lsp.trace.server` | `off` | Trace LSP communication |

## Development

### Build from Source

```bash
cd editors/vscode
npm install
npm run compile
```

### Package Extension

```bash
npm install -g vsce
vsce package
```

## License

MIT
