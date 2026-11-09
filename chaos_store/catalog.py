"""Deterministic seed data: 8 products. Never randomised."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Product:
    id: int
    name: str
    price_cents: int
    category: str
    description: str

    @property
    def price(self) -> str:
        return f"${self.price_cents // 100}.{self.price_cents % 100:02d}"


PRODUCTS: tuple[Product, ...] = (
    Product(1, "Trail Running Shoes", 8999, "footwear", "Lightweight shoes with a grippy sole."),
    Product(2, "Waterproof Jacket", 12950, "outerwear", "Seam-sealed shell for wet days."),
    Product(3, "Merino Wool Socks", 1800, "footwear", "Warm, breathable, odour-resistant."),
    Product(4, "Insulated Bottle", 2450, "gear", "Keeps drinks cold for 24 hours."),
    Product(5, "Daypack 20L", 6400, "gear", "Padded straps and a laptop sleeve."),
    Product(6, "Fleece Pullover", 5500, "outerwear", "Soft mid-layer for cool evenings."),
    Product(7, "Headlamp 300lm", 3299, "gear", "Rechargeable, with a red night mode."),
    Product(8, "Trekking Poles", 7900, "gear", "Collapsible aluminium, cork grips."),
)

_BY_ID = {p.id: p for p in PRODUCTS}


def get_product(product_id: int) -> Product | None:
    return _BY_ID.get(product_id)
