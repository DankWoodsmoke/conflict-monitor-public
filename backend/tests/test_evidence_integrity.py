"""Offline behavioral regressions for evidence integrity; no model, network or DB calls."""
import asyncio
import copy
import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from app.services import classifier, dedup, satellite_firms as firms, verification
from app.services.evidence import (append_report, assess_evidence, canonical_url,
                                  compatible_claims, make_report, parse_channels, report_count)
from app.services.retro_matcher import find_review_candidates

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def event(**changes):
    values = dict(id=1, source="telegram", channel_name="observer", raw_text="Original report",
                  summary="A source reports a fire near the main city hospital this morning",
                  source_url="https://t.me/observer/1", telegram_message_id=1,
                  timestamp=NOW, event_type="military", severity=3, lat=35., lon=50.,
                  geometry="original", source_reliability=2, report_count=1,
                  reporting_channels="observer", confirmed_networks="", reports=[],
                  classification_status="extracted", geolocation_precision="city")
    values.update(changes)
    return SimpleNamespace(**values)


class EvidenceTests(unittest.TestCase):
    def test_network_diversity_never_proves_confirmation(self):
        for channels in ("bbc_mideast, QudsNen", "satellite_firms, times_of_israel",
                         "x_ukmto, aljazeera", "x_elintnews, x_dropsitenews"):
            self.assertFalse(verification.is_cross_network_confirmed(channels))

    def test_unknown_source_is_unknown(self):
        self.assertEqual(verification.get_channel_network("brand_new_outlet"), "UNKNOWN")

    def test_multiword_source_and_transport_alias(self):
        self.assertEqual(parse_channels("NASA FIRMS VIIRS-NOAA20, satellite_firms"), ["satellite_firms"])
        info = assess_evidence(event(reporting_channels="x_geoconfirmed, geoconfirmed",
                                     channel_name="geoconfirmed"))
        self.assertEqual(info["unique_source_count"], 1)
        self.assertIsNone(info["independent_origin_count"])
        self.assertEqual(info["verification_basis"], "none")

    def test_source_scoped_message_identity(self):
        a = make_report(event(channel_name="one"))
        b = make_report(event(channel_name="two"))
        self.assertNotEqual(a["report_id"], b["report_id"])

    def test_report_replay_and_edit(self):
        original = make_report(event())
        reports = append_report([original], make_report(event()))
        self.assertEqual(len(reports), 1)
        edited = make_report(event(raw_text="Correction: fire report withdrawn"))
        reports = append_report(reports, edited)
        self.assertEqual(len(reports), 2)
        self.assertEqual(report_count(reports), 1)
        self.assertEqual(reports[0]["raw_text"], "Original report")

    def test_url_canonicalization_does_not_erase_article_identity(self):
        self.assertEqual(canonical_url("https://example.org/article?id=7&utm_source=x#part"),
                         "https://example.org/article?id=7")
        self.assertEqual(canonical_url("javascript:alert(1)"), "")
        self.assertEqual(canonical_url("https://key:secret@example.org/"), "")

    def test_negation_and_changed_casualties_do_not_merge(self):
        a = "An airstrike destroyed the main hospital in the city centre during the overnight attack"
        self.assertFalse(dedup.safe_text_match(a, a.replace("destroyed", "did not destroy")))
        self.assertFalse(compatible_claims("3 killed in the strike", "30 killed in the strike"))
        self.assertFalse(compatible_claims("The hospital was hit", "The hospital wasn’t hit"))
        self.assertFalse(compatible_claims("The hospital was hit", "The hospital was reportedly hit"))
        self.assertTrue(dedup.safe_text_match(a, a))

    def test_sensor_never_becomes_verified_event(self):
        info = assess_evidence(event(source="satellite_firms", event_type="thermal_anomaly"))
        self.assertEqual(info["status"], "sensor_observation")
        self.assertEqual(info["verification_basis"], "none")
        self.assertTrue(any("cause" in note for note in info["limitations"]))

    def test_unlocated_event_is_explicit(self):
        info = assess_evidence(event(lat=None, lon=None))
        self.assertTrue(any("unresolved" in note for note in info["limitations"]))

    def test_retro_candidates_preserve_opposing_reports(self):
        a = event()
        b = event(id=2, summary=a.summary.replace("reports a fire", "denies a fire"))
        before = copy.deepcopy([vars(a), vars(b)])
        candidates = find_review_candidates([a, b])
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0]["polarity_or_numeric_conflict"])
        self.assertEqual(candidates[0]["status"], "needs_review")
        self.assertEqual(before, [vars(a), vars(b)])


class MergeTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_source_cannot_inflate_score_or_count(self):
        existing = event()
        session = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
        for _ in range(5):
            await dedup.merge_duplicate(session, existing, "observer", 10, 36., 51.,
                                        report=make_report(event()))
        self.assertEqual(existing.report_count, 1)
        self.assertEqual(existing.source_reliability, 2)
        self.assertEqual(existing.severity, 3)
        self.assertEqual((existing.lat, existing.lon, existing.geometry), (35., 50., "original"))
        self.assertEqual(len(existing.reports), 1)

    async def test_new_source_retains_raw_report_without_confirmation(self):
        existing = event()
        incoming = event(channel_name="observer_extra", telegram_message_id=2,
                         raw_text="Second original statement", source_url="https://example.org/2")
        session = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
        await dedup.merge_duplicate(session, existing, incoming.channel_name, 9, 36., 51.,
                                    report=make_report(incoming))
        self.assertEqual(existing.report_count, 2)
        self.assertEqual(existing.source_reliability, 2)
        self.assertEqual({r["raw_text"] for r in existing.reports},
                         {"Original report", "Second original statement"})
        self.assertEqual(parse_channels(existing.reporting_channels), ["observer", "observer_extra"])

    async def test_unlocated_report_is_not_fuzzy_merged(self):
        session = SimpleNamespace(execute=AsyncMock())
        result = await dedup.check_duplicate(session, event().summary, "military", None, None, NOW)
        self.assertIsNone(result)
        session.execute.assert_not_awaited()


class ClassifierTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        classifier._CONTENT_SEEN.clear()

    def test_required_fields_and_type_fail_closed(self):
        for data in ({}, {"event_type": "invented", "severity": 5, "summary": "test", "location_name": "Unknown"},
                     {"event_type": "military", "severity": True, "summary": "test", "location_name": "Unknown"}):
            with self.assertRaises(ValidationError):
                classifier.ClassifierResult(**data)

    def test_unknown_location_stays_unknown_despite_flag(self):
        result = classifier.ClassifierResult(event_type="military", severity=3,
                                            summary="Officials reported an exercise", location_name="Unknown")
        classified = classifier._post_process(result, "🇮🇷 Iranian officials announced an exercise abroad")
        self.assertEqual(classified["location_name"], "Unknown")

    def test_short_report_and_promotional_suffix_are_not_blindly_dropped(self):
        self.assertFalse(classifier._is_obvious_noise("Explosion reported in Beirut"))
        self.assertFalse(classifier._is_obvious_noise("Explosion reported in Beirut. Subscribe for updates."))
        self.assertTrue(classifier._is_obvious_noise("Subscribe!"))

    async def test_missing_credentials_returns_explicit_nonpublishable_failure(self):
        with patch.object(classifier, "settings", SimpleNamespace(anthropic_api_key="")):
            result = await classifier.classify_message("An official source denies explosions in Tehran after an exercise")
        self.assertTrue(result["is_noise"])
        self.assertEqual(result["classification_status"], "unavailable")
        self.assertEqual(result["event_type"], "unclassified")
        self.assertEqual(result["location_name"], "Unknown")

    def test_cache_reuses_extraction_without_discarding_second_report(self):
        result = {"classification_status": "extracted", "summary": "Report retained", "is_noise": False}
        classifier._cache_result("identical source bytes", result)
        cached = classifier._cached_result("identical source bytes")
        self.assertFalse(cached["is_noise"])
        cached["summary"] = "mutation"
        self.assertEqual(classifier._cached_result("identical source bytes")["summary"], "Report retained")

    def test_failed_extraction_is_not_cached(self):
        classifier._cache_result("report", classifier._build_fallback("report"))
        self.assertIsNone(classifier._cached_result("report"))

    async def test_batch_output_is_bound_to_input_ids(self):
        loop = asyncio.get_running_loop()
        jobs = [classifier._ClassifyJob(str(i), "", str(i), loop.create_future()) for i in (1, 2)]
        def item(i):
            return {"input_id": i, "event_type": "military", "severity": 3,
                    "location_name": "Unknown", "summary": f"Report {i}"}
        response = SimpleNamespace(content=[SimpleNamespace(text=json.dumps([item(2), item(1)]))], usage=None)
        client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=response)))
        with patch.object(classifier, "_get_client", return_value=client), patch.object(classifier, "_log_usage_bg"):
            await classifier._process_batch(jobs)
        self.assertEqual(jobs[0].future.result()["summary"], "Report 1")
        self.assertEqual(jobs[1].future.result()["summary"], "Report 2")

    async def test_partially_invalid_batch_publishes_no_success(self):
        loop = asyncio.get_running_loop()
        jobs = [classifier._ClassifyJob(str(i), "", str(i), loop.create_future()) for i in (1, 2)]
        valid = {"input_id": 1, "event_type": "military", "severity": 3,
                 "location_name": "Unknown", "summary": "Valid first result"}
        response = SimpleNamespace(content=[SimpleNamespace(text=json.dumps([valid, {"input_id": 2}]))], usage=None)
        client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=response)))
        with patch.object(classifier, "_get_client", return_value=client), patch.object(classifier, "_log_usage_bg"):
            await classifier._process_batch(jobs)
        for job in jobs:
            self.assertTrue(job.future.result()["is_noise"])
            self.assertNotEqual(job.future.result()["classification_status"], "extracted")
        self.assertFalse(classifier._CONTENT_SEEN)

    async def test_cancelled_batch_never_calls_provider(self):
        future = asyncio.get_running_loop().create_future()
        future.cancel()
        job = classifier._ClassifyJob("text", "", "text", future)
        with patch.object(classifier, "_get_client") as client:
            await classifier._process_batch([job])
        client.assert_not_called()

    async def test_unknown_model_price_is_not_invented(self):
        session = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
        context = AsyncMock()
        context.__aenter__.return_value = session
        with patch("app.db.async_session", return_value=context):
            classifier._log_usage_bg("classify", "unknown-model", SimpleNamespace(input_tokens=100, output_tokens=20))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
        self.assertIsNone(session.execute.await_args.args[1]["cost"])


