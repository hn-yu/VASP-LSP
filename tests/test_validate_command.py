"""Tests for #25: optional VASP validate/dry-run command."""

import json
import os
import tempfile
from unittest.mock import patch

from vasp_lsp.server import _handle_validate, server


class TestValidateCommand:
    """Tests for the vasp-lsp.validate execute command."""

    def test_validate_no_arguments(self):
        result = json.loads(_handle_validate([]))
        assert result["status"] == "configuration_error"
        assert "No document URI" in result["message"]

    def test_validate_missing_binary(self):
        result = json.loads(_handle_validate(["file:///tmp/INCAR"]))
        assert result["status"] == "configuration_error"
        assert "not configured" in result["message"]

    def test_validate_nonexistent_binary(self):
        result = json.loads(_handle_validate(["file:///tmp/INCAR", "/nonexistent/vasp"]))
        assert result["status"] == "configuration_error"
        assert "not configured" in result["message"]

    def test_validate_document_not_open(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix="vasp") as f:
            f.write(b"some content")
            binary_path = f.name
        try:
            result = json.loads(_handle_validate(["file:///tmp/INCAR", binary_path]))
            assert result["status"] == "configuration_error"
            assert "not open" in result["message"]
        finally:
            os.unlink(binary_path)

    def test_validate_unknown_file_type(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix="vasp") as f:
            f.write(b"some content")
            binary_path = f.name
        try:
            server.set_document_content("file:///tmp/UNKNOWN.txt", "some content")
            result = json.loads(_handle_validate(["file:///tmp/UNKNOWN.txt", binary_path]))
            assert result["status"] == "configuration_error"
            assert "INCAR" in result["message"]
        finally:
            os.unlink(binary_path)
            server.documents.pop("file:///tmp/UNKNOWN.txt", None)

    def test_validate_runs_binary(self):
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix="vasp", prefix="vasp-test-"
        ) as f:
            f.write("ENCUT = 400")
            binary_path = f.name
        # Create a fake VASP binary
        fake_bin = tempfile.mktemp(suffix="vasp_bin")
        try:
            with open(fake_bin, "w") as bh:
                bh.write("#!/bin/sh\necho 'vasp validate ok'\n")
            os.chmod(fake_bin, 0o755)

            server.set_document_content("file:///tmp/INCAR", "ENCUT = 400")
            result = json.loads(_handle_validate(["file:///tmp/INCAR", fake_bin]))
            assert result["status"] == "success"
            assert result["exit_code"] == 0
            assert len(result["diagnostics"]) >= 1
            assert "vasp validate ok" in result["diagnostics"][0]["message"]
        finally:
            os.unlink(fake_bin) if os.path.exists(fake_bin) else None
            os.unlink(binary_path) if os.path.exists(binary_path) else None
            server.documents.pop("file:///tmp/INCAR", None)

    def test_validate_timeout(self):
        # Create a binary that sleeps forever
        fake_bin = tempfile.mktemp(suffix="vasp_bin")
        try:
            with open(fake_bin, "w") as bh:
                bh.write("#!/bin/sh\nsleep 60\n")
            os.chmod(fake_bin, 0o755)

            server.set_document_content("file:///tmp/INCAR", "ENCUT = 400")
            result = json.loads(_handle_validate(["file:///tmp/INCAR", fake_bin, "1"]))
            assert result["status"] == "timeout"
            assert "timed out" in result["message"]
        finally:
            os.unlink(fake_bin) if os.path.exists(fake_bin) else None
            server.documents.pop("file:///tmp/INCAR", None)

    def test_validate_with_env_binary(self):
        fake_bin = tempfile.mktemp(suffix="vasp_bin")
        try:
            with open(fake_bin, "w") as bh:
                bh.write("#!/bin/sh\necho 'env binary ok'\n")
            os.chmod(fake_bin, 0o755)

            server.set_document_content("file:///tmp/INCAR", "ENCUT = 400")
            with patch.dict(os.environ, {"VASP_BINARY": fake_bin}):
                result = json.loads(_handle_validate(["file:///tmp/INCAR"]))
                assert result["status"] == "success"
                assert "env binary ok" in result["diagnostics"][0]["message"]
        finally:
            os.unlink(fake_bin) if os.path.exists(fake_bin) else None
            server.documents.pop("file:///tmp/INCAR", None)

    def test_validate_error_exit_code(self):
        fake_bin = tempfile.mktemp(suffix="vasp_bin")
        try:
            with open(fake_bin, "w") as bh:
                bh.write("#!/bin/sh\necho 'FATAL: bad input' >&2\nexit 1\n")
            os.chmod(fake_bin, 0o755)

            server.set_document_content("file:///tmp/INCAR", "ENCUT = 400")
            result = json.loads(_handle_validate(["file:///tmp/INCAR", fake_bin]))
            assert result["status"] == "success"
            assert result["exit_code"] == 1
            assert any("FATAL" in d["message"] for d in result["diagnostics"])
        finally:
            os.unlink(fake_bin) if os.path.exists(fake_bin) else None
            server.documents.pop("file:///tmp/INCAR", None)

    def test_validate_generic_exception(self):
        """Test that generic exceptions during subprocess.run are caught."""
        fake_bin = tempfile.mktemp(suffix="vasp_bin")
        try:
            with open(fake_bin, "w") as bh:
                bh.write("#!/bin/sh\necho 'ok'\n")
            os.chmod(fake_bin, 0o755)

            server.set_document_content("file:///tmp/INCAR", "ENCUT = 400")
            with patch("vasp_lsp.server.subprocess.run", side_effect=OSError("permission denied")):
                result = json.loads(_handle_validate(["file:///tmp/INCAR", fake_bin]))
                assert result["status"] == "error"
                assert "permission denied" in result["message"]
        finally:
            os.unlink(fake_bin) if os.path.exists(fake_bin) else None
            server.documents.pop("file:///tmp/INCAR", None)

    def test_validate_severity_parsing(self):
        """Test that stdout/stderr lines are parsed into diagnostics with correct severity."""
        fake_bin = tempfile.mktemp(suffix="vasp_bin")
        try:
            with open(fake_bin, "w") as bh:
                bh.write(
                    "#!/bin/sh\necho 'INFO: all clear'\necho 'WARNING: low ENCUT' >&2\necho 'ERROR: fatal crash' >&2\n"
                )
            os.chmod(fake_bin, 0o755)

            server.set_document_content("file:///tmp/INCAR", "ENCUT = 400")
            result = json.loads(_handle_validate(["file:///tmp/INCAR", fake_bin]))
            assert result["status"] == "success"
            diags = result["diagnostics"]
            severities = [d["severity"] for d in diags]
            assert "information" in severities
            assert "warning" in severities
            assert "error" in severities
        finally:
            os.unlink(fake_bin) if os.path.exists(fake_bin) else None
            server.documents.pop("file:///tmp/INCAR", None)
