"""
Tests for INCAR parser.
"""

import pytest

from vasp_lsp.parsers.incar_parser import INCARParser


class TestINCARParser:
    """Test cases for INCARParser."""

    def test_parse_empty_content(self):
        """Test parsing empty content."""
        parser = INCARParser("")
        params = parser.parse()
        assert params == {}
        assert parser.get_errors() == []

    def test_parse_single_parameter(self):
        """Test parsing a single parameter."""
        content = "ENCUT = 520"
        parser = INCARParser(content)
        params = parser.parse()

        assert len(params) == 1
        assert "ENCUT" in params
        assert params["ENCUT"].value == 520
        assert params["ENCUT"].line_number == 1

    def test_parse_multiple_parameters(self):
        """Test parsing multiple parameters."""
        content = """
        ENCUT = 520
        ISMEAR = 0
        SIGMA = 0.05
        """
        parser = INCARParser(content)
        params = parser.parse()

        assert len(params) == 3
        assert params["ENCUT"].value == 520
        assert params["ISMEAR"].value == 0
        assert params["SIGMA"].value == pytest.approx(0.05)

    def test_parse_boolean_true(self):
        """Test parsing boolean true values."""
        for value in [".TRUE.", "T", "TRUE", ".true.", "t", "true"]:
            parser = INCARParser(f"LDAU = {value}")
            params = parser.parse()
            assert params["LDAU"].value is True, f"Failed for {value}"

    def test_parse_boolean_false(self):
        """Test parsing boolean false values."""
        for value in [".FALSE.", "F", "FALSE", ".false.", "f", "false"]:
            parser = INCARParser(f"LDAU = {value}")
            params = parser.parse()
            assert params["LDAU"].value is False, f"Failed for {value}"

    def test_parse_float_values(self):
        """Test parsing float values."""
        content = "EDIFF = 1.0e-6"
        parser = INCARParser(content)
        params = parser.parse()
        assert params["EDIFF"].value == pytest.approx(1.0e-6)

    def test_parse_integer_values(self):
        """Test parsing integer values."""
        content = "NSW = 100"
        parser = INCARParser(content)
        params = parser.parse()
        assert params["NSW"].value == 100
        assert isinstance(params["NSW"].value, int)

    def test_parse_string_values(self):
        """Test parsing string values."""
        content = "SYSTEM = Test"
        parser = INCARParser(content)
        params = parser.parse()
        # String without spaces is treated as simple string
        assert params["SYSTEM"].value == "Test"

    def test_parse_array_values(self):
        """Test parsing array values."""
        content = "MAGMOM = 5 5 5"
        parser = INCARParser(content)
        params = parser.parse()
        assert params["MAGMOM"].value == [5, 5, 5]

    def test_parse_multiword_values_as_strings(self):
        """Non-numeric whitespace-separated values remain one INCAR string."""
        content = "ALGO = Old Fast\nSYSTEM = Fe2 surface"
        parser = INCARParser(content)
        params = parser.parse()

        assert params["ALGO"].value == "Old Fast"
        assert params["SYSTEM"].value == "Fe2 surface"

    def test_parse_comments_hash(self):
        """Test parsing with # comments."""
        content = """
        ENCUT = 520  # Cutoff energy
        # This is a comment
        ISMEAR = 0
        """
        parser = INCARParser(content)
        params = parser.parse()

        assert len(params) == 2
        assert "ENCUT" in params
        assert "ISMEAR" in params

    def test_parse_comments_exclamation(self):
        """Test parsing with ! comments."""
        content = """
        ENCUT = 520  ! Cutoff energy
        ! This is a comment
        ISMEAR = 0
        """
        parser = INCARParser(content)
        params = parser.parse()

        assert len(params) == 2
        assert "ENCUT" in params
        assert "ISMEAR" in params

    def test_parse_duplicate_parameter(self):
        """Test parsing duplicate parameters (should warn)."""
        content = """
        ENCUT = 500
        ENCUT = 520
        """
        parser = INCARParser(content)
        params = parser.parse()

        # Should have the second value
        assert params["ENCUT"].value == 520

        # Should have a warning
        errors = parser.get_errors()
        assert len(errors) == 1
        assert errors[0]["severity"] == "warning"
        assert "Duplicate" in errors[0]["message"]

    def test_parse_invalid_format(self):
        """Test parsing invalid format."""
        content = "This is not a valid parameter"
        parser = INCARParser(content)
        parser.parse()

        errors = parser.get_errors()
        assert len(errors) == 1
        assert errors[0]["severity"] == "error"

    def test_get_parameter(self):
        """Test get_parameter method."""
        content = "ENCUT = 520"
        parser = INCARParser(content)
        parser.parse()

        param = parser.get_parameter("ENCUT")
        assert param is not None
        assert param.value == 520

        # Test case insensitivity
        param = parser.get_parameter("encut")
        assert param is not None

        # Test non-existent parameter
        param = parser.get_parameter("NONEXISTENT")
        assert param is None

    def test_has_parameter(self):
        """Test has_parameter method."""
        content = "ENCUT = 520"
        parser = INCARParser(content)
        parser.parse()

        assert parser.has_parameter("ENCUT") is True
        assert parser.has_parameter("encut") is True  # Case insensitive
        assert parser.has_parameter("NONEXISTENT") is False

    def test_get_all_parameters(self):
        """Test get_all_parameters method."""
        content = "ENCUT = 520\nISMEAR = 0"
        parser = INCARParser(content)
        parser.parse()

        all_params = parser.get_all_parameters()
        assert len(all_params) == 2
        assert "ENCUT" in all_params
        assert "ISMEAR" in all_params

    def test_whitespace_handling(self):
        """Test handling of various whitespace."""
        content = "ENCUT=520\nISMEAR  =  0\nSIGMA= 0.05"
        parser = INCARParser(content)
        params = parser.parse()

        assert len(params) == 3
        assert params["ENCUT"].value == 520
        assert params["ISMEAR"].value == 0
        assert params["SIGMA"].value == pytest.approx(0.05)

    def test_complex_incar(self):
        """Test parsing a complex INCAR file."""
        content = """
        # VASP INCAR file
        SYSTEM = DFT
        ! Basic parameters
        ENCUT = 520
        ISMEAR = 0
        SIGMA = 0.05
        EDIFF = 1.0e-6
        NSW = 100
        ISIF = 3
        IBRION = 2
        POTIM = 0.5
        ! Magnetic moments
        MAGMOM = 5 5 5 -5
        LDAU = .TRUE.
        """
        parser = INCARParser(content)
        params = parser.parse()

        assert len(params) == 11  # SYSTEM + 10 other params
        assert parser.get_errors() == []
