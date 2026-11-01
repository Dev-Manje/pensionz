---
name: pz-verify
description: Use before declaring any Pensionz change done — brings the Docker stack up, applies migrations, type-checks and tests, smoke-tests the API with curl (including negative access cases), and captures headless-Chrome screenshots of changed screens at desktop and mobile widths.
---

# Verifying a Pensionz change

A change is done only when it has been **seen working**, not just compiled.

## 1. Stack

```bash
cd c:/x/htdocs/pensionz
docker compose up -d && docker compose ps          # db, minio, mailpit, backend, worker, frontend
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current         # must print "(head)"
docker compose logs --tail=50 backend               # no tracebacks
```

Frontend http://localhost:5178 · API http://localhost:8002/api/v1 (docs `/docs`) ·
Mailpit http://localhost:8026 (`curl -s localhost:8026/api/v1/messages`).
Ports differ from Money Market (5177/8001/8025) so both stacks can run together.

## 2. Static checks & tests

```bash
docker compose exec -T frontend sh -c "npx tsc -b --noEmit"
docker compose exec -T frontend npm test
docker compose exec backend pytest -q
```

## 3. API smoke test

Log in with a user from `TEST_USERS.md`, exercise the new endpoints with the bearer token,
including **negative** cases (wrong role → 403, other employer's member → 403, closed period →
409, invalid input → 400).

## 4. Visual check (required for any UI change)

Drive Chrome over raw CDP with Python `websockets` (same recipe as Money Market's `mm-verify`):

1. Launch `"/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new
   --disable-gpu --remote-debugging-port=9334 --no-sandbox
   --user-data-dir=<scratchpad>/chrome-profile about:blank` in the background; poll
   `curl -s http://127.0.0.1:9334/json/version`.
2. `PUT /json/new?about:blank` → `webSocketDebuggerUrl`.
3. Inject tokens into `localStorage` via `Runtime.evaluate`, `Page.reload`.
4. Navigate by clicking elements found by `textContent`; listen for `Runtime.exceptionThrown`.
5. `Emulation.setDeviceMetricsOverride` at 1440×900 **and** 390×844; `Page.captureScreenshot`
   → PNG in the scratchpad → **open it with the Read tool** and look at it.

Keep Chrome profiles and PNGs in the scratchpad, never the repo. Kill Chrome with
`taskkill //F //IM chrome.exe` when done.

## 5. Report

State what was verified and how (commands, roles used, screenshots viewed), and anything not
verified.
