# Benchmark: healwright_noverify on eval: 3 run(s) combined

VLM modes per run: record, live, live. Generated from the runs' results.json files. Do not edit by hand.

| Metric | Mean | Range (min to max) | Per run |
| --- | --- | --- | --- |
| True heals (healable) | 39.3333 | 39.0 to 40.0 | [40, 39, 39] |
| True heal rate (healable) | 1.0 | 1.0 to 1.0 | [1.0, 1.0, 1.0] |
| False heals on traps | 3.0 | 3.0 to 3.0 | [3, 3, 3] |
| Silent false-heal rate (all scenarios) | 0.0608 | 0.06 to 0.0612 | [0.06, 0.0612, 0.0612] |
| Precision of accepted heals | 0.9353 | 0.9348 to 0.9362 | [0.9362, 0.9348, 0.9348] |
| Tier-1 share of heals | 0.9155 | 0.9149 to 0.9167 | [0.9167, 0.9149, 0.9149] |
| Tier-1 heal latency p50 (ms) | 203.3333 | 188.0 to 219.0 | [219.0, 188.0, 203.0] |
| Tier-1 heal latency p95 (ms) | 265.1333 | 263.5 to 266.0 | [265.9, 266.0, 263.5] |
| Tier-2 heal latency p50 (ms) | 799.1667 | 320.0 to 1234.0 | [320.0, 1234.0, 843.5] |
| Tier-2 heal latency p95 (ms) | 3137.2 | 397.4 to 7350.9 | [397.4, 7350.9, 1663.3] |
| Heal latency, all heals, p50 (ms) | 208.3333 | 203.0 to 219.0 | [219.0, 203.0, 203.0] |
| Heal latency, all heals, p95 (ms) | 739.9667 | 326.9 to 1112.0 | [326.9, 1112.0, 781.0] |
| Scenarios lost to provider failures | 0.0 | 0.0 to 0.0 | [0, 0, 0] |
| Heal deadline exceeded during Tier 2 due to provider waits (outcome stays red) | 0.6667 | 0.0 to 1.0 | [0, 1, 1] |
|   of which on healable scenarios (cost a heal; traps should be red anyway) | 0.0 | 0.0 to 0.0 | [0, 0, 0] |
| Regression traps red: healer declined (no heal) | 2.3333 | 2.0 to 3.0 | [3, 2, 2] |
| Regression traps red: 30 s heal deadline hit | 0.6667 | 0.0 to 1.0 | [0, 1, 1] |
| Regression traps red: other error or no heal event recorded | 0.0 | 0.0 to 0.0 | [0, 0, 0] |
| Healable scenarios scored (denominator) | 39.3333 | 39.0 to 40.0 | [40, 39, 39] |
| Scenarios scored (all) | 49.3333 | 49.0 to 50.0 | [50, 49, 49] |
| Harness errors (excluded from all rates) | 0.6667 | 0.0 to 1.0 | [0, 1, 1] |

Inputs:

- `benchmark/results/2026-11-08/healwright_noverify-eval-r1` (record)
- `benchmark/results/2026-11-08/healwright_noverify-eval-r2` (live)
- `benchmark/results/2026-11-08/healwright_noverify-eval-r3` (live)
