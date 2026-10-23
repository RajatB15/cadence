"""Command-line entry point: `cadence {scan,inspect,capture,analyze}`."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Callable, Coroutine

from .capture_format import Recorder, default_output_path, load_capture
from .filters import add_filter_arguments


def _add_common_ble(p: argparse.ArgumentParser) -> None:
    p.add_argument("-o", "--output", type=Path, help="capture JSON path (default: captures/<kind>-<time>.json)")
    p.add_argument("--notes", help="free-text notes stored in the capture (scale state, person, etc.)")
    p.add_argument(
        "--use-bdaddr",
        action="store_true",
        help="macOS: report real Bluetooth addresses via an undocumented API instead of CoreBluetooth UUIDs",
    )
    add_filter_arguments(p)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cadence", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scan", help="log BLE advertisements and find devices that appear when the scale wakes")
    _add_common_ble(p)
    p.add_argument("-d", "--duration", type=float, default=30.0, help="scan seconds (default 30)")
    p.add_argument("-i", "--interactive", action="store_true", help="press Enter to mark the moment you wake the scale")
    p.add_argument("--all-events", action="store_true", help="record every advertisement, not just changes + 1/s")
    p.add_argument("-v", "--verbose", action="store_true", help="print advertisement changes for all devices")

    p = sub.add_parser("inspect", help="connect and enumerate GATT services, characteristics and descriptors")
    _add_common_ble(p)
    p.add_argument("--scan-timeout", type=float, default=30.0)
    p.add_argument("--connect-timeout", type=float, default=20.0)
    p.add_argument("--no-read", action="store_true", help="do not read characteristic/descriptor values")

    p = sub.add_parser("capture", help="phase-guided capture of advertisements and notifications")
    _add_common_ble(p)
    p.add_argument("-d", "--duration", type=float, help="stop after N seconds (default: until q)")
    p.add_argument("--connect-timeout", type=float, default=20.0)
    p.add_argument("--adv-only", action="store_true", help="never connect; record advertisements only")
    p.add_argument("--once", action="store_true", help="do not reconnect after the first disconnect")
    p.add_argument("--no-read", action="store_true", help="skip reading readable characteristics on connect")
    p.add_argument("--char", action="append", help="only subscribe to this characteristic UUID (repeatable)")
    p.add_argument("--phases", help="comma-separated custom phase names instead of the default scenario")

    p = sub.add_parser("analyze", help="group, diff and time-line payloads from capture files")
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--stream", help="only streams whose key contains this substring")
    p.add_argument("--max-distinct", type=int, default=40)
    p.add_argument("--no-timeline", action="store_true")
    return parser


def _run_ble(
    kind: str,
    args: argparse.Namespace,
    runner: Callable[[argparse.Namespace, Recorder], Coroutine[Any, Any, None]],
) -> int:
    from bleak.exc import BleakError

    recorder = Recorder(kind, command=sys.argv, notes=args.notes)
    output = args.output or default_output_path(kind)
    exit_code = 0
    try:
        asyncio.run(runner(args, recorder))
    except KeyboardInterrupt:
        print("\nInterrupted.")
    except BleakError as e:
        print(f"Bluetooth error: {type(e).__name__}: {e}", file=sys.stderr)
        exit_code = 1
    finally:
        path = recorder.save(output)
        print(f"Saved {len(recorder.events)} events to {path}")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "analyze":
        from .analyze import format_report

        docs = [(f.name, load_capture(f)) for f in args.files]
        sys.stdout.write(
            format_report(docs, args.stream, args.max_distinct, show_timeline=not args.no_timeline)
        )
        return 0

    if args.command == "scan":
        from .scanner import run_scan

        return _run_ble("scan", args, run_scan)

    from .filters import TargetFilter

    if TargetFilter.from_args(args).is_empty():
        raise SystemExit(f"{args.command}: give at least one of --address/--name/--service-uuid/--company-id")
    if args.command == "inspect":
        from .gatt import run_inspect

        return _run_ble("inspect", args, run_inspect)

    from .capture import run_capture

    return _run_ble("capture", args, run_capture)


if __name__ == "__main__":
    sys.exit(main())
