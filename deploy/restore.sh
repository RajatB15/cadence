#!/usr/bin/env bash
# Restore the database (and archive) from Drive. Usage: restore.sh <snapshot>   (see: rclone lsf cadence-crypt:db)
# Stops the service, replaces the database with the snapshot (keeping the old one beside it), restarts.
set -euo pipefail
SNAP="${1:?usage: restore.sh <snapshot>  e.g. 20261024-0330}"
DATA="${CADENCE_DATA_DIR:-/var/lib/cadence/data}"
REMOTE="${CADENCE_BACKUP_REMOTE:-cadence-crypt:}"
OWNER="${CADENCE_OWNER:-cadence}"

[[ "$(id -u)" -eq 0 ]] && systemctl stop cadence 2>/dev/null || true
mkdir -p "$DATA"
if [[ -f "$DATA/cadence.sqlite3" ]]; then
  mv "$DATA/cadence.sqlite3" "$DATA/cadence.sqlite3.before-restore"
  rm -f "$DATA/cadence.sqlite3-wal" "$DATA/cadence.sqlite3-shm"
fi
rclone copy "${REMOTE}db/$SNAP/cadence.sqlite3" "$DATA"
rclone copy "${REMOTE}archive" "$DATA/archive"
[[ "$(id -u)" -eq 0 ]] && chown -R "$OWNER:$OWNER" "$DATA" && systemctl start cadence 2>/dev/null || true
echo "Restored $SNAP."
