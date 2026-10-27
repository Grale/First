"""Assemble watchlist.json from the research JSON files (one array per file, see tools/research/*.json).

    python tools/build_watchlist.py [research_dir]

Entries that clear the criteria in the config "criteria" block go to "models"; the rest go to "rejected"
with a reason, so the discovery scan knows they were checked rather than missed. An entry that a review
showed to be virtual-Atmos or wired carries "qualifies": false in the research file, because that is a
judgement about prose ("lacks dedicated up-firing speakers") rather than something a regex should decide.
Aliases that would claim another model's titles are dropped.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from soundbot import criteria as criteria_mod          # noqa: E402  (needs ROOT on the path)
from soundbot.models import Specs                      # noqa: E402

# Models the buyer named: they earn a fit bonus and sort first. Star a model on the Watchlist page to
# add one without touching this file.
PRIORITY: set[str] = set()
# How much of each product line to watch. A line is the family a model belongs to ("Samsung Q990"),
# named by the "line" field in the research files; KEEP_GENERATIONS counts back from its newest member,
# so when a 2027 Q990 is researched the 2025 one drops out on its own rather than by hand.
KEEP_GENERATIONS = 2
# Nothing older than this model year. Set it to 0 to watch every generation that is still on sale.
MIN_YEAR = 2024
# Aliases dropped because they name a range or a tier rather than one model. "BAR 8" would be claimed by
# any "JBL Bar 800" listing once the spaces come out, and "Q-SERIES" covers eleven Samsungs.
GENERIC_ALIASES = {"BAR 8", "BAR 9", "BAR 6", "BAR 7", "BAR8", "BAR9", "BAR6", "BAR7", "Q SERIES",
                   "Q-SERIES", "S SERIES", "FLEXUS", "HESTON", "ENCHANT", "ARC", "BEAM", "BRAVIA THEATRE",
                   "BRAVIA THEATER", "SMART SOUNDBAR", "CINEMA"}


def specs_from(e: dict) -> Specs:
    return Specs(channels=e.get("channels"), sub_channels=e.get("sub_channels"),
                 height_channels=e.get("height_channels"), height_type=e.get("height_type") or "",
                 subwoofer=e.get("subwoofer") or "", rears=e.get("rears") or "",
                 atmos=e.get("atmos"), dtsx=e.get("dtsx"), earc=e.get("earc"), hdmi_in=e.get("hdmi_in"))


def reason_for(e: dict, crit) -> str:
    """The shortest true statement of why this one is not watched."""
    specs = specs_from(e)
    if specs.height_type == "virtual":
        return "Dolby Atmos is virtual only: no drivers fire at the ceiling"
    if specs.height_type == "none" or not specs.atmos:
        return "no Dolby Atmos height channels"
    problems = crit.spec_problems(specs)
    return "; ".join(problems) if problems else "specs unverified"


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


def older_than_floor(entries: dict[str, dict]) -> dict[str, str]:
    """Which models are out on age rather than on merit, and in one sentence why.

    Two cuts, both about keeping the list to what is worth watching rather than about the hardware:
    a model year floor, and only the newest few generations of each line. A model that falls to either
    is still recorded as rejected, so the discovery scan does not keep offering it back.
    """
    out: dict[str, str] = {}
    by_line: dict[str, list[dict]] = {}
    for e in entries.values():
        by_line.setdefault(e.get("line") or e["model_key"], []).append(e)
    for line, members in by_line.items():
        members.sort(key=lambda m: (m.get("year") or 0), reverse=True)
        for rank, e in enumerate(members):
            year = e.get("year") or 0
            if MIN_YEAR and year and year < MIN_YEAR:
                out[e["model_key"]] = f"{year} model, and the list stops at {MIN_YEAR}"
            elif KEEP_GENERATIONS and rank >= KEEP_GENERATIONS:
                newer = ", ".join(m["model_key"] for m in members[:KEEP_GENERATIONS])
                out[e["model_key"]] = (f"superseded in the {line} line: only the newest "
                                       f"{KEEP_GENERATIONS} are watched ({newer})")
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

    superseded = older_than_floor(entries)

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
        specs = specs_from(e)
        # Why it is out matters: "virtual Atmos" tells you something about the hardware that "2021
        # model" does not, so a model that fails on merit is recorded that way whatever its age.
        on_merit = crit.specs_qualify(specs) and e.get("qualifies", True) is not False
        qualifies = on_merit and key not in superseded
        verified = e.get("verified") or "unstated"
        notes = e.get("notes") or ""
        if verified and verified not in notes:
            notes = f"[{verified}] {notes}".strip()
        if qualifies:
            models.append({
                "brand": e["brand"], "model_key": key, "family": e.get("family") or "", "year": e.get("year"),
                "specs": {"channels": specs.channels, "sub_channels": specs.sub_channels,
                          "height_channels": specs.height_channels, "height_type": specs.height_type,
                          "subwoofer": specs.subwoofer, "rears": specs.rears,
                          "atmos": specs.atmos, "dtsx": specs.dtsx, "earc": specs.earc,
                          "hdmi_in": specs.hdmi_in},
                "source_url": e.get("source_url") or "", "aliases": aliases, "priority": key in PRIORITY,
                "notes": notes, "enabled": True,
                "review": reviews.get(key, {}),
            })
        else:
            rejected.append({"brand": e["brand"], "model_key": key,
                             "reason": reason_for(e, crit) if not on_merit else superseded[key],
                             "source_url": e.get("source_url") or "", "aliases": aliases})

    models.sort(key=lambda m: (not m["priority"], m["brand"], m["model_key"]))
    rejected.sort(key=lambda r: (r["brand"], r["model_key"]))
    out = ROOT / "watchlist.json"
    out.write_text(json.dumps({"models": models, "rejected": rejected}, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"criteria: {crit.label}")
    print(f"curation: newest {KEEP_GENERATIONS} generations of each line, nothing before {MIN_YEAR}")
    print(f"{len(models)} models ({sum(1 for m in models if m['review'])} with reviews), "
          f"{len(rejected)} rejected -> {out}")
    for m in models:
        s = m["specs"]
        layout = f"{s['channels']:g}.{s['sub_channels'] or 0}.{s['height_channels'] or 0}"
        print(f"  + {m['brand']:<14} {m['model_key']:<22} {layout:<8} sub={s['subwoofer']:<18} "
              f"rears={s['rears']:<18} {'*' if m['priority'] else ''}")
    for r in rejected:
        print(f"  - {r['brand']:<14} {r['model_key']:<22} {r['reason']}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tools" / "research")
