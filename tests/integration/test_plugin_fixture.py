"""The plugin's ``page`` override, modes and guards, in real inner pytest sessions."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

INNER = """
from playwright.sync_api import Page, expect

def test_inner(page: Page) -> None:
    print("PAGE_TYPE=" + type(page).__name__)
    page.set_content("<button id='b' onclick=\\"this.textContent='done'\\">b</button>")
    page.click("#b")
    expect(page.locator("#b")).to_have_text("done")
"""


def run(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, **env: str) -> pytest.RunResult:
    for name in ("HEALWRIGHT_MODE", "PYTEST_XDIST_WORKER"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    pytester.makepyfile(test_inner=INNER)
    return pytester.runpytest_subprocess("-s", "-p", "no:cacheprovider", timeout=120)


def page_type(result: pytest.RunResult) -> str:
    for line in result.outlines:
        if "PAGE_TYPE=" in line:
            return line.split("PAGE_TYPE=", 1)[1].strip()
    raise AssertionError("\n".join(result.outlines))


@pytest.mark.parametrize("mode", ["record", "heal"])
def test_page_is_proxied_when_on(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    result = run(pytester, monkeypatch, HEALWRIGHT_MODE=mode)
    result.assert_outcomes(passed=1)
    assert page_type(result) == "PageProxy"


def test_off_mode_leaves_pytest_playwright_untouched(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = run(pytester, monkeypatch, HEALWRIGHT_MODE="off")
    result.assert_outcomes(passed=1)
    assert page_type(result) == "Page"


def test_cli_option_overrides_env(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HEALWRIGHT_MODE", "record")
    pytester.makepyfile(test_inner=INNER)
    result = pytester.runpytest_subprocess("-s", "--healwright-mode", "off", timeout=120)
    result.assert_outcomes(passed=1)
    assert page_type(result) == "Page"


def test_xdist_worker_disables_plugin_with_warning(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = run(pytester, monkeypatch, HEALWRIGHT_MODE="record", PYTEST_XDIST_WORKER="gw0")
    assert result.parseoutcomes()["passed"] == 1  # warning count includes upstream ones
    assert page_type(result) == "Page"
    result.stdout.fnmatch_lines(["*HealWright disabled: pytest-xdist*"])


def test_invalid_config_disables_plugin_with_warning(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = run(pytester, monkeypatch, HEALWRIGHT_MODE="sometimes")
    assert result.parseoutcomes()["passed"] == 1  # warning count includes upstream ones
    assert page_type(result) == "Page"
    result.stdout.fnmatch_lines(["*HealWright disabled: invalid configuration*"])


def test_disable_with_no_flag(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEALWRIGHT_MODE", "record")
    pytester.makepyfile(test_inner=INNER)
    result = pytester.runpytest_subprocess("-s", "-p", "no:healwright", timeout=120)
    result.assert_outcomes(passed=1)
    assert page_type(result) == "Page"


def test_baselines_persist_in_the_repo_folder_between_runs(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no HEALWRIGHT_BASELINE_DIR, baselines live in
    <rootdir>/.healwright/baselines/ (to be committed with the tests) and survive runs."""
    monkeypatch.delenv("HEALWRIGHT_BASELINE_DIR", raising=False)
    monkeypatch.setenv("HEALWRIGHT_ARTIFACT_DIR", str(pytester.path / "elsewhere"))
    run(pytester, monkeypatch, HEALWRIGHT_MODE="record").assert_outcomes(passed=1)
    files = list((pytester.path / ".healwright" / "baselines").rglob("*.json"))
    assert len(files) == 1, files
    first = files[0].read_text(encoding="utf-8")
    assert '"observations": 1' in first.replace(" ", "").replace('":', '": ')
    run(pytester, monkeypatch, HEALWRIGHT_MODE="record").assert_outcomes(passed=1)
    second = files[0].read_text(encoding="utf-8")
    assert second != first  # the second run merged into the SAME file on disk
    assert '"observations": 2' in second.replace(" ", "").replace('":', '": ')
    assert not (pytester.path / "elsewhere" / "baselines").exists()  # not under artifact_dir
