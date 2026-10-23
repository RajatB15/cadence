"""Versioned JSON capture format shared by all research tools.

A capture document looks like::

    {
      "format": "cadence-capture",
      "schema_version": 1,
      "kind": "scan" | "inspect" | "capture",
      "created_at": "2026-10-22T12:00:00.000000Z",
      "tool": {...},            # versions of this tool, bleak, python, OS
      "command": [...],         # argv used to produce the file
      "notes": "...",
      "target": {...} | null,   # locked target device, if any
      "gatt": [...] | null,     # GATT snapshot (inspect only)
      "events": [ {...}, ... ]  # chronological, see Recorder.record
    }

Every event carries ``seq``, ``t`` (UTC wall clock, ISO 8601), ``t_rel``
(monotonic seconds since the recorder started), ``phase`` and ``type``.
Raw bytes are always stored as lowercase hex without separators.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import __version__

FORMAT_NAME = "cadence-capture"
# Captures recorded before the project was renamed from WeighIn.
LEGACY_FORMAT_NAMES = ("weighin-capture",)
SCHEMA_VERSION = 1

EVENT_TYPES = (
    "advertisement",
    "notification",
    "read",
    "gatt",
    "subscription",
    "connection",
    "marker",
    "note",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def company_key(company_id: int) -> str:
    return f"0x{company_id:04x}"


def adv_to_dict(address: str, name: str | None, adv: Any) -> dict[str, Any]:
    """Convert a Bleak ``AdvertisementData`` (or look-alike) to JSON-safe fields.

    ``platform_data`` is deliberately dropped: on macOS it holds CoreBluetooth
    objects that are not serialisable and carry no extra payload bytes.
    """
    return {
        "address": address,
        "name": name,
        "local_name": adv.local_name,
        "rssi": adv.rssi,
        "tx_power": adv.tx_power,
        "service_uuids": sorted(set(adv.service_uuids or [])),
        "manufacturer_data": {
            company_key(cid): bytes(data).hex()
            for cid, data in sorted((adv.manufacturer_data or {}).items())
        },
        "service_data": {
            uuid: bytes(data).hex() for uuid, data in sorted((adv.service_data or {}).items())
        },
    }


def adv_fingerprint(fields: Mapping[str, Any]) -> tuple:
    """Content of an advertisement excluding volatile RSSI, for change detection."""
    return (
        fields.get("local_name"),
        fields.get("tx_power"),
        tuple(fields.get("service_uuids") or ()),
        tuple(sorted((fields.get("manufacturer_data") or {}).items())),
        tuple(sorted((fields.get("service_data") or {}).items())),
    )


def tool_info() -> dict[str, Any]:
    from importlib.metadata import PackageNotFoundError, version

    try:
        bleak_version = version("bleak")
    except PackageNotFoundError:
        bleak_version = None
    return {
        "name": "cadence_ble",
        "version": __version__,
        "bleak": bleak_version,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }


class Recorder:
    """Accumulates timestamped events and writes a capture document."""

    def __init__(self, kind: str, command: Iterable[str] | None = None, notes: str | None = None):
        self._t0 = time.monotonic()
        self.phase: str | None = None
        self.doc: dict[str, Any] = {
            "format": FORMAT_NAME,
            "schema_version": SCHEMA_VERSION,
            "kind": kind,
            "created_at": utc_now_iso(),
            "tool": tool_info(),
            "command": list(command or []),
            "notes": notes,
            "target": None,
            "gatt": None,
            "events": [],
        }

    @property
    def events(self) -> list[dict[str, Any]]:
        return self.doc["events"]

    def elapsed(self) -> float:
        return time.monotonic() - self._t0

    def record(self, type_: str, **fields: Any) -> dict[str, Any]:
        if type_ not in EVENT_TYPES:
            raise ValueError(f"unknown event type {type_!r}")
        event = {
            "seq": len(self.events),
            "t": utc_now_iso(),
            "t_rel": round(self.elapsed(), 6),
            "phase": self.phase,
            "type": type_,
            **fields,
        }
        self.events.append(event)
        return event

    def set_phase(self, phase: str, description: str | None = None) -> dict[str, Any]:
        self.phase = phase
        return self.record("marker", text=description or phase)

    def note(self, text: str) -> dict[str, Any]:
        return self.record("note", text=text)

    def save(self, path: str | os.PathLike[str]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.doc, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
        return path


def load_capture(path: str | os.PathLike[str]) -> dict[str, Any]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("format") not in (FORMAT_NAME, *LEGACY_FORMAT_NAMES):
        raise ValueError(f"{path}: not a {FORMAT_NAME} file")
    version = doc.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(f"{path}: unsupported schema_version {version!r}")
    return doc


def default_output_path(kind: str, directory: str = "captures") -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path(directory) / f"{kind}-{stamp}.json"


def hex_spaced(hex_str: str) -> str:
    return " ".join(hex_str[i : i + 2] for i in range(0, len(hex_str), 2))


def printable_ascii(data: bytes) -> str | None:
    """Return ``data`` as text if every byte is printable ASCII, else None."""
    if data and all(0x20 <= b < 0x7F for b in data):
        return data.decode("ascii")
    return None
