# Protocol investigation guide

A repeatable workflow for collecting evidence from the Dr Trust 526 Legend. Every step produces a JSON
capture in `captures/`. Run all commands from the repository root.

```sh
W=research/.venv/bin/cadence
```

## Before you start

- Bluetooth access granted to your terminal / VS Code.
- **Close the official Dr Trust app on your iPhone and turn off the iPhone's Bluetooth.** A BLE scale usually
  accepts only one connection; if the phone connects first, the Mac sees nothing.
- Put the scale on a hard floor 0.5–1 m from the Mac.
- Have something to write down every value the display shows, in order.
- Use `--notes` on every command to describe conditions (person, clothing, unit set on scale, battery age).

## Step 1 — identify the scale (wake diff)

```sh
$W scan -i -d 60 --notes "wake diff #1"
```

1. Wait ~15 s without touching the scale (baseline).
2. Step on the scale and press **Enter** at the same moment (records the wake marker).
3. Stay on until the measurement finishes; step off. The scan ends after 60 s.

The summary flags devices `NEW-AFTER-WAKE` or `CHANGED-AFTER-WAKE`. Repeat 2–3 times. The scale is the
device flagged consistently. Record its address, name, service UUIDs and manufacturer company IDs.

If the scale is not flagged, rerun with `--all-events -v` and look for any device whose RSSI jumps to a
strong value (e.g. above −60 dBm) after the marker.

## Step 2 — GATT inspection

Wake the scale, then immediately run (substitute what you found in step 1):

```sh
$W inspect --address <ADDRESS> --notes "gatt inspect"
# or: $W inspect --name <NAME>
```

Record: services, characteristic properties, readable values (Device Information strings are useful),
and whether standard SIG Weight Scale (0x181D) or Body Composition (0x181B) services are present.

If the scale disconnects before inspection finishes, repeat — the scale may sleep within seconds.

## Step 3 — measurement captures

### 3a. Connected capture (notifications)

```sh
$W capture --address <ADDRESS> --notes "barefoot, unit kg"
```

Follow the on-screen phases. Empty Enter advances; any text is stored as a note in the current phase.
**At each phase, type exactly what the display shows**, for example:

```
display 72.4 kg flashing
display 72.6 kg locked
display BF 21.3 %
```

Type `q` + Enter when the scale turns off. Ctrl+C also saves the file.

### 3b. Advertisement-only capture

Some scales broadcast measurements without a connection. Run the same scenario without connecting:

```sh
$W capture --address <ADDRESS> --adv-only --notes "adv only"
```

### 3c. Variations that make fields stand out

Do each capture at least twice. Vary one thing at a time:

| Variation | What it reveals |
| --- | --- |
| Same person, back-to-back | Noise vs stable fields |
| Hold a known object (e.g. 5 kg) | Weight field + scale factor |
| Shoes on vs barefoot | Whether impedance/body-comp data depends on skin contact |
| Unit switched kg ↔ lb on the scale | Unit flag |
| Different person | Profile-dependent fields |
| Empty scale tapped awake | Wake-only packets |

## Step 4 — offline analysis

```sh
$W analyze captures/capture-*.json
$W analyze captures/capture-A.json captures/capture-B.json --stream notify
```

Look for:
- Streams that only appear after the scale wakes.
- Byte offsets (`??` in the mask) that change while the display changes, and stay fixed when it is locked.
- Payloads whose arrival coincides with your notes in the timeline.

Do not label a field as decoded until it matches the display across several captures.

## What to share for protocol analysis

1. The JSON files from steps 1–3 (scan files contain nearby devices; trim them if you prefer — only the
   scale's events are needed).
2. For each capture: the sequence of values the display showed, and anything unusual
   (error codes, lost connection, measurement aborted).
3. The scale's unit setting and whether you were barefoot.
4. Whether the official app had ever been paired with this scale.

## Confirmed decodes (SSW526 / Dr Trust USA 526 Legend)

Evidence as of the captures from 2026-10-23. Update this section only when a new capture confirms or
revises something — see the rule at the top of Step 4.

**GATT layout.** One vendor-specific service, `0xffb0`. `0xffb2` is notify-only and streams continuously
once connected, with nothing written. `0xffb1` is writable; its purpose is untested — `cadence capture`
never writes to it, and weight streams fine without doing so. No standard SIG Weight Scale (`0x181D`) or
Body Composition (`0x181B`) service is present.

**Packet shape.** Every notification on `0xffb2` is 20 bytes:

```
ac 27 00 [B3] [B4 B5] 00 00 00 00 00 00 00 00 00 00 00 03 d5 [B19]
```

- `ac 27 00` / `03 d5` — fixed header/trailer, unchanged across every capture so far.
- `B3` — a one-byte flag: `0x68` while the reading is settling, `0x69` once it locks. Confirmed
  independently in two captures (the value flips exactly when `B4 B5` stops moving).
- `B4 B5` (big-endian uint16) — the weight field. Settles with visible overshoot/damping (classic
  load-cell ADC settling), matching the "locked" state of `B3`.
- Bytes 6–16 — zero in every packet captured so far, in both idle and locked states.
- `B19` — changes only when `B4 B5`/`B3` do; almost certainly a checksum over the payload. Not reverse
  engineered.

**Weight formula — confirmed:**

```
weight_kg = uint16_be(B4, B5) / 120
```

Verified against the official Dr Trust app's displayed weight for one capture session: the raw value
divided by 120 matched the app's reading exactly (to the app's own two decimal places). A second,
independent capture session landed on a different but equally plausible weight using the same formula —
consistent with two real, separate weigh-ins rather than a coincidence.

Not yet established:
- Whether there's a small additive offset the single confirmed data point can't rule out (the "hold a
  known object" variation in Step 3c would settle this — a known weight added should shift the raw value
  by exactly `object_kg × 120`, from the same baseline).
- Behaviour across a wider weight range; only one person's weight has been confirmed so far.
- What, if anything, `B19` encodes, and what `0xffb1` is for.

**Body composition — not observed on the wire.** Bytes 6–16 never populated with anything beyond zero
across two full capture sessions, including a ~26 s silent window before the scale disconnected on its
own — the point at which the display would be cycling through body-fat/BMI/etc. The official app's own UI
for these values is headed "based on your initial info" (the stored age/height/sex profile), consistent
with the app computing them client-side from weight plus profile rather than reading them from the scale.
Per the project's own rule, Cadence will not present body-composition values as *measured* unless a future
capture shows the scale actually transmitting them — right now the evidence points the other way.

**In the app.** The weight formula above is live in `app/backend/cadence_app/scale.py` — an opt-in background
listener (Settings → Bluetooth scale) that imports `decode_weight_packet` directly from this package rather
than reimplementing it, debounces a stream of packets down to one accepted reading per weigh-in, and stores
it in the local vault. See that module's docstring for the debounce policy. Verified end-to-end against real
hardware on 2026-10-23: enabled in Settings, a real weigh-in connected, locked, debounced and appeared in
the weight trend with no manual steps beyond standing on the scale.

**Next useful captures**, in order of value:
1. Step on holding (or not holding) a known small weight, to test for an offset in the weight formula.
2. A capture that stays connected through the scale's full auto-cycle and display sequence without
   stepping off early, to settle whether body-comp data ever crosses `0xffb2` under any circumstance.
3. If a packet sniffer (nRF Connect on iPhone, or Apple PacketLogger) is available, observing what the
   *official* app does with `0xffb1` — without replicating any write here until it's understood.
