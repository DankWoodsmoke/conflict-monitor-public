"""Bounded, offline place-mention review; never incident geolocation.

The inherited gazetteer has no independently verified survey provenance. Its
points are offered only as explicitly unverified references. Literal source
spans establish a mention, not an assertion, actor, event location or truth.
"""

from __future__ import annotations

import hashlib
import json
import re

from app.services.evidence import valid_coordinates
from app.services.geocoder import (
    _DIRECTIONAL_REGIONS,
    AMBIGUOUS_PLACE_ALIASES,
    KNOWN_LOCATIONS,
    NON_PLACE_ALIASES,
)

MAX_SOURCE_CHARACTERS = 24_000
MAX_MENTIONS = 24
_TABLE = {**KNOWN_LOCATIONS, **_DIRECTIONAL_REGIONS}
_KEYS = sorted(
    (key for key in _TABLE if key not in NON_PLACE_ALIASES),
    key=lambda key: (-len(key), key),
)
_MENTIONS = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(key) for key in _KEYS) + r")(?!\w)",
    re.IGNORECASE,
)
GAZETTEER_SHA256 = hashlib.sha256(
    json.dumps(
        {key: _TABLE[key] for key in sorted(_TABLE)},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()

# Lexical exclusions only: never render/parse a DOM, decode entities, follow a
# URL or rewrite source text. Offsets always refer to the original string.
_TAG_START = re.compile(r"<\s*/?\s*([A-Za-z][A-Za-z0-9:-]*)")
_MARKUP_START = re.compile(r"<\s*[A-Za-z/!?]")
_RAW_BLOCKS = frozenset({"script", "style", "head", "title", "template"})
_RAW_CLOSE = {
    name: re.compile(r"</\s*" + name + r"\s*>", re.IGNORECASE) for name in _RAW_BLOCKS
}
_BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "br",
        "hr",
        "li",
        "ul",
        "ol",
        "section",
        "article",
        "body",
        "header",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "tr",
        "td",
        "blockquote",
        "figure",
        "figcaption",
    }
)
_URL_TOKEN = re.compile(
    r"(?<!\w)(?:https?://|ftp://|mailto:|www\.|//)[^\s<>\"']+|"
    r"(?<![\w@])(?:[a-z0-9-]{1,63}\.){1,10}[a-z]{2,63}(?:[/:?#][^\s<>\"']*)?|"
    r"(?<!\w)[a-z0-9._%+-]{1,64}@[a-z0-9.-]{1,253}\.[a-z]{2,63}",
    re.IGNORECASE,
)


def _tag_end(text: str, start: int) -> int | None:
    """Find an unquoted terminator; a nested opener makes the rest uncertain."""
    quote = None
    for index in range(start + 1, len(text)):
        char = text[index]
        if quote:
            if char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char == ">":
            return index + 1
        elif char == "<":
            return None
    return None


def _excluded_text(text: str) -> tuple[bytearray, bool]:
    """Bounded mask: 1=excluded inline bytes, 2=excluded block boundary.

    These are Python code-point positions, despite bytearray storage. An
    unterminated/ambiguous construct suppresses its entire remaining suffix.
    """
    excluded = bytearray(len(text))
    incomplete = False
    cursor = 0
    while (start := text.find("<", cursor)) != -1:
        block = 1
        if text.startswith("<!--", start):
            end = text.find("-->", start + 4)
            end = end + 3 if end != -1 else None
        elif text.startswith("<![CDATA[", start):
            end = text.find("]]>", start + 9)
            end = end + 3 if end != -1 else None
        elif _MARKUP_START.match(text, start):
            end = _tag_end(text, start)
            tag = _TAG_START.match(text, start)
            name = tag.group(1).lower() if tag else ""
            if name in _BLOCK_TAGS:
                block = 2
            if (
                end is not None
                and name in _RAW_BLOCKS
                and not text[start:end].lstrip("< ").startswith("/")
            ):
                closing = _RAW_CLOSE[name].search(text, end)
                if closing is None:
                    end = None
                else:
                    closing_start = closing.start()
                    # Nested templates/head metadata require a tree parser to
                    # interpret safely. Suppress instead of guessing a boundary.
                    if name not in {"script", "style"} and re.search(
                        r"<\s*" + re.escape(name) + r"\b",
                        text[end:closing_start],
                        re.IGNORECASE,
                    ):
                        end = None
                    else:
                        end = closing.end()
        else:
            cursor = start + 1
            continue
        if end is None:
            end = len(text)
            incomplete = True
        excluded[start:end] = bytes([block]) * (end - start)
        cursor = end
    for token in _URL_TOKEN.finditer(text):
        excluded[token.start() : token.end()] = b"\x01" * (token.end() - token.start())
    return excluded, incomplete


