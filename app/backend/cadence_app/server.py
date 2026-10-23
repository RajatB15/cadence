from __future__ import annotations

import os

import uvicorn


def main() -> None:
    # Loopback only: this service exposes personal health data.
    port = int(os.environ.get("CADENCE_PORT", "8765"))
    uvicorn.run(
        "cadence_app.main:app_factory", factory=True, host="127.0.0.1", port=port,
        access_log=os.environ.get("CADENCE_ACCESS_LOG") == "1",
    )


if __name__ == "__main__":
    main()
