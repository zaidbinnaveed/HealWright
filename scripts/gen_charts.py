"""Results charts as PNG for the slides, generated from the committed benchmark results.

    uv run python scripts/gen_charts.py

Reads benchmark/results/eval-combined/<system>/combined.json (via the API's combined view, so
the numbers are exactly the ones the app shows) and writes light and dark PNGs (1600x900) to
docs/presentation/charts/. Nothing is typed by hand.
"""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from healwright.api.app import combined_view  # noqa: E402

OUT = ROOT / "docs" / "presentation" / "charts"
ORDER = ["native", "greedy", "rawhtml", "tier1_only", "healwright_noverify", "healwright"]
LABEL = {
    "native": "Native Playwright",
    "greedy": "Greedy healing",
    "rawhtml": "Raw-HTML LLM",
    "tier1_only": "Tier 1 only",
    "healwright_noverify": "No verifier",
    "healwright": "HealWright",
}
THEMES = {
    "light": {
        "bg": "#ffffff",
        "ink": "#14161a",
        "muted": "#55606c",
        "grid": "#e6e8eb",
        "hw": "#047857",
        "ai": "#6d28d9",
        "base": "#9aa3ad",
        "bad": "#c62828",
    },
    "dark": {
        "bg": "#0f1114",
        "ink": "#eef1f4",
        "muted": "#9aa4af",
        "grid": "#262b31",
        "hw": "#34d399",
        "ai": "#a78bfa",
        "base": "#5b6470",
        "bad": "#f87171",
    },
}


def pct(v: float) -> str:
    return f"{v * 100:.1f}%".replace(".0%", "%")


def bars(
    title: str,
    subtitle: str,
    rows: list[tuple[str, float | None, str, str]],
    vmax: float,
    t: dict[str, str],
    fmt: Any,
) -> str:
    """Horizontal bar chart: rows = (label, value, colour key, note)."""
    left, right, top = 330, 1160, 190
    row_h = 92 if len(rows) > 3 else 220
    bar_h = 40 if len(rows) > 3 else 96
    pad = (row_h - bar_h) / 2 if len(rows) <= 3 else 12
    width = right - left
    parts = [
        f'<text x="80" y="92" font-size="44" font-weight="700" fill="{t["ink"]}">{escape(title)}</text>',
        f'<text x="80" y="140" font-size="26" fill="{t["muted"]}">{escape(subtitle)}</text>',
    ]
    for i in range(5):
        x = left + width * i / 4
        parts.append(
            f'<line x1="{x}" y1="{top - 20}" x2="{x}" y2="{top + row_h * len(rows)}" stroke="{t["grid"]}" stroke-width="2"/>'
        )
    for n, (label, value, colour, note) in enumerate(rows):
        y = top + n * row_h
        mid = y + pad + bar_h / 2 + 10  # text baseline, vertically centred on the bar
        bold = "700" if label == "HealWright" else "400"
        parts.append(
            f'<text x="{left - 24}" y="{mid}" font-size="28" font-weight="{bold}" '
            f'fill="{t["ink"]}" text-anchor="end">{escape(label)}</text>'
        )
        if value is None:
            parts.append(
                f'<text x="{left + 12}" y="{mid}" font-size="26" fill="{t["muted"]}">not applicable</text>'
            )
            continue
        w = max(4.0, width * min(value / vmax, 1.0)) if value > 0 else 0
        parts.append(
            f'<rect x="{left}" y="{y + pad}" width="{w:.1f}" height="{bar_h}" rx="6" fill="{t[colour]}"/>'
        )
        parts.append(
            f'<text x="{left + w + 16}" y="{mid}" font-size="28" font-weight="700" '
            f'fill="{t["ink"]}">{escape(fmt(value))}</text>'
        )
        if note:
            x = left + w + 16 + 14 * len(fmt(value)) + 30
            parts.append(
                f'<text x="{x}" y="{mid}" font-size="22" fill="{t["muted"]}">{escape(note)}</text>'
            )
    return "".join(parts)


