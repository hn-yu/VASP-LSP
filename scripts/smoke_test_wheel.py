#!/usr/bin/env python3
"""Install a wheel in isolation and smoke its server and agent-facing CLI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import venv
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _run(
    command: list[str],
    *,
    cwd: Path,
    expected_returncodes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if result.returncode not in expected_returncodes:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _json(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("command did not return a JSON object")
    return payload


def smoke(wheel: Path) -> None:
    wheel = wheel.resolve()
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ValueError(f"wheel does not exist: {wheel}")
    expected_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

    with tempfile.TemporaryDirectory(prefix="vasp-lsp-wheel-") as temporary:
        isolated = Path(temporary)
        environment = isolated / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        bindir = environment / ("Scripts" if os.name == "nt" else "bin")
        python = bindir / ("python.exe" if os.name == "nt" else "python")
        executable_suffix = ".exe" if os.name == "nt" else ""

        _run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check", str(wheel)],
            cwd=isolated,
        )

        server = bindir / f"vasp-lsp{executable_suffix}"
        tool = bindir / f"vasp-lsp-tool{executable_suffix}"
        check = bindir / f"vasp-lsp-check{executable_suffix}"
        explain = bindir / f"vasp-lsp-explain{executable_suffix}"

        _run([str(server), "--help"], cwd=isolated)
        server_version = _run([str(server), "--version"], cwd=isolated).stdout.strip()
        installed_version = _run(
            [
                str(python),
                "-c",
                "from importlib.metadata import version; print(version('vasp-lsp'))",
            ],
            cwd=isolated,
        ).stdout.strip()
        if installed_version != expected_version or expected_version not in server_version:
            raise RuntimeError(
                "installed wheel and server versions do not match VERSION: "
                f"metadata={installed_version!r}, server={server_version!r}, "
                f"expected={expected_version!r}"
            )
        rules = _json(_run([str(tool), "rules"], cwd=isolated))
        if rules.get("operation") != "rules" or not rules.get("rules"):
            raise RuntimeError("agent rules smoke returned an incomplete payload")

        valid = ROOT / "tests/fixtures/valid/minimal.INCAR"
        valid_payload = _json(_run([str(check), str(valid), "--format", "json"], cwd=isolated))
        if valid_payload.get("ok") is not True:
            raise RuntimeError("valid fixture did not pass the installed wheel")

        invalid = ROOT / "tests/fixtures/invalid/blocking_invalid_tag.INCAR"
        invalid_payload = _json(
            _run(
                [str(check), str(invalid), "--format", "json", "--fail-on-blocking"],
                cwd=isolated,
                expected_returncodes=(1,),
            )
        )
        if invalid_payload.get("ok") is not False or not invalid_payload.get("diagnostics"):
            raise RuntimeError("invalid fixture did not produce blocking diagnostics")

        log = ROOT / "tests/fixtures/logs/electronic_minimization_failed.out"
        log_payload = _json(
            _run(
                [str(explain), str(log), "--format", "json", "--fail-on-blocking"],
                cwd=isolated,
                expected_returncodes=(1,),
            )
        )
        if log_payload.get("operation") != "explain" or not log_payload.get("diagnostics"):
            raise RuntimeError("runtime-log fixture did not produce diagnostics")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", required=True, type=Path)
    args = parser.parse_args()
    smoke(args.wheel)
    print(f"fresh-wheel smoke passed: {args.wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
