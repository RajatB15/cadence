# Demo media

Records a scripted tour of the Cadence UI and encodes it for the repo README and for social posts. It lives outside
`app/` on purpose: it is marketing tooling, not part of the product.

```sh
tools/demo-media/build.sh
```

It starts a throwaway Cadence server on port 8790 with **synthetic demo data in a temp folder**, so your real data is
never read or changed, records a desktop tour and a phone tour in headless Chrome, and writes:

| Output | Where | Used for |
|---|---|---|
| `tour-desktop.webp`, `tour-phone.webp` | `docs/media/` | the README (commit these) |
| `cadence-tour-*.gif`, `cadence-tour-*.mp4` | `marketing/` (git-ignored) | posts on X, LinkedIn and similar; prefer the MP4 |

Set `MEDIA_DIR` or `SOCIAL_DIR` to write somewhere else, and `DEMO_PORT` / `DEMO_SHARE_PORT` if 8790 or 8791 are busy.

## Needs

macOS, Google Chrome, Node 20+, ImageMagick (`brew install imagemagick`), the WebP tools (`brew install webp`), the Xcode
command line tools (`xcode-select --install`, for `swiftc`), and the backend venv from the main README. It takes about
six minutes.

## Changing the tour

The steps are in `record-tour.mjs` (plain Playwright: click, scroll, wait). Rebuild afterwards and commit the new WebPs.

## Quality notes (learned the hard way)

- Frames are captured as lossless PNG. JPEG frames leave blocky dark backgrounds.
- GIFs use one shared 256-color palette with no dithering and no `-fuzz`. Per-frame palettes flicker, and `-fuzz`
  leaves grainy streaks on dark gradients. The cost is file size (about 8 MB), which is why the MP4 is the better
  format for social posts.
- The README WebPs use quality 80. Quality 60 looked blocky on the dark UI.
- The tour never saves anything: the weight dialog is typed into and then closed.
- A video file in the repo will not play inside a GitHub README. To embed a video, drag the MP4 into the README
  editor on github.com, which creates a playable link.
