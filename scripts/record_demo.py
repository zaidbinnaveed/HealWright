"""Record the backup demo video (silent, captioned) by driving the running app with Playwright.

    uv run healwright serve                    # in another terminal, http://127.0.0.1:8000
    uv run python scripts/record_demo.py       # -> docs/presentation/healwright-demo.webm

Follows docs/presentation/demo-script.md: overview, the broken shop, a heal (dev-01), the
look-alike trap (dev-07), the heal event evidence, the benchmark page. The demo runs are real
(replay mode, recorded model replies); nothing is staged. Run it with the machine otherwise idle.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, ViewportSize, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "presentation" / "healwright-demo.webm"
SIZE: ViewportSize = {"width": 1366, "height": 768}
RUN_TIMEOUT_MS = 240_000

CAPTION_JS = """text => {
  let el = document.getElementById('__demo_caption');
  if (!el) {
    el = document.createElement('div');
    el.id = '__demo_caption';
    el.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:99999;' +
      'max-width:1100px;padding:12px 22px;border-radius:12px;background:rgba(15,17,20,.88);color:#fff;' +
      'font:500 20px/1.4 "Segoe UI",system-ui,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,.35);text-align:center';
    document.body.appendChild(el);
  }
  el.textContent = text;
}"""


def caption(page: Page, text: str, hold_ms: int = 3500) -> None:
    page.evaluate(CAPTION_JS, text)
    page.wait_for_timeout(hold_ms)


def scroll(page: Page, to: int, steps: int = 8, pause_ms: int = 180) -> None:
    start = page.evaluate("window.scrollY")
    for i in range(1, steps + 1):
        page.evaluate("y => window.scrollTo(0, y)", start + (to - start) * i / steps)
        page.wait_for_timeout(pause_ms)


def pick(page: Page, scenario: str) -> None:
    page.get_by_role("radio").filter(has_text=scenario).click()


def run_and_wait(page: Page) -> None:
    page.get_by_role("button", name="2. Break it and run the test").click()
    page.wait_for_timeout(1500)
    expect(page.get_by_role("button", name="2. Break it and run the test")).to_be_enabled(
        timeout=RUN_TIMEOUT_MS
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--theme", choices=["light", "dark"], default="light")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    videos = Path(tempfile.mkdtemp(prefix="hw-video-"))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport=SIZE,
            record_video_dir=str(videos),
            record_video_size=SIZE,
            color_scheme=args.theme,
        )
        # The app keeps its own theme in localStorage ("hw-theme"), which wins over the
        # browser's colour scheme: set it before any page script runs.
        context.add_init_script(
            f"try {{ localStorage.setItem('hw-theme', '{args.theme}'); }} catch (e) {{}}"
        )
        page = context.new_page()

        # 1. The problem
        page.goto(base + "/")
        caption(page, "HealWright: self-healing Playwright tests that never fake a pass.", 4500)
        caption(
            page, "Selectors break for harmless reasons. Greedy healers can turn real bugs green."
        )
        scroll(page, 700)
        caption(page, "HealWright heals only when the new element does what the old one did.", 4500)
        scroll(page, 1500)
        page.wait_for_timeout(2500)

        # 2. The broken shop (same tab instead of a new one, so it is in the recording)
        page.goto(base + "/demo")
        pick(page, "dev-01-id-rename")
        caption(page, "Scenario dev-01: the Add-to-cart button's id was renamed.")
        req = urllib.request.Request(
            base + "/api/v1/demo/shop",
            data=json.dumps({"scenario_id": "dev-01-id-rename"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as res:
            shop_url = json.loads(res.read())["url"]
        # The test's own page: enter the scenario's session, land on /product/1.
        page.goto(shop_url.replace("next=/", "next=/product/1", 1))
        caption(page, "The broken shop, on the product page the test opens.", 3500)
        old_matches = page.locator("#add-to-cart").count()
        button = page.get_by_role("button", name="Add to cart")
        button.evaluate(
            "el => { el.style.outline = '4px solid #e5484d'; el.style.outlineOffset = '4px'; }"
        )
        caption(
            page,
            "The Add to cart button looks the same to a user, but its id changed: "
            f"the test's #add-to-cart matches {old_matches} elements.",
            5000,
        )
        new_id = button.get_attribute("id")
        caption(page, f"Same button, new id: #{new_id}. Exactly the change HealWright should heal.")

        # 3. A harmless change heals
        page.goto(base + "/demo")
        pick(page, "dev-01-id-rename")
        caption(page, "Break the page and run the real test, HealWright in heal mode.", 2500)
        run_and_wait(page)
        caption(
            page,
            "Healed. The verdict comes from the store's own server log: the right action fired.",
            4500,
        )
        scroll(page, 900)
        caption(page, "Clean run, page at failure, and how the healed run ended.", 4500)

        # 4. The evidence
        page.get_by_role("link", name="Open heal event").first.click()
        page.wait_for_load_state("networkidle")
        caption(
            page, "Every heal leaves evidence: screenshots, the decision, the candidates.", 4000
        )
        scroll(page, 900, steps=10)
        caption(page, "Candidate scores per feature, and the gate margin.", 3500)
        scroll(page, 1900, steps=10)
        caption(page, "Recorded vs observed network behaviour, then the patch to review.", 4500)
        scroll(page, 3200, steps=10)
        page.wait_for_timeout(2500)

        # 5. The look-alike trap
        page.goto(base + "/demo")
        pick(page, "dev-07-distractor")
        caption(
            page,
            "Trap dev-07: the real Confirm button was renamed; a look-alike Cancel button took its place.",
            5000,
        )
        run_and_wait(page)
        caption(
            page,
            "Cancel would send DELETE instead of the recorded POST. The verifier never picks it.",
            5000,
        )
        scroll(page, 700)
        page.wait_for_timeout(3000)

        # 6. Results
        page.goto(base + "/benchmarks")
        caption(page, "Chaos Benchmark: 50 frozen scenarios, 10 of them traps, six systems.", 4500)
        scroll(page, 600)
        caption(page, "HealWright: 99.2% true heal rate and 0 false heals in every run.", 5000)
        scroll(page, 1400)
        caption(
            page, "Same AI answers with the verifier switched off: 3 false heals per run.", 5000
        )
        page.goto(base + "/")
        caption(page, "HealWright. Self-healing tests that never lie.", 4000)

        video = page.video
        context.close()
        browser.close()
        assert video is not None
        OUT.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(video.path(), OUT)
    shutil.rmtree(videos, ignore_errors=True)
    print("wrote", OUT, f"{OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
