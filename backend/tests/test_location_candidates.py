import copy
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.routes import events
from app.services import geocoder
from app.services.location_candidates import (
    MAX_MENTIONS,
    MAX_SOURCE_CHARACTERS,
    place_mentions,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "IDF",
        "IRGC",
        "CENTCOM",
        "fifth fleet",
        "khomeini",
        "US Fifth Fleet",
        "IRGC Aerospace",
        "Bagheri",
        "Imam Ali",
        "Hemmat",
        "Beirut or Damascus",
        "north of Tehran",
        "near Tehran",
        "Natanz",
        "Arak",
        "Strike from Tehran",
        "Tehran; Haifa",
        "IRGC says the situation is normal",
    ],
)
async def test_actors_ambiguous_aliases_and_relative_or_multiple_mentions_never_autoplot(
    query, monkeypatch
):
    # Even an inherited cached guess cannot bypass the changed input boundary.
    monkeypatch.setattr(geocoder, "_cache", {query.lower(): (32.0, 35.0)})
    external = AsyncMock(
        side_effect=AssertionError("No external disambiguation by ranking")
    )
    monkeypatch.setattr(geocoder, "_query_nominatim", external)
    assert await geocoder.geocode(query) is None
    external.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_exact_place_retains_reference_but_partial_sentence_does_not(
    monkeypatch,
):
    from collections import OrderedDict

    monkeypatch.setattr(geocoder, "_cache", OrderedDict())
    assert await geocoder.geocode("Tehran") == (35.6892, 51.3890)
    assert await geocoder.geocode("The source is in Tehran") is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("IDF and IRGC statements", []),
        ("US Fifth Fleet and IRGC Aerospace issued statements.", []),
        (
            "No explosion in Beirut; reports instead mention Damascus.",
            ["beirut", "damascus"],
        ),
        ("near Natanz", ["natanz"]),
        ("northern Israel and Beirut airport", ["northern israel", "beirut airport"]),
        ("Miranda and Tehranian", []),
    ],
)
def test_mentions_preserve_ambiguity_negation_and_longest_named_place_without_selecting_event(
    text, expected
):
    result = place_mentions(text)
    assert [row["name"] for row in result["mentions"]] == expected
    assert result["external_requests"] == 0 and result["mutates_events"] is False
    assert result["event_location_established"] is False
    assert all(row["automatically_plottable"] is False for row in result["mentions"])
    assert all(row["incident_precision"] == "unknown" for row in result["mentions"])
    assert result["source_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    if expected == ["natanz"]:
        assert result["mentions"][0]["reference_coordinates"] is None
        assert result["mentions"][0]["status"] == "disambiguation_required"


def test_unicode_source_spans_bind_exact_browser_and_python_offsets():
    text = "🛰️ Arabic اقتباس: BEIRUT, then Tehran."
    result = place_mentions(text)
    for row in result["mentions"]:
        span = row["span"]
        assert text[span["start"] : span["end"]] == span["text"]
        encoded = text.encode("utf-16-le")
        assert (
            encoded[span["start_utf16"] * 2 : span["end_utf16"] * 2].decode("utf-16-le")
            == span["text"]
        )
    revised = place_mentions("Correction: " + text)
    assert result["source_sha256"] != revised["source_sha256"]
    assert result["mentions"][0]["mention_id"] != revised["mentions"][0]["mention_id"]


def test_rss_photo_attributes_and_permalink_do_not_become_body_locations():
    text = (
        '<a href="https://news.example/photos/Tehran"><img src="https://cdn.example/Tehran.jpg" '
        'alt="Tehran archive photo" title="Tehran > old photograph" /></a>'
        "<p>Reports describe activity in the Negev near Ovda and Nevatim.</p>"
    )
    original = text
    result = place_mentions(text)
    assert [row["name"] for row in result["mentions"]] == ["negev", "ovda", "nevatim"]
    assert result["markup_incomplete"] is False and text == original
    assert result["source_sha256"] == hashlib.sha256(original.encode()).hexdigest()
    assert all(not row["automatically_plottable"] for row in result["mentions"])


@pytest.mark.parametrize(
    "metadata",
    [
        "<!-- Tehran and Damascus -->",
        '<script>const place="Tehran"; const tag="<img title=Damascus>";</script>',
        '<STYLE>.Tehran { background: url("https://example.org/Damascus"); }</STYLE>',
        '<head><title>Tehran</title><meta content="Damascus"></head>',
        "<title>Tehran</title>",
        "<template><p>Tehran and Damascus</p></template>",
        "<![CDATA[Tehran and Damascus]]>",
        '<?metadata location="Tehran"?>',
        "<img data-place=Tehran alt=Damascus>",
        "<span title=Tehran></span>",
    ],
)
def test_metadata_and_inert_blocks_are_excluded_without_rendering(metadata):
    result = place_mentions(metadata + "<p>Beirut</p>")
    assert [row["name"] for row in result["mentions"]] == ["beirut"]
    assert result["markup_incomplete"] is False


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/Tehran?caption=Beirut#Damascus",
        "http://Tehran.example/Beirut",
        "//example.org/Tehran",
        "www.example.org/Tehran",
        "news.example/Tehran",
        "Tehran@example.org",
        "mailto:Tehran@example.org",
        "ftp://example.org/Tehran",
        "https://example.org/Tehran%20Beirut",
    ],
)
def test_visible_url_and_email_tokens_are_not_place_mentions(url):
    result = place_mentions(f"Source: {url} Actual body mentions Nevatim.")
    assert [row["name"] for row in result["mentions"]] == ["nevatim"]
    assert result["markup_incomplete"] is False


