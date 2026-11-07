#!/bin/sh
set -eu
input_dir="$(cd "$(dirname "$0")" && pwd)"
evidence=/opt/ffmpeg/share/security
cc -I. "$input_dir/ffmpeg_security_probe.c" libavutil/libavutil.a -lm -pthread -o /build/ffmpeg-security-probe
for name in empty-search deep-encryption-list hdr-roundtrip; do
    (ulimit -s 256; timeout 3 /build/ffmpeg-security-probe "$name") > "$evidence/$name.log" 2>&1
    printf '%s PASS\n' "$name" >> "$evidence/regression-results.txt"
done
make fate-encryption-info > "$evidence/upstream-encryption-suite.log" 2>&1
sha256sum /build/ffmpeg-security-probe ffmpeg ffprobe > "$evidence/native.sha256"
