#!/bin/sh
set -eu

# Provider bytes, RSA signature and fingerprint were independently verified
# before pinning. Fetch/build tools remain in the disposable builder stage.
version=9.0.2
archive_sha256=8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e
key_fingerprint=FCF986EA15E6E293A5644F10B4322F04D67658D8

# Three bounded GET attempts tolerate transient transport/HTTP failures. TLS
# verification, redirect/protocol errors and permanent HTTP failures fail closed.
# Per-file upper bounds: 3 * max-time + 1s + 2s (363s archive; 93s each metadata).
fetch() {
    fetch_target=$1 fetch_seconds=$2 fetch_size=$3 fetch_url=$4
    fetch_attempt=1
    while :; do
        if fetch_status=$(curl --fail --location --proto '=https' --proto-redir '=https' --max-redirs 3 --tlsv1.2 --connect-timeout 15 --max-time "$fetch_seconds" --max-filesize "$fetch_size" --write-out '%{http_code}' -o "$fetch_target" "$fetch_url"); then
            return 0
        else
            fetch_exit=$?
        fi
        case "$fetch_exit:$fetch_status" in
            5:*|6:*|7:*|18:*|28:*|35:*|52:*|55:*|56:*|92:*|22:408|22:429|22:500|22:502|22:503|22:504|22:522|22:524) ;;
            *) return "$fetch_exit" ;;
        esac
        [ "$fetch_attempt" -lt 3 ] || return "$fetch_exit"
        sleep "$fetch_attempt"
        fetch_attempt=$((fetch_attempt + 1))
    done
}

mkdir -p /build /opt/ffmpeg/share/source
cd /build
fetch ffmpeg.tar.xz 120 30000000 "https://ffmpeg.org/releases/ffmpeg-${version}.tar.xz"
printf '%s  ffmpeg.tar.xz\n' "$archive_sha256" | sha256sum -c -
fetch ffmpeg.tar.xz.asc 30 20000 "https://ffmpeg.org/releases/ffmpeg-${version}.tar.xz.asc"
fetch ffmpeg-devel.asc 30 50000 https://ffmpeg.org/ffmpeg-devel.asc
mkdir -m 700 /build/gnupg
gpg --batch --homedir /build/gnupg --no-auto-key-retrieve --import ffmpeg-devel.asc
gpg --batch --homedir /build/gnupg --no-auto-key-retrieve --status-fd 1 --verify ffmpeg.tar.xz.asc ffmpeg.tar.xz > signature.status
grep -F "[GNUPG:] VALIDSIG ${key_fingerprint} " signature.status
cp ffmpeg.tar.xz "/opt/ffmpeg/share/source/ffmpeg-${version}.tar.xz"
cp ffmpeg.tar.xz.asc ffmpeg-devel.asc signature.status /opt/ffmpeg/share/source/
tar -xJf ffmpeg.tar.xz
cd "ffmpeg-${version}"
./configure \
    --prefix=/opt/ffmpeg \
    --disable-autodetect --disable-everything --disable-network \
    --disable-debug --disable-doc --disable-shared --enable-static \
    --disable-avdevice --disable-ffplay --enable-ffmpeg --enable-ffprobe \
    --enable-gpl --enable-libx264 --enable-zlib \
    --enable-decoder=png,pcm_s16le,h264,aac \
    --enable-encoder=libx264,aac,pcm_s16le,wrapped_avframe \
    --enable-parser=png,h264,aac \
    --enable-bsf=h264_mp4toannexb \
    --enable-demuxer=image2,wav,mov,concat \
    --enable-muxer=mp4,null \
    --enable-protocol=file,pipe \
    --enable-filter=scale,format,aresample,anull,null
make -j2
make install
cp COPYING.GPLv2 COPYING.GPLv3 COPYING.LGPLv2.1 COPYING.LGPLv3 LICENSE.md /opt/ffmpeg/share/
cp ffbuild/config.log /opt/ffmpeg/share/build-config.log
/opt/ffmpeg/bin/ffmpeg -hide_banner -buildconf > /opt/ffmpeg/share/buildconf.txt 2>&1
/opt/ffmpeg/bin/ffmpeg -hide_banner -protocols > /opt/ffmpeg/share/protocols.txt 2>&1
/opt/ffmpeg/bin/ffmpeg -hide_banner -demuxers > /opt/ffmpeg/share/demuxers.txt 2>&1
/opt/ffmpeg/bin/ffmpeg -hide_banner -decoders > /opt/ffmpeg/share/decoders.txt 2>&1
# The separately linked libx264 package retains its Debian copyright/source
# information under /usr/share/doc in the runtime image.