@pytest.mark.parametrize(
    "broken",
    [
        '<img alt="Tehran > Nevatim',
        "<img alt=Tehran",
        "<!-- Tehran <p>Nevatim</p>",
        "<script>Tehran</scriptx><p>Nevatim</p>",
        "<style>Tehran",
        "<img alt=Tehran <p>Nevatim</p>",
        "<![CDATA[Tehran",
        "<template><template>Tehran</template>Nevatim",
    ],
)
def test_malformed_markup_suppresses_uncertain_suffix_and_reports_incompleteness(
    broken,
):
    text = "Beirut. " + broken
    result = place_mentions(text)
    assert [row["name"] for row in result["mentions"]] == ["beirut"]
    assert result["markup_incomplete"] is True
    assert result["source_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert (
        result["truncated"] is False
    )  # This flag remains only the mention-count limit.


def test_markup_preserves_exact_unicode_offsets_and_does_not_decode_entities():
    text = (
        '🛰️ <img alt="Tehran"><p>اقتباس: BEIRUT &amp; <b>Nevatim</b>; Teh&#114;an.</p>'
    )
    result = place_mentions(text)
    assert [row["name"] for row in result["mentions"]] == ["beirut", "nevatim"]
    for row in result["mentions"]:
        span = row["span"]
        assert text[span["start"] : span["end"]] == span["text"]
        encoded = text.encode("utf-16-le")
        assert (
            encoded[span["start_utf16"] * 2 : span["end_utf16"] * 2].decode("utf-16-le")
            == span["text"]
        )
        assert span["start_utf16"] == span["start"] + 1


def test_inline_markup_cannot_split_a_nonplace_word_into_a_place():
    result = place_mentions(
        "Tehran<em>ian</em> and Bei<b>rut</b>. Tehran<em>_ian</em> "
        "and <em>_</em>Tehran. <p>Beirut</p><p>Damascus</p>"
    )
    assert [row["name"] for row in result["mentions"]] == ["beirut", "damascus"]
    assert result["markup_incomplete"] is False


def test_plain_comparison_and_visible_anchor_text_remain_literal_mentions():
    text = '2 < 5 km from Beirut. <a href="https://example.org/Tehran">Nevatim</a>'
    result = place_mentions(text)
    assert [row["name"] for row in result["mentions"]] == ["beirut", "nevatim"]
    assert result["markup_incomplete"] is False