def _joins_hidden_inline_text(
    text: str, excluded: bytearray, start: int, end: int
) -> bool:
    # Inline tags/comments do not create word boundaries: Tehran<em>ian</em>
    # must not become a Tehran mention. Block tags do create boundaries.
    for index, step, edge in ((start - 1, -1, text[start]), (end, 1, text[end - 1])):
        if (
            not (edge.isalnum() or edge == "_")
            or not 0 <= index < len(text)
            or excluded[index] != 1
        ):
            continue
        while 0 <= index < len(text) and excluded[index] == 1:
            index += step
        if (
            0 <= index < len(text)
            and not excluded[index]
            and (text[index].isalnum() or text[index] == "_")
        ):
            return True
    return False


def place_mentions(raw_text: str) -> dict:
    """Preserve original text offsets, bounded work and explicit omissions."""
    if not isinstance(raw_text, str):
        raise TypeError("source text must be a string")
    source_sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    base = {
        "source_sha256": source_sha,
        "basis": "literal_place_mentions_in_inherited_gazetteer",
        "gazetteer_sha256": GAZETTEER_SHA256,
        "mutates_events": False,
        "external_requests": 0,
        "event_location_established": False,
        "markup_incomplete": False,
        "limits": [
            "A place mention may describe an actor, quotation, origin, destination, denial or an unrelated event.",
            "Reference coordinates are inherited and unverified, not surveyed incident or impact positions.",
            "The inherited name inventory is incomplete and primarily English; no matches does not establish absence of a place.",
            "Markup metadata, comments, script/style content and URL tokens are excluded; entities are not decoded and rendered visibility is not inferred.",
        ],
    }
    if len(raw_text) > MAX_SOURCE_CHARACTERS:
        return {
            **base,
            "status": "source_too_large",
            "mentions": [],
            "truncated": False,
            "max_source_characters": MAX_SOURCE_CHARACTERS,
        }
    matches = []
    truncated = False
    excluded, base["markup_incomplete"] = _excluded_text(raw_text)
    for match in _MENTIONS.finditer(raw_text):
        start, end = match.span()
        if any(excluded[start:end]) or _joins_hidden_inline_text(
            raw_text, excluded, start, end
        ):
            continue
        if len(matches) == MAX_MENTIONS:
            truncated = True
            break
        literal = match.group()
        key = literal.lower()
        # Unicode ignore-case variants need not identify the same gazetteer key.
        if key not in _TABLE:
            continue
        lat, lon = _TABLE[key]
        ambiguous = key in AMBIGUOUS_PLACE_ALIASES
        coordinates = (
            None
            if ambiguous or not valid_coordinates(lat, lon)
            else {"lat": lat, "lon": lon}
        )
        matches.append(
            {
                "mention_id": hashlib.sha256(
                    f"{source_sha}:{start}:{end}:{key}".encode()
                ).hexdigest(),
                "name": key,
                "span": {
                    "text": literal,
                    "start": start,
                    "end": end,
                    "index_unit": "unicode_code_points",
                    "start_utf16": len(raw_text[:start].encode("utf-16-le")) // 2,
                    "end_utf16": len(raw_text[:end].encode("utf-16-le")) // 2,
                },
                "status": "disambiguation_required" if ambiguous else "needs_review",
                "reference_coordinates": coordinates,
                "reference_kind": "regional_reference"
                if key in _DIRECTIONAL_REGIONS
                else "unverified_gazetteer_reference",
                "incident_precision": "unknown",
                "relationship_to_incident": "unassessed",
                "automatically_plottable": False,
            }
        )
    return {
        **base,
        "status": "mentions_available" if matches else "no_known_mentions",
        "mentions": matches,
        "truncated": truncated,
        "max_mentions": MAX_MENTIONS,
    }
