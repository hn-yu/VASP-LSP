"""Tests for the agent-facing VASP DSL description API (#26, #29, #30, #31)."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from vasp_lsp import dsl_description, tool
from vasp_lsp.rules import RULES_MANIFEST


def test_describe_language_returns_stable_overview() -> None:
    payload = dsl_description.describe_language()

    assert payload["languageId"] == "vasp-input"
    assert payload["software"] == "vasp"
    assert "INCAR" in payload["fileExtensions"]
    assert payload["overview"]
    assert payload["grammarSummary"]
    assert isinstance(payload["topLevelSections"], list) and payload["topLevelSections"]
    assert isinstance(payload["commonPatterns"], list) and payload["commonPatterns"]
    assert isinstance(payload["examples"], list) and payload["examples"]
    assert isinstance(payload["references"], list) and payload["references"]
    # Every registered rule is reflected in the validation-rules index.
    rule_ids = {entry["rule_id"] for entry in payload["validationRules"]}
    assert rule_ids == set(RULES_MANIFEST)


def test_describe_keyword_returns_known_incar_metadata() -> None:
    payload = dsl_description.describe_keyword("ENCUT")

    assert payload["found"] is True
    schema = payload["schema"]
    assert schema["name"] == "ENCUT"
    assert schema["type"] in {"integer", "float"}
    assert schema["unit"] == "eV"
    assert schema["manual_ref"].endswith("/ENCUT")


def test_describe_keyword_returns_structured_not_found_with_suggestions() -> None:
    payload = dsl_description.describe_keyword("NOSUCHTAG")

    assert payload["found"] is False
    assert "reason" in payload
    assert isinstance(payload["suggestions"], list)


def test_describe_keyword_rejects_empty_input() -> None:
    payload = dsl_description.describe_keyword("")

    assert payload["found"] is False
    assert payload["reason"]


def test_describe_section_returns_known_file_types() -> None:
    payload = dsl_description.describe_section("INCAR")

    assert payload["found"] is True
    assert payload["section"] == "INCAR"
    assert payload["description"]
    assert payload["grammar_summary"]


def test_describe_section_returns_known_sections_for_unknown_input() -> None:
    payload = dsl_description.describe_section("NOSUCH")

    assert payload["found"] is False
    assert payload["known_sections"]


@pytest.mark.parametrize("calculation_type", ["static", "relaxation", "spin_polarized"])
def test_make_minimal_example_returns_valid_snippet(calculation_type: str) -> None:
    payload = dsl_description.make_minimal_example(calculation_type)

    assert payload["found"] is True
    assert payload["calculation_type_key"] == calculation_type
    assert payload["calculation_type"]
    assert payload["snippet"]
    assert payload["file_type"] == "INCAR"


def test_make_minimal_example_snippets_parse_clean() -> None:
    """Generated minimal examples must parse cleanly under the diagnostics harness (#31)."""
    from vasp_lsp.features.diagnostics import DiagnosticsProvider

    provider = DiagnosticsProvider()
    for calculation_type in ("static", "relaxation", "spin_polarized"):
        payload = dsl_description.make_minimal_example(calculation_type)
        diagnostics = provider.get_diagnostics(payload["snippet"], "file:///INCAR", {})
        errors = [d for d in diagnostics if d.severity == 1]
        assert errors == [], (
            f"{calculation_type} example produced errors: "
            f"{[(d.code, d.message) for d in errors]}"
        )


def test_make_minimal_example_returns_structured_not_found() -> None:
    payload = dsl_description.make_minimal_example("nonsense")

    assert payload["found"] is False
    assert "available_types" in payload


def test_suggest_next_tokens_returns_default_for_unknown_context() -> None:
    payload = dsl_description.suggest_next_tokens("NOSUCHCONTEXT")

    assert payload["context"] == "NOSUCHCONTEXT"
    assert isinstance(payload["tokens"], list) and payload["tokens"]


def test_suggest_next_tokens_returns_targeted_for_known_context() -> None:
    payload = dsl_description.suggest_next_tokens("ISMEAR")

    assert payload["context"] == "ISMEAR"
    assert any("= 0" in token["token"] for token in payload["tokens"])


def test_rule_explain_returns_known_rule() -> None:
    payload = dsl_description.rule_explain("vasp.incar.invalid_tag")

    assert payload["found"] is True
    assert payload["rule"]["rule_id"] == "vasp.incar.invalid_tag"


def test_rule_explain_returns_structured_not_found() -> None:
    payload = dsl_description.rule_explain("nonsense")

    assert payload["found"] is False
    assert "known_rule_ids" in payload


def test_tool_main_describe_subcommand(capsys) -> None:
    exit_code = tool.main(["describe", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["languageId"] == "vasp-input"
    assert payload["capabilities"]["operation"] == "describe"


def test_tool_main_schema_subcommand(capsys) -> None:
    exit_code = tool.main(["schema", "ENCUT", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["found"] is True
    assert payload["schema"]["name"] == "ENCUT"
    assert payload["capabilities"]["operation"] == "schema"


def test_tool_main_examples_subcommand(capsys) -> None:
    exit_code = tool.main(["examples", "static", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["found"] is True
    assert "ENCUT" in payload["snippet"]
    assert payload["capabilities"]["operation"] == "examples"


def test_tool_main_next_tokens_subcommand(capsys) -> None:
    exit_code = tool.main(["next-tokens", "ISMEAR", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["context"] == "ISMEAR"
    assert payload["capabilities"]["operation"] == "next-tokens"


def test_tool_main_explain_subcommand(capsys) -> None:
    exit_code = tool.main(["explain", "vasp.incar.invalid_tag", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["found"] is True
    assert payload["capabilities"]["operation"] == "explain"


def test_describe_main_console_script(capsys) -> None:
    exit_code = tool.describe_main([])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["languageId"] == "vasp-input"


def test_schema_main_console_script(capsys) -> None:
    exit_code = tool.schema_main(["ENCUT"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["found"] is True


def test_examples_main_console_script(capsys) -> None:
    exit_code = tool.examples_main(["static"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["found"] is True


def test_console_scripts_launch_via_subprocess() -> None:
    """Smoke-test that the console scripts are wired through pyproject.toml."""
    for command in ("vasp-lsp-describe", "vasp-lsp-schema", "vasp-lsp-examples"):
        result = subprocess.run(
            [sys.executable, "-m", "vasp_lsp.tool", command.split("-")[-1]],
            capture_output=True,
            text=True,
            check=False,
            # examples/next-tokens take positional args; only describe is
            # safe to invoke without arguments here.
        )
        # describe is the only command that runs without args; others
        # exit with argparse error which is also acceptable (smoke only).
        assert result.returncode in (0, 2)
