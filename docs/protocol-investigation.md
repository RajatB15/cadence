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
  independently in two captures (the value flips exactly when `B4 B5` stops moving) — **but** `0x69` turns
  on several seconds before `B4 B5` is actually done moving (seen clearly in the 2026-10-23 capture: `B3`
  flips to `0x69` at ~11s while `B4 B5` keeps wobbling until ~18s). A consumer debouncing on raw-value
  repeats needs a window long enough to outlast that wobble, not just the flag transition.
- `B4 B5` (big-endian uint16) — the weight field. Settles with visible overshoot/damping (classic
  load-cell ADC settling), matching the "locked" state of `B3`.
- Bytes 6–16 — zero in every packet captured so far, in both idle and locked states.
- `B19` — changes only when `B4 B5`/`B3` do; almost certainly a checksum over the payload. Not reverse
  engineered.

**Weight formula — NOT reliable (retracted 2026-10-23):**

```
weight_kg = uint16_be(B4, B5) / 120      # matched one app reading, then failed live use
```

This matched the official app's reading in one early session, but live use disproved it: repeated weigh-ins
decoded to roughly 72.0-72.4 kg while the scale's own display settled at 74.2 kg (about 2 kg apart, same
direction each time). A "hold a known object" check (display: 74.2 kg alone, about 75.6 kg holding a laptop)
was started but never paired with matching decoded values, so it did not show whether the error is an
offset, a different divisor, or a different byte layout. The investigation was stopped there: weight is now
entered manually. Treat `decode_weight_packet`'s weight as unverified; the stability flag and packet shape
are still well supported.

Not established:
- The correct weight conversion (offset vs divisor vs layout), and whether the stream carries a fully
  settled value at all.
- What, if anything, `B19` encodes, and what `0xffb1` is for.

**Body composition — not observed on the wire.** Bytes 6–16 never populated with anything beyond zero
across three full capture sessions now, including a third capture (2026-10-23) that stayed connected
deliberately through the scale's weight-locked state and its full display cycle (the point where it would
show body-fat/BMI/etc. on-device) without disconnecting early. That session produced zero additional
notifications past the point the weight locked — the scale went silent on `0xffb2` rather than sending a
second packet shape — then stayed silent through to step-off. The official app's own UI for these values
is headed "based on your initial info" (the stored age/height/sex profile), consistent with the app
computing them client-side from weight plus profile rather than reading them from the scale.

This is conclusive enough to stop chasing on this characteristic: either the scale doesn't measure body
composition at all, or it measures but never exposes it over `0xffb2` in a normal connect-and-stream
session. Settling which of those two would require either writing an unknown "request" command to the
untested `0xffb1` characteristic, or packet-sniffing the official app's own pairing/handshake traffic —
both bigger asks than this investigation's evidence bar justifies for a question that only ever downgrades
back to "still unmeasured." Per the project's own rule, Cadence will not present body-composition values
as *measured* unless a future capture shows the scale actually transmitting them — right now the evidence
points the other way, and this investigation is considered closed unless new evidence surfaces.

**In the app.** Not used. A background listener existed briefly (2026-10-23) and was removed the same day
because the decoded weight did not match the scale's display (see above). The app logs weight manually or
takes it from Garmin; this package is kept only as research tooling.

**Next useful captures**, in order of value:
1. Redo the known-object test properly: for each of two known loads, record the display value and the
   decoded raw value together, then solve for offset and divisor.
2. A capture that stays connected through the scale's full auto-cycle and display sequence without
   stepping off early, to settle whether body-comp data ever crosses `0xffb2` under any circumstance.
3. If a packet sniffer (nRF Connect on iPhone, or Apple PacketLogger) is available, observing what the
   *official* app does with `0xffb1` — without replicating any write here until it's understood.
