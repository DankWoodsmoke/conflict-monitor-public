FROM postgres:17.11-alpine3.24@sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b AS spatial-build
RUN apk update && apk upgrade --no-cache && apk add --no-cache \
    build-base clang21 llvm21-dev pkgconf perl cunit-dev geos-dev proj-dev \
    libxml2-dev json-c-dev protobuf-c-dev pcre2-dev openssl-dev icu-dev \
    lz4-dev zstd-dev curl ca-certificates git
COPY build_postgis.sh /build_postgis.sh
COPY flatgeobuf-3.6.4.patch /flatgeobuf-3.6.4.patch
RUN sh /build_postgis.sh

FROM postgres:17.11-alpine3.24@sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b AS sqlite-build
RUN apk add --no-cache abuild build-base readline-dev curl ca-certificates \
    && adduser -D builder && addgroup builder abuild
COPY --chown=builder:builder APKBUILD smoke.sql session_probe.c /home/builder/sqlite/
COPY build_sqlite.sh /build_sqlite.sh
WORKDIR /home/builder/sqlite
RUN sh /build_sqlite.sh

FROM postgres:17.11-alpine3.24@sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b AS zlib-build
RUN apk add --no-cache abuild build-base curl ca-certificates \
    && adduser -D builder && addgroup builder abuild
COPY --chown=builder:builder zlib/ /home/builder/zlib/
WORKDIR /home/builder/zlib
RUN sh build_zlib.sh

FROM postgres:17.11-alpine3.24@sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b
RUN apk update && apk upgrade --no-cache && apk add --no-cache \
    geos proj libxml2 json-c protobuf-c libstdc++ pcre2 su-exec=0.3-r0 \
    && find /usr -xdev -type f -perm /6000 -exec chmod a-s '{}' +
COPY --from=spatial-build /opt/postgis/ /
COPY --from=sqlite-build /out/ /usr/local/share/postgis-build/private-sqlite/
COPY --from=zlib-build /out/ /usr/local/share/postgis-build/private-zlib/
COPY initdb-postgis.sh /docker-entrypoint-initdb.d/10_postgis.sh
RUN cp /usr/local/share/postgis-build/private-zlib/*.rsa.pub /etc/apk/keys/ \
    && apk verify /usr/local/share/postgis-build/private-zlib/zlib-1.4-r0.apk \
    && apk add --no-cache /usr/local/share/postgis-build/private-zlib/zlib-1.4-r0.apk \
    && apk info -e zlib=1.4-r0 \
    && test ! -e /usr/lib/libz.so.1.3.2 \
    && sha256sum /usr/lib/libz.so.1.4 > /usr/local/share/postgis-build/private-zlib/installed-library.sha256 \
    && ldd /usr/local/bin/pg_dump > /usr/local/share/postgis-build/private-zlib/pg-dump-library-binding.txt \
    && cp /usr/local/share/postgis-build/private-sqlite/*.rsa.pub /etc/apk/keys/ \
    && apk add --no-cache /usr/local/share/postgis-build/private-sqlite/sqlite-libs-3.54.1-r0.apk \
    && apk info -e sqlite-libs=3.54.1-r0 \
    && test ! -e /usr/bin/sqlite3 \
    && sha256sum /usr/lib/libsqlite3.so.3.54.1 > /usr/local/share/postgis-build/private-sqlite/installed-library.sha256 \
    && ldd /usr/lib/libproj.so.25 > /usr/local/share/postgis-build/private-sqlite/proj-library-binding.txt \
    && mkdir -p /usr/local/share/postgis-build/su-exec \
    && wget -T 30 -O /usr/local/share/postgis-build/su-exec/su-exec-0.3-r0.apk https://dl-cdn.alpinelinux.org/alpine/v3.24/main/$(apk --print-arch)/su-exec-0.3-r0.apk \
    && apk verify /usr/local/share/postgis-build/su-exec/su-exec-0.3-r0.apk \
    && cp /usr/local/bin/docker-entrypoint.sh /usr/local/share/postgis-build/su-exec/original-entrypoint.sh \
    && test "$(grep -c 'exec gosu postgres' /usr/local/bin/docker-entrypoint.sh)" = 1 \
    && test "$(grep -c gosu /usr/local/bin/docker-entrypoint.sh)" = 1 \
    && sed -i 's/exec gosu postgres/exec su-exec postgres/' /usr/local/bin/docker-entrypoint.sh \
    && rm /usr/local/bin/gosu \
    && test ! -e /usr/local/bin/gosu \
    && apk info -e su-exec=0.3-r0 \
    && sha256sum /sbin/su-exec /usr/local/bin/docker-entrypoint.sh /usr/local/share/postgis-build/su-exec/original-entrypoint.sh /usr/local/share/postgis-build/su-exec/su-exec-0.3-r0.apk > /usr/local/share/postgis-build/su-exec/SHA256SUMS
LABEL cm.private.owner="postgis-alpine-candidate-20261104" \
      org.opencontainers.image.description="Private PostgreSQL17.11/PostGIS3.6.4 FlatGeobuf backport; Alpine-native SQLite3.54.1 and official zlib1.4 local signed APKs; signed su-exec0.3; gosu removed; no installed SQLite CLI; amd64 qualified, other architectures unverified"
