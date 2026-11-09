"""LibCST patcher golden tests: literal, constant, f-string, CRLF,
repeated selectors, locator form, injection-proof names, git apply."""

from __future__ import annotations

import ast
import shutil
import subprocess
from pathlib import Path

import pytest

from healwright.errors import UnpatchableCallSite
from healwright.locators.synth import LocatorCall, SynthesizedLocator
from healwright.patcher import git_apply_check, make_patch, sha256_of

pytestmark = pytest.mark.unit

ROLE = SynthesizedLocator(
    "role",
    (LocatorCall("get_by_role", ("button",), (("name", "Confirm order"), ("exact", True))),),
)
LABEL = SynthesizedLocator("label", (LocatorCall("get_by_label", ("Email",), (("exact", True),)),))
SCOPED_NTH = SynthesizedLocator(
    "scoped_role",
    (
        LocatorCall("locator", ("#card-2",)),
        LocatorCall("get_by_role", ("button",), (("name", "Remove"), ("exact", True))),
        LocatorCall("nth", (1,)),
    ),
    fragile=True,
)


def write(tmp: Path, text: str, name: str = "test_x.py", newline: str = "\n") -> Path:
    path = tmp / name
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    return path


def apply_and_read(root: Path, path: Path, diff: str) -> str:
    ok, err = git_apply_check(root, diff)
    assert ok, err
    subprocess.run(
        ["git", "-c", "core.autocrlf=false", "apply", "-"],
        cwd=root,
        input=diff.encode(),
        check=True,
    )
    return path.read_bytes().decode("utf-8")


def test_literal_page_call(tmp_path: Path) -> None:
    src = 'def test_a(page):\n    page.goto("/order/1")\n    page.click("#confirm-order")\n'
    path = write(tmp_path, src)
    result = make_patch(tmp_path, path, 3, "click", "#confirm-order", "page", ROLE)
    expected = (
        'def test_a(page):\n    page.goto("/order/1")\n'
        "    page.get_by_role('button', name='Confirm order', exact=True).click()\n"
    )
    assert result.new_source == expected
    assert result.source_sha256 == sha256_of(path)
    assert "--- a/test_x.py" in result.diff
    assert apply_and_read(tmp_path, path, result.diff) == expected


def test_keeps_other_arguments(tmp_path: Path) -> None:
    src = 'def test_b(page):\n    page.fill("#email", "ada@example.com", timeout=2000)\n'
    path = write(tmp_path, src)
    result = make_patch(tmp_path, path, 2, "fill", "#email", "page", LABEL)
    assert result.new_source.splitlines()[1] == (
        "    page.get_by_label('Email', exact=True).fill(\"ada@example.com\", timeout=2000)"
    )


def test_locator_form(tmp_path: Path) -> None:
    src = 'def test_c(page):\n    page.locator(".buy-box .btn-primary").click()\n'
    path = write(tmp_path, src)
    result = make_patch(tmp_path, path, 2, "click", ".buy-box .btn-primary", "locator", ROLE)
    assert result.new_source.splitlines()[1] == (
        "    page.get_by_role('button', name='Confirm order', exact=True).click()"
    )


def test_scoped_nth_chain(tmp_path: Path) -> None:
    src = "def test_d(page):\n    page.click('#remove-2')\n"
    path = write(tmp_path, src)
    result = make_patch(tmp_path, path, 2, "click", "#remove-2", "page", SCOPED_NTH)
    assert result.new_source.splitlines()[1] == (
        "    page.locator('#card-2').get_by_role('button', name='Remove', exact=True).nth(1).click()"
    )


def test_constant_is_unpatchable(tmp_path: Path) -> None:
    src = 'SEL = "#confirm-order"\n\ndef test_e(page):\n    page.click(SEL)\n'
    path = write(tmp_path, src)
    with pytest.raises(UnpatchableCallSite):
        make_patch(tmp_path, path, 4, "click", "#confirm-order", "page", ROLE)


def test_f_string_is_unpatchable(tmp_path: Path) -> None:
    src = 'def test_f(page, i=1):\n    page.click(f"#item-{i}")\n'
    path = write(tmp_path, src)
    with pytest.raises(UnpatchableCallSite):
        make_patch(tmp_path, path, 2, "click", "#item-1", "page", ROLE)


