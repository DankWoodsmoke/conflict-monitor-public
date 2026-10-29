# SPDX-License-Identifier: MIT
"""Pure snapshot of the evaluated source-span contract. No app/DB/network access."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


class ExtractedReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: StrictInt = Field(gt=0)
    relevance: Literal["relevant", "not_relevant", "uncertain"]
    stance: Literal["reported", "denied", "uncertain"]
    place_mentions: list[StrictStr] = Field(max_length=6)
    actor_mentions: list[StrictStr] = Field(max_length=6)
    quantity_mentions: list[StrictStr] = Field(max_length=6)


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    reports: list[ExtractedReport] = Field(min_length=1, max_length=8)


def validate_extraction(raw, snapshot):
    result = Extraction.model_validate_json(raw)
    by_id = {r["id"]: r for r in snapshot}
    if len(result.reports) != len(by_id) or {r.id for r in result.reports} != set(
        by_id
    ):
        raise ValueError("Model changed or omitted source identities")
    output = []
    for report in result.reports:
        source = by_id[report.id]
        text = source["text"]
        if report.relevance == "not_relevant" and re.search(
            r"\b(?:airstrike|ceasefire|missile|military|casualties|diplomatic)\b",
            text,
            re.IGNORECASE,
        ):
            raise ValueError("Model discarded an explicit conflict-related topic")
        # The label cannot erase a visible explicit negation. This is a narrow
        # linguistic guard, not a multilingual entailment or incident classifier.
        negated = re.search(
            r"\b(?:denied|denies|did not|didn't|no evidence|no strike|not confirmed)\b",
            text,
            re.IGNORECASE,
        )
        if negated and report.stance == "reported":
            raise ValueError("Model omitted explicit uncertainty or negation")
        spans = {}
        for field in ("place_mentions", "actor_mentions", "quantity_mentions"):
            values = getattr(report, field)
            if len(set(values)) != len(values):
                raise ValueError("Duplicate model mention")
            spans[field] = []
            for mention in values:
                if not mention.strip() or len(mention) > 160 or mention not in text:
                    raise ValueError("Model mention is not an exact source span")
                start = text.index(mention)
                if (mention[0].isalnum() and start and text[start - 1].isalnum()) or (
                    mention[-1].isalnum()
                    and start + len(mention) < len(text)
                    and text[start + len(mention)].isalnum()
                ):
                    raise ValueError("Model mention splits a source token")
                spans[field].append(
                    {
                        "text": mention,
                        "start": start,
                        "end": start + len(mention),
                        "offset_unit": "unicode_codepoints",
                        "start_utf16": len(text[:start].encode("utf-16-le")) // 2,
                        "end_utf16": len(
                            text[: start + len(mention)].encode("utf-16-le")
                        )
                        // 2,
                        "status": "source_mention_not_event_location"
                        if field == "place_mentions"
                        else "source_mention_unverified",
                    }
                )
        output.append(
            {
                **source,
                "relevance": report.relevance,
                "stance": report.stance,
                "mentions": spans,
                "assessment_status": "model_generated_unreviewed",
                "coordinates": None,
                "severity": None,
            }
        )
    return output
