import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.services import ingest_ledger as ledger


def oversized(suffix):
    prefix = "x" * 12000
    original = prefix + suffix
    return {"source":"telegram","channel_name":"fixture_public","telegram_message_id":42,
        "source_url":"https://t.me/fixture_public/42","raw_text":prefix,
        "raw_text_truncated":True,"original_text_sha256":hashlib.sha256(original.encode()).hexdigest()}


def test_different_oversized_originals_with_identical_retained_prefix_do_not_collide():
    first, second = oversized("first original suffix"), oversized("second original suffix")
    assert first["raw_text"] == second["raw_text"]
    first_id, first_hash = ledger.report_identity(first)
    second_id, second_hash = ledger.report_identity(second)
    assert first_id != second_id and first_hash != second_hash
    assert first_hash == first["original_text_sha256"]
    assert ledger.report_identity(dict(first)) == (first_id, first_hash)


def test_normal_report_identity_stays_compatible_with_existing_ledger():
    report={"source":"telegram","channel_name":"fixture_public","telegram_message_id":42,
        "source_url":"https://t.me/fixture_public/42","raw_text":"Original report"}
    old_hash=hashlib.sha256(report["raw_text"].encode()).hexdigest()
    old_id=hashlib.sha256(json.dumps([report["source"],report["channel_name"],42,report["source_url"],old_hash],ensure_ascii=False).encode()).hexdigest()
    assert ledger.report_identity(report)==(old_id,old_hash)


@pytest.mark.parametrize("invalid",[None,"","abc","z"*64,17])
def test_truncated_report_without_valid_original_hash_cannot_claim_identity(invalid):
    report=oversized("suffix")
    report["original_text_sha256"]=invalid
    with pytest.raises(ValueError,match="original content hash"):
        ledger.report_identity(report)


@pytest.mark.asyncio
async def test_actual_capture_keeps_both_original_hash_and_stored_prefix_hash(monkeypatch):
    session=MagicMock()
    session.__aenter__=AsyncMock(return_value=session)
    session.__aexit__=AsyncMock()
    session.commit=AsyncMock()
    captured=[]
    async def execute(statement):
        params=statement.compile().params
        captured.append(params)
        return SimpleNamespace(scalar_one_or_none=lambda:params["identity"])
    session.execute=execute
    monkeypatch.setattr(ledger,"async_session",lambda:session)
    first,second=oversized("A"),oversized("B")
    assert await ledger.capture_report(first) != await ledger.capture_report(second)
    assert len(captured)==2
    assert captured[0]["report"]["stored_raw_sha256"]==captured[1]["report"]["stored_raw_sha256"]
    assert captured[0]["content_hash"]!=captured[1]["content_hash"]
    assert "stored_raw_sha256" not in first  # Caller/source payload remains untouched.
