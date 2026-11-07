FROM node:24-alpine@sha256:8a32c8cf649a49915a66e81e7a609223c708d0adabf288ee3f4077d765542f85 AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY tools/patch-cesium.mjs ./tools/patch-cesium.mjs
RUN npm ci --ignore-scripts && node tools/patch-cesium.mjs
COPY . .
RUN npm run build

# Same pinned Alpine builder and byte-identical source recipe as tools/postgis/zlib.
# The APK signature is local provenance, not an Alpine distributor endorsement.
FROM postgres:17.11-alpine3.24@sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b AS zlib-build
RUN apk add --no-cache abuild build-base curl ca-certificates \
    && adduser -D builder && addgroup builder abuild
COPY --chown=builder:builder container/zlib/ /home/builder/zlib/
WORKDIR /home/builder/zlib
RUN sh build_zlib.sh

FROM nginx:alpine@sha256:785835ea65db4bba6f021acc0f3be91b0fef76a53fe41f8588c6698d2aed0606
# Pinned distributor security fixes not yet present in the base image.
RUN apk add --no-cache --upgrade brotli-libs=1.2.1-r0 curl=8.23.0-r0 libcurl=8.23.0-r0 libexpat=2.10.0-r0
COPY --from=zlib-build /out/ /usr/local/share/zlib-build/
RUN cp /usr/local/share/zlib-build/*.rsa.pub /etc/apk/keys/ \
    && apk verify /usr/local/share/zlib-build/zlib-1.4-r0.apk \
    && apk add --no-cache /usr/local/share/zlib-build/zlib-1.4-r0.apk \
    && apk info -e zlib=1.4-r0 \
    && test ! -e /usr/lib/libz.so.1.3.2 \
    && sha256sum /usr/lib/libz.so.1.4 > /usr/local/share/zlib-build/installed-library.sha256 \
    && ldd /usr/sbin/nginx > /usr/local/share/zlib-build/nginx-library-binding.txt
# The default remains the private/operator profile. Public builds opt in explicitly.
ARG NGINX_CONFIG=nginx.conf
COPY ${NGINX_CONFIG} /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
