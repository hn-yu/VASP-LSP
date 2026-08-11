"""Parser results are reused when a document is parsed more than once."""

import pytest

from vasp_lsp.parsers.incar_parser import INCARParser
from vasp_lsp.parsers.kpoints_parser import KPOINTSParser
from vasp_lsp.parsers.poscar_parser import POSCARParser
from vasp_lsp.parsers.potcar_parser import POTCARParser


@pytest.mark.parametrize(
    ("parser_factory", "content"),
    [
        (
            POSCARParser,
            """Test
1.0
5 0 0
0 5 0
0 0 5
Si
1
Direct
0 0 0
""",
        ),
        (
            KPOINTSParser,
            """Automatic
0
Gamma
4 4 4
0 0 0
""",
        ),
        (
            POTCARParser,
            """TITEL = PAW_PBE Si 05Jan2001
ENMAX = 245.345; ENMIN = 143.678
""",
        ),
    ],
)
def test_static_parser_returns_same_result_for_unchanged_content(
    parser_factory, content
) -> None:
    parser = parser_factory(content)

    first = parser.parse()
    second = parser.parse()

    assert first is second


def test_incar_parser_remains_current_document_parser() -> None:
    parser = INCARParser("ENCUT = 520\n")
    first = parser.parse()
    second = parser.parse()

    # INCAR is intentionally included as a control: current-document parsing
    # retains its existing contract while neighbor-parser memoization evolves.
    assert first is not second
