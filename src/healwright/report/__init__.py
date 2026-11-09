"""Self-contained HTML run report: one page per run, images inlined.

Reads only the run folder (``events.jsonl`` + ``artifacts/<event_id>/``) and writes
``report.html`` next to it. It never changes a test outcome: the plugin renders it at session
end inside a ``try`` (failure: report skipped, terminal summary still printed), and
``healwright report <run_id>`` renders it on demand.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Environment, select_autoescape

from healwright.models import HealEvent
from healwright.store.index import RunInfo

STATUS_LABEL = {
    "healed": "Healed",
    "suggested": "Suggested",
    "needs_human": "Needs human",
    "regression_suspected": "Regression suspected",
    "not_a_locator_failure": "Not a locator failure",
    "error": "Error",
}
FEATURES = ("role", "text", "attributes", "ancestors", "neighbors", "geometry")
MAX_IMAGE_BYTES = 5 * 1024 * 1024


@dataclass
class EventView:
    event: HealEvent
    images: dict[str, str] = field(default_factory=dict)  # name -> data URI
    report: dict[str, Any] | None = None

    @property
    def label(self) -> str:
        return STATUS_LABEL.get(self.event.decision.status, self.event.decision.status)


def _data_uri(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) > MAX_IMAGE_BYTES:
        return None
    mime = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _view(run_dir: Path, event: HealEvent) -> EventView:
    view = EventView(event)
    folder = run_dir / "artifacts" / event.id
    for name in ("before", "som"):
        file = event.artifacts.get(name)
        if file:
            uri = _data_uri(folder / file)
            if uri:
                view.images[name] = uri
    cand = event.artifacts.get("candidates")
    if cand:
        try:
            view.report = json.loads((folder / cand).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            view.report = None
    return view


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>HealWright run {{ run_id }}</title>
<style>
:root{--bg:#f7f8f9;--card:#fff;--ink:#14161a;--muted:#55606c;--line:#e3e6ea;--ok:#047857;--bad:#c62828;--ai:#6d28d9;--warn:#b45309;--info:#1d4ed8}
@media (prefers-color-scheme:dark){:root{--bg:#0f1114;--card:#171a1f;--ink:#eef1f4;--muted:#9aa4af;--line:#2a2f36;--ok:#34d399;--bad:#f87171;--ai:#a78bfa;--warn:#fbbf24;--info:#60a5fa}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px 20px 64px}h1{font-size:26px;margin:0 0 4px}h2{font-size:17px;margin:0}
.muted{color:var(--muted)}.mono,code,pre{font-family:ui-monospace,"Cascadia Code",Consolas,monospace;font-size:13px}
.summary{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0 28px}.pill{border:1px solid var(--line);border-radius:999px;padding:3px 12px;background:var(--card)}
.event{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;margin:0 0 22px}
.head{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:10px}
.status{font-weight:600;border-radius:999px;padding:2px 10px;font-size:13px;border:1px solid currentColor}
.healed{color:var(--ok)}.suggested{color:var(--info)}.needs_human{color:var(--warn)}.regression_suspected,.error{color:var(--bad)}.not_a_locator_failure{color:var(--muted)}
.change{border:1px solid var(--line);border-radius:10px;overflow:hidden;margin:10px 0}.change div{padding:8px 12px}
.broke{background:color-mix(in srgb,var(--bad) 10%,transparent);color:var(--bad);text-decoration:line-through}
.fixed{background:color-mix(in srgb,var(--ok) 10%,transparent);color:var(--ok)}
.shots{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin:14px 0}
figure{margin:0;border:1px solid var(--line);border-radius:10px;overflow:hidden}figure img{display:block;width:100%;height:auto;background:#fff}figcaption{padding:6px 10px;font-size:13px}
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:13px}th,td{text-align:left;padding:6px 8px;border-top:1px solid var(--line);vertical-align:top}
.bar{display:inline-block;height:6px;border-radius:3px;background:var(--ok);vertical-align:middle}
.chosen td{background:color-mix(in srgb,var(--ok) 8%,transparent)}
pre{background:#0b0d10;color:#e6e6e6;border-radius:10px;padding:12px;overflow:auto;margin:10px 0}
.add{color:#7ee2b8}.del{color:#ff9b9b}.hunk{color:#8ab4ff}
details{margin-top:8px}summary{cursor:pointer;color:var(--muted)}
</style></head><body><main>
<h1>HealWright run</h1>
<p class="muted mono">{{ run_id }} · {{ started_at }} · {{ views|length }} heal event{{ "" if views|length == 1 else "s" }}</p>
<div class="summary">{% for status, n in counts %}<span class="pill"><span class="{{ status }}">●</span> {{ n }} {{ labels[status] }}</span>{% endfor %}</div>
{% if not views %}<p class="muted">No heal events in this run.</p>{% endif %}
{% for v in views %}{% set e = v.event %}{% set d = e.decision %}
<section class="event" id="{{ e.id }}">
  <div class="head"><span class="status {{ d.status }}">{{ v.label }}</span>
  {% if d.tier %}<span class="pill">Tier {{ d.tier }}</span>{% endif %}
  <span class="mono muted">{{ e.key.test_nodeid }}</span>
  {% if e.timings_ms.get("total") is not none %}<span class="mono muted">{{ "%.2f"|format(e.timings_ms["total"] / 1000) }} s</span>{% endif %}</div>
  <div class="change mono"><div class="broke">page.{{ e.key.action }}({{ e.key.selector|tojson }})</div>
  {% if d.locator and d.status in ("healed", "suggested") %}<div class="fixed">{{ d.locator }}</div>{% else %}<div class="muted">No verified replacement: the original error was re-raised.</div>{% endif %}</div>
  <p>{{ d.reason }}</p>
  {% if v.images %}<div class="shots">{% if v.images.before %}<figure><img alt="Page at failure" src="{{ v.images.before }}"><figcaption>Page at failure</figcaption></figure>{% endif %}
  {% if v.images.som %}<figure><img alt="Set-of-Mark screenshot sent to the vision model" src="{{ v.images.som }}"><figcaption>Set-of-Mark (what the vision model saw)</figcaption></figure>{% endif %}</div>{% endif %}
  {% if v.report and v.report.candidates %}<h2>Candidates</h2>
  {% if v.report.gate %}<p class="muted">Gate: score ≥ {{ v.report.gate.tau }} and margin ≥ {{ v.report.gate.delta }}; this step: top {{ "%.3f"|format(v.report.gate.top_score or 0) }}, margin {{ "%.3f"|format(v.report.gate.margin) }}: {{ "accepted" if v.report.gate.accepted else "escalated" }}</p>{% endif %}
  <table><tr><th>#</th><th>Element</th><th>Score</th>{% for f in features %}<th>{{ f }}</th>{% endfor %}</tr>
  {% for c in v.report.candidates %}<tr class="{{ 'chosen' if d.chosen and d.chosen.index == c.index else '' }}"><td>{{ loop.index }}</td>
  <td>{{ c.fingerprint.accessible_name or c.fingerprint.text or c.fingerprint.tag }}<br><span class="mono muted">{{ c.fingerprint.tag }}</span></td>
  <td class="mono">{{ "%.3f"|format(c.score) }}</td>
  {% for f in features %}{% set s = c.feature_scores.get(f) %}<td>{% if s is not none %}<span class="bar" style="width:{{ (s * 48)|round|int }}px"></span> <span class="mono">{{ "%.2f"|format(s) }}</span>{% else %}<span class="muted">n/a</span>{% endif %}</td>{% endfor %}</tr>{% endfor %}</table>{% endif %}
  {% if d.verification %}{% set vr = d.verification %}<h2>Expected vs observed behaviour</h2>
  <p class="muted">Sandbox verification: <strong>{{ vr.outcome }}</strong>{% if vr.mismatches %}: {{ vr.mismatches|join("; ") }}{% endif %}</p>
  <table><tr><th></th><th>Recorded</th><th>Observed</th></tr>
  <tr><td>URL after</td><td class="mono">{{ vr.expected.url_after }}</td><td class="mono">{{ vr.observed.url_after if vr.observed else "n/a" }}</td></tr>
  <tr><td>API calls</td><td class="mono">{% for c in vr.expected.api_calls|sort(attribute="path_template") %}{{ c.method }} {{ c.path_template }} {{ c.status_class }}<br>{% endfor %}</td>
  <td class="mono">{% if vr.observed %}{% for c in vr.observed.api_calls|sort(attribute="path_template") %}{{ c.method }} {{ c.path_template }} {{ c.status_class }}<br>{% endfor %}{% else %}n/a{% endif %}</td></tr></table>{% endif %}
  {% if e.diff %}<h2>Patch</h2><pre>{% for line in e.diff.splitlines() %}<span class="{{ 'add' if line.startswith('+') and not line.startswith('+++') else 'del' if line.startswith('-') and not line.startswith('---') else 'hunk' if line.startswith('@@') else '' }}">{{ line }}</span>
{% endfor %}</pre><p class="muted">Apply with <code>healwright apply {{ e.id }}</code></p>{% endif %}
</section>{% endfor %}
</main></body></html>
"""

_ENV = Environment(autoescape=select_autoescape(default=True, default_for_string=True))


def render_run(info: RunInfo) -> str:
    views = [_view(info.dir, e) for e in info.events]
    counts: dict[str, int] = {}
    for v in views:
        counts[v.event.decision.status] = counts.get(v.event.decision.status, 0) + 1
    return _ENV.from_string(TEMPLATE).render(
        run_id=info.run_id,
        started_at=info.started_at,
        views=views,
        counts=sorted(counts.items()),
        labels=STATUS_LABEL,
        features=FEATURES,
    )


def write_report(info: RunInfo) -> Path:
    path = info.dir / "report.html"
    path.write_text(render_run(info), encoding="utf-8")
    return path
