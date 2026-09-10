#!/usr/bin/env bash
set -euo pipefail
DOMAIN="${1:-}"
if [[ -z "$DOMAIN" ]]; then
  echo "Usage: navylink-domain navylink.net" >&2
  exit 1
fi

cat >/etc/caddy/Caddyfile <<CADDY
${DOMAIN}, www.${DOMAIN} {
    encode zstd gzip

    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }

    handle {
        root * /opt/navylink/_site
        try_files {path} {path}/ /index.html
        file_server
    }

    header {
        X-Content-Type-Options nosniff
        Referrer-Policy strict-origin-when-cross-origin
        X-Frame-Options SAMEORIGIN
        Permissions-Policy "geolocation=(), microphone=(), camera=()"
    }
}
CADDY

caddy fmt --overwrite /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
