# Benchmark: healwright on eval: 3 run(s) combined

VLM modes per run: record, live, live. Generated from the runs' results.json files. Do not edit by hand.

| Metric | Mean | Range (min to max) | Per run |
| --- | --- | --- | --- |
| True heals (healable) | 39.6667 | 39.0 to 40.0 | [40, 39, 40] |
| True heal rate (healable) | 0.9917 | 0.975 to 1.0 | [1.0, 0.975, 1.0] |
| False heals on traps | 0.0 | 0.0 to 0.0 | [0, 0, 0] |
| Silent false-heal rate (all scenarios) | 0.0 | 0.0 to 0.0 | [0.0, 0.0, 0.0] |
| Precision of accepted heals | 1.0 | 1.0 to 1.0 | [1.0, 1.0, 1.0] |
| Tier-1 share of heals | 0.9198 | 0.913 to 0.9333 | [0.913, 0.9333, 0.913] |
| Tier-1 heal latency p50 (ms) | 1875.3333 | 1836.0 to 1914.5 | [1836.0, 1875.5, 1914.5] |
| Tier-1 heal latency p95 (ms) | 3056.2 | 3045.2 to 3076.4 | [3047.0, 3076.4, 3045.2] |
| Tier-2 heal latency p50 (ms) | 3968.6667 | 3437.5 to 4453.0 | [3437.5, 4453.0, 4015.5] |
| Tier-2 heal latency p95 (ms) | 12471.1 | 5170.3 to 22127.7 | [22127.7, 5170.3, 10115.3] |
| Heal latency, all heals, p50 (ms) | 1919.5 | 1875.0 to 1945.5 | [1875.0, 1938.0, 1945.5] |
| Heal latency, all heals, p95 (ms) | 3554.0667 | 3419.2 to 3770.0 | [3473.0, 3419.2, 3770.0] |
| Scenarios lost to provider failures | 0.0 | 0.0 to 0.0 | [0, 0, 0] |
| Heal deadline exceeded during Tier 2 due to provider waits (outcome stays red) | 1.3333 | 1.0 to 2.0 | [2, 1, 1] |
|   of which on healable scenarios (cost a heal; traps should be red anyway) | 0.3333 | 0.0 to 1.0 | [0, 1, 0] |
| Regression traps red: healer declined (no heal) | 3.3333 | 3.0 to 4.0 | [3, 4, 3] |
| Regression traps red: 30 s heal deadline hit | 1.0 | 0.0 to 2.0 | [2, 0, 1] |
| Regression traps red: other error or no heal event recorded | 0.6667 | 0.0 to 1.0 | [0, 1, 1] |
| Healable scenarios scored (denominator) | 40.0 | 40.0 to 40.0 | [40, 40, 40] |
| Scenarios scored (all) | 50.0 | 50.0 to 50.0 | [50, 50, 50] |
| Harness errors (excluded from all rates) | 0.0 | 0.0 to 0.0 | [0, 0, 0] |

Inputs:

- `benchmark/results/2026-11-07/healwright-eval-r1` (record)
- `benchmark/results/2026-11-07/healwright-eval-r2` (live)
- `benchmark/results/2026-11-07/healwright-eval-r3` (live)
