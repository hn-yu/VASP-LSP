# VASP-LSP for Neovim

VASP-LSP uses Neovim's native LSP configuration API. The documented setup
targets Neovim 0.11 or newer.

You do not need to install nvim-lspconfig solely for VASP-LSP. It can still
be used for other servers in a larger Neovim distribution.

## Install the server

Install the executable with uv:

~~~bash
# Published upstream package:
uv tool install vasp-lsp

# This fork:
uv tool install git+https://github.com/hn-yu/VASP-LSP.git
~~~

Check that Neovim can find it:

~~~vim
:lua print(vim.fn.exepath("vasp-lsp"))
~~~

## Install the native config

Copy the bundled config:

~~~bash
mkdir -p ~/.config/nvim/lsp
cp editors/neovim/lsp/vasp_lsp.lua ~/.config/nvim/lsp/vasp_lsp.lua
~~~

Enable it from init.lua:

~~~lua
vim.lsp.enable("vasp_lsp")
~~~

Neovim's filetype detection must be enabled. Most distributions, including
LazyVim, already do this. The bundled LSP config also registers the standard
VASP filenames automatically. A minimal configuration can use:

~~~lua
vim.cmd("filetype plugin indent on")
~~~

The bundled configuration also includes a small `on_init` compatibility
fallback that requests full-document synchronization from older VASP-LSP/pygls
installations. New installations receive the same mode from the server itself.

## Additional log filetype mappings

The bundled configuration registers OUTCAR, OSZICAR, STDOUT, STDERR, vasp.out,
and Slurm captures such as slurm-123.out. If another plugin overwrites those
filetype mappings, the following explicit mapping can be used before
`vim.lsp.enable("vasp_lsp")`:

~~~lua
vim.filetype.add({
  filename = {
    POTCAR = "potcar",
    OSZICAR = "vasp_log",
    STDOUT = "vasp_log",
    STDERR = "vasp_log",
    ["vasp.out"] = "vasp_log",
  },
  pattern = {
    ["slurm%-.*%.out"] = "vasp_log",
  },
})
~~~

The `potcar` filetype enables hover documentation for read-only POTCAR
metadata such as `ENMAX` and `ENMIN`. These are not INCAR keywords and are
therefore intentionally absent from INCAR completion.

OUTCAR is detected as outcar by current Neovim releases and is already
included in the bundled LSP config.

## Troubleshooting

Run these commands inside Neovim:

~~~vim
:set filetype?
:checkhealth vim.lsp
:LspInfo
~~~

The most common causes of no attachment are an empty filetype, a missing
vasp-lsp executable in Neovim's PATH, or a directory without one of the
configured root markers.
