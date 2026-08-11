# VASP-LSP

A Language Server for VASP. It provides completion, hover documentation,
diagnostics, and formatting for `INCAR`, `POSCAR`, `CONTCAR`, `KPOINTS`,
`POTCAR`, and selected VASP runtime logs.

This is a fork of [newtontech/VASP-LSP](https://github.com/newtontech/VASP-LSP):
[hn-yu/VASP-LSP](https://github.com/hn-yu/VASP-LSP).

## Install

Python 3.9+ and [uv](https://docs.astral.sh/uv/) are recommended.

```bash
uv tool install --force git+https://github.com/hn-yu/VASP-LSP.git
vasp-lsp --version
```

To install from a local checkout:

```bash
git clone https://github.com/hn-yu/VASP-LSP.git
cd VASP-LSP
uv tool install --force .
```

VASP is not required for editing, completion, or static diagnostics. A VASP
executable is needed only for the optional editor dry-run command.

## Use

### Neovim 0.11+

Install the bundled native LSP configuration:

```bash
mkdir -p ~/.config/nvim/lsp
curl -fsSL https://raw.githubusercontent.com/hn-yu/VASP-LSP/main/editors/neovim/lsp/vasp_lsp.lua \
  -o ~/.config/nvim/lsp/vasp_lsp.lua
```

Add this to `init.lua`:

```lua
vim.lsp.enable("vasp_lsp")
```

No `nvim-lspconfig` installation is required. Open an `INCAR`, `POSCAR`,
`CONTCAR`, `KPOINTS`, `POTCAR`, or VASP log file to start the server.

### VSCode

Build the extension from the checkout:

```bash
cd editors/vscode
npm install
npm run compile
npx @vscode/vsce package
```

Install the generated `.vsix` file from VSCode's Extensions menu with
**Install from VSIX**. The extension starts `vasp-lsp` automatically. If the
executable is not on VSCode's `PATH`, set:

```json
{
  "vasp-lsp.serverPath": "/absolute/path/to/vasp-lsp"
}
```

### Command line

Check a calculation directory:

```bash
vasp-lsp-check /path/to/calculation
```

For JSON output and CI failure on blocking diagnostics:

```bash
vasp-lsp-check /path/to/calculation --format json --fail-on-blocking
```

Inspect an INCAR keyword:

```bash
vasp-lsp-tool schema ENCUT
```

The editor-facing server command is:

```bash
vasp-lsp --stdio
```

More configuration, CLI contracts, and known boundaries are documented in the
[user guide](docs/user-guide.md), [Neovim guide](editors/neovim/README.md),
and [VSCode guide](editors/vscode/README.md).

## License

MIT
