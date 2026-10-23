"""`cadence capture`: phase-guided recording of advertisements and notifications."""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakError

from .capture_format import Recorder, adv_fingerprint, adv_to_dict, hex_spaced
from .console import start_stdin_reader
from .filters import TargetFilter, normalize_uuid
from .gatt import NOTIFY_PROPS, snapshot_gatt

DEFAULT_PHASES: list[tuple[str, str]] = [
    ("idle", "Scale idle. Do not touch it. Press Enter once ~10 s have passed."),
    ("awake", "Step on (or tap) the scale to wake it. Press Enter when the display lights up."),
    ("measuring", "Stand still while the weight settles. Press Enter when the number stops changing."),
    (
        "weight_done",
        "Weight is final. Type what the display shows (e.g. 'display 72.4 kg') + Enter,"
        " then an empty Enter to continue.",
    ),
    (
        "body_comp_done",
        "If the scale shows body-composition values, type each one shown + Enter."
        " Empty Enter when it finishes (or if it shows none).",
    ),
    ("stepped_off", "Step off. Wait for the display to turn off, then type q + Enter."),
]

CONNECT_ERRORS = (BleakError, asyncio.TimeoutError, OSError)


def resolve_phases(spec: str | None) -> list[tuple[str, str]]:
    if not spec:
        return DEFAULT_PHASES
    return [(name.strip(), name.strip()) for name in spec.split(",") if name.strip()]


async def run_capture(args: argparse.Namespace, recorder: Recorder) -> None:
    loop = asyncio.get_running_loop()
    target = TargetFilter.from_args(args)
    phases = resolve_phases(args.phases)
    only_chars = {normalize_uuid(u) for u in args.char or []}
    stop = asyncio.Event()
    adv_seen = asyncio.Event()
    locked: dict[str, Any] = {"device": None, "fingerprint": None}

    def on_adv(device: BLEDevice, adv: AdvertisementData) -> None:
        current = locked["device"]
        if current is None:
            if not target.matches(device.address, device.name, adv):
                return
            locked["device"] = device
            recorder.doc["target"] = {"address": device.address, "name": device.name}
            print(f"[{recorder.elapsed():7.2f}s] target locked: {device.address} name={device.name!r}")
        elif device.address != current.address:
            return
        locked["device"] = device
        fields = adv_to_dict(device.address, device.name, adv)
        recorder.record("advertisement", **fields)
        fp = adv_fingerprint(fields)
        if fp != locked["fingerprint"]:
            locked["fingerprint"] = fp
            print(
                f"[{recorder.elapsed():7.2f}s] ADV rssi={fields['rssi']}"
                f" mfr={fields['manufacturer_data']} svcdata={fields['service_data']}"
            )
        adv_seen.set()

    def on_notify(char: BleakGATTCharacteristic, data: bytearray) -> None:
        ev = recorder.record(
            "notification",
            char_uuid=char.uuid,
            char_handle=char.handle,
            service_uuid=char.service_uuid,
            hex=bytes(data).hex(),
        )
        print(f"[{ev['t_rel']:7.2f}s] NOTIFY {char.uuid} h={char.handle} len={len(data)}: {hex_spaced(ev['hex'])}")

    async def connection_loop() -> None:
        while not stop.is_set():
            adv_seen.clear()
            await adv_seen.wait()
            device: BLEDevice = locked["device"]
            disconnected = asyncio.Event()

            def on_disconnect(_: BleakClient) -> None:
                loop.call_soon_threadsafe(disconnected.set)

            recorder.record("connection", state="connecting", address=device.address)
            print(f"[{recorder.elapsed():7.2f}s] connecting to {device.address}...")
            try:
                async with BleakClient(
                    device, disconnected_callback=on_disconnect, timeout=args.connect_timeout
                ) as client:
                    recorder.record("connection", state="connected", address=device.address, mtu=client.mtu_size)
                    print(f"[{recorder.elapsed():7.2f}s] connected (mtu={client.mtu_size})")
                    services = await snapshot_gatt(client, read_values=not args.no_read, recorder=recorder)
                    recorder.record("gatt", services=services)
                    await _subscribe_all(client, services, only_chars, on_notify, recorder)
                    waiters = [asyncio.create_task(stop.wait()), asyncio.create_task(disconnected.wait())]
                    try:
                        await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
                    finally:
                        for w in waiters:
                            w.cancel()
            except CONNECT_ERRORS as e:
                recorder.record("connection", state="error", address=device.address, detail=f"{type(e).__name__}: {e}")
                print(f"[{recorder.elapsed():7.2f}s] connection error: {type(e).__name__}: {e}")
            by = "peer" if disconnected.is_set() else "client"
            recorder.record("connection", state="disconnected", address=device.address, detail=by)
            print(f"[{recorder.elapsed():7.2f}s] disconnected ({by})")
            if args.once:
                return
            await asyncio.sleep(1.0)

    async def input_loop() -> None:
        lines = start_stdin_reader(loop)
        index = 0
        _announce_phase(recorder, phases, index)
        while True:
            line = await lines.get()
            if line is None or line.strip().lower() == "q":
                stop.set()
                return
            text = line.strip()
            if text:
                ev = recorder.note(text)
                print(f"[{ev['t_rel']:7.2f}s] note recorded in phase '{recorder.phase}': {text}")
            elif index + 1 < len(phases):
                index += 1
                _announce_phase(recorder, phases, index)
            else:
                print("Last phase reached; type q + Enter to finish.")

    print(f"Capture target filter: {target.describe()}  (adv-only={args.adv_only})")
    scanner = BleakScanner(on_adv, cb={"use_bdaddr": args.use_bdaddr})
    await scanner.start()
    tasks = [asyncio.create_task(input_loop())]
    if not args.adv_only:
        tasks.append(asyncio.create_task(connection_loop()))
    try:
        try:
            await asyncio.wait_for(stop.wait(), timeout=args.duration)
        except asyncio.TimeoutError:
            print("Duration reached.")
        stop.set()
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await scanner.stop()


async def _subscribe_all(
    client: BleakClient,
    services: list[dict[str, Any]],
    only_chars: set[str],
    callback: Any,
    recorder: Recorder,
) -> None:
    for s in services:
        for c in s["characteristics"]:
            modes = NOTIFY_PROPS & set(c["properties"])
            if not modes or (only_chars and c["uuid"] not in only_chars):
                continue
            fields = {"char_uuid": c["uuid"], "char_handle": c["handle"], "modes": sorted(modes)}
            try:
                await client.start_notify(c["handle"], callback)
                recorder.record("subscription", state="subscribed", **fields)
                print(f"  subscribed {c['uuid']} h={c['handle']} {sorted(modes)}")
            except CONNECT_ERRORS as e:
                recorder.record("subscription", state="error", detail=f"{type(e).__name__}: {e}", **fields)
                print(f"  subscribe FAILED {c['uuid']}: {e}")


def _announce_phase(recorder: Recorder, phases: list[tuple[str, str]], index: int) -> None:
    name, description = phases[index]
    recorder.set_phase(name, description)
    print(f"\n=== Phase {index + 1}/{len(phases)}: {name} ===\n{description}")
    print("(empty Enter = next phase, text = add note, q = finish)\n")
