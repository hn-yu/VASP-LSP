# Architecture

## Overview

VASP-LSP is a Language Server Protocol (LSP) implementation for VASP input files. It provides intelligent code editing features for:
- INCAR - Input parameters
- POSCAR - Structure files
- KPOINTS - K-point grids

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      Editor (VSCode, Neovim, etc.)         │
└────────────────────────┬────────────────────────────────────┘
                         │ LSP (stdio/TCP)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                     VASP-LSP Server                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Completion  │  │    Hover    │  │ Diagnostics │         │
│  │  Provider   │  │  Provider   │  │  Provider   │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│         │                │                │                │
│         └────────────────┼────────────────┘                │
│                          ▼                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    Parsers                          │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │   │
│  │  │  INCAR   │  │  POSCAR  │  │  KPOINTS │          │   │
│  │  │  Parser  │  │  Parser  │  │  Parser  │          │   │
│  │  └──────────┘  └──────────┘  └──────────┘          │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    Schemas                          │   │
│  │              (VASP Parameter Data)                  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Components

### Server (`server.py`)

The main LSP server that handles protocol messages:
- Initialize: Server capabilities advertisement
- Text document sync: Document open/change/save events
- Completion: Autocomplete requests
- Hover: Documentation on hover
- Diagnostics: Error/warning reporting

### Parsers

#### INCAR Parser
Parses key-value pairs from INCAR files:
- Handles various value types (int, float, bool, array)
- Case-insensitive tag names
- Comment handling
- Error recovery

#### POSCAR Parser
Parses crystal structure files:
- Lattice vectors
- Atom types and counts
- Coordinate parsing (Direct/Cartesian)
- Selective dynamics flags

#### KPOINTS Parser
Parses k-point specifications:
- Automatic mode
- Gamma/Monkhorst-Pack grids
- Explicit k-point lists
- Line mode for band structures

### Features

#### Completion Provider
- Tag name completion for INCAR
- Enum value suggestions
- Context-aware snippets

#### Hover Provider
- Parameter documentation
- Line-specific help for POSCAR/KPOINTS

#### Diagnostics Provider
- Parse error detection
- Unknown tag warnings
- Parameter validation
- Dependency checking

### Schemas

Parameter metadata for validation and documentation:
- Tag names
- Value types
- Defaults
- Valid ranges
- Enum values
- Dependencies

## Data Flow

### Document Open
1. Editor sends `textDocument/didOpen`
2. Server caches document content
3. Parser validates content
4. Diagnostics published

### Completion Request
1. Editor sends `textDocument/completion`
2. Server determines file type from URI
3. Provider generates suggestions based on cursor position
4. Completions returned to editor

### Hover Request
1. Editor sends `textDocument/hover`
2. Server extracts word at cursor position
3. Provider looks up documentation
4. Hover info returned to editor

## Extension Points

To add new VASP parameters:

1. Edit `src/vasp_lsp/schemas/incar_tags.py`
2. Add new `INCARTag` entry to `INCAR_TAGS` dict
3. Restart server

Example:
```python
"NEW_TAG": INCARTag(
    name="NEW_TAG",
    type="integer",
    default=0,
    description="Description of the parameter",
    category="electronic",
    enum_values=["0", "1", "2"],
),
```
