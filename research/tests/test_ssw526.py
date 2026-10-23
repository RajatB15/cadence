import pytest

from cadence_ble.ssw526 import SETTLING_FLAG, STABLE_FLAG, decode_weight_packet


def packet(flag: int, raw: int, checksum: int = 0x00) -> bytes:
    """Build a synthetic (not captured) packet matching the confirmed shape, for testing the decoder only."""
    return bytes([0xAC, 0x27, 0x00, flag, (raw >> 8) & 0xFF, raw & 0xFF]) + bytes(11) + bytes([0x03, 0xD5, checksum])


@pytest.mark.parametrize("weight_kg,raw", [(72.4, 8688), (55.0, 6600), (100.0, 12000)])
def test_decodes_a_locked_weight_exactly(weight_kg, raw):
    r = decode_weight_packet(packet(STABLE_FLAG, raw))
    assert r is not None
    assert r.weight_kg == weight_kg and r.stable and r.flag == STABLE_FLAG and r.raw == raw


def test_settling_flag_decodes_as_unstable():
    r = decode_weight_packet(packet(SETTLING_FLAG, 5000))
    assert r is not None and not r.stable and r.weight_kg == round(5000 / 120, 2)


def test_zero_weight_still_decodes_the_decoder_does_not_filter_it():
    r = decode_weight_packet(packet(SETTLING_FLAG, 0))
    assert r is not None and r.weight_kg == 0.0


def test_rounds_to_two_decimal_places():
    r = decode_weight_packet(packet(STABLE_FLAG, 8689))  # 8689 / 120 = 72.4083...
    assert r is not None and r.weight_kg == 72.41


def test_checksum_is_reported_but_not_validated():
    r = decode_weight_packet(packet(STABLE_FLAG, 8688, checksum=0x99))
    assert r is not None and r.checksum == 0x99  # any trailing byte is accepted; the algorithm is unconfirmed


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p[:-1],  # too short
        lambda p: p + b"\x00",  # too long
        lambda p: b"\xff" + p[1:],  # wrong header
        lambda p: p[:17] + b"\x00\x00" + p[19:],  # wrong trailer
        lambda p: p[:3] + b"\x00" + p[4:],  # unrecognised flag byte
    ],
)
def test_rejects_anything_not_matching_the_confirmed_shape(mutate):
    assert decode_weight_packet(mutate(packet(STABLE_FLAG, 8688))) is None
