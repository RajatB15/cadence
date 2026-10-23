"""Tests for the capture format. All payloads here are synthetic, not scale data."""

import json
from types import SimpleNamespace

import pytest

from cadence_ble.capture_format import (
    SCHEMA_VERSION,
    Recorder,
    adv_fingerprint,
    adv_to_dict,
    hex_spaced,
    load_capture,
    printable_ascii,
)


def fake_adv(**kw):
    base = dict(local_name=None, manufacturer_data={}, service_data={}, service_uuids=[], tx_power=None, rssi=-60)
    base.update(kw)
    return SimpleNamespace(**base)


def test_adv_to_dict_hex_encodes_and_sorts():
    adv = fake_adv(
        local_name="X",
        manufacturer_data={0x0157: b"\x01\xab", 0x0001: bytearray(b"\xff")},
        service_data={"0000181d-0000-1000-8000-00805f9b34fb": b"\x00"},
        service_uuids=["b", "a", "b"],
    )
    d = adv_to_dict("ADDR", "dev", adv)
    assert d["manufacturer_data"] == {"0x0001": "ff", "0x0157": "01ab"}
    assert d["service_data"] == {"0000181d-0000-1000-8000-00805f9b34fb": "00"}
    assert d["service_uuids"] == ["a", "b"]
    json.dumps(d)


def test_fingerprint_ignores_rssi_but_not_payload():
    a = adv_to_dict("A", None, fake_adv(rssi=-50, manufacturer_data={1: b"\x01"}))
    b = adv_to_dict("A", None, fake_adv(rssi=-90, manufacturer_data={1: b"\x01"}))
    c = adv_to_dict("A", None, fake_adv(rssi=-50, manufacturer_data={1: b"\x02"}))
    assert adv_fingerprint(a) == adv_fingerprint(b)
    assert adv_fingerprint(a) != adv_fingerprint(c)


def test_recorder_events_are_ordered_and_phased(tmp_path):
    r = Recorder("capture", command=["cadence", "capture"], notes="n")
    r.record("connection", state="connecting")
    r.set_phase("awake", "woke")
    r.record("notification", char_uuid="u", char_handle=1, hex="0102")
    r.note("display 0.0 kg")
    seqs = [e["seq"] for e in r.events]
    assert seqs == [0, 1, 2, 3]
    assert r.events[0]["phase"] is None
    assert [e["phase"] for e in r.events[1:]] == ["awake"] * 3
    assert all(e["t"].endswith("Z") for e in r.events)
    assert r.events == sorted(r.events, key=lambda e: e["t_rel"])

    path = r.save(tmp_path / "sub" / "c.json")
    doc = load_capture(path)
    assert doc["schema_version"] == SCHEMA_VERSION
    assert doc["events"][2]["hex"] == "0102"
    assert not (tmp_path / "sub" / "c.json.tmp").exists()


def test_recorder_rejects_unknown_event_type():
    with pytest.raises(ValueError):
        Recorder("scan").record("bogus")


@pytest.mark.parametrize(
    "doc",
    [{"format": "other", "schema_version": 1}, {"format": "cadence-capture", "schema_version": 999}],
)
def test_load_capture_rejects_foreign_or_future_files(tmp_path, doc):
    p = tmp_path / "x.json"
    p.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        load_capture(p)


def test_load_capture_accepts_pre_rename_files(tmp_path):
    p = tmp_path / "old.json"
    p.write_text(json.dumps({"format": "weighin-capture", "schema_version": 1, "events": []}))
    assert load_capture(p)["format"] == "weighin-capture"


def test_helpers():
    assert hex_spaced("a1b2c3") == "a1 b2 c3"
    assert hex_spaced("") == ""
    assert printable_ascii(b"Scale v1") == "Scale v1"
    assert printable_ascii(b"\x00ab") is None
    assert printable_ascii(b"") is None
