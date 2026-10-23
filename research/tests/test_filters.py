from types import SimpleNamespace

import pytest

from cadence_ble.filters import TargetFilter, normalize_uuid


def adv(**kw):
    base = dict(local_name=None, manufacturer_data={}, service_data={}, service_uuids=[], rssi=-60)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("181D", "0000181d-0000-1000-8000-00805f9b34fb"),
        ("0x181d", "0000181d-0000-1000-8000-00805f9b34fb"),
        ("0000181d", "0000181d-0000-1000-8000-00805f9b34fb"),
        ("ABCDEF01-0000-1000-8000-00805F9B34FB", "abcdef01-0000-1000-8000-00805f9b34fb"),
    ],
)
def test_normalize_uuid(raw, expected):
    assert normalize_uuid(raw) == expected


def test_empty_filter_matches_everything():
    f = TargetFilter()
    assert f.is_empty()
    assert f.matches("A", None, adv())


def test_name_matches_device_or_local_name_case_insensitive():
    f = TargetFilter(name="scale")
    assert f.matches("A", "My SCALE", adv())
    assert f.matches("A", None, adv(local_name="scale-01"))
    assert not f.matches("A", "Phone", adv(local_name=None))


def test_criteria_are_anded():
    f = TargetFilter(address="aa-bb", company_id=0x1234, min_rssi=-70)
    good = adv(manufacturer_data={0x1234: b""}, rssi=-50)
    assert f.matches("AA-BB", None, good)
    assert not f.matches("CC", None, good)
    assert not f.matches("AA-BB", None, adv(manufacturer_data={0x9999: b""}, rssi=-50))
    assert not f.matches("AA-BB", None, adv(manufacturer_data={0x1234: b""}, rssi=-80))
    assert not f.matches("AA-BB", None, adv(manufacturer_data={0x1234: b""}, rssi=None))


def test_service_uuid_matches_advertised_or_service_data():
    u = normalize_uuid("181d")
    f = TargetFilter(service_uuid=u)
    assert f.matches("A", None, adv(service_uuids=[u]))
    assert f.matches("A", None, adv(service_data={u: b"\x00"}))
    assert not f.matches("A", None, adv())
