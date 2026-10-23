#!/bin/zsh
# Runs Cadence in the background at login and restarts it if it stops (a macOS LaunchAgent).
# Usage: scripts/cadence-service.sh install | uninstall | restart | status | logs
set -euo pipefail

LABEL="com.cadence.backend"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$ROOT/app/backend/.venv/bin/python"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/Cadence"
DOMAIN="gui/$(id -u)"

install_agent() {
  [[ -x "$PYTHON" ]] || { echo "Backend environment missing: $PYTHON" >&2; exit 1; }
  if [[ ! -f "$ROOT/app/web/dist/index.html" ]]; then
    echo "Building the web app…"
    npm --prefix "$ROOT/app/web" run build >/dev/null
  fi
  if lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1 && ! launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "Port 8765 is already in use. Stop the Cadence backend you started by hand, then run install again." >&2
    exit 1
  fi
  mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>-m</string>
    <string>cadence_app.server</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT/app/backend</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONUNBUFFERED</key><string>1</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$LOG_DIR/backend.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/backend.log</string>
</dict>
</plist>
EOF
  plutil -lint "$PLIST" >/dev/null
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$PLIST"
  echo "Installed. Cadence starts at login: http://127.0.0.1:8765"
  echo "Logs: $LOG_DIR/backend.log"
}

case "${1:-}" in
  install) install_agent ;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Removed. Cadence no longer starts at login."
    ;;
  restart) launchctl kickstart -k "$DOMAIN/$LABEL" && echo "Restarted." ;;
  status)
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
      launchctl print "$DOMAIN/$LABEL" | grep -E "^\s+(state|pid|last exit code) =" || true
    else
      echo "Not installed."
    fi
    ;;
  logs) tail -n 60 -f "$LOG_DIR/backend.log" ;;
  *) echo "Usage: $0 install | uninstall | restart | status | logs" >&2; exit 2 ;;
esac
