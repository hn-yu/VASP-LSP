#!/usr/bin/env python3
"""Fetch the official VASP Wiki INCAR-tag catalog and generate schema data.

The generated module is deliberately kept in the source tree so the language
server does not need network access at runtime. Page titles establish that a
name is an official INCAR tag; type/default/enum metadata is only emitted when
the corresponding TAGDEF notation can be parsed without guessing.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import time
from pathlib import Path
from pprint import pformat
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

API_URL = "https://vasp.at/wiki/api.php"
WIKI_URL = "https://vasp.at/wiki"
CATEGORY_TITLE = "Category:INCAR tag"
USER_AGENT = "vasp-lsp-incar-schema-audit/0.4.5"
TAG_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*(?:/[A-Z0-9_]+)*$")


def _request_json(params: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch one MediaWiki API response with small retry/backoff handling."""
    url = f"{API_URL}?{urlencode(params)}"
    last_error: Optional[BaseException] = None
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=45) as response:
                payload = json.load(response)
            if not isinstance(payload, dict):
                raise RuntimeError("VASP Wiki API returned a non-object response")
            return payload
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(float(attempt + 1))
    raise RuntimeError(f"Unable to fetch VASP Wiki API response: {last_error}") from last_error


def _chunks(items: Sequence[str], size: int) -> Iterator[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def fetch_category_titles() -> List[str]:
    """Return every namespace-0 page in the official INCAR-tag category."""
    params: Dict[str, Any] = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": CATEGORY_TITLE,
        "cmnamespace": 0,
        "cmlimit": "max",
        "format": "json",
    }
    titles: List[str] = []
    while True:
        payload = _request_json(params)
        for member in payload.get("query", {}).get("categorymembers", []):
            title = member.get("title")
            if isinstance(title, str):
                titles.append(title)
        continuation = payload.get("continue")
        if not isinstance(continuation, dict):
            break
        params.update(continuation)
    return sorted(set(titles), key=str.upper)


def fetch_page_contents(titles: Sequence[str]) -> Dict[str, str]:
    """Fetch current wikitext for all requested pages in bounded batches."""
    pages_by_title: Dict[str, str] = {}
    for batch in _chunks(titles, 25):
        payload = _request_json(
            {
                "action": "query",
                "prop": "revisions",
                "titles": "|".join(batch),
                "rvprop": "content",
                "rvslots": "main",
                "format": "json",
            }
        )
        pages = payload.get("query", {}).get("pages", {})
        page_values = pages.values() if isinstance(pages, dict) else pages
        for page in page_values:
            if not isinstance(page, dict):
                continue
            title = page.get("title")
            revisions = page.get("revisions", [])
            if not isinstance(title, str) or not revisions:
                continue
            revision = revisions[0]
            slots = revision.get("slots", {}) if isinstance(revision, dict) else {}
            main_slot = slots.get("main", {}) if isinstance(slots, dict) else {}
            content = main_slot.get("*") if isinstance(main_slot, dict) else None
            if isinstance(content, str):
                pages_by_title[title] = content
        time.sleep(0.05)
    return pages_by_title


def _iter_templates(text: str) -> Iterator[str]:
    """Yield balanced MediaWiki template bodies, including nested templates."""
    position = 0
    while True:
        start = text.find("{{", position)
        if start < 0:
            return
        depth = 0
        cursor = start
        while cursor < len(text) - 1:
            token = text[cursor : cursor + 2]
            if token == "{{":
                depth += 1
                cursor += 2
                continue
            if token == "}}":
                depth -= 1
                cursor += 2
                if depth == 0:
                    yield text[start + 2 : cursor - 2]
                    position = cursor
                    break
                continue
            cursor += 1
        else:
            return


def _split_template_fields(body: str) -> List[str]:
    """Split a template body on top-level pipes only."""
    fields: List[str] = []
    start = 0
    depth = 0
    cursor = 0
    while cursor < len(body):
        if body.startswith("{{", cursor):
            depth += 1
            cursor += 2
            continue
        if body.startswith("}}", cursor):
            depth = max(depth - 1, 0)
            cursor += 2
            continue
        if body[cursor] == "|" and depth == 0:
            fields.append(body[start:cursor])
            start = cursor + 1
        cursor += 1
    fields.append(body[start:])
    return fields


