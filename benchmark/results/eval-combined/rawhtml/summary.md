# Benchmark: rawhtml on eval: 3 run(s) combined

VLM modes per run: record, live, live. Generated from the runs' results.json files. Do not edit by hand.

| Metric | Mean | Range (min to max) | Per run |
| --- | --- | --- | --- |
| True heals (healable) | 38.0 | 37.0 to 39.0 | [38, 37, 39] |
| True heal rate (healable) | 0.95 | 0.925 to 0.975 | [0.95, 0.925, 0.975] |
| False heals on traps | 1.0 | 1.0 to 1.0 | [1, 1, 1] |
| Silent false-heal rate (all scenarios) | 0.02 | 0.02 to 0.02 | [0.02, 0.02, 0.02] |
| Precision of accepted heals | 0.9773 | 0.9767 to 0.9778 | [0.9773, 0.9767, 0.9778] |
| Tier-1 share of heals | 0.0 | 0.0 to 0.0 | [0.0, 0.0, 0.0] |
| Tier-1 heal latency p50 (ms) | n/a | n/a | [None, None, None] |
| Tier-1 heal latency p95 (ms) | n/a | n/a | [None, None, None] |
| Tier-2 heal latency p50 (ms) | n/a | n/a | [None, None, None] |
| Tier-2 heal latency p95 (ms) | n/a | n/a | [None, None, None] |
| Heal latency, all heals, p50 (ms) | 414.1667 | 399.2 to 440.5 | [399.2, 402.8, 440.5] |
| Heal latency, all heals, p95 (ms) | 3144.0 | 1327.9 to 6550.5 | [1553.6, 1327.9, 6550.5] |
| Scenarios lost to provider failures | 1.0 | 0.0 to 2.0 | [1, 2, 0] |
| Heal deadline exceeded during Tier 2 due to provider waits (outcome stays red) | 0.0 | 0.0 to 0.0 | [0, 0, 0] |
|   of which on healable scenarios (cost a heal; traps should be red anyway) | 0.0 | 0.0 to 0.0 | [0, 0, 0] |
| Regression traps red: healer declined (no heal) | 0.0 | 0.0 to 0.0 | [0, 0, 0] |
| Regression traps red: 30 s heal deadline hit | 0.0 | 0.0 to 0.0 | [0, 0, 0] |
| Regression traps red: other error or no heal event recorded | 4.0 | 4.0 to 4.0 | [4, 4, 4] |
| Healable scenarios scored (denominator) | 40.0 | 40.0 to 40.0 | [40, 40, 40] |
| Scenarios scored (all) | 50.0 | 50.0 to 50.0 | [50, 50, 50] |
| Harness errors (excluded from all rates) | 0.0 | 0.0 to 0.0 | [0, 0, 0] |

Inputs:

- `benchmark/results/2026-11-08/rawhtml-eval-r1` (record)
- `benchmark/results/2026-11-08/rawhtml-eval-r2` (live)
- `benchmark/results/2026-11-08/rawhtml-eval-r3` (live)
