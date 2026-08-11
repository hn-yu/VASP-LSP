"""Public behavior tests for shared VASP calculation workspace context."""

from __future__ import annotations

from pathlib import Path

from vasp_lsp.tool import check_path
from vasp_lsp.workspace import CalculationWorkspace, DocumentKind, document_kind


def test_document_kind_is_consistent_for_vasp_names_and_uri_paths() -> None:
    assert document_kind("file:///calc/INCAR") is DocumentKind.INCAR
    assert document_kind("file:///calc/INCAR.static") is DocumentKind.INCAR
    assert document_kind("file:///calc/blocking_invalid_tag.INCAR") is DocumentKind.INCAR
    assert document_kind("file:///calc/POSCAR") is DocumentKind.POSCAR
    assert document_kind("file:///calc/CONTCAR.md") is DocumentKind.POSCAR
    assert document_kind("file:///calc/KPOINTS.vasp") is DocumentKind.KPOINTS
    assert document_kind("file:///calc/POTCAR") is DocumentKind.POTCAR
    assert document_kind("file:///calc/POTCAR.spec") is DocumentKind.UNKNOWN
    assert document_kind("file:///calc/slurm-123.out") is DocumentKind.VASP_LOG


def test_calculation_workspace_prefers_open_buffer_over_disk(tmp_path: Path) -> None:
    incar = tmp_path / "INCAR"
    potcar = tmp_path / "POTCAR"
    incar.write_text("ENCUT = 520\n", encoding="utf-8")
    potcar.write_text("disk POTCAR\n", encoding="utf-8")
    open_potcar = potcar.resolve().as_uri()

    workspace = CalculationWorkspace(
        incar.resolve().as_uri(),
        {open_potcar: "unsaved POTCAR\n"},
    )

    assert workspace.read("POTCAR") == "unsaved POTCAR\n"
    assert workspace.read("INCAR") == "ENCUT = 520\n"
    assert workspace.read("MISSING") is None


def test_calculation_workspace_has_checks_binary_restart_without_reading_it(
    tmp_path: Path, monkeypatch,
) -> None:
    wavecar = tmp_path / "WAVECAR"
    wavecar.write_bytes(b"binary restart payload")

    workspace = CalculationWorkspace(tmp_path / "INCAR")

    original_read_text = Path.read_text

    def read_text(path, *args, **kwargs):
        if path == wavecar:
            raise AssertionError("binary restart must be checked by existence only")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)

    assert workspace.has("WAVECAR") is True
    assert workspace.has("CHGCAR") is False


def test_single_file_cli_check_uses_neighbor_files(tmp_path: Path) -> None:
    incar = tmp_path / "INCAR"
    incar.write_text("ENCUT = 250\n", encoding="utf-8")
    (tmp_path / "POTCAR").write_text(
        "TITEL = PAW_PBE Si 05Jan2001\nENMAX = 400; ENMIN = 300\n",
        encoding="utf-8",
    )

    payload = check_path(incar)

    assert any(
        item["code"] == "vasp.encut.below_enmax"
        for item in payload["diagnostics"]
    )