def page(svg: str, t: dict[str, str], footer: str) -> str:
    return (
        f"<html><body style='margin:0;background:{t['bg']}'>"
        f"<svg xmlns='http://www.w3.org/2000/svg' width='1600' height='900' viewBox='0 0 1600 900' "
        f"font-family='Segoe UI, system-ui, sans-serif'><rect width='1600' height='900' fill='{t['bg']}'/>{svg}"
        f"<text x='80' y='860' font-size='20' fill='{t['muted']}'>{escape(footer)}</text></svg></body></html>"
    )


def colour(system: str) -> str:
    return "hw" if system == "healwright" else "ai" if system == "rawhtml" else "base"


def main() -> None:
    data = combined_view(ROOT / "benchmark" / "results")
    by = {s["system"]: s for s in data["systems"]}
    systems = [k for k in ORDER if k in by]
    traps = sum(1 for s in data["scenarios"] if s["class"].endswith("_trap"))
    footer = f"Chaos Benchmark, eval split: {len(data['scenarios'])} frozen scenarios ({traps} traps). Model systems: mean of 3 runs (1 record + 2 live)."

    def stat(k: str, metric: str) -> dict[str, Any]:
        return by[k]["summary"].get(metric) or {}

    def rng(k: str, metric: str, f: Any) -> str:
        s = stat(k, metric)
        return (
            f"range {f(s['min'])} to {f(s['max'])}"
            if s.get("min") is not None and s["min"] != s["max"]
            else ""
        )

    charts: dict[str, Any] = {
        "heal-rate": lambda t: bars(
            "True heal rate",
            "Healable scenarios healed to the right element. Higher is better.",
            [
                (
                    LABEL[k],
                    stat(k, "true_heal_rate").get("mean"),
                    colour(k),
                    rng(k, "true_heal_rate", pct),
                )
                for k in systems
            ],
            1.0,
            t,
            pct,
        ),
        "false-heals": lambda t: bars(
            "False heals on traps",
            f"Trap scenarios turned green the wrong way, per run (of {traps}). Lower is better.",
            [
                (
                    LABEL[k],
                    stat(k, "false_heals_on_traps").get("mean"),
                    "bad" if (stat(k, "false_heals_on_traps").get("mean") or 0) > 0 else colour(k),
                    "",
                )
                for k in systems
            ],
            max(1.0, max((stat(k, "false_heals_on_traps").get("mean") or 0) for k in systems)),
            t,
            lambda v: f"{v:g}",
        ),
        "verifier": lambda t: bars(
            "Same AI answers, verifier on vs off",
            "Run 1 of each used the same recorded Tier-2 replies. False heals on traps.",
            [
                ("Verifier ON", by["healwright"]["per_run"][0]["false_heals_on_traps"], "hw", ""),
                (
                    "Verifier OFF",
                    by["healwright_noverify"]["per_run"][0]["false_heals_on_traps"],
                    "bad",
                    "",
                ),
            ],
            max(1.0, float(by["healwright_noverify"]["per_run"][0]["false_heals_on_traps"] or 1)),
            t,
            lambda v: f"{v:g}",
        ),
        "no-ai-share": lambda t: bars(
            "Heals decided without an AI call",
            "Share of heals picked by the deterministic Tier-1 scorer.",
            [
                (
                    LABEL[k],
                    stat(k, "tier1_share_of_heals").get("mean"),
                    colour(k),
                    "one LLM call per step" if k == "rawhtml" else "",
                )
                for k in systems
                if k != "native"
            ],
            1.0,
            t,
            lambda v: pct(v),
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1600, "height": 900})
        for name, build in charts.items():
            for theme, t in THEMES.items():
                pg.set_content(page(build(t), t, footer))
                pg.screenshot(path=str(OUT / f"{name}-{theme}.png"))
        browser.close()
    print("wrote", sorted(f.name for f in OUT.glob("*.png")))


if __name__ == "__main__":
    main()
