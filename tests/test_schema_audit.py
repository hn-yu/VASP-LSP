"""Tests for the offline official-Wiki schema audit."""

from __future__ import annotations

import json

from vasp_lsp import tool
from vasp_lsp.schema_audit import audit_schema


def test_schema_audit_proves_official_catalog_is_loaded_and_traceable() -> None:
    report = audit_schema()

    assert report["schema_version"] == "vasp-lsp.schema.v1"
    assert report["ok"] is True
    assert report["official_tag_count"] >= 600
    assert report["runtime_tag_count"] >= report["official_tag_count"]
    assert report["unknown_type_count"] >= 0
    assert report["errors"] == []


def test_schema_audit_cli_returns_json(capsys) -> None:
    exit_code = tool.schema_audit_main([])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["capabilities"]["operation"] == "schema-audit"
