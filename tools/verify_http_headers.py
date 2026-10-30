"""Check the built local Compose HTTP boundary without fetching any provider.

Only literal loopback origins are accepted. Redirects are never followed and
response bodies have a fixed byte bound. Output contains flags and hashes,
never HTML, source reports, cookies or authentication values.
"""

import argparse
import hashlib
import ipaddress
import json
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from http.client import HTTPException
from pathlib import Path
from urllib.parse import urlsplit

MAX_BODY = 256_000


def local_origin(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or not parsed.hostname
    ):
        raise ValueError("Use a credential-free literal loopback origin")
    if not ipaddress.ip_address(parsed.hostname).is_loopback:
        raise ValueError("Only literal loopback origins are allowed")
    _ = parsed.port  # Validate malformed/out-of-range ports before any request.
    return value.rstrip("/")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def fetch(origin, path, *, method="GET"):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(origin + path, method=method)
    try:
        response = opener.open(request, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise ValueError("HTTP fixture response exceeds the body bound")
        return response.status, response.headers, body


def consistent(headers, name, expected):
    values = headers.get_all(name, [])
    return bool(values) and all(value.strip().lower() == expected for value in values)


def qualify(frontend, backend):
    frontend, backend = local_origin(frontend), local_origin(backend)
    status, headers, html = fetch(frontend, "/")
    matches = re.findall(rb'src="(/assets/[A-Za-z0-9_-]+\.js)"', html)
    if status != 200 or not matches:
        raise ValueError("The built HTML must name its local hashed application script")
    asset = matches[0].decode("ascii")
    cases = [("html", status, headers, 200, "html")]
    for name, origin, path, expected, policy, method in [
        ("hashed_asset", frontend, asset, 200, "immutable_asset", "HEAD"),
        (
            "missing_asset",
            frontend,
            "/assets/__security_fixture_missing__.js",
            404,
            "error",
            "GET",
        ),
        ("proxied_health", frontend, "/api/health", 200, "api", "GET"),
        (
            "proxied_404",
            frontend,
            "/api/__security_fixture_missing__",
            404,
            "api",
            "GET",
        ),
        ("direct_health", backend, "/health", 200, "api_direct", "GET"),
        (
            "direct_404",
            backend,
            "/__security_fixture_missing__",
            404,
            "api_direct",
            "GET",
        ),
    ]:
        actual, actual_headers, _ = fetch(origin, path, method=method)
        cases.append((name, actual, actual_headers, expected, policy))
    rows = []
    for name, actual, actual_headers, expected, policy in cases:
        cache = ",".join(actual_headers.get_all("Cache-Control", [])).lower()
        checks = {
            "expected_status": actual == expected,
            "nosniff": consistent(actual_headers, "X-Content-Type-Options", "nosniff"),
            "referrer_policy": consistent(
                actual_headers, "Referrer-Policy", "strict-origin-when-cross-origin"
            ),
        }
        if policy != "api_direct":
            checks["sameorigin_frame_policy"] = consistent(
                actual_headers, "X-Frame-Options", "sameorigin"
            )
        if policy == "html":
            checks["html_revalidated_or_not_stored"] = (
                "no-cache" in cache or "no-store" in cache
            )
        elif policy == "immutable_asset":
            checks["hashed_asset_immutable_year"] = (
                "immutable" in cache and "max-age=31536000" in cache
            )
        elif policy.startswith("api"):
            checks["api_not_stored"] = "no-store" in cache
        elif policy == "error":
            checks["missing_asset_not_immutable"] = (
                "immutable" not in cache and "max-age=31536000" not in cache
            )
        rows.append({"case": name, "status": actual, "checks": checks})
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "scope": "Actual built loopback HTML, hashed script, frontend/API errors and proxied/direct API response headers",
        "status": "PASS"
        if all(all(row["checks"].values()) for row in rows)
        else "FAIL",
        "cases": rows,
        "html_sha256": hashlib.sha256(html).hexdigest(),
        "redirects_followed": 0,
        "provider_or_generation_requests": 0,
        "limits": [
            "This checks the declared local header/cache policy, not TLS/HSTS, CSP completeness, every endpoint or arbitrary deployment security.",
            "An absent cache lifetime on the missing asset is not a claim that all intermediaries will never cache an error.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = qualify(args.frontend_url, args.backend_url)
    except (OSError, ValueError, RuntimeError, HTTPException) as error:
        result = {"status": "FAIL/INCOMPLETE", "error_type": type(error).__name__}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 2)
