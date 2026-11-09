"""HTML run report: renders for every status, self-contained, escaped."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ulid import ULID

from healwright.cli import main as cli_main
from healwright.report import STATUS_LABEL, render_run, write_report
from healwright.store.index import load_run
from tests.factories import decision, heal_event

pytestmark = pytest.mark.unit

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def make_run(tmp_path: Path) -> Path:
    run_id = str(ULID())
    run = tmp_path / "runs" / run_id
    run.mkdir(parents=True)
    events = []
    for status in STATUS_LABEL:
        healed = status in ("healed", "suggested")
        e = heal_event(
            id=str(ULID()),
            run_id=run_id,
            decision=decision(
                status=status,
                tier=1 if healed else None,
                locator="page.get_by_role('button', name='Confirm order')" if healed else None,
                chosen=None,
                verification=None,
                reason=f"reason for {status} <script>alert(1)</script>",
            ),
            artifacts={"before": "before.png", "candidates": "candidates.json"}
            if status == "healed"
            else {},
            diff='--- a/t.py\n+++ b/t.py\n@@ -1 +1 @@\n-    page.click("#old")\n+    page.click("#new")\n'
            if status == "healed"
            else None,
            source_sha256=None,
        )
        events.append(e)
        if status == "healed":
            art = run / "artifacts" / e.id
            art.mkdir(parents=True)
            (art / "before.png").write_bytes(PNG)
            (art / "candidates.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "gate": {
                            "accepted": True,
                            "top_score": 0.93,
                            "second_score": 0.4,
                            "margin": 0.53,
                            "reason": "",
                            "tau": 0.7,
                            "delta": 0.06,
                            "tier2_floor": 0.5,
                            "compatible_candidates": 3,
                        },
                        "candidates": [
                            {
                                "index": 0,
                                "score": 0.93,
                                "feature_scores": {"role": 1.0, "text": 0.8},
                                "fingerprint": {
                                    "accessible_name": "confirm order",
                                    "text": "",
                                    "tag": "button",
                                },
                            }
                        ],
                        "attempts": [],
                        "live_check": None,
                    }
                ),
                encoding="utf-8",
            )
    (run / "events.jsonl").write_text(
        "\n".join(e.model_dump_json() for e in events) + "\n", encoding="utf-8"
    )
    return run


def test_report_renders_every_status_self_contained_and_escaped(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    info = load_run(tmp_path, run.name)
    assert info is not None
    html = render_run(info)
    for label in STATUS_LABEL.values():
        assert label in html
    assert "data:image/png;base64," in html  # screenshots are inlined
    assert "<script>alert(1)</script>" not in html  # page-derived text is escaped
    assert "&lt;script&gt;" in html
    assert "confirm order" in html  # candidate table
    assert 'page.click("#new")' in html or "page.click(&#34;#new&#34;)" in html
    assert "healwright apply" in html
    assert "http://" not in html
    assert "https://" not in html


def test_report_is_written_next_to_the_events(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    info = load_run(tmp_path, run.name)
    assert info is not None
    path = write_report(info)
    assert path == run / "report.html"
    assert path.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_cli_report_writes_and_prints_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = make_run(tmp_path)
    monkeypatch.setenv("HEALWRIGHT_ARTIFACT_DIR", str(tmp_path))
    assert cli_main(["report", run.name]) == 0
    assert capsys.readouterr().out.strip() == str(run / "report.html")
    assert cli_main(["report", str(ULID())]) == 1
    assert "NOT_FOUND" in capsys.readouterr().err
