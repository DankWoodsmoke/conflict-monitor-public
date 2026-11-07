#!/bin/sh
set -eu
cd /home/builder/sqlite
curl --fail --location --proto '=https' --proto-redir '=https' --tlsv1.2 --retry 2 --connect-timeout 15 --max-time 120 --max-filesize 5000000 https://sqlite.org/2026/sqlite-autoconf-3540100.tar.gz -o sqlite-autoconf-3540100.tar.gz
printf '%s\n' '926ef8d3eab93fbf6e06011901273eec076b25594a4e1cdadd50c987f4f6d64e  sqlite-autoconf-3540100.tar.gz' | sha256sum -c -
chown builder:builder sqlite-autoconf-3540100.tar.gz
su builder -c 'abuild-keygen -a -n'
cp /home/builder/.abuild/*.rsa.pub /etc/apk/keys/
su builder -c 'abuild -r'
rm /home/builder/.abuild/*.rsa
mkdir /out
native_arch="$(apk --print-arch)"
cp "/home/builder/packages/builder/$native_arch/sqlite-libs-3.54.1-r0.apk" /out/
cp /home/builder/.abuild/*.rsa.pub /out/
cp APKBUILD sqlite-smoke-output.txt session-probe-output.txt /out/
sha256sum /out/* > /out/SHA256SUMS
