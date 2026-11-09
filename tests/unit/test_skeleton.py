"""Smoke test: the package and every Phase 0 subpackage import."""

import importlib

import pytest

MODULES = [
    "healwright",
    "healwright.config",
    "healwright.models",
    "healwright.errors",
    "healwright.engine",
    "healwright.cli",
    "healwright.plugin",
    "healwright.recorder",
    "healwright.store",
    "healwright.tier1",
    "healwright.tier2",
    "healwright.tier2.providers",
    "healwright.locators",
    "healwright.verify",
    "healwright.patcher",
    "healwright.report",
]


@pytest.mark.unit
@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name: str) -> None:
    importlib.import_module(name)


@pytest.mark.unit
def test_cli_without_a_command_exits_with_usage_error() -> None:
    from healwright.cli import main

    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
