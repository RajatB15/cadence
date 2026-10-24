#!/bin/zsh
# Keeps the food library fresh by itself: every 15 minutes it restarts the crawl if it stopped, rebuilds the catalogue
# from everything crawled so far, and makes it live in the running service (a macOS LaunchAgent, no help needed).
# Usage: scripts/food-sync.sh install | uninstall | run | status | logs
set -euo pipefail

LABEL="com.cadence.food-sync"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$ROOT/app/backend/.venv/bin/python"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$ROOT/food-data/healthifyme/sync.log"
DOMAIN="gui/$(id -u)"
EVERY=900

case "${1:-}" in
  install)
    [[ -x "$PYTHON" ]] || { echo "Backend environment missing: $PYTHON" >&2; exit 1; }
    [[ -f "$ROOT/food-data/tools/crawl_healthifyme.py" ]] || { echo "The food-data submodule is missing: git submodule update --init" >&2; exit 1; }
    mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/food-data/healthifyme"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$ROOT/scripts/food_sync.py</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin</string>
    <key>PYTHONUNBUFFERED</key><string>1</string>
  </dict>
  <key>StartInterval</key><integer>$EVERY</integer>
  <key>RunAtLoad</key><true/>
  <key>AbandonProcessGroup</key><true/>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF
    plutil -lint "$PLIST" >/dev/null
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$PLIST"
    echo "Installed. It runs now and then every $((EVERY / 60)) minutes. Log: $LOG"
    ;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Removed. The crawl and catalogue stop updating by themselves."
    ;;
  run) "$PYTHON" "$ROOT/scripts/food_sync.py" ;;
  status)
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
      launchctl print "$DOMAIN/$LABEL" | grep -E "^\s+(state|run interval|runs|last exit code) =" || true
      tail -n 8 "$LOG" 2>/dev/null || true
    else
      echo "Not installed."
    fi
    ;;
  logs) tail -n 60 -f "$LOG" ;;
  *) echo "Usage: $0 install | uninstall | run | status | logs" >&2; exit 2 ;;
esac
