# Project Instructions

- Read [plan.md](../plan.md) before planning or implementing project changes. It is the source of truth for scope, stack, roadmap, and acceptance criteria; update its checklist when milestones are verified.
- Build the local-first web experience first, package for macOS after functionality is validated, and implement LLM integration last.
- Preserve the existing BLE research tools and tests. Do not assume the scale protocol or Garmin API capabilities are verified.
- Store everything, surface what matters: keep every imported response in the vault (never drop data at import), but product pages show curated, meaningful views and derived insights rather than raw field dumps. Raw records stay inspectable through the Vault data explorer.
- Local Garmin credentials are in `.secrets/garmin.env`. Load them directly in the backend process when needed; never print, copy into prompts, put in frontend bundles, log, or commit them. Do not request the key again while this file is available.
- Credential expiry metadata lives alongside the key. Implement the renewal reminder specified in plan.md; never infer expiry from the token format.
- Do not make authenticated network requests merely to inspect credentials. Verify official endpoint documentation before using the key.
- Run focused tests for changed behavior. Existing research tests: `cd research && .venv/bin/pytest`.