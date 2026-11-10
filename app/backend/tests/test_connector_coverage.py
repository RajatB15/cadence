"""The rule, enforced: every user-facing /api route is either covered by a Claude connector tool or listed in connector_exempt.txt with a reason.

A new route that is neither fails here, so a feature can't ship without its connector tools (or a written reason it has none).
Reasons starting "legacy" are features from before the rule that still need tools; shrink that list, never grow it.
"""

import re
from pathlib import Path

from fastapi.routing import APIRoute

from cadence_app import connector as C
from cadence_app.config import Settings
from cadence_app.main import create_app
from tests.test_api import FixedClock
from datetime import date

EXEMPT = Path(__file__).with_name("connector_exempt.txt")
norm = lambda path: re.sub(r"\{[^}]+\}", "{}", path)  # noqa: E731


def app_routes(tmp_path) -> set[str]:
    secrets = tmp_path / "garmin.env"
    secrets.write_text("GARMIN_API_KEY='x'\n")
    app = create_app(Settings(data_dir=tmp_path / "data", secrets_file=secrets), FixedClock(date(2026, 11, 10)))
    return {f"{m} {norm(r.path)}" for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/") for m in r.methods if m not in ("HEAD", "OPTIONS")}


def covered() -> set[str]:
    return {f"{t.get('method', 'GET')} {norm(t['path'])}" for t in C.TOOLS.values()}


def exempt() -> dict[str, str]:
    out = {}
    for line in EXEMPT.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            key, _, reason = line.partition("  # ")
            out[key.strip()] = reason.strip()
    return out


def test_every_route_has_connector_tools_or_a_written_reason(tmp_path):
    routes, listed = app_routes(tmp_path), exempt()
    missing = sorted(routes - covered() - set(listed))
    assert not missing, "These routes have no Claude connector tool and no entry in tests/connector_exempt.txt (add tools in connector.py TOOLS, or a reason):\n" + "\n".join(missing)
    stale = sorted(set(listed) - routes)
    assert not stale, "connector_exempt.txt lists routes that no longer exist:\n" + "\n".join(stale)
    assert not sorted(set(listed) & covered()), "These routes now have tools; remove them from connector_exempt.txt"
    assert all(listed.values()), "every exemption needs a reason"


def test_tools_point_at_real_routes(tmp_path):
    routes = app_routes(tmp_path)
    assert sorted(covered() - routes) == [], "connector tools call routes that don't exist"


def test_the_gym_planner_is_fully_covered(tmp_path):
    gym = {r for r in app_routes(tmp_path) if " /api/gym/" in r or r.endswith("/api/settings/gym")}
    helpers = {k for k, v in exempt().items() if "editor helper" in v}  # stateless editor helpers: the tools cover the same ground by session id
    assert gym and gym <= covered() | helpers and len(helpers) == 5
    assert "POST /api/gym/sessions/build" in covered() and "DELETE /api/gym/sessions/{}" in covered()
