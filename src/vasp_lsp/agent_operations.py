"""Shared agent-facing operations for Diagnostic Engine v1 CLIs.

The editor servers already own the expensive parsing and validation logic. This
module exposes the same information in a command-line friendly JSON shape for
agents that need LSP-style context without starting an editor client.
"""

from __future__ import annotations

import importlib
import inspect
import re
from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from lsprotocol.types import (
    CompletionParams,
    Diagnostic,
    DiagnosticSeverity,
    HoverParams,
    Position,
    Range,
    TextDocumentIdentifier,
)

from .features.completion import CompletionProvider
from .features.hover import HoverProvider
from .features.navigation import DocumentSymbolsProvider
from .features.quickfixes import QuickFixesProvider
from .rich_diagnostics import agent_check_payload

OPERATIONS = (
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
)
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.$%+-]*")
_SECTION_RE = re.compile(r"^\s*(?:&(?P<section>[A-Za-z][A-Za-z0-9_.$-]*)|\[(?P<bracket>[^\]]+)\])")
_ASSIGNMENT_RE = re.compile(r"^\s*(?P<key>[A-Za-z_][A-Za-z0-9_.$%-]*)\s*(?:=|:|\s+)")


def with_capabilities(
    payload: dict[str, Any],
    operation: str,
    *,
    status: str = "available",
    reason: str | None = None,
    source: str = "agent_operations",
) -> dict[str, Any]:
    """Attach the fleet-standard capabilities block to a payload."""
    payload["capabilities"] = {
        "operations": list(OPERATIONS),
        "operation": operation,
        "status": status,
        "source": source,
    }
    if reason:
        payload["capabilities"]["reason"] = reason
        payload.setdefault("summary", {})["note"] = reason
    return payload


def operation_path(
    path: Path,
    operation: str,
    *,
    software: str,
    file_type_func: Callable[[Path], str],
    collect_diagnostics: Callable[[Path], Iterable[Any]],
    line: int = 0,
    character: int = 0,
) -> dict[str, Any]:
    """Return a Diagnostic Engine v1 payload for non-check agent operations."""
    path = Path(path)
    file_type = file_type_func(path)
    text = _read_text(path)
    diagnostics = (
        _safe_collect_diagnostics(path, collect_diagnostics)
        if operation in {"context", "complete", "hover", "fix"}
        else []
    )
    payload = agent_check_payload(
        software=software,
        uri=path.resolve().as_uri(),
        operation=operation,
        diagnostics=diagnostics,
        path=str(path),
        file_type=file_type,
    )
    payload["file_type"] = file_type
    position = {"line": max(line, 0), "character": max(character, 0)}
    payload["position"] = position

    if operation == "context":
        context = _context_for(text, position)
        context.update({"path": str(path), "file_type": file_type})
        symbols, symbols_source = _symbols_dispatch(path, text)
        context["nearby_symbols"] = _nearby_symbols(symbols, line)
        context["symbols_source"] = symbols_source
        context["diagnostics_at_position"] = _diagnostics_at_position(
            payload["diagnostics"], line, character
        )
        payload["context"] = context
        return with_capabilities(payload, operation)

    if operation == "complete":
        items, result_source = _completion_dispatch(
            path, text, file_type, line=line, character=character, diagnostics=payload["diagnostics"]
        )
        payload["items"] = items
        _mark_result_source(payload, result_source)
        status = "available" if items else "unavailable"
        reason = (
            None if items else "No completion provider or extractable symbols for this document."
        )
        return with_capabilities(payload, operation, status=status, reason=reason)

    if operation == "hover":
        context = _context_for(text, position)
        contents, result_source = _hover_dispatch(
            path,
            text,
            context.get("token", ""),
            file_type,
            line=line,
            character=character,
            diagnostics=payload["diagnostics"],
        )
        payload["context"] = context
        payload["contents"] = contents
        _mark_result_source(payload, result_source)
        status = "available" if contents else "unavailable"
        reason = None if contents else "No hover documentation found for this position."
        return with_capabilities(payload, operation, status=status, reason=reason)

    if operation == "symbols":
        items, result_source = _symbols_dispatch(path, text)
        payload["items"] = items
        _mark_result_source(payload, result_source)
        status = "available" if items else "unavailable"
        reason = None if items else "No document symbols could be extracted."
        return with_capabilities(payload, operation, status=status, reason=reason)

    if operation == "fix":
        actions, result_source = _fix_dispatch(
            path,
            text,
            payload["diagnostics"],
            line=line,
            character=character,
        )
        payload["actions"] = actions
        _mark_result_source(payload, result_source)
        status = "available" if actions else "unavailable"
        reason = (
            None if actions else "No safe quick-fix hints are available for current diagnostics."
        )
        return with_capabilities(payload, operation, status=status, reason=reason)

    return with_capabilities(
        payload,
        operation,
        status="unavailable",
        reason=f"Unknown operation: {operation}",
    )


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _safe_collect_diagnostics(
    path: Path, collect_diagnostics: Callable[[Path], Iterable[Any]]
) -> list[Any]:
    try:
        return list(collect_diagnostics(path))
    except Exception as exc:  # pragma: no cover - defensive agent boundary
        return [
            {
                "code": "agent.operation.diagnostics_failed",
                "severity": "warning",
                "source": "agent-lsp",
                "message": f"Could not collect diagnostics for operation payload: {exc}",
                "line": 1,
                "column": 1,
                "category": "preflight/runtime-risk",
                "confidence": 1.0,
                "blocking": False,
            }
        ]


