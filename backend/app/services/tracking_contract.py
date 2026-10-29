"""Shared bounded numeric/time parsing for untrusted tracking messages."""
import json
import math
from datetime import datetime, timezone


def number(value, minimum=None, maximum=None):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    if not math.isfinite(result) or (minimum is not None and result < minimum) or (
        maximum is not None and result > maximum
    ):
        return None
    return result


def coordinates(lat, lon):
    return number(lat, -90, 90), number(lon, -180, 180)


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z") if epoch is not None else None


def source_epoch(value, *, now, milliseconds=False):
    stamp = number(value)
    if stamp is None:
        return None
    if milliseconds:
        stamp /= 1000
    # Refuse arbitrary monotonic clocks and future receiver clocks.
    return stamp if 946684800 <= stamp <= now + 30 else None


def text(value, limit=120):
    return value.strip()[:limit] if isinstance(value, str) else ""


async def bounded_json(client, url, *, params=None, max_bytes=2_000_000):
    """Stream decoded bytes so Content-Length/compression cannot bypass the cap."""
    async with client.stream("GET", url, params=params) as response:
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > max_bytes:
                raise ValueError("Tracking provider response exceeds byte limit")
            body.extend(chunk)
    return json.loads(body, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
