# VASP-LSP Validation Contract

This document describes the supported diagnostics and validations for each VASP file type, as well as explicitly unsupported or partially supported scenarios.

The contract is static and evidence-based. It does not run VASP during normal
LSP diagnostics. When a cross-file check needs a neighbor, an unsaved open
buffer is preferred over the same file on disk in the calculation directory.
Unknown INCAR tags remain `Error`; schema incompleteness is fixed by adding
reviewed metadata rather than by weakening that severity.

Severity has the following meaning:

- **Error**: high-confidence syntax, schema, or type/value failure likely to
  make the input unusable.
- **Warning**: suspicious or high-risk configuration that may still be
  intentional.
- **Information/Hint**: advisory documentation, style, or convergence context.

## POSCAR Diagnostics (Supported)

| Check | Severity | Scope |
|-------|----------|-------|
| Invalid scale factor | Error | Line 2 |
| Invalid lattice vector | Error | Lines 3-5 |
| Missing atom types or counts | Error | Line 6/7 |
| Negative atom counts | Error | Line 6/7 |
| Type/count mismatch | Error | Line 6/7 |
| Unknown coordinate type | Error | Coord-type line |
| Invalid coordinate values | Error | Coordinate rows |
| Invalid selective dynamics flags | Error | Coordinate rows |
| Extra coordinate rows | Warning | After expected rows |
| Negative scale factor | Warning | Line 2 |
| Zero atom count (empty structure) | Error | Atom counts line |
| Zero-length lattice vector | Error | Lines 3-5 |
| Linearly dependent lattice (zero volume) | Error | Lines 3-5 |
| Invalid element symbols | Warning | Atom types line |
| Direct coordinates outside [0, 1] | Information | Coordinate rows |
| Extreme scale factor magnitude (<0.01 or >100) | Warning | Line 2 |
| Nearly degenerate lattice angles (<10 or >170 deg) | Warning | Lines 3-5 |
| Coordinate count mismatch vs atom counts | Error | Coordinate rows |
| Duplicate atom positions (within 1e-6 tolerance) | Warning | Coordinate rows |
| Very close atoms (<0.5 Angstrom) | Warning | Coordinate rows |

### POSCAR Source Spans

Diagnostics use exact line indices from the parser when available:
- Scale factor warnings target the actual scale factor line.
- Atom count warnings target the actual atom counts line.
- Direct coordinate range warnings target the exact coordinate row.
- Lattice vector warnings target the exact vector line.

### POSCAR Edge Cases Handled

- **Selective dynamics**: The `S` (or `Selective dynamics`) line shifts all subsequent line indices by 1. The parser records `has_selective_dynamics` and adjusts `coordinate_start_line` accordingly.
- **Cartesian vs Direct**: Different range thresholds apply. Direct coordinates are checked against [0, 1] (with tolerance to -0.5/1.5). Cartesian coordinates are not range-checked but close-atom distances use Cartesian distances directly.
- **VASP 4 format** (no atom types line): Parser generates generic `TypeN` names. Element symbol validation is skipped for these.
- **Multiple species**: Atom type/count length mismatch is detected.
- **CONTCAR post-coordinate data**: Legal velocity and molecular-dynamics
  predictor-corrector sections are accepted. Unseparated numeric rows that do
  not fit a recognized optional section remain diagnosable.

### POSCAR Limitations (Unsupported)

- No validation of lattice vector physical plausibility beyond linear dependence.
- No check for atom positions outside the unit cell for Cartesian coordinates.
- No cell shape symmetry analysis.
- No validation of lattice vector units (assumes Angstrom).

## KPOINTS Diagnostics (Supported)

| Check | Severity | Scope |
|-------|----------|-------|
| File too short | Error | File-level |
| Invalid k-point specification | Error | Line 2 |
| Automatic mode: missing grid values | Error | Grid line |
| Gamma/Monkhorst mode: missing grid values | Error | Grid line |
| Explicit mode: fewer than 4 values per k-point | Error | K-point rows |
| Non-positive grid values (<=0) | Error | Grid line |
| Very sparse grid (all values < 2) | Information | Grid line |
| Very dense grid (all values > 50) | Warning | Grid line |
| Zero-weight k-points | Warning | K-point rows |
| K-point coordinates outside [-1, 1] | Error | K-point rows |
| Weights not summing to ~1.0 | Information | K-point section |
| Line-mode density < 10 | Information | Line-density line |
| Gamma/Monkhorst centering hint | Information | Grid line |

### KPOINTS Source Spans

Diagnostics use exact line indices from the parser:
- Grid warnings target the actual grid line (`grid_line_idx`).
- Zero-weight k-point warnings target the exact k-point row.
- Out-of-range coordinate errors target the exact k-point row with the coordinate string length.

