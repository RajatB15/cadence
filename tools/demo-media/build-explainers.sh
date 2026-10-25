#!/usr/bin/env bash
# Renders the animated algorithm explainers (explainers/explainers.html) for the README and for social posts.
#   tools/demo-media/build-explainers.sh
# Outputs (override with the env vars below):
#   $MEDIA_DIR   (default docs/media)  algo-<name>.webp                       - used by the README
#   $SOCIAL_DIR  (default marketing/)  algo-<name>.mp4 and cadence-algorithms-reel.mp4 (git-ignored)
# Synthetic data only, no server. Needs: macOS, Google Chrome, Node 20+, ImageMagick, webp tools, swiftc, and
# `npm install` done in app/web (the clips reuse the app's fonts). Takes about 3 minutes.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
MEDIA_DIR="${MEDIA_DIR:-$ROOT/docs/media}"
SOCIAL_DIR="${SOCIAL_DIR:-$ROOT/marketing}"
FPS=12

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1 ($2)" >&2; exit 1; }; }
need magick "brew install imagemagick"; need img2webp "brew install webp"; need swiftc "xcode-select --install"
[[ -d "$ROOT/app/web/node_modules/@fontsource" ]] || { echo "Run npm install in app/web first (fonts)." >&2; exit 1; }
[[ -d "$HERE/node_modules/playwright-core" ]] || (cd "$HERE" && npm ci --silent)

WORK="$(mktemp -d "${TMPDIR:-/tmp}/cadence-explainers.XXXXXX")"
trap '[[ "$WORK" == */cadence-explainers.* && -d "$WORK" ]] && rm -rf "$WORK"' EXIT
mkdir -p "$MEDIA_DIR" "$SOCIAL_DIR"

echo "== Rendering frames"
node "$HERE/render-explainers.mjs" "$WORK/frames" "$FPS" 10
swiftc -O "$HERE/frames2mp4.swift" -o "$WORK/frames2mp4" 2>&1 | grep -v warning || true

echo "== README animations (animated WebP, 880 px) and per-algorithm MP4s"
for dir in "$WORK"/frames/*/; do
  name="$(basename "$dir")"
  mkdir -p "$WORK/small/$name"
  # every other frame keeps the file small; the clips are smooth curves, not fast motion
  ls "$dir"/f*.png | awk 'NR%2==1' | while read -r f; do magick "$f" -resize 880x "$WORK/small/$name/$(basename "$f")"; done
  img2webp -loop 0 -d 167 -lossy -q 80 -m 6 "$WORK/small/$name"/f*.png -o "$MEDIA_DIR/algo-$name.webp" >/dev/null
  "$WORK/frames2mp4" "$dir" "$SOCIAL_DIR/algo-$name.mp4" "$FPS" 1800000
done

echo "== Reel: every algorithm in one video"
mkdir -p "$WORK/reel"; i=0
for name in banister hrv cs plan trust; do
  for f in "$WORK/frames/$name"/f*.png; do ln -s "$f" "$WORK/reel/f$(printf %05d $i).png"; i=$((i+1)); done
done
"$WORK/frames2mp4" "$WORK/reel" "$SOCIAL_DIR/cadence-algorithms-reel.mp4" "$FPS" 1800000

echo "== Done"
ls -la "$MEDIA_DIR"/algo-*.webp "$SOCIAL_DIR"/algo-*.mp4 "$SOCIAL_DIR"/cadence-algorithms-reel.mp4 | awk '{printf "%6.1f MB  %s\n", $5/1048576, $9}'
