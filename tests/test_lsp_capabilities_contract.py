"""OpenQC lsp-capabilities contract tests for VASP-LSP (#82-#84)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from vasp_lsp.rules import RULES_MANIFEST, export_manifest

REPO_ROOT = Path(__file__).resolve().parent.parent
CAPABILITIES_PATH = REPO_ROOT / "lsp-capabilities.json"


def _load_capabilities() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(CAPABILITIES_PATH.read_text(encoding="utf-8")))


def test_lsp_capabilities_manifest_exists_and_matches_tooling() -> None:
    caps = _load_capabilities()
    assert caps["schema"] == "OpenQCLspCapabilities"
    assert caps["software"] == "vasp"
    assert caps["executable"] == "vasp-lsp"
    assert caps["openqc"]["diagnosticEnvelope"] == "DiagnosticEnvelope/v1"
    assert caps["agentCli"]["command"] == "vasp-lsp-tool"
    assert set(caps["agentCli"]["operations"]) >= {"check", "rules", "fix", "hover"}


def test_lsp_capabilities_source_provenance_entries() -> None:
    caps = _load_capabilities()
    assert len(caps["sourceProvenance"]) >= 3
    urls = {entry.get("url") for entry in caps["sourceProvenance"] if entry.get("url")}
    assert "https://www.vasp.at/wiki/index.php/INCAR" in urls
    paths = {entry.get("path") for entry in caps["sourceProvenance"] if entry.get("path")}
    assert "raw/assets/upstream-vasp-reference.md" in paths
    assert "rules/diagnostics.yaml" in paths


def test_lsp_capabilities_rule_count_matches_registry() -> None:
    manifest = export_manifest()
    assert len(manifest["rules"]) == len(RULES_MANIFEST)


def test_wiki_lint_script_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/wiki_lint.py"), "--root", str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_asset_manifest_checksums_match_disk() -> None:
    manifest = json.loads(
        (REPO_ROOT / "raw/assets/asset-manifest.json").read_text(encoding="utf-8")
    )
    upstream = next(
        a for a in manifest["assets"] if a["path"].endswith("upstream-vasp-reference.md")
    )
    data = (REPO_ROOT / upstream["path"]).read_bytes()
    import hashlib

    assert hashlib.sha256(data).hexdigest() == upstream["sha256"]
