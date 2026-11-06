#!/bin/sh
set -eu
cd /home/builder/zlib
url=https://github.com/madler/zlib/releases/download/v1.4/zlib-1.4.tar.gz
curl --fail --location --proto '=https' --proto-redir '=https' --tlsv1.2 --retry 2 --connect-timeout 15 --max-time 120 --max-filesize 3000000 "$url" -o zlib-1.4.tar.gz
printf '%s\n' '02dd159783677a749c04adbdd02b55b8a2bcc7e054f51b76b549199a916ad584  zlib-1.4.tar.gz' | sha256sum -c -
chown builder:builder zlib-1.4.tar.gz
su builder -c 'abuild-keygen -a -n'
cp /home/builder/.abuild/*.rsa.pub /etc/apk/keys/
su builder -c 'abuild -r'
rm /home/builder/.abuild/*.rsa
mkdir /out
native_arch="$(apk --print-arch)"
cp "/home/builder/packages/builder/$native_arch/zlib-1.4-r0.apk" /out/
cp /home/builder/.abuild/*.rsa.pub /out/
cp APKBUILD window_reset_probe.c upstream-tests.txt window-reset-old.txt window-reset-fixed.txt abi-old.txt abi-new.txt abi-missing.txt versions-old.txt versions-new.txt soname.txt /out/
printf 'source_url=%s\nsource_sha256=%s\nlocal_package=zlib-1.4-r0\nlocal_signature=build-generated-key-not-Alpine-distributor\n' "$url" 02dd159783677a749c04adbdd02b55b8a2bcc7e054f51b76b549199a916ad584 > /out/SOURCE.txt
sha256sum /out/* > /out/SHA256SUMS
