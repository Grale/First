# TV Deal Bot

Watches Cyprus electronics shops for **75/77-inch OLED and Mini LED TVs** and alerts you when one shop is
clearly cheaper than the others, when a shop runs a big discount, or when a watched model comes back in
stock. It starts with the laptop and serves a local dashboard.

Shops: Electroline, Scandia, MegaElectric, Stephanis, Public, Kotsovolos.

Ranking is **picture quality first**: panel type, measured brightness and dimming zones carry the most
weight, with refresh rate, HDMI 2.1 and input lag as smaller bonuses.

## Daily use

* Dashboard: <http://127.0.0.1:8765> (only reachable from this laptop). It shows every watched model with the
  price in each shop, the cheapest shop, the lowest price ever seen, and when the next check runs.
* Alerts arrive as a Windows toast and as a push on your phone through [ntfy](https://ntfy.sh): install the
  ntfy app and subscribe to the topic shown on the Settings page (it is private to you; keep it to yourself).
* **Run check now** on the dashboard forces a check; **Test notification** sends a test toast and push.

## What it watches

The requirements live in one place: the `criteria` block of `config.json`, editable on the **Settings** page.

| Setting | Value | Meaning |
|---|---|---|
| `sizes` | `[75, 77]` | Both sizes are one class: the OLED lines are sold at 77" where Mini LED is sold at 75", so watching only one number would miss half the market |
| `panels` | `["oled", "miniled"]` | OLED (incl. QD-OLED) and Mini LED (incl. Neo QLED, QNED, ULED, RGB Mini LED) |
| `min_hz` | `100` | Native refresh floor. European spec sheets quote 100 Hz for panels that run 120/144/165 Hz, so this is the honest floor |
| `require_vrr` | `false` | VRR earns fit points instead of being a hard requirement |
| `require_hdmi21` | `false` | Same for HDMI 2.1 |

Everything downstream follows from that block: which shop listings are matched, which titles the discovery
scan suggests, the search terms sent to Public and Kotsovolos, and which watchlist models are checked.
`python main.py validate` prints the active criteria and any watchlist entry that falls short of them.

Changing the criteria does **not** rewrite the watch list. Widen the size class or add a panel family and you
also need models to watch: run **Discover**, confirm the specs, and add them (or add research files and rebuild,
see below).

## How it decides what to alert

Rules live on the Settings page (saved to `config.json`):

| Rule | Default |
|---|---|
| Cross-shop: one shop is at least X % below the next-cheapest shop for the same model | 10 % |
| List discount: a shop's price is at least Y % below its own strikethrough price | 20 % |
| Back in stock: a model that was out of stock or missing in a shop is available again | on |
| Same alert not repeated for | 7 days (a lower price re-alerts at once) |
| Checks every | 3 hours |
| Prices outside this range are treated as shop data errors | €700 to €9,000 |

## Ranking

Every watched model gets three scores, shown on the **Ranking** page, on each model page, and as the order of
the dashboard:

* **Fit (0-100)**: how well the specs match what you asked for, under the **picture** profile (set in
  `scoring.profile`): panel type (QD-OLED or META OLED 22, OLED 20, RGB Mini LED 17, quantum-dot Mini LED 13,
  plain Mini LED 10), contrast (OLED 20 for per-pixel control, otherwise up to 18 for measured dimming
  zones), measured peak brightness (22), native refresh (10), full HDMI 2.1 ports (6), input lag (4), model
  year (8). Deductions apply where reviews found a clash with your criteria: edge-lit despite a Mini LED
  label, no local dimming, dimming switched off with VRR, few zones, an IPS panel.
  The old gaming-first weighting is still there: set `scoring.profile` to `gaming` on the Settings page to
  rank by refresh, HDMI 2.1 and lag instead.
* **Reviews (0-100)**: critic reviews (70 %) and owner sentiment (30 %), each with sources and a confidence level.
* **Overall**: 50 % fit + 50 % reviews by default; change the weights on Settings. **Value** is overall per
  €1,000 of the cheapest in-stock price.

The evidence lives in `tools/reviews/*.json` and the deductions in `tools/reviews/_fit_penalties.json`.
Rerun `python tools/build_watchlist.py` after editing either.

## The watch list

`watchlist.json` is the only thing that decides which TVs are watched: **74 models** across OLED (LG, Samsung,
Sony, Philips) and Mini LED (Samsung, LG, Hisense, TCL, Sony, Philips, Panasonic, Metz, Xiaomi), plus **16**
checked and rejected. A model is watched only when its specs clear the criteria above.

Every entry carries a `source_url` and says in `notes` how far it was verified, because the two are not the
same thing:

* **Checked at this size** - the spec page, lab review or retailer listing in `source_url` is for the 75 or
  77-inch set itself (for example the Samsung UK page for the QE75QN90F, LG's page for the 77-inch C6H,
  RTINGS' review of the 77-inch S90H).
* **Ported from the 65-inch sibling** - the specs come from the same series' 65-inch spec page, verified in
  an earlier research round, and the note says so. Refresh rate, VRR and HDMI ports almost never change
  across sizes within a series; brightness and zone counts do, usually upward.
* A handful of entries say the size variant itself **was not confirmed to exist** (Samsung M80H, Sony's 2026
  Bravia II pair, Metz, Xiaomi). They cost nothing but one search query if they turn out not to exist.
* `75QN90H` and `75QN85H` (2026 Samsung Mini LED) have **no review evidence yet** and are ranked on fit
  alone; the dashboard flags them.

Measured figures carried over from the 65-inch research were taken on that size, as each review entry says.

* Edit on the **Watchlist** page, or rebuild from the research files:
  `python tools/build_watchlist.py` (reads `tools/research/*.json`, reviews from `tools/reviews/*.json`).
* **Discover** scans the shops for titles that fit the criteria but match nothing on the list, so new models
  can be researched and added. Always confirm the specs online before adding one. Models that were checked
  and failed sit in the `rejected` list with the reason, so the scan does not keep suggesting them.
* Aliases are the tokens a shop title contains (`QN85D` -> `QE75QN85DATXXH`, `OLED77C5` -> `OLED77C54LA`);
  the matcher prefers the longest matching alias and lets rejected models win ties, so `75C6K` never claims
  a `75C6KS` listing, and the Frame Pro never claims a plain Frame. A title that names another size is
  rejected, so the 65 and 83-inch versions of a watched model are ignored.
* Tier names that LG has reused across years and dimming tiers (`QNED87`, `QNED93`, ...) and brand words
  (`Bravia 9`) are dropped as aliases in `tools/build_watchlist.py`: they would claim the wrong set.
* `tools/archive/65inch/` holds the previous round's research and reviews for the 65-inch Mini LED gaming
  build. The builder does not read it.

## Command line

```bash
.venv\Scripts\python.exe main.py run-once --dry-run      # one check, print what would alert, send nothing
.venv\Scripts\python.exe main.py run-once                # one real check
.venv\Scripts\python.exe main.py report                  # current prices per model and shop
.venv\Scripts\python.exe main.py discover                # titles in the shops that fit the criteria but are not watched
.venv\Scripts\python.exe main.py test-notify             # test toast + ntfy push
.venv\Scripts\python.exe main.py validate                # active criteria + check watchlist.json
.venv\Scripts\python.exe main.py serve --open            # dashboard + background checks
```

## Start with the laptop

`main.py install-task` registers the Windows scheduled task **TV Deal Bot** (`scheduler/task.xml`): at your
logon, after one minute, it starts `pythonw.exe main.py serve` hidden, which serves the dashboard and runs the
first check two minutes later, then every 3 hours. `task-status`, `task-run`, `task-restart` (use this after
code or config changes) and `uninstall-task` manage it.
Logs: `logs/bot.log`. Price history: `prices.db` (SQLite).

## How each shop is read

| Shop | Method |
|---|---|
| Electroline | TV category page embeds a JSON blob of every TV (`var pageProducts`) |
| Scandia, MegaElectric | server-rendered catalog pages (same platform) |
| Stephanis | server-rendered TV category, 100 per page |
| Public | its search provider's JSON API (findbar.io) with Public's own front-end token; broad queries built from the criteria, titles matched locally |
| Kotsovolos | search page `__NEXT_DATA__` for part numbers, then the shop's product and availability JSON APIs; needs the Chrome-TLS tier (`curl_cffi`) because of Akamai. The selling price is the API's `Offer` entry; its `price_EUR` field holds stale values and must not be used |

Public and Kotsovolos are queried per panel family and brand against each wanted size, so a second size in
`criteria.sizes` roughly doubles their query count. A query that finds nothing costs one request.

Fetching escalates `requests` -> `curl_cffi` (Chrome TLS impersonation) -> Playwright Chromium (only if installed).
A shop that fails is skipped for that run and its previous snapshot is kept; it never triggers alerts from stale data.

## Setup from scratch

```bash
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py validate
.venv\Scripts\python.exe main.py run-once --dry-run
.venv\Scripts\python.exe main.py install-task
```

Then open Settings and subscribe to the ntfy topic shown there in the ntfy phone app.
