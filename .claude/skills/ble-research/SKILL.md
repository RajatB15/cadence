---
name: ble-research
description: Work on the Dr Trust 526 Legend (SSW526) BLE scale reverse-engineering: running scans/captures, analyzing capture files, writing parsers or fixtures. Use for anything under research/ or docs/protocol-investigation.md.
---

- Read [docs/protocol-investigation.md](../../../docs/protocol-investigation.md) and the README "Findings" table first. Status is **unconfirmed**; don't state the protocol, measurement transport, or which metrics are transmitted vs app-calculated until evidence from a capture shows it. Update the Findings table with evidence (capture file + what changed) when something is established.
- Tools: `research/.venv/bin/cadence scan|inspect|capture|analyze`, run from the repo root so captures land in `captures/`. Hardware steps (waking/stepping on the scale, Bluetooth permission) need the user; ask them and provide exact commands.
- Never write to the scale. Any command/profile/time-sync write must be added deliberately with captured justification.
- Captures contain neighbours' device identifiers and body data: don't commit or paste raw ones. Reviewed, redacted fixtures go in `research/tests/fixtures`; tests otherwise use synthetic data.
- Capture format is versioned JSON (`research/cadence_ble/capture_format.py`); raw bytes stay lowercase hex, never altered. Old `weighin-capture` files must still load.
- On macOS `--address` is a per-Mac CoreBluetooth UUID, not the MAC; Bleak coalesces duplicate adverts, so rates are approximate.
- Run `cd research && .venv/bin/pytest` after changes. Any parser reused by the app goes behind the connector boundary only once verified.