def _extract_tagdef(wikitext: str) -> Optional[Tuple[str, str, Optional[str]]]:
    for body in _iter_templates(wikitext):
        fields = _split_template_fields(body)
        if not fields or fields[0].strip().upper() != "TAGDEF" or len(fields) < 2:
            continue
        name = fields[1].strip()
        value_spec = fields[2].strip() if len(fields) >= 3 else ""
        default = fields[3].strip() if len(fields) >= 4 else None
        return name, value_spec, default
    return None


def _clean_wikitext(value: str) -> str:
    """Reduce a short piece of Wiki markup to readable metadata text."""
    text = html.unescape(value)
    text = re.sub(r"<ref\b[^>]*>.*?</ref\s*>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("{{!}}", "|").replace("{{=}}", "=")

    def template_replacement(match: re.Match[str]) -> str:
        fields = _split_template_fields(match.group(1))
        if len(fields) > 1:
            return fields[1]
        return ""

    for _ in range(4):
        new_text = re.sub(r"\{\{([^{}]*)\}\}", template_replacement, text)
        if new_text == text:
            break
        text = new_text

    text = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r"\s+", " ", text)
    # Keep periods: .TRUE. and .FALSE. are VASP boolean tokens, not
    # punctuation that may be discarded during type inference.
    return text.strip(" \t\r\n;")


def _extract_description(wikitext: str, title: str) -> str:
    match = re.search(
        r"(?:^|\n)\s*(?:'''Description:'''|Description:)\s*(.*)",
        wikitext,
        flags=re.IGNORECASE,
    )
    description = ""
    if match:
        description = _clean_wikitext(match.group(1))
        if not description:
            for line in wikitext[match.end() :].splitlines():
                if line.strip() and not line.lstrip().startswith("-"):
                    description = _clean_wikitext(line)
                    if description:
                        break
    if not description:
        description = f"Official VASP Wiki INCAR tag page for {title}."
    return f"Official VASP Wiki: {description[:500]}"


def _extract_categories(wikitext: str) -> List[str]:
    categories = re.findall(r"\[\[Category:([^|\]]+)", wikitext, flags=re.IGNORECASE)
    return [category.strip() for category in categories if category.strip().lower() != "incar tag"]


def _canonical_name(title: str, tagdef_name: Optional[str]) -> Optional[str]:
    candidate = (tagdef_name or title.replace(" ", "_")).strip().upper()
    candidate = candidate.replace(" ", "_")
    if TAG_NAME_RE.fullmatch(candidate) is None:
        return None
    return candidate


def _infer_type(value_spec: str) -> str:
    """Infer only types explicitly represented by common TAGDEF notation."""
    clean_spec = _clean_wikitext(value_spec)
    lowered = clean_spec.lower()
    if (
        "logical" in lowered
        or "boolean" in lowered
        or ".true." in lowered
        or ".false." in lowered
    ):
        return "boolean"
    if any(
        marker in lowered
        for marker in ("array", "vector", "matrix", "list", "nions", "n_atoms", "3 real")
    ):
        return "array"
    if re.search(r"\binteger\b|\bint(?:eger)?\b", lowered):
        return "integer"
    if re.search(r"\breal\b|\bfloat\b", lowered):
        return "float"
    if "string" in lowered or "character" in lowered:
        return "string"
    alternatives = [_clean_wikitext(part).strip() for part in value_spec.split("{{!}}")]
    if len(alternatives) > 1 and all(re.fullmatch(r"[+-]?\d+", part) for part in alternatives):
        return "integer"
    if len(alternatives) > 1 and all(
        re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", part) for part in alternatives
    ):
        return "float"
    if len(alternatives) > 1 and all(
        re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", part) for part in alternatives
    ):
        return "string"
    return "unknown"


def _parse_default(default: Optional[str]) -> Any:
    if not default:
        return None
    clean_default = _clean_wikitext(default)
    lowered = clean_default.lower()
    if not clean_default or "not set" in lowered or "if " in lowered:
        return None
    if clean_default.upper() in {".TRUE.", "TRUE", "T"}:
        return True
    if clean_default.upper() in {".FALSE.", "FALSE", "F"}:
        return False
    if re.fullmatch(r"[+-]?\d+", clean_default):
        return int(clean_default)
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?", clean_default):
        return float(clean_default)
    if clean_default.startswith("[") or len(clean_default) > 120:
        return None
    return clean_default


