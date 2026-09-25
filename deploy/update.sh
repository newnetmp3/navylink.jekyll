#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/navylink"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run navylink-update as root (or with sudo)." >&2
  exit 1
fi
if [[ $# -gt 1 ]]; then
  echo "Usage: navylink-update [40-character main-branch commit SHA]" >&2
  exit 2
fi

# Prevent a manual update and an Actions deploy from mutating the checkout together.
exec 9>/run/lock/navylink-update.lock
flock -w 300 9 || { echo "Timed out waiting for another Navylink deployment." >&2; exit 1; }

cd "$APP_DIR"
git fetch --all --prune

DEPLOY_REF="origin/main"
if [[ $# -eq 1 ]]; then
  DEPLOY_REF="$1"
  if [[ ! "$DEPLOY_REF" =~ ^[0-9a-f]{40}$ ]]; then
    echo "Expected a full lowercase 40-character commit SHA." >&2
    exit 2
  fi
  if [[ "$(git rev-parse origin/main)" != "$DEPLOY_REF" ]]; then
    echo "Refusing to deploy stale/unreviewed commit; origin/main differs from $DEPLOY_REF" >&2
    exit 1
  fi
fi

git reset --hard "$DEPLOY_REF"
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
install -m 0755 "$APP_DIR/deploy/github-deploy-ssh.sh" /usr/local/sbin/navylink-github-deploy

systemctl restart navylink
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy

echo "Waiting for Navylink API..."
for attempt in {1..20}; do
  if curl -fsS http://127.0.0.1:8000/api/health; then
    echo
    echo "Navylink update complete. Deployed commit: $(git rev-parse HEAD)"
    exit 0
  fi
  sleep 1
done

echo "Navylink API did not become healthy within 20 seconds." >&2
systemctl --no-pager --full status navylink.service >&2 || true
journalctl -u navylink.service -n 40 --no-pager >&2 || true
exit 1
