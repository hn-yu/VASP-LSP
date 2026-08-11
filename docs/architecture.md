# Architecture

VASP-LSP has two related entry points that share parsers, schema data, and
diagnostic rules:

1. The native LSP server is the primary editor integration.
2. The agent CLI is a deterministic JSON adapter for scripts and automation.

The Python agent wrapper and the generic agent fallbacks are compatibility
surfaces around the second entry point. They are intentionally not presented
as a second implementation of the editor providers.

## System boundary

```text
                 Native LSP clients
             (Neovim, VSCode, other editors)
                           |
                      LSP over stdio
                           v
                    +---------------+
                    |   server.py   |
                    | protocol/cache|
                    +-------+-------+
                            |
              +-------------+-------------+
              |                           |
              v                           v
       Native feature providers       Document lifecycle
   diagnostics/completion/hover/     open/change/save/close
   formatting/symbols/code actions          |
              |                             |
              +-------------+---------------+
                            v
                    +---------------+
                    | Shared boundary|
                    | workspace.py  |
                    +-------+-------+
                            |
         +------------------+------------------+
         |                  |                  |
         v                  v                  v
      Parsers            INCAR schema       Rule catalog
 INCAR/POSCAR/          official Wiki       semantic and
 KPOINTS/POTCAR/         metadata             runtime rules
 VASP logs

                 Agent and automation clients
                            |
                            v
       tool.py -> DiagnosticEnvelope/v1 or PLAN24
                            ^
                            |
       agent_lsp.py -> compatibility wrapper
```

The providers and adapters use the same document-kind policy. This prevents
the editor and CLI from disagreeing about whether a file is an INCAR,
CONTCAR, POTCAR, or runtime log.

## Runtime components

### `server.py`: native LSP boundary

`server.py` owns the pygls server, protocol handlers, document cache, version
ordering, and diagnostic publication. It advertises completion, hover,
formatting, document symbols, code actions, definition, references, rename,
workspace symbols, and execute-command capabilities.

The advertised capability is not a promise that every provider is
workspace-wide. Navigation scope is documented separately below. In
particular, the server cache is the source of truth for open-buffer navigation,
not a recursive filesystem index.

### Feature providers

The `features/` package contains the editor-facing providers:

- `diagnostics.py` validates syntax, schema values, cross-file consistency,
  semantic rules, and selected runtime-log patterns.
- `completion.py` supplies INCAR names/values and structural suggestions for
  POSCAR and KPOINTS.
- `hover.py` supplies INCAR and structure documentation plus read-only POTCAR
  metadata such as `ENMAX` and `ENMIN`.
- `formatting.py` formats INCAR, POSCAR, and KPOINTS. It does not rewrite
  POTCAR or runtime logs.
- `navigation.py` supplies document symbols and the intentionally limited
  INCAR navigation operations.
- `quickfixes.py` builds code actions from diagnostics and their safe hints.

### Parsers and schema

The parser layer keeps file syntax separate from VASP keyword semantics:

- `INCARParser` parses assignments and typed values.
- `POSCARParser` parses POSCAR and CONTCAR structure data. CONTCAR velocity
  and predictor-corrector sections are treated as legal post-coordinate data.
- `KPOINTSParser` parses automatic, explicit, and line-mode k-point files.
- `POTCARParser` extracts pseudopotential metadata and species order. Names such
  as `H1.25` and `H.75` are compared by their base species where appropriate.
- The runtime-log parser recognizes selected VASP failure patterns without
  claiming to reproduce VASP's complete execution semantics.

The INCAR schema is the validation source of truth for recognized tags. The
checked-in Wiki catalog is audited offline. A tag that is not in the schema is
still an `Error`; the project does not lower unknown-tag severity to conceal a
missing schema entry.

## Calculation workspace

`workspace.py` defines the shared `DocumentKind` and `CalculationWorkspace`
boundary. A workspace is the directory containing the anchor document, not an
unbounded project-wide index.

When a diagnostic needs a neighbor, resolution follows this order:

1. An open, unsaved buffer overlay in the same calculation directory.
2. The corresponding file on disk in that directory.
3. No evidence if neither exists.

The workspace recognizes exact VASP names and safe filename variants such as
`INCAR.relax`, `POSCAR.final`, and `CONTCAR`. `POTCAR.spec` is deliberately not
classified as a POTCAR document because it is VASPKIT metadata rather than the
VASP pseudopotential file itself. Binary restart files such as `WAVECAR` and
`CHGCAR` are checked for existence without being loaded as text.

The CLI uses the same policy. A single-file operation loads small neighboring
input files for context; a directory check scans recognized input documents
and selected runtime logs while avoiding large calculation artifacts. The
editor and CLI therefore agree on the important precedence rule: unsaved input
wins over stale disk content.

## Document coverage

