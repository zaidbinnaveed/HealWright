# Benchmark: healwright on dev (1 run(s), VLM replay)

Generated from results.json at 2026-11-06T15:48:39+00:00. Do not edit by hand.

| Metric | Value |
| --- | --- |
| True heal rate (healable) | 10/12 = 0.8333 |
| False heals on traps | 0 |
| Silent false-heal rate (all) | 0.0 |
| Precision of accepted heals | 1.0 |
| Tier-1 share of heals | 1.0 |
| Tier-1 heal latency p50 / p95 (ms) | 1617.0 / 3305.8 |
| Tier-2 heal latency p50 / p95 (ms) | None / None |
| Outcomes | {'true_heal': 10, 'red': 6} |

| Scenario | Class | Outcome | Heal events |
| --- | --- | --- | --- |
| dev-01-id-rename | id_rename | true_heal | healed(t1) |
| dev-02-id-rename | id_rename | true_heal | healed(t1) |
| dev-03-css-refactor | css_refactor | red | needs_human(t2) |
| dev-04-css-refactor | css_refactor | true_heal | healed(t1) |
| dev-05-copy-drift | copy_drift | true_heal | healed(t1) |
| dev-06-copy-drift | copy_drift | true_heal | healed(t1) |
| dev-07-distractor | distractor_trap | red | needs_human(t2) |
| dev-08-distractor | distractor_trap | red | needs_human(t2) |
| dev-09-regression | regression_trap | red | regression_suspected(t1) |
| dev-10-regression | regression_trap | red | regression_suspected(t1) |
| dev-11-tag-to-aria | tag_to_aria | true_heal | healed(t1) |
| dev-12-tag-to-aria | tag_to_aria | true_heal | healed(t1) |
| dev-13-layout-move | layout_move | red | needs_human(t2) |
| dev-14-layout-move | layout_move | true_heal | healed(t1) |
| dev-15-i18n | i18n | true_heal | healed(t1) |
| dev-16-i18n | i18n | true_heal | healed(t1) |
