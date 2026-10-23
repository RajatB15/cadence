"""BLE scale bridge: a background listener that turns confirmed SSW526 weight readings into the vault.

Platform- and opt-in-gated. `available()` is true only when the `cadence_ble` research package (and bleak)
are importable — install it alongside this backend with `pip install -e '.[test]' -e ../../research` to
turn this on; the backend runs and is fully tested without it (nothing here is a hard dependency). Even
when available, nothing connects until the user turns it on in Settings (`enabled()`); unlike weather this
needs real hardware present, so it defaults to off.

Decoding is never reimplemented here — it's imported from `cadence_ble.ssw526`, the tested module that
docs/protocol-investigation.md documents the evidence for. Only weight is confirmed; body composition is
not transmitted by this scale and is never stored from it (see that doc's "Confirmed decodes" section).

The listener owns a dedicated thread with its own asyncio loop (bleak is async-native, but this mirrors the
existing Scheduler/AnalysisWorker thread pattern, keeping it off the main request loop and inert unless
started) and writes through the normal `write_batch` upsert, so reconnects or repeated notifications of an
already-accepted reading can never duplicate a row.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable

from sqlalchemy.orm import sessionmaker

from cadence_app.importer import Batch, WeightRecord, ensure_source, write_batch
from cadence_app.models import AppSetting

log = logging.getLogger(__name__)

SOURCE_ID = "scale"
SOURCE_NAME = "Bluetooth scale"
ENABLED_KEY = "scale_enabled"
STABLE_REPEATS = 3  # consecutive identical *locked* raw values required before accepting a reading
ACCEPT_COOLDOWN_S = 60.0  # one physical weigh-in shouldn't produce two rows this close together
SCAN_RETRY_S = 5.0
RECONNECT_DELAY_S = 1.0


def available() -> bool:
    try:
        import bleak  # noqa: F401
        import cadence_ble.ssw526  # noqa: F401
    except ImportError:
        return False
    return True


def enabled(session) -> bool:
    row = session.get(AppSetting, ENABLED_KEY)
    return row is not None and row.value == "1"


def set_enabled(session, on: bool) -> None:
    row = session.get(AppSetting, ENABLED_KEY)
    if row:
        row.value = "1" if on else "0"
    else:
        session.add(AppSetting(key=ENABLED_KEY, value="1" if on else "0"))
    session.commit()


# ---- debounce: a stream of packets -> at most one accepted reading per weigh-in -----------------------


class Debouncer:
    """Requires N consecutive identical locked readings, then a cooldown, before accepting one."""

    def __init__(self, stable_repeats: int = STABLE_REPEATS, cooldown_s: float = ACCEPT_COOLDOWN_S):
        self.stable_repeats, self.cooldown_s = stable_repeats, cooldown_s
        self._run_raw: int | None = None
        self._run_len = 0
        self._last_accept_t: float | None = None

    def offer(self, reading, now_s: float):
        """Feed one decoded `ssw526.WeightReading`; returns it if this packet completes an acceptance."""
        if not reading.stable:
            self._run_raw, self._run_len = None, 0
            return None
        if reading.raw == self._run_raw:
            self._run_len += 1
        else:
            self._run_raw, self._run_len = reading.raw, 1
        if self._run_len < self.stable_repeats:
            return None
        if self._last_accept_t is not None and now_s - self._last_accept_t < self.cooldown_s:
            return None
        self._last_accept_t = now_s
        return reading


def default_now_local() -> datetime:
    """Local time with its UTC offset attached, so the formula below never silently falls back to UTC."""
    return datetime.now().astimezone()


def _local_tz_label(local: datetime) -> str:
    """'UTC+05:30'-style label, matching the convention used for Garmin activity timezones elsewhere."""
    offset = local.utcoffset() or timedelta(0)
    sign = "+" if offset >= timedelta(0) else "-"
    minutes = int(abs(offset).total_seconds() // 60)
    return f"UTC{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def build_record(reading, accepted_at_local: datetime) -> WeightRecord:
    """A weight-only record: this scale confirms no other field, so everything else stays None.

    `accepted_at_local` must be timezone-aware (e.g. from `default_now_local()`), since both the stored
    local day and the UTC instant depend on knowing the actual offset.
    """
    return WeightRecord(
        source_record_id=f"ssw526:{int(accepted_at_local.timestamp())}",
        measured_at_utc=accepted_at_local.astimezone(UTC).replace(tzinfo=None),
        timezone=_local_tz_label(accepted_at_local),
        local_date=accepted_at_local.date(),
        weight_kg=reading.weight_kg,
        body_fat_pct=None,
    )


@dataclass
class LastReading:
    weight_kg: float
    local_date: str
    accepted_at: str


@dataclass
class LiveReading:
    """Every decoded packet, not just accepted ones — for a UI that shows the number settling in real time."""

    weight_kg: float
    stable: bool
    seen_at: str


# ---- the background listener ------------------------------------------------------------------------


class ScaleListener:
    def __init__(self, factory: sessionmaker, now_local: Callable[[], datetime] = default_now_local):
        self.factory, self.now_local = factory, now_local
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.connected = False
        self.last_reading: LastReading | None = None
        self.live: LiveReading | None = None
        self.last_error: str | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running or not available():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="scale-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        import asyncio  # local: keeps this module importable with no event loop running, and without bleak

        try:
            asyncio.run(self._loop())
        except Exception:  # pylint: disable=broad-exception-caught  # background thread boundary
            log.exception("Scale listener stopped unexpectedly")
        finally:
            self.connected = False

    def _accept(self, reading) -> None:
        now = self.now_local()
        record = build_record(reading, now)
        with self.factory() as session, session.begin():
            ensure_source(session, SOURCE_ID, SOURCE_NAME, "scale")
            write_batch(session, SOURCE_ID, Batch(weights=[record]), record.measured_at_utc)
        self.last_reading = LastReading(reading.weight_kg, record.local_date.isoformat(), now.isoformat())
        log.info("Accepted a scale reading: %.2f kg", reading.weight_kg)

    async def _loop(self) -> None:
        # Imported lazily: this module (and the rest of the backend) must import cleanly without bleak or
        # the research package installed at all.
        import asyncio

        from bleak import BleakClient, BleakScanner
        from bleak.exc import BleakError
        from cadence_ble import ssw526
        from cadence_ble.filters import TargetFilter

        # Matched by what the device actually advertises (name, manufacturer id) — its GATT service UUID
        # (0xffb0) is confirmed by `cadence inspect` but isn't present in the advertisement itself, so it
        # can't be used to filter scan results.
        target = TargetFilter(name=ssw526.DEVICE_NAME, company_id=ssw526.MANUFACTURER_COMPANY_ID)
        connect_errors = (BleakError, asyncio.TimeoutError, OSError)
        debouncer = Debouncer()
        loop = asyncio.get_running_loop()

        locked: dict = {"device": None}
        found = asyncio.Event()

        def on_adv(device, adv) -> None:
            if locked["device"] is not None:
                return  # already found one this cycle; ignore other devices until we reconnect
            if not target.matches(device.address, device.name, adv):
                return
            locked["device"] = device
            found.set()

        def on_notify(_char, data: bytearray) -> None:
            reading = ssw526.decode_weight_packet(bytes(data))
            if reading is None:
                return
            self.live = LiveReading(reading.weight_kg, reading.stable, self.now_local().isoformat())
            accepted = debouncer.offer(reading, loop.time())
            if accepted is not None:
                self._accept(accepted)

        scanner = BleakScanner(on_adv)
        await scanner.start()
        try:
            while not self._stop.is_set():
                found.clear()
                locked["device"] = None
                self.live = None
                try:
                    await asyncio.wait_for(found.wait(), timeout=SCAN_RETRY_S)
                except asyncio.TimeoutError:
                    continue
                device = locked["device"]
                disconnected = asyncio.Event()

                def on_disconnect(_client) -> None:
                    loop.call_soon_threadsafe(disconnected.set)

                try:
                    async with BleakClient(device, disconnected_callback=on_disconnect) as client:
                        self.connected, self.last_error = True, None
                        await client.start_notify(ssw526.NOTIFY_CHAR_UUID, on_notify)
                        waiters = [asyncio.create_task(self._wait_stop()), asyncio.create_task(disconnected.wait())]
                        try:
                            await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
                        finally:
                            for w in waiters:
                                w.cancel()
                except connect_errors as exc:
                    self.last_error = f"{type(exc).__name__}: {exc}"
                finally:
                    self.connected = False
                if self._stop.is_set():
                    break
                await asyncio.sleep(RECONNECT_DELAY_S)
        finally:
            await scanner.stop()

    async def _wait_stop(self) -> None:
        import asyncio

        while not self._stop.is_set():
            await asyncio.sleep(0.2)
