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

# SQLite's online backup is consistent even while the service is writing.
sqlite3 "$DATA/cadence.sqlite3" ".backup '$work/cadence.sqlite3'"
rclone copy "$work" "${REMOTE}db/$stamp"

# Archived Garmin responses are write-once, so only new files are uploaded (never deletes remote copies).
[[ -d "$DATA/archive" ]] && rclone copy "$DATA/archive" "${REMOTE}archive"

# Keep the newest $KEEP database snapshots.
rclone lsf --dirs-only "${REMOTE}db" | sed 's#/$##' | sort | head -n "-$KEEP" | while read -r old; do
  [[ -n "$old" ]] && rclone purge "${REMOTE}db/$old"
done
echo "Backup $stamp done."
