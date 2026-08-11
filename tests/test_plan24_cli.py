import json

from vasp_lsp import tool
from vasp_lsp.features.diagnostics import DiagnosticsProvider
from vasp_lsp.parsers.potcar_parser import POTCARParser


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


def test_workspace_documents_ignore_large_calculation_artifacts(tmp_path, monkeypatch) -> None:
    incar = tmp_path / "INCAR"
    potcar = tmp_path / "POTCAR"
    wavecar = tmp_path / "WAVECAR"
    chgcar = tmp_path / "CHGCAR"
    incar.write_text("ENCUT = 520\n", encoding="utf-8")
    potcar.write_text("PAW_PBE Si 05Jan2001\n", encoding="utf-8")
    wavecar.write_bytes(b"binary wavefunction payload")
    chgcar.write_bytes(b"binary charge density payload")

    original_read_text = tool._read_text

    def read_text(path):
        if path in {wavecar, chgcar}:
            raise AssertionError(f"large artifact should not be read: {path.name}")
        return original_read_text(path)

    monkeypatch.setattr(tool, "_read_text", read_text)
    documents = tool._workspace_documents(tmp_path)

    assert incar.resolve().as_uri() in documents
    assert potcar.resolve().as_uri() in documents
    assert wavecar.resolve().as_uri() not in documents
    assert chgcar.resolve().as_uri() not in documents


def test_workspace_documents_do_not_load_runtime_logs(tmp_path, monkeypatch) -> None:
    """Input-file context must not read multi-megabyte OUTCAR/slurm logs."""
    incar = tmp_path / "INCAR"
    outcar = tmp_path / "OUTCAR"
    slurm = tmp_path / "slurm-123.out"
    incar.write_text("ENCUT = 520\n", encoding="utf-8")
    outcar.write_text("runtime output\n", encoding="utf-8")
    slurm.write_text("scheduler output\n", encoding="utf-8")

    original_read_text = tool._read_text

    def read_text(path):
        if path in {outcar, slurm}:
            raise AssertionError(f"runtime log should not be loaded: {path.name}")
        return original_read_text(path)

    monkeypatch.setattr(tool, "_read_text", read_text)
    documents = tool._workspace_documents(tmp_path)

    assert incar.resolve().as_uri() in documents
    assert outcar.resolve().as_uri() not in documents
    assert slurm.resolve().as_uri() not in documents


def test_directory_check_skips_vaspkit_metadata_file(tmp_path) -> None:
    (tmp_path / "INCAR").write_text("ENCUT = 520\n", encoding="utf-8")
    (tmp_path / "POTCAR.spec").write_text("Si\n", encoding="utf-8")

    payload = tool.check_target(tmp_path)

    assert not any(
        item["source_file"].endswith("POTCAR.spec") for item in payload["diagnostics"]
    )


def test_tool_and_check_entrypoints_share_directory_diagnostics(tmp_path, capsys) -> None:
    """The two check envelopes must serialize the same collected diagnostics."""
    (tmp_path / "INCAR").write_text("ENCUT = 250\n", encoding="utf-8")
    (tmp_path / "POSCAR").write_text(
        "Si\n"
        "1\n"
        "5 0 0\n"
        "0 5 0\n"
        "0 0 5\n"
        "Si\n"
        "1\n"
        "Direct\n"
        "0 0 0\n",
        encoding="utf-8",
    )
    (tmp_path / "POTCAR").write_text(
        "TITEL = PAW_PBE Si 05Jan2001\n"
        "ENMAX = 400; ENMIN = 300\n",
        encoding="utf-8",
    )

    assert tool.main(["check", str(tmp_path)]) == 0
    tool_payload = json.loads(capsys.readouterr().out)

    assert tool.check_main([str(tmp_path), "--format", "json"]) == 0
    check_payload = json.loads(capsys.readouterr().out)

    tool_codes = sorted(
        (item["code"], item["severity"]) for item in tool_payload["diagnostics"]
    )
    check_codes = sorted(
        (item["id"], item["severity"]) for item in check_payload["diagnostics"]
    )

    assert tool_codes == check_codes
    assert tool_codes == [("vasp.encut.below_enmax", "warning")]


def test_check_entrypoints_stabilize_empty_unreadable_and_binary_targets(
    tmp_path, monkeypatch
) -> None:
    empty = tmp_path / "INCAR"
    unreadable = tmp_path / "INCAR.unreadable"
    wavecar = tmp_path / "WAVECAR"
    chgcar = tmp_path / "CHGCAR"
    empty.write_text("", encoding="utf-8")
    unreadable.write_text("ENCUT = 520\n", encoding="utf-8")
    wavecar.write_bytes(b"binary wavefunction payload")
    chgcar.write_bytes(b"binary charge density payload")

    original_read_text = tool._read_text

    def read_text(path):
        if path == unreadable:
            raise PermissionError("test-only unreadable target")
        if path in {wavecar, chgcar}:
            raise AssertionError(f"binary target should not be read: {path.name}")
        return original_read_text(path)

    monkeypatch.setattr(tool, "_read_text", read_text)

    for target in (empty, unreadable, wavecar, chgcar):
        assert tool.check_path(target)["ok"] is True
        assert tool.check_target(target)["ok"] is True


def test_diagnostics_reuses_unchanged_potcar_parse(monkeypatch) -> None:
    poscar = """Test
1.0
5 0 0
0 5 0
0 0 5
Si
1
Direct
0 0 0
"""
    potcar = """TITEL = PAW_PBE Si 05Jan2001
ENMAX = 245.345; ENMIN = 143.678
"""
    workspace = {
        "file:///calc/POSCAR": poscar,
        "file:///calc/POTCAR": potcar,
    }
    provider = DiagnosticsProvider()
    init_calls = 0
    original_init = POTCARParser.__init__

    def counted_init(self, content):
        nonlocal init_calls
        init_calls += 1
        original_init(self, content)

    monkeypatch.setattr(POTCARParser, "__init__", counted_init)

    for _ in range(2):
        provider.get_diagnostics(
            "ENCUT = 520\n",
            "file:///calc/INCAR",
            workspace_documents=workspace,
        )

    assert init_calls == 1


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
