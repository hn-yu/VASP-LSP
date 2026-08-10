import json

from vasp_lsp import tool


def test_workspace_documents_skip_unreadable_peer(tmp_path, monkeypatch) -> None:
    readable = tmp_path / "INCAR"
    unreadable = tmp_path / "other.out"
    readable.write_text("ENCUT = 520\n", encoding="utf-8")
    unreadable.write_text("not needed\n", encoding="utf-8")

    original_read_text = tool._read_text

    def read_text(path):
        if path == unreadable:
            raise PermissionError("test-only unreadable peer")
        return original_read_text(path)

    monkeypatch.setattr(tool, "_read_text", read_text)
    documents = tool._workspace_documents(tmp_path)

    assert readable.resolve().as_uri() in documents
    assert unreadable.resolve().as_uri() not in documents


def test_vasp_lsp_check_directory_json_and_blocking_exit(tmp_path, capsys) -> None:
    (tmp_path / "INCAR").write_text("ENCUT = high\n", encoding="utf-8")
    (tmp_path / "KPOINTS").write_text(
        "Automatic\n0\nGamma\n4 4 4\n0 0 0\n",
        encoding="utf-8",
    )

    exit_code = tool.check_main([str(tmp_path), "--format", "json", "--fail-on-blocking"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["schema_version"] == "vasp-lsp.plan24.v1"
    assert payload["operation"] == "check"
    assert payload["ok"] is False
    assert payload["summary"]["errors"] >= 1
    assert any(item["source_file"].endswith("INCAR") for item in payload["diagnostics"])


def test_vasp_lsp_explain_log_json_and_guarded_actions(tmp_path, capsys) -> None:
    log_path = tmp_path / "slurm-123.out"
    log_path.write_text(
        "Error EDDDAV: Call to ZHEGV failed. Returncode = 5\n",
        encoding="utf-8",
    )

    exit_code = tool.explain_main([str(log_path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["schema_version"] == "vasp-lsp.plan24.v1"
    assert payload["operation"] == "explain"
    assert payload["ok"] is False
    diagnostic = payload["diagnostics"][0]
    # Electronic-minimization runtime patterns roll up to the aggregated
    # rule id vasp.log.electronic_minimization_failed (#59).
    assert diagnostic["id"] == "vasp.log.electronic_minimization_failed"
    assert diagnostic["source_file"].endswith("slurm-123.out")
    assert "INCAR" in diagnostic["related_files"]
    assert any(
        action["title"] == "Suggest removing CHGCAR/WAVECAR after confirmation"
        and action["safe_to_auto_apply"] is False
        for action in diagnostic["suggested_actions"]
    )
