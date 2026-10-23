"""Non-blocking line input for interactive capture sessions."""

from __future__ import annotations

import asyncio
import sys
import threading


def start_stdin_reader(loop: asyncio.AbstractEventLoop) -> "asyncio.Queue[str | None]":
    """Feed stdin lines into a queue; ``None`` signals EOF.

    A daemon thread is used because kqueue (macOS) cannot poll TTYs, so
    ``loop.add_reader(sys.stdin)`` is unreliable there.
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def put(item: str | None) -> bool:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
            return True
        except RuntimeError:  # loop already closed
            return False

    def worker() -> None:
        for line in sys.stdin:
            if not put(line.rstrip("\r\n")):
                return
        put(None)

    threading.Thread(target=worker, name="stdin-reader", daemon=True).start()
    return queue
