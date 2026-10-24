#!/usr/bin/env bash
# Nightly encrypted backup of the Cadence database and Garmin archive to Google Drive (via rclone crypt).
# Not backed up on purpose: the Garmin key (/etc/cadence/garmin.env) and the push-notification key.
# Setup: docs/deploy-digitalocean.md. Env: CADENCE_BACKUP_REMOTE (default "cadence-crypt:"), CADENCE_BACKUP_KEEP (default 14).
set -euo pipefail
DATA="${CADENCE_DATA_DIR:-/var/lib/cadence/data}"
REMOTE="${CADENCE_BACKUP_REMOTE:-cadence-crypt:}"
KEEP="${CADENCE_BACKUP_KEEP:-14}"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
stamp="$(date +%Y%m%d-%H%M)"

# Tell the Settings page how the last run went (naive UTC times, like the rest of Cadence).
STATUS="$DATA/backup-status.json"
prev_success="" prev_snap=""
if [[ -f "$STATUS" ]]; then
  prev_success="$(sed -n 's/.*"last_success_at": *"\([^"]*\)".*/\1/p' "$STATUS" | head -1)"
  prev_snap="$(sed -n 's/.*"snapshot": *"\([^"]*\)".*/\1/p' "$STATUS" | head -1)"
fi
json() { if [[ -n "$1" ]]; then printf '"%s"' "$1"; else printf null; fi; }
write_status() {  # success_at snapshot error
  printf '{"last_success_at": %s, "snapshot": %s, "last_attempt_at": "%s", "last_error": %s}\n' \
    "$(json "$1")" "$(json "$2")" "$(date -u +%Y-%m-%dT%H:%M:%S)" "$(json "$3")" > "$STATUS.tmp" && mv "$STATUS.tmp" "$STATUS"
}
trap 'write_status "$prev_success" "$prev_snap" "Backup failed - see: journalctl -u cadence-backup"' ERR

# SQLite's online backup is consistent even while the service is writing.
sqlite3 "$DATA/cadence.sqlite3" ".backup '$work/cadence.sqlite3'"
rclone copy "$work" "${REMOTE}db/$stamp"

# Archived Garmin responses are write-once, so only new files are uploaded (never deletes remote copies).
[[ -d "$DATA/archive" ]] && rclone copy "$DATA/archive" "${REMOTE}archive"

# Keep the newest $KEEP database snapshots.
rclone lsf --dirs-only "${REMOTE}db" | sed 's#/$##' | sort | head -n "-$KEEP" | while read -r old; do
  [[ -n "$old" ]] && rclone purge "${REMOTE}db/$old"
done
write_status "$(date -u +%Y-%m-%dT%H:%M:%S)" "$stamp" ""
echo "Backup $stamp done."
