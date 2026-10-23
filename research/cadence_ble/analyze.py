"""`cadence analyze`: offline comparison of captured payload streams.

This module only groups and diffs raw bytes. It deliberately does not
interpret any field; decoding belongs to the later protocol module and must be
justified by evidence gathered here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .capture_format import hex_spaced


@dataclass
class Occurrence:
    t_rel: float
    phase: str | None
    source: str
    hex: str


@dataclass
class DistinctPayload:
    hex: str
    count: int = 0
    first_t_rel: float = 0.0
    phases: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


@dataclass
class StreamReport:
    key: str
    total: int
    distinct: list[DistinctPayload]
    masks: dict[int, list[str | None]]


def stream_keys(event: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (stream key, hex payload) pairs carried by one event."""
    etype = event.get("type")
    if etype == "notification":
        return [(f"notify {event['char_uuid']} h={event.get('char_handle')}", event["hex"])]
    if etype == "read" and "hex" in event:
        return [(f"read {event['char_uuid']} h={event.get('char_handle')}", event["hex"])]
    if etype == "advertisement":
        addr = event.get("address")
        out = [(f"adv {addr} mfr {cid}", hx) for cid, hx in (event.get("manufacturer_data") or {}).items()]
        out += [(f"adv {addr} svcdata {uuid}", hx) for uuid, hx in (event.get("service_data") or {}).items()]
        return out
    return []


def extract_streams(docs: Iterable[tuple[str, dict[str, Any]]]) -> dict[str, list[Occurrence]]:
    streams: dict[str, list[Occurrence]] = {}
    for label, doc in docs:
        for ev in doc.get("events", []):
            for key, hx in stream_keys(ev):
                streams.setdefault(key, []).append(Occurrence(ev["t_rel"], ev.get("phase"), label, hx))
    return streams


def byte_mask(payloads: list[bytes]) -> list[str | None]:
    """Per offset: the constant byte as hex, or None if it varies.

    All payloads must have the same length.
    """
    if not payloads:
        return []
    length = len(payloads[0])
    if any(len(p) != length for p in payloads):
        raise ValueError("payloads must share one length")
    mask: list[str | None] = []
    for i in range(length):
        values = {p[i] for p in payloads}
        mask.append(f"{payloads[0][i]:02x}" if len(values) == 1 else None)
    return mask


def analyze_stream(key: str, occurrences: list[Occurrence]) -> StreamReport:
    by_hex: dict[str, DistinctPayload] = {}
    for occ in occurrences:
        d = by_hex.get(occ.hex)
        if d is None:
            d = by_hex[occ.hex] = DistinctPayload(occ.hex, first_t_rel=occ.t_rel)
        d.count += 1
        if occ.phase and occ.phase not in d.phases:
            d.phases.append(occ.phase)
        if occ.source not in d.sources:
            d.sources.append(occ.source)
    by_len: dict[int, list[bytes]] = {}
    for hx in by_hex:
        data = bytes.fromhex(hx)
        by_len.setdefault(len(data), []).append(data)
    masks = {n: byte_mask(ps) for n, ps in sorted(by_len.items()) if len(ps) > 1}
    return StreamReport(key, len(occurrences), list(by_hex.values()), masks)


def timeline(doc: dict[str, Any]) -> list[str]:
    """Markers, notes, connection changes and payload *changes* in time order."""
    last: dict[str, str] = {}
    lines: list[str] = []
    for ev in doc.get("events", []):
        prefix = f"[{ev['t_rel']:9.3f}] {ev.get('phase') or '-':<15}"
        etype = ev.get("type")
        if etype == "marker":
            lines.append(f"{prefix} === {ev.get('text')}")
        elif etype == "note":
            lines.append(f"{prefix} NOTE: {ev.get('text')}")
        elif etype == "connection":
            detail = f" ({ev['detail']})" if ev.get("detail") else ""
            lines.append(f"{prefix} connection {ev.get('state')}{detail}")
        elif etype == "subscription":
            lines.append(f"{prefix} subscription {ev.get('state')} {ev.get('char_uuid')}")
        for key, hx in stream_keys(ev):
            if last.get(key) != hx:
                last[key] = hx
                lines.append(f"{prefix} {key}: {hex_spaced(hx)}")
    return lines


def format_mask(mask: list[str | None]) -> list[str]:
    offsets = " ".join(f"{i:02d}" for i in range(len(mask)))
    values = " ".join(m if m is not None else "??" for m in mask)
    return [f"offset {offsets}", f"value  {values}"]


def format_report(
    docs: list[tuple[str, dict[str, Any]]],
    stream_filter: str | None = None,
    max_distinct: int = 40,
    show_timeline: bool = True,
) -> str:
    out: list[str] = []
    for label, doc in docs:
        target = doc.get("target") or {}
        out.append(
            f"# {label}: kind={doc.get('kind')} created={doc.get('created_at')}"
            f" target={target.get('address')} name={target.get('name')!r}"
            f" events={len(doc.get('events', []))}"
        )
        if doc.get("notes"):
            out.append(f"  notes: {doc['notes']}")

    streams = extract_streams(docs)
    keys = [k for k in sorted(streams) if not stream_filter or stream_filter.lower() in k.lower()]
    out.append(f"\n## Payload streams ({len(keys)})")
    for key in keys:
        r = analyze_stream(key, streams[key])
        out.append(f"\n-- {key}  total={r.total} distinct={len(r.distinct)}")
        out.append(f"   {'first_t':>9} {'count':>5}  {'len':>3}  phases | hex")
        for d in r.distinct[:max_distinct]:
            src = f"  [{','.join(d.sources)}]" if len(docs) > 1 else ""
            out.append(
                f"   {d.first_t_rel:9.3f} {d.count:5d}  {len(d.hex) // 2:3d}"
                f"  {','.join(d.phases) or '-'} | {hex_spaced(d.hex)}{src}"
            )
        if len(r.distinct) > max_distinct:
            out.append(f"   ... {len(r.distinct) - max_distinct} more distinct payloads")
        for length, mask in r.masks.items():
            out.append(f"   byte mask for len={length} (?? = varies across distinct payloads):")
            out.extend("     " + line for line in format_mask(mask))

    if show_timeline:
        for label, doc in docs:
            lines = timeline(doc)
            if stream_filter:
                lines = [
                    ln for ln in lines
                    if stream_filter.lower() in ln.lower() or " === " in ln or " NOTE: " in ln
                ]
            out.append(f"\n## Timeline (changes only): {label}")
            out.extend(lines)
    return "\n".join(out) + "\n"
