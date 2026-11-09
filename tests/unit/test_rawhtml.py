"""Raw-HTML baseline helpers (benchmark/rawhtml_plugin.py): offline."""

from __future__ import annotations

import pytest

from benchmark.rawhtml_plugin import HTML_LIMIT, build_prompt, clean_html, parse_selector

pytestmark = pytest.mark.unit


def test_clean_html_drops_scripts_styles_and_comments() -> None:
    html = (
        "<html><head><style>.x{color:red}</style></head><body>\n"
        '<button id="b">Confirm   order</button>\n'
        "<script>cw.bind(el, 'confirm_order')</script><!-- confirm_order -->"
        "<SCRIPT type=module>alert(1)</SCRIPT></body></html>"
    )
    out = clean_html(html)
    assert "confirm_order" not in out  # handler names live only in scripts
    assert "color:red" not in out
    assert "alert" not in out
    assert '<button id="b">Confirm order</button>' in out


def test_clean_html_truncates_to_the_fixed_limit() -> None:
    assert len(clean_html("<p>" + "x" * (HTML_LIMIT * 2) + "</p>")) == HTML_LIMIT


def test_prompt_marks_page_content_as_untrusted() -> None:
    prompt = build_prompt({"accessible_name": "confirm order"}, "click", "<b>hi</b>")
    assert "<data>" in prompt
    assert "untrusted" in prompt
    assert '{"selector": "<CSS selector>"}' in prompt


@pytest.mark.parametrize(
    ("raw", "ok"),
    [
        ('{"selector": "#confirm-order-v2"}', "#confirm-order-v2"),
        ('{"selector": "  button.primary  "}', "button.primary"),
    ],
)
def test_parse_selector_ok(raw: str, ok: str) -> None:
    assert parse_selector(raw) == ok


@pytest.mark.parametrize(
    "raw",
    [
        '{"selector": ""}',
        '{"sel": "#x"}',
        '["#x"]',
        "not json",
        '{"selector": "' + "a" * 501 + '"}',
    ],
)
def test_parse_selector_rejects_bad_replies(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_selector(raw)