class FirmsTests(unittest.IsolatedAsyncioTestCase):
    def rows(self, confidence="n", date="2026-10-28", time="1200", lat="35", frp="90"):
        return ("latitude,longitude,acq_date,acq_time,frp,confidence,satellite,instrument\n"
                f"{lat},50,{date},{time},{frp},{confidence},N20,VIIRS\n")

    def test_viirs_categories_are_not_invented_percentages(self):
        for raw, label in (("l", "low"), ("n", "nominal"), ("h", "high"), ("", "unknown")):
            observation = firms._parse_firms_csv(self.rows(confidence=raw))[0]
            self.assertEqual(observation["confidence_label"], label)
            self.assertIsNone(observation["conf"])

    def test_malformed_data_cannot_become_current_observation(self):
        for args in ({"date": ""}, {"time": "2500"}, {"lat": "nan"}, {"frp": "inf"}, {"lat": "91"}):
            with self.assertRaises(ValueError):
                firms._parse_firms_csv(self.rows(**args))
        with self.assertRaises(ValueError):
            firms._parse_firms_csv("Invalid MAP_KEY")

    def test_observation_identity_contains_acquisition_time(self):
        a = firms._parse_firms_csv(self.rows(time="1200"))[0]
        b = firms._parse_firms_csv(self.rows(time="1205"))[0]
        self.assertNotEqual(firms._hotspot_key(a), firms._hotspot_key(b))

    async def test_spatial_association_never_moves_or_confirms_incident(self):
        incident = event()
        original = copy.deepcopy(vars(incident))
        observation = firms._parse_firms_csv(self.rows(lat="35.01"))[0]
        result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [incident]))
        session = SimpleNamespace(execute=AsyncMock(return_value=result), commit=AsyncMock())
        context = AsyncMock()
        context.__aenter__.return_value = session
        with patch.object(firms, "async_session", return_value=context):
            associated = await firms._cross_reference_events([observation])
        self.assertEqual(associated, 1)
        self.assertEqual(original, vars(incident))
        session.commit.assert_not_awaited()
        self.assertEqual(observation["proximity_matches"][0]["causation"], "unassessed")

    async def test_empty_success_clears_cache_but_failure_preserves_previous_age(self):
        firms._last_hotspots, firms._last_poll_ts = [{"old": True}], "old-time"
        with patch.object(firms, "_fetch_firms_hotspots", AsyncMock(return_value=None)):
            await firms.poll_firms_once()
        self.assertEqual(firms._last_poll_ts, "old-time")
        self.assertEqual(firms._last_hotspots, [{"old": True}])
        with patch.object(firms, "_fetch_firms_hotspots", AsyncMock(return_value=[])):
            await firms.poll_firms_once()
        self.assertEqual(firms._last_hotspots, [])
        self.assertNotEqual(firms._last_poll_ts, "old-time")
        self.assertEqual(firms._last_poll_confirmed, 0)


if __name__ == "__main__":
    unittest.main()
