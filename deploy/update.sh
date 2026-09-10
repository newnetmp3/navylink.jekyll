#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/navylink"
cd "$APP_DIR"

git fetch --all --prune
git reset --hard origin/main
./.venv/bin/pip install -r server/requirements.txt

PREV_MNP=""
PREV_META=""
if [[ -f _data/mnp_quick_links.generated.yml ]]; then
  PREV_MNP="$(mktemp)"
  cp _data/mnp_quick_links.generated.yml "$PREV_MNP"
fi
if [[ -f _data/mnp_quick_links.meta.yml ]]; then
  PREV_META="$(mktemp)"
  cp _data/mnp_quick_links.meta.yml "$PREV_META"
fi

echo "Syncing MyNavy Portal Quick Links..."
if ./.venv/bin/python tools/sync_mnp_quicklinks.py; then
  echo "MyNavy Portal Quick Links sync complete."
else
  echo "WARNING: MyNavy Portal sync failed; preserving the last known-good generated catalog." >&2
  if [[ -n "$PREV_MNP" && -f "$PREV_MNP" ]]; then cp "$PREV_MNP" _data/mnp_quick_links.generated.yml; fi
  if [[ -n "$PREV_META" && -f "$PREV_META" ]]; then cp "$PREV_META" _data/mnp_quick_links.meta.yml; fi
fi
[[ -z "$PREV_MNP" ]] || rm -f "$PREV_MNP"
[[ -z "$PREV_META" ]] || rm -f "$PREV_META"

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
