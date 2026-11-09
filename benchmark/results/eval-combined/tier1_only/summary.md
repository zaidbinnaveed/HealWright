# Benchmark: tier1_only on eval: 1 run(s) combined

VLM modes per run: replay. Generated from the runs' results.json files. Do not edit by hand.

| Metric | Mean | Range (min to max) | Per run |
| --- | --- | --- | --- |
| True heals (healable) | 39.0 | 39.0 to 39.0 | [39] |
| True heal rate (healable) | 0.975 | 0.975 to 0.975 | [0.975] |
| False heals on traps | 0.0 | 0.0 to 0.0 | [0] |
| Silent false-heal rate (all scenarios) | 0.0 | 0.0 to 0.0 | [0.0] |
| Precision of accepted heals | 1.0 | 1.0 to 1.0 | [1.0] |
| Tier-1 share of heals | 1.0 | 1.0 to 1.0 | [1.0] |
| Tier-1 heal latency p50 (ms) | 1882.5 | 1882.5 to 1882.5 | [1882.5] |
| Tier-1 heal latency p95 (ms) | 3120.3 | 3120.3 to 3120.3 | [3120.3] |
| Tier-2 heal latency p50 (ms) | n/a | n/a | [None] |
| Tier-2 heal latency p95 (ms) | n/a | n/a | [None] |
| Heal latency, all heals, p50 (ms) | 1882.5 | 1882.5 to 1882.5 | [1882.5] |
| Heal latency, all heals, p95 (ms) | 3120.3 | 3120.3 to 3120.3 | [3120.3] |
| Scenarios lost to provider failures | 0.0 | 0.0 to 0.0 | [0] |
| Heal deadline exceeded during Tier 2 due to provider waits (outcome stays red) | 0.0 | 0.0 to 0.0 | [0] |
|   of which on healable scenarios (cost a heal; traps should be red anyway) | 0.0 | 0.0 to 0.0 | [0] |
| Regression traps red: healer declined (no heal) | 5.0 | 5.0 to 5.0 | [5] |
| Regression traps red: 30 s heal deadline hit | 0.0 | 0.0 to 0.0 | [0] |
| Regression traps red: other error or no heal event recorded | 0.0 | 0.0 to 0.0 | [0] |
| Healable scenarios scored (denominator) | 40.0 | 40.0 to 40.0 | [40] |
| Scenarios scored (all) | 50.0 | 50.0 to 50.0 | [50] |
| Harness errors (excluded from all rates) | 0.0 | 0.0 to 0.0 | [0] |

Inputs:

- `benchmark/results/2026-11-07/tier1_only-eval-r1` (replay)
