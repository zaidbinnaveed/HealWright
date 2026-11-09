"""Turn a JUnit XML report into GitHub Actions error annotations (CI only).

    uv run python scripts/ci_annotate.py test-results.xml

Prints one ``::error`` workflow command per failed or errored test (name + the first lines
of the message), so failures show on the run's summary page and through the public API
without opening the job log. GitHub keeps at most 10 error annotations per step, so the
first 9 failures are listed and the last annotation gives the total.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MAX = 9


def escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_prop(text: str) -> str:
    """Property values (title=...) must also escape ':' and ','."""
    return escape(text).replace(":", "%3A").replace(",", "%2C")


def main() -> int:
    report = Path(sys.argv[1] if len(sys.argv) > 1 else "test-results.xml")
    if not report.is_file():
        print(
            f"::error title=No test report::{report} was not written (pytest crashed before the end?)"
        )
        return 0
    failures: list[tuple[str, str]] = []
    for case in ET.parse(report).getroot().iter("testcase"):
        for kind in ("failure", "error"):
            node = case.find(kind)
            if node is not None:
                name = f"{case.get('classname', '')}::{case.get('name', '')}"
                detail = (node.get("message") or "") + "\n" + (node.text or "")
                lines = [ln for ln in detail.strip().splitlines() if ln.strip()]
                failures.append((f"{kind}: {name}", "\n".join(lines[:12])[:1500]))
    for title, body in failures[:MAX]:
        print(f"::error title={escape_prop(title)[:250]}::{escape(body)}")
    if failures:
        names = "; ".join(t.split(": ", 1)[1] for t, _ in failures)
        print(f"::error title={len(failures)} failed test(s)::{escape(names[:3000])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
