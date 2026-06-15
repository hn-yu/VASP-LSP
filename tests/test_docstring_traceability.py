"""Tests for OpenQC v1 docstring/wiki/raw traceability report (#92).

Validates the report shape, repo-relative paths, rule ID format,
semantic linking, and zero failure counters.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = REPO_ROOT / "reports" / "docstring-wiki-raw-traceability.json"
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_docstring_traceability.py"
SCHEMA_VERSION = "openqc.lsp.traceability.v1"


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    """Regenerate the report once per test module."""
    subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        check=True,
        cwd=str(REPO_ROOT),
    )
    return cast(dict[str, Any], json.loads(REPORT_PATH.read_text(encoding="utf-8")))


def test_report_schema_version(report: dict) -> None:
    assert report["schemaVersion"] == SCHEMA_VERSION


def test_report_top_level_fields(report: dict) -> None:
    required = [
        "schemaVersion",
        "serverId",
        "repository",
        "languageId",
        "generatedAt",
        "summary",
        "docstrings",
        "wikiSources",
        "ruleIds",
        "sourceUrls",
        "rawManifest",
    ]
    for field in required:
        assert field in report, f"missing top-level field: {field}"


def test_report_server_id(report: dict) -> None:
    assert report["serverId"] == "vasp-lsp"


def test_report_repository(report: dict) -> None:
    assert report["repository"] == "newtontech/VASP-LSP"


def test_report_language_id(report: dict) -> None:
    assert report["languageId"] == "vasp-input"


def test_report_has_generated_at(report: dict) -> None:
    assert "T" in report["generatedAt"] or re.match(r"\d{4}-", report["generatedAt"])


def test_summary_docstrings_linked_equals_total(report: dict) -> None:
    summary = report["summary"]
    assert summary["docstringsLinked"] == summary["docstringsTotal"], (
        f"docstringsLinked ({summary['docstringsLinked']}) "
        f"!= docstringsTotal ({summary['docstringsTotal']})"
    )


def test_summary_docstrings_total_positive(report: dict) -> None:
    assert report["summary"]["docstringsTotal"] > 0


def test_summary_zero_broken_wiki_links(report: dict) -> None:
    assert report["summary"]["brokenWikiLinks"] == 0


def test_summary_zero_wiki_sources_without_raw(report: dict) -> None:
    assert report["summary"]["wikiSourcesWithoutRaw"] == 0


def test_summary_zero_raw_manifest_failures(report: dict) -> None:
    assert report["summary"]["rawManifestFailures"] == 0


def test_all_paths_repo_relative(report: dict) -> None:
    absolute_paths = []
    for d in report.get("docstrings", []):
        for field in ("path", "wikiPath"):
            if d.get(field, "").startswith("/"):
                absolute_paths.append(d[field])
    for ws in report.get("wikiSources", []):
        for field in ("wikiPath", "rawPath"):
            if ws.get(field, "").startswith("/"):
                absolute_paths.append(ws[field])
    for source in report.get("sourceUrls", []):
        if source.get("rawPath", "").startswith("/"):
            absolute_paths.append(source["rawPath"])
    raw_manifest = report["rawManifest"]
    if raw_manifest.get("path", "").startswith("/"):
        absolute_paths.append(raw_manifest["path"])
    assert not absolute_paths, f"absolute paths found: {absolute_paths}"


def test_rule_id_code_format(report: dict) -> None:
    pattern = re.compile(r"^VASP-[A-Z]+-[A-Z]+-\d{3}$")
    for rule in report["ruleIds"]:
        code = rule["code"]
        assert pattern.match(
            code
        ), f"rule code {code!r} does not match VASP-<FILE_ROLE>-<CATEGORY>-NNN"


def test_rule_ids_have_required_fields(report: dict) -> None:
    for rule in report["ruleIds"]:
        assert "dottedId" in rule
        assert "code" in rule
        assert "sourcePath" in rule
        assert "fileRole" in rule
        assert "category" in rule


def test_docstrings_list(report: dict) -> None:
    assert isinstance(report["docstrings"], list)
    assert len(report["docstrings"]) > 0


def test_docstrings_entry_shape(report: dict) -> None:
    for entry in report["docstrings"]:
        assert "path" in entry
        assert "symbol" in entry
        assert "wikiPath" in entry
        assert "docstring" in entry
        assert entry["wikiPath"].startswith("wiki/")


def test_wiki_sources_list(report: dict) -> None:
    assert isinstance(report["wikiSources"], list)
    assert len(report["wikiSources"]) > 0


def test_wiki_sources_have_raw_sources(report: dict) -> None:
    for ws in report["wikiSources"]:
        assert "wikiPath" in ws
        assert "rawPath" in ws
        assert "sourceUrl" in ws
        assert ws["wikiPath"].startswith("wiki/")
        assert ws["rawPath"].startswith("raw/")
        assert ws["sourceUrl"]


def test_raw_manifest(report: dict) -> None:
    rm = report["rawManifest"]
    assert "path" in rm
    assert rm["ok"] is True
    assert "assetCount" in rm
    assert rm["assetCount"] > 0


def test_strict_validation_passes(report: dict) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--strict"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"strict validation failed: {result.stderr}"


def test_report_deterministic(report: dict) -> None:
    """Running the generator twice should produce identical content."""
    subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        check=True,
        cwd=str(REPO_ROOT),
    )
    report2 = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert report == report2
