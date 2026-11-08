"""Pipeline entry point.

    python -m jobradar.cli run [--sources a,b] [--llm] [--notify|--notify-dry-run]

Stages: discover -> dedupe -> enrich+score -> persist -> artifact -> notify.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from . import llm
from .config import ROOT, load_profile, load_text
from .dedupe import dedupe
from .models import Job
from .notify import telegram
from .report import excel
from .scoring.scorer import evaluate
from .sources import REGISTRY
from .storage import Store

log = logging.getLogger("jobradar")

CAVEATS = [
    "LinkedIn, Indeed, Glassdoor, StepStone and Xing are NOT included: their terms "
    "of service prohibit automated access. Adding them needs an official partner "
    "API or a manual export.",
    "Workable's public job-board API (used by most Greek tech employers) rate-limited "
    "this environment, so Greek on-site coverage is thin in this run.",
    "Salary figures marked 'estimated' are benchmark-derived, not employer-published.",
    "Net monthly figures assume the 50% expatriate relief applies and are indicative "
    "only. They are not tax advice and the relief must be confirmed case by case.",
]


def discover(cfg, only: list[str] | None, store, run_id: str):
    names = [s for s in cfg["sources"]["enabled"] if not only or s in only]
    jobs: list[Job] = []
    stats = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(REGISTRY[n], cfg): n for n in names if n in REGISTRY}
        for fut in as_completed(futs):
            name = futs[fut]
            errors: list[str] = []
            try:
                res = fut.result()
            except Exception as exc:                  # noqa: BLE001
                log.warning("source %s failed: %s", name, exc)
                stats.append({"source": name, "fetched": 0, "eligible": 0,
                              "errors": f"{type(exc).__name__}: {exc}"})
                continue
            good = []
            for item in res:
                if isinstance(item, dict) and "_error" in item:
                    errors.append(str(item["_error"])[:160])
                else:
                    good.append(item)
            jobs.extend(good)
            stats.append({"source": name, "fetched": len(good), "eligible": 0,
                          "errors": "; ".join(errors[:3])})
            log.info("  %-16s %4d jobs%s", name, len(good),
                     f"  ({len(errors)} errors)" if errors else "")
    return jobs, stats


def run(args) -> int:
    try:                       # progress should stream, not sit in a buffer
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    cfg = load_profile(args.profile)
    cfg["_cv_text"] = load_text(cfg["candidate"]["cv_file"])
    if args.notify_min_score is not None:
        cfg["output"]["notify_min_score"] = args.notify_min_score
    if args.shortlist_min_score is not None:
        cfg["output"]["shortlist_min_score"] = args.shortlist_min_score
    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S")
    store = Store(args.db)
    store.start_run(run_id)
    t0 = time.time()

    only = [s.strip() for s in args.sources.split(",")] if args.sources else None
    print(f"\n=== {run_id} ===\nDiscovering...")
    raw, src_stats = discover(cfg, only, store, run_id)
    print(f"\nFetched {len(raw)} candidate postings (after title prefilter)")

    kept, removed = dedupe(raw)
    print(f"Deduplicated: {len(kept)} unique ({removed} duplicates collapsed)")

    print("Enriching and scoring...")
    for job in kept:
        try:
            evaluate(job, cfg)
        except Exception as exc:                      # noqa: BLE001
            log.warning("scoring failed for %r: %s", job.title[:50], exc)
            job.eligible = False
            job.exclusion_reasons.append(f"Scoring error: {type(exc).__name__}")

    eligible = sorted([j for j in kept if j.eligible], key=lambda j: -j.score)
    excluded = sorted([j for j in kept if not j.eligible],
                      key=lambda j: (j.exclusion_reasons or [""])[0])

    if args.llm:
        if llm.available():
            print(f"LLM adjudication on the top {args.llm_limit}...")
            n = llm.adjudicate(eligible, cfg, args.llm_limit)
            print(f"  reviewed {n} postings")
            eligible = sorted([j for j in eligible if j.eligible], key=lambda j: -j.score)
        else:
            print("LLM review requested but ANTHROPIC_API_KEY is not set - skipping")

    # ---- persist + novelty ----------------------------------------------
    novelty = {"new": 0, "changed": 0, "seen": 0}
    for job in kept:
        novelty[store.upsert(job)] += 1

    # ---- funnel ----------------------------------------------------------
    def why(j, *keys):
        return any(k in r.lower() for r in j.exclusion_reasons for k in keys)

    geo_kw = ("united states", "us-based", "us-only", "restricted to a country",
              "on-site/hybrid outside", "forex/cfd brokerage in cyprus")
    comp_kw = ("below the greece/austria floor",)
    excl_geo = sum(1 for j in excluded if why(j, *geo_kw))
    excl_comp = sum(1 for j in excluded if why(j, *comp_kw))
    excl_prof = len(excluded) - excl_geo - excl_comp

    floor = cfg["output"]["shortlist_min_score"]
    shortlist = [j for j in eligible if j.score >= floor]

    by_src = {s["source"]: s for s in src_stats}
    for j in eligible:
        if j.source in by_src:
            by_src[j.source]["eligible"] += 1

    stats = {
        "run_id": run_id,
        "funnel": {"fetched": len(raw), "unique": len(kept), "duplicates": removed,
                   "excl_geo": excl_geo, "excl_prof": excl_prof, "excl_comp": excl_comp,
                   "eligible": len(eligible), "shortlist": len(shortlist)},
        "novelty": novelty,
        "sources": sorted(src_stats, key=lambda s: -s["fetched"]),
        "caveats": CAVEATS,
        "elapsed_s": round(time.time() - t0, 1),
    }

    # ---- artifact --------------------------------------------------------
    out = args.out or f"out/job_evaluation_{run_id}.xlsx"
    path = excel.build(out, eligible[:cfg["output"]["max_rows_artifact"]],
                       excluded[:cfg["output"]["max_rows_artifact"]],
                       shortlist, stats, cfg)
    print(f"\nArtifact: {path}")

    jpath = Path(out).with_suffix(".json")
    jpath.write_text(json.dumps(
        {"stats": stats,
         "eligible": [j.to_dict() for j in eligible],
         "excluded": [{"title": j.title, "company": j.company, "url": j.url,
                       "reasons": j.exclusion_reasons} for j in excluded]},
        indent=2, default=str), encoding="utf-8")
    print(f"Raw results: {jpath}")

    # ---- notifications ---------------------------------------------------
    if args.notify or args.notify_dry_run:
        res = telegram.notify_new(shortlist, store, cfg, dry_run=args.notify_dry_run)
        mode = "DRY RUN" if args.notify_dry_run else "LIVE"
        print(f"\nTelegram ({mode}): sent={res['sent']} "
              f"deduped={res['skipped_duplicate']} failed={res['failed']}")
        if res["previews"]:
            prev = Path("out") / f"telegram_preview_{run_id}.txt"
            prev.write_text("\n\n" + ("\n\n" + "=" * 60 + "\n\n").join(res["previews"]),
                            encoding="utf-8")
            print(f"Message previews: {prev}")

    # ---- console summary -------------------------------------------------
    f = stats["funnel"]
    print(f"\n{'-' * 62}\nFUNNEL")
    print(f"  fetched {f['fetched']} -> unique {f['unique']} -> eligible {f['eligible']} "
          f"-> shortlist {f['shortlist']}")
    print(f"  excluded: geo {f['excl_geo']} | professional {f['excl_prof']} | comp {f['excl_comp']}")
    print(f"  novelty: {novelty['new']} new, {novelty['changed']} changed, {novelty['seen']} seen")
    print(f"\nTOP {min(20, len(eligible))}")
    for i, j in enumerate(eligible[:20], 1):
        print(f"  {i:2}. {j.score:5.1f}  {j.title[:46]:48} {j.company[:20]:22} "
              f"{j.geo_tier:15} {j.industry}")
    print(f"\nElapsed {stats['elapsed_s']}s")
    store.finish_run(run_id, stats)
    store.close()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="jobradar")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="discover, score and report")
    r.add_argument("--profile", default=None)
    r.add_argument("--db", default="data/jobs.db")
    r.add_argument("--out", default=None)
    r.add_argument("--sources", default=None, help="comma-separated subset")
    r.add_argument("--llm", action="store_true", help="LLM adjudication of the top matches")
    r.add_argument("--llm-limit", type=int, default=25)
    r.add_argument("--notify", action="store_true", help="send Telegram messages")
    r.add_argument("--notify-dry-run", action="store_true",
                   help="render Telegram messages to a file without sending")
    r.add_argument("--notify-min-score", type=float, default=None,
                   help="override the notification score floor (demo/tuning)")
    r.add_argument("--shortlist-min-score", type=float, default=None,
                   help="override the shortlist score floor (demo/tuning)")
    r.set_defaults(func=run)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
