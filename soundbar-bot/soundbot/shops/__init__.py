from __future__ import annotations
from typing import Type

from .base import Shop
from .electroline import Electroline
from .scandia_like import Scandia
from .stephanis import Stephanis
from .public_like import PublicGr
from .kotsovolos_like import KotsovolosGr
from .skroutz import Skroutz

SHOPS: dict[str, Type[Shop]] = {
    # Cyprus
    Electroline.name: Electroline,
    Scandia.name: Scandia,
    Stephanis.name: Stephanis,
    # Greece
    Skroutz.name: Skroutz,
    PublicGr.name: PublicGr,
    KotsovolosGr.name: KotsovolosGr,
}

COUNTRIES = {"CY": "Cyprus", "GR": "Greece"}


def shop_country(name: str) -> str:
    cls = SHOPS.get(name)
    return cls.country if cls else ""


def shops_in(country: str) -> list[str]:
    return [n for n, c in SHOPS.items() if c.country == country]


__all__ = ["Shop", "SHOPS", "COUNTRIES", "shop_country", "shops_in"]
