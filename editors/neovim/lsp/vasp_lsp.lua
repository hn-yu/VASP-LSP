-- Native Neovim 0.11+ configuration for VASP-LSP.
--
-- Copy this file to:
--   ~/.config/nvim/lsp/vasp_lsp.lua
--
-- Then enable it once from init.lua:
--   vim.lsp.enable("vasp_lsp")

return {
  cmd = { "vasp-lsp", "--stdio" },

  filetypes = {
    "incar",
    "poscar",
    "kpoints",
    "outcar",
    "vasp_log",
  },

  root_markers = {
    "INCAR",
    "POSCAR",
    "KPOINTS",
    "POTCAR",
    ".git",
  },
}
