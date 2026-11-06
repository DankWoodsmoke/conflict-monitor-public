#!/bin/sh
set -eu
input_dir="$(cd "$(dirname "$0")" && pwd)"
evidence=/opt/ffmpeg/share/security
mkdir -p "$evidence"
(
    cd "$input_dir"
    printf '%s\n' \
        'fb9d5c7625495040858ef316396d10d8be62c514187d0e19cc455410dbce79a9  ffmpeg-CVE-2026-107676.patch' \
        '6ca7762b7d5e5730848e75ca48a8cbcae2c8acfe6e5db1cbbe7427a5a84b2ed3  ffmpeg-CVE-2026-107677.patch' \
        '594a0cbca9527bc1edab7f76679af5a73cee23aadc878e2cc6a9001e22742c45  ffmpeg-CVE-2026-107678-free.patch' \
        'a64eeeec5b90e89241a29b10c3b8ed7ac9fb380be82f6bebf06df6b9d9b4e77a  ffmpeg-CVE-2026-107678-append.patch' \
        'af4bf01465777b2b8d159e8cd8a2185f155a0db39baa7fc2c0e6acf4d5f734b8  ffmpeg-CVE-2026-107678-mov.patch' \
        '3f81fd5d5867e91f2cf735563973b46426a5524e1f42bbe836a46ae2841e4424  ffmpeg_security_probe.c' | sha256sum -c -
)
sha256sum libavutil/hdr_dynamic_metadata.c libavutil/avstring.c libavutil/encryption_info.c \
    libavutil/encryption_info.h libavformat/isom.h libavformat/mov.c > "$evidence/source-before.sha256"
for file in ffmpeg-CVE-2026-107676.patch ffmpeg-CVE-2026-107677.patch \
    ffmpeg-CVE-2026-107678-free.patch ffmpeg-CVE-2026-107678-append.patch ffmpeg-CVE-2026-107678-mov.patch; do
    patch --batch --fuzz=0 -p1 < "$input_dir/$file" >> "$evidence/patch.log"
    cp "$input_dir/$file" "$evidence/"
done
printf '%s\n' \
    'fd4c3136169f0de91375d769788fb10967875baae44e62fba11e2ffd43f988a3  libavutil/avstring.c' \
    '23df4161f23452d5a5c1c586fee6e0b193e0df701ffb611d95c50a8b4fb0fcfe  libavutil/hdr_dynamic_metadata.c' \
    '17505745d726433d4d0aa4740809caaa38e8befd640f75806ecaa63ac896b0a1  libavutil/encryption_info.c' \
    '782fcd91eee6cce50eb6336d6311c4c113a38f1d8f21e6cc1eb616cb1cac653b  libavutil/encryption_info.h' \
    '25720c5721eff23c0059e8b1e4649eeebcf72d94797d239d6cc476bbd5ef15b6  libavformat/mov.c' \
    '823d27a6804f115860525c9154ec41e0ce817a67234cf888fc52c8cb1a135938  libavformat/isom.h' | sha256sum -c -
sha256sum libavutil/hdr_dynamic_metadata.c libavutil/avstring.c libavutil/encryption_info.c \
    libavutil/encryption_info.h libavformat/isom.h libavformat/mov.c > "$evidence/source-after.sha256"
cp "$input_dir/patch_ffmpeg.sh" "$input_dir/check_ffmpeg_security.sh" \
    "$input_dir/ffmpeg_security_probe.c" "$input_dir/build_ffmpeg.sh" "$evidence/"
cat > "$evidence/UPSTREAM.txt" <<'EOF'
Local source security backports to FFmpeg9.0.2, nominal version unchanged.
CVE-2026-107676: 2c2f6e96e31795ae95a8f8323a493ffbc493111f
CVE-2026-107677: ed27bfcbbbc0872c0195eaf4dd2c0c93b9f1778e
CVE-2026-107678: 969c7eb091989a664cb7bf66a1f02051cc46cb52
                 d1434518fbd03789e3e5dc0657a7a9f1123ce074
                 71403a21b02a92b925e26e609e9bd3e48df451cf
Upstream repository: https://github.com/FFmpeg/FFmpeg
The append patch excludes development-branch doc/APIchanges and libavutil/version.h only.
All implementation changes and upstream regression cases are retained.
Raw scanner records remain visible; no ignore or release-gate change.
EOF
