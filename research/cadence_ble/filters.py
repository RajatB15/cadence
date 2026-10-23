"""Target-device selection shared by scan, inspect and capture."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

BASE_UUID_SUFFIX = "-0000-1000-8000-00805f9b34fb"


def normalize_uuid(value: str) -> str:
    """Expand 16/32-bit SIG short UUIDs to 128-bit lowercase form."""
    v = value.strip().lower()
    if v.startswith("0x"):
        v = v[2:]
    if len(v) == 4:
        return f"0000{v}{BASE_UUID_SUFFIX}"
    if len(v) == 8:
        return f"{v}{BASE_UUID_SUFFIX}"
    return v


def parse_company_id(value: str) -> int:
    return int(value, 0)


@dataclass
class TargetFilter:
    address: str | None = None
    name: str | None = None
    service_uuid: str | None = None
    company_id: int | None = None
    min_rssi: int | None = None

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "TargetFilter":
        return cls(
            address=args.address,
            name=args.name,
            service_uuid=normalize_uuid(args.service_uuid) if args.service_uuid else None,
            company_id=args.company_id,
            min_rssi=args.min_rssi,
        )

    def is_empty(self) -> bool:
        return not any(
            v is not None
            for v in (self.address, self.name, self.service_uuid, self.company_id, self.min_rssi)
        )

    def matches(self, address: str, name: str | None, adv: Any) -> bool:
        """All configured criteria must match (logical AND)."""
        if self.address and address.lower() != self.address.lower():
            return False
        if self.name:
            names = [n for n in (name, adv.local_name) if n]
            if not any(self.name.lower() in n.lower() for n in names):
                return False
        if self.service_uuid:
            uuids = {u.lower() for u in (adv.service_uuids or [])}
            uuids |= {u.lower() for u in (adv.service_data or {})}
            if self.service_uuid not in uuids:
                return False
        if self.company_id is not None and self.company_id not in (adv.manufacturer_data or {}):
            return False
        if self.min_rssi is not None and (adv.rssi is None or adv.rssi < self.min_rssi):
            return False
        return True

    def describe(self) -> str:
        parts = []
        if self.address:
            parts.append(f"address={self.address}")
        if self.name:
            parts.append(f"name~{self.name!r}")
        if self.service_uuid:
            parts.append(f"service={self.service_uuid}")
        if self.company_id is not None:
            parts.append(f"company=0x{self.company_id:04x}")
        if self.min_rssi is not None:
            parts.append(f"rssi>={self.min_rssi}")
        return ", ".join(parts) or "(any device)"


def add_filter_arguments(parser: argparse.ArgumentParser) -> None:
    g = parser.add_argument_group("target selection (criteria are AND-ed)")
    g.add_argument("--address", help="exact device address (a CoreBluetooth UUID on macOS)")
    g.add_argument("--name", help="case-insensitive substring of the advertised name")
    g.add_argument("--service-uuid", help="advertised service UUID (16-bit short form allowed)")
    g.add_argument(
        "--company-id", type=parse_company_id, help="manufacturer-data company ID, e.g. 0x0157"
    )
    g.add_argument("--min-rssi", type=int, help="ignore devices weaker than this RSSI (dBm)")
