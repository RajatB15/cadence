---
name: ship-local
description: Apply Cadence changes to the running local service (rebuild frontend, restart backend LaunchAgent) and verify. Use after finishing frontend or backend changes the user will see on their Mac or iPhone.
---

1. Run the relevant tests first: `cd app/backend && .venv/bin/pytest`, `npm --prefix app/web test`, and `npm --prefix app/web run typecheck`.
2. Frontend changed → `npm --prefix app/web run build` (typechecks, writes `app/web/dist`, which the service and phone share server serve).
3. Backend changed (including migrations) → `scripts/cadence-service.sh restart`, then `scripts/cadence-service.sh status`.
4. Verify: `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/` should be 200; check `scripts/cadence-service.sh logs` for startup errors (logs can contain health data: skim for errors only, don't paste them).
5. Phone-visible UI changes also need the dist rebuild; the iPhone PWA may need a reload to pick up the new service worker (`app/web/public/sw.js`).
6. If a milestone is now verified, tick it in plan.md.
