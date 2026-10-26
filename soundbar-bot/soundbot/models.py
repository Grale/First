from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Specs:
    """What decides whether a soundbar qualifies. See soundbot/criteria.py for the rules.

    channels         main (ear-level) channels, the first number of a layout like 11.1.4
    sub_channels     the middle number: 1 when the system has a subwoofer channel
    height_channels  the third number: how many channels are steered overhead
    height_type      upfiring | dedicated | virtual | none  (see criteria.HEIGHT_TYPES)
    subwoofer        wireless_included | wireless_optional | built_in | none | wired
    rears            wireless_included | wireless_optional | none | wired
    atmos/dtsx       format decoding
    earc             the bar has an HDMI eARC output
    hdmi_in          HDMI inputs for passthrough (0 means eARC only)
    """
    channels: Optional[float] = None
    sub_channels: Optional[int] = None
    height_channels: Optional[int] = None
    height_type: str = ""
    subwoofer: str = ""
    rears: str = ""
    atmos: Optional[bool] = None
    dtsx: Optional[bool] = None
    earc: Optional[bool] = None
    hdmi_in: Optional[int] = None

    @property
    def layout(self) -> str:
        if self.channels is None:
            return ""
        main = f"{self.channels:g}"
        if self.sub_channels is None and self.height_channels is None:
            return main
        return f"{main}.{self.sub_channels or 0}.{self.height_channels or 0}"


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
