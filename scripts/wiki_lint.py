#!/usr/bin/env python3
"""Validate VASP-LSP wiki, provenance, and OpenQC fixture contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REQUIRED_PATHS = (
    "lsp-capabilities.json",
    "raw/assets/asset-manifest.json",
    "raw/assets/upstream-vasp-reference.md",
    "rules/diagnostics.yaml",
    "wiki/entities",
    "wiki/concepts",
    "wiki/synthesis",
)
SOURCES_HEADINGS = (
    "## Sources",
    "## 参考来源 (Sources)",
    "## 来源 / Sources",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def lint(root: Path) -> list[str]:
    errors: list[str] = []
    for rel in REQUIRED_PATHS:
        if not (root / rel).exists():
            errors.append(f"missing required path: {rel}")

    caps_path = root / "lsp-capabilities.json"
    if caps_path.exists():
        caps = json.loads(caps_path.read_text(encoding="utf-8"))
        for bucket in ("valid", "invalid", "logs"):
            for rel in caps.get("fixturePaths", {}).get(bucket, []):
                path = root / rel
                if not path.exists():
                    errors.append(f"fixture path missing ({bucket}): {rel}")
                elif bucket in {"valid", "invalid"} and not any(path.iterdir()):
                    errors.append(f"fixture directory empty ({bucket}): {rel}")

    manifest_path = root / "raw/assets/asset-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for asset in manifest.get("assets", []):
            rel = asset.get("path")
            if not isinstance(rel, str):
                continue
            file_path = root / rel
            if not file_path.exists():
                errors.append(f"asset-manifest path missing: {rel}")
                continue
            expected_sha = asset.get("sha256")
            if expected_sha and _sha256(file_path) != expected_sha:
                errors.append(f"asset-manifest sha256 mismatch: {rel}")
            expected_size = asset.get("size_bytes")
            if expected_size is not None and file_path.stat().st_size != expected_size:
                errors.append(f"asset-manifest size_bytes mismatch: {rel}")

    for wiki_path in sorted((root / "wiki").glob("**/*.md")):
        text = wiki_path.read_text(encoding="utf-8")
        rel = wiki_path.relative_to(root).as_posix()
        if not any(heading in text for heading in SOURCES_HEADINGS):
            errors.append(f"wiki page missing Sources section: {rel}")

    yaml_path = root / "rules" / "diagnostics.yaml"
    if yaml_path.exists():
        from vasp_lsp.rules import export_manifest

        lines = [
            line
            for line in yaml_path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        ]
        on_disk = json.loads("\n".join(lines).strip())
        if on_disk != export_manifest():
            errors.append("rules/diagnostics.yaml out of sync with src/vasp_lsp/rules.py")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    errors = lint(root)
    if errors:
        for error in errors:
            print(f"wiki-lint: {error}", file=sys.stderr)
        return 1
    print("wiki-lint: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
