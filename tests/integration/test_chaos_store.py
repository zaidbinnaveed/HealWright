"""Chaos Store skeleton: sessions, action log, control routes, scenarios."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chaos_store.app import create_app
from chaos_store.catalog import PRODUCTS
from chaos_store.elements import DEFAULT_ELEMENTS
from chaos_store.scenario import load_scenario
from chaos_store.state import SESSION_COOKIE

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parents[1] / "fixtures" / "scenarios"
CSS_YAML = (FIXTURES / "fixture-css-refactor.yaml").read_text(encoding="utf-8")


@pytest.fixture
def app():  # type: ignore[no-untyped-def]
    return create_app(control=True)


def client_for(app) -> TestClient:  # type: ignore[no-untyped-def]
    return TestClient(app)


def session_of(client: TestClient) -> str:
    client.get("/")
    sid = client.cookies.get(SESSION_COOKIE)
    assert sid
    return sid


# ------------------------------------------------------------------ pages


def test_catalog_lists_eight_deterministic_products(app) -> None:  # type: ignore[no-untyped-def]
    html = client_for(app).get("/").text
    assert len(PRODUCTS) == 8
    for p in PRODUCTS:
        assert f'href="/product/{p.id}"' in html
        assert p.name in html


def test_product_page_renders_default_elements(app) -> None:  # type: ignore[no-untyped-def]
    res = client_for(app).get("/product/1")
    assert res.status_code == 200
    html = res.text
    assert '<button id="add-to-cart" data-testid="add-to-cart" class="btn btn-primary"' in html
    assert '<label class="field-label" for="qty">Quantity</label>' in html
    assert "Trail Running Shoes" in html


def test_unknown_product_is_404(app) -> None:  # type: ignore[no-untyped-def]
    assert client_for(app).get("/product/99").status_code == 404


def test_no_answer_attributes_in_dom(app) -> None:  # type: ignore[no-untyped-def]
    html = client_for(app).get("/product/1").text
    # Elements must not carry an attribute naming their action.
    tags = re.findall(r"<(?!script)[a-z]+[^>]*>", html)
    assert not any("add_to_cart" in tag or "data-action" in tag for tag in tags)


# ------------------------------------------------------------------ sessions + action log


def test_session_cookie_set_once(app) -> None:  # type: ignore[no-untyped-def]
    c = client_for(app)
    first = c.get("/")
    assert SESSION_COOKIE in first.cookies
    second = c.get("/product/2")
    assert SESSION_COOKIE not in second.cookies  # existing cookie reused, not reissued


def test_add_to_cart_logs_action_for_that_session_only(app) -> None:  # type: ignore[no-untyped-def]
    a, b = client_for(app), client_for(app)
    sid_a, sid_b = session_of(a), session_of(b)
    assert sid_a != sid_b

    res = a.post("/api/cart", json={"product_id": 3, "qty": 2})
    assert res.status_code == 200
    assert res.json()["count"] == 2

    log_a = a.get("/__chaos/actions", params={"session": sid_a}).json()["actions"]
    log_b = b.get("/__chaos/actions", params={"session": sid_b}).json()["actions"]
    assert [e["action_id"] for e in log_a] == ["add_to_cart"]
    assert set(log_a[0]) == {"session", "action_id", "ts"}
    assert log_a[0]["session"] == sid_a
    assert log_b == []


def test_carts_are_isolated_between_sessions(app) -> None:  # type: ignore[no-untyped-def]
    a, b = client_for(app), client_for(app)
    session_of(a)
    session_of(b)
    a.post("/api/cart", json={"product_id": 1})
    a.post("/api/cart", json={"product_id": 2})
    assert b.post("/api/cart", json={"product_id": 1}).json()["count"] == 1


def test_client_chosen_session_id_is_honoured(app) -> None:  # type: ignore[no-untyped-def]
    c = client_for(app)
    c.cookies.set(SESSION_COOKIE, "runner-session-0001")
    c.post("/api/cart", json={"product_id": 4})
    actions = c.get("/__chaos/actions", params={"session": "runner-session-0001"}).json()
    assert len(actions["actions"]) == 1


def test_invalid_cookie_is_replaced(app) -> None:  # type: ignore[no-untyped-def]
    c = client_for(app)
    c.cookies.set(SESSION_COOKIE, "../../x")
    res = c.get("/")
    assert res.cookies.get(SESSION_COOKIE) not in (None, "../../x")


def test_failed_add_is_not_logged(app) -> None:  # type: ignore[no-untyped-def]
    c = client_for(app)
    sid = session_of(c)
    assert c.post("/api/cart", json={"product_id": 999}).status_code == 404
    assert c.post("/api/cart", json={"product_id": 1, "qty": 0}).status_code == 422
    assert c.get("/__chaos/actions", params={"session": sid}).json()["actions"] == []


# ------------------------------------------------------------------ control routes


def test_control_routes_absent_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHAOS_CONTROL", raising=False)
    c = TestClient(create_app())
    assert c.get("/__chaos/actions").status_code == 404
    assert c.post("/__chaos/reset").status_code == 404
    assert c.post("/__chaos/scenario", content=CSS_YAML).status_code == 404


def test_control_routes_enabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAOS_CONTROL", "1")
    assert TestClient(create_app()).get("/__chaos/actions").status_code == 200


def test_reset_clears_only_that_session(app) -> None:  # type: ignore[no-untyped-def]
    a, b = client_for(app), client_for(app)
    sid_a, sid_b = session_of(a), session_of(b)
    a.post("/api/cart", json={"product_id": 1})
    b.post("/api/cart", json={"product_id": 1})
    assert a.post("/__chaos/reset", params={"session": sid_a}).status_code == 200
    assert a.get("/__chaos/actions", params={"session": sid_a}).json()["actions"] == []
    assert len(b.get("/__chaos/actions", params={"session": sid_b}).json()["actions"]) == 1
    assert a.post("/api/cart", json={"product_id": 1}).json()["count"] == 1  # cart emptied


def test_control_requests_do_not_create_sessions(app) -> None:  # type: ignore[no-untyped-def]
    res = client_for(app).get("/__chaos/actions")
    assert SESSION_COOKIE not in res.cookies


# ------------------------------------------------------------------ scenarios


def test_scenario_yaml_for_one_session_mutates_only_that_session(app) -> None:  # type: ignore[no-untyped-def]
    a, b = client_for(app), client_for(app)
    sid_a = session_of(a)
    session_of(b)
    res = a.post("/__chaos/scenario", params={"session": sid_a}, content=CSS_YAML)
    assert res.status_code == 200
    assert res.json() == {"session": sid_a, "scenario": "fixture-css-refactor"}
    assert 'class="css-9f2kq1 btn-x"' in a.get("/product/1").text
    assert 'class="btn btn-primary"' in b.get("/product/1").text


def test_global_scenario_applies_to_new_sessions(app) -> None:  # type: ignore[no-untyped-def]
    control = client_for(app)
    assert control.post("/__chaos/scenario", content=CSS_YAML).status_code == 200
    fresh = client_for(app)  # e.g. the sandbox BrowserContext with its own cookie
    assert 'class="css-9f2kq1 btn-x"' in fresh.get("/product/1").text
    control.post("/__chaos/reset")
    assert 'class="btn btn-primary"' in client_for(app).get("/product/1").text


def test_scenario_by_id_and_unknown_or_unsafe_ids(app, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    c = client_for(app)
    assert c.post("/__chaos/scenario", content='{"id": "does-not-exist"}').status_code == 404
    assert c.post("/__chaos/scenario", content='{"id": "../../etc"}').status_code == 422
    loaded = load_scenario("fixture-css-refactor", FIXTURES)
    assert loaded.klass == "css_refactor"
    assert loaded.expected is not None
    assert loaded.expected.action_id == "add_to_cart"


def test_invalid_scenarios_rejected(app) -> None:  # type: ignore[no-untyped-def]
    c = client_for(app)
    bad = [
        "id: x\nmutation:\n  class_map: {no_such_element: foo}\n",  # unknown key
        "id: x\nmutation:\n  colour_map: {}\n",  # unknown mutation field
        "id: x\nclass: not_a_class\n",
        "- just\n- a list\n",
        "id: Bad Id\n",
    ]
    for body in bad:
        assert c.post("/__chaos/scenario", content=body).status_code == 422, body


@pytest.mark.parametrize(
    ("yaml_body", "expected", "absent"),
    [
        (
            "id: t1\nmutation:\n  id_map: {add_to_cart_btn: buy-now-7}\n  testid_map: {add_to_cart_btn: null}\n",
            '<button id="buy-now-7" class="btn btn-primary"',
            'data-testid="add-to-cart"',
        ),
        (
            "id: t2\nmutation:\n  text_map: {add_to_cart_btn: Add to bag}\n",
            ">Add to bag</button>",
            ">Add to cart<",
        ),
        (
            "id: t3\nmutation:\n  tag_map: {add_to_cart_btn: div}\n"
            "  attr_map: {add_to_cart_btn: {type: null, role: button, tabindex: '0'}}\n",
            'role="button" tabindex="0">Add to cart</div>',
            '<button id="add-to-cart"',
        ),
        (
            "id: t4\nmutation:\n  id_map: {qty_input: amount}\n",
            'for="amount">Quantity</label>',
            'for="qty"',
        ),
    ],
)
def test_each_mutation_map_renders(app, yaml_body: str, expected: str, absent: str) -> None:  # type: ignore[no-untyped-def]
    c = client_for(app)
    assert c.post("/__chaos/scenario", content=yaml_body).status_code == 200
    html = c.get("/product/1").text
    assert expected in html
    assert absent not in html


def test_text_from_page_data_is_escaped(app) -> None:  # type: ignore[no-untyped-def]
    c = client_for(app)
    body = 'id: t5\nmutation:\n  text_map: {add_to_cart_btn: "<img src=x onerror=alert(1)>"}\n'
    assert c.post("/__chaos/scenario", content=body).status_code == 200
    html = c.get("/product/1").text
    assert "<img src=x" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_every_default_element_is_used_by_a_template() -> None:
    from chaos_store.elements import DEFAULT_REGIONS

    templates = Path(__file__).parents[2] / "chaos_store" / "templates"
    text = "".join(p.read_text(encoding="utf-8") for p in templates.glob("*.html"))
    used_regions = {r for r in DEFAULT_REGIONS if f'ui.region("{r}")' in text}
    assert used_regions == set(DEFAULT_REGIONS)
    via_region = {k for r in DEFAULT_REGIONS.values() for k in r}
    unused = [k for k in DEFAULT_ELEMENTS if f'"{k}"' not in text and k not in via_region]
    assert unused == []


def test_static_assets_served(app) -> None:  # type: ignore[no-untyped-def]
    c = client_for(app)
    assert c.get("/static/store.css").status_code == 200
    assert "cw" in c.get("/static/store.js").text
