"""extract.js spike: candidates, features, flags and caps."""

from __future__ import annotations

import json
from typing import Any

import pytest
from playwright.sync_api import Page

from healwright.recorder.extract import FIELDS, extract, row_as_dict
from tests.conftest import LiveStore

pytestmark = pytest.mark.integration


def _by(rows: list[dict[str, Any]], **match: Any) -> dict[str, Any]:
    hits = [r for r in rows if all(r[k] == v for k, v in match.items())]
    assert len(hits) == 1, (match, [(r["role"], r["name"]) for r in rows])
    return hits[0]


def test_product_page_snapshot(page: Page, store: LiveStore) -> None:
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(f"{store.base_url}/product/1")
    snap = extract(page)
    assert snap["mode"] == "snapshot"
    assert snap["fields"] == list(FIELDS)
    assert snap["viewport"] == [1280, 800]
    assert snap["has_iframes"] is False
    assert snap["has_shadow_roots"] is False
    assert snap["truncated"] is False
    rows = [row_as_dict(r) for r in snap["rows"]]

    btn = _by(rows, role="button", name="Add to cart")
    assert btn["tag"] == "button"
    assert btn["text"] == "Add to cart"
    assert btn["attrs"] == {"id": "add-to-cart", "type": "button", "data-testid": "add-to-cart"}
    assert btn["classes"] == ["btn", "btn-primary"]
    assert btn["ancestors"][:2] == ["form[form]", "main[main]"]
    assert "Quantity" in btn["neighbors"]
    _x, _y, w, h = btn["bbox"]
    assert w > 0
    assert h > 0
    assert btn["in_shadow"] is False

    qty = _by(rows, role="spinbutton")
    assert qty["name"] == "Quantity"  # from the <label for>
    assert qty["attrs"]["name"] == "qty"

    back = _by(rows, role="link", name="Back to products")
    assert back["attrs"]["href"] == "/"


def test_never_leaks_script_content(page: Page, store: LiveStore) -> None:
    page.goto(f"{store.base_url}/product/1")
    payload = json.dumps(extract(page)["rows"])
    assert "cw.bind" not in payload
    assert "cw.ref" not in payload
    assert "add_to_cart" not in payload


def test_hidden_elements_contribute_no_text(page: Page) -> None:
    page.set_content(
        "<div><button>Go</button>"
        "<div hidden>secret modal<script>cw.bind('x')</script></div>"
        "<p style='display:none'>also hidden</p></div>"
    )
    rows = [row_as_dict(r) for r in extract(page)["rows"]]
    payload = json.dumps(rows)
    assert "secret modal" not in payload
    assert "also hidden" not in payload
    assert "cw.bind" not in payload


def test_target_mode_matches_snapshot_row(page: Page, store: LiveStore) -> None:
    page.goto(f"{store.base_url}/product/1")
    handle = page.query_selector("#add-to-cart")
    assert handle is not None
    single = extract(page, target=handle)
    assert single["mode"] == "target"
    assert len(single["rows"]) == 1
    full = [row_as_dict(r) for r in extract(page)["rows"]]
    assert row_as_dict(single["rows"][0]) == _by(full, name="Add to cart", role="button")


CANDIDATE_HTML = """
<main>
  <button id="b1">Save</button>
  <a href="/orders/42?x=1#top" aria-label="Order 42">#42</a>
  <div role="button" tabindex="0" class="css-9f2kq1 btn-x">Confirm order</div>
  <div tabindex="-1">not focusable by tab</div>
  <div tabindex="0">focusable div</div>
  <span onclick="void 0">clickable span</span>
  <button style="display:none">hidden</button>
  <input type="hidden" name="csrf" value="x">
  <input type="checkbox" id="agree"><label for="agree">I agree</label>
  <input placeholder="Search products" type="search">
  <select aria-labelledby="lbl"><option>One</option></select><span id="lbl">Size</span>
  <button aria-label="Close"><svg width="10" height="10"></svg></button>
  <script>var secret = "do not read";</script>
</main>
"""


def test_candidate_rules_and_names(page: Page) -> None:
    page.set_content(CANDIDATE_HTML)
    rows = [row_as_dict(r) for r in extract(page)["rows"]]
    names = {(r["role"], r["name"]) for r in rows}
    assert ("button", "Save") in names
    assert ("link", "Order 42") in names
    assert ("button", "Confirm order") in names
    assert ("checkbox", "I agree") in names
    assert ("searchbox", "Search products") in names
    assert ("combobox", "Size") in names
    assert ("button", "Close") in names
    texts = {r["text"] for r in rows}
    assert "focusable div" in texts
    assert "clickable span" in texts
    assert "not focusable by tab" not in texts
    assert "hidden" not in texts
    assert all(r["attrs"].get("name") != "csrf" for r in rows)
    link = _by(rows, role="link")
    assert link["attrs"]["href"] == "/orders/42"  # path only
    assert "do not read" not in json.dumps(rows)


def test_iframe_and_shadow_root_flags(page: Page) -> None:
    page.set_content(
        "<button>x</button><iframe srcdoc='<p>hi</p>'></iframe><div id='host'></div>"
        "<script>document.getElementById('host').attachShadow({mode:'open'}).innerHTML="
        "'<button>inner</button>'</script>"
    )
    snap = extract(page)
    assert snap["has_iframes"] is True
    assert snap["has_shadow_roots"] is True
    assert all(row_as_dict(r)["in_shadow"] is False for r in snap["rows"])  # main frame light DOM


def test_cap_at_400_and_text_bounded(page: Page) -> None:
    page.set_content("".join(f"<button>{'w ' * 150}{i}</button>" for i in range(450)))
    snap = extract(page)
    assert snap["total"] == 450
    assert snap["truncated"] is True
    assert len(snap["rows"]) == 400
    assert all(len(row_as_dict(r)["text"]) <= 200 for r in snap["rows"])


def test_keep_stores_candidates_for_later_lookup(page: Page) -> None:
    page.set_content("<button>a</button><button>b</button>")
    extract(page, keep=True)
    assert page.evaluate("window.__healwright_candidates.map(e => e.textContent)") == ["a", "b"]
    assert "__healwright_candidates" not in page.evaluate("Object.keys(window)")
