"""VASP INCAR tag definitions with metadata.

This module contains structured metadata for VASP INCAR parameters,
enabling autocomplete, validation, and documentation features.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, cast

from .incar_wiki_tags import OFFICIAL_WIKI_TAGS


@dataclass
class INCARTag:
    """Metadata for a single INCAR tag."""

    name: str
    # "unknown" means the official Wiki confirms the tag, but its TAGDEF
    # notation was not unambiguous enough for safe local type validation.
    type: str  # "integer", "float", "boolean", "string", "array", "unknown"
    default: Any
    description: str
    category: str  # "electronic", "ionic", "parallel", "output", etc.
    valid_range: Optional[tuple] = None
    enum_values: Optional[List[str]] = None
    requires: Optional[List[str]] = None  # Related tags that should be set
    conflicts_with: Optional[List[str]] = None  # Tags that conflict with this one
    version_note: Optional[str] = None  # Version-specific notes
    unit: Optional[str] = None  # e.g. "eV", "eV/Å", "Å", "fs", "Å⁻¹"
    case_sensitive: bool = False  # Whether string enum values are case-sensitive
    source_url: Optional[str] = None  # Official documentation source, when available

    def to_markdown(self) -> str:
        """Generate markdown documentation for this tag."""
        # Keep the raw official Wiki URL on its own first line. Neovim's hover
        # window can then copy just the URL with `yy`, without copying a
        # Markdown label or the surrounding documentation.
        lines = []
        if self.source_url:
            lines.extend([self.source_url, ""])
        lines.extend([f"### {self.name}", ""])
        lines.append(f"**Type:** {self.type}")
        lines.append(f"**Default:** {self.default}")
        lines.append(f"**Category:** {self.category}")
        if self.valid_range:
            lines.append(f"**Range:** {self.valid_range[0]} to {self.valid_range[1]}")
        if self.enum_values:
            lines.append(f"**Allowed values:** {', '.join(self.enum_values)}")
        lines.append("")
        lines.append(self.description)
        if self.requires:
            lines.append("")
            lines.append(f"**Related tags:** {', '.join(self.requires)}")
        if self.conflicts_with:
            lines.append("")
            lines.append(f"**Conflicts with:** {', '.join(self.conflicts_with)}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Calculation-mode definitions (#21 required-sections)
# ---------------------------------------------------------------------------


@dataclass
class CalculationMode:
    """A VASP calculation mode with its required and recommended tags."""

    name: str
    description: str
    required_tags: List[str] = field(default_factory=list)
    recommended_tags: List[str] = field(default_factory=list)
    detector_tags: Dict[str, Any] = field(default_factory=dict)
    """Tag-value pairs that, when present, indicate this mode."""


CALCULATION_MODES: List[CalculationMode] = [
    CalculationMode(
        name="relaxation",
        description="Structural relaxation (ionic minimization)",
        required_tags=["IBRION", "NSW", "EDIFFG"],
        recommended_tags=["ISIF", "POTIM", "EDIFF", "ENCUT"],
        detector_tags={"IBRION": [1, 2], "NSW": None},
    ),
    CalculationMode(
        name="molecular_dynamics",
        description="Molecular dynamics simulation",
        required_tags=["IBRION", "NSW", "POTIM"],
        recommended_tags=["SMASS", "TEBEG", "TEEND"],
        detector_tags={"IBRION": [0], "NSW": None},
    ),
    CalculationMode(
        name="static",
        description="Static (single-point) calculation",
        required_tags=[],
        recommended_tags=["ENCUT", "EDIFF"],
        detector_tags={"NSW": [0], "IBRION": [-1]},
    ),
    CalculationMode(
        name="band_structure",
        description="Band structure calculation (non-self-consistent)",
        required_tags=["ICHARG"],
        recommended_tags=["LORBIT", "NBANDS"],
        detector_tags={"ICHARG": [11, 12]},
    ),
    CalculationMode(
        name="phonon",
        description="Phonon / finite-difference calculation",
        required_tags=["IBRION", "POTIM"],
        recommended_tags=["EDIFF", "ENCUT", "NSW"],
        detector_tags={"IBRION": [5, 6, 7, 8]},
    ),
    CalculationMode(
        name="hybrid",
        description="Hybrid functional calculation",
        required_tags=["LHFCALC"],
        recommended_tags=["HFSCREEN", "PRECFOCK", "ALGO", "NCORE"],
        detector_tags={"LHFCALC": [True]},
    ),
    CalculationMode(
        name="dft_u",
        description="DFT+U calculation",
        required_tags=["LDAU", "LDAUTYPE", "LDAUL", "LDAUU"],
        recommended_tags=["LDAUJ"],
        detector_tags={"LDAU": [True]},
    ),
]


# INCAR tag definitions
INCAR_TAGS: Dict[str, INCARTag] = {
    # Electronic structure
    "ENCUT": INCARTag(
        name="ENCUT",
        type="float",
        default=None,
        description="Cutoff energy for the plane-wave basis set in eV. If not specified, VASP uses the maximum ENMAX from POTCAR files.",
        category="electronic",
        valid_range=(0.0, None),
        unit="eV",
    ),
    "ISMEAR": INCARTag(
        name="ISMEAR",
        type="integer",
        default=1,
        description=(
            "Determines how the partial occupancies are set for each orbital. "
            "The documented discrete values are -15, -14, -5, -4, -3, -2, "
            "-1, and 0; every positive integer selects Methfessel-Paxton "
            "smearing of that order."
        ),
        category="electronic",
        enum_values=["-15", "-14", "-5", "-4", "-3", "-2", "-1", "0"],
        valid_range=(1, None),
        source_url="https://vasp.at/wiki/ISMEAR",
    ),
    "SIGMA": INCARTag(
        name="SIGMA",
        type="float",
        default=0.2,
        description="Width of the smearing in eV. Default depends on ISMEAR. For ISMEAR >= 0, SIGMA determines the width of the smearing.",
        category="electronic",
        valid_range=(0.0, None),
        requires=["ISMEAR"],
        unit="eV",
    ),
    "EDIFF": INCARTag(
        name="EDIFF",
        type="float",
        default=1e-4,
        description="Convergence criterion for electronic self-consistency. The relaxation stops when the total energy change between two steps is smaller than EDIFF.",
        category="electronic",
        valid_range=(0.0, None),
        unit="eV",
    ),
    "NELM": INCARTag(
        name="NELM",
        type="integer",
        default=60,
        description="Maximum number of electronic self-consistency steps.",
        category="electronic",
        valid_range=(1, None),
    ),
    "NELMIN": INCARTag(
        name="NELMIN",
        type="integer",
        default=2,
        description="Minimum number of electronic self-consistency steps.",
        category="electronic",
        valid_range=(1, None),
    ),
    "NELMDL": INCARTag(
        name="NELMDL",
        type="integer",
        default=None,
        description=(
            "Number of non-self-consistent electronic steps at the beginning. "
            "The default is conditional on ISTART, INIWAV, IALGO, and whether a WAVECAR is present."
        ),
        category="electronic",
        version_note=(
            "VASP.6 allows positive NELMDL values for delays after ionic movements; "
            "the recommended behavior depends on ALGO and the VASP version."
        ),
    ),
    "IALGO": INCARTag(
        name="IALGO",
        type="integer",
        default=None,
        description=(
            "Selects the algorithm used to optimize the orbitals. Allowed values are "
            "-1, 2-4, 5-8, 15-18, 28, 38, 44-48, and 53-58."
        ),
        category="electronic",
        enum_values=[
            "-1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
            "15",
            "16",
            "17",
            "18",
            "28",
            "38",
            "44",
            "45",
            "46",
            "47",
            "48",
            "53",
            "54",
            "55",
            "56",
            "57",
            "58",
        ],
        version_note=(
            "The VASP Wiki recommends selecting algorithms through ALGO; several older "
            "IALGO algorithms are deprecated or unsupported in VASP.5 and newer."
        ),
    ),
    "ALGO": INCARTag(
        name="ALGO",
        type="string",
        default="Normal",
        description=(
            "Selects the electronic-minimization algorithm or many-body method. "
            "For the ordinary self-consistency-cycle algorithms, VASP also accepts "
            "the documented first-letter form (for example V for VeryFast)."
        ),
        category="electronic",
        enum_values=[
            "Normal",
            "N",
            "Fast",
            "F",
            "VeryFast",
            "V",
            "All",
            "A",
            "Conjugate",
            "C",
            "Damped",
            "D",
            "Subrot",
            "S",
            "Eigenval",
            "None",
            "Nothing",
            "Exact",
            "CHI",
            "TDHF",
            "Timeev",
            "ACFDT",
            "RPA",
            "RPAR",
            "ACFDTR",
            "ACFDTRK",
            "CRPA",
            "EVGW0",
            "EVGW",
            "QPGW0",
            "QPGW",
            "GW0R",
            "GWR",
            "G0W0R",
            "G0W0",
            "EVGW0R",
            "BSE",
            "GW",
            "GW0",
            "Old Fast",
            "Old VeryFast",
            "of",
            "fo",
            "ov",
            "vo",
            # VASP versions before 6 use these names for related GW methods.
            "scGW0",
            "scGW",
        ],
        case_sensitive=True,
        version_note=(
            "The official VASP Wiki documents Normal, Fast, VeryFast, All/Conjugate, "
            "Damped, Subrot, Eigenval, None/Nothing, Exact, response-function methods, "
            "and version-specific GW/RPA names."
        ),
        source_url="https://vasp.at/wiki/ALGO",
    ),
    "ISPIN": INCARTag(
        name="ISPIN",
        type="integer",
        default=1,
        description="Spin polarization: 1 = non-spin polarized, 2 = spin-polarized (collinear).",
        category="electronic",
        enum_values=["1", "2"],
    ),
    "MAGMOM": INCARTag(
        name="MAGMOM",
        type="array",
        default=None,
        description="Initial magnetic moments for each atom. Format: MAGMOM = m1 m2 m3 ... (one per atom) or MAGMOM = m1*m2*m3 (for ISPIN=2, multiple values per atom).",
        category="electronic",
        requires=["ISPIN"],
    ),
    "LORBIT": INCARTag(
        name="LORBIT",
        type="integer",
        default=0,
        description="Determines whether the PROCAR or PROOUT files are written and the format of the file. 0: no output, 1: simple output, 2: detailed output, 5: simple output + phase, 10: time-dependent DFT, 11: like 1 + phase information, 12: like 2 + phase information.",
        category="output",
        enum_values=["0", "1", "2", "5", "10", "11", "12"],
        source_url="https://vasp.at/wiki/LORBIT",
    ),
    "ADDGRID": INCARTag(
        name="ADDGRID",
        type="boolean",
        default=False,
        description=(
            "Determines whether an additional support grid is used for evaluating "
            "the augmentation charges."
        ),
        category="accuracy",
        version_note=(
            "The VASP Wiki recommends testing this setting carefully rather than using "
            "it by default in every calculation."
        ),
    ),
    "LASPH": INCARTag(
        name="LASPH",
        type="boolean",
        default=False,
        description=(
            "Includes non-spherical contributions related to the gradient of the "
            "density inside the PAW spheres."
        ),
        category="exchange-correlation",
        version_note=(
            "In VASP.5 and newer, the aspherical contributions are included in the "
            "Kohn-Sham potential when LASPH=.TRUE."
        ),
        source_url="https://vasp.at/wiki/LASPH",
    ),
    "LMAXMIX": INCARTag(
        name="LMAXMIX",
        type="integer",
        default=2,
        description=(
            "Controls the maximum l-quantum number of one-center PAW charge-density "
            "components passed through the density mixer and written to CHGCAR."
        ),
        category="mixing",
    ),
    "LMIXTAU": INCARTag(
        name="LMIXTAU",
        type="boolean",
        default=False,
        description=(
            "Determines whether the kinetic-energy density is passed through the "
            "density mixer as well."
        ),
        category="mixing",
    ),
    "NEDOS": INCARTag(
        name="NEDOS",
        type="integer",
        default=301,
        description="Number of grid points on which the DOS is calculated.",
        category="output",
        valid_range=(1, None),
    ),
    # Ionic relaxation
    "IBRION": INCARTag(
        name="IBRION",
        type="integer",
        default=None,
        description=(
            "Determines how the ions are updated and moved. -1: no update, "
            "0: molecular dynamics, 1: RMM-DIIS, 2: conjugate gradient, "
            "3: damped molecular dynamics, 5-8: phonons, 11: interactive "
            "standard-input updates, 12: Python-plugin updates, 40: intrinsic "
            "reaction coordinate, and 44: improved dimer method."
        ),
        category="ionic",
        enum_values=[
            "-1",
            "0",
            "1",
            "2",
            "3",
            "5",
            "6",
            "7",
            "8",
            "11",
            "12",
            "40",
            "44",
        ],
        source_url="https://vasp.at/wiki/IBRION",
    ),
    "NSW": INCARTag(
        name="NSW",
        type="integer",
        default=0,
        description="Maximum number of ionic steps. For IBRION=0 (MD), this is the number of MD steps.",
        category="ionic",
        valid_range=(0, None),
    ),
    "EDIFFG": INCARTag(
        name="EDIFFG",
        type="float",
        default=None,
        description="Convergence criterion for ionic relaxation. If EDIFFG < 0, relaxation stops when all forces are smaller than |EDIFFG| in eV/Å. If EDIFFG > 0, relaxation stops when the energy change is smaller than EDIFFG in eV.",
        category="ionic",
        unit="eV (if positive) or eV/Å (if negative)",
        source_url="https://vasp.at/wiki/EDIFFG",
    ),
    "POTIM": INCARTag(
        name="POTIM",
        type="float",
        default=None,
        description="Scaling factor for the forces or time step for MD. For IBRION=2: trial step size for translation. For IBRION=1: step width scaling. For IBRION=0: time step in fs.",
        category="ionic",
        valid_range=(0.0, None),
        unit="fs (for MD) or Å (for relaxation)",
    ),
    "ISIF": INCARTag(
        name="ISIF",
        type="integer",
        default=None,
        description="Controls whether the stress tensor is calculated and which degrees of freedom are allowed to change. Values 0-8 select the documented combinations of forces/stress, ionic positions, cell shape, and cell volume; ISIF=8 is available since VASP.6.4.1.",
        category="ionic",
        enum_values=["0", "1", "2", "3", "4", "5", "6", "7", "8"],
        version_note="ISIF=8 is available since VASP.6.4.1; the default is conditional on IBRION and LHFCALC.",
        source_url="https://vasp.at/wiki/ISIF",
    ),
    # Symmetry
    "ISYM": INCARTag(
        name="ISYM",
        type="integer",
        default=None,
        description=(
            "Determines how VASP treats symmetry. Values -1 and 0 switch symmetry "
            "off; values 1, 2, and 3 enable the corresponding symmetry treatments. "
            "The default depends on the pseudopotential and whether LHFCALC is enabled."
        ),
        category="symmetry",
        enum_values=["-1", "0", "1", "2", "3"],
        source_url="https://vasp.at/wiki/ISYM",
    ),
    "SYMPREC": INCARTag(
        name="SYMPREC",
        type="float",
        default=1e-5,
        description=(
            "Determines the positional accuracy used when identifying equivalent "
            "atomic positions during symmetry analysis."
        ),
        category="symmetry",
        version_note="Available since VASP.4.4.4 according to the VASP Wiki.",
    ),
    # K-points
    "KGAMMA": INCARTag(
        name="KGAMMA",
        type="boolean",
        default=False,
        description="If .TRUE., the k-point grid includes the Gamma point. Only relevant for Monkhorst-Pack grids.",
        category="electronic",
    ),
    "KSPACING": INCARTag(
        name="KSPACING",
        type="float",
        default=0.5,
        description="Generate an automatic k-point mesh from a target reciprocal-space spacing. Do not use together with an explicit KPOINTS file.",
        category="electronic",
        valid_range=(0.0, None),
        unit="Å⁻¹",
        source_url="https://vasp.at/wiki/KSPACING",
    ),
    # Parallelization
    "NCORE": INCARTag(
        name="NCORE",
        type="integer",
        default=1,
        description="Number of cores per orbital that work on an individual orbital. NCORE determines the number of compute cores working on an individual orbital.",
        category="parallel",
        valid_range=(1, None),
    ),
    "NPAR": INCARTag(
        name="NPAR",
        type="integer",
        default=None,
        description="Determines the number of bands treated in parallel. NPAR determines the number of parallel band groups. If not set, VASP attempts to determine it automatically.",
        category="parallel",
        valid_range=(1, None),
        conflicts_with=["NCORE"],
    ),
    "KPAR": INCARTag(
        name="KPAR",
        type="integer",
        default=1,
        description="Parallelization over k-points. KPAR determines the number of k-point groups that are solved in parallel.",
        category="parallel",
        valid_range=(1, None),
    ),
    # Output control
    "LWAVE": INCARTag(
        name="LWAVE",
        type="boolean",
        default=True,
        description="Determines whether the wavefunctions are written to the WAVECAR file.",
        category="output",
    ),
    "LCHARG": INCARTag(
        name="LCHARG",
        type="boolean",
        default=True,
        description="Determines whether the charge density is written to the CHGCAR file.",
        category="output",
    ),
    "LAECHG": INCARTag(
        name="LAECHG",
        type="boolean",
        default=False,
        description="Determines whether the all-electron charge density is written to the AECCAR0/AECCAR2 files for Bader analysis.",
        category="output",
    ),
    "LVHAR": INCARTag(
        name="LVHAR",
        type="boolean",
        default=False,
        description="Determines whether the electrostatic potential (Hartree potential) is written to the LOCPOT file.",
        category="output",
    ),
    "LVTOT": INCARTag(
        name="LVTOT",
        type="boolean",
        default=False,
        description="Determines whether the total local potential is written to the LOCPOT file.",
        category="output",
    ),
    "LELF": INCARTag(
        name="LELF",
        type="boolean",
        default=False,
        description="Determines whether the electron localization function (ELF) is written to the ELFCAR file.",
        category="output",
    ),
    "LDIPOL": INCARTag(
        name="LDIPOL",
        type="boolean",
        default=False,
        description=(
            "Switches on corrections to the potential and forces for charged molecules "
            "and slabs with a net dipole moment."
        ),
        category="electrostatics",
        requires=["IDIPOL"],
    ),
    "IDIPOL": INCARTag(
        name="IDIPOL",
        type="integer",
        default=None,
        description=(
            "Selects the direction for monopole, dipole, and quadrupole corrections: "
            "1, 2, or 3 for one lattice direction, or 4 for all directions."
        ),
        category="electrostatics",
        enum_values=["1", "2", "3", "4"],
    ),
    "DIPOL": INCARTag(
        name="DIPOL",
        type="array",
        default=None,
        description=(
            "Specifies the center of the cell in direct lattice coordinates with "
            "respect to which the total dipole moment is calculated."
        ),
        category="electrostatics",
        unit="direct lattice coordinates",
    ),
    "LORBITALREAL": INCARTag(
        name="LORBITALREAL",
        type="boolean",
        default=False,
        description="Determines whether real-space projection operators are used.",
        category="electronic",
    ),
    # Hybrid functionals
    "LHFCALC": INCARTag(
        name="LHFCALC",
        type="boolean",
        default=False,
        description="Determines whether Hartree-Fock type calculations are performed. If set to .TRUE., a hybrid functional calculation is performed.",
        category="electronic",
    ),
    "HFSCREEN": INCARTag(
        name="HFSCREEN",
        type="float",
        default=0.2,
        description="Screening parameter for HSE06 functional in Å⁻¹. Default is 0.2 (HSE06). For HSE03 use 0.3.",
        category="electronic",
        valid_range=(0.0, None),
        requires=["LHFCALC"],
        unit="Å⁻¹",
    ),
    "PRECFOCK": INCARTag(
        name="PRECFOCK",
        type="string",
        default="Normal",
        description="Determines the FFT grid used for the exact exchange (Hartree-Fock) calculations. Options: Low, Medium, Normal, Fast, Accurate.",
        category="electronic",
        enum_values=["Low", "Medium", "Normal", "Fast", "Accurate"],
        requires=["LHFCALC"],
        case_sensitive=True,
        source_url="https://vasp.at/wiki/PRECFOCK",
    ),
    # Van der Waals corrections
    "IVDW": INCARTag(
        name="IVDW",
        type="integer",
        default=0,
        description="Determines the type of van der Waals correction. 0: no correction, 1: DFT-D2, 11: DFT-D3, 12: DFT-D3 with Becke-Johnson damping, 2: TS method, 21: TS with iterative Hirshfeld partitioning, 202: MBD@rsSCS.",
        category="electronic",
        enum_values=["0", "1", "11", "12", "2", "21", "202"],
    ),
    # Exchange-correlation functionals
    "GGA": INCARTag(
        name="GGA",
        type="string",
        default=None,
        description="Selects an LDA or GGA exchange-correlation functional.",
        category="exchange-correlation",
        version_note=(
            "The available functional names depend on the VASP version and compilation "
            "options; see the VASP Wiki for the current list."
        ),
    ),
    "METAGGA": INCARTag(
        name="METAGGA",
        type="string",
        default=None,
        description="Selects a meta-GGA exchange-correlation functional.",
        category="exchange-correlation",
        version_note=(
            "The available meta-GGA functional names and their VASP-version availability "
            "are documented on the VASP Wiki."
        ),
    ),
    "SMASS": INCARTag(
        name="SMASS",
        type="float",
        default=-3,
        description=(
            "Controls the ionic velocities during ab-initio molecular dynamics. "
            "The documented discrete modes are -3, -2, and -1; non-negative real "
            "values select the Nosé mass."
        ),
        category="molecular-dynamics",
        valid_range=(0.0, None),
        enum_values=["-3", "-2", "-1"],
        source_url="https://vasp.at/wiki/SMASS",
    ),
    # DFT+U
    "LDAU": INCARTag(
        name="LDAU",
        type="boolean",
        default=False,
        description="Determines whether the DFT+U calculation is performed (LSDA+U or GGA+U).",
        category="electronic",
    ),
    "LDAUTYPE": INCARTag(
        name="LDAUTYPE",
        type="integer",
        default=2,
        description="Determines the type of DFT+U approach. 1: Liechtenstein, 2: Dudarev (simpler, only Ueff = U - J matters), 4: Liechtenstein with rotationally invariant formulation.",
        category="electronic",
        enum_values=["1", "2", "4"],
        requires=["LDAU"],
    ),
    "LDAUL": INCARTag(
        name="LDAUL",
        type="array",
        default=None,
        description="LDAUL specifies the l-quantum number on which the projection is applied for each species. -1: no U, 0: s, 1: p, 2: d, 3: f.",
        category="electronic",
        requires=["LDAU"],
    ),
    "LDAUU": INCARTag(
        name="LDAUU",
        type="array",
        default=None,
        description="The effective on-site Coulomb interaction parameter Ueff = U - J for each species (in eV).",
        category="electronic",
        requires=["LDAU"],
    ),
    "LDAUJ": INCARTag(
        name="LDAUJ",
        type="array",
        default=None,
        description="The on-site exchange interaction J for each species (in eV). Required by some DFT+U formulations.",
        category="electronic",
        requires=["LDAU"],
    ),
    # Magnetic calculations
    "LSORBIT": INCARTag(
        name="LSORBIT",
        type="boolean",
        default=False,
        description="Determines whether spin-orbit coupling is included. If set to .TRUE., a non-collinear calculation with spin-orbit coupling is performed.",
        category="electronic",
    ),
    "LNONCOLLINEAR": INCARTag(
        name="LNONCOLLINEAR",
        type="boolean",
        default=None,
        description="Switches on noncollinear magnetic calculations.",
        category="magnetism",
        version_note=("Supported since VASP.4.5; the default becomes .TRUE. when LSORBIT=.TRUE."),
        source_url="https://vasp.at/wiki/LNONCOLLINEAR",
    ),
    "NUPDOWN": INCARTag(
        name="NUPDOWN",
        type="float",
        default=None,
        description=(
            "Sets the difference between the numbers of electrons in the up and down "
            "spin components. A specified value fixes the spin multiplet; NUPDOWN=-1 "
            "requests a full relaxation."
        ),
        category="magnetism",
        source_url="https://vasp.at/wiki/NUPDOWN",
    ),
    "SAXIS": INCARTag(
        name="SAXIS",
        type="array",
        default=[0.0, 0.0, 1.0],
        description="Quantization axis for non-collinear spin calculations. SAXIS = sx sy sz defines the direction of the magnetization.",
        category="electronic",
        requires=["LSORBIT"],
    ),
    # Charge mixing
    "AMIX": INCARTag(
        name="AMIX",
        type="float",
        default=0.4,
        description="Linear mixing parameter for the charge density. AMIX determines the mixing amplitude for the charge density.",
        category="electronic",
        valid_range=(0.0, 1.0),
    ),
    "BMIX": INCARTag(
        name="BMIX",
        type="float",
        default=1.0,
        description="Cutoff wave vector for Kerker mixing scheme in Å⁻¹.",
        category="electronic",
        valid_range=(0.0, None),
    ),
    "AMIX_MAG": INCARTag(
        name="AMIX_MAG",
        type="float",
        default=1.6,
        description="Linear mixing parameter for the magnetization density.",
        category="mixing",
    ),
    "BMIX_MAG": INCARTag(
        name="BMIX_MAG",
        type="float",
        default=1.0,
        description=(
            "Sets the cutoff wave vector for the Kerker mixing scheme for the "
            "magnetization density."
        ),
        category="mixing",
    ),
    "MAXMIX": INCARTag(
        name="MAXMIX",
        type="integer",
        default=-45,
        description=(
            "Specifies the maximum number of vectors stored in the Broyden or Pulay "
            "mixer. Negative and positive values select different reset behavior."
        ),
        category="mixing",
        version_note="Available since VASP.4.4 according to the VASP Wiki.",
    ),
    "AMIN": INCARTag(
        name="AMIN",
        type="float",
        default=0.1,
        description="Minimum mixing parameter for the charge density.",
        category="electronic",
        valid_range=(0.0, 1.0),
    ),
    # Other
    "SYSTEM": INCARTag(
        name="SYSTEM",
        type="string",
        default="Unknown",
        description="A description of the calculation. This string is written to the OUTCAR and OSZICAR files.",
        category="general",
    ),
    "NWRITE": INCARTag(
        name="NWRITE",
        type="integer",
        default=2,
        description="Determines the verbosity of the output. 0: minimal, 1: reduced, 2: normal, 3: detailed, 4: extensive.",
        category="output",
        enum_values=["0", "1", "2", "3", "4"],
    ),
    "PREC": INCARTag(
        name="PREC",
        type="string",
        default="Normal",
        description="Determines the precision mode. Normal and Accurate are recommended; Single and SingleN are reduced-memory modes; Low, Medium, and High are deprecated compatibility modes.",
        category="electronic",
        enum_values=["Normal", "Single", "SingleN", "Accurate", "Low", "Medium", "High"],
        case_sensitive=True,
        version_note="Normal and Accurate are available since VASP.4.5; Single is available since VASP.5.1; Low, Medium, and High are deprecated compatibility modes.",
        source_url="https://vasp.at/wiki/PREC",
    ),
    "ISTART": INCARTag(
        name="ISTART",
        type="integer",
        default=None,
        description="Determines whether WAVECAR is read. 0: start from scratch, 1: restart with constant energy cutoff, 2: restart with constant basis set, 3: full restart with orbital and charge prediction.",
        category="electronic",
        enum_values=["0", "1", "2", "3"],
        source_url="https://vasp.at/wiki/ISTART",
    ),
    "ICHARG": INCARTag(
        name="ICHARG",
        type="integer",
        default=None,
        description="Determines how the initial charge density is constructed. The official modes include 0, 1, 2, 4, and 5; adding 10 selects a fixed-density non-self-consistent mode, commonly written as 10, 11, or 12.",
        category="electronic",
        enum_values=["0", "1", "2", "4", "5", "10", "11", "12"],
        source_url="https://vasp.at/wiki/ICHARG",
    ),
    "NBANDS": INCARTag(
        name="NBANDS",
        type="integer",
        default=None,
        description="Number of bands included in the calculation. Default is determined from the number of valence electrons.",
        category="electronic",
        valid_range=(1, None),
    ),
    "NELECT": INCARTag(
        name="NELECT",
        type="float",
        default=None,
        description="Total number of electrons in the system. Can be used to set a different number of electrons than determined from POTCAR.",
        category="electronic",
    ),
    "LREAL": INCARTag(
        name="LREAL",
        type="boolean",
        default=False,
        description="Determines whether the projection operators are evaluated in real space or reciprocal space.",
        category="electronic",
        enum_values=[".FALSE.", ".TRUE.", "Auto", "A", "On", "O"],
        source_url="https://vasp.at/wiki/LREAL",
    ),
    "ROPT": INCARTag(
        name="ROPT",
        type="array",
        default=None,
        description="Optimization of the real-space projection operators. One value per species.",
        category="electronic",
        requires=["LREAL"],
    ),
    "EMIN": INCARTag(
        name="EMIN",
        type="float",
        default=None,
        description="Minimum energy for DOS calculation in eV.",
        category="output",
    ),
    "EMAX": INCARTag(
        name="EMAX",
        type="float",
        default=None,
        description="Maximum energy for DOS calculation in eV.",
        category="output",
    ),
}

# The curated entries above take precedence because they contain reviewed
# project-specific validation metadata. Every remaining official Wiki page is
# still registered, so a documented tag is not reported as unknown; records
# with type="unknown" intentionally skip value validation until their Wiki
# TAGDEF can be interpreted without guessing.
for _wiki_tag_name, _wiki_tag_metadata in OFFICIAL_WIKI_TAGS.items():
    if _wiki_tag_name not in INCAR_TAGS:
        INCAR_TAGS[_wiki_tag_name] = INCARTag(**cast(Dict[str, Any], _wiki_tag_metadata))

# Curated entries retain their richer descriptions and cross-tag metadata, but
# still inherit the official Wiki URL when the local override did not specify
# one. This keeps provenance visible for every documented tag without making
# the runtime depend on the network.
for _tag_name, _tag in INCAR_TAGS.items():
    if _tag.source_url is None:
        _official_metadata = OFFICIAL_WIKI_TAGS.get(_tag_name)
        if isinstance(_official_metadata, dict):
            _official_url = _official_metadata.get("source_url")
            if isinstance(_official_url, str):
                _tag.source_url = _official_url


# List of all tag names for quick reference
INCAR_TAG_LIST: List[str] = list(INCAR_TAGS.keys())


def get_tag_info(name: str) -> Optional[INCARTag]:
    """Get metadata for a specific INCAR tag.

    Args:
        name: The INCAR tag name (case-insensitive).

    Returns:
        INCARTag object if found, None otherwise.
    """
    return INCAR_TAGS.get(name.upper())


def search_tags(query: str) -> List[INCARTag]:
    """Search for INCAR tags matching a query string.

    Args:
        query: Search string to match against tag names and descriptions.

    Returns:
        List of matching INCARTag objects.
    """
    query_lower = query.lower()
    results = []
    for tag in INCAR_TAGS.values():
        if query_lower in tag.name.lower() or query_lower in tag.description.lower():
            results.append(tag)
    return results
