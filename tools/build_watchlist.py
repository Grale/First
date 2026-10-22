"""Assemble watchlist.json from research JSON files (one array per file, see tools/research/*.json).

    python tools/build_watchlist.py [research_dir]

Entries that clear the spec floor in the config "criteria" block go to "models"; the rest go to "rejected"
with a reason, so the discovery scan knows they were checked. An entry whose panel is not one of the wanted
families carries "qualifies": false in the research file, because that is a judgement about prose ("Edge LED
despite the QNED label") rather than something a regex should decide. Aliases that would claim another
model's titles are dropped.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tvbot import criteria as criteria_mod   # noqa: E402  (needs ROOT on the path)
# Models the buyer named: they earn a fit bonus and sort first. Star a model on the Watchlist page to
# add one without touching this file.
PRIORITY: set[str] = set()
# Aliases dropped because they name a tier rather than a model: LG has reused QNED85/86/87/93 across
# years and dimming tiers, so a bare tier alias would claim the wrong set. Brand words ("Bravia 9") go
# the same way: they match every set in the range.
GENERIC_ALIASES = {"QNED70", "QNED72", "QNED81", "QNED83", "QNED85", "QNED86", "QNED87", "QNED90", "QNED92",
                   "QNED93", "QNED826", "QNED866", "QNED876", "BRAVIA 5", "BRAVIA 7", "BRAVIA 8", "BRAVIA 9",
                   "THE XTRA", "QLED MINILED"}


def reason_for(e: dict, crit) -> str:
    bl = (e.get("backlight") or "").lower()
    notes = (e.get("notes") or "").lower()
    if "not mini led" in bl or "not mini" in bl or "edge" in bl or "dled" in bl:
        return f"panel is not {crit.panel_label} ({e.get('backlight')})"
    if "does not exist" in notes or "not sold in europe" in notes or "no european" in notes:
        return "no European model with this code"
    problems = crit.spec_problems(e.get("hz"), e.get("vrr"), e.get("hdmi21"))
    if problems:
        return "; ".join(problems)
    return "specs unverified"


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
        hz, vrr, hdmi = e.get("hz"), e.get("vrr"), e.get("hdmi21")
        qualifies = crit.specs_qualify(hz, vrr, hdmi) and e.get("qualifies", True) is not False
        if qualifies:
            models.append({
                "brand": e["brand"], "model_key": key, "family": e.get("family") or "", "year": e.get("year"),
                "backlight": e.get("backlight") or "",
                "specs": {"hz": hz, "vrr": bool(vrr), "hdmi21": bool(hdmi), "hdmi21_ports": e.get("hdmi21_ports")},
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
    print(f"{len(models)} models ({sum(1 for m in models if m['review'])} with reviews), {len(rejected)} rejected -> {out}")
    for m in models:
        print(f"  + {m['brand']:<9} {m['model_key']:<12} {m['specs']['hz']}Hz  ports={m['specs']['hdmi21_ports']}  {'*' if m['priority'] else ''}")
    for r in rejected:
        print(f"  - {r['brand']:<9} {r['model_key']:<12} {r['reason']}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tools" / "research")
