#!/usr/bin/env bash
set -euo pipefail

REPO="https://github.com/newnetmp3/navylink.jekyll.git"
APP_DIR="/opt/navylink"
DATA_DIR="/var/lib/navylink"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gnupg git ufw python3 python3-venv python3-pip ruby-full build-essential zlib1g-dev

install -d -m 0755 /usr/share/keyrings
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
apt-get update
apt-get install -y caddy

if ! id navylink >/dev/null 2>&1; then
  useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin navylink
fi
install -d -o navylink -g navylink -m 0750 "$DATA_DIR"

if [[ -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" fetch --all --prune
  git -C "$APP_DIR" reset --hard origin/main
else
  rm -rf "$APP_DIR"
  git clone "$REPO" "$APP_DIR"
fi

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/server/requirements.txt"

cd "$APP_DIR"
gem install bundler --no-document
bundle install
bundle exec jekyll build

install -m 0644 "$APP_DIR/deploy/navylink.service" /etc/systemd/system/navylink.service
install -m 0644 "$APP_DIR/deploy/Caddyfile.ip" /etc/caddy/Caddyfile

systemctl daemon-reload
systemctl enable --now navylink.service
caddy validate --config /etc/caddy/Caddyfile
systemctl enable --now caddy
systemctl restart caddy

ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

cat >/usr/local/sbin/navylink-update <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd /opt/navylink
git fetch --all --prune
git reset --hard origin/main
./.venv/bin/pip install -r server/requirements.txt
bundle install
bundle exec jekyll build
systemctl restart navylink
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
curl -fsS http://127.0.0.1:8000/api/health && echo
EOF
chmod 0755 /usr/local/sbin/navylink-update

cat >/usr/local/sbin/navylink-domain <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
DOMAIN="${1:-}"
if [[ -z "$DOMAIN" ]]; then echo "Usage: navylink-domain navylink.net" >&2; exit 1; fi
cat >/etc/caddy/Caddyfile <<CADDY
${DOMAIN}, www.${DOMAIN} {
    encode zstd gzip
    @api path /api/*
    reverse_proxy @api 127.0.0.1:8000
    root * /opt/navylink/_site
    try_files {path} {path}/ /index.html
    file_server
    header {
        X-Content-Type-Options nosniff
        Referrer-Policy strict-origin-when-cross-origin
        X-Frame-Options SAMEORIGIN
        Permissions-Policy "geolocation=(), microphone=(), camera=()"
    }
}
CADDY
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
EOF
chmod 0755 /usr/local/sbin/navylink-domain

echo
echo "Navylink installed."
echo "Test: http://172.245.6.106"
echo "API:  http://172.245.6.106/api/health"
echo "After DNS points here, run: navylink-domain navylink.net"
systemctl --no-pager --full status navylink.service | sed -n '1,12p'
