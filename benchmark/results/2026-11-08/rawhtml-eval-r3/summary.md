# Benchmark: rawhtml on eval (1 run(s), VLM live)

Generated from results.json at 2026-11-08T12:10:13+00:00. Do not edit by hand.

| Metric | Value |
| --- | --- |
| True heal rate (healable) | 39/40 = 0.975 |
| False heals on traps | 1 |
| Silent false-heal rate (all) | 0.02 |
| Precision of accepted heals | 0.9778 |
| Tier-1 share of heals | 0.0 |
| Tier-1 heal latency p50 / p95 (ms) | None / None |
| Tier-2 heal latency p50 / p95 (ms) | None / None |
| Heal latency, all heals, p50 / p95 (ms) | 440.5 / 6550.5 |
| Healed events whose diff passes `git apply --check` | 0/46 (no patch: 46, failed: 0) |
| Scenarios lost to provider failures (rate limit / quota / cap) | 0 |
| Outcomes | {'true_heal': 44, 'red': 5, 'false_heal': 1} |

| Scenario | Class | Outcome | Heal events |
| --- | --- | --- | --- |
| eval-01-id-rename | id_rename | true_heal | healed(tNone), healed(tNone) |
| eval-02-id-rename | id_rename | true_heal | healed(tNone) |
| eval-03-id-rename | id_rename | true_heal | healed(tNone) |
| eval-04-id-rename | id_rename | red | needs_human(tNone) |
| eval-05-id-rename | id_rename | true_heal | healed(tNone) |
| eval-06-id-rename | id_rename | true_heal | healed(tNone) |
| eval-07-id-rename | id_rename | true_heal | healed(tNone) |
| eval-08-id-rename | id_rename | true_heal | healed(tNone) |
| eval-09-css-refactor | css_refactor | true_heal | healed(tNone) |
| eval-10-css-refactor | css_refactor | true_heal | healed(tNone) |
| eval-11-css-refactor | css_refactor | true_heal | healed(tNone) |
| eval-12-css-refactor | css_refactor | true_heal | healed(tNone) |
| eval-13-css-refactor | css_refactor | true_heal | healed(tNone) |
| eval-14-css-refactor | css_refactor | true_heal | healed(tNone) |
| eval-15-css-refactor | css_refactor | true_heal | healed(tNone) |
| eval-16-css-refactor | css_refactor | true_heal | healed(tNone) |
| eval-17-copy-drift | copy_drift | true_heal | healed(tNone) |
| eval-18-copy-drift | copy_drift | true_heal | healed(tNone) |
| eval-19-copy-drift | copy_drift | true_heal | healed(tNone) |
| eval-20-copy-drift | copy_drift | true_heal | healed(tNone) |
| eval-21-copy-drift | copy_drift | true_heal | healed(tNone) |
| eval-22-copy-drift | copy_drift | true_heal | healed(tNone) |
| eval-23-copy-drift | copy_drift | true_heal | healed(tNone) |
| eval-24-tag-to-aria | tag_to_aria | true_heal | healed(tNone) |
| eval-25-tag-to-aria | tag_to_aria | true_heal | healed(tNone) |
| eval-26-tag-to-aria | tag_to_aria | true_heal | healed(tNone) |
| eval-27-tag-to-aria | tag_to_aria | true_heal | healed(tNone) |
| eval-28-tag-to-aria | tag_to_aria | true_heal | healed(tNone) |
| eval-29-tag-to-aria | tag_to_aria | true_heal | healed(tNone) |
| eval-30-tag-to-aria | tag_to_aria | true_heal | healed(tNone) |
| eval-31-layout-move | layout_move | true_heal | healed(tNone) |
| eval-32-layout-move | layout_move | true_heal | healed(tNone) |
| eval-33-layout-move | layout_move | true_heal | healed(tNone) |
| eval-34-layout-move | layout_move | true_heal | healed(tNone) |
| eval-35-layout-move | layout_move | true_heal | healed(tNone) |
| eval-36-layout-move | layout_move | true_heal | healed(tNone) |
| eval-37-i18n | i18n | true_heal | healed(tNone) |
| eval-38-i18n | i18n | true_heal | healed(tNone) |
| eval-39-i18n | i18n | true_heal | healed(tNone) |
| eval-40-i18n | i18n | true_heal | healed(tNone) |
| eval-41-distractor | distractor_trap | true_heal | healed(tNone) |
| eval-42-distractor | distractor_trap | true_heal | healed(tNone) |
| eval-43-distractor | distractor_trap | true_heal | healed(tNone) |
| eval-44-distractor | distractor_trap | true_heal | healed(tNone) |
| eval-45-distractor | distractor_trap | true_heal | healed(tNone) |
| eval-46-regression | regression_trap | red | needs_human(tNone) |
| eval-47-regression | regression_trap | red | needs_human(tNone) |
| eval-48-regression | regression_trap | false_heal | healed(tNone) |
| eval-49-regression | regression_trap | red | needs_human(tNone) |
| eval-50-regression | regression_trap | red | needs_human(tNone) |
