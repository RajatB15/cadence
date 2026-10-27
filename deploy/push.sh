#!/usr/bin/env bash
# Deploy the current code to the server from your Mac. Usage: deploy/push.sh root@<droplet-ip>
# Builds the web app here (the server needs no Node), copies code + build, installs, restarts.
set -euo pipefail
HOST="${1:?usage: deploy/push.sh root@<droplet-ip>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/deploy/ssh-share.sh"

npm --prefix "$ROOT/app/web" run build >/dev/null
RS=(rsync -az --delete --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' --exclude '*.egg-info' --exclude tests)
"${RS[@]}" "$ROOT/app/backend/" "$HOST:/opt/cadence/app/backend/"
"${RS[@]}" "$ROOT/app/web/dist/" "$HOST:/opt/cadence/app/web/dist/"
"${RS[@]}" "$ROOT/deploy/" "$HOST:/opt/cadence/deploy/"
# The food library: only the built catalogue (not the raw crawl) from the private food-data submodule, when it exists.
if [[ -f "$ROOT/food-data/library/catalogue.json" ]]; then
  ssh "$HOST" 'mkdir -p /opt/cadence/food-data/library'
  rsync -az "$ROOT/food-data/library/catalogue.json" "$HOST:/opt/cadence/food-data/library/"
fi
# The reading cards from the private reading-data folder, when it exists (the app hides reading without them).
if [[ -d "$ROOT/reading-data/cards" ]]; then
  ssh "$HOST" 'mkdir -p /opt/cadence/reading-data'
  rsync -az --delete "$ROOT/reading-data/cards/" "$HOST:/opt/cadence/reading-data/cards/"
fi

ssh "$HOST" 'bash -s' <<'REMOTE'
set -euo pipefail
cd /opt/cadence/app/backend
[[ -d .venv ]] || python3 -m venv .venv
# Editable on purpose: the app locates its web build relative to the source tree.
.venv/bin/pip install -q -e '.[garmin-push]'
chown -R cadence:cadence /opt/cadence
chmod +x /opt/cadence/deploy/*.sh
[[ -f /etc/cadence/cadence.env ]] || install -m 640 -o root -g cadence /opt/cadence/deploy/cadence.env /etc/cadence/cadence.env
cp /opt/cadence/deploy/cadence.service /opt/cadence/deploy/cadence-backup.service /opt/cadence/deploy/cadence-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now cadence >/dev/null
systemctl restart cadence
# A 1 vCPU server needs ~15 s to start; wait for the API rather than guessing.
for _ in $(seq 1 30); do
  curl -sf http://127.0.0.1:8765/api/health >/dev/null && { echo "Cadence is up: $(systemctl is-active cadence)"; exit 0; }
  sleep 2
done
echo "Cadence did not become healthy within 60 s. Check: journalctl -u cadence -n 50 --no-pager" >&2
exit 1
REMOTE
echo "Deployed."
