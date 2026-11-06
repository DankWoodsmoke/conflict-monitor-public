FROM cgr.dev/chainguard/wolfi-base@sha256:771146c2dfc880902a185f060c3db5571473c46b267edd98c3119c83068dfb61 AS media-build
# Build only the local media components the worker uses.
RUN apk add --no-cache build-base=1-r10 pkgconf=3.0.10-r2 nasm=3.02-r3 x264-dev=2025.06.08-r7 \
    zlib=1.3.2.1_rc20260921-r2 zlib-dev=1.3.2.1_rc20260921-r2 curl=8.23.0-r3 gpg=2.4.9-r12 gpgv=2.4.9-r12 gnutar=1.35-r15 xz=5.8.4-r0 patch=2.8.1-r1
COPY container/ /media-input/
RUN sh /media-input/build_ffmpeg.sh

FROM cgr.dev/chainguard/wolfi-base@sha256:771146c2dfc880902a185f060c3db5571473c46b267edd98c3119c83068dfb61 AS runtime
RUN apk add --no-cache python-3.12=3.12.16_git20261030-r0 ttf-dejavu=2.37-r9 x264-libs=2025.06.08-r7 \
    libstdc++=16.2.0-r2 zlib=1.3.2.1_rc20260921-r2

FROM runtime AS socket-security-build
RUN apk add --no-cache build-base=1-r10 python-3.12-dev=3.12.16_git20261030-r0 patch=2.8.1-r1
COPY container/build_socket_patch.py container/CVE-2026-116566.patch /socket-security-input/
RUN python3.12 /socket-security-input/build_socket_patch.py fetch
RUN --network=none python3.12 /socket-security-input/build_socket_patch.py build

FROM runtime AS glibc-security-build
RUN apk add --no-cache build-base=1-r10 patch=2.8.1-r1 bash=5.3-r14 gawk=5.4.1-r4 \
    bison=3.8.2-r64 flex=2.6.4-r16 texinfo=7.3-r10 gettext=1.0-r8 gnutar=1.35-r15 \
    grep=3.12-r11 sed=4.10-r5 coreutils=9.12-r7 findutils=4.11.0-r5
COPY container/native_build.py container/build_glibc_patch.py container/CVE-2026-84243.patch \
    container/glibc-wolfi-startup.patch container/glibc-wolfi-fdo.patch \
    container/glibc-wolfi-test-matcher.patch /glibc-security-input/
RUN python3.12 /glibc-security-input/build_glibc_patch.py fetch
RUN --network=none python3.12 /glibc-security-input/build_glibc_patch.py build

FROM runtime AS python-packages
RUN apk add --no-cache py3.12-pip=26.2.2-r2
COPY requirements.txt /build/requirements.txt
RUN python3.12 -m venv --without-pip /opt/monitor \
    && python3.12 -m pip --python /opt/monitor/bin/python install --no-cache-dir pip==26.2.2 setuptools==84.2.1 \
    && /opt/monitor/bin/python -m pip install --no-cache-dir -r /build/requirements.txt \
    && /opt/monitor/bin/python -m pip check

FROM python-packages AS curl-security-build
RUN apk add --no-cache build-base=1-r10 python-3.12-dev=3.12.16_git20261030-r0 \
    patch=2.8.1-r1 bash=5.3-r14 cmake=4.4.5-r0 pkgconf=3.0.10-r2 \
    clang-21=21.1.8-r17 samurai=1.3-r3 gnutar=1.35-r15 grep=3.12-r11 \
    sed=4.10-r5 coreutils=9.12-r7 findutils=4.11.0-r5 perl=5.44.0-r4
