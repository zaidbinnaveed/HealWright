# Benchmark: rawhtml on dev (1 run(s), VLM record)

Generated from results.json at 2026-11-07T10:43:55+00:00. Do not edit by hand.

| Metric | Value |
| --- | --- |
| True heal rate (healable) | 12/12 = 1.0 |
| False heals on traps | 0 |
| Silent false-heal rate (all) | 0.0 |
| Precision of accepted heals | 1.0 |
| Tier-1 share of heals | 0.0 |
| Tier-1 heal latency p50 / p95 (ms) | None / None |
| Tier-2 heal latency p50 / p95 (ms) | None / None |
| Heal latency, all heals, p50 / p95 (ms) | 467.5 / 3397.2 |
| Healed events whose diff passes `git apply --check` | 0/14 (no patch: 14, failed: 0) |
| Outcomes | {'true_heal': 14, 'red': 2} |

| Scenario | Class | Outcome | Heal events |
| --- | --- | --- | --- |
| dev-01-id-rename | id_rename | true_heal | healed(tNone) |
| dev-02-id-rename | id_rename | true_heal | healed(tNone) |
| dev-03-css-refactor | css_refactor | true_heal | healed(tNone) |
| dev-04-css-refactor | css_refactor | true_heal | healed(tNone) |
| dev-05-copy-drift | copy_drift | true_heal | healed(tNone) |
| dev-06-copy-drift | copy_drift | true_heal | healed(tNone) |
| dev-07-distractor | distractor_trap | true_heal | healed(tNone) |
| dev-08-distractor | distractor_trap | true_heal | healed(tNone) |
| dev-09-regression | regression_trap | red | needs_human(tNone) |
| dev-10-regression | regression_trap | red | needs_human(tNone) |
| dev-11-tag-to-aria | tag_to_aria | true_heal | healed(tNone) |
| dev-12-tag-to-aria | tag_to_aria | true_heal | healed(tNone) |
| dev-13-layout-move | layout_move | true_heal | healed(tNone) |
| dev-14-layout-move | layout_move | true_heal | healed(tNone) |
| dev-15-i18n | i18n | true_heal | healed(tNone) |
| dev-16-i18n | i18n | true_heal | healed(tNone) |
