#!/usr/bin/env bash
set -euo pipefail

# Force-command entrypoint for the GitHub Actions SSH key.
# Never pass an arbitrary SSH command through to a shell.
if [[ "${SSH_ORIGINAL_COMMAND:-}" =~ ^deploy[[:space:]]([0-9a-f]{40})$ ]]; then
  exec /usr/local/sbin/navylink-update "${BASH_REMATCH[1]}"
fi

echo "Only 'deploy <40-character main-branch commit SHA>' is permitted." >&2
exit 1
