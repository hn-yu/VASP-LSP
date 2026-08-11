"""Offline integrity checks for the generated official INCAR schema."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, cast

from .schemas.incar_tags import INCAR_TAGS, OFFICIAL_WIKI_TAGS

SCHEMA_AUDIT_VERSION = "vasp-lsp.schema.v1"
_ALLOWED_TYPES = {"integer", "float", "boolean", "string", "array", "unknown"}


def audit_schema() -> Dict[str, Any]:
    """Return a deterministic report without contacting the VASP Wiki.

    Network access belongs to ``scripts/update_incar_wiki_schema.py``.  The
    runtime audit instead proves that the checked-in generated catalog is
    loaded, every official entry is registered, and metadata is safe enough
    for the validator to consume.  ``unknown`` types are intentionally valid:
    they preserve official tag recognition without inventing value semantics.
    """
    errors: List[str] = []
    official_tags = cast(Mapping[str, Mapping[str, Any]], OFFICIAL_WIKI_TAGS)
    for name, metadata in official_tags.items():
        runtime_tag = INCAR_TAGS.get(name)
        if runtime_tag is None:
            errors.append(f"official tag {name} is missing from runtime schema")
            continue
        if metadata.get("name") != name:
            errors.append(f"official tag key/name mismatch: {name}")
        source_url = metadata.get("source_url")
        if not isinstance(source_url, str) or not source_url.startswith(
            "https://vasp.at/wiki/"
        ):
            errors.append(f"official tag {name} has no official source URL")
        description = metadata.get("description")
        if not isinstance(description, str) or not description.strip():
            errors.append(f"official tag {name} has no description")
        if metadata.get("type") not in _ALLOWED_TYPES:
            errors.append(f"official tag {name} has unsupported type {metadata.get('type')!r}")
        if not isinstance(runtime_tag.source_url, str) or not runtime_tag.source_url.startswith(
            "https://vasp.at/wiki/"
        ):
            errors.append(f"runtime tag {name} lost official provenance")

    malformed_runtime = [
        name
        for name, tag in INCAR_TAGS.items()
        if tag.name != name or tag.type not in _ALLOWED_TYPES
    ]
    errors.extend(f"malformed runtime tag {name}" for name in malformed_runtime)

    return {
        "schema_version": SCHEMA_AUDIT_VERSION,
        "ok": not errors,
        "official_tag_count": len(official_tags),
        "runtime_tag_count": len(INCAR_TAGS),
        "overlay_tag_count": len(set(INCAR_TAGS) - set(official_tags)),
        "unknown_type_count": sum(
            1
            for metadata in official_tags.values()
            if metadata.get("type") == "unknown"
        ),
        "errors": errors,
    }
