"""Tests for offline stream analysis. Payloads are synthetic, not scale data."""

import json

import pytest

from cadence_ble.analyze import (
    analyze_stream,
    byte_mask,
    extract_streams,
    format_report,
    stream_keys,
    timeline,
)
from cadence_ble.capture_format import Recorder
from cadence_ble.cli import main


def synthetic_doc():
    r = Recorder("capture")
    r.set_phase("idle")
    r.record("advertisement", address="A", manufacturer_data={"0x0001": "aa00"}, service_data={})
    r.record("advertisement", address="A", manufacturer_data={"0x0001": "aa00"}, service_data={})
    r.set_phase("measuring")
    r.record("connection", state="connected")
    r.record("notification", char_uuid="u1", char_handle=7, hex="10010203")
    r.record("notification", char_uuid="u1", char_handle=7, hex="10010204")
    r.record("notification", char_uuid="u1", char_handle=7, hex="10010204")
    r.note("display 12.3")
    r.record("read", char_uuid="u2", char_handle=3, hex="41")
    r.record("read", char_uuid="u3", char_handle=4, error="denied")
    return r.doc


def test_stream_keys_cover_payload_bearing_events():
    assert stream_keys({"type": "notification", "char_uuid": "u", "char_handle": 1, "hex": "00"}) == [
        ("notify u h=1", "00")
    ]
    keys = stream_keys(
        {"type": "advertisement", "address": "A", "manufacturer_data": {"0x0001": "01"}, "service_data": {"s": "02"}}
    )
    assert keys == [("adv A mfr 0x0001", "01"), ("adv A svcdata s", "02")]
    assert stream_keys({"type": "read", "char_uuid": "u", "error": "x"}) == []
    assert stream_keys({"type": "note", "text": "x"}) == []


def test_byte_mask():
    assert byte_mask([b"\x01\x02\x03", b"\x01\x05\x03"]) == ["01", None, "03"]
    assert byte_mask([]) == []
    with pytest.raises(ValueError):
        byte_mask([b"\x01", b"\x01\x02"])


def test_analyze_stream_dedupes_and_tracks_phases():
    streams = extract_streams([("f", synthetic_doc())])
    r = analyze_stream("notify u1 h=7", streams["notify u1 h=7"])
    assert r.total == 3
    assert [d.hex for d in r.distinct] == ["10010203", "10010204"]
    assert [d.count for d in r.distinct] == [1, 2]
    assert r.distinct[0].phases == ["measuring"]
    assert r.masks == {4: ["10", "01", "02", None]}
    assert "read u3 h=4" not in streams


def test_analyze_stream_handles_mixed_lengths_and_empty_payloads():
    streams = extract_streams(
        [("f", {"events": [
            {"type": "notification", "char_uuid": "u", "char_handle": 1, "hex": h, "t_rel": i, "phase": None}
            for i, h in enumerate(["", "01", "0102", "0103"])
        ]})]
    )
    r = analyze_stream("notify u h=1", streams["notify u h=1"])
    assert len(r.distinct) == 4
    assert list(r.masks) == [2]


def test_timeline_reports_only_changes():
    lines = timeline(synthetic_doc())
    adv_lines = [ln for ln in lines if "adv A mfr" in ln]
    notify_lines = [ln for ln in lines if "notify u1" in ln]
    assert len(adv_lines) == 1
    assert len(notify_lines) == 2
    assert any("NOTE: display 12.3" in ln for ln in lines)


def test_format_report_and_cli_roundtrip(tmp_path, capsys):
    doc = synthetic_doc()
    text = format_report([("f", doc)])
    assert "notify u1 h=7  total=3 distinct=2" in text
    assert "value  10 01 02 ??" in text

    path = tmp_path / "c.json"
    path.write_text(json.dumps(doc))
    assert main(["analyze", str(path), "--stream", "notify"]) == 0
    out = capsys.readouterr().out
    assert "notify u1" in out
    assert "adv A mfr" not in out
