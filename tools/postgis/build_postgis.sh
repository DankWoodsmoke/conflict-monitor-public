#!/bin/sh
set -eu
mkdir -p /build /opt/postgis
cd /build
curl --fail --location --proto '=https' --proto-redir '=https' --tlsv1.2 --retry 3 --connect-timeout 15 --max-time 180 --max-filesize 25000000 \
  https://download.osgeo.org/postgis/source/postgis-3.6.4.tar.gz -o postgis.tar.gz
echo 'ed8dc6679f1e06f7b113592b04cde2a7e00f1b1e681294c8ca2204058990cec6  postgis.tar.gz' | sha256sum -c -
curl --fail --location --proto '=https' --proto-redir '=https' --tlsv1.2 --retry 3 --connect-timeout 15 --max-time 60 --max-filesize 1000000 \
  https://gitea.osgeo.org/postgis/postgis/commit/767fa40644253281f6d4e8b06811489b0a0f9b0d.patch -o flatgeobuf.patch
echo 'dc31d8b92d00cfe3fdae75ea4f0bcc6e1e6132be655d0e4f391221be60792b3d  flatgeobuf.patch' | sha256sum -c -
tar -xzf postgis.tar.gz
cd postgis-3.6.4
# The upstream patch includes a NEWS entry against its development branch.
# Apply every source and regression change; retain the release NEWS unchanged.
# Two numeric-value contexts differ in the released 3.6.4 source. The reviewed
# adaptation preserves its uint32 and float-widening behavior; security changes
# and regression cases otherwise match the pinned upstream patch.
echo '7dc9dec77d21562088a1574a27f9f91d8604a4c4d6055e6d63bc0be226b75632  /flatgeobuf-3.6.4.patch' | sha256sum -c -
git apply --check --recount --exclude=NEWS /flatgeobuf-3.6.4.patch
git apply --recount --exclude=NEWS /flatgeobuf-3.6.4.patch
./configure --with-pgconfig=/usr/lib/postgresql/17/bin/pg_config --without-raster --without-address-standardizer
make -j2
make install DESTDIR=/opt/postgis
mkdir -p /opt/postgis/usr/local/share/postgis-build
cp ../flatgeobuf.patch /opt/postgis/usr/local/share/postgis-build/
cp /flatgeobuf-3.6.4.patch /opt/postgis/usr/local/share/postgis-build/
cp regress/core/flatgeobuf.sql regress/core/flatgeobuf_expected /opt/postgis/usr/local/share/postgis-build/
printf '%s\n' 'PostGIS 3.6.4; upstream FlatGeobuf backport SHA256 dc31d8b92d00cfe3fdae75ea4f0bcc6e1e6132be655d0e4f391221be60792b3d; applied reviewed 3.6.4 adaptation SHA256 7dc9dec77d21562088a1574a27f9f91d8604a4c4d6055e6d63bc0be226b75632; no raster/address_standardizer/SFCGAL' > /opt/postgis/usr/local/share/postgis-build/provenance.txt
cd /build
arch="$(dpkg --print-architecture)"
curl --fail --location --proto '=https' --proto-redir '=https' --tlsv1.2 --retry 3 --connect-timeout 15 --max-time 120 --max-filesize 10000000 "https://github.com/tianon/gosu/releases/download/1.20/gosu-$arch" -o gosu
curl --fail --location --proto '=https' --proto-redir '=https' --tlsv1.2 --retry 3 --connect-timeout 15 --max-time 60 --max-filesize 20000 "https://github.com/tianon/gosu/releases/download/1.20/gosu-$arch.asc" -o gosu.asc
GNUPGHOME="$(mktemp -d)"; export GNUPGHOME
gpg --batch --keyserver hkps://keys.openpgp.org --recv-keys B42F6819007F00F88E364FD4036A9C25BF357DD4
gpg --batch --verify gosu.asc gosu
gpgconf --kill all
chmod 0755 gosu
./gosu --version
./gosu nobody true
cp gosu /opt/verified-gosu
