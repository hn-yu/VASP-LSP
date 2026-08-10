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

  -- Keep compatibility with older VASP-LSP/pygls installations that may
  -- advertise incremental sync. The server also applies incremental changes,
  -- so this is a defensive client-side fallback rather than a requirement.
  on_init = function(client)
    local sync = client.server_capabilities.textDocumentSync
    if type(sync) == "table" then
      sync.change = 1 -- TextDocumentSyncKind.Full
    end
  end,
}
