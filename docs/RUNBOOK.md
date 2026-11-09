# HealWright runbook

How to set up, run, test, benchmark and demo HealWright on a fresh machine. Commands run from the repository root unless noted. Tested on Windows 10 with 8 GB RAM; Linux and macOS work the same way.

## 1. Requirements

- Python 3.11 and [uv](https://docs.astral.sh/uv/) (uv installs the right Python itself).
- Git.
- Node.js LTS (only for building the web app in `frontend/`).
- About 2 GB of free RAM for tests and demos; close other heavy browsers during benchmark runs.

## 2. Setup

```bash
uv sync --locked                     # Python dependencies into .venv
uv run playwright install chromium   # the browser HealWright drives
cd frontend && npm ci && npm run build && cd ..   # the web app, served by the API
```

Optional, only to regenerate the brand assets (favicons and the social card in `frontend/public/`):

```bash
uv run python scripts/fetch_fonts.py   # Clash Display + Satoshi from Fontshare into frontend/public/fonts/
uv run python scripts/gen_brand.py
```

The Fontshare fonts are free for commercial use and self-hosting under the ITF Free Font License, but may not be redistributed, so they are fetched, never committed (`frontend/public/fonts/` is git-ignored). The web app itself bundles its own fonts through npm and does not need this step.

### API keys (only for live model calls)

Copy `.env.example` to `.env` and fill in what you have: `GROQ_API_KEY` (default provider), optionally `MISTRAL_API_KEY`, `GEMINI_API_KEY`. `.env` is git-ignored; never commit keys. Without keys, everything still works in **replay** mode: committed model replies in `benchmark/vlm_cache/` are reused at zero calls.

## 3. Using HealWright on a test suite

```bash
uv run pytest tests/ --healwright-mode=record   # on green runs: save fingerprints + behaviour contracts
uv run pytest tests/ --healwright-mode=heal     # when a selector breaks: heal, verify, patch
uv run healwright report <run_id>               # self-contained HTML report of one run
uv run healwright apply <event_id>              # apply an accepted heal's patch (checks SHA-256 + git apply --check)
```

Heal mode prints the run folder and the report path in the terminal summary. Baselines live in `.healwright/baselines/` (commit them); run data in `.healwright/runs/` (git-ignored).

## 4. Running the app

```bash
uv run healwright serve                     # API + web app on http://127.0.0.1:8000
uv run uvicorn chaos_store.app:create_app --factory --host 127.0.0.1 --port 8001   # the Chaos Store test shop, optional
```

Pages: `/` (overview), `/runs`, `/runs/<run_id>`, `/events/<event_id>`, `/benchmarks`, `/demo`. API docs: `/api/v1/docs`.

## 5. Tests

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -m "unit or integration" -q                  # full suite, about 13 minutes
uv run pytest -m "(unit or integration) and not slow" -q   # quick loop
uv run pytest tests/integration/test_release_gate.py --run-release-gate   # invariants 2 and 3, about 20 minutes
```

`frontend/dist` must be built for the UI tests (`tests/ui/`); they are skipped otherwise. Never run the frontend dev server (`npm run dev`) while tests or benchmarks run.

## 6. Benchmark

```bash
uv run python -m benchmark.run --split dev  --system healwright --vlm-mode replay     # quick check on the dev set
uv run python -m benchmark.run --split eval --providers groq --system <system> --vlm-mode replay --tag <tag>
uv run python -m benchmark.combine          # mean + range across runs -> benchmark/results/eval-combined/
```

Systems: `native`, `greedy`, `rawhtml`, `tier1_only`, `healwright_noverify`, `healwright`. One run at a time; nothing else heavy running. Never tune on the eval split (it is frozen; a test fails if it changes). Method and results: `docs/BENCHMARK.md`.

## 7. Demo-day checklist

The day before:

- [ ] `git pull`, `uv sync --locked`, `cd frontend && npm ci && npm run build`.
- [ ] `uv run pytest -m "unit or integration" -q` is green.
- [ ] Rehearse the demo script (`docs/presentation/demo-script.md`) end to end, twice, timing it.
- [ ] Check the backup video plays offline (`docs/presentation/healwright-demo.webm`). It is not in git (about 20 MB): to regenerate, start `uv run healwright serve`, then run `uv run python scripts/record_demo.py` with the machine otherwise idle (about 3 minutes).
- [ ] Charts and screenshots for the slides are in `docs/presentation/charts/` and `docs/screenshots/`.

On the day, 30 minutes before:

- [ ] Laptop on power; notifications off; close desktop Chrome and other heavy apps (free RAM ≥ 2 GB).
- [ ] Wi-Fi is not needed: the demo runs in replay mode with committed model replies.
- [ ] Start the app: `uv run healwright serve`; open http://127.0.0.1:8000 and http://127.0.0.1:8000/demo.
- [ ] Do one warm-up demo run (dev-01) so Chromium and the store are cached; it should end "Healed".
- [ ] Projector: browser zoom 125% if the room is large; test both themes, pick the one that reads best.
- [ ] Keep the backup video open in a second window.

During the demo:

- [ ] dev-01 (UI change): heals. Tick "Watch it happen" to show the browser; "Open the broken shop" shows the breakage.
- [ ] dev-07 (look-alike trap): the verifier refuses the look-alike; heals to the true target or stays red.
- [ ] dev-09 (regression trap): stays red: the feature really is gone.
- [ ] Open the heal event: screenshots, candidate scores, expected vs observed behaviour, the diff.

If something fails: switch to the backup video; do not debug live.

## 8. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Address already in use` on 8000/8001 | Another server is running: stop it, or `healwright serve --port 8010` |
| Demo run ends "error" | Check the terminal running `healwright serve`; a busy laptop can exceed timeouts: close other apps and retry |
| Groq 429 in live runs | Free-tier per-minute limits; the client waits and retries. Use `--vlm-mode replay` to avoid calls |
| UI tests skipped | Build the app first: `cd frontend && npm run build` |
| A benchmark scenario ends as a harness error | A rare pytest-subprocess timeout. The runner records diagnostics in `benchmark/results/ki10-diagnostics/`; harness errors are excluded from rates and counted separately |
| Windows console shows garbled characters in test output | Set `PYTHONIOENCODING=utf-8` |
