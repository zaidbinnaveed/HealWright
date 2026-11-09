"""The no-verifier ablation must show what the verifier prevents.

dev-09-regression: the true target is gone and Tier 1 picks "Cancel order" with a
score the gate accepts (G1 finding). With the verifier the test must stay red; with
HEALWRIGHT_VERIFY=false the same pick is accepted and the run is a false heal.
Drives benchmark.run end to end (real pytest subprocess, real Chromium).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark.run import main

pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.mark.timeout(300)
@pytest.mark.parametrize(
    ("system", "expected"),
    [("healwright_noverify", "false_heal"), ("healwright", "red")],
)
def test_verifier_ablation_on_dev09_regression(system: str, expected: str, tmp_path: Path) -> None:
    code = main(
        [
            "--system",
            system,
            "--split",
            "dev",
            "--only",
            "dev-09-regression",
            "--vlm-mode",
            "replay",
            "--out",
            str(tmp_path),
        ]
    )
    assert code == 0
    (results,) = tmp_path.glob(f"*/{system}-dev/results.json")
    rows = json.loads(results.read_text(encoding="utf-8"))["rows"]
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["outcome"] == expected, row
    if expected == "false_heal":
        assert "cancel_order" in row["fired"], row
    else:
        assert "cancel_order" not in row["fired"], row
