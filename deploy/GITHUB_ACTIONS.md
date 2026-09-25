# Automatic deployment to Navylink.net

Navylink currently uses **Jekyll + a FastAPI server + Caddy on the RackNerd VPS**.
It is not the original Cloudflare Worker starter. This workflow deploys
`newnetmp3/navylink.jekyll` to the existing server at `172.245.6.106`.

`.github/workflows/deploy-vps.yml` runs after **CI succeeds for a push to main**.
You can also use **Actions → Deploy Navylink to VPS → Run workflow**.
The runner builds and checks the exact commit before sending its SHA over SSH.
The server refuses a stale SHA and checks `/api/health` after restarting.
PRs do not deploy; GitHub Pages has a separate workflow.

**One-time setup is required.** A GitHub commit cannot install an SSH key on
your VPS or create repository Actions secrets. Do not send private keys in chat
or commit them to the repository.

## 1. Install the updated deploy scripts on the VPS

From your Arch PC, connect to the VPS and run:

```bash
ssh root@172.245.6.106
navylink-update
command -v navylink-github-deploy
exit
```

The last command should print `/usr/local/sbin/navylink-github-deploy`.
If `navylink-update` isn't installed, on the VPS use
`cd /opt/navylink && git pull --ff-only origin main && bash deploy/update.sh`.

## 2. Generate a dedicated deploy key on your Arch PC

```bash
ssh-keygen -t ed25519 -f ~/.ssh/navylink_actions -C "navylink-github-actions" -N ''
cat ~/.ssh/navylink_actions.pub
```

Copy **only the single public-key line** printed by the second command.

On the VPS, open the root authorized-keys file
(`install -d -m 700 /root/.ssh && nano /root/.ssh/authorized_keys`).
Add **one line**, replacing `ssh-ed25519 AAAA... navylink-github-actions`
with your actual public key:

```text
restrict,command="/usr/local/sbin/navylink-github-deploy" ssh-ed25519 AAAA... navylink-github-actions
```

Keep any existing authorized keys. Run
`chmod 600 /root/.ssh/authorized_keys`. This key can only invoke the
restricted updater for a 40-character commit SHA; it cannot open a shell.

## 3. Pin the VPS host key (do not use StrictHostKeyChecking=no)

On the **VPS**, note the actual server fingerprint:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

On your **Arch PC**, collect its public host key and compare the fingerprint
to the one from the VPS:

```bash
ssh-keyscan -t ed25519 172.245.6.106 > ~/navylink-known-hosts
ssh-keygen -lf ~/navylink-known-hosts
```

If the fingerprints differ, stop: do not add the key to GitHub.

## 4. Set GitHub Actions secrets

On your Arch PC, with `gh` authenticated to your GitHub account:

```bash
gh secret set NAVYLINK_SSH_PRIVATE_KEY -R newnetmp3/navylink.jekyll < ~/.ssh/navylink_actions
gh secret set NAVYLINK_SSH_KNOWN_HOSTS -R newnetmp3/navylink.jekyll < ~/navylink-known-hosts
```

Alternatively use **GitHub repository → Settings → Secrets and variables →
Actions → New repository secret**, with those exact secret names and file
contents. These are secrets, not ordinary repository files.

Defaults are host `172.245.6.106`, SSH user `root`, and port `22`.
If your VPS differs, configure repository **Actions variables**
`NAVYLINK_SSH_HOST`, `NAVYLINK_SSH_USER`, and `NAVYLINK_SSH_PORT`.
The forced-command installation above is written for the root SSH user.

## Updating the official MyNavy Portal Quick Links catalog

The historical `my.navy.mil/quick-links.html` destination now redirects/migrates
to the public `www.mn3p.navy.mil` portal. The importer reads the official
public Quick Link **search results** (not the JavaScript-only placeholder cards
on the landing page). A past run from GitHub Actions received HTTP 403 from
the Navy site. That is a server-side restriction, **not** missing Python
dependencies. Do not disable TLS validation or try to bypass a CAC login.

The **Sync MyNavy Portal Quick Links** action attempts the public endpoint
directly at **07:17 UTC daily** and has an Actions → Run workflow button.
If the Navy refuses GitHub's IP, it uses the same restricted SSH key described
above to request `sync-mnp` from the VPS. If the VPS is also blocked, the run
fails without replacing the previous snapshot. No login cookies or CAC
credentials are collected or stored.

Before the first automatic sync, run `navylink-update` on the VPS so its
restricted SSH command recognizes `sync-mnp`; complete the GitHub SSH secrets
setup above. You can test network access from the VPS without modifying files:

```bash
cd /opt/navylink
.venv/bin/python tools/sync_mnp_quicklinks.py --audit --min-records 350
```

A successful import commits `_data/mnp_quick_links_generated.yml` and its
coverage report on `main`, explicitly dispatches CI (bot-token commits do
not trigger ordinary push events), and the existing VPS deploy workflow runs
after CI succeeds. Existing hand-curated entries in `quick_links.yml` and
`extra_links.yml` are preserved rather than silently overwritten.

If *both* GitHub and VPS cannot reach the official public site, a fallback
for a **trusted browser-exported HTML set** is available:

```bash
python tools/sync_mnp_quicklinks.py --html-dir /path/to/mnp-pages --min-records 350
```

Save each page of the official Quick Link search-results pagination as a
separate `.html` file in the directory. Import refuses an incomplete catalog
and does not treat the empty example cards on the JavaScript landing page as
real destinations. You can review the generated YAML and commit it normally.

## 5. Try it

Navigate to **Actions → Deploy Navylink to VPS → Run workflow** and select
`main`. Once configured, subsequent pushes to `main` deploy on a successful
CI run. The run fails clearly if secrets, SSH access, the site build, or the
VPS health check fail. The Jekyll theme's Sass deprecation warnings are
non-fatal; see the final "Navylink update complete" line on the VPS.

Keep the private key only in your local `~/.ssh/navylink_actions` and the
encrypted GitHub secret. If compromised, remove that line from
`/root/.ssh/authorized_keys`, rotate the key and update the secret.
