"""`cadence scan`: advertisement discovery and wake-diff candidate detection."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from typing import Any

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from .capture_format import Recorder, adv_fingerprint, adv_to_dict
from .console import start_stdin_reader
from .filters import TargetFilter, normalize_uuid

# Bluetooth SIG assigned numbers; only used to flag what a device advertises.
SIG_SERVICES_OF_INTEREST = {
    normalize_uuid("181d"): "Weight Scale",
    normalize_uuid("181b"): "Body Composition",
    normalize_uuid("181c"): "User Data",
}

# Throttle for unchanged advertisements so scan files stay a manageable size.
UNCHANGED_RECORD_INTERVAL_S = 1.0


@dataclass
class DeviceSeen:
    address: str
    names: set[str] = field(default_factory=set)
    first_seen: float = 0.0
    last_seen: float = 0.0
    count: int = 0
    rssi_min: int | None = None
    rssi_max: int | None = None
    service_uuids: set[str] = field(default_factory=set)
    company_ids: set[str] = field(default_factory=set)
    service_data_uuids: set[str] = field(default_factory=set)
    fingerprints: set[tuple] = field(default_factory=set)
    last_fingerprint: tuple | None = None
    last_recorded: float = float("-inf")
    changed_after_wake: bool = False

    def update(self, fields: dict[str, Any], t: float) -> bool:
        """Update stats; return True if advertisement content changed."""
        self.count += 1
        self.last_seen = t
        for n in (fields["name"], fields["local_name"]):
            if n:
                self.names.add(n)
        rssi = fields["rssi"]
        if rssi is not None:
            self.rssi_min = rssi if self.rssi_min is None else min(self.rssi_min, rssi)
            self.rssi_max = rssi if self.rssi_max is None else max(self.rssi_max, rssi)
        self.service_uuids.update(fields["service_uuids"])
        self.company_ids.update(fields["manufacturer_data"])
        self.service_data_uuids.update(fields["service_data"])
        fp = adv_fingerprint(fields)
        changed = fp != self.last_fingerprint
        self.last_fingerprint = fp
        self.fingerprints.add(fp)
        return changed

    def to_summary(self, wake_t: float | None) -> dict[str, Any]:
        sig = sorted(
            SIG_SERVICES_OF_INTEREST[u]
            for u in self.service_uuids | self.service_data_uuids
            if u in SIG_SERVICES_OF_INTEREST
        )
        return {
            "address": self.address,
            "names": sorted(self.names),
            "first_seen_t_rel": round(self.first_seen, 3),
            "last_seen_t_rel": round(self.last_seen, 3),
            "adv_count": self.count,
            "rssi_min": self.rssi_min,
            "rssi_max": self.rssi_max,
            "service_uuids": sorted(self.service_uuids),
            "manufacturer_company_ids": sorted(self.company_ids),
            "service_data_uuids": sorted(self.service_data_uuids),
            "distinct_adv_payloads": len(self.fingerprints),
            "sig_services_of_interest": sig,
            "appeared_after_wake": wake_t is not None and self.first_seen >= wake_t,
            "changed_after_wake": self.changed_after_wake,
        }


def _fmt_adv(fields: dict[str, Any]) -> str:
    parts = [f"rssi={fields['rssi']}"]
    name = fields["local_name"] or fields["name"]
    if name:
        parts.append(f"name={name!r}")
    if fields["service_uuids"]:
        parts.append("svc=[" + ",".join(fields["service_uuids"]) + "]")
    if fields["manufacturer_data"]:
        parts.append(
            "mfr={" + ",".join(f"{k}:{v}" for k, v in fields["manufacturer_data"].items()) + "}"
        )
    if fields["service_data"]:
        parts.append("svcdata={" + ",".join(f"{k}:{v}" for k, v in fields["service_data"].items()) + "}")
    return "  ".join(parts)


async def run_scan(args: argparse.Namespace, recorder: Recorder) -> None:
    target = TargetFilter.from_args(args)
    devices: dict[str, DeviceSeen] = {}
    wake_t: float | None = None
    stop = asyncio.Event()
    verbose_changes = args.verbose or not target.is_empty()

    def on_adv(device: BLEDevice, adv: AdvertisementData) -> None:
        if not target.matches(device.address, device.name, adv):
            return
        t = recorder.elapsed()
        fields = adv_to_dict(device.address, device.name, adv)
        seen = devices.get(device.address)
        is_new = seen is None
        if is_new:
            seen = devices[device.address] = DeviceSeen(device.address, first_seen=t)
        changed = seen.update(fields, t)
        if changed and wake_t is not None and not is_new:
            seen.changed_after_wake = True
        if args.all_events or changed or t - seen.last_recorded >= UNCHANGED_RECORD_INTERVAL_S:
            recorder.record("advertisement", **fields)
            seen.last_recorded = t
        if is_new:
            print(f"[{t:7.2f}s] NEW {device.address}  {_fmt_adv(fields)}")
        elif changed and verbose_changes:
            print(f"[{t:7.2f}s] CHG {device.address}  {_fmt_adv(fields)}")

    print(f"Scanning for {args.duration:.0f}s, filter: {target.describe()}")
    if args.interactive:
        recorder.set_phase("baseline", "scan started; scale idle")
        print("Interactive: press Enter right as you wake the scale; type 'q' + Enter to stop early.")

    scanner = BleakScanner(on_adv, cb={"use_bdaddr": args.use_bdaddr})
    await scanner.start()
    input_task: asyncio.Task[None] | None = None
    try:
        if args.interactive:
            lines = start_stdin_reader(asyncio.get_running_loop())

            async def read_input() -> None:
                nonlocal wake_t
                while True:
                    line = await lines.get()
                    if line is None or line.strip().lower() == "q":
                        stop.set()
                        return
                    if line.strip():
                        recorder.note(line.strip())
                    elif wake_t is None:
                        wake_t = recorder.elapsed()
                        recorder.set_phase("awake", "user marked: scale woken")
                        print(f"[{wake_t:7.2f}s] -- wake marker recorded --")

            input_task = asyncio.create_task(read_input())
        try:
            await asyncio.wait_for(stop.wait(), timeout=args.duration)
        except asyncio.TimeoutError:
            pass
    finally:
        if input_task:
            input_task.cancel()
        await scanner.stop()
        summaries = [d.to_summary(wake_t) for d in sorted(devices.values(), key=lambda d: d.first_seen)]
        recorder.doc["summary"] = {"wake_t_rel": wake_t, "devices": summaries}
        _print_summary(summaries, wake_t)


def _print_summary(summaries: list[dict[str, Any]], wake_t: float | None) -> None:
    print(f"\n{len(summaries)} device(s) seen")
    print(f"{'first':>7} {'last':>7} {'n':>5} {'rssi':>9}  address / names / ids")
    for s in summaries:
        rssi = f"{s['rssi_min']}..{s['rssi_max']}"
        flags = []
        if s["appeared_after_wake"]:
            flags.append("NEW-AFTER-WAKE")
        if s["changed_after_wake"]:
            flags.append("CHANGED-AFTER-WAKE")
        if s["sig_services_of_interest"]:
            flags.append("SIG:" + "/".join(s["sig_services_of_interest"]))
        print(
            f"{s['first_seen_t_rel']:7.2f} {s['last_seen_t_rel']:7.2f} {s['adv_count']:5d} {rssi:>9}  {s['address']}"
            f"  names={s['names']}  mfr={s['manufacturer_company_ids']}"
            f"  svc={s['service_uuids']}  payloads={s['distinct_adv_payloads']}"
            + (f"  <{' '.join(flags)}>" if flags else "")
        )
    if wake_t is not None:
        candidates = [s for s in summaries if s["appeared_after_wake"] or s["changed_after_wake"]]
        print(f"\nCandidates (appeared or changed after wake marker at {wake_t:.2f}s): {len(candidates)}")
        for s in candidates:
            print(f"  {s['address']}  names={s['names']}  rssi_max={s['rssi_max']}")
