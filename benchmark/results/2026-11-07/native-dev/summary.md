# Benchmark: native on dev (1 run(s), VLM replay)

Generated from results.json at 2026-11-07T07:18:34+00:00. Do not edit by hand.

| Metric | Value |
| --- | --- |
| True heal rate (healable) | 0/12 = 0.0 |
| False heals on traps | 0 |
| Silent false-heal rate (all) | 0.0 |
| Precision of accepted heals | None |
| Tier-1 share of heals | None |
| Tier-1 heal latency p50 / p95 (ms) | None / None |
| Tier-2 heal latency p50 / p95 (ms) | None / None |
| Heal latency, all heals, p50 / p95 (ms) | None / None |
| Healed events whose diff passes `git apply --check` | 0/0 (no patch: 0, failed: 0) |
| Outcomes | {'red': 16} |

| Scenario | Class | Outcome | Heal events |
| --- | --- | --- | --- |
| dev-01-id-rename | id_rename | red | - |
| dev-02-id-rename | id_rename | red | - |
| dev-03-css-refactor | css_refactor | red | - |
| dev-04-css-refactor | css_refactor | red | - |
| dev-05-copy-drift | copy_drift | red | - |
| dev-06-copy-drift | copy_drift | red | - |
| dev-07-distractor | distractor_trap | red | - |
| dev-08-distractor | distractor_trap | red | - |
| dev-09-regression | regression_trap | red | - |
| dev-10-regression | regression_trap | red | - |
| dev-11-tag-to-aria | tag_to_aria | red | - |
| dev-12-tag-to-aria | tag_to_aria | red | - |
| dev-13-layout-move | layout_move | red | - |
| dev-14-layout-move | layout_move | red | - |
| dev-15-i18n | i18n | red | - |
| dev-16-i18n | i18n | red | - |
