#!/bin/bash
# /opt/conflict-monitor/gen_video_cron.sh
# Checks every run if any recent SITREPs are missing videos and generates them.
# Add to crontab: */12 * * * * /opt/conflict-monitor/gen_video_cron.sh

LOCK=/tmp/gen_video.lock
LOG=/opt/conflict-monitor/videos/last_video.log

# Prevent concurrent runs — bail if lock is <18 minutes old
if [ -f "$LOCK" ]; then
    AGE=$(( $(date +%s) - $(stat -c %Y "$LOCK" 2>/dev/null || echo 0) ))
    if [ "$AGE" -lt 1080 ]; then
        exit 0
    fi
    rm -f "$LOCK"
fi

touch "$LOCK"
cleanup() { rm -f "$LOCK"; }
trap cleanup EXIT

cd /opt/conflict-monitor

# Find the most recent SITREP ID that has no video in the manifest
MISSING=$(python3 - <<'PYEOF'
import json, subprocess, sys

try:
    with open('videos/manifest.json') as f:
        manifest = json.load(f)
except Exception:
    manifest = {}

result = subprocess.run([
    'docker', 'exec',
    '-e', 'PGPASSWORD=ConflictMon1t0r!',
    'conflict-monitor-db-1',
    'psql', '-U', 'postgres', '-d', 'conflict_monitor',
    '-t', '-A', '-c', 'SELECT id FROM sitreps ORDER BY id DESC LIMIT 5'
], capture_output=True, text=True)

sitrep_ids = []
for line in result.stdout.strip().splitlines():
    line = line.strip()
    if line.isdigit():
        sitrep_ids.append(int(line))

# Find IDs not in manifest
missing = [i for i in sitrep_ids if str(i) not in manifest]
if missing:
    # Generate for the most recent missing one
    print(missing[0])
PYEOF
)

if [ -n "$MISSING" ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting video for SITREP #${MISSING}" >> "$LOG"
    python3 /opt/conflict-monitor/sitrep_video.py >> "$LOG" 2>&1
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Video generation complete (exit $?)" >> "$LOG"
fi
