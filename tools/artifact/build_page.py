"""Inject the current watchlist, criteria and parity result into tools/artifact/ranking.html.

    python tools/artifact/export_scores.py > tools/artifact/expected_scores.json
    node tools/artifact/parity.mjs
    python tools/artifact/build_page.py

Rewrites the <script id="watchlist-data"> block in place, so the published page can never drift from
watchlist.json. Prices are deliberately absent: the page carries specs, scores and evidence only.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent
BLOCK = re.compile(
    r'(<script id="watchlist-data" type="application/json">)(.*?)(</script>)', re.S)


def main() -> int:
    watchlist = json.loads((ROOT / "watchlist.json").read_text(encoding="utf-8"))
    criteria = json.loads((ROOT / "config.json").read_text(encoding="utf-8")).get("criteria", {})
    parity_file = HERE / "parity_result.json"
    parity = json.loads(parity_file.read_text(encoding="utf-8")) if parity_file.exists() else {}
    prices_file = HERE / "prices.json"
    prices = json.loads(prices_file.read_text(encoding="utf-8")) if prices_file.exists() else {}
    if parity.get("failures"):
        print(f"refusing to build: parity reports {parity['failures']} mismatch(es); "
              "fix scoring.mjs first", file=sys.stderr)
        return 1

    payload = {
        "criteria": criteria,
        "models": watchlist.get("models", []),
        "rejected": watchlist.get("rejected", []),
        "parity": parity,
        "prices": prices,
    }
    page = HERE / "ranking.html"
    html = page.read_text(encoding="utf-8")
    # </script> inside a JSON string would end the block early; no field contains one, but escape anyway
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    new_html, n = BLOCK.subn(lambda m: m.group(1) + data + m.group(3), html, count=1)
    if n != 1:
        print("refusing to build: the watchlist-data block was not found in ranking.html", file=sys.stderr)
        return 1
    page.write_text(new_html, encoding="utf-8")
    print(f"ranking.html rebuilt: {len(payload['models'])} models, "
          f"{len(payload['rejected'])} rejected, {len(prices.get('groups', []))} priced products "
          f"as of {prices.get('as_of', 'never')}, {parity.get('comparisons', '?')} parity comparisons, "
          f"{len(new_html) / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
