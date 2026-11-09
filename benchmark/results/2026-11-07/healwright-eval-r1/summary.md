# Benchmark: healwright on eval (1 run(s), VLM record)

Generated from results.json at 2026-11-07T15:57:28+00:00. Do not edit by hand.

| Metric | Value |
| --- | --- |
| True heal rate (healable) | 40/40 = 1.0 |
| False heals on traps | 0 |
| Silent false-heal rate (all) | 0.0 |
| Precision of accepted heals | 1.0 |
| Tier-1 share of heals | 0.913 |
| Tier-1 heal latency p50 / p95 (ms) | 1836.0 / 3047.0 |
| Tier-2 heal latency p50 / p95 (ms) | 3437.5 / 22127.7 |
| Heal latency, all heals, p50 / p95 (ms) | 1875.0 / 3473.0 |
| Healed events whose diff passes `git apply --check` | 46/46 (no patch: 0, failed: 0) |
| Scenarios lost to provider failures (rate limit / quota / cap) | 0 |
| Outcomes | {'true_heal': 45, 'red': 5} |

| Scenario | Class | Outcome | Heal events |
| --- | --- | --- | --- |
| eval-01-id-rename | id_rename | true_heal | healed(t1), healed(t1) |
| eval-02-id-rename | id_rename | true_heal | healed(t1) |
| eval-03-id-rename | id_rename | true_heal | healed(t1) |
| eval-04-id-rename | id_rename | true_heal | healed(t1) |
| eval-05-id-rename | id_rename | true_heal | healed(t1) |
| eval-06-id-rename | id_rename | true_heal | healed(t1) |
| eval-07-id-rename | id_rename | true_heal | healed(t1) |
| eval-08-id-rename | id_rename | true_heal | healed(t1) |
| eval-09-css-refactor | css_refactor | true_heal | healed(t1) |
| eval-10-css-refactor | css_refactor | true_heal | healed(t1) |
| eval-11-css-refactor | css_refactor | true_heal | healed(t2) |
| eval-12-css-refactor | css_refactor | true_heal | healed(t1) |
| eval-13-css-refactor | css_refactor | true_heal | healed(t1) |
| eval-14-css-refactor | css_refactor | true_heal | healed(t1) |
| eval-15-css-refactor | css_refactor | true_heal | healed(t1) |
| eval-16-css-refactor | css_refactor | true_heal | healed(t1) |
| eval-17-copy-drift | copy_drift | true_heal | healed(t1) |
| eval-18-copy-drift | copy_drift | true_heal | healed(t1) |
| eval-19-copy-drift | copy_drift | true_heal | healed(t1) |
| eval-20-copy-drift | copy_drift | true_heal | healed(t1) |
| eval-21-copy-drift | copy_drift | true_heal | healed(t1) |
| eval-22-copy-drift | copy_drift | true_heal | healed(t1) |
| eval-23-copy-drift | copy_drift | true_heal | healed(t1) |
| eval-24-tag-to-aria | tag_to_aria | true_heal | healed(t1) |
| eval-25-tag-to-aria | tag_to_aria | true_heal | healed(t1) |
| eval-26-tag-to-aria | tag_to_aria | true_heal | healed(t1) |
| eval-27-tag-to-aria | tag_to_aria | true_heal | healed(t1) |
| eval-28-tag-to-aria | tag_to_aria | true_heal | healed(t1) |
| eval-29-tag-to-aria | tag_to_aria | true_heal | healed(t1) |
| eval-30-tag-to-aria | tag_to_aria | true_heal | healed(t1) |
| eval-31-layout-move | layout_move | true_heal | healed(t1) |
| eval-32-layout-move | layout_move | true_heal | healed(t1) |
| eval-33-layout-move | layout_move | true_heal | healed(t1) |
| eval-34-layout-move | layout_move | true_heal | healed(t1) |
| eval-35-layout-move | layout_move | true_heal | healed(t1) |
| eval-36-layout-move | layout_move | true_heal | healed(t1) |
| eval-37-i18n | i18n | true_heal | healed(t1) |
| eval-38-i18n | i18n | true_heal | healed(t1) |
| eval-39-i18n | i18n | true_heal | healed(t1) |
| eval-40-i18n | i18n | true_heal | healed(t1) |
| eval-41-distractor | distractor_trap | true_heal | healed(t2) |
| eval-42-distractor | distractor_trap | true_heal | healed(t1) |
| eval-43-distractor | distractor_trap | true_heal | healed(t1) |
| eval-44-distractor | distractor_trap | true_heal | healed(t2) |
| eval-45-distractor | distractor_trap | true_heal | healed(t2) |
| eval-46-regression | regression_trap | red | error(tNone) |
| eval-47-regression | regression_trap | red | regression_suspected(t2) |
| eval-48-regression | regression_trap | red | error(tNone) |
| eval-49-regression | regression_trap | red | regression_suspected(t1) |
| eval-50-regression | regression_trap | red | regression_suspected(t1) |
