# Soundbar Deal Bot

Watches Cypriot and Greek shops for **wireless soundbars with real Dolby Atmos** and alerts you when one
shop is clearly cheaper than the others, when a shop runs a big discount, or when a watched model comes
back in stock. Same shape as the TV bot: starts with the laptop, serves a local dashboard, pushes to your
phone.

Shops: Electroline, Scandia, MegaElectric, Stephanis, Public CY, Kotsovolos CY (Cyprus) · Skroutz,
Public GR, Kotsovolos GR (Greece).

Ranking is **immersion first**: height channels and wireless rears carry the most weight, with bass,
ear-level channels, formats and connections as smaller bonuses.

## Daily use

* Dashboard: <http://127.0.0.1:8766> (only reachable from this laptop). Prices are grouped by country, so
  the Cypriot and Greek columns sit side by side with the cheapest shop in each.
* Alerts arrive as a Windows toast and as a push on your phone through [ntfy](https://ntfy.sh): install the
  ntfy app and subscribe to the topic shown on the Settings page (it is private to you; keep it to yourself).
* **Run check now** on the dashboard forces a check; **Test notification** sends a test toast and push.

## What "wireless" and "true Atmos" mean here

Both halves of the requirement are checked separately, because plenty of soundbars pass one and fail the
other. The 5.1 Sony Theatre System 6 is wireless end to end and has no height drivers at all; the JBL Bar
800MK2 has a wireless sub and wireless rears and still renders Atmos in a processor.

The requirements live in one place: the `criteria` block of `config.json`, editable on the **Settings** page.

| Setting | Default | Meaning |
|---|---|---|
| `min_height_channels` | `2` | The third number of a layout like 11.1.**4**. Two is the floor: one up-firing driver (5.1.1) cannot place a sound to your left or right overhead, which is the whole point |
| `require_physical_height` | `true` | Height has to come from drivers that fire at the ceiling, or dedicated height drivers. A virtual processor does not count, whatever the box says |
| `require_earc` | `true` | Plain ARC carries Atmos only inside lossy Dolby Digital+. Without eARC the bar cannot receive the lossless TrueHD Atmos track from a disc or a TV app |
| `no_wired_speakers` | `true` | **The wireless rule.** A subwoofer or rear speaker that connects with a speaker cable disqualifies the system. Components may be in the box or sold separately, as long as they talk to the bar over the air |
| `require_sub_included` | `false` | Stricter: the box must contain a wireless subwoofer |
| `require_rears_included` | `false` | Stricter: the box must contain wireless rear speakers |
| `min_channels` | `3.0` | Lowest number of ear-level channels |

The two strict switches are **off by default**, which is a judgement worth knowing about. With them off,
a single bar whose sub and rears are wireless extras — Sonos Arc Ultra, Sony Bar 9, Marshall Heston 120 —
stays on the list, because nothing in those systems is ever cabled; it simply scores below a four-piece
set. Tick `require_sub_included` on Settings and the list drops from 36 models to 25, all of them complete
wireless systems out of the box. That one checkbox is the difference between "no speaker cables" and
"bar, wireless sub and wireless rears, in the box".

Everything downstream follows from that block: which shop listings are matched, which titles the discovery
scan suggests, and which watchlist models are checked. `python main.py validate` prints the active criteria
and any watchlist entry that falls short of them.

## How it decides what to alert

Rules live on the Settings page (saved to `config.json`):

| Rule | Default |
|---|---|
| Cross-shop: one shop is at least X % below the next-cheapest shop for the same model | 10 % |
| …compared | within each country (a price in Athens is not an offer you can take in Nicosia) |
| List discount: a shop's price is at least Y % below its own strikethrough price | 20 % |
| Back in stock: a model that was out of stock or missing in a shop is available again | on |
| Same alert not repeated for | 7 days (a lower price re-alerts at once) |
| Checks every | 3 hours |
| Prices outside this range are treated as shop data errors | €200 to €3,500 |

## Ranking

Every watched model gets three scores, shown on the **Ranking** page, on each model page, and as the order
of the dashboard:

* **Fit (0-100)** under the **cinema** profile (set in `scoring.profile`): height channels (4+ 24 pts,
  3 20, 2 15, and nothing at all for virtual height), wireless rears (in the box 20, available 9), bass
  (wireless sub in the box with an 8-inch driver 14, any wireless sub in the box 12, bass built into the
  bar 7, wireless sub available 6), ear-level channels (10), Atmos + DTS:X (6), eARC and HDMI input (6),
  room calibration (4), model year (8). Deductions apply where reviews found a clash with the criteria:
  HDMI passthrough capped below the TV's panel, no HDMI input at all, height effects reviewers could not
  place, a subwoofer that cannot keep up with the bar.
  A **music** profile is also there: set `scoring.profile` to `music` on the Settings page to rank by
  tonal quality, streaming support and whether there is an analogue input for a turntable instead.
* **Reviews (0-100)**: critic reviews and owner sentiment, each with sources and a confidence level.
* **Overall**: 50 % fit + 50 % reviews by default; change the weights on Settings. **Value** is overall
  per €1,000 of the cheapest in-stock price.

The evidence lives in `tools/reviews/*.json` and the deductions in `tools/reviews/_fit_penalties.json`.
Rerun `python tools/build_watchlist.py` after editing either.

## The watch list

`watchlist.json` is the only thing that decides which soundbars are watched: **36 models** across Samsung,
Sony, LG, JBL, Sonos, Bose, Marshall, Harman Kardon, Klipsch and Bowers & Wilkins, plus **11** checked and
rejected. A model is watched only when its specs clear the criteria above.

Every entry carries a `source_url` and opens its `notes` with how far it was verified, because the two are
not the same thing:

* **`[spec page]`** — the manufacturer's own spec sheet for this exact model was read: every current
  Samsung (Q990H, Q990F, Q930H, Q930F, QS90H, Q800H, Q800F, QS700F) and the two LG sets.
* **`[series page]`** — the specs come from the same series' current spec page and the retailer listings
  agree (the 2024 Q990D and Q930D, which Samsung has retired).
* **`[review]` / `[reviews + retailer spec]`** — the layout and the up-firing drivers come from reviews
  that describe the drivers, not from a spec sheet (the Sony Bravia Theatre bars, the JBL MK2 pair,
  Sonos, Bose, Marshall, Klipsch).
* **`[retailer listing]`** — the layout comes only from what Electroline or Stephanis print in the title.
  Good enough to watch a price, **not** good enough to buy on: confirm at the manufacturer first. The JBL
  Cinema SB595 is the one to be most careful with — a 3.1.2 at €349 would be the bargain of the list, and
  the Cinema line is also where JBL puts its virtual-Atmos bars.

The rejected list is as useful as the watched one: it is where the near-misses sit with the reason, so the
discovery scan stops offering them. The JBL **Bar 800MK2** is the cautionary tale — a €900 soundbar sold on
Dolby Atmos that dropped the up-firing drivers its predecessor had, so the older Bar 800 is on the watched
list and its replacement is not.

* Edit on the **Watchlist** page, or rebuild from the research files:
  `python tools/build_watchlist.py` (reads `tools/research/*.json`, reviews from `tools/reviews/*.json`).
* **Discover** scans the shops for soundbars that fit the criteria but match nothing on the list. A listing
  shows up there when its printed layout has enough height channels, or when it claims Atmos without
  printing a layout. A shop that prints *no* layout and *no* "Atmos" for a bar that does have height
  drivers will be missed — that is what the research files are for.
* Aliases are the tokens a shop title contains (`Q990H` → `HW-Q990H/EN`, `JBLBAR1300M2` →
  `JBLBAR1300M2BLKEP`). The matcher prefers the longest matching alias and lets rejected models win ties.
  Two extra rules keep neighbouring models apart: an alias shorter than five characters has to match as a
  whole word, and a generation marker has to agree, so a title saying MK2 (or a part number saying `M2`)
  is only ever claimed by a model whose own aliases say the same. Models that only share a layout, like the
  2023 Q600C and the 2025 Q600F, get separate entries rather than shared aliases, so a price for one is
  never compared against a price for the other.

## Command line

```bash
.venv\Scripts\python.exe main.py run-once --dry-run      # one check, print what would alert, send nothing
.venv\Scripts\python.exe main.py run-once                # one real check
.venv\Scripts\python.exe main.py run-once --country CY   # or --shop electroline --shop skroutz
.venv\Scripts\python.exe main.py report                  # current prices per model and shop
.venv\Scripts\python.exe main.py discover                # soundbars in the shops that are not watched
.venv\Scripts\python.exe main.py test-notify             # test toast + ntfy push
.venv\Scripts\python.exe main.py validate                # active criteria + check watchlist.json
.venv\Scripts\python.exe tools\selftest.py               # offline checks, no network
.venv\Scripts\python.exe main.py serve --open            # dashboard + background checks
```

## Start with the laptop

`main.py install-task` registers the Windows scheduled task **Soundbar Deal Bot** (`scheduler/task.xml`):
at your logon, after one minute, it starts `pythonw.exe main.py serve` hidden, which serves the dashboard
and runs the first check two minutes later, then every 3 hours. `task-status`, `task-run`, `task-restart`
(use this after code or config changes) and `uninstall-task` manage it.
Logs: `logs/bot.log`. Price history: `prices.db` (SQLite).

It can run next to the TV bot: this one uses port **8766** and its own database, so both dashboards can be
open at once.

## How each shop is read, and what has been tested

| Shop | Country | Method | State |
|---|---|---|---|
| Electroline | CY | Both soundbar category pages embed a JSON blob of every product (`var pageProducts`) | **Tested against the live shop**: 54 products, 25 matched |
| Stephanis | CY | Server-rendered soundbar category, 100 per page | **Tested against the live shop**: 75 products, 23 matched |
| Scandia, MegaElectric | CY | Server-rendered catalog, category 202 (Sound Bars) | **Tested against the live shop**: 11 products each, none of them a true-Atmos model today |
| Public CY | CY | Its search provider's JSON API (findbar.io) with Public's own front-end token | Ported unchanged from the TV bot, soundbar queries instead of TV ones. Not re-run here |
| Kotsovolos CY | CY | Search page `__NEXT_DATA__` for part numbers, then the shop's product and availability JSON APIs; needs the Chrome-TLS tier (`curl_cffi`) because of Akamai | Ported unchanged from the TV bot. Not re-run here |
| Public GR | GR | Same findbar.io API as Public CY. The token is issued per website, so the adapter reads it out of public.gr's own front end and caches it in `.cache/` | **Written but never run.** Verify with `run-once --shop public_gr` |
| Kotsovolos GR | GR | Same HCL Commerce APIs as Kotsovolos CY, with the store id read from the storefront and cached | **Reaches the shop; store id not found automatically.** Put it in `config.json` (below) or send the error text |
| Skroutz | GR | One `/search?keyphrase=<model>` query per watched model; the cards are read by following the product links rather than by class name | **Written but never run.** Verify with `run-once --shop skroutz` |

Every shop above turns away a plain HTTP client except Electroline, Scandia, MegaElectric and Stephanis.
Fetching escalates `requests` → `curl_cffi` (Chrome TLS impersonation) → Playwright Chromium (only if
installed). A shop that fails is skipped for that run and its previous snapshot is kept; it never triggers
alerts from stale data.

The three Greek adapters were written against the shops' documented behaviour and the structures their
Cypriot twins use, but could not be exercised from the machine this was built on, which Akamai and Skroutz
both refuse. Run each once with `--shop` before trusting the dashboard, and read the error if one fails:
the adapters raise with the reason (a rejected token, a missing store id, a Skroutz page that parsed to
nothing) rather than quietly reporting an empty shop.

### If a Greek shop cannot find its own id or token

Kotsovolos GR and Public GR each need one value that belongs to that storefront: an HCL store id and a
findbar search token. The adapters look for it on the shop's own pages and cache it in `.cache/`, and the
error says which pages they read and what they found. When the lookup comes up empty, give it the value
by hand — open the shop in a browser, view source (Ctrl+U), search for `storeId` or for a long string
starting `eyJ`, and put it in `config.json`:

```json
{
  "shops_config": {
    "kotsovolos_gr": {"store_id": "10151"},
    "public_gr": {"findbar_token": "eyJhbGciOi…"}
  }
}
```

A configured value always wins over the lookup, so this ends the problem rather than working around it
until the cache expires. Delete the entry later if you want the adapter to go back to finding it itself.

### Skroutz, and what this does not do

Skroutz quotes one price per product — it picks the shop, fulfils the order itself and adds delivery — which
is the number worth watching, and it is what the search results show.

Skroutz's `robots.txt` allows the pages this adapter uses (`/search?keyphrase=`, `/c/<id>/<slug>.html`,
and plain `/s/<id>/<slug>.html` product pages) and disallows the Skroutz API, `/products/show`, the
per-product `shops_list` and `price_graph` endpoints, and any URL carrying `filter_id=`. The adapter checks
every URL against that list before requesting it (`_assert_allowed`) and refuses the disallowed ones, so a
later edit cannot quietly drift into the API or into the per-shop price lists. One query per watched model,
at the shared one-second pause between requests.

The Skroutz **Partner API** would be the cleaner source, but it needs OAuth credentials that Skroutz issues
to merchants by email, so it is not an option for a personal watcher.

Skroutz also has its own price alerts — the bell on any product page. For the Greek side it is worth using
both: Skroutz's alert is authoritative for Skroutz, and this bot is what compares Skroutz against Public GR,
Kotsovolos GR and the Cypriot shops in one table.

### Shops that were considered and left out

* **Plaisio, you.gr, MediaMarkt GR** — no adapter yet; most of their stock is also quoted through Skroutz.
* **e-shop.gr** — reachable without any bot check, but its `robots.txt` disallows `*offset=*`, which is the
  only way to page through a category. That leaves the first 10 of roughly 80 soundbars, which is not
  enough to watch a price, so it was left out rather than half-added.

## Setup from scratch

```bash
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe tools\selftest.py
.venv\Scripts\python.exe main.py validate
.venv\Scripts\python.exe main.py run-once --dry-run --country CY
.venv\Scripts\python.exe main.py run-once --dry-run --shop skroutz
.venv\Scripts\python.exe main.py install-task
```

Then open Settings and subscribe to the ntfy topic shown there in the ntfy phone app.
