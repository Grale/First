"""Assemble watchlist.json from research JSON files (one array per file, see tools/research/*.json).

    python tools/build_watchlist.py [research_dir]

Entries that clear the spec floor in the config "criteria" block go to "models"; the rest go to "rejected"
with a reason, so the discovery scan knows they were checked. An entry whose panel is not one of the wanted
families carries "qualifies": false in the research file, because that is a judgement about prose ("sold as
Mini LED, reviewed as edge-lit") rather than something a regex should decide. Aliases that would claim
another model's titles are dropped.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from monbot import criteria as criteria_mod   # noqa: E402  (needs ROOT on the path)

# Models the buyer named: they earn a fit bonus and sort first. Star a model on the Watchlist page to
# add one without touching this file.
PRIORITY: set[str] = set()

# Aliases dropped because they name a range, a tier or a marketing line rather than one model. Monitor
# ranges collide harder than TV ones: every maker runs a 34-inch ultrawide in several tiers under one
# family name, and the short codes repeat across generations. "34GP" alone spans the 34GP63A, 34GP83A
# and 34GP950G, three different panels at three different prices; "G5" is a Samsung Odyssey tier, an LG
# OLED tier and an MSI range all at once. A bare tier alias would claim whichever listing it met first.
GENERIC_ALIASES = {
    # marketing lines
    "ULTRAGEAR", "ULTRAWIDE", "ULTRASHARP", "ODYSSEY", "ODYSSEY G5", "ODYSSEY G9", "VIEWFINITY",
    "SMART MONITOR", "PROART", "ROG", "ROG SWIFT", "TUF", "TUF GAMING", "MOBIUZ", "NITRO", "PREDATOR",
    "AGON", "AORUS", "OPTIX", "MAG", "MPG", "MAG ARTYMIS", "ALIENWARE", "THINKVISION", "PROLITE",
    "SPECTRUM", "EVNIA", "BRILLIANCE", "CINEMA", "ESSENTIAL", "PERFORMANCE",
    # bare tier and family codes that span several panels
    "34GP", "34GN", "34WQ", "34WN", "34WR", "34U", "34G2", "34G3", "34E", "34M", "34B", "34C", "34P",
    "G5", "G6", "G7", "G8", "G9", "M34", "C34", "CU34", "U34", "P34", "S34", "E34", "LS34", "LC34",
    "AW34", "PG34", "XZ34", "XR34", "VG34", "VP34", "GS34", "QD34",
    # panel words that would match anything
    "QD OLED", "QD-OLED", "WOLED", "IPS BLACK", "NANO IPS", "MINI LED", "WQHD", "UWQHD", "5K2K",
}

# Why an entry did not qualify, in words that say what was checked rather than what a regex saw.
_PANEL_HINTS = ("TN", "NOT IPS", "NOT OLED", "NOT MINI LED", "EDGE LIT", "EDGE-LIT")


def reason_for(e: dict, crit) -> str:
    # A research entry may state its own reason. It has to be able to: "sold as Mini LED, measured as
    # edge-lit" and "VA, which is not one of the wanted families" are judgements about a panel, and
    # nothing derived from the numbers would ever produce them.
    stated = (e.get("reject_reason") or "").strip()
    if stated:
        return stated
    panel = (e.get("panel") or "").upper()
    notes = (e.get("notes") or "").lower()
    if any(h in panel for h in _PANEL_HINTS):
        return f"panel is not {crit.panel_label} ({e.get('panel')})"
    if "does not exist" in notes or "not sold in europe" in notes or "no european" in notes:
        return "no European model with this code"
    if "discontinued" in notes:
        return "discontinued, not stocked in Cyprus"
    problems = crit.spec_problems(e.get("hz"), e.get("width"), e.get("height"), e.get("height_adjust"),
                                 e.get("usb_c_pd_w"), e.get("kvm"), e.get("vrr"))
    if problems:
        return "; ".join(problems)
    return "specs unverified"


SPEC_KEYS = ("hz", "width", "height", "response_ms", "usb_c_pd_w", "kvm", "height_adjust", "curvature",
             "dp_version", "hdr", "srgb_pct", "dci_p3_pct", "contrast", "tuv_eye_comfort_stars",
             "vrr", "vrr_brand", "burn_in_warranty_years")


def load_reviews(reviews_dir: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not reviews_dir.exists():
        return out
    for f in sorted(reviews_dir.glob("*.json")):
        if f.name.startswith("_"):
            continue
        for r in json.loads(f.read_text(encoding="utf-8")):
            out[r["model_key"].strip().upper()] = r
    pen_file = reviews_dir / "_fit_penalties.json"
    if pen_file.exists():
        for key, items in json.loads(pen_file.read_text(encoding="utf-8")).items():
            if key.startswith("_"):
                continue
            out.setdefault(key.strip().upper(), {"model_key": key})["fit_penalties"] = items
    return out


def main(research_dir: Path) -> None:
    crit = criteria_mod.active()
    reviews = load_reviews(research_dir.parent / "reviews")
    entries: dict[str, dict] = {}
    for f in sorted(research_dir.glob("*.json")):
        for e in json.loads(f.read_text(encoding="utf-8")):
            key = e["model_key"].strip().upper()
            if key in entries:
                old = entries[key]
                old["aliases"] = sorted(set(old.get("aliases", [])) | set(e.get("aliases", [])), key=str.upper)
                continue
            e["model_key"] = key
            entries[key] = e

    models, rejected = [], []
    for key, e in entries.items():
        aliases = []
        seen = set()
        for a in [key, *e.get("aliases", [])]:
            a = (a or "").strip()
            if not a or a.upper() in seen or a.upper() in GENERIC_ALIASES:
                continue
            seen.add(a.upper())
            if a.upper() != key:
                aliases.append(a)
        qualifies = (crit.specs_qualify(e.get("hz"), e.get("width"), e.get("height"),
                                        e.get("height_adjust"), e.get("usb_c_pd_w"), e.get("kvm"),
                                        e.get("vrr"))
                     and e.get("qualifies", True) is not False)
        if qualifies:
            models.append({
                "brand": e["brand"], "model_key": key, "family": e.get("family") or "", "year": e.get("year"),
                "panel": e.get("panel") or "", "size_inch": e.get("size_inch"),
                "specs": {k: e.get(k) for k in SPEC_KEYS},
                "source_url": e.get("source_url") or "", "aliases": aliases, "priority": key in PRIORITY,
                "notes": e.get("notes") or "", "enabled": True,
                "review": reviews.get(key, {}),
            })
        else:
            rejected.append({"brand": e["brand"], "model_key": key, "reason": reason_for(e, crit),
                             "source_url": e.get("source_url") or "", "aliases": aliases})

    models.sort(key=lambda m: (not m["priority"], m["brand"], m["model_key"]))
    rejected.sort(key=lambda r: (r["brand"], r["model_key"]))
    out = ROOT / "watchlist.json"
    out.write_text(json.dumps({"models": models, "rejected": rejected}, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"criteria: {crit.size_label} {crit.panel_label}, {crit.spec_label}")
    print(f"{len(models)} models ({sum(1 for m in models if m['review'])} with reviews), "
          f"{len(rejected)} rejected -> {out}")
    for m in models:
        s = m["specs"]
        pd = f"{s['usb_c_pd_w']}W" if s.get("usb_c_pd_w") else "-"
        print(f"  + {m['brand']:<10} {m['model_key']:<12} {s['hz']}Hz {s['width']}x{s['height']} "
              f"PD={pd:<5} KVM={'y' if s.get('kvm') else 'n'}  {m['panel']:<14}{'*' if m['priority'] else ''}")
    for r in rejected:
        print(f"  - {r['brand']:<10} {r['model_key']:<12} {r['reason']}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tools" / "research")
