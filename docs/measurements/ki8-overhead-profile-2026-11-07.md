# Where record-mode time goes (2026-11-07)

Time-boxed investigation (about 2 h allowed, about 1 h used). Windows 10, i7-8550U, 8 GB, Chromium headless, examples suite (69 tests, 202 wrapped actions), Chaos Store in-process. Numbers are pytest's own "passed in" durations (no process start-up), from a local diagnostic plugin that wraps recorder methods and can stub parts out (not committed: diagnostic only).

## Headline (reported number)

Wall time per suite run including process start-up, `scripts/measure_overhead.py --runs 5` (`recording-overhead-2026-11-07T080132Z.json`): off median **31.97 s**, record median **38.79 s**, median overhead **21.3%** (paired 13.1–25.3%). This is the number to report.

Inside pytest (excluding start-up), 5 rounds today: off 30.28 / 29.54 / 30.35 / 30.66 / 29.30 s; record 35.20 / 35.14 / 34.51 / 36.35 / 33.68 s → medians 30.28 vs 35.14 s, **+16.0%**.

## Experiments (in-pytest durations)

| Variant | Runs (s) | What it shows |
| --- | --- | --- |
| off | 30.28, 29.54, 30.35, 30.66, 29.30 | reference |
| record | 35.20, 35.14, 34.51, 36.35, 33.68 | full recording |
| record, recorder hooks AND network listeners stubbed | 29.19, 31.05 | the page/locator proxy itself costs nothing measurable |
| record, recorder hooks stubbed, listeners on | 33.81, 31.51 | (noisy) |
| record, network listeners off, hooks on | 35.16, 36.29, 34.15 (+34.46, 33.54) | **≈ record: listeners are not the cost** |
| record, target fingerprint evaluate replaced by state-only | 33.80, 33.94 | the fingerprint evaluate is ≈ 1.3 s of the ≈ 5 s |

Accumulated hook time (unprofiled, 2 runs): `before_action` 8.3–8.6 s over 202 actions (median 40–43 ms), boundary evaluates 9.6 s over 310 calls (median 13–14 ms), `finish` 0.8–0.9 s, baseline merge + write 1.0–1.5 s over 69 tests. The in-hook time (≈ 8 s) is larger than the net overhead (≈ 5 s): an evaluate issued right after a click or navigation waits for the page's main thread, time the next action would partly spend waiting anyway.

Isolated on an idle Chaos Store page (30 samples): trivial `evaluate("1")` 1.88 ms, state-only evaluate 3.07 ms, target `locator.evaluate_all(extract)` 5.91 ms, of which the in-page JavaScript is 0.14 ms.

## Suspects, checked

- **Per-action fingerprint runs full candidate extraction:** no. Record mode already extracts only the target (`locator.evaluate_all` on the one element, `target_expression()`); candidate extraction (up to 400) runs only on the heal path.
- **DOM node counting on every action:** it is part of the same single evaluate (state), sub-millisecond in-page.
- **Listener setup per action:** no, listeners are attached once per page (`Recorder.attach`), and switching them off does not change the suite time.
- **Synchronous file writes per step:** no, writes happen once per test at test end (`record_passing_run`); 1.0–1.5 s per suite run in total.

## Why no fix was applied

The remaining cost is the boundary evaluates themselves (needed: the fingerprint and the before/after page state ARE the baseline) plus one baseline write per test. Candidate savings: batching baseline writes to session end and pre-installing the extract script per document (smaller payload per call), together roughly 1 s (≈ 3%). Neither brings the overhead under 10%; dropping the before-action fingerprint would, but healing depends on it. At the end of the time box the optimisation stopped and the claim is phrased as the measured value.
