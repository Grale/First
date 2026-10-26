from __future__ import annotations
from typing import Type

from .base import Shop
from .electroline import Electroline
from .scandia_like import Scandia, MegaElectric
from .stephanis import Stephanis
from .public_like import PublicCy, PublicGr
from .kotsovolos_like import KotsovolosCy, KotsovolosGr
from .skroutz import Skroutz, SkroutzCy

SHOPS: dict[str, Type[Shop]] = {
    # Cyprus
    Electroline.name: Electroline,
    Scandia.name: Scandia,
    MegaElectric.name: MegaElectric,
    Stephanis.name: Stephanis,
    PublicCy.name: PublicCy,
    KotsovolosCy.name: KotsovolosCy,
    SkroutzCy.name: SkroutzCy,
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
