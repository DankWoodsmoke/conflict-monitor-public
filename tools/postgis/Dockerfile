FROM postgres:17-trixie@sha256:31ba9c94a03ada9988f2bb493a22a75eef3a185884533e5cdbcd498ea835b08f AS spatial-build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential clang-19 llvm-19-dev postgresql-server-dev-17 \
    libgeos-dev libproj-dev libxml2-dev libjson-c-dev libprotobuf-c-dev protobuf-c-compiler \
    libpcre2-dev libssl-dev libicu-dev liblz4-dev libzstd-dev libcunit1-dev curl ca-certificates git gnupg \
    && rm -rf /var/lib/apt/lists/*
COPY build_postgis.sh /build_postgis.sh
COPY flatgeobuf-3.6.4.patch /flatgeobuf-3.6.4.patch
RUN sh /build_postgis.sh

FROM postgres:17-trixie@sha256:31ba9c94a03ada9988f2bb493a22a75eef3a185884533e5cdbcd498ea835b08f
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    libgeos-c1t64 libproj25 libxml2 libjson-c5 libprotobuf-c1 \
    && rm -rf /var/lib/apt/lists/* \
    && find /usr -xdev -type f -perm /6000 -exec chmod a-s '{}' +
COPY --from=spatial-build /opt/postgis/ /
COPY --from=spatial-build /opt/verified-gosu /usr/local/bin/gosu
COPY initdb-postgis.sh /docker-entrypoint-initdb.d/10_postgis.sh
LABEL org.opencontainers.image.description="PostgreSQL 17 / PostGIS 3.6.4 with upstream FlatGeobuf validation backport; raster and SFCGAL excluded"
