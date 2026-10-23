"""Confirmed decode for the SSW526 (Dr Trust USA 526 Legend) weight notification.

Evidence and the full methodology live in docs/protocol-investigation.md ("Confirmed decodes"). In short:
characteristic 0xffb2 streams a fixed 20-byte packet with no write required; byte 3 is a settling/locked
flag and bytes 4-5 are the weight as a big-endian uint16, confirmed against the official app's displayed
weight. Nothing else in the packet is decoded yet (the trailing byte looks like a checksum of some kind;
the algorithm is unconfirmed, so it is reported but not validated).

This module only decodes bytes already proven to mean something. It must not grow a field that analyze.py
hasn't first shown evidence for.
"""

from __future__ import annotations

from dataclasses import dataclass

PACKET_LEN = 20
HEADER = bytes.fromhex("ac2700")
TRAILER = bytes.fromhex("03d5")
WEIGHT_SCALE = 120.0  # raw units per kg
SETTLING_FLAG = 0x68
STABLE_FLAG = 0x69


@dataclass(frozen=True)
class WeightReading:
    weight_kg: float
    stable: bool
    flag: int
    raw: int
    checksum: int


def decode_weight_packet(data: bytes) -> WeightReading | None:
    """Decode one notification payload from 0xffb2, or None if it doesn't match the confirmed shape.

    `None` covers anything not yet understood: wrong length, a different header/trailer, or a settling-flag
    byte other than the two observed values. It is not an error signal — callers should skip unrecognised
    packets rather than raise, since this device may send packet types this module hasn't seen evidence for.
    """
    if len(data) != PACKET_LEN or data[:3] != HEADER or data[17:19] != TRAILER:
        return None
    flag = data[3]
    if flag not in (SETTLING_FLAG, STABLE_FLAG):
        return None
    raw = int.from_bytes(data[4:6], "big")
    return WeightReading(weight_kg=round(raw / WEIGHT_SCALE, 2), stable=flag == STABLE_FLAG, flag=flag, raw=raw, checksum=data[19])