def _enum_values(value_spec: str, inferred_type: str) -> Optional[List[str]]:
    if inferred_type == "unknown":
        return None
    raw_parts = value_spec.split("{{!}}")
    if len(raw_parts) < 2:
        return None
    values: List[str] = []
    for raw_part in raw_parts:
        part = _clean_wikitext(raw_part)
        aliases = re.findall(r"\(\s*or\s+([^)]+)\)", part, flags=re.IGNORECASE)
        part = re.sub(r"\(\s*or\s+[^)]+\)", "", part, flags=re.IGNORECASE).strip()
        candidates = [part] + [_clean_wikitext(alias).strip() for alias in aliases]
        for candidate in candidates:
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*|[+-]?\d+(?:\.\d+)?", candidate):
                continue
            if candidate.lower() in {"real", "integer", "logical", "string"}:
                continue
            if candidate not in values:
                values.append(candidate)
    return values or None


def _valid_range(
    value_spec: str, inferred_type: str
) -> Optional[Tuple[float, Optional[float]]]:
    """Extract an explicit lower-bounded numeric range from TAGDEF notation."""
    if inferred_type not in {"integer", "float"}:
        return None
    clean_spec = _clean_wikitext(value_spec)
    match = re.search(r"(?:≥|>=)\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", clean_spec)
    if not match:
        return None
    lower = float(match.group(1))
    return (lower, None)


def _version_note(wikitext: str) -> Optional[str]:
    notes: List[str] = []
    for line in wikitext.splitlines():
        clean_line = _clean_wikitext(line)
        if re.search(r"\bVASP(?:\.[0-9Xx]+)?\b|available as of", clean_line, re.IGNORECASE):
            if clean_line and clean_line not in notes:
                notes.append(clean_line[:240])
        if len(notes) == 2:
            break
    return " ".join(notes)[:480] or None


def _tag_record(title: str, wikitext: str) -> Optional[Dict[str, Any]]:
    tagdef = _extract_tagdef(wikitext)
    tagdef_name, value_spec, default = tagdef if tagdef else (None, "", None)
    name = _canonical_name(title, tagdef_name)
    if name is None:
        return None
    tag_type = _infer_type(value_spec)
    record: Dict[str, Any] = {
        "name": name,
        "type": tag_type,
        "default": _parse_default(default),
        "description": _extract_description(wikitext, title),
        "category": (_extract_categories(wikitext) or ["Official VASP Wiki"])[0],
        "source_url": f"{WIKI_URL}/{quote(title.replace(' ', '_'), safe='/()_')}",
    }
    enum_values = _enum_values(value_spec, tag_type)
    if enum_values:
        record["enum_values"] = enum_values
    valid_range = _valid_range(value_spec, tag_type)
    if valid_range:
        record["valid_range"] = valid_range
    version_note = _version_note(wikitext)
    if version_note:
        record["version_note"] = version_note
    return record


def build_catalog(
    titles: Sequence[str], pages: Dict[str, str]
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    records: Dict[str, Dict[str, Any]] = {}
    skipped: List[str] = []
    for title in titles:
        record = _tag_record(title, pages.get(title, ""))
        if record is None:
            skipped.append(title)
            continue
        records[record["name"]] = record
    return dict(sorted(records.items())), skipped


def write_module(output: Path, records: Dict[str, Dict[str, Any]]) -> None:
    header = '''"""Generated from the official VASP Wiki INCAR-tag category.

Source: https://vasp.at/wiki/Category:INCAR_tag
Generated by: scripts/update_incar_wiki_schema.py

Do not edit this catalog by hand; update it from the Wiki and review the diff.
"""

OFFICIAL_WIKI_TAGS = '''
    body = pformat(records, width=100, sort_dicts=False)
    footer = f"""

OFFICIAL_WIKI_TAG_COUNT = {len(records)}
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(header + body + footer, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "src/vasp_lsp/schemas/incar_wiki_tags.py",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    titles = fetch_category_titles()
    pages = fetch_page_contents(titles)
    records, skipped = build_catalog(titles, pages)
    print(f"Official category pages: {len(titles)}")
    print(f"Pages with fetched content: {len(pages)}")
    print(f"Generated canonical tag records: {len(records)}")
    if skipped:
        print(f"Skipped non-INCAR identifier titles: {len(skipped)}")
        print("Skipped titles: " + ", ".join(skipped))
    if not args.dry_run:
        write_module(args.output, records)
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
