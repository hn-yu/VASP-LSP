"""Regression tests for common INCAR schema and validation failures."""

from __future__ import annotations

from pathlib import Path

import pytest
from lsprotocol.types import DiagnosticSeverity

from vasp_lsp.features.diagnostics import DiagnosticsProvider
from vasp_lsp.parsers.incar_parser import INCARParser
from vasp_lsp.schemas.incar_tags import INCARTag, get_tag_info

FE2_FIXTURE = Path(__file__).parent / "fixtures" / "real_world" / "fe2" / "INCAR"
COMMON_AUDIT_TAGS = (
    "PREC",
    "ISTART",
    "ICHARG",
    "NELM",
    "NELMIN",
    "NELMDL",
    "ALGO",
    "IALGO",
    "NBANDS",
    "NELECT",
    "ISMEAR",
    "SIGMA",
    "ENCUT",
    "EDIFF",
    "LREAL",
    "LASPH",
    "ADDGRID",
    "LMAXMIX",
    "LMIXTAU",
    "LORBIT",
    "ISYM",
    "SYMPREC",
    "ISPIN",
    "MAGMOM",
    "NUPDOWN",
    "LNONCOLLINEAR",
    "LSORBIT",
    "SAXIS",
    "IBRION",
    "NSW",
    "ISIF",
    "POTIM",
    "EDIFFG",
    "LWAVE",
    "LCHARG",
    "LAECHG",
    "LELF",
    "LVHAR",
    "LVTOT",
    "NCORE",
    "NPAR",
    "KPAR",
    "AMIX",
    "BMIX",
    "AMIX_MAG",
    "BMIX_MAG",
    "MAXMIX",
    "LDIPOL",
    "IDIPOL",
    "DIPOL",
    "GGA",
    "METAGGA",
)


def _incar_diagnostics(content: str):
    return DiagnosticsProvider().get_diagnostics(content, "file:///tmp/INCAR", {})


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (".FALSE.", False),
        (".TRUE.", True),
        ("FALSE", False),
        ("TRUE", True),
        ("F", False),
        ("T", True),
        ("Auto", "Auto"),
        ("On", "On"),
        ("auto", "auto"),
        ("AUTO", "AUTO"),
    ],
)
def test_lreal_accepts_vasp_boolean_and_string_values(value, expected):
    """All documented LREAL spellings must pass schema validation."""
    parsed = INCARParser(f"LREAL = {value}").parse()
    assert parsed["LREAL"].value == expected

    diagnostics = _incar_diagnostics(f"LREAL = {value}")
    assert not [d for d in diagnostics if "LREAL" in d.message]


def test_common_missing_tags_are_known_and_have_expected_parsed_types():
    content = """\
ISYM = 0
LASPH = .TRUE.
LREAL = .FALSE.
NUPDOWN = 4
"""

    parsed = INCARParser(content).parse()
    assert parsed["ISYM"].value == 0
    assert isinstance(parsed["ISYM"].value, int)
    assert parsed["LASPH"].value is True
    assert isinstance(parsed["LASPH"].value, bool)
    assert parsed["LREAL"].value is False
    assert isinstance(parsed["LREAL"].value, bool)
    assert parsed["NUPDOWN"].value == 4
    assert isinstance(parsed["NUPDOWN"].value, int)

    diagnostics = _incar_diagnostics(content)
    assert not any("Unknown INCAR tag" in d.message for d in diagnostics)
    assert not any("Invalid value" in d.message for d in diagnostics)


@pytest.mark.parametrize(
    "assignment",
    ["ISYM = hello", "LASPH = maybe", "LREAL = maybe", "NUPDOWN = hello"],
)
def test_common_tags_still_reject_obviously_invalid_values(assignment):
    diagnostics = _incar_diagnostics(assignment)
    assert any(
        d.severity in {DiagnosticSeverity.Error, DiagnosticSeverity.Warning} for d in diagnostics
    )
    assert any("Invalid" in d.message or "expects" in d.message for d in diagnostics)


def test_common_dft_schema_audit_tags_are_present():
    missing = [name for name in COMMON_AUDIT_TAGS if get_tag_info(name) is None]
    assert missing == []


def test_lreal_schema_uses_boolean_semantics_with_documented_alternatives():
    tag = get_tag_info("LREAL")
    assert tag is not None
    assert tag.type == "boolean"
    assert tag.default is False
    assert tag.enum_values is not None
    assert {".FALSE.", ".TRUE.", "Auto", "On"}.issubset(tag.enum_values)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (".FALSE.", False),
        ("FALSE", False),
        ("F", False),
        (".TRUE.", True),
        ("TRUE", True),
        ("T", True),
        ("Auto", "Auto"),
    ],
)
def test_boolean_enum_normalization_is_generic(value, expected):
    """Boolean enum normalization must work for any boolean schema tag."""
    tag = INCARTag(
        name="MIXED_BOOLEAN_TEST",
        type="boolean",
        default=False,
        description="test schema",
        category="test",
        enum_values=[".FALSE.", "FALSE", "F", ".TRUE.", "TRUE", "T", "Auto"],
    )
    parsed = INCARParser(f"MIXED_BOOLEAN_TEST = {value}").parse()
    param = parsed["MIXED_BOOLEAN_TEST"]
    assert param.value == expected

    diagnostics = DiagnosticsProvider()._validate_incar_value(tag, param, "")
    assert diagnostics == []


def test_fe2_fixture_does_not_report_core_schema_false_positives():
    content = FE2_FIXTURE.read_text(encoding="utf-8")
    diagnostics = _incar_diagnostics(content)
    core_tags = {"ISYM", "LASPH", "LREAL", "NUPDOWN"}

    assert not any(
        "Unknown INCAR tag" in diagnostic.message
        and any(tag in diagnostic.message for tag in core_tags)
        for diagnostic in diagnostics
    )
    assert not any(
        tag in diagnostic.message and "Invalid value" in diagnostic.message
        for diagnostic in diagnostics
        for tag in core_tags
    )
