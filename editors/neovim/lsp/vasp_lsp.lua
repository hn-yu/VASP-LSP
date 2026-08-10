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
    local default_diagnostics_handler = vim.lsp.handlers["textDocument/publishDiagnostics"]
    local diagnostic_versions = {}

    -- Neovim 0.11 accepts the LSP diagnostic `version` field but its default
    -- handler does not use it to reject late notifications. Formatting and
    -- rapid edits can therefore let an older range overwrite a newer one.
    client.handlers["textDocument/publishDiagnostics"] = function(err, result, ctx, config)
      if result and result.uri and result.version ~= nil then
        local previous_version = diagnostic_versions[result.uri]
        if previous_version ~= nil and result.version < previous_version then
          return
        end
        diagnostic_versions[result.uri] = result.version
      end

      return default_diagnostics_handler(err, result, ctx, config)
    end

    local sync = client.server_capabilities.textDocumentSync
    if type(sync) == "table" then
      sync.change = 1 -- TextDocumentSyncKind.Full
    end
  end,
}