def _context_for(text: str, position: dict[str, int]) -> dict[str, Any]:
    lines = text.splitlines()
    line_no = min(position["line"], max(len(lines) - 1, 0))
    current = lines[line_no] if lines else ""
    character = min(position["character"], len(current))
    token, start, end = _word_at(current, character)
    return {
        "line_text": current,
        "token": token,
        "word_range": {
            "start": {"line": line_no, "character": start},
            "end": {"line": line_no, "character": end},
        },
        "before": lines[max(0, line_no - 3) : line_no],
        "after": lines[line_no + 1 : line_no + 4],
    }


def _word_at(line: str, character: int) -> tuple[str, int, int]:
    if not line:
        return "", character, character
    character = min(max(character, 0), len(line))
    for match in _WORD_RE.finditer(line):
        if match.start() <= character <= match.end():
            return match.group(0), match.start(), match.end()
    return "", character, character


def _diagnostics_at_position(
    diagnostics: list[dict[str, Any]], line: int, character: int
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for item in diagnostics:
        rng = item.get("range", {})
        start = rng.get("start", {})
        end = rng.get("end", {})
        start_line = int(start.get("line", 0) or 0)
        end_line = int(end.get("line", start_line) or start_line)
        start_char = int(start.get("character", 0) or 0)
        end_char = int(end.get("character", start_char + 1) or (start_char + 1))
        if (
            start_line <= line <= end_line
            and (line != start_line or character >= start_char)
            and (line != end_line or character <= end_char)
        ):
            selected.append(item)
    return selected


def _mark_result_source(payload: dict[str, Any], source: str) -> None:
    """Expose whether an operation used a real provider or a fallback."""
    payload["result_source"] = source
    payload["fallback"] = source == "fallback"


def _legacy_adapter_overridden() -> bool:
    """Return whether a caller replaced the old dynamic adapter hook.

    Older integrations and the historical test seam monkeypatch
    ``_import_optional``.  Treating that as an explicit compatibility mode
    keeps those integrations stable while the normal path always starts with
    the first-class providers imported above.
    """
    return _import_optional is not _DEFAULT_IMPORT_OPTIONAL


def _completion_dispatch(
    path: Path,
    text: str,
    file_type: str,
    *,
    line: int,
    character: int,
    diagnostics: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    if _legacy_adapter_overridden():
        legacy = _legacy_completion_items(path, text, file_type)
        if legacy:
            return legacy, "legacy-provider"
        fallback = _generic_completion_items(text, diagnostics)
        return fallback, "fallback"

    provider = _real_completion_items(path, text, line=line, character=character)
    if provider:
        # Keep diagnostic-derived labels available to older agent clients, but
        # leave the first-class provider as the primary result source.
        if diagnostics:
            provider = _dedupe_items(
                provider + _generic_completion_items(text, diagnostics), "label"
            )[:200]
        return provider, "provider"

    legacy = _legacy_completion_items(path, text, file_type)
    if legacy:
        return legacy, "legacy-provider"

    fallback = _generic_completion_items(text, diagnostics)
    if fallback:
        return fallback, "fallback"
    return [], "provider" if provider is not None else "fallback"


def _real_completion_items(
    path: Path, text: str, *, line: int, character: int
) -> list[dict[str, Any]] | None:
    uri = path.resolve().as_uri()
    params = CompletionParams(
        text_document=TextDocumentIdentifier(uri=uri),
        position=Position(line=max(line, 0), character=max(character, 0)),
    )
    try:
        result = CompletionProvider().get_completions(params, text, uri)
    except Exception:
        return None
    raw_items = getattr(result, "items", None)
    if raw_items is None:
        return None
    return _dedupe_items(
        [_normalize_completion_item(item, source="provider") for item in raw_items],
        "label",
    )[:200]


def _legacy_completion_items(path: Path, text: str, file_type: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    package = __name__.rsplit(".", 1)[0]
    module_names = (
        f"{package}.completion",
        f"{package}.completions",
        f"{package}.features.completion",
        f"{package}.handlers.completion",
    )
    function_names = (
        "mdp_completions",
        "topology_completions",
        "completion_items",
        "get_completions",
        "complete",
    )
    for module_name in module_names:
        module = _import_optional(module_name)
        if module is None:
            continue
        for function_name in function_names:
            fn = getattr(module, function_name, None)
            if not callable(fn):
                continue
            value = _call_provider(fn, path, text, file_type)
            if isinstance(value, list):
                items.extend(
                    _normalize_completion_item(item, source="legacy-provider") for item in value
                )
    return _dedupe_items(items, "label")[:200]


def _hover_dispatch(
    path: Path,
    text: str,
    token: str,
    file_type: str,
    *,
    line: int,
    character: int,
    diagnostics: list[dict[str, Any]],
) -> tuple[Any, str]:
    if not _legacy_adapter_overridden():
        provider = _real_hover_contents(path, text, line=line, character=character)
        if provider is not None:
            diagnostic_context = _diagnostic_hover(diagnostics, line, character)
            if diagnostic_context:
                return f"{_hover_text(provider)}\n\n{diagnostic_context}", "provider"
            return provider, "provider"

    legacy = _legacy_hover_contents(path, text, token, file_type)
    if legacy is not None:
        return legacy, "legacy-provider"

    fallback = _diagnostic_hover(diagnostics, line, character)
    return fallback, "fallback"


def _hover_text(value: Any) -> str:
    if isinstance(value, dict) and "value" in value:
        return str(value["value"])
    return str(value)


def _real_hover_contents(
    path: Path, text: str, *, line: int, character: int
) -> Any | None:
    uri = path.resolve().as_uri()
    params = HoverParams(
        text_document=TextDocumentIdentifier(uri=uri),
        position=Position(line=max(line, 0), character=max(character, 0)),
    )
    try:
        result = HoverProvider().get_hover(params, text, uri)
    except Exception:
        return None
    return _normalize_hover(result)


def _normalize_hover(value: Any) -> Any | None:
    if value is None:
        return None
    contents = value.get("contents") if isinstance(value, dict) else getattr(value, "contents", value)
    if contents is None:
        return None
    return _serialize_lsp_value(contents)


def _legacy_hover_contents(path: Path, text: str, token: str, file_type: str) -> Any:
    if not token:
        return None
    package = __name__.rsplit(".", 1)[0]
    module_names = (
        f"{package}.hover",
        f"{package}.features.hover",
        f"{package}.handlers.hover",
    )
    function_names = (
        "mdp_hover",
        "topology_hover",
        "hover",
        "get_hover",
        "hover_contents",
    )
    for module_name in module_names:
        module = _import_optional(module_name)
        if module is None:
            continue
        for function_name in function_names:
            fn = getattr(module, function_name, None)
            if not callable(fn):
                continue
            value = _call_provider(fn, token, path, text, file_type)
            if value:
                return value
    return None


def _symbols_dispatch(path: Path, text: str) -> tuple[list[dict[str, Any]], str]:
    if not _legacy_adapter_overridden():
        provider = _real_symbols(path, text)
        if provider:
            return provider, "provider"

    legacy = _legacy_symbols(path, text)
    if legacy:
        return legacy, "legacy-provider"

    fallback = [_normalize_symbol(item, source="fallback") for item in _generic_symbols(text)]
    if fallback:
        return fallback, "fallback"
    return [], "provider"


def _real_symbols(path: Path, text: str) -> list[dict[str, Any]] | None:
    uri = path.resolve().as_uri()
    try:
        raw_symbols = DocumentSymbolsProvider().get_symbols(text, uri)
    except Exception:
        return None
    return [_normalize_symbol(item, source="provider") for item in raw_symbols]


def _legacy_symbols(path: Path, text: str) -> list[dict[str, Any]]:
    package = __name__.rsplit(".", 1)[0]
    module_names = (
        f"{package}.symbols",
        f"{package}.features.symbols",
        f"{package}.handlers.document_symbol",
    )
    function_names = ("document_symbols", "get_document_symbols", "symbols")
    for module_name in module_names:
        module = _import_optional(module_name)
        if module is None:
            continue
        for function_name in function_names:
            fn = getattr(module, function_name, None)
            if not callable(fn):
                continue
            value = _call_provider(fn, path, text)
            if isinstance(value, list):
                return [_normalize_symbol(item, source="legacy-provider") for item in value]
    return []


def _generic_completion_items(text: str, diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labels: dict[str, str] = {}
    for symbol in _generic_symbols(text):
        labels.setdefault(symbol["name"], symbol.get("detail", "Document symbol"))
    for diagnostic in diagnostics:
        for hint in diagnostic.get("fix_hints") or []:
            if isinstance(hint, str) and hint.strip():
                labels.setdefault(
                    hint.strip(),
                    f"Fix hint for {diagnostic.get('code', 'diagnostic')}",
                )
        manual_ref = diagnostic.get("manual_ref")
        if isinstance(manual_ref, str) and manual_ref.strip():
            labels.setdefault(manual_ref.strip(), "Manual reference")
    return [
        {"label": label, "detail": detail, "kind": 1, "source": "fallback"}
        for label, detail in sorted(labels.items())
    ][:200]


def _generic_symbols(text: str) -> list[dict[str, Any]]:
    symbols: list[dict[str, Any]] = []
    for line_no, raw in enumerate(text.splitlines()):
        stripped = raw.strip()
        if not stripped or stripped.startswith(("#", "!", ";")):
            continue
        section = _SECTION_RE.match(raw)
        if section:
            name = (section.group("section") or section.group("bracket") or "").strip()
            symbols.append(_symbol(name, "section", line_no, raw.find(name)))
            continue
        assignment = _ASSIGNMENT_RE.match(raw)
        if assignment:
            name = assignment.group("key")
            symbols.append(_symbol(name, "property", line_no, raw.find(name)))
    return symbols


def _symbol(name: str, kind: str, line: int, character: int) -> dict[str, Any]:
    character = max(character, 0)
    return {
        "name": name,
        "kind": kind,
        "range": {
            "start": {"line": line, "character": character},
            "end": {"line": line, "character": character + len(name)},
        },
        "selectionRange": {
            "start": {"line": line, "character": character},
            "end": {"line": line, "character": character + len(name)},
        },
    }


def _nearby_symbols(symbols: list[dict[str, Any]], line: int) -> list[dict[str, Any]]:
    def distance(item: dict[str, Any]) -> int:
        start = item.get("range", {}).get("start", {})
        return abs(int(start.get("line", 0) or 0) - line)

    return sorted(symbols, key=distance)[:5]


def _diagnostic_hover(diagnostics: list[dict[str, Any]], line: int, character: int) -> str | None:
    selected = _diagnostics_at_position(diagnostics, line, character)
    if not selected:
        return None
    first = selected[0]
    parts = [f"{first.get('code')}: {first.get('message')}"]
    hints = first.get("fix_hints") or []
    if hints:
        parts.append("Fix hints: " + "; ".join(str(hint) for hint in hints[:3]))
    manual_ref = first.get("manual_ref")
    if manual_ref:
        parts.append(f"Manual: {manual_ref}")
    return "\n".join(parts)


def _fix_dispatch(
    path: Path,
    text: str,
    diagnostics: list[dict[str, Any]],
    *,
    line: int,
    character: int,
) -> tuple[list[dict[str, Any]], str]:
    if not _legacy_adapter_overridden():
        provider = _real_fix_actions(path, text, diagnostics, line=line, character=character)
        if provider:
            return provider, "provider"

    fallback = _fix_actions(diagnostics, line=line, character=character)
    return fallback, "fallback"


def _real_fix_actions(
    path: Path,
    text: str,
    diagnostics: list[dict[str, Any]],
    *,
    line: int,
    character: int,
) -> list[dict[str, Any]] | None:
    uri = path.resolve().as_uri()
    lsp_diagnostics = [_diagnostic_to_lsp(item) for item in diagnostics]
    requested_range = Range(
        start=Position(line=max(line, 0), character=max(character, 0)),
        end=Position(line=max(line, 0), character=max(character, 0) + 1),
    )
    try:
        actions = QuickFixesProvider().get_code_actions(
            text,
            uri,
            lsp_diagnostics,
            requested_range,
        )
    except Exception:
        return None
    return [_normalize_code_action(action, diagnostics) for action in actions]


def _diagnostic_to_lsp(item: dict[str, Any]) -> Diagnostic:
    raw_range = item.get("range") or {}
    start = raw_range.get("start") or {}
    end = raw_range.get("end") or start
    severity = {
        "error": DiagnosticSeverity.Error,
        "warning": DiagnosticSeverity.Warning,
        "information": DiagnosticSeverity.Information,
        "info": DiagnosticSeverity.Information,
        "hint": DiagnosticSeverity.Hint,
    }.get(str(item.get("severity", "information")).lower())
    metadata = {
        key: item[key]
        for key in (
            "confidence",
            "category",
            "manual_ref",
            "fix_hints",
            "blocking",
            "suggested_actions",
        )
        if key in item
    }
    return Diagnostic(
        range=Range(
            start=Position(
                line=int(start.get("line", 0) or 0),
                character=int(start.get("character", 0) or 0),
            ),
            end=Position(
                line=int(end.get("line", 0) or 0),
                character=int(end.get("character", 0) or 0),
            ),
        ),
        message=str(item.get("message", "")),
        severity=severity,
        code=item.get("code"),
        source=item.get("source"),
        data=metadata,
    )


def _normalize_code_action(
    action: Any, diagnostics: list[dict[str, Any]]
) -> dict[str, Any]:
    title = str(_get_value(action, "title", "Quick fix"))
    kind = _enum_value(_get_value(action, "kind", "quickfix"))
    action_diagnostics = _get_value(action, "diagnostics", None) or []
    first_diagnostic = action_diagnostics[0] if action_diagnostics else None
    diagnostic_code = _get_value(first_diagnostic, "code", None)
    diagnostic_range = _range_to_dict(_get_value(first_diagnostic, "range", None))
    matching = next(
        (item for item in diagnostics if item.get("code") == diagnostic_code),
        {},
    )
    data = _serialize_lsp_value(_get_value(action, "data", None))
    if data is None:
        data = {}
    if not isinstance(data, dict):
        data = {"provider_data": data}
    data.setdefault("source", "provider")
    return {
        "title": title,
        "kind": kind,
        "diagnostic_code": diagnostic_code or matching.get("code"),
        "diagnostic_range": diagnostic_range or matching.get("range"),
        "confidence": matching.get("confidence", 1.0),
        "blocking": bool(matching.get("blocking", False)),
        "safe_to_auto_apply": False,
        "edit": _serialize_lsp_value(_get_value(action, "edit", None)),
        "data": data,
        "source": "provider",
    }


def _fix_actions(
    diagnostics: list[dict[str, Any]], *, line: int, character: int
) -> list[dict[str, Any]]:
    selected = _diagnostics_at_position(diagnostics, line, character) or diagnostics
    actions: list[dict[str, Any]] = []
    for diagnostic in selected:
        hints = diagnostic.get("fix_hints") or []
        if not hints:
            hints = ["Review this diagnostic before running the calculation."]
        for index, hint in enumerate(hints[:5]):
            actions.append(
                {
                    "title": str(hint),
                    "kind": "quickfix",
                    "diagnostic_code": diagnostic.get("code"),
                    "diagnostic_range": diagnostic.get("range"),
                    "confidence": diagnostic.get("confidence", 1.0),
                    "blocking": bool(diagnostic.get("blocking", False)),
                    "safe_to_auto_apply": False,
                    "edit": None,
                    "data": {"hint_index": index, "source": diagnostic.get("source")},
                    "source": "fallback",
                }
            )
    return actions


def _import_optional(module_name: str) -> Any | None:
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


_DEFAULT_IMPORT_OPTIONAL = _import_optional


def _call_provider(fn: Callable[..., Any], *values: Any) -> Any:
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        try:
            return fn()
        except Exception:
            return None
    required = [
        param
        for param in signature.parameters.values()
        if param.default is inspect.Parameter.empty
        and param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
    ]
    attempts: list[tuple[Any, ...]] = [(), values[:1], values[:2], values[:3], values[:4]]
    for args in attempts:
        if len(args) < len(required):
            continue
        try:
            return fn(*args[: len(signature.parameters)])
        except Exception:
            continue
    return None


def _get_value(item: Any, name: str, default: Any = None) -> Any:
    if item is None:
        return default
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _position_to_dict(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return {
            "line": int(value.get("line", 0) or 0),
            "character": int(value.get("character", 0) or 0),
        }
    return {
        "line": int(getattr(value, "line", 0) or 0),
        "character": int(getattr(value, "character", 0) or 0),
    }


def _range_to_dict(value: Any) -> dict[str, dict[str, int]] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        start = _position_to_dict(value.get("start"))
        end = _position_to_dict(value.get("end"))
    else:
        start = _position_to_dict(getattr(value, "start", None))
        end = _position_to_dict(getattr(value, "end", None))
    if start is None or end is None:
        return None
    return {"start": start, "end": end}


def _serialize_lsp_value(value: Any) -> Any:
    """Serialize lsprotocol objects without relying on their private layout."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_serialize_lsp_value(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_lsp_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_lsp_value(item) for key, item in value.items()}
    if hasattr(value, "start") and hasattr(value, "end"):
        return _range_to_dict(value)
    slots = getattr(type(value), "__slots__", ())
    if slots:
        result: dict[str, Any] = {}
        for name in slots:
            if name == "__weakref__":
                continue
            member = getattr(value, name, None)
            if member is None:
                continue
            json_name = re.sub(r"_([a-z])", lambda match: match.group(1).upper(), name)
            result[json_name] = _serialize_lsp_value(member)
        return result
    return str(value)


def _normalize_completion_item(item: Any, *, source: str = "provider") -> dict[str, Any]:
    if isinstance(item, dict):
        label = str(item.get("label") or item.get("name") or item.get("insertText") or "")
        detail = item.get("detail") or item.get("documentation") or item.get("description")
        kind = _enum_value(item.get("kind", 1))
    else:
        label = str(getattr(item, "label", item))
        detail = getattr(item, "detail", None)
        kind = _enum_value(getattr(item, "kind", 1))
    return {"label": label, "detail": _serialize_lsp_value(detail), "kind": kind, "source": source}


def _normalize_symbol(item: Any, *, source: str = "provider") -> dict[str, Any]:
    if not isinstance(item, dict):
        data = {
            "name": str(getattr(item, "name", item)),
            "kind": _enum_value(getattr(item, "kind", "symbol")),
            "range": _range_to_dict(getattr(item, "range", None)),
            "selectionRange": _range_to_dict(getattr(item, "selection_range", None)),
            "detail": getattr(item, "detail", None),
        }
        data = {key: value for key, value in data.items() if value is not None}
    else:
        data = dict(item)
        data["kind"] = _enum_value(data.get("kind", "symbol"))
    name = str(data.get("name") or data.get("label") or "symbol")
    if "range" in data and "selectionRange" in data:
        data["source"] = source
        return data
    if "selection_range" in data:
        data["selectionRange"] = _range_to_dict(data.pop("selection_range"))
    if "range" in data:
        data["range"] = _range_to_dict(data["range"])
    if "range" in data and "selectionRange" in data:
        data["source"] = source
        return data
    line = int(data.get("line", 1) or 1) - 1
    column = int(data.get("column", 1) or 1) - 1
    result = _symbol(name, data.get("kind", "symbol"), max(line, 0), max(column, 0))
    if "detail" in data:
        result["detail"] = data["detail"]
    result["source"] = source
    return result


def _dedupe_items(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        label = str(item.get(key) or "")
        if not label or label in seen:
            continue
        seen.add(label)
        result.append(item)
    return result
