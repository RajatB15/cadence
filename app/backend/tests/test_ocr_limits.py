import asyncio
import io
import threading
import time

import pytest

from cadence_app import ocr


def test_declared_length_over_cap_is_refused_before_reading():
    async def chunks():
        raise AssertionError("body must not be read")
        yield b""

    with pytest.raises(ocr.UploadError) as err:
        asyncio.run(ocr.read_upload(chunks(), str(ocr.MAX_IMAGE_BYTES + 1)))
    assert err.value.status == 413


def test_streaming_cap_applies_without_content_length():
    async def chunks():
        for _ in range(4):
            yield b"x" * (ocr.MAX_IMAGE_BYTES // 3)

    with pytest.raises(ocr.UploadError) as err:
        asyncio.run(ocr.read_upload(chunks(), None))
    assert err.value.status == 413


def test_small_and_empty_bodies():
    async def one():
        yield b"abc"

    async def none():
        return
        yield b""

    assert asyncio.run(ocr.read_upload(one(), "3")) == b"abc"
    with pytest.raises(ocr.UploadError):
        asyncio.run(ocr.read_upload(none(), None))
    with pytest.raises(ocr.UploadError) as err:
        asyncio.run(ocr.read_upload(one(), "nope"))
    assert err.value.status == 400


def _png(width, height):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("L", (width, height), 255).save(buf, "PNG")
    return buf.getvalue()


def test_huge_pixel_count_is_refused_without_decoding():
    data = _png(9000, 9000)  # 81 MP of white compresses to a tiny file
    assert len(data) < ocr.MAX_IMAGE_BYTES
    with pytest.raises(ValueError, match="too large"):
        ocr._upright(data)  # pylint: disable=protected-access


def test_decompression_bomb_error_becomes_value_error(monkeypatch):
    from PIL import Image

    def boom(*_a, **_k):
        raise Image.DecompressionBombError("bomb")

    monkeypatch.setattr(Image, "open", boom)
    with pytest.raises(ValueError, match="too large"):
        ocr._upright(b"x")  # pylint: disable=protected-access


def test_only_one_recognition_runs_at_a_time(monkeypatch):
    running, peak, lock = 0, 0, threading.Lock()

    def slow(_data):
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.05)
        with lock:
            running -= 1
        return "ok"

    monkeypatch.setattr(ocr, "_tesseract_text", slow)
    results = []
    threads = [threading.Thread(target=lambda: results.append(ocr.image_text(b""))) for _ in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results == ["ok"] * 3 and peak == 1


def test_queue_is_bounded(monkeypatch):
    monkeypatch.setattr(ocr, "_pending", ocr.MAX_WAITING + 1)
    with pytest.raises(ocr.Busy):
        ocr.image_text(b"")