COPY container/native_build.py container/build_curl_patch.py container/CVE-2026-27135.patch \
    container/nghttp2-prerequisite.patch container/nghttp2-altsvc.patch \
    container/nghttp2-state-tests.patch container/boringssl-test-deleters.patch container/boringssl-crl-tests.patch \
    container/boringssl-crl-tests.upstream.patch container/boringssl-CVE-2026-35189.patch \
    container/boringssl-CVE-2026-35189.upstream.patch container/boringssl-rng-thread-local.patch \
    container/nghttp2-client-hardening.patch container/nghttp2-client-hardening.json \
    container/nghttp2-pr2826.upstream.patch container/nghttp2-pr2829.upstream.patch \
    container/nghttp2-pr2926.upstream.patch container/nghttp2-pr2931.upstream.patch \
    container/nghttp2-pr2934.upstream.patch container/nghttp2-pr2945.upstream.patch \
    container/nghttp2-pr2485.upstream.patch container/nghttp2-pr2488.upstream.patch \
    container/nghttp2-pr2508.upstream.patch container/nghttp2-pr2509.upstream.patch \
    container/nghttp2-pr2510.upstream.patch container/nghttp2-pr2598.upstream.patch \
    container/nghttp2-pr2599.upstream.patch container/nghttp2-pr2607.upstream.patch \
    container/nghttp2-pr2856.upstream.patch /curl-security-input/
RUN /opt/monitor/bin/python /curl-security-input/build_curl_patch.py fetch
RUN --network=none /opt/monitor/bin/python /curl-security-input/build_curl_patch.py build

FROM runtime
WORKDIR /app
ENV PATH=/opt/monitor/bin:$PATH HOME=/home/monitor LANG=C.UTF-8
COPY --from=glibc-security-build /opt/glibc-security/lib/libc.so.6 /usr/lib/libc.so.6
COPY --from=glibc-security-build /opt/glibc-security/provenance/ /usr/local/share/glibc-security/CVE-2026-84243/
COPY --from=socket-security-build /opt/socket-security/lib/ /usr/lib/python3.12/lib-dynload/
COPY --from=socket-security-build /opt/socket-security/provenance/ /usr/local/share/cpython-security/CVE-2026-116566/
COPY --from=media-build /opt/ffmpeg/bin/ffmpeg /opt/ffmpeg/bin/ffprobe /usr/local/bin/
COPY --from=media-build /opt/ffmpeg/share /usr/local/share/ffmpeg
COPY --from=python-packages /opt/monitor /opt/monitor
COPY --from=curl-security-build /opt/curl-security/lib/ /opt/monitor/lib/python3.12/site-packages/curl_cffi/
COPY --from=curl-security-build /opt/curl-security/provenance/ /usr/local/share/curl-security/
COPY --from=curl-security-build /opt/curl-security/zlib/libz.so.1.4 /usr/lib/libz.so.1.4
RUN test "$(readlink -f /usr/lib/libz.so.1)" = /usr/lib/libz.so.1.3.2.1-motley \
    && ln -sfn libz.so.1.4 /usr/lib/libz.so.1 \
    && rm /usr/lib/libz.so.1.3.2.1-motley \
    && /opt/monitor/bin/python -c 'import zlib; assert zlib.ZLIB_RUNTIME_VERSION == "1.4"'
COPY requirements.txt .
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
# The base creates an empty, inaccessible man-account directory. Remove only
# that empty directory so the nonroot privilege audit can traverse all of /usr.
RUN addgroup -S -g 10001 monitor && adduser -S -D -u 10001 -G monitor -h /home/monitor monitor \
    && mkdir -p /app/sessions /app/videos/briefing \
    && chown -R monitor:monitor /app/sessions /app/videos \
    && rmdir /usr/man \
    && find /usr -xdev -type f -perm /6000 -exec chmod a-s '{}' +
# Python and the market cache use the library. The upstream recovery shell
# must stay outside the runtime.
RUN set -eu; \
    apk info -e sqlite-libs >/dev/null 2>&1; \
    sqlite_shell="$(find /usr /opt -xdev \( -type f -o -type l \) -name sqlite3 -print -quit)"; \
    if [ -n "$sqlite_shell" ] || command -v sqlite3 >/dev/null || apk info -e sqlite >/dev/null 2>&1; then \
        echo "SQLite command-line shell is forbidden in the backend image" >&2; \
        exit 1; \
    fi
USER 10001:10001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--ws-max-size", "4096"]
