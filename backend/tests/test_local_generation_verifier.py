"""Independent qualification tool boundaries; tests never queue real generation."""

import hashlib
import importlib.util
import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location(
    "local_generation_verifier",
    Path(__file__).resolve().parents[2] / "tools/verify_local_generation.py",
)
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


@pytest.mark.parametrize(
    "url",
    [
        "https://remote.example:443",
        "http://user:fixture-password@localhost:2",
        "http://127.0.0.1:2/evil",
        "http://127.0.0.1:2?key=x",
        "http://localhost",
    ],
)
def test_qualifier_refuses_nonloopback_and_credential_origins(url):
    with pytest.raises(subject.VerificationError):
        subject.local_origin(url, api=True)


def test_no_execute_writes_incomplete_receipt_without_loading_key_or_calling_api(
    monkeypatch, tmp_path
):
    execute = Mock(side_effect=AssertionError("Must not execute"))
    monkeypatch.setattr(subject, "execute", execute)
    output = tmp_path / "receipt.json"
    assert subject.main(["--output", str(output)]) == 2
    assert json.loads(output.read_text())["status"] == "NOT_EXECUTED"
    execute.assert_not_called()


def test_failed_run_preserves_previous_receipt_and_never_prints_secret(
    monkeypatch, tmp_path, capsys
):
    def failed(*args):
        raise subject.VerificationError("controlled failure")

    monkeypatch.setattr(subject, "execute", failed)
    monkeypatch.setenv("ADMIN_API_KEY", "fixture-operator-value-never-output")
    output = tmp_path / "receipt.json"
    output.write_text('{"prior":"preserve"}')
    assert subject.main(["--execute", "--output", str(output)]) == 1
    assert (
        next(iter(tmp_path.glob("receipt-prior-*.json"))).read_text()
        == '{"prior":"preserve"}'
    )
    assert (
        "fixture-operator-value-never-output"
        not in capsys.readouterr().out + output.read_text()
    )


def test_current_rss_selection_and_binding_preserve_literal_unicode():
    raw = "🛰️ Publisher denies the reported strike."
    event = {
        "id": 55,
        "source": "rss_publisher",
        "classification_status": "not_requested",
        "severity": 0,
        "raw_text": raw,
        "summary": raw,
        "source_url": "https://example.org/report",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    row = {
        "id": 55,
        "source_url": event["source_url"],
        "original_text_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "text": raw,
        "published_at": event["timestamp"],
        "source": "rss publisher",
        "source_platform": event["source"],
        "headline": raw,
    }
    assert subject.select_report([event]) is event
    assert subject.source_binding(row, event)
    event["source"] = "rss_aljazeera"
    row["source_platform"] = event["source"]
    row["source"] = "Al Jazeera"
    assert subject.source_binding(row, event)
    row["source"] = "aljazeera"
    assert not subject.source_binding(row, event)
    event["source"] = "rss_publisher"
    row["source_platform"] = event["source"]
    row["source"] = "rss publisher"
    row["text"] = raw.replace("denies", "confirms")
    assert not subject.source_binding(row, event)
    event["timestamp"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    with pytest.raises(subject.VerificationError):
        subject.select_report([event])


def test_sql_query_container_is_validated_before_subprocess(monkeypatch):
    call = Mock(side_effect=AssertionError("No shell/database call allowed"))
    monkeypatch.setattr(subject.subprocess, "run", call)
    with pytest.raises(subject.VerificationError):
        subject.database_snapshot("db; unsafe", 55)
    with pytest.raises(subject.VerificationError):
        subject.database_snapshot("valid-db", True)
    call.assert_not_called()


def test_real_http_redirect_does_not_forward_operator_header():
    received = []

    class Target(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(self.headers.get("X-Admin-Key"))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    target = ThreadingHTTPServer(("127.0.0.1", 0), Target)

    class Redirect(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(302)
            self.send_header(
                "Location", f"http://127.0.0.1:{target.server_port}/stolen"
            )
            self.end_headers()

        def log_message(self, *args):
            pass

    redirect = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    threads = [
        threading.Thread(target=server.serve_forever, daemon=True)
        for server in (target, redirect)
    ]
    for thread in threads:
        thread.start()
    try:
        client = subject.Client(
            f"http://127.0.0.1:{redirect.server_port}", "fixture-operator-header"
        )
        with pytest.raises(subject.VerificationError, match="302"):
            client.json("/briefing/analyze", data={"event_ids": [55]})
        assert not received
    finally:
        for server in (target, redirect):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)
