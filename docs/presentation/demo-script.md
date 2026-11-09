# HealWright demo script

Length: about 7 minutes live, plus questions. Everything runs offline in replay mode (recorded model replies), so Wi-Fi is not needed. Backup: `docs/presentation/healwright-demo.webm` (play it if anything goes wrong; do not debug live).

Setup before the talk (see the demo-day checklist in `docs/RUNBOOK.md`):

```bash
uv run healwright serve          # http://127.0.0.1:8000
```

Open three tabs: `/` (overview), `/demo`, `/benchmarks`. Do one warm-up run of dev-01 on `/demo`.

---

## 1. The problem (45 s) · tab `/`

> "UI tests break all the time for reasons that are not bugs: an id gets renamed, a class is refactored, a button's text changes. Self-healing tools promise to fix that automatically. The catch: most of them pick the closest-looking element and call it fixed. On a page with a look-alike button, that turns a real bug into a green test. That is worse than a red test."

Point at the headline number on the overview: heal rate, and zero false heals.

## 2. How HealWright works (60 s) · tab `/`, "How it works"

> "On every green run, HealWright records two things for each step: a fingerprint of the element and the network calls the click causes. When a selector breaks, it scores every candidate element against the fingerprint. If one clearly wins, that's Tier 1, no AI. If it's a close call, a vision model picks a numbered mark, never code. Then the important part: the chosen element is clicked in a sandboxed copy of the page, and its network effect must match the recording. Only then does the test continue, and HealWright writes a patch you review."

## 3. Live: a harmless UI change heals (90 s) · tab `/demo`

1. Pick **dev-01-id-rename**. Say: "the Add-to-cart button's id was renamed".
2. Click **Open the broken shop**: a new tab shows the shop with the change applied. Close it.
3. Tick **Watch it happen**, then **Break it and run the test**.
4. A browser window opens, slowed down: the store loads, the old selector fails, HealWright clicks the right button.
5. Back in the app, the progress steps tick through; the screenshots fill in (clean run, page at failure, after heal); the verdict says **Healed**.

> "The verdict is not HealWright's opinion: it comes from the store's own server log: the right action fired."

## 4. Live: the look-alike trap (60 s) · tab `/demo`

1. Pick **dev-07-distractor** (untick Watch it happen to save time), run it.

> "Here the real button was renamed and an identical-looking Cancel button sits in its place. A greedy healer clicks Cancel. HealWright's verifier sees the click would send a DELETE instead of the recorded POST, and refuses it."

Result: healed to the **true** target (or red). Never the look-alike.

## 5. The evidence for one heal (60 s) · click "Open heal event"

Walk the heal event page top to bottom:

- before / Set-of-Mark screenshots
- the decision timeline: Tier 1 → (Tier 2) → sandbox verification → live re-check → patch
- the candidate table with per-feature scores and the gate margin
- expected vs observed behaviour: the network calls compared
- the patch, and **Accept** / **Apply** (apply is optional; it edits the test file)

## 6. Results (75 s) · tab `/benchmarks` (or the chart PNGs in `docs/presentation/charts/`)

> "We built a benchmark of 50 frozen scenarios, 10 of them traps that must stay red, and ran six systems."

- **Heal rate**: HealWright 99.2% (3 runs).
- **False heals**: greedy healing 6 per run, HealWright 0 in every run.
- **The verifier experiment**: same recorded AI answers, verifier on vs off: 0 vs 3 false heals. That one switch is the difference.
- **No-AI share**: 92% of heals need no model call.
- Every HealWright patch applies cleanly with `git apply --check`.

## 7. Close (20 s)

> "HealWright fixes the selectors that broke for harmless reasons, proves each fix against recorded behaviour, and leaves the test red when it can't prove it. Self-healing tests that never lie."

---

## Likely questions

- **What if the AI is down or rate-limited?** It fails closed: the test stays red with the original error (`needs_human`). Tier 1 handles most heals without it.
- **Does it slow down green runs?** Recording adds about 21% to suite time on our laptop (measured, median of 5 runs). Zero AI calls on green runs.
- **Can it turn a passing test red?** No: release-gate invariant 2 (the 69-test suite passes 20 times in record mode and under each recorder fault).
- **Is the patch trustworthy?** Release-gate invariant 3: every dev-set patch applies on a clean checkout and the test then passes with HealWright turned off.
