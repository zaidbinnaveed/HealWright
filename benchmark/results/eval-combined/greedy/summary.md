# Benchmark: greedy on eval: 1 run(s) combined

VLM modes per run: replay. Generated from the runs' results.json files. Do not edit by hand.

| Metric | Mean | Range (min to max) | Per run |
| --- | --- | --- | --- |
| True heals (healable) | 39.0 | 39.0 to 39.0 | [39] |
| True heal rate (healable) | 1.0 | 1.0 to 1.0 | [1.0] |
| False heals on traps | 6.0 | 6.0 to 6.0 | [6] |
| Silent false-heal rate (all scenarios) | 0.1224 | 0.1224 to 0.1224 | [0.1224] |
| Precision of accepted heals | 0.8776 | 0.8776 to 0.8776 | [0.8776] |
| Tier-1 share of heals | 1.0 | 1.0 to 1.0 | [1.0] |
| Tier-1 heal latency p50 (ms) | 218.0 | 218.0 to 218.0 | [218.0] |
| Tier-1 heal latency p95 (ms) | 266.0 | 266.0 to 266.0 | [266.0] |
| Tier-2 heal latency p50 (ms) | n/a | n/a | [None] |
| Tier-2 heal latency p95 (ms) | n/a | n/a | [None] |
| Heal latency, all heals, p50 (ms) | 218.0 | 218.0 to 218.0 | [218.0] |
| Heal latency, all heals, p95 (ms) | 266.0 | 266.0 to 266.0 | [266.0] |
| Scenarios lost to provider failures | 0.0 | 0.0 to 0.0 | [0] |
| Heal deadline exceeded during Tier 2 due to provider waits (outcome stays red) | 0.0 | 0.0 to 0.0 | [0] |
|   of which on healable scenarios (cost a heal; traps should be red anyway) | 0.0 | 0.0 to 0.0 | [0] |
| Regression traps red: healer declined (no heal) | 0.0 | 0.0 to 0.0 | [0] |
| Regression traps red: 30 s heal deadline hit | 0.0 | 0.0 to 0.0 | [0] |
| Regression traps red: other error or no heal event recorded | 0.0 | 0.0 to 0.0 | [0] |
| Healable scenarios scored (denominator) | 39.0 | 39.0 to 39.0 | [39] |
| Scenarios scored (all) | 49.0 | 49.0 to 49.0 | [49] |
| Harness errors (excluded from all rates) | 1.0 | 1.0 to 1.0 | [1] |

Inputs:

- `benchmark/results/2026-11-07/greedy-eval-r1` (replay)
