"""Offline satellite ingestion regressions; no provider calls or model runtime."""
import copy
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx

from app.services import satellites


NOW = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)


def element(**changes):
    row = {
        "OBJECT_NAME": "SYNTHETIC ORBIT TEST", "OBJECT_ID": "2026-001A",
        "NORAD_CAT_ID": 100001, "EPOCH": "2026-10-28T06:00:00.123456",
        "MEAN_MOTION": 15.5, "ECCENTRICITY": 0.0001, "INCLINATION": 51.6,
        "RA_OF_ASC_NODE": 123.0, "ARG_OF_PERICENTER": 42.0,
        "MEAN_ANOMALY": 84.0, "BSTAR": 0.0001,
        "MEAN_MOTION_DOT": 0.00001, "MEAN_MOTION_DDOT": 0,
    }
    return {**row, **changes}


class OrbitMetadataTests(unittest.TestCase):
    def normalize(self, rows):
        return satellites.normalize_omm_records(rows, group="military", fetched_at=NOW)

    def test_six_digit_catalog_and_epoch_survive_without_synthetic_tle(self):
        original = element()
        row = self.normalize([original])[0]
        self.assertEqual(row["norad_id"], "100001")
        self.assertEqual(row["omm"]["NORAD_CAT_ID"], 100001)
        self.assertEqual(row["epoch"], "2026-10-28T06:00:00.123456Z")
        self.assertEqual(row["omm"]["EPOCH"], row["epoch"])
        self.assertIsNone(row["line1"])
        self.assertIsNone(row["line2"])
        self.assertEqual(original["EPOCH"], "2026-10-28T06:00:00.123456")
        self.assertIn("FORMAT=JSON", row["source_url"])

    def test_invalid_or_unusable_snapshot_cannot_be_accepted(self):
        cases = [[], {}, ["not a row"], [element(), element()],
                 [element(NORAD_CAT_ID=True)], [element(NORAD_CAT_ID=100001.5)],
                 [element(NORAD_CAT_ID=1000000000)], [element(EPOCH="2026-10-28")],
                 [element(EPOCH="2026-02-30T00:00:00")], [element(REF_FRAME="ITRF")],
                 [element(ECCENTRICITY=1)], [element(INCLINATION=181)],
                 [element(MEAN_MOTION=0)], [element(BSTAR=float("nan"))],
                 [element(MEAN_MOTION_DOT=float("inf"))], [element(MEAN_ANOMALY=-1)],
                 [element(TLE_LINE1="1 99999", TLE_LINE2="2 99999")]]
        for rows in cases:
            with self.subTest(rows=str(rows)[:150]), self.assertRaises(ValueError):
                self.normalize(rows)


class OrbitRefreshTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = (satellites._tle_cache, satellites._last_attempt_at,
                      satellites._last_success_at, satellites._last_error)
        satellites._tle_cache = []
        satellites._last_attempt_at = satellites._last_success_at = None
        satellites._last_error = None

    def tearDown(self):
        (satellites._tle_cache, satellites._last_attempt_at,
         satellites._last_success_at, satellites._last_error) = self.state

    async def refresh(self, handler):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await satellites.refresh_satellites(client)

    async def test_failure_preserves_cohort_and_success_clock(self):
        def success(request):
            self.assertEqual(request.url.params["FORMAT"], "JSON")
            return httpx.Response(200, json=[element()])
        self.assertTrue(await self.refresh(success))
        snapshot = copy.deepcopy(satellites._tle_cache)
        clock = satellites._last_success_at
        self.assertFalse(await self.refresh(lambda req: httpx.Response(429)))
        self.assertEqual(satellites._tle_cache, snapshot)
        self.assertEqual(satellites._last_success_at, clock)
        status = satellites.get_tle_status()
        self.assertEqual(status["status"], "failed")
        self.assertTrue(status["data_available"])
        self.assertEqual(status["error"], "upstream HTTP 429")

    async def test_empty_or_partial_validity_cannot_replace_last_good(self):
        self.assertTrue(await self.refresh(lambda req: httpx.Response(200, json=[element()])))
        snapshot = copy.deepcopy(satellites._tle_cache)
        for payload in ([], [element(), element(NORAD_CAT_ID=100002, EPOCH="bad")]):
            with self.subTest(payload=payload):
                self.assertFalse(await self.refresh(lambda req: httpx.Response(200, json=payload)))
                self.assertEqual(satellites._tle_cache, snapshot)

    async def test_unavailable_is_distinct_from_empty_success(self):
        self.assertEqual(satellites.get_tle_status(now=NOW)["status"], "unavailable")
        self.assertFalse(await self.refresh(lambda req: httpx.Response(200, text="not JSON")))
        status = satellites.get_tle_status()
        self.assertEqual(status["status"], "failed")
        self.assertIsNone(status["last_success_at"])
        self.assertFalse(status["data_available"])

    async def test_stream_size_limit_rejects_oversize_body(self):
        with patch.object(satellites, "MAX_RESPONSE_BYTES", 20):
            self.assertFalse(await self.refresh(lambda req: httpx.Response(200, content=b" " * 21)))
        self.assertEqual(satellites.get_tle_status()["status"], "failed")

    async def test_cache_age_and_epoch_age_are_separate(self):
        satellites._tle_cache = satellites.normalize_omm_records([element()], group="military", fetched_at=NOW)
        satellites._last_success_at = NOW
        status = satellites.get_tle_status(now=NOW + timedelta(hours=13))
        self.assertEqual(status["status"], "stale")
        self.assertTrue(status["data_stale"])
        self.assertEqual(status["data_age_seconds"], 13 * 3600)
        rows = satellites.get_tles(now=NOW)
        self.assertAlmostEqual(rows[0]["epoch_age_hours"], 6, places=3)
        rows[0]["omm"]["NORAD_CAT_ID"] = 1
        self.assertEqual(satellites.get_tles(now=NOW)[0]["omm"]["NORAD_CAT_ID"], 100001)

    async def test_group_failure_does_not_publish_partial_cohort(self):
        self.assertTrue(await self.refresh(lambda req: httpx.Response(200, json=[element()])))
        snapshot = copy.deepcopy(satellites._tle_cache)
        def response(request):
            if request.url.params["GROUP"] == "military":
                return httpx.Response(200, json=[element(NORAD_CAT_ID=100002)])
            return httpx.Response(503)
        with patch.object(satellites, "TLE_GROUPS", ["military", "other"]):
            self.assertFalse(await self.refresh(response))
        self.assertEqual(satellites._tle_cache, snapshot)


if __name__ == "__main__":
    unittest.main()
