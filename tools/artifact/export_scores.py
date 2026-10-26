"""Dump the Python scoring for every model, both profiles and a grid of weights, as JSON.

    python tools/artifact/export_scores.py > tools/artifact/expected_scores.json

tools/artifact/parity.mjs reads the result and checks the JavaScript port in scoring.mjs against it,
component by component. The artifact page shows no prices, so nothing here needs one.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from monbot import watchlist as watchlist_mod   # noqa: E402
from monbot.scoring import PROFILES, fit_score, score_model  # noqa: E402

# fit_weight / review_weight pairs, including the two degenerate ends
WEIGHT_GRID = [(round(i / 10, 1), round(1 - i / 10, 1)) for i in range(11)]


def best_prices() -> dict:
    """The cheapest in-stock price per model from the captured snapshot, so the value score is tested
    against real numbers rather than invented ones."""
    f = Path(__file__).resolve().parent / "prices.json"
    return json.loads(f.read_text(encoding="utf-8")).get("best_prices", {}) if f.exists() else {}


def main() -> int:
    wl = watchlist_mod.load()
    prices = best_prices()
    out = []
    for m in wl.models:
        for profile in PROFILES:
            fit, parts = fit_score(m, profile)
            overalls = []
            for w_fit, w_rev in WEIGHT_GRID:
                cfg = {"scoring": {"fit_weight": w_fit, "review_weight": w_rev, "profile": profile}}
                sc = score_model(m, cfg, prices.get(m.model_key))
                overalls.append({"fit_weight": w_fit, "review_weight": w_rev,
                                 "overall": sc.overall, "fit": sc.fit, "value": sc.value,
                                 "review": sc.review, "has_review": sc.has_review})
            out.append({"model_key": m.model_key, "profile": profile,
                        "fit_raw": fit, "parts": parts, "ppi": m.ppi, "overalls": overalls})
    json.dump({"weight_grid": WEIGHT_GRID, "best_prices": prices, "expected": out},
              sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
