#!/usr/bin/env python3
"""Deterministic OpenQC v1 docstring/wiki/raw traceability report generator.

Scans src/vasp_lsp/ for module docstrings, discovers wiki/ pages, discovers
raw/ assets, and writes reports/docstring-wiki-raw-traceability.json.

Usage:
    python scripts/check_docstring_traceability.py          # generate + validate
    python scripts/check_docstring_traceability.py --strict # validate only
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = REPO_ROOT / "reports" / "docstring-wiki-raw-traceability.json"
SCHEMA_VERSION = "openqc.lsp.traceability.v1"
SERVER_ID = "vasp-lsp"
LANGUAGE_ID = "vasp-input"

WIKI_DIR = REPO_ROOT / "wiki"
RAW_DIR = REPO_ROOT / "raw"
SRC_DIR = REPO_ROOT / "src" / "vasp_lsp"

# Map existing VASP rule_id dotted names to VASP-<FILE_ROLE>-<CATEGORY>-NNN
_RULE_CODE_MAP: Dict[str, Tuple[str, str, int]] = {
    "vasp.incar.invalid_tag": ("INCAR", "SCHEMA", 1),
    "vasp.incar.invalid_value": ("INCAR", "SCHEMA", 2),
    "vasp.spin.missing_magmom": ("INCAR", "SEMANTIC", 1),
    "vasp.smearing.ismear_sigma_mismatch": ("INCAR", "SEMANTIC", 2),
    "vasp.encut.below_enmax": ("INCAR", "SEMANTIC", 3),
    "vasp.parallel.ncore_npar_conflict": ("INCAR", "SEMANTIC", 4),
    "vasp.parallel.kpar_incompatible": ("INCAR", "SEMANTIC", 5),
    "vasp.restart.file_mismatch": ("INCAR", "SEMANTIC", 6),
    "vasp.log.symmetry_failure": ("LOG", "RUNTIME", 1),
    "vasp.log.electronic_minimization_failed": ("LOG", "RUNTIME", 2),
}

# Semantic keywords that link a docstring to a wiki page
_WIKI_SEMANTIC_RULES: Dict[str, List[str]] = {
    "wiki/entities/VASP_LSP.md": [
        "vasp",
        "lsp",
        "server",
        "language server",
        "language-server",
        "diagnostic engine",
    ],
    "wiki/concepts/VASP_Input_Validation.md": [
        "diagnostic",
        "validation",
        "validator",
        "parser",
        "check",
    ],
    "wiki/synthesis/Agent_Workflow.md": [
        "agent",
        "cli",
        "command-line",
        "tool",
    ],
}

# Raw assets that support each wiki page (truthful provenance)
_WIKI_RAW_SUPPORT: Dict[str, List[str]] = {
    "wiki/synthesis/Agent_Workflow.md": [
        "raw/assets/docs__validation-contract.md",
        "raw/assets/docs__user-guide.md",
    ],
}


def _raw_manifest_data() -> Dict[str, Any]:
    raw_manifest = REPO_ROOT / "raw" / "assets" / "asset-manifest.json"
    if not raw_manifest.exists():
        return {}
    try:
        data = json.loads(raw_manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _manifest_generated_at() -> str:
    generated_at = _raw_manifest_data().get("generated_at")
    return generated_at if isinstance(generated_at, str) else "1970-01-01T00:00:00Z"


def _manifest_asset_url(raw_path: str) -> str:
    for asset in _raw_manifest_data().get("assets", []):
        if isinstance(asset, dict) and asset.get("path") == raw_path:
            url = asset.get("url")
            return url if isinstance(url, str) and url else f"repo:{raw_path}"
    return f"repo:{raw_path}"


def _discover_wiki_pages() -> Dict[str, str]:
    pages: Dict[str, str] = {}
    if not WIKI_DIR.exists():
        return pages
    for md_file in sorted(WIKI_DIR.rglob("*.md")):
        rel = md_file.relative_to(REPO_ROOT).as_posix()
        name = md_file.stem
        pages[name] = rel
    return pages


def _discover_raw_assets() -> List[Dict[str, str]]:
    assets: List[Dict[str, str]] = []
    if not RAW_DIR.exists():
        return assets
    for asset_file in sorted(RAW_DIR.rglob("*")):
        if asset_file.is_file():
            rel_path = asset_file.relative_to(REPO_ROOT)
            if any(part.startswith(".") or part == "__pycache__" for part in rel_path.parts):
                continue
            rel = rel_path.as_posix()
            sha = hashlib.sha256(asset_file.read_bytes()).hexdigest()
            assets.append({"path": rel, "sha256": sha})
    return assets


def _extract_module_docstrings(wiki_pages: Dict[str, str]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if not SRC_DIR.exists():
        return entries
    for py_file in sorted(SRC_DIR.rglob("*.py")):
        rel = py_file.relative_to(REPO_ROOT).as_posix()
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError):
            continue
        module_doc = ast.get_docstring(tree)
        if not module_doc:
            continue
        doc_lower = module_doc.lower()
        # Explicit wiki references from docstring text
        wiki_refs = _extract_explicit_wiki_refs(module_doc, wiki_pages)
        # Semantic wiki links based on docstring content
        for page_path, keywords in _WIKI_SEMANTIC_RULES.items():
            if any(kw in doc_lower for kw in keywords):
                if page_path not in wiki_refs:
                    wiki_refs.append(page_path)
        for wiki_path in sorted(wiki_refs):
            entries.append(
                {
                    "path": rel,
                    "symbol": Path(rel).stem,
                    "wikiPath": wiki_path,
                    "docstring": module_doc.split("\n")[0].strip(),
                }
            )
    return entries


def _extract_explicit_wiki_refs(text: str, wiki_pages: Dict[str, str]) -> List[str]:
    refs: List[str] = []
    # Match [[PageName]] wiki-style links
    for match in re.finditer(r"\[\[([A-Za-z_]+)\]\]", text):
        page_name = match.group(1)
        if page_name in wiki_pages:
            refs.append(wiki_pages[page_name])
    return refs


def _extract_raw_refs(text: str) -> List[str]:
    refs: List[str] = []
    raw_assets = _discover_raw_assets()
    for asset in raw_assets:
        rel_path = asset["path"]
        basename = Path(rel_path).name
        if basename in text or rel_path in text:
            refs.append(rel_path)
    for match in re.finditer(r"raw/assets/[\w._-]+", text):
        ref = match.group(0)
        if ref not in refs:
            refs.append(ref)
    return sorted(refs)


def _extract_urls(text: str) -> List[str]:
    urls: List[str] = []
    for match in re.finditer(r"https?://[^\s,;)\]>\"]+", text):
        url = match.group(0).rstrip(".,;)")
        if url not in urls:
            urls.append(url)
    return sorted(urls)


def _build_wiki_sources(wiki_pages: Dict[str, str]) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    for name, path in sorted(wiki_pages.items()):
        wiki_file = REPO_ROOT / path
        raw_refs: List[str] = []
        if wiki_file.exists():
            content = wiki_file.read_text(encoding="utf-8")
            raw_refs = _extract_raw_refs(content)
        # Add known truthful raw support for wiki pages
        if path in _WIKI_RAW_SUPPORT:
            for ref in _WIKI_RAW_SUPPORT[path]:
                if ref not in raw_refs:
                    raw_refs.append(ref)
        for raw_ref in sorted(raw_refs):
            sources.append(
                {
                    "wikiPath": path,
                    "rawPath": raw_ref,
                    "sourceUrl": _manifest_asset_url(raw_ref),
                }
            )
    return sources


def _build_rule_ids() -> List[Dict[str, Any]]:
    ids: List[Dict[str, Any]] = []
    for rule_id, (file_role, category, num) in sorted(_RULE_CODE_MAP.items()):
        code = f"VASP-{file_role}-{category}-{num:03d}"
        ids.append(
            {
                "dottedId": rule_id,
                "code": code,
                "sourcePath": "src/vasp_lsp/rules.py",
                "fileRole": file_role,
                "category": category,
            }
        )
    return ids


def _build_source_urls() -> List[Dict[str, str]]:
    urls: Dict[str, str] = {}
    for asset in _raw_manifest_data().get("assets", []):
        if not isinstance(asset, dict):
            continue
        raw_path = asset.get("path")
        if not isinstance(raw_path, str):
            continue
        urls[raw_path] = _manifest_asset_url(raw_path)
    return [{"rawPath": raw_path, "url": url} for raw_path, url in sorted(urls.items())]


def generate_report() -> Dict[str, Any]:
    wiki_pages = _discover_wiki_pages()
    raw_assets = _discover_raw_assets()
    docstrings = _extract_module_docstrings(wiki_pages)
    wiki_sources = _build_wiki_sources(wiki_pages)
    rule_ids = _build_rule_ids()
    source_urls = _build_source_urls()

    docstrings_total = len(docstrings)
    docstrings_linked = sum(1 for d in docstrings if d.get("wikiPath"))

    broken_wiki = 0
    for d in docstrings:
        wp = d.get("wikiPath")
        if isinstance(wp, str) and not (REPO_ROOT / wp).exists():
            broken_wiki += 1

    linked_wiki_pages = {ws["wikiPath"] for ws in wiki_sources}
    wiki_without_raw = sum(1 for path in wiki_pages.values() if path not in linked_wiki_pages)

    raw_manifest = REPO_ROOT / "raw" / "assets" / "asset-manifest.json"
    raw_manifest_failures = 0
    if raw_manifest.exists():
        try:
            data = json.loads(raw_manifest.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "assets" not in data:
                raw_manifest_failures = 1
        except (json.JSONDecodeError, OSError):
            raw_manifest_failures = 1
    else:
        raw_manifest_failures = 1

    report: Dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "serverId": SERVER_ID,
        "repository": "newtontech/VASP-LSP",
        "languageId": LANGUAGE_ID,
        "generatedAt": _manifest_generated_at(),
        "summary": {
            "docstringsTotal": docstrings_total,
            "docstringsLinked": docstrings_linked,
            "wikiPagesTotal": len(wiki_pages),
            "rawAssetsTotal": len(raw_assets),
            "ruleIdsTotal": len(rule_ids),
            "brokenWikiLinks": broken_wiki,
            "wikiSourcesWithoutRaw": wiki_without_raw,
            "rawManifestFailures": raw_manifest_failures,
        },
        "docstrings": docstrings,
        "wikiSources": wiki_sources,
        "ruleIds": rule_ids,
        "sourceUrls": source_urls,
        "rawManifest": {
            "path": "raw/assets/asset-manifest.json",
            "ok": raw_manifest_failures == 0,
            "assetCount": len(raw_assets),
        },
    }
    return report


def validate_strict(report: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    if report.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"schemaVersion must be {SCHEMA_VERSION}, got {report.get('schemaVersion')}")

    required_fields = [
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
    for field in required_fields:
        if field not in report:
            errors.append(f"missing top-level field: {field}")

    for rule in report.get("ruleIds", []):
        code = rule.get("code", "")
        if not re.match(r"^VASP-[A-Z]+-[A-Z]+-\d{3}$", code):
            errors.append(f"ruleIds code format invalid: {code}")

    all_paths: List[str] = []
    for d in report.get("docstrings", []):
        all_paths.append(d.get("path", ""))
        all_paths.append(d.get("wikiPath", ""))
    for ws in report.get("wikiSources", []):
        all_paths.append(ws.get("wikiPath", ""))
        all_paths.append(ws.get("rawPath", ""))
    for source in report.get("sourceUrls", []):
        all_paths.append(source.get("rawPath", ""))
    raw_manifest = report.get("rawManifest", {})
    if isinstance(raw_manifest, dict):
        all_paths.append(raw_manifest.get("path", ""))
    for p in all_paths:
        if p.startswith("/"):
            errors.append(f"absolute path found: {p}")

    summary = report.get("summary", {})
    if summary.get("docstringsLinked") != summary.get("docstringsTotal"):
        errors.append(
            f"docstringsLinked ({summary.get('docstringsLinked')}) "
            f"!= docstringsTotal ({summary.get('docstringsTotal')})"
        )

    for key in ("brokenWikiLinks", "wikiSourcesWithoutRaw", "rawManifestFailures"):
        if summary.get(key, -1) != 0:
            errors.append(f"summary.{key} must be 0, got {summary.get(key)}")

    return errors


def main() -> int:
    strict = "--strict" in sys.argv
    report = generate_report()

    if strict:
        errors = validate_strict(report)
        if errors:
            print("VALIDATION FAILED:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 1
        print("VALIDATION PASSED", file=sys.stderr)
        return 0

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"Report written to {REPORT_PATH.relative_to(REPO_ROOT)}")

    errors = validate_strict(report)
    if errors:
        print("VALIDATION FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
