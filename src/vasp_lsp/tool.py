"""Agent-facing CLI for Diagnostic Engine v1 operations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import dsl_description
from .agent_operations import operation_path, with_capabilities
from .rich_diagnostics import agent_check_payload, diagnostic_to_dict
from .workspace import DocumentKind, document_kind

SOFTWARE = "vasp"
PLAN24_SCHEMA_VERSION = "vasp-lsp.plan24.v1"

_WORKSPACE_DOCUMENT_NAMES = frozenset(
    {
        "INCAR",
        "POSCAR",
        "CONTCAR",
        "KPOINTS",
        "POTCAR",
        "OUTCAR",
        "OSZICAR",
        "STDOUT",
        "STDERR",
        "VASP.OUT",
        "VASP.ERR",
    }
)


def _file_type(path: Path) -> str:
    kind = document_kind(path)
    if kind is not DocumentKind.UNKNOWN:
        return str(kind.value)
    if "." in path.name:
        return path.suffix.lstrip(".").lower()
    return path.name.lower()


def _collect_diagnostics(path: Path) -> list[Any]:
    from .features.diagnostics import DiagnosticsProvider

    text = path.read_text(encoding="utf-8")
    workspace_documents = _workspace_documents(path.parent)
    return list(
        DiagnosticsProvider().get_diagnostics(
            text,
            path.resolve().as_uri(),
            workspace_documents,
        )
    )


def check_path(path: Path) -> dict[str, Any]:
    uri = path.resolve().as_uri()
    diagnostics = _collect_diagnostics(path)
    return dict(
        agent_check_payload(
            software=SOFTWARE,
            uri=uri,
            operation="check",
            diagnostics=diagnostics,
            path=str(path),
            file_type=_file_type(path),
        )
    )


def rules_payload(rule_id: str | None = None) -> dict[str, Any]:
    """Build the rules-export payload for OpenQC and other catalog consumers.

    With no ``rule_id`` this exports the full rule manifest. With a
    ``rule_id`` it explains a single rule (mirrors ``explain`` semantics for
    rule metadata).
    """
    from .rules import RULES_MANIFEST, export_manifest, get_rule

    if rule_id is not None:
        rule = get_rule(rule_id)
        payload: dict[str, Any] = {
            "operation": "rules",
            "software": SOFTWARE,
            "rule_id": rule_id,
            "found": rule is not None,
            "rule": rule,
            "known_rule_ids": sorted(RULES_MANIFEST),
        }
        return with_capabilities(payload, "rules")
    payload = dict(export_manifest())
    payload["operation"] = "rules"
    payload["rule_count"] = len(RULES_MANIFEST)
    return with_capabilities(payload, "rules")


def check_target(path: Path) -> dict[str, Any]:
    """Build the PLAN24 JSON payload for an input file or calculation directory."""
    diagnostics_by_path = _collect_plan24_check_diagnostics(path)
    return _plan24_payload("check", [path], diagnostics_by_path)


def explain_logs(paths: list[Path], workdir: Path | None = None) -> dict[str, Any]:
    """Build the PLAN24 JSON payload for one or more runtime logs."""
    diagnostics_by_path = _collect_plan24_explain_diagnostics(paths, workdir)
    return _plan24_payload("explain", paths, diagnostics_by_path)


def _collect_plan24_check_diagnostics(path: Path) -> list[tuple[Path, list[Any]]]:
    from .features.diagnostics import DiagnosticsProvider

    provider = DiagnosticsProvider()
    if path.is_dir():
        workspace_documents = _workspace_documents(path)
        results: list[tuple[Path, list[Any]]] = []
        for candidate in sorted(path.iterdir()):
            if not _is_workspace_document(candidate):
                continue
            file_type = provider._get_file_type(candidate.resolve().as_uri())
            if file_type == "UNKNOWN":
                continue
            text = _read_text(candidate)
            results.append(
                (
                    candidate,
                    list(
                        provider.get_diagnostics(
                            text,
                            candidate.resolve().as_uri(),
                            workspace_documents,
                        )
                    ),
                )
            )
        return results

    workspace_documents = _workspace_documents(path.parent)
    return [
        (
            path,
            list(
                provider.get_diagnostics(
                    _read_text(path),
                    path.resolve().as_uri(),
                    workspace_documents,
                )
            ),
        )
    ]


def _collect_plan24_explain_diagnostics(
    paths: list[Path], workdir: Path | None = None
) -> list[tuple[Path, list[Any]]]:
    from .features.diagnostics import DiagnosticsProvider

    provider = DiagnosticsProvider()
    workspace_documents = _workspace_documents(workdir) if workdir else {}
    results: list[tuple[Path, list[Any]]] = []
    for path in paths:
        results.append(
            (
                path,
                list(
                    provider.get_diagnostics(
                        _read_text(path),
                        path.resolve().as_uri(),
                        workspace_documents,
                    )
                ),
            )
        )
    return results


def _workspace_documents(directory: Path) -> dict[str, str]:
    if not directory.exists() or not directory.is_dir():
        return {}
    documents: dict[str, str] = {}
    for path in sorted(directory.iterdir()):
        if _is_neighbor_document(path):
            try:
                documents[path.resolve().as_uri()] = _read_text(path)
            except OSError:
                # A workspace directory can contain files owned by another
                # process/user (especially /tmp). One unreadable peer should
                # not prevent checking the requested INCAR.
                continue
    return documents


def _is_neighbor_document(path: Path) -> bool:
    """Return whether *path* is a small input file needed as neighbor context."""
    if not path.is_file() or path.name.startswith("."):
        return False
    return document_kind(path) in {
        DocumentKind.INCAR,
        DocumentKind.POSCAR,
        DocumentKind.KPOINTS,
        DocumentKind.POTCAR,
    }


def _is_workspace_document(path: Path) -> bool:
    """Return whether *path* is a small VASP text document worth loading.

    Calculation directories commonly contain multi-gigabyte binary artifacts
    such as WAVECAR and CHGCAR. They are not inputs to the static text
    diagnostics, so reading them as UTF-8 merely adds I/O and memory pressure.
    Keep this allowlist deliberately narrow; in particular, POTCAR.spec is a
    VASPKIT metadata record, not a POTCAR document.
    """
    if not path.is_file() or path.name.startswith("."):
        return False
    name = path.name.upper()
    kind = document_kind(path)
    if kind in {
        DocumentKind.INCAR,
        DocumentKind.POSCAR,
        DocumentKind.KPOINTS,
        DocumentKind.POTCAR,
    }:
        return True
    if name in _WORKSPACE_DOCUMENT_NAMES:
        return True
    return name.startswith("SLURM-") and name.endswith((".OUT", ".ERR"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _plan24_payload(
    operation: str,
    sources: list[Path],
    diagnostics_by_path: list[tuple[Path, list[Any]]],
) -> dict[str, Any]:
    diagnostics = [
        _plan24_diagnostic(item, source_path)
        for source_path, source_diagnostics in diagnostics_by_path
        for item in source_diagnostics
    ]
    diagnostics.sort(
        key=lambda item: (
            item["source_file"],
            item["range"]["start"]["line"],
            item["range"]["start"]["character"],
            item["id"],
            item["message"],
        )
    )
    blocking_count = sum(1 for item in diagnostics if item["blocking"])
    return {
        "schema_version": PLAN24_SCHEMA_VERSION,
        "operation": operation,
        "ok": blocking_count == 0,
        "software": SOFTWARE,
        "source": [str(path) for path in sources],
        "diagnostics": diagnostics,
        "summary": {
            "count": len(diagnostics),
            "blocking": blocking_count,
            "errors": sum(1 for item in diagnostics if item["severity"] == "error"),
            "warnings": sum(1 for item in diagnostics if item["severity"] == "warning"),
        },
    }


def _plan24_diagnostic(diagnostic: Any, source_path: Path) -> dict[str, Any]:
    rich = diagnostic_to_dict(
        diagnostic,
        software=SOFTWARE,
        path=str(source_path),
        file_type=_file_type(source_path),
    )
    data = getattr(diagnostic, "data", None)
    if not isinstance(data, dict):
        data = {}
    suggested_actions = data.get("suggested_actions")
    if not isinstance(suggested_actions, list):
        suggested_actions = [
            {"title": hint, "safe_to_auto_apply": True, "target_file": _file_type(source_path)}
            for hint in rich.get("fix_hints", [])
        ]
    related_files = data.get("related_files", [])
    if not isinstance(related_files, list):
        related_files = []
    return {
        "id": rich["code"],
        "severity": rich["severity"],
        "message": rich["message"],
        "source": rich["source"],
        "source_file": str(source_path),
        "file_type": rich["file_type"],
        "range": rich["range"],
        "confidence": data.get("confidence", rich["confidence"]),
        "category": data.get("category", rich["category"]),
        "related_files": related_files,
        "suggested_actions": suggested_actions,
        "blocking": rich["blocking"],
    }


def _operation_payload(
    path: Path,
    operation: str,
    line: int = 0,
    character: int = 0,
) -> dict[str, Any]:
    return operation_path(
        path,
        operation,
        software=SOFTWARE,
        file_type_func=_file_type,
        collect_diagnostics=_collect_diagnostics,
        line=line,
        character=character,
    )


def check_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vasp-lsp-check")
    parser.add_argument("path", type=Path)
    parser.add_argument("--format", choices=["json"], default="json")
    parser.add_argument("--fail-on-blocking", action="store_true")
    args = parser.parse_args(argv)
    payload = check_target(args.path)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if args.fail_on_blocking and not payload["ok"] else 0


def explain_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vasp-lsp-explain")
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--format", choices=["json"], default="json")
    parser.add_argument("--workdir", type=Path)
    parser.add_argument("--fail-on-blocking", action="store_true")
    args = parser.parse_args(argv)
    payload = explain_logs(args.logs, args.workdir)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if args.fail_on_blocking and not payload["ok"] else 0


def describe_main(argv: list[str] | None = None) -> int:
    """Console entry for ``vasp-lsp-describe``: print the DSL overview JSON (#29)."""
    parser = argparse.ArgumentParser(prog="vasp-lsp-describe")
    parser.add_argument("--format", choices=["json"], default="json")
    parser.parse_args(argv)
    payload = with_capabilities(dsl_description.describe_language(), "describe")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def schema_main(argv: list[str] | None = None) -> int:
    """Console entry for ``vasp-lsp-schema``: print the keyword schema JSON (#30)."""
    parser = argparse.ArgumentParser(prog="vasp-lsp-schema")
    parser.add_argument("keyword", help="INCAR keyword to look up (e.g. ENCUT).")
    parser.add_argument("--format", choices=["json"], default="json")
    args = parser.parse_args(argv)
    payload = with_capabilities(dsl_description.describe_keyword(args.keyword), "schema")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def schema_audit_main(argv: list[str] | None = None) -> int:
    """Console entry for the offline official-Wiki schema audit."""
    parser = argparse.ArgumentParser(prog="vasp-lsp-schema-audit")
    parser.add_argument("--format", choices=["json"], default="json")
    parser.parse_args(argv)
    from .schema_audit import audit_schema

    payload = with_capabilities(audit_schema(), "schema-audit")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


def examples_main(argv: list[str] | None = None) -> int:
    """Console entry for ``vasp-lsp-examples``: print minimal example JSON (#31)."""
    parser = argparse.ArgumentParser(prog="vasp-lsp-examples")
    parser.add_argument(
        "calculation_type",
        nargs="?",
        default="static",
        help="Calculation pattern (e.g. static, relaxation, spin_polarized).",
    )
    parser.add_argument("--format", choices=["json"], default="json")
    args = parser.parse_args(argv)
    payload = with_capabilities(
        dsl_description.make_minimal_example(args.calculation_type), "examples"
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vasp-lsp-tool")
    subparsers = parser.add_subparsers(dest="operation", required=True)
    for operation in (
        "check",
        "context",
        "complete",
        "hover",
        "symbols",
        "fix",
        "rules",
        "describe",
        "schema",
        "schema-audit",
        "section",
        "examples",
        "next-tokens",
        "explain",
    ):
        sub = subparsers.add_parser(operation)
        # Catalog-only operations take no file path.
        if operation == "rules":
            sub.add_argument(
                "rule_id",
                nargs="?",
                help="Optional rule_id to explain (e.g. vasp.incar.invalid_tag).",
            )
        elif operation == "describe":
            # ``describe`` takes no arguments (language overview).
            pass
        elif operation == "schema":
            sub.add_argument("keyword", help="INCAR keyword to look up.")
        elif operation == "schema-audit":
            pass
        elif operation == "section":
            sub.add_argument("section", help="VASP section/file type to look up.")
        elif operation == "examples":
            sub.add_argument(
                "calculation_type",
                nargs="?",
                default="static",
                help="Calculation pattern (e.g. static, relaxation, spin_polarized).",
            )
        elif operation == "next-tokens":
            sub.add_argument(
                "context",
                nargs="?",
                default="",
                help="Cursor context (the last meaningful token on the line).",
            )
        elif operation == "explain":
            sub.add_argument("rule_id", help="Rule id to explain.")
        else:
            sub.add_argument("path", type=Path)
        sub.add_argument("--format", choices=["json"], default="json")
        sub.add_argument(
            "--line",
            type=int,
            default=0,
            help="0-based line for position-aware operations.",
        )
        sub.add_argument(
            "--character",
            type=int,
            default=0,
            help="0-based character for position-aware operations.",
        )
        if operation == "check":
            sub.add_argument("--fail-on-blocking", action="store_true")
    args = parser.parse_args(argv)
    if args.operation == "check":
        payload = with_capabilities(check_path(args.path), "check")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1 if getattr(args, "fail_on_blocking", False) and not payload["ok"] else 0
    if args.operation == "rules":
        payload = rules_payload(getattr(args, "rule_id", None))
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.operation == "describe":
        payload = with_capabilities(dsl_description.describe_language(), "describe")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.operation == "schema":
        payload = with_capabilities(dsl_description.describe_keyword(args.keyword), "schema")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.operation == "schema-audit":
        from .schema_audit import audit_schema

        payload = with_capabilities(audit_schema(), "schema-audit")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["ok"] else 1
    if args.operation == "section":
        payload = with_capabilities(dsl_description.describe_section(args.section), "section")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.operation == "examples":
        payload = with_capabilities(
            dsl_description.make_minimal_example(args.calculation_type), "examples"
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.operation == "next-tokens":
        payload = with_capabilities(
            dsl_description.suggest_next_tokens(args.context), "next-tokens"
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.operation == "explain":
        payload = with_capabilities(dsl_description.rule_explain(args.rule_id), "explain")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    payload = _operation_payload(args.path, args.operation, args.line, args.character)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
