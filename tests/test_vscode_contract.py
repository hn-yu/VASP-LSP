"""Contract tests for the bundled VS Code client."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VSCODE_ROOT = REPO_ROOT / "editors" / "vscode"


def test_vscode_manifest_declares_potcar_documents() -> None:
    """POTCAR files must activate the extension and receive a language id."""
    manifest = json.loads((VSCODE_ROOT / "package.json").read_text(encoding="utf-8"))
    languages = {
        language["id"]: language for language in manifest["contributes"]["languages"]
    }

    assert "onLanguage:vasp-potcar" in manifest["activationEvents"]
    assert languages["vasp-potcar"]["filenames"] == ["POTCAR", "POTCAR."]


def test_vscode_client_selects_and_watches_potcar_documents() -> None:
    """The LSP client must attach to and resynchronize POTCAR files."""
    source = (VSCODE_ROOT / "extension.ts").read_text(encoding="utf-8")

    assert re.search(r"language:\s*['\"]vasp-potcar['\"]", source)
    assert re.search(r"\{INCAR,POSCAR,CONTCAR,KPOINTS,POTCAR\}\*", source)
