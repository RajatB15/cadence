#!/usr/bin/env bash
# Records the Cadence demo tour and encodes it for the README and for social posts.
#   tools/demo-media/build.sh
# Outputs (override with the env vars below):
#   $MEDIA_DIR   (default docs/media)  tour-desktop.webp, tour-phone.webp      - used by the README
#   $SOCIAL_DIR  (default marketing/)  GIFs and MP4s for posts (git-ignored)
# Everything runs on a throwaway server with synthetic demo data in a temp folder: your real data is never touched.
# Needs: macOS, Google Chrome, Node 20+, ImageMagick (magick), webp tools (img2webp), Xcode command line tools (swiftc),
# and the repo's backend venv. Takes about 6 minutes.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
MEDIA_DIR="${MEDIA_DIR:-$ROOT/docs/media}"
SOCIAL_DIR="${SOCIAL_DIR:-$ROOT/marketing}"
PORT="${DEMO_PORT:-8790}"
SHARE_PORT="${DEMO_SHARE_PORT:-8791}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1 ($2)" >&2; exit 1; }; }
need node "install Node 20+"
need magick "brew install imagemagick"
need img2webp "brew install webp"
need swiftc "xcode-select --install"
[[ -d "/Applications/Google Chrome.app" ]] || { echo "Missing: Google Chrome" >&2; exit 1; }
[[ -x "$ROOT/app/backend/.venv/bin/cadence-app" ]] || { echo "Missing backend venv: cd app/backend && python3 -m venv .venv && .venv/bin/pip install -e '.[test]'" >&2; exit 1; }
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then echo "Port $PORT is in use; set DEMO_PORT to another port." >&2; exit 1; fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/cadence-media.XXXXXX")"
SERVER_PID=""
cleanup() {
  [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true
  [[ "$WORK" == */cadence-media.* && -d "$WORK" ]] && rm -rf "$WORK"
}
trap cleanup EXIT

echo "== Web build and demo server"
npm --prefix "$ROOT/app/web" run build >/dev/null
[[ -d "$HERE/node_modules/playwright-core" ]] || (cd "$HERE" && npm ci --silent)
mkdir -p "$WORK/data" && : > "$WORK/secrets.env"
(
  cd "$ROOT/app/backend"
  CADENCE_PORT="$PORT" CADENCE_SHARE_PORT="$SHARE_PORT" CADENCE_DATA_DIR="$WORK/data" CADENCE_SECRETS_FILE="$WORK/secrets.env" \
    CADENCE_SCHEDULER=0 CADENCE_WEATHER=0 exec .venv/bin/cadence-app
) >"$WORK/server.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 60); do curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null && break; sleep 1; done
curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null || { echo "Demo server did not start; see $WORK/server.log" >&2; exit 1; }

BASE="http://127.0.0.1:$PORT"
post() { curl -sf -X "$1" -H "X-Cadence-Request: 1" -H "Content-Type: application/json" -d "${3:-{\}}" "$BASE$2" >/dev/null; }
post POST /api/sync/demo
post PUT /api/settings/profile '{"height_cm":178,"birth_date":"1990-01-01","sex":"male"}'
post PUT /api/settings/weight-goal '{"goal_kg":76}'

echo "== Recording"
export CADENCE_URL="$BASE"
node "$HERE/record-tour.mjs" "$WORK/desktop" desktop
node "$HERE/record-tour.mjs" "$WORK/phone" phone
kill "$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null || true; SERVER_PID=""

mkdir -p "$MEDIA_DIR" "$SOCIAL_DIR"

echo "== README animations (animated WebP)"
resize_all() {  # in-dir out-dir width [keep-pattern: awk condition on line number NR]
  mkdir -p "$2"
  ls "$1"/f*.png | awk "${4:-1}" | while read -r f; do magick "$f" -resize "$3" "$2/$(basename "$f")"; done
}
resize_all "$WORK/desktop" "$WORK/d1000" 1000x
img2webp -loop 0 -d 50 -lossy -q 80 -m 6 "$WORK"/d1000/f*.png -o "$MEDIA_DIR/tour-desktop.webp" >/dev/null
resize_all "$WORK/phone" "$WORK/p340" 340x
img2webp -loop 0 -d 50 -lossy -q 80 -m 6 "$WORK"/p340/f*.png -o "$MEDIA_DIR/tour-phone.webp" >/dev/null

echo "== Social GIFs (one shared 256-color palette, no dithering, no tolerance: keeps dark gradients clean)"
# Dropping every third frame keeps the file size sane; fuzz/dither options are deliberately not used (they cause grain).
gif() {  # frames-dir work-dir width palette-sample-step out
  resize_all "$1" "$2" "$3" 'NR%3!=0'
  magick $(ls "$2"/f*.png | awk "NR%$4==1") +append -colors 256 -unique-colors "$2/palette.png"
  magick -delay 12 -loop 0 "$2"/f*.png +dither -remap "$2/palette.png" -layers OptimizeFrame "$5"
}
gif "$WORK/desktop" "$WORK/g-desktop" 720x 12 "$SOCIAL_DIR/cadence-tour-desktop.gif"
gif "$WORK/phone" "$WORK/g-phone" 330x 8 "$SOCIAL_DIR/cadence-tour-phone.gif"

echo "== Social MP4s (H.264 via Apple's video framework)"
swiftc -O "$HERE/frames2mp4.swift" -o "$WORK/frames2mp4" 2>&1 | grep -v warning || true
"$WORK/frames2mp4" "$WORK/desktop" "$SOCIAL_DIR/cadence-tour-desktop.mp4" 12 1800000
"$WORK/frames2mp4" "$WORK/phone" "$SOCIAL_DIR/cadence-tour-phone.mp4" 12 1500000

echo "== Done"
ls -la "$MEDIA_DIR"/tour-*.webp "$SOCIAL_DIR"/cadence-tour-* | awk '{printf "%6.1f MB  %s\n", $5/1048576, $9}'
