# HealWright triage API (`/api/v1`)

Status: implemented 2026-11-07. Source: `src/healwright/api/`. Tests: `tests/integration/test_api.py` (every endpoint and every error code), `tests/integration/test_api_demo_live.py` (real demo run).

Run it: `uv run healwright serve` (default `127.0.0.1:8000`; `--host` other than localhost requires `HEALWRIGHT_API_TOKEN`). Interactive docs at `/api/v1/docs`. The built frontend (`frontend/dist`) is served at `/`.

## Conventions

- **Data:** read from `<HEALWRIGHT_ARTIFACT_DIR>/runs/*` (events.jsonl, artifacts, triage.json) and `benchmark/results/*/*/results.json`. No database. Corrupt event lines are skipped and counted (`skipped_lines`); unreadable files are `STORAGE_UNAVAILABLE`.
- **Request id:** every response carries `X-Request-ID`. A client value matching `^[A-Za-z0-9._-]{1,64}$` is echoed, otherwise a ULID is generated. The same id is on every log record for that request (`<artifact_dir>/logs/healwright.log`, JSON lines, secrets redacted).
- **Errors:** always this envelope, never a stack trace:

  ```json
  {"error": {"code": "SOURCE_CHANGED",
             "message": "tests/test_checkout.py changed after the patch was generated",
             "details": {"expected_sha256": "...", "actual_sha256": "..."},
             "request_id": "01JC8Z..."}}
  ```

  | Code | HTTP | When |
  | --- | --- | --- |
  | `VALIDATION_ERROR` | 422 | bad query, body, path or header; ids and cursors are ULIDs checked by regex; `details.errors` lists each problem |
  | `UNAUTHORIZED` | 401 | `HEALWRIGHT_API_TOKEN` is set and the `Authorization: Bearer` header is missing or wrong |
  | `NOT_FOUND` | 404 | unknown run, event, artifact, benchmark, scenario, demo run or route |
  | `NO_PATCH` | 404 | the event has no diff |
  | `METHOD_NOT_ALLOWED` | 405 | wrong HTTP method |
  | `ALREADY_TRIAGED` | 409 | a different triage decision is already recorded (`details.decision`); the same decision again is an idempotent 200 |
  | `NOT_ACCEPTED` | 409 | apply requested before the heal was accepted |
  | `SOURCE_CHANGED` | 409 | the test file's SHA-256 differs from heal time (`details.expected_sha256`, `details.actual_sha256`) |
  | `DEMO_BUSY` | 409 | a demo run is already in progress |
  | `PAYLOAD_TOO_LARGE` | 413 | request body over 64 KiB (`details.max_bytes`) |
  | `PATCH_INVALID` | 422 | `git apply --check` fails |
  | `STORAGE_UNAVAILABLE` | 503 | run folders or artifacts cannot be read or written |
  | `INTERNAL_ERROR` | 500 | anything unhandled; the trace is logged with the request id, never returned |
- **Auth:** with `HEALWRIGHT_API_TOKEN` set, every `/api/*` request needs `Authorization: Bearer <token>` (CORS preflights excepted). The static UI bundle is not guarded (no data in it).
- **Pagination:** `?limit=&cursor=`; responses are `{"items": [...], "next_cursor": "<ULID>" | null}`. Newest first; the cursor is the last ULID of the page.
- **CORS:** only `http://localhost:5173` and `http://127.0.0.1:5173` (the Vite dev server).
- **Triage state** lives in `runs/<run_id>/triage.json` (the plugin's `events.jsonl` is append-only). The API returns the effective state in `triage.status`: `pending | accepted | rejected | applied`.

## Endpoints

| Method | Path | Success | Errors |
| --- | --- | --- | --- |
| GET | `/health` | `{"status": "ok", "version"}` | |
| GET | `/ready` | 200 `{"status": "ready", "checks": {artifact_root, results_root, git}}` | 503 with the failing checks |
| GET | `/runs?limit(1–100, 20)&cursor` | runs with `status_counts`, `tier_counts`, `tests`, `started_at` | 422, 503 |
| GET | `/runs/{run_id}` | run + `events` (oldest first) | 404, 422, 503 |
| GET | `/heal-events?run_id&status&tier(1,2)&limit(1–200, 50)&cursor` | events, newest first | 404 (unknown run), 422, 503 |
| GET | `/heal-events/{id}` | `HealEvent` JSON + `triage` + `artifact_urls` | 404, 422 |
| GET | `/heal-events/{id}/artifacts/{name}` | the file; `name` ∈ `before.png, som.jpg, sandbox.png, candidates.json, patch.diff, suggestion.txt` | 404 (not recorded / file missing), 422 (any other name) |
| GET | `/heal-events/{id}/patch` | `diff, source_path, source_sha256, current_sha256, source_changed, apply_check{ok,message}` | 404 `NO_PATCH` |
| POST | `/heal-events/{id}/triage` `{"decision": "accepted"\|"rejected", "note"≤1000}` | updated event | 404, 409 `ALREADY_TRIAGED`, 413, 422, 503 |
| POST | `/heal-events/{id}/patch/apply` + `Idempotency-Key` | `{"code": "APPLIED", "replayed": false, ...}`; applying again → 200 `replayed: true` | 404 `NOT_FOUND`/`NO_PATCH`, 409 `NOT_ACCEPTED`/`SOURCE_CHANGED`, 422 `VALIDATION_ERROR` (no key) / `PATCH_INVALID`, 503 |
| GET | `/benchmarks` | one summary per `benchmark/results/<date>/<system>-<split>/`; id = `<date>--<system>-<split>` | |
| GET | `/benchmarks/{id}` | the full `results.json` | 404, 422 |
| GET | `/scenarios` | **dev** scenarios only (the demo never touches the frozen eval split) | |
| POST | `/demo/runs` `{"scenario_id", "watch"?}` | 202 + run state; `watch: true` runs the heal step in a visible browser slowed to 400 ms per action (default headless) | 404 (not a dev scenario), 409 `DEMO_BUSY`, 422 |
| GET | `/demo/runs/{id}` | `stage` (`queued → starting_store → recording_baselines → breaking → running_test → done/error`), `running`, `outcome`, `fired_actions`, `heal_events`, `watch`, `shots` (names available) | 404, 422 |
| GET | `/demo/runs/{id}/shots/{clean\|healed}` | PNG: end of the first clean run / end of the healed run (pytest-playwright `--screenshot=on`) | 404, 422 |
| POST | `/demo/shop` `{"scenario_id"}` | `{"url"}`: opens the Chaos Store on a fresh session with the scenario applied (a separate in-process store, never reset by demo runs; uses the store's control-only `/__chaos/enter?session=&next=` route to set the session cookie) | 404, 422 |

## Apply checks (shared with `healwright apply`)

`src/healwright/apply.py`, in order: `Idempotency-Key` present (API) → event exists → has a diff → (API only) triage decision is `accepted` → the target file's SHA-256 equals the one recorded at heal time → `git apply --check` → `git apply`. The CLI does not require `accepted` (running it is the decision). Applying an already-applied event is a no-op.

## Demo runs

One at a time. Starts the Chaos Store in the API process (once), records baselines with 2 clean runs, applies the scenario's mutation, runs the test once (heal mode, VLM replay), and classifies the outcome from the store's action log exactly like the benchmark. Heal events are written to the API's artifact dir, so they appear in `/heal-events`. Must be run from the repository root. Never start the frontend dev server or a demo run during test or benchmark runs.
