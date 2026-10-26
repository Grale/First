from __future__ import annotations
import json
import threading
from dataclasses import dataclass, field, asdict
from typing import TYPE_CHECKING, Any, Optional

from .models import Specs
from .paths import WATCHLIST_PATH

if TYPE_CHECKING:
    from .criteria import Criteria

_lock = threading.Lock()


@dataclass
class Model:
    brand: str
    model_key: str
    family: str = ""
    year: Optional[int] = None
    specs: Specs = field(default_factory=Specs)
    source_url: str = ""
    aliases: list[str] = field(default_factory=list)
    priority: bool = False
    notes: str = ""
    enabled: bool = True
    review: dict = field(default_factory=dict)   # critic/user review evidence, see tools/reviews

    def meets(self, crit: "Criteria") -> bool:
        """True when the specs clear the floor in the active criteria."""
        return crit.specs_qualify(self.specs)

    @property
    def display_name(self) -> str:
        fam = ""
        if self.family and self.family.upper() not in self.model_key.upper():
            fam = f" ({self.family})"
        return f"{self.brand} {self.model_key}{fam}".strip()

    def all_aliases(self) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for a in [self.model_key, *self.aliases]:
            a = (a or "").strip()
            if a and a.upper() not in seen:
                seen.add(a.upper())
                out.append(a)
        return out

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Rejected:
    brand: str
    model_key: str
    reason: str
    source_url: str = ""
    aliases: list[str] = field(default_factory=list)


@dataclass
class Watchlist:
    models: list[Model] = field(default_factory=list)
    rejected: list[Rejected] = field(default_factory=list)

    def active(self) -> list[Model]:
        return [m for m in self.models if m.enabled]

    def watched(self, crit: "Criteria") -> list[Model]:
        return [m for m in self.active() if m.meets(crit)]

    def get(self, model_key: str) -> Optional[Model]:
        for m in self.models:
            if m.model_key.upper() == model_key.upper():
                return m
        return None

    def validate(self, crit: "Criteria") -> list[str]:
        problems: list[str] = []
        keys: set[str] = set()
        for m in self.models:
            if m.model_key.upper() in keys:
                problems.append(f"duplicate model_key {m.model_key}")
            keys.add(m.model_key.upper())
            if not m.source_url:
                problems.append(f"{m.model_key}: missing source_url")
            for why in crit.spec_problems(m.specs):
                problems.append(f"{m.model_key}: {why}")
        return problems


def model_from_dict(d: dict[str, Any]) -> Model:
    s = d.get("specs") or {}
    return Model(
        brand=d.get("brand", ""),
        model_key=d.get("model_key", ""),
        family=d.get("family", "") or "",
        year=d.get("year"),
        specs=Specs(channels=s.get("channels"), sub_channels=s.get("sub_channels"),
                    height_channels=s.get("height_channels"), height_type=s.get("height_type", "") or "",
                    subwoofer=s.get("subwoofer", "") or "", rears=s.get("rears", "") or "",
                    atmos=s.get("atmos"), dtsx=s.get("dtsx"), earc=s.get("earc"), hdmi_in=s.get("hdmi_in")),
        source_url=d.get("source_url", "") or "",
        aliases=list(d.get("aliases") or []),
        priority=bool(d.get("priority", False)),
        notes=d.get("notes", "") or "",
        enabled=bool(d.get("enabled", True)),
        review=dict(d.get("review") or {}),
    )


def load() -> Watchlist:
    with _lock:
        if not WATCHLIST_PATH.exists():
            return Watchlist()
        data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    models = [model_from_dict(d) for d in data.get("models", [])]
    rejected = [Rejected(brand=r.get("brand", ""), model_key=r.get("model_key", ""), reason=r.get("reason", ""),
                         source_url=r.get("source_url", ""), aliases=list(r.get("aliases") or []))
                for r in data.get("rejected", [])]
    return Watchlist(models=models, rejected=rejected)


def save(wl: Watchlist) -> None:
    data = {"models": [m.to_dict() for m in wl.models], "rejected": [asdict(r) for r in wl.rejected]}
    with _lock:
        WATCHLIST_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
