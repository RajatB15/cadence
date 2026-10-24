#!/usr/bin/env bash
# One command from your Mac: server setup (idempotent), then build + push + restart.
# Usage: deploy/full-deploy.sh [root@<droplet-ip>]   (defaults to the host in .deploy-host)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${1:-}"
[[ -n "$HOST" || ! -f "$ROOT/.deploy-host" ]] || HOST="$(tr -d '[:space:]' < "$ROOT/.deploy-host")"
[[ -n "$HOST" ]] || { echo "usage: deploy/full-deploy.sh root@<droplet-ip> (or put it in .deploy-host)" >&2; exit 1; }

echo "==> Server setup on $HOST"
ssh "$HOST" 'bash -s' < "$ROOT/deploy/setup-server.sh"
echo "==> Deploying code"
"$ROOT/deploy/push.sh" "$HOST"
echo "==> Checking"
ssh "$HOST" 'tesseract --version 2>&1 | head -1; systemctl is-active cadence'