| Document kind | Parse/diagnose | Completion/hover | Formatting | Cross-file role |
| --- | --- | --- | --- | --- |
| `INCAR` | Full schema, type, range, and semantic checks | Full INCAR keyword/value support | Yes | Anchor for POSCAR, KPOINTS, POTCAR, restart, and rule checks |
| `POSCAR` | Structure and coordinate checks | Structural hover/completion | Yes | Species/count evidence; can be compared with POTCAR |
| `CONTCAR` | POSCAR parser plus legal velocity/MD sections | POSCAR-style structural support | POSCAR-style formatting | Structure evidence when POSCAR is absent; POTCAR comparison |
| `KPOINTS` | Grid, explicit, and line-mode checks | Structural hover/completion | Yes | KPOINTS/INCAR smearing and charge-mode checks |
| `POTCAR` | Species and selected metadata checks | Read-only metadata hover | No | Species order, functional, ENMAX/ENMIN evidence |
| VASP runtime log | Selected failure-pattern diagnostics | No input completion | No | Runtime evidence for `vasp-lsp-explain` and directory checks |

`POTCAR` metadata is not added to INCAR completion: `ENMAX` and `ENMIN` are
read-only values from the pseudopotential file, not INCAR keywords.

## Navigation scope

Navigation is deliberately split into core document navigation and
open-buffer-only experiments:

| LSP operation | Implementation scope | Contract status |
| --- | --- | --- |
| `textDocument/documentSymbol` | Current INCAR, POSCAR/CONTCAR, or KPOINTS document | Core editor feature |
| `textDocument/definition` | First matching INCAR assignment in the current document | Experimental navigation |
| `textDocument/references` | Matching INCAR assignments in the current document | Experimental navigation |
| `workspace/symbol` | INCAR symbols from documents currently cached as open | Experimental, open-buffer only |
| `textDocument/prepareRename` / `rename` | Matching INCAR assignments in cached open buffers | Experimental, open-buffer only |

`rename` returns a `WorkspaceEdit`, but the edit set is built from
`server.documents`, not from a disk walk. Closing a buffer removes it from this
scope. Therefore the implementation must not be described as workspace-wide
rename, safe repository-wide rename, or a complete references index.

## Agent-facing interfaces

### Primary CLI path

`tool.py` exposes two families of commands:

- `vasp-lsp-tool` provides single-file operations such as `check`, `context`,
  `complete`, `hover`, `symbols`, and `fix`, plus schema/rule catalog commands.
- `vasp-lsp-check` checks a file or calculation directory and
  `vasp-lsp-explain` analyzes one or more runtime logs.

These commands have different JSON envelopes by design:

| Envelope | Commands | Shape and purpose |
| --- | --- | --- |
| `DiagnosticEnvelope/v1` | `vasp-lsp-tool check/context/complete/hover/symbols/fix` | `operation`, `uri`, `diagnostics`, `summary`, and a `capabilities` block; suitable for one operation at a time |
| `vasp-lsp.plan24.v1` | `vasp-lsp-check`, `vasp-lsp-explain` | `schema_version`, `source`, `diagnostics`, `summary`; suitable for file sets, calculation directories, and runtime logs |

The diagnostic items share rich fields such as stable codes, severity,
category, confidence, source, range, references, hints, and blocking status,
but the top-level envelopes must not be mixed. A caller should dispatch on
`schema_version` or `capabilities.operation`.

### Generic fallback behavior

The agent operation adapter looks for optional module-level provider hooks. If
one is not available, it returns deterministic generic results:

- completion falls back to assignment symbols and diagnostic hints;
- symbols fall back to section/assignment extraction;
- hover falls back to diagnostics and manual references;
- fixes fall back to diagnostic fix hints.

This behavior keeps automation useful when a rich provider is unavailable, but
it is not the same as invoking the native `CompletionProvider` or
`HoverProvider`. The payload reports the operation status and source so an
agent can distinguish a provider result from a generic fallback.

### `AgentLSP` compatibility wrapper

`vasp_lsp.agent_lsp.AgentLSP` is retained for existing Python integrations. It
supports text/path construction and delegates to the agent operation and
diagnostic helpers. It is a compatibility wrapper, not a separate server, and
it inherits the same generic fallback and file-scope limits.

New integrations should use the native `vasp-lsp --stdio` protocol or the
documented CLI commands. The wrapper remains in the repository so existing
callers are not broken; its presence is not a recommendation to build new
integrations against a legacy Python API.

## Optional VASP dry-run

The native server advertises `workspace/executeCommand` with
`vasp-lsp.validate`. This is an explicit, editor-triggered operation:

1. The document must be open in the server.
2. The client supplies a VASP binary path or the server reads
   `VASP_BINARY`/`VASP_LSP_VASP_BINARY`.
3. The server writes a temporary input and invokes the binary with
   `--dry-run`.
4. stdout/stderr are converted into structured diagnostics.

Static diagnostics and agent CLI checks do not run VASP implicitly. The
`vasp-lsp-tool` command family has no `validate` operation.

## Extension guidance

When adding a supported document or provider, update the canonical document
classification and the relevant capability manifest together. Keep these
boundaries explicit:

- schema metadata comes from the checked-in official Wiki catalog or a reviewed
  local overlay;
- cross-file evidence must state which neighbor files were available;
- runtime-log rules must identify the observed log pattern;
- unknown INCAR tags remain errors until the schema is actually expanded;
- a feature that only sees open buffers must be documented as open-buffer-only.

This keeps editor behavior, agent behavior, and documentation aligned without
making the LSP promise a full VASP execution model or a repository index.
