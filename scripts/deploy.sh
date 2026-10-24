#!/usr/bin/env bash
# Test, build and deploy Cadence to the DigitalOcean server in one command.
#   scripts/deploy.sh [--fast] [root@<ip>]
# --fast skips the test suites. The server comes from the argument, $CADENCE_DEPLOY_HOST, or the first line of
# .deploy-host in the repo root (git-ignored). Details: docs/deploy-digitalocean.md
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

FAST=0
if [[ "${1:-}" == "--fast" ]]; then FAST=1; shift; fi
HOST="${1:-${CADENCE_DEPLOY_HOST:-}}"
if [[ -z "$HOST" && -f "$ROOT/.deploy-host" ]]; then HOST="$(head -n1 "$ROOT/.deploy-host")"; fi
[[ -n "$HOST" ]] || { echo "No server set. Pass root@<ip>, set CADENCE_DEPLOY_HOST, or put it in $ROOT/.deploy-host" >&2; exit 2; }

cd "$ROOT"
if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
  echo "Note: deploying your working tree, which has uncommitted changes."
fi

if [[ $FAST -eq 0 ]]; then
  echo "== Backend tests"
  (cd app/backend && .venv/bin/pytest -q)
  echo "== Web typecheck and tests"
  npm --prefix app/web run typecheck >/dev/null
  npm --prefix app/web test >/dev/null
fi

echo "== Build and deploy to $HOST"
deploy/push.sh "$HOST"

echo "== Server status"
ssh "$HOST" 'free -m | sed -n 2p | awk "{print \"memory: \"\$3\" of \"\$2\" MB used\"}"; df -h /var/lib/cadence | tail -1 | awk "{print \"disk: \"\$3\" used, \"\$4\" free\"}"; systemctl list-timers cadence-backup.timer --no-pager | sed -n 2p | cut -c1-60'
echo "Deployed. Open the phone address (docs/deploy-digitalocean.md) or tunnel: ssh -L 8765:127.0.0.1:8765 $HOST"
