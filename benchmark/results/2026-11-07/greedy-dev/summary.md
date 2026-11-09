# Benchmark: greedy on dev (1 run(s), VLM replay)

Generated from results.json at 2026-11-07T07:31:58+00:00. Do not edit by hand.

| Metric | Value |
| --- | --- |
| True heal rate (healable) | 12/12 = 1.0 |
| False heals on traps | 2 |
| Silent false-heal rate (all) | 0.125 |
| Precision of accepted heals | 0.875 |
| Tier-1 share of heals | 1.0 |
| Tier-1 heal latency p50 / p95 (ms) | 234.5 / 304.8 |
| Tier-2 heal latency p50 / p95 (ms) | None / None |
| Heal latency, all heals, p50 / p95 (ms) | 234.5 / 304.8 |
| Healed events whose diff passes `git apply --check` | 0/16 (no patch: 0, failed: 0) |
| Outcomes | {'true_heal': 14, 'false_heal': 2} |

| Scenario | Class | Outcome | Heal events |
| --- | --- | --- | --- |
| dev-01-id-rename | id_rename | true_heal | healed(t1) |
| dev-02-id-rename | id_rename | true_heal | healed(t1) |
| dev-03-css-refactor | css_refactor | true_heal | healed(t1) |
| dev-04-css-refactor | css_refactor | true_heal | healed(t1) |
| dev-05-copy-drift | copy_drift | true_heal | healed(t1) |
| dev-06-copy-drift | copy_drift | true_heal | healed(t1) |
| dev-07-distractor | distractor_trap | true_heal | healed(t1) |
| dev-08-distractor | distractor_trap | true_heal | healed(t1) |
| dev-09-regression | regression_trap | false_heal | healed(t1) |
| dev-10-regression | regression_trap | false_heal | healed(t1) |
| dev-11-tag-to-aria | tag_to_aria | true_heal | healed(t1) |
| dev-12-tag-to-aria | tag_to_aria | true_heal | healed(t1) |
| dev-13-layout-move | layout_move | true_heal | healed(t1) |
| dev-14-layout-move | layout_move | true_heal | healed(t1) |
| dev-15-i18n | i18n | true_heal | healed(t1) |
| dev-16-i18n | i18n | true_heal | healed(t1) |
