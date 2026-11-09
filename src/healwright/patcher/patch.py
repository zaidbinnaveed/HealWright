"""LibCST patcher.

Only a selector LITERAL at the failing call site is replaced:

    page.click("#confirm-order")            -> page.get_by_role('button', name='Confirm order', exact=True).click()
    page.locator("#confirm-order").click()  -> page.get_by_role('button', name='Confirm order', exact=True).click()

Everything else (constants, variables, f-strings, page objects, a locator kept
in a variable) raises ``UnpatchableCallSite``; the caller then records
suggestion text instead of a diff.

New nodes are built from ``repr()`` of each value, never by concatenating page
text into source code, so a name like ``x'); import os; ('`` can only ever end
up inside a string literal. The file's line endings (CRLF or LF) are preserved
and every diff is checked with ``git apply --check``.
"""

from __future__ import annotations

import difflib
import hashlib
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

from healwright.errors import PatchError, UnpatchableCallSite
from healwright.locators.synth import LocatorCall, SynthesizedLocator

ACTIONS = frozenset({"click", "fill", "check", "uncheck", "press", "select_option", "hover"})


@dataclass(frozen=True)
class PatchResult:
    diff: str
    new_source: str
    source_sha256: str


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _literal(value: Any) -> cst.BaseExpression:
    """A LibCST node for a Python literal, built from ``repr()`` (never concatenation)."""
    if not isinstance(value, (str, int, bool)) or value is None:
        raise PatchError(f"unsupported literal type: {type(value).__name__}")
    node = cst.parse_expression(repr(value))
    if not isinstance(node, (cst.SimpleString, cst.Integer, cst.Name, cst.UnaryOperation)):
        raise PatchError("literal did not parse to a literal node")
    return node


def _chain(receiver: cst.BaseExpression, calls: Sequence[LocatorCall]) -> cst.BaseExpression:
    expr = receiver
    for call in calls:
        args = [cst.Arg(value=_literal(a)) for a in call.args]
        args += [
            cst.Arg(
                keyword=cst.Name(k),
                value=_literal(v),
                equal=cst.AssignEqual(
                    whitespace_before=cst.SimpleWhitespace(""),
                    whitespace_after=cst.SimpleWhitespace(""),
                ),
            )
            for k, v in call.kwargs
        ]
        expr = cst.Call(func=cst.Attribute(value=expr, attr=cst.Name(call.method)), args=args)
    return expr


def _string_value(node: cst.BaseExpression) -> str | None:
    """Value of a plain string literal (no f-string, no implicit concatenation)."""
    if isinstance(node, cst.SimpleString):
        evaluated = node.evaluated_value
        return evaluated if isinstance(evaluated, str) else None
    return None


class _Rewriter(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(
        self, line: int, action: str, selector: str, via: str, spec: SynthesizedLocator
    ) -> None:
        self.line = line
        self.action = action
        self.selector = selector
        self.via = via
        self.spec = spec
        self.matches = 0
        self.seen_call_on_line = False

    def leave_Call(  # noqa: N802 - LibCST visitor naming
        self, original: cst.Call, updated: cst.Call
    ) -> cst.BaseExpression:
        pos = self.get_metadata(PositionProvider, original)
        if not (pos.start.line <= self.line <= pos.end.line):
            return updated
        func = updated.func
        if not isinstance(func, cst.Attribute) or func.attr.value != self.action:
            return updated
        self.seen_call_on_line = True
        if self.via == "page":
            if not updated.args or updated.args[0].keyword is not None:
                return updated
            if _string_value(updated.args[0].value) != self.selector:
                return updated
            receiver, rest = func.value, list(updated.args[1:])
        else:  # X.locator("<selector>").<action>(...)
            inner = func.value
            if not (
                isinstance(inner, cst.Call)
                and isinstance(inner.func, cst.Attribute)
                and inner.func.attr.value == "locator"
                and len(inner.args) == 1
                and inner.args[0].keyword is None
                and _string_value(inner.args[0].value) == self.selector
            ):
                return updated
            receiver, rest = inner.func.value, list(updated.args)
        self.matches += 1
        new_target = _chain(receiver, self.spec.calls)
        return updated.with_changes(
            func=cst.Attribute(value=new_target, attr=cst.Name(self.action)), args=rest
        )


def _rewrite(
    source: str, line: int, action: str, selector: str, via: str, spec: SynthesizedLocator
) -> str:
    try:
        module = cst.parse_module(source)
    except cst.ParserSyntaxError as exc:
        raise PatchError(f"test file does not parse: {exc}") from exc
    rewriter = _Rewriter(line, action, selector, via, spec)
    new_module = MetadataWrapper(module).visit(rewriter)
    if rewriter.matches == 0:
        raise UnpatchableCallSite(
            f"no `{action}` call with the literal selector {selector!r} at line {line} "
            "(constant, variable, f-string or page object)"
        )
    if rewriter.matches > 1:
        raise UnpatchableCallSite(f"{rewriter.matches} matching calls at line {line}: ambiguous")
    return new_module.code


def make_patch(
    repo_root: Path,
    test_file: Path,
    line: int,
    action: str,
    selector: str,
    via: str,
    spec: SynthesizedLocator,
) -> PatchResult:
    """Unified diff (paths relative to ``repo_root``) replacing one selector literal."""
    if action not in ACTIONS:
        raise UnpatchableCallSite(f"action {action!r} is not patchable")
    raw = test_file.read_bytes()
    source = raw.decode("utf-8")
    new_source = _rewrite(source, line, action, selector, via, spec)
    try:
        rel = test_file.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise UnpatchableCallSite(f"{test_file} is outside {repo_root}") from exc
    diff_lines = difflib.unified_diff(
        source.splitlines(keepends=True),
        new_source.splitlines(keepends=True),
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
    )
    # difflib does not emit git's marker for a last line without a newline; without it
    # the patch is corrupt for every test file that does not end in a newline.
    diff = "".join(
        line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
        for line in diff_lines
    )
    if not diff:
        raise PatchError("rewrite produced no change")
    return PatchResult(
        diff=diff, new_source=new_source, source_sha256=hashlib.sha256(raw).hexdigest()
    )


def git_apply_check(repo_root: Path, diff: str) -> tuple[bool, str]:
    """Run ``git apply --check`` in ``repo_root`` (works in and outside git repos)."""
    try:
        proc = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "apply", "--check", "-"],
            cwd=repo_root,
            input=diff.encode("utf-8"),
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"git apply could not run: {type(exc).__name__}"
    return proc.returncode == 0, proc.stderr.decode("utf-8", "replace").strip()


def suggestion(
    test_file: Path, line: int, selector: str, spec: SynthesizedLocator, receiver: str = "page"
) -> str:
    return (
        f"{test_file.name}:{line}: replace the selector {selector!r} with "
        f"{spec.code(receiver)} (HealWright could not patch this call site automatically)"
    )


__all__ = ["PatchResult", "git_apply_check", "make_patch", "sha256_of", "suggestion"]