### KPOINTS Edge Cases Handled

- **Fully automatic mode** (`A` or `Automatic` on line 2): Parsed with `_parse_automatic_mode`.
- **Gamma-centered vs Monkhorst-Pack**: Both produce grid and shift data with a centering hint.
- **Explicit k-points with weights**: Weight sum and zero-weight checks apply.
- **Line mode**: Density check applies. Band-path endpoints are extracted but not validated for physical consistency.

### KPOINTS Limitations (Unsupported)

- No cross-referencing of k-point density against cell size (requires POSCAR).
- No validation of band-path connectivity in line mode.
- No check for tetragonal/hexagonal-specific k-point grids.
- No validation of explicit k-point coordinates against Brillouin zone boundaries.

## Cross-File Diagnostics

Cross-file consistency checks run from the relevant input provider when the
calculation neighbors are available. INCAR is the main semantic anchor, while
POSCAR/CONTCAR and POTCAR can also report their own species consistency
diagnostics. Open buffers override disk content for the same neighbor.

| Check | Severity | Files |
|-------|----------|-------|
| MAGMOM count vs POSCAR atom count | Warning | INCAR + POSCAR |
| LDAU parameter count vs POSCAR species count | Warning | INCAR + POSCAR |
| KSPACING + KPOINTS file conflict | Warning | INCAR + KPOINTS |
| POSCAR/POTCAR species order mismatch | Warning | INCAR + POSCAR + POTCAR |
| POSCAR/POTCAR species-count mismatch | Warning | POSCAR/CONTCAR + POTCAR |
| POTCAR parser failure | Error | POTCAR |
| ENCUT below max POTCAR ENMAX | Warning | INCAR + POTCAR |
| POTCAR functional mixing | Warning | INCAR + POTCAR |
| ENCUT below 1.3 × max POTCAR ENMAX recommendation | Information | INCAR + POTCAR |
| ICHARG=1/11 without CHGCAR | Information | INCAR + CHGCAR |
| Line-mode KPOINTS without ICHARG=11/12 | Information | INCAR + KPOINTS |
| MDALGO outside effective molecular-dynamics mode | Warning | INCAR |
| IBRION/NSW/POTIM/SMASS consistency | Warning/Error/Information | INCAR |
| LSORBIT/LNONCOLLINEAR with ISPIN=2 | Warning | INCAR |

POTCAR comparison preserves the complete species sequence and count. Hydrogen
like titles such as `H1.25` and `H.75` are compared using their base species
`H`, while their order remains significant. POSCAR VASP 4 placeholder names
such as `Type1` are not treated as chemical symbols for a false mismatch. A
POTCAR parse failure is reported separately instead of being relabeled as an
order mismatch. `POTCAR.spec` is not used as POTCAR evidence.

## VASP runtime-log diagnostics

The runtime-log parser is a focused pattern detector, not a complete parser of
all VASP output. It can report selected high-confidence failures, including:

| Check | Severity | Sources |
| --- | --- | --- |
| Symmetry-analysis failure (`INVGRP`, `PRICEL`, `SGRCON`, `SGRGEN`) | Error | OUTCAR/stdout/stderr/Slurm capture |
| Electronic-minimization failure (`EDDDAV`, `EDDRMM`, `PSSYEVX`, `ZPOTRF`) | Error | OUTCAR/stdout/stderr/Slurm capture |

Use `vasp-lsp-explain` for an explicit log explanation. Directory checks also
visit recognized runtime-log names but avoid loading large binary artifacts such
as WAVECAR and CHGCAR as text.

## Cross-File Limitations (Unsupported)

- No validation of KPOINTS grid density against POSCAR cell dimensions.
- No validation of POTCAR-specific flavor compatibility beyond species order
  and count, parser errors, functional mixing, and ENMAX/ENMIN metadata.
- No KPOINTS grid-density recommendation derived from the reciprocal lattice.
- No spin-orbit axis recommendation: SAXIS has an official default, so the
  server does not invent a mandatory SAXIS requirement.
- No complete VASP runtime-log interpretation or guarantee that a run is
  scientifically converged.

## JSON validation surfaces

The static CLI exposes two top-level envelopes. `vasp-lsp-tool` operation
payloads use `DiagnosticEnvelope/v1` with `operation`, `uri`, `diagnostics`,
`summary`, and `capabilities`. `vasp-lsp-check` and `vasp-lsp-explain` use
`vasp-lsp.plan24.v1` with `schema_version`, `source`, `diagnostics`, and
`summary`. They share diagnostic concepts but are separate contracts; clients
must dispatch on the envelope identifier.
