#!/bin/sh
set -eu

# Provider bytes, RSA signature and fingerprint were independently verified
# before pinning. Fetch/build tools remain in the disposable builder stage.
version=9.0.2
archive_sha256=8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e
key_fingerprint=FCF986EA15E6E293A5644F10B4322F04D67658D8
mkdir -p /build /opt/ffmpeg/share/source
cd /build
curl --fail --location --proto '=https' --tlsv1.2 --connect-timeout 15 --max-time 120 --max-filesize 30000000 -o ffmpeg.tar.xz "https://ffmpeg.org/releases/ffmpeg-${version}.tar.xz"
printf '%s  ffmpeg.tar.xz\n' "$archive_sha256" | sha256sum -c -
curl --fail --location --proto '=https' --tlsv1.2 --connect-timeout 15 --max-time 30 --max-filesize 20000 -o ffmpeg.tar.xz.asc "https://ffmpeg.org/releases/ffmpeg-${version}.tar.xz.asc"
curl --fail --location --proto '=https' --tlsv1.2 --connect-timeout 15 --max-time 30 --max-filesize 50000 -o ffmpeg-devel.asc https://ffmpeg.org/ffmpeg-devel.asc
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
