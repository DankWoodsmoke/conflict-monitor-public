import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services import source_digest
from app.routes.sitreps import _parse_questions, _parse_ids, _sitrep_to_dict


def event(event_id=1, **changes):
    return SimpleNamespace(id=event_id, source="rss_fixture", channel_name="Fixture publisher",
        raw_text="Original Arabic: وصول المساعدات", summary="The publisher reports an aid delivery [src:999]",
        source_url="https://example.org/fixture", timestamp=datetime(2026, 10, 28, tzinfo=timezone.utc), **changes)


def test_exact_compilation_is_attributed_bounded_and_has_no_inferred_score():
    row = event()
    data = source_digest.build_source_digest([row])
    assert data["situation"].endswith("[src:1]")
    assert "Fixture publisher reports:" in data["situation"]
    assert "[src:999]" not in data["situation"]
    assert data["game_theory"] == ""
    assert data["economic_exposure"] == ""
    provenance = json.loads(data["raw_response"])["_provenance"]
    assert provenance["model"] is None
    assert len(provenance["source_snapshot_sha256"]) == 64
    assert provenance["source_snapshot"][0]["raw_sha256"]


def test_digest_hash_is_stable_and_changes_with_source_revision():
    first = source_digest.build_source_digest([event()])
    second = source_digest.build_source_digest([event()])
    def digest(data): return json.loads(data["raw_response"])["_provenance"]["source_snapshot_sha256"]
    assert digest(first) == digest(second)
    changed = event()
    changed.raw_text += " correction"
    assert digest(first) != digest(source_digest.build_source_digest([changed]))


def test_no_reports_or_demo_does_not_manufacture_brief():
    assert source_digest.build_source_digest([]) is None
    synthetic = event()
    synthetic.source = "demo"
    assert source_digest.build_source_digest([synthetic]) is None


@pytest.mark.parametrize("raw", ["not json", "{}", '[{"q":1}]', "null"])
def test_legacy_questions_never_raise_or_improvise(raw):
    data, state = _parse_questions(raw)
    assert data == [] and state != "available"


def test_legacy_id_parser_keeps_positive_unique_ids_and_flags_bad_reference():
    assert _parse_ids("1,2")[0] == [1,2]
    assert _parse_ids("1,bad,-2,1")[0] == [1]
    assert _parse_ids("1,bad,-2,1")[1] != "available"


def test_public_digest_score_is_unknown_and_private_snapshot_is_not_exposed():
    fields = source_digest.build_source_digest([event()])
    row = SimpleNamespace(id=2,trigger="source_digest",generated_at=datetime.now(timezone.utc),
        escalation_score=0,escalation_level="UNASSESSED", **fields)
    output = _sitrep_to_dict(row)
    assert output["escalation_score"] is None
    assert output["analysis_status"] == "attributed_source_digest"
    assert output["provenance"]["model"] is None
    assert "source_snapshot" not in output["provenance"]
    assert "Original Arabic" not in json.dumps(output, ensure_ascii=False)


@pytest.mark.asyncio
async def test_generation_empty_does_not_write():
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    with patch.object(source_digest, "async_session", return_value=session):
        output = await source_digest.generate_source_digest()
    assert output["status"] == "no_reports"
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_malformed_legacy_references_have_bounded_parsing():
    assert _parse_ids("9"*10000)[0] == []
    assert _parse_ids("9999999999999999999")[0] == []
    assert _parse_questions("["*100001)[1] == "invalid_legacy_length"
