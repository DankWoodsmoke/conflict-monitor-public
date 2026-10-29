"""Bounded SITREP structure and source-reference integrity, without I/O.

Passing this contract establishes shape and citation membership, not factual
entailment. Generated conclusions still require evidence review before reliance.
"""
from __future__ import annotations

import json
import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NO_EVIDENCE = "Insufficient evidence in the supplied reports."
CONTRACT_VERSION = "sitrep-evidence-v1"
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1400,
                                      pattern=r"^[^\r\n\x00-\x1f]+$")]
EventId = Annotated[int, Field(strict=True, gt=0)]
_CITATION = re.compile(r"\[src:([1-9]\d*(?:,[1-9]\d*)*)\]")


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Hypothesis(StrictRecord):
    hypothesis: Text
    premise: Text
    alternative: Text
    falsifier: Text


class HistoricalAnalogue(StrictRecord):
    hypothesis: Text
    premise: Text
    limitations: Text
    falsifier: Text


class KeyQuestion(StrictRecord):
    q: Text
    a: Text
    watch: Text


class SitrepOutput(StrictRecord):
    headline: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120,
                                              pattern=r"^[^\r\n\x00-\x1f]+$")]
    situation: Annotated[list[Text], Field(min_length=4, max_length=4)]
    escalation_text: Annotated[list[Text], Field(min_length=3, max_length=3)]
    economic_exposure: Annotated[list[Text], Field(min_length=4, max_length=4)]
    humanitarian_ground: Annotated[list[Text], Field(min_length=4, max_length=4)]
    game_theory: Annotated[list[Hypothesis], Field(min_length=4, max_length=4)]
    historical_analogue: HistoricalAnalogue
    key_questions: Annotated[list[KeyQuestion], Field(min_length=5, max_length=5)]
    key_event_ids: Annotated[list[EventId], Field(min_length=1, max_length=80)]


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("SITREP JSON contains a duplicate key")
        result[key] = value
    return result


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _strings(nested)


def citation_ids(text: str) -> set[int]:
    """Accept only the exact [src:1,2] notation rendered by existing clients."""
    references = {int(item) for match in _CITATION.finditer(text) for item in match[1].split(",")}
    remaining = _CITATION.sub("", text)
    if re.search(r"\[\s*(?:src\b|#\d)", remaining, re.I):
        raise ValueError("SITREP contains malformed source references")
    return references


def validate_sitrep(raw: str, allowed_ids: set[int]) -> SitrepOutput:
    if len(raw.encode("utf-8")) > 100_000:
        raise ValueError("SITREP response exceeds its byte limit")
    data = json.loads(raw, object_pairs_hook=_no_duplicate_keys,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON value")))
    report = SitrepOutput.model_validate(data)
    cited: set[int] = set()
    for prose in _strings(report.model_dump()):
        refs = citation_ids(prose)
        if not refs <= allowed_ids:
            raise ValueError("SITREP cites an event outside its input snapshot")
        cited.update(refs)

    # Every substantive section/answer has a traceable premise, or explicitly
    # abstains. An existing ID is not proof the cited text supports the claim.
    required = [*report.situation, *report.escalation_text, *report.economic_exposure,
                *report.humanitarian_ground, *(h.premise for h in report.game_theory),
                report.historical_analogue.premise, *(q.a for q in report.key_questions)]
    for prose in required:
        if prose != NO_EVIDENCE and not citation_ids(prose):
            raise ValueError("SITREP assertion lacks a source reference or explicit abstention")
    for hypothesis in [*report.game_theory, report.historical_analogue]:
        if hypothesis.premise == NO_EVIDENCE and any(
            value != NO_EVIDENCE for value in hypothesis.model_dump().values()
        ):
            raise ValueError("SITREP cannot extend an unsupported hypothesis")

    key_ids = report.key_event_ids
    if len(set(key_ids)) != len(key_ids) or set(key_ids) != cited or not cited:
        raise ValueError("SITREP key events must equal its unique cited input events")
    return report


def render_sitrep(report: SitrepOutput) -> dict:
    """Preserve legacy rich-text fields while making analytical status explicit."""
    bullets = lambda items: "\n".join("• " + item for item in items)
    history = report.historical_analogue
    return {
        "headline": report.headline,
        **{key: bullets(getattr(report, key)) for key in (
            "situation", "escalation_text", "economic_exposure", "humanitarian_ground")},
        "game_theory": bullets([
            f"HYPOTHESIS — {h.hypothesis} Premise: {h.premise} Alternative: {h.alternative} Falsifier: {h.falsifier}"
            for h in report.game_theory
        ]),
        "historical_analogue": (
            f"ANALOGY HYPOTHESIS — {history.hypothesis} Premise: {history.premise} "
            f"Limitations: {history.limitations} Falsifier: {history.falsifier}"
        ),
        "key_questions": json.dumps([q.model_dump() for q in report.key_questions], ensure_ascii=False),
        "key_event_ids": ",".join(str(i) for i in sorted(report.key_event_ids)),
    }
