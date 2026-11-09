"""Scenario model and element rendering for the Chaos Store.

Templates never hard-code an id, data-testid, class string, text or tag: they
ask the active ``Scenario`` for an element by key, and render layout regions
in the order the scenario gives. The default scenario is the unmutated store;
a mutation only changes the maps below, so new mutation classes never touch
template structure.

Ground truth is never written into element attributes. The server-side action
log is the only source of truth.
"""

from __future__ import annotations

import json
import re
import string
from pathlib import Path
from typing import Any, Literal

import yaml
from markupsafe import Markup, escape
from pydantic import BaseModel, ConfigDict, Field, model_validator

from chaos_store.elements import DEFAULT_ELEMENTS, DEFAULT_REGIONS, ElementSpec

SCENARIO_DIR = Path(__file__).parent / "scenarios"
SCENARIO_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
VOID_TAGS = frozenset({"input", "img", "br", "hr", "meta", "link"})
MUTATION_CLASSES = (
    "id_rename",
    "css_refactor",
    "copy_drift",
    "tag_to_aria",
    "layout_move",
    "i18n",
    "distractor_trap",
    "regression_trap",
)
MutationClass = Literal[
    "id_rename",
    "css_refactor",
    "copy_drift",
    "tag_to_aria",
    "layout_move",
    "i18n",
    "distractor_trap",
    "regression_trap",
]


class Mutation(BaseModel):
    """Per-element overrides. A ``None`` value removes the id/testid/attribute."""

    model_config = ConfigDict(extra="forbid")

    id_map: dict[str, str | None] = Field(default_factory=dict)
    testid_map: dict[str, str | None] = Field(default_factory=dict)
    class_map: dict[str, str] = Field(default_factory=dict)
    text_map: dict[str, str] = Field(default_factory=dict)
    tag_map: dict[str, str] = Field(default_factory=dict)
    attr_map: dict[str, dict[str, str | None]] = Field(default_factory=dict)
    order_map: dict[str, list[str]] = Field(default_factory=dict)  # region -> keys
    remove: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_keys(self) -> Mutation:
        keys: set[str] = set(self.remove)
        for mapping in (
            self.id_map,
            self.testid_map,
            self.class_map,
            self.text_map,
            self.tag_map,
            self.attr_map,
        ):
            keys |= set(mapping)
        unknown = keys - set(DEFAULT_ELEMENTS)
        if unknown:
            raise ValueError(f"mutation refers to unknown element keys: {sorted(unknown)}")
        for region, order in self.order_map.items():
            if region not in DEFAULT_REGIONS:
                raise ValueError(f"unknown region: {region!r}")
            allowed = set(DEFAULT_REGIONS[region])
            if not set(order) <= allowed or len(order) != len(set(order)):
                raise ValueError(f"order_map[{region!r}] must list distinct keys of that region")
        for key, tag in self.tag_map.items():
            ElementSpec(tag=tag)  # validates the tag name
            del key
        return self


class Expected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["healed", "red_or_true_heal", "red"]
    action_id: str | None = None


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(pattern=SCENARIO_ID.pattern)
    split: Literal["dev", "eval"] | None = None
    klass: MutationClass | None = Field(default=None, alias="class")
    test: str | None = None
    mutation: Mutation = Field(default_factory=Mutation)
    expected: Expected | None = None

    def element(self, key: str) -> ElementSpec:
        spec = DEFAULT_ELEMENTS[key]
        m = self.mutation
        attrs = dict(spec.attrs)
        for name, value in m.attr_map.get(key, {}).items():
            if value is None:
                attrs.pop(name, None)
            else:
                attrs[name] = value
        return spec.model_copy(
            update={
                "tag": m.tag_map.get(key, spec.tag),
                "id": m.id_map.get(key, spec.id),  # an explicit None removes the id
                "testid": m.testid_map.get(key, spec.testid),
                "classes": m.class_map.get(key, spec.classes),
                "text": m.text_map.get(key, spec.text),
                "attrs": attrs,
            }
        )

    def removed(self, key: str) -> bool:
        return key in self.mutation.remove

    def region(self, name: str) -> list[str]:
        order = self.mutation.order_map.get(name, list(DEFAULT_REGIONS[name]))
        return [k for k in order if not self.removed(k)]


