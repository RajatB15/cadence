"""GATT enumeration (`cadence inspect`) and the shared snapshot helper."""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakError

from .capture_format import Recorder, adv_to_dict, printable_ascii
from .filters import TargetFilter, normalize_uuid

READ_ERRORS = (BleakError, asyncio.TimeoutError, OSError)

NOTIFY_PROPS = {"notify", "indicate"}
WRITE_PROPS = {"write", "write-without-response", "authenticated-signed-writes"}

# Bluetooth SIG assigned numbers, used only to report whether they are present.
STANDARD_SERVICES = {
    normalize_uuid("181d"): "Weight Scale Service",
    normalize_uuid("181b"): "Body Composition Service",
    normalize_uuid("181c"): "User Data Service",
    normalize_uuid("180a"): "Device Information Service",
    normalize_uuid("180f"): "Battery Service",
}


def _value_fields(data: bytes) -> dict[str, Any]:
    fields: dict[str, Any] = {"value_hex": bytes(data).hex()}
    text = printable_ascii(bytes(data))
    if text is not None:
        fields["value_ascii"] = text
    return fields


async def snapshot_gatt(
    client: BleakClient,
    *,
    read_values: bool = True,
    read_timeout: float = 5.0,
    recorder: Recorder | None = None,
) -> list[dict[str, Any]]:
    """Enumerate services/characteristics/descriptors, optionally reading values.

    Read results (and errors) are also emitted as ``read`` events when a
    recorder is given, so they are timestamped like every other payload.
    """
    services: list[dict[str, Any]] = []
    for service in client.services:
        s: dict[str, Any] = {
            "uuid": service.uuid,
            "handle": service.handle,
            "description": service.description,
            "characteristics": [],
        }
        for char in service.characteristics:
            c: dict[str, Any] = {
                "uuid": char.uuid,
                "handle": char.handle,
                "description": char.description,
                "properties": sorted(char.properties),
                "descriptors": [],
            }
            if read_values and "read" in char.properties:
                event: dict[str, Any] = {
                    "char_uuid": char.uuid,
                    "char_handle": char.handle,
                    "service_uuid": service.uuid,
                }
                try:
                    data = await asyncio.wait_for(client.read_gatt_char(char), read_timeout)
                    c.update(_value_fields(data))
                    event["hex"] = bytes(data).hex()
                except READ_ERRORS as e:
                    c["read_error"] = event["error"] = f"{type(e).__name__}: {e}"
                if recorder:
                    recorder.record("read", **event)
            for desc in char.descriptors:
                d: dict[str, Any] = {
                    "uuid": desc.uuid,
                    "handle": desc.handle,
                    "description": desc.description,
                }
                if read_values:
                    try:
                        data = await asyncio.wait_for(client.read_gatt_descriptor(desc), read_timeout)
                        d.update(_value_fields(data))
                    except READ_ERRORS as e:
                        d["read_error"] = f"{type(e).__name__}: {e}"
                c["descriptors"].append(d)
            s["characteristics"].append(c)
        services.append(s)
    return services


def gatt_overview(services: list[dict[str, Any]]) -> dict[str, Any]:
    chars = [(s, c) for s in services for c in s["characteristics"]]
    return {
        "standard_services_present": sorted(
            STANDARD_SERVICES[s["uuid"]] for s in services if s["uuid"] in STANDARD_SERVICES
        ),
        "readable": [c["uuid"] for _, c in chars if "read" in c["properties"]],
        "writable": [c["uuid"] for _, c in chars if WRITE_PROPS & set(c["properties"])],
        "notifiable": [c["uuid"] for _, c in chars if NOTIFY_PROPS & set(c["properties"])],
    }


def print_gatt(services: list[dict[str, Any]]) -> None:
    for s in services:
        print(f"\nService {s['uuid']}  ({s['description']})  handle={s['handle']}")
        for c in s["characteristics"]:
            props = ",".join(c["properties"])
            print(f"  Char {c['uuid']}  ({c['description']})  handle={c['handle']}  [{props}]")
            if "value_hex" in c:
                text = f"  ascii={c['value_ascii']!r}" if "value_ascii" in c else ""
                print(f"      value={c['value_hex'] or '(empty)'}{text}")
            elif "read_error" in c:
                print(f"      read error: {c['read_error']}")
            for d in c["descriptors"]:
                val = d.get("value_hex", d.get("read_error", ""))
                print(f"      Desc {d['uuid']}  ({d['description']})  handle={d['handle']}  {val}")
    o = gatt_overview(services)
    print("\nStandard SIG services present:", ", ".join(o["standard_services_present"]) or "none")
    print("Notify/indicate characteristics:", ", ".join(o["notifiable"]) or "none")
    print("Writable characteristics:", ", ".join(o["writable"]) or "none")


async def find_target(
    target: TargetFilter, timeout: float, use_bdaddr: bool
) -> tuple[BLEDevice, AdvertisementData] | None:
    found: asyncio.Future[tuple[BLEDevice, AdvertisementData]] = (
        asyncio.get_running_loop().create_future()
    )

    def on_adv(device: BLEDevice, adv: AdvertisementData) -> None:
        if not found.done() and target.matches(device.address, device.name, adv):
            found.set_result((device, adv))

    async with BleakScanner(on_adv, cb={"use_bdaddr": use_bdaddr}):
        try:
            return await asyncio.wait_for(found, timeout)
        except asyncio.TimeoutError:
            return None


async def run_inspect(args: argparse.Namespace, recorder: Recorder) -> None:
    target = TargetFilter.from_args(args)
    print(f"Waiting up to {args.scan_timeout:.0f}s for a device matching {target.describe()}")
    print("Wake the scale now (step on it) if it is not advertising.")
    result = await find_target(target, args.scan_timeout, args.use_bdaddr)
    if result is None:
        recorder.record("connection", state="not_found", detail=target.describe())
        raise SystemExit("No matching device found.")
    device, adv = result
    fields = adv_to_dict(device.address, device.name, adv)
    recorder.record("advertisement", **fields)
    recorder.doc["target"] = {"address": device.address, "name": device.name}
    print(f"Found {device.address} name={device.name!r} rssi={adv.rssi}; connecting...")

    recorder.record("connection", state="connecting", address=device.address)
    async with BleakClient(device, timeout=args.connect_timeout) as client:
        recorder.record("connection", state="connected", address=device.address, mtu=client.mtu_size)
        services = await snapshot_gatt(client, read_values=not args.no_read, recorder=recorder)
    recorder.record("connection", state="disconnected", address=device.address, detail="by client")
    recorder.doc["gatt"] = services
    recorder.doc["summary"] = gatt_overview(services)
    print_gatt(services)