def test_excluded_metadata_does_not_consume_the_visible_mention_budget():
    result = place_mentions(
        '<img alt="Tehran">' * (MAX_MENTIONS + 5) + "<p>Nevatim</p>"
    )
    assert [row["name"] for row in result["mentions"]] == ["nevatim"]
    assert result["truncated"] is False and result["markup_incomplete"] is False


def test_markup_scan_is_bounded_and_missing_tag_terminator_fails_closed():
    text = '<img alt="' + "Tehran " * ((MAX_SOURCE_CHARACTERS - 10) // 7)
    assert len(text) <= MAX_SOURCE_CHARACTERS
    result = place_mentions(text)
    assert result["markup_incomplete"] is True and result["mentions"] == []
    result = place_mentions(text + "x" * MAX_SOURCE_CHARACTERS)
    assert (
        result["status"] == "source_too_large" and result["markup_incomplete"] is False
    )


def test_large_and_truncated_inputs_are_explicit_incomplete_work():
    large = place_mentions("a" * (MAX_SOURCE_CHARACTERS + 1))
    assert large["status"] == "source_too_large" and large["mentions"] == []
    repeated = place_mentions("Beirut. " * (MAX_MENTIONS + 5))
    assert repeated["truncated"] is True and len(repeated["mentions"]) == MAX_MENTIONS
    assert len({row["mention_id"] for row in repeated["mentions"]}) == MAX_MENTIONS


@pytest.mark.asyncio
async def test_event_review_does_not_write_or_change_original_source():
    event = SimpleNamespace(
        id=12, raw_text="IDF denies an explosion in Beirut", lat=None, lon=None
    )
    before = copy.deepcopy(vars(event))
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalar_one_or_none=lambda: event)
        ),
        commit=AsyncMock(),
    )
    result = await events.event_location_candidates(12, session)
    assert result["event_id"] == 12 and result["mentions"][0]["name"] == "beirut"
    assert vars(event) == before
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_event_is_not_an_empty_success():
    from fastapi import HTTPException

    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    )
    with pytest.raises(HTTPException) as error:
        await events.event_location_candidates(12, session)
    assert error.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response,expected",
    [
        ([{"lat": "31.8", "lon": "35.2"}], (31.8, 35.2)),
        ([{"lat": "31.8", "lon": "35.2"}, {"lat": "33.8", "lon": "36.2"}], None),
        ([{"lat": True, "lon": 35}], None),
        ([{"lat": "NaN", "lon": "35"}], None),
        ({"error": "not a result list"}, None),
    ],
)
async def test_external_search_rejects_ranked_ambiguity_and_bad_coordinates(
    response, expected, monkeypatch
):
    monkeypatch.setattr(
        geocoder.settings, "nominatim_url", "https://fixture.invalid/search"
    )
    monkeypatch.setattr(geocoder, "_last_nominatim_call", 0.0)
    client = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(status_code=200, json=lambda: response)
        )
    )
    context = AsyncMock()
    context.__aenter__.return_value = client
    monkeypatch.setattr(geocoder.httpx, "AsyncClient", lambda **kwargs: context)
    assert await geocoder._query_nominatim("FixtureVille") == expected
    assert client.get.await_args.kwargs["params"]["limit"] == 5
    assert geocoder._last_nominatim_call > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://nominatim.openstreetmap.org/search",
        "https://NOMINATIM.OPENSTREETMAP.ORG.:443/search",
    ],
)
async def test_automatic_collectors_do_not_use_donated_public_nominatim(
    url, monkeypatch
):
    from unittest.mock import Mock

    monkeypatch.setattr(geocoder.settings, "nominatim_url", url)
    client = Mock(side_effect=AssertionError("No public-server request"))
    monkeypatch.setattr(geocoder.httpx, "AsyncClient", client)
    assert await geocoder._query_nominatim("FixtureVille") is None
    client.assert_not_called()