DEFAULT_SCENARIO = Scenario(id="unmutated")


def parse_scenario_yaml(text: str) -> Scenario:
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("scenario YAML must be a mapping")
    return Scenario.model_validate(data)


def load_scenario(scenario_id: str, directory: Path = SCENARIO_DIR) -> Scenario:
    if not SCENARIO_ID.match(scenario_id):
        raise ValueError(f"invalid scenario id: {scenario_id!r}")
    for path in sorted(directory.rglob(f"{scenario_id}.yaml")):
        return parse_scenario_yaml(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(scenario_id)


def iter_scenarios(directory: Path = SCENARIO_DIR) -> list[Scenario]:
    return [
        parse_scenario_yaml(p.read_text(encoding="utf-8"))
        for p in sorted(directory.rglob("*.yaml"))
    ]


# --------------------------------------------------------------------------- rendering


class _StrictFormatter(string.Formatter):
    """str.format that only allows plain named fields (no attribute/index access)."""

    def get_field(self, field_name: str, args: Any, kwargs: Any) -> Any:
        if not field_name.isidentifier():
            raise ValueError(f"unsupported placeholder: {field_name!r}")
        return super().get_field(field_name, args, kwargs)


_FMT = _StrictFormatter()


def _fill(template: str, fmt: dict[str, Any]) -> str:
    return _FMT.vformat(template, (), fmt)


def _js(value: Any) -> str:
    return json.dumps(value, separators=(",", ":")).replace("<", "\\u003c")


class Renderer:
    """Jinja helper. ``ui.el("key", pid=3)`` renders one element from the scenario.

    ``close()`` (and therefore ``el()``) also emits the inline script that binds
    the element's JS handler and/or registers it as a ref, placed directly after
    the element. A removed element renders nothing, scripts included.
    """

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario

    def spec(self, key: str) -> ElementSpec:
        return self.scenario.element(key)

    def removed(self, key: str) -> bool:
        return self.scenario.removed(key)

    def region(self, name: str) -> list[str]:
        return self.scenario.region(name)

    def id(self, key: str, **fmt: Any) -> str | None:
        if self.removed(key):
            return None
        spec = self.spec(key)
        return _fill(spec.id, fmt) if spec.id is not None else None

    def open(self, key: str, extra: dict[str, str | None] | None = None, **fmt: Any) -> Markup:
        if self.removed(key):
            return Markup("")
        spec = self.spec(key)
        attrs: dict[str, str | None] = {}
        if spec.id is not None:
            attrs["id"] = _fill(spec.id, fmt)
        if spec.testid is not None:
            attrs["data-testid"] = _fill(spec.testid, fmt)
        if spec.classes:
            attrs["class"] = _fill(spec.classes, fmt)
        attrs.update({k: _fill(v, fmt) for k, v in spec.attrs.items()})
        for attr, target in spec.ref_attrs.items():
            attrs[attr] = self.id(target, **fmt)
        if extra:
            attrs.update(extra)
        parts = [spec.tag]
        for name, value in attrs.items():
            if value is None:
                continue
            parts.append(f'{escape(name)}="{escape(value)}"')
        return Markup("<" + " ".join(parts) + ">")

    def text(self, key: str, **fmt: Any) -> Markup:
        if self.removed(key):
            return Markup("")
        spec = self.spec(key)
        return escape(_fill(spec.text, fmt)) if spec.text else Markup("")

    def close(self, key: str, **fmt: Any) -> Markup:
        if self.removed(key):
            return Markup("")
        spec = self.spec(key)
        html = "" if spec.tag in VOID_TAGS else f"</{spec.tag}>"
        prev = "document.currentScript.previousElementSibling"
        if spec.action is not None:
            args = {name: fmt[name] for name in spec.bind_args}
            html += f"<script>cw.bind({prev},{_js(spec.action)},{_js(args)})</script>"
        if spec.ref is not None:
            html += f"<script>cw.ref({_js(spec.ref)},{prev})</script>"
        return Markup(html)

    def el(self, key: str, extra: dict[str, str | None] | None = None, **fmt: Any) -> Markup:
        return self.open(key, extra, **fmt) + self.text(key, **fmt) + self.close(key, **fmt)
