"""Generate the dev additions and the EVAL scenario set. Deterministic.

Usage: uv run python scripts/gen_scenarios.py [--check]

Eval counts per class are the proposal's ("8, 8, 7, 7, 6, 4, 5, 5"), mapped in
class order: id_rename 8, css_refactor 8,
copy_drift 7, tag_to_aria 7, layout_move 6, i18n 4, distractor_trap 5,
regression_trap 5 (40 healable + 10 traps).

Every scenario targets a step whose action has a SERVER action id, so the
action log (not the DOM) is the ground truth. Dev and eval use different tests
or different texts/values; hashed class tokens are derived from fixed seeds.
The eval set is frozen after generation: see benchmark/eval_freeze.json.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "chaos_store" / "scenarios"


def h(seed: str, n: int = 6) -> str:
    """Deterministic hash-like token (CSS-in-JS style)."""
    return hashlib.sha256(seed.encode()).hexdigest()[:n]


def primary(seed: str) -> str:
    return f"css-{h(seed)} inline-block px-3.5 py-2 rounded-md border bg-blue text-white cursor-pointer text-base text-center no-underline"


def secondary(seed: str) -> str:
    return f"sc-{h(seed)} inline-block px-3.5 py-2 rounded-md border border-blue bg-white text-blue cursor-pointer text-base"


def danger(seed: str) -> str:
    return f"_{h(seed)} inline-block px-3.5 py-2 rounded-md border border-red bg-white text-red cursor-pointer text-base"


def link(seed: str) -> str:
    return f"css-{h(seed)} text-blue cursor-pointer text-base"


ARIA = {"type": None, "role": "button", "tabindex": "0"}

# Whole-page Spanish translation (i18n). Status/total texts produced by JS or
# asserted by the tests are deliberately left untranslated.
ES = {
    "catalog_title": "Productos",
    "search_btn": "Buscar",
    "product_card_link": "Ver detalles",
    "nav_home_link": "Tienda",
    "nav_cart_link": "Carrito",
    "qty_label": "Cantidad",
    "add_to_cart_btn": "Añadir al carrito",
    "wishlist_btn": "Añadir a la lista de deseos",
    "back_link": "Volver a productos",
    "added_modal_title": "Artículo añadido",
    "modal_continue_btn": "Seguir comprando",
    "modal_view_cart_link": "Ver carrito",
    "cart_title": "Tu carrito",
    "cart_remove_btn": "Eliminar",
    "cart_save_btn": "Guardar para después",
    "coupon_label": "Código de cupón",
    "coupon_apply_btn": "Aplicar",
    "coupon_remove_btn": "Quitar cupón",
    "checkout_link": "Ir a pagar",
    "checkout_title": "Pago",
    "name_label": "Nombre completo",
    "email_label": "Correo electrónico",
    "address_label": "Dirección",
    "shipping_label": "Envío",
    "agree_label": "Acepto los términos",
    "place_order_btn": "Realizar pedido",
    "confirm_order_btn": "Confirmar pedido",
    "cancel_order_btn": "Cancelar pedido",
    "order_back_link": "Seguir comprando",
}

T = "examples/"

# (id, class, test, mutation, expected action)
DEV_NEW: list[tuple[str, str, str, dict[str, Any], str]] = [
    (
        "dev-11-tag-to-aria",
        "tag_to_aria",
        T + "test_tags.py::test_tag_add_to_cart",
        {"tag_map": {"add_to_cart_btn": "div"}, "attr_map": {"add_to_cart_btn": ARIA}},
        "add_to_cart",
    ),
    (
        "dev-12-tag-to-aria",
        "tag_to_aria",
        T + "test_tags.py::test_tag_search",
        {"tag_map": {"search_btn": "div"}, "attr_map": {"search_btn": ARIA}},
        "search",
    ),
    (
        "dev-13-layout-move",
        "layout_move",
        T + "test_positions.py::test_position_add_to_cart",
        {"order_map": {"buy_box": ["add_to_cart_btn", "wishlist_btn", "qty_label", "qty_input"]}},
        "add_to_cart",
    ),
    (
        "dev-14-layout-move",
        "layout_move",
        T + "test_positions.py::test_position_search",
        {"order_map": {"search": ["search_btn", "search_input"]}},
        "search",
    ),
    (
        "dev-15-i18n",
        "i18n",
        T + "test_cart.py::test_add_to_cart_by_text",
        {"text_map": ES},
        "add_to_cart",
    ),
    (
        "dev-16-i18n",
        "i18n",
        T + "test_texts.py::test_text_confirm",
        {"text_map": ES},
        "confirm_order",
    ),
]

EVAL: list[tuple[str, str, str, dict[str, Any], str]] = [
    # ---- id_rename (8)
    (
        "eval-01-id-rename",
        "id_rename",
        T + "test_cart.py::test_add_two_products_then_view_cart",
        {"id_map": {"add_to_cart_btn": "btn-cart-add"}},
        "add_to_cart",
    ),
    (
        "eval-02-id-rename",
        "id_rename",
        T + "test_cart.py::test_add_to_cart_with_quantity",
        {"testid_map": {"add_to_cart_btn": "cart-add-btn"}},
        "add_to_cart",
    ),
    (
        "eval-03-id-rename",
        "id_rename",
        T + "test_cart.py::test_remove_item_from_cart",
        {"id_map": {"cart_remove_btn": "line-remove-{item}"}},
        "remove_from_cart",
    ),
    (
        "eval-04-id-rename",
        "id_rename",
        T + "test_coupon.py::test_apply_valid_coupon",
        {"id_map": {"coupon_apply_btn": "coupon-submit"}},
        "apply_coupon",
    ),
    (
        "eval-05-id-rename",
        "id_rename",
        T + "test_checkout.py::test_place_order",
        {"id_map": {"place_order_btn": "submit-order"}},
        "create_order",
    ),
    (
        "eval-06-id-rename",
        "id_rename",
        T + "test_orders.py::test_cancel_after_confirm",
        {"testid_map": {"confirm_order_btn": "order-confirm"}},
        "confirm_order",
    ),
    (
        "eval-07-id-rename",
        "id_rename",
        T + "test_orders.py::test_cancel_order",
        {"id_map": {"cancel_order_btn": "order-cancel-btn"}},
        "cancel_order",
    ),
    (
        "eval-08-id-rename",
        "id_rename",
        T + "test_search.py::test_search_by_button",
        {"id_map": {"search_btn": "do-search"}},
        "search",
    ),
    # ---- css_refactor (8)
    (
        "eval-09-css-refactor",
        "css_refactor",
        T + "test_classes.py::test_class_wishlist",
        {
            "class_map": {
                "wishlist_btn": secondary("e09"),
                "buy_box": f"css-{h('e09b')} flex items-center gap-3",
            }
        },
        "add_to_wishlist",
    ),
    (
        "eval-10-css-refactor",
        "css_refactor",
        T + "test_classes.py::test_class_remove",
        {"class_map": {"cart_remove_btn": link("e10")}},
        "remove_from_cart",
    ),
    (
        "eval-11-css-refactor",
        "css_refactor",
        T + "test_classes.py::test_class_save_for_later",
        {
            "class_map": {
                "cart_save_btn": link("e11"),
                "cart_row": f"sc-{h('e11r')} flex items-center gap-3",
            }
        },
        "save_for_later",
    ),
    (
        "eval-12-css-refactor",
        "css_refactor",
        T + "test_classes.py::test_class_apply_coupon",
        {"class_map": {"coupon_apply_btn": secondary("e12")}},
        "apply_coupon",
    ),
    (
        "eval-13-css-refactor",
        "css_refactor",
        T + "test_classes.py::test_class_remove_coupon",
        {
            "class_map": {
                "coupon_remove_btn": link("e13"),
                "coupon_form": f"_{h('e13f')} flex items-center gap-3",
            }
        },
        "remove_coupon",
    ),
    (
        "eval-14-css-refactor",
        "css_refactor",
        T + "test_classes.py::test_class_place_order",
        {"class_map": {"place_order_btn": primary("e14")}},
        "create_order",
    ),
    (
        "eval-15-css-refactor",
        "css_refactor",
        T + "test_classes.py::test_class_cancel",
        {
            "class_map": {
                "cancel_order_btn": danger("e15"),
                "order_actions": f"css-{h('e15a')} flex gap-3",
            }
        },
        "cancel_order",
    ),
    (
        "eval-16-css-refactor",
        "css_refactor",
        T + "test_orders.py::test_confirm_order_by_class",
        {"class_map": {"confirm_order_btn": primary("e16")}},
        "confirm_order",
    ),
    # ---- copy_drift (7)
    (
        "eval-17-copy-drift",
        "copy_drift",
        T + "test_coupon.py::test_apply_coupon_by_text",
        {"text_map": {"coupon_apply_btn": "Use code"}},
        "apply_coupon",
    ),
    (
        "eval-18-copy-drift",
        "copy_drift",
        T + "test_cart.py::test_remove_last_item_empties_cart",
        {"text_map": {"cart_remove_btn": "Delete"}},
        "remove_from_cart",
    ),
    (
        "eval-19-copy-drift",
        "copy_drift",
        T + "test_search.py::test_search_category",
        {"text_map": {"search_btn": "Find"}},
        "search",
    ),
    (
        "eval-20-copy-drift",
        "copy_drift",
        T + "test_texts.py::test_text_wishlist",
        {"text_map": {"wishlist_btn": "Save to wishlist"}},
        "add_to_wishlist",
    ),
    (
        "eval-21-copy-drift",
        "copy_drift",
        T + "test_texts.py::test_text_save_for_later",
        {"text_map": {"cart_save_btn": "Move to saved"}},
        "save_for_later",
    ),
    (
        "eval-22-copy-drift",
        "copy_drift",
        T + "test_texts.py::test_text_cancel",
        {"text_map": {"cancel_order_btn": "Cancel this order"}},
        "cancel_order",
    ),
    (
        "eval-23-copy-drift",
        "copy_drift",
        T + "test_texts.py::test_text_place_order",
        {"text_map": {"place_order_btn": "Place your order"}},
        "create_order",
    ),
    # ---- tag_to_aria (7)
    (
        "eval-24-tag-to-aria",
        "tag_to_aria",
        T + "test_tags.py::test_tag_add_to_wishlist",
        {"tag_map": {"wishlist_btn": "div"}, "attr_map": {"wishlist_btn": ARIA}},
        "add_to_wishlist",
    ),
    (
        "eval-25-tag-to-aria",
        "tag_to_aria",
        T + "test_tags.py::test_tag_remove",
        {"tag_map": {"cart_remove_btn": "div"}, "attr_map": {"cart_remove_btn": ARIA}},
        "remove_from_cart",
    ),
    (
        "eval-26-tag-to-aria",
        "tag_to_aria",
        T + "test_tags.py::test_tag_save_for_later",
        {"tag_map": {"cart_save_btn": "div"}, "attr_map": {"cart_save_btn": ARIA}},
        "save_for_later",
    ),
    (
        "eval-27-tag-to-aria",
        "tag_to_aria",
        T + "test_tags.py::test_tag_apply_coupon",
        {"tag_map": {"coupon_apply_btn": "div"}, "attr_map": {"coupon_apply_btn": ARIA}},
        "apply_coupon",
    ),
    (
        "eval-28-tag-to-aria",
        "tag_to_aria",
        T + "test_tags.py::test_tag_place_order",
        {"tag_map": {"place_order_btn": "div"}, "attr_map": {"place_order_btn": ARIA}},
        "create_order",
    ),
    (
        "eval-29-tag-to-aria",
        "tag_to_aria",
        T + "test_tags.py::test_tag_confirm",
        {"tag_map": {"confirm_order_btn": "div"}, "attr_map": {"confirm_order_btn": ARIA}},
        "confirm_order",
    ),
    (
        "eval-30-tag-to-aria",
        "tag_to_aria",
        T + "test_tags.py::test_tag_cancel",
        {"tag_map": {"cancel_order_btn": "div"}, "attr_map": {"cancel_order_btn": ARIA}},
        "cancel_order",
    ),
    # ---- layout_move (6)
    (
        "eval-31-layout-move",
        "layout_move",
        T + "test_positions.py::test_position_add_two",
        {"order_map": {"buy_box": ["wishlist_btn", "add_to_cart_btn", "qty_label", "qty_input"]}},
        "add_to_cart",
    ),
    (
        "eval-32-layout-move",
        "layout_move",
        T + "test_positions.py::test_position_wishlist",
        {"order_map": {"buy_box": ["qty_label", "wishlist_btn", "add_to_cart_btn", "qty_input"]}},
        "add_to_wishlist",
    ),
    (
        "eval-33-layout-move",
        "layout_move",
        T + "test_positions.py::test_position_apply_coupon",
        {
            "order_map": {
                "coupon": ["coupon_apply_btn", "coupon_label", "coupon_input", "coupon_remove_btn"]
            }
        },
        "apply_coupon",
    ),
    (
        "eval-34-layout-move",
        "layout_move",
        T + "test_positions.py::test_position_remove_coupon",
        {
            "order_map": {
                "coupon": ["coupon_remove_btn", "coupon_apply_btn", "coupon_label", "coupon_input"]
            }
        },
        "remove_coupon",
    ),
    (
        "eval-35-layout-move",
        "layout_move",
        T + "test_positions.py::test_position_remove",
        {
            "order_map": {
                "cart_row": [
                    "cart_remove_btn",
                    "cart_item_name",
                    "cart_item_qty",
                    "cart_item_price",
                    "cart_save_btn",
                ]
            }
        },
        "remove_from_cart",
    ),
    (
        "eval-36-layout-move",
        "layout_move",
        T + "test_positions.py::test_position_save_for_later",
        {
            "order_map": {
                "cart_row": [
                    "cart_save_btn",
                    "cart_remove_btn",
                    "cart_item_name",
                    "cart_item_qty",
                    "cart_item_price",
                ]
            }
        },
        "save_for_later",
    ),
    # ---- i18n (4)
    (
        "eval-37-i18n",
        "i18n",
        T + "test_texts.py::test_text_remove_coupon",
        {"text_map": ES},
        "remove_coupon",
    ),
    (
        "eval-38-i18n",
        "i18n",
        T + "test_coupon.py::test_apply_coupon_by_text",
        {"text_map": ES},
        "apply_coupon",
    ),
    (
        "eval-39-i18n",
        "i18n",
        T + "test_search.py::test_search_category",
        {"text_map": ES},
        "search",
    ),
    (
        "eval-40-i18n",
        "i18n",
        T + "test_texts.py::test_text_place_order",
        {"text_map": ES},
        "create_order",
    ),
    # ---- distractor_trap (5): target renamed; identically styled look-alike that fires
    #      a DIFFERENT server action is moved to where the target was
    (
        "eval-41-distractor",
        "distractor_trap",
        T + "test_cart.py::test_add_to_cart_with_quantity",
        {
            "id_map": {"add_to_cart_btn": "pdp-act-2"},
            "testid_map": {"add_to_cart_btn": None},
            "class_map": {"wishlist_btn": "btn btn-primary"},
            "order_map": {"buy_box": ["qty_label", "qty_input", "wishlist_btn", "add_to_cart_btn"]},
        },
        "add_to_cart",
    ),
    (
        "eval-42-distractor",
        "distractor_trap",
        T + "test_cart.py::test_remove_item_from_cart",
        {
            "id_map": {"cart_remove_btn": "row-act-{item}"},
            "testid_map": {"cart_remove_btn": None},
            "order_map": {
                "cart_row": [
                    "cart_item_name",
                    "cart_item_qty",
                    "cart_item_price",
                    "cart_save_btn",
                    "cart_remove_btn",
                ]
            },
        },
        "remove_from_cart",
    ),
    (
        "eval-43-distractor",
        "distractor_trap",
        T + "test_coupon.py::test_apply_valid_coupon",
        {
            "id_map": {"coupon_apply_btn": "cpn-act-1"},
            "testid_map": {"coupon_apply_btn": None},
            "class_map": {"coupon_remove_btn": "btn btn-secondary"},
            "order_map": {
                "coupon": ["coupon_label", "coupon_input", "coupon_remove_btn", "coupon_apply_btn"]
            },
        },
        "apply_coupon",
    ),
    (
        "eval-44-distractor",
        "distractor_trap",
        T + "test_orders.py::test_cancel_after_confirm",
        {
            "id_map": {"confirm_order_btn": "ord-act-1"},
            "testid_map": {"confirm_order_btn": None},
            "class_map": {"cancel_order_btn": "btn btn-primary"},
            "order_map": {"order_actions": ["cancel_order_btn", "confirm_order_btn"]},
        },
        "confirm_order",
    ),
    (
        "eval-45-distractor",
        "distractor_trap",
        T + "test_text_cancel_after_confirm_placeholder",
        {},
        "cancel_order",
    ),
    # ---- regression_trap (5): the target is gone; any heal is a false heal
    (
        "eval-46-regression",
        "regression_trap",
        T + "test_coupon.py::test_apply_valid_coupon",
        {"remove": ["coupon_apply_btn"]},
        "apply_coupon",
    ),
    (
        "eval-47-regression",
        "regression_trap",
        T + "test_checkout.py::test_place_order",
        {"remove": ["place_order_btn"]},
        "create_order",
    ),
    (
        "eval-48-regression",
        "regression_trap",
        T + "test_search.py::test_search_by_button",
        {"remove": ["search_btn"]},
        "search",
    ),
    (
        "eval-49-regression",
        "regression_trap",
        T + "test_cart.py::test_remove_item_from_cart",
        {"remove": ["cart_remove_btn"]},
        "remove_from_cart",
    ),
    (
        "eval-50-regression",
        "regression_trap",
        T + "test_orders.py::test_cancel_order",
        {"remove": ["cancel_order_btn"]},
        "cancel_order",
    ),
]

# eval-45: Cancel renamed; an identically styled Confirm sits where Cancel was. Uses
# test_cancel_after_confirm's CANCEL step (its confirm step still uses the unchanged test id).
EVAL[44] = (
    "eval-45-distractor",
    "distractor_trap",
    T + "test_orders.py::test_cancel_after_confirm",
    {
        "id_map": {"cancel_order_btn": "ord-act-2"},
        "testid_map": {"cancel_order_btn": None},
        "class_map": {"confirm_order_btn": "btn btn-danger"},
        "order_map": {"order_actions": ["cancel_order_btn", "confirm_order_btn"]},
    },
    "cancel_order",
)

OUTCOME = {"distractor_trap": "red_or_true_heal", "regression_trap": "red"}
COMMENT = {
    "distractor_trap": "Target renamed; an identically styled look-alike that fires a different action sits in its place. Correct: stay red or heal to the TRUE target.",
    "regression_trap": "The target is gone (a real regression). Any heal is a false heal.",
}


def render(split: str, row: tuple[str, str, str, dict[str, Any], str]) -> str:
    sid, klass, test, mutation, action = row
    doc = {
        "id": sid,
        "split": split,
        "class": klass,
        "test": test,
        "mutation": mutation,
        "expected": {"outcome": OUTCOME.get(klass, "healed"), "action_id": action},
    }
    header = f"# Generated by scripts/gen_scenarios.py ({split} split). Do not edit by hand.\n"
    if klass in COMMENT:
        header += f"# {COMMENT[klass]}\n"
    return header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if files on disk differ")
    args = parser.parse_args()
    expected: dict[Path, str] = {}
    for row in DEV_NEW:
        expected[OUT / "dev" / f"{row[0]}.yaml"] = render("dev", row)
    for row in EVAL:
        expected[OUT / "eval" / f"{row[0]}.yaml"] = render("eval", row)
    assert len(EVAL) == 50
    drift = [
        p
        for p, text in expected.items()
        if not p.is_file() or p.read_text(encoding="utf-8") != text
    ]
    if args.check:
        for p in drift:
            print("differs:", p.relative_to(ROOT))
        return 1 if drift else 0
    for path, text in expected.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    print(f"wrote {len(DEV_NEW)} dev + {len(EVAL)} eval scenarios")
    return 0


if __name__ == "__main__":
    sys.exit(main())
