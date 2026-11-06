"""Fail-closed public reader policy for dedicated source publication datasets.

Legacy whole-corpus switches cannot admit private reports or tracking caches.
Generated artifacts and operator APIs have no public admission path yet.
"""
import re
from app.config import settings


PUBLIC_NOTICE = (
    "Public research workspace. Independent NASA thermal observations and adsb.lol aircraft snapshots provide source context, not strike or mission detection. Private reports and tracking are withheld. "
    "Unavailable layers are withheld, not evidence of no activity. "
    "Generated briefings and media are not published."
)
TRACKING_UNAVAILABLE = "Private tracking/replay is excluded. Independent adsb.lol publication has separate source, license and freshness limits."
_REPORT_PATHS = re.compile(
    r"/events(?:/(?:time-range|batch|anomalies|delivery/(?:baseline|changes)|[0-9]+(?:/location-candidates)?))?"
)
_TRACK_PATHS = re.compile(r"/tracking/(?:aircraft(?:/[A-Za-z0-9]+/track)?|vessels|jamming|tle)")


def public_capabilities() -> dict:
    return {
        "public_read_only": settings.public_read_only,
        "public_reports_enabled": False,
        "public_observations_enabled": settings.public_read_only and not settings.demo_mode,
        "public_aircraft_enabled": settings.public_read_only and not settings.demo_mode,
        "public_tracking_enabled": False,
        "public_tracking_unavailable_reason": TRACKING_UNAVAILABLE if settings.public_read_only else "",
        "public_media_enabled": False,
        "public_notice": PUBLIC_NOTICE if settings.public_read_only else "",
    }


def public_http_denial(method: str, path: str) -> tuple[int, str] | None:
    if not settings.public_read_only:
        return None
    if method not in {"GET", "HEAD"}:
        return 403, "Public deployment is read-only"
    if path in {"/", "/health", "/config", "/status"}:
        return None
    if path in {"/publication/observations", "/publication/observations/download"} and not settings.demo_mode:
        return None
    if (path == "/publication/aircraft" or re.fullmatch(r"/publication/(?:observations|aircraft)/download/[0-9a-f]{64}", path)) and not settings.demo_mode:
        return None
    if _REPORT_PATHS.fullmatch(path):
        return 503, "Private reports are not part of the public publication dataset"
    if _TRACK_PATHS.fullmatch(path):
        return 503, TRACKING_UNAVAILABLE
    if path in {"/tracking/snapshots", "/satellite/hotspots"}:
        return 503, "This mixed-data layer requires publication approval and a qualified shared tracking feed"
    return 403, "This endpoint is unavailable in public read-only mode"
