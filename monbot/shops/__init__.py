from __future__ import annotations
from typing import Type

from .base import Shop
from .electroline import Electroline
from .scandia_like import Scandia, MegaElectric
from .stephanis import Stephanis
from .public_cy import PublicCy
from .kotsovolos import Kotsovolos

SHOPS: dict[str, Type[Shop]] = {
    Electroline.name: Electroline,
    Scandia.name: Scandia,
    MegaElectric.name: MegaElectric,
    Stephanis.name: Stephanis,
    PublicCy.name: PublicCy,
    Kotsovolos.name: Kotsovolos,
}

__all__ = ["Shop", "SHOPS"]
