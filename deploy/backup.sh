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
# JSON string or null; escapes backslashes, quotes and control characters so an odd error text can't corrupt backup-status.json.
json() {
  if [[ -z "$1" ]]; then printf null; return; fi
  local v="${1//\\/\\\\}"
  v="${v//\"/\\\"}"
  v="${v//$'\n'/\\n}"; v="${v//$'\r'/\\r}"; v="${v//$'\t'/\\t}"
  printf '"%s"' "$v"
}
write_status() {  # success_at snapshot error
  printf '{"last_success_at": %s, "snapshot": %s, "last_attempt_at": "%s", "last_error": %s}\n' \
    "$(json "$1")" "$(json "$2")" "$(date -u +%Y-%m-%dT%H:%M:%S)" "$(json "$3")" > "$STATUS.tmp" && mv "$STATUS.tmp" "$STATUS"
}
trap 'write_status "$prev_success" "$prev_snap" "Backup failed - see: journalctl -u cadence-backup"' ERR

# Refuse to upload anything unless the remote is an rclone crypt remote: a plain Drive remote would store health data unencrypted.
remote_name="${REMOTE%%:*}"
# Capture first: with `set -o pipefail`, `grep -q` closing the pipe early can SIGPIPE rclone and make a valid crypt remote look invalid.
cfg=$(rclone config show "$remote_name" 2>/dev/null) || true
if [[ "$REMOTE" != *:* ]] || ! grep -Eq '^type *= *crypt *$' <<<"$cfg"; then
  echo "CADENCE_BACKUP_REMOTE ($REMOTE) is not an rclone crypt remote; refusing to upload." >&2
  write_status "$prev_success" "$prev_snap" "Backup refused: remote is not an rclone crypt remote"
  trap - ERR
  exit 1
fi

# SQLite's online backup is consistent even while the service is writing.
sqlite3 "$DATA/cadence.sqlite3" ".backup '$work/cadence.sqlite3'"
rclone copy "$work" "${REMOTE}db/$stamp"

# Archived Garmin responses are write-once, so only new files are uploaded (never deletes remote copies).
# Retention note: the archive is never pruned (db snapshots are, see KEEP). It only grows; prune old remote files by hand if Drive space matters.
[[ -d "$DATA/archive" ]] && rclone copy "$DATA/archive" "${REMOTE}archive"

# Keep the newest $KEEP database snapshots.
rclone lsf --dirs-only "${REMOTE}db" | sed 's#/$##' | sort | head -n "-$KEEP" | while read -r old; do
  [[ -n "$old" ]] && rclone purge "${REMOTE}db/$old"
done
write_status "$(date -u +%Y-%m-%dT%H:%M:%S)" "$stamp" ""
echo "Backup $stamp done."