def test_locator_in_variable_is_unpatchable(tmp_path: Path) -> None:
    src = 'def test_g(page):\n    btn = page.locator("#go")\n    btn.click()\n'
    path = write(tmp_path, src)
    with pytest.raises(UnpatchableCallSite):
        make_patch(tmp_path, path, 3, "click", "#go", "locator", ROLE)


def test_repeated_selector_only_patches_the_failing_line(tmp_path: Path) -> None:
    src = 'def test_h(page):\n    page.click("#confirm-order")\n    page.click("#confirm-order")\n'
    path = write(tmp_path, src)
    result = make_patch(tmp_path, path, 3, "click", "#confirm-order", "page", ROLE)
    lines = result.new_source.splitlines()
    assert lines[1] == '    page.click("#confirm-order")'
    assert lines[2].startswith("    page.get_by_role(")


def test_file_without_final_newline(tmp_path: Path) -> None:
    src = 'def test_n(page):\n    page.click("#confirm-order")'  # no trailing newline
    path = write(tmp_path, src)
    result = make_patch(tmp_path, path, 2, "click", "#confirm-order", "page", ROLE)
    assert "\\ No newline at end of file" in result.diff
    patched = apply_and_read(tmp_path, path, result.diff)
    assert patched.endswith("exact=True).click()")


def test_crlf_file_keeps_crlf(tmp_path: Path) -> None:
    src = 'def test_i(page):\n    page.goto("/")\n    page.click("#confirm-order")\n'
    path = write(tmp_path, src, newline="\r\n")
    result = make_patch(tmp_path, path, 3, "click", "#confirm-order", "page", ROLE)
    assert result.new_source.count("\r\n") == 3
    assert "\r\n" in result.diff
    patched = apply_and_read(tmp_path, path, result.diff)
    assert patched.count("\r\n") == 3
    assert "get_by_role" in patched


@pytest.mark.parametrize("name", ['Say "hi"', "x'); import os; ('", "back\\slash", "Ünïcödé ✓"])
def test_page_text_can_only_become_a_string_literal(tmp_path: Path, name: str) -> None:
    spec = SynthesizedLocator(
        "role", (LocatorCall("get_by_role", ("button",), (("name", name), ("exact", True))),)
    )
    path = write(tmp_path, 'def test_j(page):\n    page.click("#x")\n')
    result = make_patch(tmp_path, path, 2, "click", "#x", "page", spec)
    tree = ast.parse(result.new_source)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    for call in calls:
        for arg in [*call.args, *(k.value for k in call.keywords)]:
            assert isinstance(arg, ast.Constant)
    assert any(isinstance(n, ast.Constant) and n.value == name for n in ast.walk(tree))


def test_git_apply_check_rejects_stale_diff(tmp_path: Path) -> None:
    path = write(tmp_path, 'def test_k(page):\n    page.click("#a")\n')
    result = make_patch(tmp_path, path, 2, "click", "#a", "page", ROLE)
    path.write_text("def test_k(page):\n    page.click('#changed')\n", encoding="utf-8")
    ok, err = git_apply_check(tmp_path, result.diff)
    assert not ok
    assert err


def test_path_outside_repo_is_unpatchable(tmp_path: Path) -> None:
    inside = tmp_path / "repo"
    inside.mkdir()
    path = write(tmp_path, 'def test_l(page):\n    page.click("#a")\n')
    with pytest.raises(UnpatchableCallSite):
        make_patch(inside, path, 2, "click", "#a", "page", ROLE)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_diff_paths_are_repo_relative(tmp_path: Path) -> None:
    sub = tmp_path / "examples"
    sub.mkdir()
    path = write(sub, 'def test_m(page):\n    page.click("#a")\n')
    result = make_patch(tmp_path, path, 2, "click", "#a", "page", ROLE)
    assert result.diff.startswith("--- a/examples/test_x.py\n+++ b/examples/test_x.py\n")
    assert git_apply_check(tmp_path, result.diff)[0]
