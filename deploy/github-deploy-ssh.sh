#!/usr/bin/env bash
set -euo pipefail

# Force-command entrypoint for the GitHub Actions SSH key.
# Never pass an arbitrary SSH command through to a shell.
if [[ "${SSH_ORIGINAL_COMMAND:-}" =~ ^deploy[[:space:]]([0-9a-f]{40})$ ]]; then
  exec /usr/local/sbin/navylink-update "${BASH_REMATCH[1]}"
fi

if [[ "${SSH_ORIGINAL_COMMAND:-}" == "sync-mnp" ]]; then
  # Reuse the same lock as deployment so git reset cannot interrupt this sync.
  exec 9>/run/lock/navylink-update.lock
  flock -w 300 9 || { echo "Timed out waiting for Navylink deployment." >&2; exit 1; }
  cd /opt/navylink
  if [[ ! -x .venv/bin/python ]]; then
    echo "Navylink Python environment is not installed." >&2
    exit 1
  fi
  .venv/bin/python tools/sync_mnp_quicklinks.py --min-records 350 >&2
  # Deliver only the generated data files, never credentials or arbitrary paths.
  .venv/bin/python - <<'PY'
import base64
import json
from pathlib import Path

root = Path("/opt/navylink/_data")
payload = {}
for filename in ("mnp_quick_links_generated.yml", "mnp_quick_links_meta.yml"):
    data = (root / filename).read_bytes()
    if not data or len(data) > 2_000_000:
        raise SystemExit("Refusing empty or oversized MyNavy Portal output")
    payload[filename] = base64.b64encode(data).decode("ascii")
print(json.dumps(payload, separators=(",", ":")))
PY
  exit 0
fi

echo "Only 'deploy <40-character main-branch commit SHA>' and 'sync-mnp' are permitted." >&2
exit 1
