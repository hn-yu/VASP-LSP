"""Release contract for the VASP-LSP 0.4.5 publication path."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from vasp_lsp import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_VERSION = "0.4.5"


def test_release_version_is_consistent_across_all_manifests() -> None:
    """Every user-visible package manifest must advertise the release version."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    pyproject_match = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
    assert pyproject_match is not None

    package_json = json.loads(
        (REPO_ROOT / "editors/vscode/package.json").read_text(encoding="utf-8")
    )
    package_lock = json.loads(
        (REPO_ROOT / "editors/vscode/package-lock.json").read_text(encoding="utf-8")
    )
    capabilities = json.loads((REPO_ROOT / "lsp-capabilities.json").read_text(encoding="utf-8"))

    assert {
        __version__,
        pyproject_match.group(1),
        (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        package_json["version"],
        package_lock["version"],
        package_lock["packages"][""]["version"],
        capabilities["releaseVersion"],
    } == {RELEASE_VERSION}


def test_release_workflow_is_tag_only_oidc_and_smokes_the_fresh_wheel() -> None:
    """Publishing must use trusted publishing after a fresh-wheel smoke test."""
    workflow = (REPO_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch" not in workflow
    assert 'tags: ["v*"]' in workflow
    assert "environment: pypi" in workflow
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "secrets." not in workflow
    assert "password:" not in workflow
    assert "python scripts/verify_release.py" in workflow
    assert "python scripts/smoke_test_wheel.py" in workflow
    assert "needs: smoke-wheel" in workflow


def test_release_verifier_accepts_only_the_matching_release_tag() -> None:
    """The build must stop when a pushed tag disagrees with package metadata."""
    verifier = REPO_ROOT / "scripts/verify_release.py"
    matching = subprocess.run(
        [sys.executable, str(verifier), "--tag", f"v{RELEASE_VERSION}"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    mismatched = subprocess.run(
        [sys.executable, str(verifier), "--tag", "v9.9.9"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )

    assert matching.returncode == 0, matching.stderr
    assert "release metadata verified" in matching.stdout
    assert mismatched.returncode != 0
    assert "release metadata does not match v9.9.9" in mismatched.stderr
