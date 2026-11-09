"""Generate the HealWright brand assets into frontend/public/.

    uv run python scripts/fetch_fonts.py   # once: display/body fonts for the social card
    uv run python scripts/gen_brand.py

Writes favicon.svg (light/dark aware), favicon.ico (16/32/48), favicon-16.png, favicon-32.png,
apple-touch-icon.png (180), icon-192.png, icon-512.png, site.webmanifest and og.png (1200x630).
Rasters are rendered from the SVG/HTML with headless Chromium (Playwright), the .ico with Pillow.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "frontend" / "public"
FONTS = PUBLIC / "fonts"

BG = "#0A0B0D"

# The mark on a 32 grid: rounded square, check whose short arm is broken and bridged by a node.
MARK_BODY = """
  <path d="M7.8 15.8 L9 17" />
  <circle cx="11.2" cy="19.2" r="1.25" stroke="none" fill="#fff" />
  <path d="M13.3 21.3 L14 22 L24 11" />
"""


def mark_svg(light: tuple[str, str], dark: tuple[str, str] | None = None, *, pad: float = 0) -> str:
    size = 32 + 2 * pad
    style = ""
    if dark:
        style = (
            "<style>.a{stop-color:" + light[0] + "}.b{stop-color:" + light[1] + "}"
            "@media (prefers-color-scheme: dark){.a{stop-color:"
            + dark[0]
            + "}.b{stop-color:"
            + dark[1]
            + "}}</style>"
        )
        stops = '<stop offset="0" class="a"/><stop offset="1" class="b"/>'
    else:
        stops = (
            f'<stop offset="0" stop-color="{light[0]}"/><stop offset="1" stop-color="{light[1]}"/>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-pad} {-pad} {size} {size}">{style}'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">{stops}</linearGradient></defs>'
        '<rect x="1" y="1" width="30" height="30" rx="9" fill="url(#g)"/>'
        '<g fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'
        f"{MARK_BODY}</g></svg>"
    )


LIGHT = ("#059669", "#0D9488")  # deeper on light browser chrome
DARK = ("#34D399", "#14B8A6")  # brighter on dark browser chrome

OG_HTML = """<!doctype html><html><head><style>
@font-face{font-family:Clash;src:url('%(fonts)s/ClashDisplay-Variable.woff2') format('woff2');font-weight:200 700}
@font-face{font-family:Satoshi;src:url('%(fonts)s/Satoshi-Variable.woff2') format('woff2');font-weight:300 900}
*{margin:0;box-sizing:border-box}
body{width:1200px;height:630px;background:%(bg)s;color:#F3F5F7;font-family:Satoshi,sans-serif;overflow:hidden;position:relative}
.grid{position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.035) 1px,transparent 1px);background-size:48px 48px;mask-image:radial-gradient(ellipse 80%% 70%% at 70%% 40%%,#000,transparent)}
.glow{position:absolute;width:820px;height:820px;right:-260px;top:-360px;background:radial-gradient(circle,rgba(52,211,153,.22),transparent 62%%)}
.wrap{position:absolute;inset:72px 80px;display:flex;flex-direction:column;justify-content:space-between}
.brand{display:flex;align-items:center;gap:22px;font-family:Clash;font-weight:600;font-size:40px;letter-spacing:-.02em}
.brand svg{width:64px;height:64px}
h1{font-family:Clash;font-weight:600;font-size:86px;line-height:.98;letter-spacing:-.035em;max-width:900px}
h1 em{font-style:normal;color:#34D399}
.code{font-family:ui-monospace,Consolas,monospace;font-size:24px;display:flex;flex-direction:column;gap:10px}
.r{color:#F87171;text-decoration:line-through;text-decoration-thickness:2px}
.g{color:#34D399}
.row{display:flex;justify-content:space-between;align-items:flex-end}
.tag{font-size:22px;color:#A3ABB5;letter-spacing:.02em}
</style></head><body><div class="grid"></div><div class="glow"></div>
<div class="wrap"><div class="brand">%(mark)s HealWright</div>
<h1>Self-healing tests<br>that <em>never lie.</em></h1>
<div class="row"><div class="code"><span class="r">page.click("#checkout-btn")</span>
<span class="g">page.get_by_role("button", name="Checkout").click()  &#10003;</span></div>
<div class="tag">Verified heals for Playwright</div></div></div></body></html>"""


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "favicon.svg").write_text(mark_svg(LIGHT, DARK), encoding="utf-8")
    flat = mark_svg(DARK)
    maskable = mark_svg(DARK, pad=6)  # safe zone for maskable icons
    pngs: dict[int, bytes] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        for size, svg in [
            (16, flat),
            (32, flat),
            (48, flat),
            (180, flat),
            (192, maskable),
            (512, maskable),
        ]:
            page.set_viewport_size({"width": size, "height": size})
            sized = svg.replace("<svg ", '<svg width="100%" height="100%" ')
            background = BG if size >= 180 else "transparent"
            page.set_content(
                f"<html><body style='margin:0;background:{background}'>"
                f"<div style='width:{size}px;height:{size}px'>{sized}</div></body></html>"
            )
            pngs[size] = page.screenshot(omit_background=size < 180)
        page.set_viewport_size({"width": 1200, "height": 630})
        og = OG_HTML % {"fonts": FONTS.as_uri(), "bg": BG, "mark": mark_svg(DARK)}
        og_file = FONTS.parent / "_og.html"  # a file:// page may load the file:// fonts
        og_file.write_text(og, encoding="utf-8")
        page.goto(og_file.as_uri())
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(400)
        og_file.unlink()
        (PUBLIC / "og.png").write_bytes(page.screenshot())
        browser.close()
    (PUBLIC / "favicon-16.png").write_bytes(pngs[16])
    (PUBLIC / "favicon-32.png").write_bytes(pngs[32])
    (PUBLIC / "apple-touch-icon.png").write_bytes(pngs[180])
    (PUBLIC / "icon-192.png").write_bytes(pngs[192])
    (PUBLIC / "icon-512.png").write_bytes(pngs[512])
    images = [Image.open(io.BytesIO(pngs[s])).convert("RGBA") for s in (16, 32, 48)]
    images[2].save(
        PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)], append_images=images[:2]
    )
    manifest = {
        "name": "HealWright",
        "short_name": "HealWright",
        "description": "Self-healing Playwright tests that prove every fix.",
        "start_url": "/",
        "display": "standalone",
        "theme_color": BG,
        "background_color": BG,
        "icons": [
            {
                "src": "/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": "/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
    }
    (PUBLIC / "site.webmanifest").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print("wrote", sorted(p.name for p in PUBLIC.iterdir() if p.is_file()))


if __name__ == "__main__":
    main()
