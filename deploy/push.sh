#!/usr/bin/env bash
# Deploy the current code to the server from your Mac. Usage: deploy/push.sh root@<droplet-ip>
# Builds the web app here (the server needs no Node), copies code + build, installs, restarts.
set -euo pipefail
HOST="${1:?usage: deploy/push.sh root@<droplet-ip>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

npm --prefix "$ROOT/app/web" run build >/dev/null
RS=(rsync -az --delete --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' --exclude '*.egg-info' --exclude tests)
"${RS[@]}" "$ROOT/app/backend/" "$HOST:/opt/cadence/app/backend/"
"${RS[@]}" "$ROOT/app/web/dist/" "$HOST:/opt/cadence/app/web/dist/"
"${RS[@]}" "$ROOT/deploy/" "$HOST:/opt/cadence/deploy/"

ssh "$HOST" 'bash -s' <<'REMOTE'
set -euo pipefail
cd /opt/cadence/app/backend
[[ -d .venv ]] || python3 -m venv .venv
# Editable on purpose: the app locates its web build relative to the source tree.
.venv/bin/pip install -q -e .
chown -R cadence:cadence /opt/cadence
chmod +x /opt/cadence/deploy/*.sh
[[ -f /etc/cadence/cadence.env ]] || install -m 640 -o root -g cadence /opt/cadence/deploy/cadence.env /etc/cadence/cadence.env
cp /opt/cadence/deploy/cadence.service /opt/cadence/deploy/cadence-backup.service /opt/cadence/deploy/cadence-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now cadence >/dev/null
systemctl restart cadence
sleep 8
systemctl is-active cadence
REMOTE
echo "Deployed."
