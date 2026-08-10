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
    local formatting_requests = {}

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

    -- Neovim keeps diagnostics as extmarks while a formatting edit is being
    -- applied.  If the formatter deletes or moves a line, those extmarks can
    -- temporarily follow the old diagnostic to a different line until the
    -- server publishes the next snapshot.  Clear only the old snapshot after
    -- a formatting request that actually changed the buffer; a no-op format
    -- must leave the current diagnostics intact.
    local formatting_group = vim.api.nvim_create_augroup(
      "VaspLspFormattingDiagnostics" .. client.id,
      { clear = true }
    )
    vim.api.nvim_create_autocmd("LspRequest", {
      group = formatting_group,
      callback = function(args)
        local data = args.data or {}
        if data.client_id ~= client.id then
          return
        end

        local request = data.request
        if type(request) ~= "table" then
          return
        end
        if request.method ~= "textDocument/formatting"
          and request.method ~= "textDocument/rangeFormatting" then
          return
        end

        local request_id = data.request_id
        if request.type == "pending" then
          if request_id and vim.api.nvim_buf_is_valid(args.buf) then
            formatting_requests[request_id] = {
              bufnr = args.buf,
              changedtick = vim.api.nvim_buf_get_changedtick(args.buf),
            }
          end
          return
        end

        local pending = request_id and formatting_requests[request_id]
        if request_id then
          formatting_requests[request_id] = nil
        end
        if not pending or request.type ~= "complete" then
          return
        end

        -- For synchronous formatting, LspRequest/complete fires before the
        -- caller applies the returned edits.  Defer one event-loop turn so
        -- the changedtick comparison observes the final formatted buffer.
        vim.defer_fn(function()
          if not vim.api.nvim_buf_is_valid(pending.bufnr) then
            return
          end
          if vim.api.nvim_buf_get_changedtick(pending.bufnr) == pending.changedtick then
            return
          end
          vim.diagnostic.reset(
            vim.lsp.diagnostic.get_namespace(client.id),
            pending.bufnr
          )
        end, 0)
      end,
    })

    local sync = client.server_capabilities.textDocumentSync
    if type(sync) == "table" then
      sync.change = 1 -- TextDocumentSyncKind.Full
    end
  end,
}
