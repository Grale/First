from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Item:
    """A raw product card as a shop shows it, before matching to the watchlist."""
    shop: str
    title: str
    price: Optional[float]
    url: str
    list_price: Optional[float] = None
    in_stock: Optional[bool] = True
    shop_sku: str = ""


@dataclass
class Offer:
    """A matched watchlist model at one shop."""
    shop: str
    model_key: str
    title: str
    price: Optional[float]
    url: str
    list_price: Optional[float] = None
    in_stock: Optional[bool] = True
    shop_sku: str = ""
    seen_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Alert:
    rule: str            # cross_shop, list_discount, back_in_stock, test
    shop: str
    model_key: str
    price: Optional[float]
    title: str
    message: str
    url: str
    dedupe_key: str
    priority: bool = False
