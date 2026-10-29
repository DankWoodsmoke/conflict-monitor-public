"""Malformed historical rows must not make the entire brief history unusable."""
import json
from types import SimpleNamespace

import pytest

from app.routes.sitreps import _parse_ids, _parse_questions, _sitrep_to_dict
from app.routes import sitreps as subject


@pytest.mark.parametrize("raw", ["[" * 2000 + "]" * 2000, "{\"a\":" * 2000 + "0" + "}" * 2000])
def test_nested_legacy_questions_fail_closed_without_recursion_crash(raw):
    questions, status = _parse_questions(raw)
    assert questions == []
    # CPython's JSON parser depth behavior differs between 3.11 and 3.12.
    # Either decoding rejects depth or the parsed nested value fails our schema.
    assert status in {"invalid_legacy_json", "invalid_legacy_shape"}


def test_truly_malformed_questions_always_return_explicit_json_rejection():
    assert _parse_questions('[{"q":') == ([], "invalid_legacy_json")


def test_json_recursion_error_is_explicitly_handled_independently_of_runtime_parser(monkeypatch):
    def recursion_failure(raw):
        raise RecursionError("fixture decoder depth rejection")
    monkeypatch.setattr(subject, "_json", SimpleNamespace(loads=recursion_failure))
    assert subject._parse_questions("[]") == ([], "invalid_legacy_json")


def test_legacy_question_count_text_and_field_whitelist_are_bounded():
    data = [{"q": "q" * 3000, "a": "a" * 3000, "watch": "w" * 3000,
             "private": "should not be exposed"} for _ in range(21)]
    # Keep below the whole-value budget to exercise row/text bounds independently.
    for row in data[1:]:
        row.update(q="q", a="a", watch="w")
    questions, status = _parse_questions(json.dumps(data))
    assert len(questions) == 20 and status == "truncated_legacy_questions"
    assert all(set(row) == {"q", "a", "watch"} for row in questions)
    assert len(questions[0]["q"]) == len(questions[0]["a"]) == len(questions[0]["watch"]) == 2000


def test_reference_parser_rejects_sql_syntax_unicode_overflow_and_nonpositive_ids():
    value = "1,1,0,-1,１,١,9223372036854775808,1);DROP TABLE events,2"
    assert _parse_ids(value) == ([1, 2], "incomplete_legacy_references")
    ids, status = _parse_ids(",".join(map(str, range(1, 300))))
    assert ids == list(range(1, 81)) and status == "incomplete_legacy_references"
    assert _parse_ids("1," * 100_000) == ([], "invalid_legacy_shape")


def test_nested_provenance_does_not_crash_history_or_expose_private_snapshot():
    row = SimpleNamespace(id=1, trigger="source_digest", generated_at=None, events_analyzed=0,
        key_questions="[]", key_event_ids="", raw_response="[" * 2000 + "]" * 2000,
        headline="source", situation="", escalation_text="", escalation_level="HIGH", escalation_score=99,
        economic_exposure="", game_theory="", humanitarian_ground="", historical_analogue="")
    public = _sitrep_to_dict(row)
    assert public["provenance"] == {}
    assert public["provenance_status"] == "invalid_legacy_provenance"
    assert public["escalation_score"] is None and public["escalation_level"] == "UNASSESSED"
