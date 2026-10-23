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
