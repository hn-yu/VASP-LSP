# VASP-LSP for Neovim

VASP-LSP uses Neovim's native LSP configuration API. The documented setup
targets Neovim 0.11 or newer.

You do not need to install nvim-lspconfig solely for VASP-LSP. It can still
be used for other servers in a larger Neovim distribution.

## Install the server

Install the executable with either pip or uv:

~~~bash
pip install vasp-lsp
# or
uv tool install vasp-lsp
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
LazyVim, already do this. A minimal configuration can use:

~~~lua
vim.cmd("filetype plugin indent on")
~~~

The bundled configuration also includes a small `on_init` compatibility
fallback that requests full-document synchronization from older VASP-LSP/pygls
installations. New installations receive the same mode from the server itself.

## Optional VASP filetype mappings

The server can diagnose OUTCAR, OSZICAR, STDOUT, STDERR, vasp.out, and Slurm
captures such as slurm-123.out. It can also provide hover documentation for
read-only metadata in POTCAR. Neovim does not assign a useful filetype to all
of these names by default. Add this before vim.lsp.enable("vasp_lsp"):

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
