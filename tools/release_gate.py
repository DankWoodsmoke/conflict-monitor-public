"""Allowlisted public export with redacted content checks and byte manifest.

This is a content gate, not proof of production readiness or an exhaustive
secret detector. Never export the original working directory or Git history.
"""
import argparse
import hashlib
import json
import re
import sys
import stat
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_DIRS = {"backend", "frontend", "docs", "tools", ".github"}
ALLOWED_ROOT = {"README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "SECURITY.md", "CONTRIBUTING.md",
                "docker-compose.yml", ".env.example", ".gitignore", "sitrep_video.py", "gen_video_cron.sh"}
ALLOWED_SUFFIXES = {".py", ".tsx", ".ts", ".mjs", ".cjs", ".css", ".json", ".html", ".jpg", ".png", ".webp", ".svg", ".md", ".txt", ".ini", ".mako", ".yml", ".yaml", ".toml", ".ps1", ".sh", ".in", ".conf"}
ALLOWED_BASENAMES = {"Dockerfile", ".dockerignore", ".env.example", ".gitignore"}
EXCLUDED = {"node_modules", ".venv", ".git", "__pycache__", ".pytest_cache", "dist", "sessions", "artifacts", ".ruff_cache", "playwright-report", "test-results", "htmlcov"}
PATTERNS = {
    "private_key": re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "provider_credential": re.compile(rb"(?:sk-ant-|sk-proj-|sk-or-v1-|ghp_|github_pat_|xox[baprs]-)[A-Za-z0-9_\-]{16,}"),
    "google_browser_key": re.compile(rb"AIza[0-9A-Za-z_\-]{30,45}"),
    "embedded_session": re.compile(rb"(?im)^[ \t]*(?:TWITTER_AUTH_TOKEN|TWITTER_CT0|TELEGRAM_SESSION|ANTHROPIC_API_KEY|ADMIN_API_KEY)[ \t]*[:=][ \t]*[A-Za-z0-9_\-]{20,}"),
}


ASSIGNMENT = re.compile(rb"(?i)\b(?:TELEGRAM_SESSION|TELEGRAM_API_HASH|ANTHROPIC_API_KEY|ADMIN_API_KEY|AISSTREAM_API_KEY|FIRMS_MAP_KEY|OPENSKY_PASSWORD|POSTGRES_PASSWORD|POSTGRES_APP_PASSWORD|PGPASSWORD|TWITTER_BEARER_TOKEN|TWITTER_AUTH_TOKEN|TWITTER_CT0|ELEVENLABS_API_KEY|REPLICATE_API_TOKEN|PASSWORD|API_KEY|ACCESS_TOKEN)[\"']?[ \t]*[:=][ \t]*[\"']?([A-Za-z0-9_+./=\-]{16,})")
CREDENTIAL_URL = re.compile(rb"(?i)(?:postgresql(?:\+[a-z0-9]+)?|postgres|https?)://[^:/\s]+:([^@/\s]+)@")


def is_placeholder(value):
    value = value.lower()
    return (value in {b"postgres", b"password", b"secret", b"fixture_only_ci"} or
            value.startswith((b"fixture-", b"fixture_", b"example-", b"example_", b"your_", b"your-", b"offline-test-", b"settings.", b"${", b"<")))


def content_findings(data, rel):
    findings = []
    for name, pattern in PATTERNS.items():
        for match in pattern.finditer(data):
            findings.append({"file": rel, "line": data[:match.start()].count(b"\n") + 1, "kind": name})
    for name, pattern in (("credential_assignment", ASSIGNMENT), ("credential_url", CREDENTIAL_URL)):
        for match in pattern.finditer(data):
            if not is_placeholder(match.group(1)):
                findings.append({"file": rel, "line": data[:match.start()].count(b"\n") + 1, "kind": name})
    return findings


def export_files():
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if any(part in EXCLUDED for part in rel.parts):
            continue
        attrs = p.stat(follow_symlinks=False)
        if p.is_symlink() or getattr(attrs, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise ValueError(f"Symlink or reparse point requires explicit review: {rel}")
        if not p.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError(f"Resolved export path escapes candidate: {rel}")
        if not p.is_file():
            continue
        if rel.parts[0] not in ALLOWED_DIRS and str(rel) not in ALLOWED_ROOT:
            continue
        if p.name.startswith(".coverage"):
            continue
        if any(part.startswith(".") and part not in {".github", ".gitignore", ".dockerignore", ".env.example"} for part in rel.parts):
            raise ValueError(f"Hidden content requires explicit review: {rel}")
        if p.name.startswith(".env") and p.name != ".env.example":
            raise ValueError(f"Environment file blocked: {rel}")
        if p.name.startswith(".coverage"):
            continue
        if p.name.endswith((".pyc", ".tsbuildinfo", ".bak", ".log")):
            continue
        if p.suffix in {".pem", ".key", ".session", ".sql", ".gz", ".zip"}:
            raise ValueError(f"Private/runtime file type blocked: {rel}")
        if p.name not in ALLOWED_BASENAMES and p.suffix not in ALLOWED_SUFFIXES and str(rel) not in ALLOWED_ROOT:
            raise ValueError(f"File format requires explicit review: {rel}")
        yield p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan-only", action="store_true")
    parser.add_argument("--package-candidate", action="store_true")
    args = parser.parse_args()
    files = list(export_files())
    findings = []
    manifest = []
    snapshots = {}
    for p in files:
        data = p.read_bytes()
        rel = p.relative_to(ROOT).as_posix()
        snapshots[rel] = data
        findings.extend(content_findings(data, rel))
        manifest.append({"path": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    result = {"scope": "allowlisted_public_source", "file_count": len(files), "findings": findings,
              "exhaustive_secret_clearance": False, "production_readiness": "not_established_by_this_gate"}
    print(json.dumps(result, indent=2))
    if findings:
        return 1
    if args.package_candidate:
        destination = ROOT / "artifacts"
        destination.mkdir(exist_ok=True)
        package = destination / "conflict-monitor-0.2.0-rc.1-source.zip"
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
            for rel, data in snapshots.items():
                archive.writestr("conflict-monitor/" + rel, data)
            archive.writestr("conflict-monitor/RELEASE_MANIFEST.json", json.dumps({"status": "candidate",
                "verification": "See docs/VERIFICATION.md; incomplete gates prevent stable release.",
                "files": manifest}, indent=2))
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        package.with_suffix(".zip.sha256").write_text(digest + "  " + package.name + "\n", encoding="utf-8")
        print(f"CANDIDATE: {package.name} sha256={digest}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2)
