# Repackage only; do not rebuild/strip/rename the official Go executable.
# Qualification proves CGO_ENABLED=0, no ELF interpreter/dynamic segment, and
# exact binary + CA hashes. See cloudflared-provenance.json and PUBLIC_HOSTING.md.
FROM cloudflare/cloudflared:2026.10.7@sha256:4955524aeaa379e154023d5a027c250f7b35041a2e7e950cf13f144bc9b9c5ba AS upstream

FROM scratch
COPY --from=upstream /usr/local/bin/cloudflared /usr/local/bin/cloudflared
COPY --from=upstream /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=upstream /etc/passwd /etc/passwd
COPY --from=upstream /etc/group /etc/group
COPY --from=upstream /usr/share/doc/ca-certificates/copyright /usr/share/doc/ca-certificates/copyright
# Original trust-store package provenance, not a claim to install its removed
# utility scripts or the rest of the Debian runtime.
COPY --from=upstream /var/lib/dpkg/status.d/ca-certificates /opt/provenance/ca-certificates.package-metadata
COPY THIRD_PARTY_LICENSES.txt /opt/licenses/cloudflared-THIRD_PARTY_LICENSES.txt
COPY cloudflared-provenance.json /opt/provenance/cloudflared.json
LABEL org.opencontainers.image.source="https://github.com/cloudflare/cloudflared" \
      org.opencontainers.image.version="2026.10.7-conflict-monitor-static.1" \
      org.opencontainers.image.licenses="Apache-2.0" \
      io.conflict-monitor.upstream.digest="sha256:4955524aeaa379e154023d5a027c250f7b35041a2e7e950cf13f144bc9b9c5ba" \
      io.conflict-monitor.binary.sha256="c4f903368f20f303507296081cca401e765c37764698747e96988724ab1c16ed"
USER 65532:65532
ENV NO_AUTOUPDATE=true SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENTRYPOINT ["/usr/local/bin/cloudflared"]
CMD ["version"]
