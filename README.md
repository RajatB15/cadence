# Cadence

[![CI](https://github.com/RajatB15/cadence/actions/workflows/ci.yml/badge.svg)](https://github.com/RajatB15/cadence/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**A private, open-source training coach for Garmin users.** Readiness, a periodised training plan, critical speed,
habit insights and weekly reviews — computed on your own computer, from your own Garmin data, with every method
shown and nothing sent to a cloud service except the Garmin sync itself. No subscription, no account, no ads.

Cadence is not affiliated with Garmin. It reads your data through Garmin's official [Personal API](https://developer.garmin.com/gc-developer-program/personal/personal-api/).

<p align="center">
  <img src="docs/screenshots/home.webp" width="49%" alt="Cadence home screen: readiness and Cadence score rings, today's plan, a morning check-in prompt" />
  <img src="docs/screenshots/coach.webp" width="49%" alt="Cadence coach page: readiness breakdown by factor and this week's training prescription" />
</p>
<p align="center">
  <img src="docs/screenshots/plan.webp" width="49%" alt="Cadence plan page: ranked run options for today with predicted load, fitness and recovery outcomes" />
  <img src="docs/screenshots/score.webp" width="49%" alt="Cadence score page: one 0-100 number across train, recover, sleep and move, with a radar of every factor" />
</p>

<p align="center"><sub>Screenshots use the built-in demo data — no Garmin account needed to try the UI.</sub></p>

## Why

Garmin Connect already shows trends and a readiness number. Cadence is for people who want to know *why* that
number is what it is, want a training plan that adapts to a race goal instead of a fixed template, and would
rather their health data stayed on their own machine.

- **Transparent, not a black box.** Every score's "How this works" cites its method — Banister fitness/fatigue,
  Theil–Sen trend fitting, Benjamini–Hochberg false-discovery control on "what moves your recovery" — and shows
  its sample size and confidence, not just a number.
- **A real training plan, not just a daily score.** Set a race goal and distance; Cadence builds base → build →
  race-specific → taper phases, ramps load with a cap, rotates threshold/VO₂max/race-pace sessions, and caps your
  long run at 10% growth (the rule a 2025 Garmin-runner injury study found safer than weekly load ratios).
- **Runner-specific performance analytics.** Critical speed and D′ fitted from your best efforts, race-time
  predictions, pace zones, grade-adjusted heart-rate drift, a personal heat cost learned from your own runs.
- **It learns you, not an average athlete.** Your own sleep need (where more sleep stops lifting HRV), your own
  recovery time after a hard session, your own load per minute by sport — all fitted from your history, with a
  generic fallback stated plainly until there's enough of your own data.
- **A planner, not just a tracker.** Pick a day and a sport; Cadence ranks sessions for you and predicts the load,
  next-morning fitness/form, recovery time and what each one builds — before you commit.
- **Local-first.** SQLite on your Mac, nothing required in the cloud. The only outbound calls are to Garmin (your
  data, your key) and, if you enable it, Open-Meteo for weather (only a rounded location and dates, never routes
  or health data).

## Features

| | |
|---|---|
| **Readiness & Cadence Score** | A live readiness ring from HRV, resting HR, sleep, training load and Body Battery; a 0–100 Cadence Score across train/recover/sleep/move with per-factor points lost, checked against your own run efficiency. |
| **Training plan** | Goal-aware periodisation, 3:1 load blocks, progressive key sessions with heart-rate and pace targets, a 7-day session planner that ranks run/ride/swim options and predicts outcomes before you plan them. |
| **Performance** | Critical speed & D′, race predictions, pace zones, grade-adjusted Pa:HR drift and late-run durability, a heart-rate-zone staleness check. |
| **Recovery** | HRV-guided go/easy status, your personal recovery time by session type, an illness/overreach early warning, an under-fuelling pattern check. |
| **Sleep** | A personal sleep need (not a flat 8 hours), a nightly bedtime target that adapts to training load and sleep debt, Sleep Regularity Index. |
| **Strength** | Upload a class screenshot — the Mac reads it on-device (Apple Vision) and maps exercises to movement patterns; a heart-rate trace is split into warm-up/block/cool-down. |
| **Journal** | A 10-second daily check-in (alcohol, caffeine, sleep habits, stress…) tested against your recovery with the same statistical rigor as everything else. |
| **Weather** | Hot/cold/windy session notes, a personal heat cost on efficiency, forecasts with a cooler-hour suggestion for planned sessions. |
| **Reviews** | Weekly and monthly reviews — training, plan adherence, fitness, recovery, sleep, habits, highlights — each with one focus for next period. |
| **All-day strain** | Banister TRIMP from all-day heart rate, split into workout vs everyday movement, against a daily target band. |
| **BLE scale bridge** | Weight from a reverse-engineered Dr Trust USA 526 Legend, read locally over Bluetooth (opt-in, macOS) and blended into your weight trend — no cloud, no official app. |
| **Vault** | Every Garmin response is kept, compressed, forever. Dashboards rebuild from the vault with zero API calls. |
| **Your iPhone** | A read-only (apart from its own check-ins) share server with QR pairing, installable as a Home Screen app, with Web Push notifications. |

> **Scale status: weight confirmed, body composition is not.** Cadence includes Python research tools for the Dr
> Trust USA 526 Legend BLE body-composition scale (see [BLE scale research](#ble-scale-research) below) and an
> opt-in bridge that imports weight into the app. Body-composition values are never presented as measured — this
> scale doesn't transmit them, only its own app computes them from your profile.

## Quick start (try it with demo data)

No Garmin account needed — Cadence ships with a deterministic demo dataset.

```sh
# backend — http://127.0.0.1:8765
cd app/backend && python3 -m venv .venv && .venv/bin/pip install -e '.[test]'
.venv/bin/cadence-app &

# frontend (dev server) — http://127.0.0.1:5173
cd app/web && npm install && npm run dev
```

Open the app, go to **Vault**, and click **Load demo year** (or run `curl -X POST -H 'X-Cadence-Request: 1' http://127.0.0.1:8765/api/sync/demo`).

Requires Python 3.12+ and Node 20+. Platform notes: the login service and on-device screenshot reading (strength
classes) are macOS-only; everything else — backend, frontend, weather, the training plan and analytics — runs on
Linux too, and CI tests all of it there.

## Connecting your real Garmin account

1. Request a [Garmin Personal API](https://developer.garmin.com/gc-developer-program/personal/personal-api/) key
   (free, for your own data).
2. Put it in `.secrets/garmin.env` (git-ignored):
   ```sh
   mkdir -p .secrets && cat > .secrets/garmin.env <<'EOF'
   GARMIN_API_KEY=your-key-here
   GARMIN_API_KEY_EXPIRES_ON=YYYY-MM-DD
   GARMIN_API_KEY_REMINDER_DAYS=30,7,1
   EOF
   chmod 600 .secrets/garmin.env
   ```
3. Restart the backend, open **Vault**, and choose **Sync everything**. Every response is stored once, settled
   days are never re-requested, and **Rebuild offline** re-derives every chart with zero API calls. Garmin records
   take precedence over demo data everywhere once present.

Tests: `cd app/backend && .venv/bin/pytest` and `cd app/web && npm test`. The product roadmap and architecture
notes live in [plan.md](plan.md).

### Run at login (macOS)

```sh
scripts/cadence-service.sh install    # start now and at every login; restarts if it crashes
scripts/cadence-service.sh status | restart | logs | uninstall
```

The service serves the built site at http://127.0.0.1:8765 (no dev server needed), resumes phone sharing, syncs
Garmin every 3 hours (every 45 minutes on mornings until readiness is in) and sends due notifications. Logs:
`~/Library/Logs/Cadence/backend.log`. After frontend changes run `npm --prefix app/web run build`; after backend
changes run `scripts/cadence-service.sh restart`. Your Mac must be awake for the phone to connect.

### On your iPhone

1. Open **Settings → On your iPhone → Share to iPhone** and scan the QR code with the iPhone camera.
2. In Safari, tap **Share → Add to Home Screen**, then open Cadence from the Home Screen.
3. Under **Notifications**, tap **Turn on notifications**.

On home Wi-Fi the phone uses `http://<mac-ip>:8766`. For access from anywhere, and for notifications (iOS only
allows them over HTTPS), install [Tailscale](https://tailscale.com) on the Mac and iPhone, sign in with the same
account, enable HTTPS certificates in the Tailscale admin console, then run `tailscale serve --bg 8766` on the
Mac. The pairing QR switches to the `https://…ts.net` address automatically.

The phone server is read-only apart from its own push settings, the morning journal check-in, and naming strength
classes — every request needs the pairing key from the QR code (kept as an HttpOnly cookie). **New pairing code**
unpairs every phone.

### Notifications

Standard Web Push to any subscribed browser or Home Screen app: a morning readiness brief (with a journal
check-in prompt), a verdict after each session, a bedtime nudge that moves with your personal sleep target,
weekly/monthly review summaries, and Garmin key renewal reminders. Each one is sent once and can be turned off
individually in Settings. The signing key is generated locally in `data/push-vapid.pem` (mode 0600).

## Architecture

| Path | Purpose |
|---|---|
| [app/backend/cadence_app/](app/backend/cadence_app/) | FastAPI app: Garmin sync engine & vault, SQLite + Alembic migrations, journal, strength, planner, weather, push notifications |
| [app/backend/cadence_app/analytics/](app/backend/cadence_app/analytics/) | Pure analytics: load/readiness, performance (critical speed), recovery, periodised plan, habits, strength parsing, all-day strain, score, weekly/monthly reviews |
| [app/web/src/](app/web/src/) | React 19 + TypeScript + Vite + Tailwind + ECharts + MapLibre |
| [research/](research/) | Python + Bleak BLE research tools (`cadence` CLI) for the body-composition scale |
| [docs/protocol-investigation.md](docs/protocol-investigation.md) | Reproducible BLE capture workflow |
| [plan.md](plan.md) | Product roadmap, architecture notes, acceptance criteria |

**Technology:** Python/FastAPI/SQLAlchemy backend, React/TypeScript frontend, SQLite persistence, NumPy/SciPy
analytics, no required cloud backend. See [plan.md](plan.md) for the full stack and roadmap.

**Map tiles:** activity route maps use free, keyless providers — OpenFreeMap (OSM data), AWS/Mapzen terrain, and
EOX Sentinel-2 satellite imagery, the last under CC BY-NC-SA 4.0 (**personal, non-commercial use only**, with
attribution). If you deploy Cadence commercially, swap or remove the EOX satellite layer.

## BLE scale research

Cadence also includes research tools for the **Dr Trust USA 526 Legend** BLE body-composition scale,
reverse-engineering its Bluetooth Low Energy traffic with no dependency on the official app.

```sh
cd research
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

The app running the tools (Terminal, VS Code, ...) needs Bluetooth access: System Settings → Privacy & Security →
Bluetooth. Until it is granted, scanning silently waits. Run the CLI from the repository root so captures land in
`captures/` (git-ignored — raw captures can contain nearby devices' identifiers and personal body data):

```sh
research/.venv/bin/cadence --help
```

| Command | What it does |
|---|---|
| `cadence scan` | Logs advertisements (name, address, RSSI, service UUIDs, manufacturer data, service data). `-i` marks the moment you wake the scale; devices that change afterwards are flagged as candidates. |
| `cadence inspect` | Connects to a selected device, enumerates services/characteristics/descriptors, reads every readable value, and reports whether standard SIG Weight Scale (0x181D) / Body Composition (0x181B) services are present. |
| `cadence capture` | Phase-guided session (idle → awake → measuring → weight done → body comp done → stepped off). Subscribes to every notify/indicate characteristic, timestamps every payload, and lets you type what the display shows. `--adv-only` never connects. |
| `cadence analyze` | Offline: groups payloads per stream, lists distinct payloads with phases, prints byte masks showing which offsets vary, and a changes-only timeline interleaved with your notes. |

Device selection (`--address`, `--name`, `--service-uuid`, `--company-id`, `--min-rssi`) is AND-ed. On macOS,
`--address` is a CoreBluetooth UUID stable per Mac, not the scale's MAC address.

Capture format: versioned JSON (`format: "cadence-capture"`, `schema_version: 1`), defined in
[capture_format.py](research/cadence_ble/capture_format.py). Every event has `seq`, `t` (UTC ISO 8601), `t_rel`
(monotonic seconds since start), `phase`, `type`; raw bytes are stored as lowercase hex, never decoded or altered.

### Findings so far

| Item | Status |
|---|---|
| Scale identity on BLE | **Confirmed.** Device named `SSW526` (service UUID `0xffb0`, manufacturer company ID `0x27ac`) connects live and its weight stream matches real weigh-ins (see below) — two independent sessions, two plausible weights. |
| Standard Weight Scale / Body Composition service | **Confirmed absent.** `inspect-20261023-171705.json`: one vendor-specific service `0xffb0` only — `0xffb2` (notify) and `0xffb1` (write); no standard SIG `0x181D`/`0x181B`. Fully proprietary protocol. |
| Measurement transport (notifications vs advertisements) | **Confirmed: notifications, no write needed.** `0xffb2` streams ~20-byte packets within ~2 s of connecting; nothing is ever written to `0xffb1` — `cadence capture` only subscribes. |
| Weight decode | **Confirmed.** 20-byte packet `ac 27 00 [B3] [B4 B5] 00×11 03 d5 [checksum]`. `B3` is a stability flag (`0x68` settling, `0x69` locked). `weight_kg = uint16_be(B4,B5) / 120`. Verified against the official app's reading, exact match (capture `20261023`, session 2); a second independent session landed on a plausible, slightly different weight (session 1). Not yet tested for a fixed offset (needs the "hold a known object" capture from the guide) or across a wider weight range. |
| Which of the other 13 display metrics are transmitted vs app-calculated | **Likely all app-calculated, not yet proven.** Bytes 6–16 stayed zero across both full captures, including a 26 s silent window before the scale's own disconnect — right when the display would be cycling through them. The official app's own UI labels this screen "based on your initial info" (stored profile), consistent with client-side computation from weight + profile, not scale-transmitted data. Cadence will not present these as measured unless a future capture shows otherwise. |

The tools never write to the scale; a write would only be added deliberately with captured justification. See
[docs/protocol-investigation.md](docs/protocol-investigation.md) for the full capture workflow.

### Using the scale in the app

With the weight formula confirmed, the main backend can import it directly — `cadence_app/scale.py` is a
background listener (opt-in, macOS/Bluetooth only) that connects, debounces a stream of packets down to one
accepted reading per weigh-in, and stores it in your local vault (blended into your weight trend alongside
Garmin or demo data). Nothing here reimplements the protocol; it imports the tested
[`cadence_ble.ssw526`](research/cadence_ble/ssw526.py) decoder. To turn it on, install the research package
into the backend's own venv too:

```sh
cd app/backend && .venv/bin/pip install -e '.[test]' -e ../../research
```

Then enable it from **Settings → Bluetooth scale** in the app. Without that extra install, the backend runs
and tests exactly as before — this is entirely optional, and the feature reports itself as unavailable
rather than failing.

## Privacy

- Everything lives in a local SQLite database (`data/`, git-ignored). No analytics, no accounts, no telemetry.
- The local service binds to loopback (127.0.0.1); the phone share server rejects unpaired requests and foreign
  hosts.
- Outbound network calls: Garmin (your own data, your own key) and, only if you turn it on in Settings, Open-Meteo
  weather (rounded coordinates and dates only — never routes, timestamps or health data).
- Local storage is plaintext, not encrypted; back up and protect `data/` and `.secrets/` accordingly.

## Contributing

Issues and pull requests are welcome. `cd app/backend && .venv/bin/pytest`, `cd app/web && npm test && npm run
typecheck`, and `cd research && .venv/bin/pytest` must all pass (CI runs all three on every PR). See
[plan.md](plan.md) for architecture conventions and the roadmap.

## License

[MIT](LICENSE).
