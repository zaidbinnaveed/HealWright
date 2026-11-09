"""Hang capture: whole-process stack dump from inside a benchmark pytest subprocess.

Loaded by ``benchmark/run.py`` with ``-p benchmark.ki10_faulthandler`` when
``HW_KI10_DUMP`` names a file. Arms ``faulthandler.dump_traceback_later`` once at
start-up and never cancels it, so a hang anywhere in the interpreter (collection,
a test item, session end, atexit / interpreter exit) writes every thread's stack
to that file. pytest-timeout only covers test items; this covers the rest.
Reporting only: it never changes an outcome.
"""

from __future__ import annotations

import faulthandler
import os
from typing import IO, Any

_DUMP: IO[str] | None = None


def pytest_configure(config: Any) -> None:
    global _DUMP
    path = os.environ.get("HW_KI10_DUMP")
    if not path or _DUMP is not None:
        return
    _DUMP = open(path, "w", encoding="utf-8")  # noqa: SIM115 - must outlive the session
    delay = float(os.environ.get("HW_KI10_DUMP_AFTER_S", "200"))
    faulthandler.dump_traceback_later(delay, repeat=False, file=_DUMP, exit=False)
