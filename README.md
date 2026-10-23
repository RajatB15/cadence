# Cadence

A local-first training and recovery coach. It keeps every Garmin record in a private local vault and turns
it into readiness, training-load and sleep insights, with a coach note on every session, day and weigh-in.
It also includes research tools for the **Dr Trust USA 526 Legend** BLE body-composition scale,
reverse-engineering its Bluetooth Low Energy traffic with no dependency on the official app.

> **Scale status: protocol discovery.** Nothing about the scale's protocol is confirmed yet.
> No compatibility is claimed until it is verified against the physical scale.

## Layout

| Path | Purpose |
| --- | --- |
| [research/](research/) | Python + Bleak research tools (`cadence` CLI) |
| [research/cadence_ble/](research/cadence_ble/) | scanner, GATT inspector, capture recorder, offline analyzer |
| [research/tests/](research/tests/) | unit tests (synthetic data only, until real fixtures exist) |
| [docs/protocol-investigation.md](docs/protocol-investigation.md) | reproducible capture workflow |
| `captures/` | raw capture output (git-ignored) |

Product roadmap: [plan.md](plan.md). Build a local-first health and training web app,
then package for macOS, with LLM integration last. Existing BLE research continues alongside this work.

## Web app (local)

```sh
# backend: http://127.0.0.1:8765 (loopback only)
cd app/backend && python3 -m venv .venv && .venv/bin/pip install -e '.[test]'
.venv/bin/cadence-app

# frontend: http://127.0.0.1:5173
cd app/web && npm install && npm run dev
```

Tests: `cd app/backend && .venv/bin/pytest` and `cd app/web && npm test`.
The local database lives in `data/` (git-ignored). Open **Vault** and choose **Sync everything** to pull
your full Garmin history with the locally stored key. Every response is kept in a local vault, settled days
are never re-requested, and **Rebuild offline** re-derives all charts with zero API calls. Garmin records
take precedence over demo data across all views; "Load demo year" still provides labelled synthetic data.

### Run at login

```sh
scripts/cadence-service.sh install    # start now and at every login; restarts if it crashes
scripts/cadence-service.sh status | restart | logs | uninstall
```

The service serves the built site at http://127.0.0.1:8765 (no dev server needed), resumes phone sharing,
syncs Garmin every 3 hours (every 45 minutes on mornings until readiness is in) and sends due notifications.
Logs: `~/Library/Logs/Cadence/backend.log`. After frontend changes run `npm --prefix app/web run build`;
after backend changes run `scripts/cadence-service.sh restart`. Your Mac must be awake for the phone to connect.

### On your iPhone

1. Open **Settings → On your iPhone → Share to iPhone** and scan the QR code with the iPhone camera.
2. In Safari, tap **Share → Add to Home Screen**, then open Cadence from the Home Screen.
3. Under **Notifications**, tap **Turn on notifications**.

On home Wi-Fi the phone uses `http://<mac-ip>:8766`. For access from anywhere, and for notifications
(iOS only allows them over HTTPS), install [Tailscale](https://tailscale.com) on the Mac and iPhone, sign in
with the same account, enable HTTPS certificates in the Tailscale admin console, then run
`tailscale serve --bg 8766` on the Mac. The pairing QR switches to the `https://…ts.net` address automatically.

The phone server is opt-in and read-only apart from managing its own notifications, and every request needs
the pairing key from the QR code (kept as an HttpOnly cookie). **New pairing code** unpairs every phone.

### Notifications

Standard Web Push to any subscribed browser or Home Screen app: a morning readiness brief, a verdict
after each session, a 22:30 bedtime nudge, and Garmin key renewal reminders. Each one is sent once and can be
turned off in Settings. The signing key is generated locally in `data/push-vapid.pem` (mode 0600).

## Setup (macOS)

```sh
cd research
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

The app running the tools (Terminal, VS Code, ...) needs Bluetooth access:
System Settings → Privacy & Security → Bluetooth. Until it is granted, scanning silently waits.

Run the CLI from the repository root so captures land in `captures/`:

```sh
research/.venv/bin/cadence --help
```

## Tools

| Command | What it does |
| --- | --- |
| `cadence scan` | Logs advertisements (name, address, RSSI, service UUIDs, manufacturer data, service data). `-i` lets you mark the moment you wake the scale; devices that appear or change afterwards are flagged as candidates. |
| `cadence inspect` | Connects to a selected device, enumerates services/characteristics/descriptors, reads every readable value, reports read/write/notify/indicate properties and whether standard SIG Weight Scale (0x181D) / Body Composition (0x181B) services are present. |
| `cadence capture` | Phase-guided session (idle → awake → measuring → weight done → body comp done → stepped off). Records target advertisements, connects, snapshots GATT, subscribes to every notify/indicate characteristic, timestamps every payload, and lets you type what the display shows. Reconnects automatically when the scale wakes again. `--adv-only` never connects. |
| `cadence analyze` | Offline: groups payloads per stream (characteristic or advertisement field), lists distinct payloads with phases, prints byte masks showing which offsets vary, and a changes-only timeline interleaved with your notes. |

Device selection (`--address`, `--name`, `--service-uuid`, `--company-id`, `--min-rssi`) is AND-ed.
On macOS, `--address` is a CoreBluetooth UUID that is stable per Mac, not the scale's MAC address.

## Capture format

Versioned JSON (`format: "cadence-capture"`, `schema_version: 1`), defined in
[research/cadence_ble/capture_format.py](research/cadence_ble/capture_format.py).
Every event has `seq`, `t` (UTC ISO 8601), `t_rel` (monotonic seconds since start), `phase`, `type`.
Raw bytes are stored as lowercase hex, never decoded or altered.

Event types: `advertisement`, `notification`, `read`, `gatt`, `subscription`, `connection`, `marker`, `note`.

## Findings

| Item | Status | Evidence |
| --- | --- | --- |
| Scale identity on BLE | **Unconfirmed (likely)** | Device named `SSW526` (service UUID `0xffb0`, manufacturer company ID `0x27ac`, mfr data `5f a9 01 7a f6 98 01`). In `scan-20261022-183858`: advertised every ~1.2 s from 0.4 s to 25.3 s, payload never changed, then went silent; absent in a later scan. In `scan-20261022-184213` (~16 s, scale untouched; a wake marker was placed but the scale was **not** stepped on) it was not seen at all. Consistent with a device that sleeps, but no wake marker has correlated it with the scale yet. |
| Standard Weight Scale / Body Composition service | Unknown | Needs `cadence inspect`. |
| Measurement transport (notifications vs advertisements) | Unknown | Needs `cadence capture`. |
| Which of the 14 metrics are transmitted vs app-calculated | Unknown | Needs captures compared with the display. |

## Known limitations

- Bleak's CoreBluetooth backend scans without `AllowDuplicates`, so macOS may coalesce repeated identical
  advertisements. Changed advertisement content is still reported, but adv rates in captures are not exact.
  If the scale turns out to broadcast measurements, cross-check with nRF Connect on iPhone or Apple PacketLogger.
- The tools never write to the scale. If evidence shows the scale needs a command (e.g. user profile or time
  sync) before sending data, that will be added deliberately with captured justification.
- Git needs the Xcode license accepted on this Mac: `sudo xcodebuild -license`.

## Principles

Local-first, no required cloud backend or account for local scale tools. The planned web app adds a local
backend and analytics as described in [plan.md](plan.md). Body-composition values are never presented as
measured unless the protocol confirms the scale transmits them.
