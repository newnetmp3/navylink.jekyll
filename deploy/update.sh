#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/navylink"
cd "$APP_DIR"

git fetch --all --prune
git reset --hard origin/main
./.venv/bin/pip install -r server/requirements.txt

if [[ -f _data/mnp_quick_links_meta.yml ]]; then
  echo "Using committed MyNavy Portal Quick Links snapshot:"
  cat _data/mnp_quick_links_meta.yml
else
  echo "NOTE: no committed MNP Quick Links snapshot is present yet; the GitHub sync workflow will create it." >&2
fi

bundle install
bundle exec jekyll build

install -m 0755 "$APP_DIR/deploy/update.sh" /usr/local/sbin/navylink-update
install -m 0755 "$APP_DIR/deploy/domain.sh" /usr/local/sbin/navylink-domain

systemctl restart navylink
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy

echo "Waiting for Navylink API..."
for attempt in {1..20}; do
  if curl -fsS http://127.0.0.1:8000/api/health; then
    echo
    echo "Navylink update complete."
    exit 0
  fi
  sleep 1
done

echo "Navylink API did not become healthy within 20 seconds." >&2
systemctl --no-pager --full status navylink.service >&2 || true
journalctl -u navylink.service -n 40 --no-pager >&2 || true
exit 1
