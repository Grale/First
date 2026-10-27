# Monitor Deal Bot

Watches Cyprus electronics shops for **34-inch PC monitors** and alerts you when one shop is clearly
cheaper than the others, when a shop runs a big discount, or when a watched model comes back in stock.
It starts with the laptop and serves a local dashboard.

Shops: Electroline, Scandia, MegaElectric, Stephanis, Public, Kotsovolos.

Ranking is **work and productivity first**: docking, pixel density, eye comfort and text rendering carry
the most weight, with refresh rate and response time as smaller bonuses. A gaming weighting is still
available as a second profile.

This is the TV Deal Bot retargeted. The architecture, the six shops, the three alert rules, the
dashboard and the Windows scheduled task are unchanged; what it watches and how it rates are new. The
Python package was renamed `tvbot` → `monbot`, and the 75/77-inch TV research is kept under
`tools/archive/75_77inch_tv/`.

## Read this first: what is verified and what is not

All six shops have now been run for real and all six answer. An earlier round of this work was done in
a session whose network policy refused every Cyprus shop, so the adapters shipped unverified; that is
no longer the case, and the notes below say exactly where the line now falls.

**Verified against the live shops.** The six adapters, the category discovery, the matcher and the
alert rules were run end to end. Item counts on the day: Electroline 72, Scandia 3, MegaElectric 3,
Stephanis 281, Public 45, Kotsovolos 111. A dry run matched the watch list, surfaced thirteen unknown
34-inch monitors for Discover, and fired a real cross-shop alert — the Samsung G85SD at €899 in
Electroline against €1,099 at Public and €1,399 at Stephanis, an 18% gap on one afternoon. Run
`python main.py check-shops` whenever a shop changes its site; it prints what each one returned and
names the `shops_config` key to pin if one goes wrong.

**Still only claims, not measurements.** Every specification came from a maker's spec sheet, a lab
review, a retailer spec table or a full specification page — each entry's `notes` says which, and
which fields were carried from a sibling. No entry carries a figure measured by this project, and
fields no source stated are `null` rather than guessed. Two worth your own check:

* **The Dell U3425WE's five-star TÜV Eye Comfort rating**, because it is why that model ranks first. It
  comes from Dell's own copy as quoted in distributor listings and was never confirmed in TÜV's
  Certipedia register, which is the authoritative one.
* **The Samsung G85SD's HDR tier.** Its spec page states HDR10; its sibling G85SB carries DisplayHDR
  True Black 400 and this model very likely does too. The entry records the lower figure, so its score
  is probably understated by four points rather than overstated.

**The watch list is researched from the global market, not from Cyprus stock.** Of the twelve models,
only two were found in any Cyprus shop on the day of the live run. The bot still works — it found and
priced both, and alerted on one — but most of what it watches is not sold here, and most of what the
shops do sell is VA, which your criteria exclude. Discover is the tool for closing that gap: it is
currently holding eleven unresearched 34-inch monitors.

## Daily use

* Dashboard: <http://127.0.0.1:8765> (only reachable from this laptop). Every watched model with the
  price in each shop, the cheapest shop, the lowest price ever seen, and when the next check runs.
* Alerts arrive as a Windows toast and as a push on your phone through [ntfy](https://ntfy.sh): install
  the ntfy app and subscribe to the topic shown on the Settings page. **The topic is new** - the TV
  build's topic was left behind on purpose, so alerts cannot reach the previous owner's phone.
* **Run check now** on the dashboard forces a check; **Test notification** sends a test toast and push.

## What it watches

The requirements live in one place: the `criteria` block of `config.json`, editable on the **Settings**
page.

| Setting | Value | Meaning |
|---|---|---|
| `sizes` | `[34]` | 34 inch only. 38 and 39-inch ultrawides sit in the same shop aisle; add them here and they are watched and surfaced by Discover too |
| `panels` | `["miniled", "ips"]` | Mini LED backlights and IPS. OLED is excluded for text fringing and burn-in against a static desktop, VA for off-axis shift at desk distance. A panel naming an unwanted family is rejected even when it also names a wanted one, so "Mini LED VA" fails while "Mini LED IPS" passes |
| `min_hz` | `100` | Native refresh floor. 120 Hz scores higher but 100 Hz still qualifies, so the 100 Hz work-and-dock panels stay in play |
| `min_width` / `min_height` | `3440` / `1440` | 3440×1440 or better. Excludes the 2560×1080 tier outright; 5120×2160 qualifies and scores higher on density |
| `require_height_adjust` | `true` | A fixed-height stand does not qualify |
| `require_usb_c_pd_w` | `65` | Enough to charge a laptop over one cable. 15 W and 18 W ports exist on 34-inch monitors and charge a phone; the floor exists to tell them apart. 90 W still scores higher than 65 |
| `require_kvm` | `false` | Same - a KVM earns 7 points rather than gating |
| `require_vrr` | `false` | Same |

TÜV Rheinland Eye Comfort is **scored, never required**. You asked for five stars; making that a hard
requirement would empty the watchlist, because at 34 inches almost nothing documents a star rating. It
is instead worth 11 of the work profile's 92 points — the single heaviest component after the panel
type and docking — so a five-star model wins on merit. See *The five-star question* below.

Everything downstream follows from that block: which shop listings are matched, which titles Discover
suggests, the search terms sent to Public and Kotsovolos, and which watchlist models are checked.
`python main.py validate` prints the active criteria and any watchlist entry that falls short.

Changing the criteria does **not** rewrite the watch list. Widen the size class or add VA and you also
need models to watch: run **Discover**, confirm the specs, and add them (or add research files and
rebuild, below).

## How it decides what to alert

Rules live on the Settings page (saved to `config.json`):

| Rule | Default |
|---|---|
| Cross-shop: one shop is at least X % below the next-cheapest shop for the same model | 10 % |
| List discount: a shop's price is at least Y % below its own strikethrough price | 20 % |
| Back in stock: a model that was out of stock or missing in a shop is available again | on |
| Same alert not repeated for | 7 days (a lower price re-alerts at once) |
| Checks every | 3 hours |
| Prices outside this range are treated as shop data errors | €150 to €1,800 |

The price range is a data-error filter, not a budget. It was €700–9,000 for big TVs; a 34-inch monitor
priced at €2,400 is a shop mistake, one at €249 is a real AOC. The floor started at €250 and promptly
hid that AOC by a single euro, so it is €150: above the ink cartridges and phone cases a search for
"34" returns, below anything anyone sells as a monitor.

## Ranking

Every watched model gets three scores, shown on the **Ranking** page, on each model page, and as the
order of the dashboard. Each profile is worth 92 points plus 8 for a model you star, so a perfect
model scores 100.

**Fit, `work` profile (the default).** Panel type 13 · USB-C power delivery 12 · pixel density 11 ·
TÜV Eye Comfort 11 · KVM 7 · contrast 7 · colour gamut 5 · height-adjustable stand 5 · HDR tier 5 ·
refresh 4 · model year 5 · burn-in cover 3 · curvature 2 · DisplayPort version 1 · measured response 1.

**Fit, `gaming` profile.** The same facts reweighted: refresh 18 · response 14 · panel 14 · contrast 10
· VRR 7 · HDR 7 · curvature 5 · density 4 · year 4 · DisplayPort 3 · USB-C 2 · stand 2 · KVM 1 ·
eye comfort 1. Switch on the Settings page (`scoring.profile`).

Three choices in the work profile are deliberately the opposite of a gaming score:

* **OLED ranks below IPS.** QD-OLED's triangular subpixels fringe text and WOLED's RWBG layout does so
  differently; both carry burn-in risk against a static desktop. For a screen showing the same toolbars
  eight hours a day that is a cost, however good the contrast is. In the `gaming` profile QD-OLED is
  the top panel instead — the same watchlist, reordered.
* **A quoted response time can never earn the top band.** Where a lab measured the panel the
  measurement is used; where only "1 ms GtG" exists the points are capped at the honest middle band.
  Every entry on this watchlist is currently a quote, so every one of them is capped.
* **DisplayHDR 400 scores near nothing** (2 points of 5). It certifies 400 nits and no local dimming,
  roughly what an uncertified panel of the same class does anyway. True Black 400 is the OLED tier and
  is a different standard; it earns full marks.

**Reviews (0–100)** are critic and owner evidence, each with sources and a confidence level.
**Overall** is 50 % fit + 50 % reviews by default; change the weights on Settings. **Value** is overall
per €1,000 of the cheapest in-stock price.

**Deductions** live in `tools/reviews/_fit_penalties.json` and are how a spec-sheet-good panel gets
marked down for a real flaw. A deduction may name the profiles it applies to, so QD-OLED text fringing
is charged in `work` and not in `gaming`. Current deductions cover text fringing, a VA panel at desk
distance, having no way to dock a laptop, a brightness claim that cannot be reconciled, and an
overclock the maker itself warns about.

The effect is a genuine reordering rather than a cosmetic one:

| | work | gaming |
|---|---|---|
| 1 | Dell U3425WE (80) | LG 34GS95QE (77) |
| 2 | MSI MPG341CQPX (67) | MSI MPG341CQPX (73) |
| 3 | AOC AG344UXM (61) | Dell AW3423DWF (67) |
| … | | |
| | LG 34GS95QE 10th (42) | Dell U3425WE 8th (48) |

## The five-star question

You listed TÜV Eye Comfort 5 stars as a must-have. What the research found:

* The programme is real and recent. TÜV Rheinland rates displays 1–5 stars across 15 test categories in
  three groups (image quality, ambient light management, eye care); five stars overall requires five
  stars in **every** category, and the five-star tier requires at least 120 Hz — which is why your
  instinct about 120 Hz and your instinct about eye comfort were the same instinct.
* Dell is the lead adopter, and **the U3425WE is documented as the first 34-inch monitor to earn five
  stars**. That is the main reason it tops the work ranking.
* No other 34-inch monitor found in this research documents a star rating at all. Dell's own five-star
  examples otherwise are 27-inch (U2724D/DE) and 40-inch (U4025QW).
* The U3425WE claim comes from Dell's marketing copy as quoted in distributor listings, supported by
  TÜV's own brochure for how the scale works. **It was not confirmed in TÜV's Certipedia certificate
  database**, which is the authoritative register and was unreachable from the session. It is worth
  11 points and the top rank, so verify it before buying on that basis.

Models whose rating is simply unknown score the neutral middle band, not zero — "not looked into" is not
the same as "failed".

## The watch list

`watchlist.json` is the only thing that decides which monitors are watched: **12 models** with review
evidence for all 12, plus **4 checked and rejected**. That is far short of the TV build's 74, and the
shortfall is deliberate — the prompt's own rule was that a model you cannot verify is left out for
Discover to surface rather than entered on a guess, and 12 is what
the evidence supports. Eleven more are waiting in Discover, found by the live run.

| Watched | Panel | Why it is here |
|---|---|---|
| Dell U3425WE | IPS Black | The five-star TÜV model: 120 Hz, 90 W Thunderbolt, KVM, 2000:1 |
| MSI MPG341CQPX | QD-OLED | 240 Hz with 98 W docking, a KVM and a three-year burn-in warranty in MSI's own sheet |
| AOC AG344UXM | Mini LED IPS | 1,152-zone local dimming without OLED's text or burn-in trade-offs; flat |
| Asus PA348CGV | IPS | 98 % DCI-P3, 120 Hz, 90 W; the colour-work option |
| Lenovo Y34WZ-30 | Mini LED VA | Brightest here (720 cd/m² typical) and 140 W docking; VA at desk distance is the cost |
| Dell AW3423DWF | QD-OLED | Cheapest QD-OLED, three-year burn-in cover |
| LG 34GS95QE | WOLED | 240 Hz, True Black 400, 800R; no USB-C at all |
| Samsung LS34BG850 | QD-OLED | 175 Hz QD-OLED; RTINGS measured the stand |
| Samsung LS34DG850 | QD-OLED | The G85SD. Added because the live scan found it in three Cyprus shops at €899, €1,099 and €1,399 |
| Gigabyte M34WQ | IPS | Flat, 144 Hz, KVM, cheap; USB-C wattage undocumented |
| LG 34GP83A | Nano IPS | The usual cheapest 144 Hz+ IPS at this size |
| LG 34GN850 | Nano IPS | Same panel as the 34GP83A, usually priced higher — there to catch it when it is not |

| Rejected | Why |
|---|---|
| Dell U3423WE | 60 Hz. Otherwise exactly the brief, and one digit from the U3425WE, so it has to be a negative match |
| Asus PA34VCNV | 60 Hz, 3800R. Easily confused with the PA348CGV and the PA34VC |
| Philips 34B1U5600CH | VA. 120 Hz, 100 W, KVM, Ethernet, Windows Hello webcam — rejected only on panel family |
| Samsung LS34C650 | VA. 100 Hz, 90 W, KVM |

Known candidates deliberately **left for Discover** rather than guessed: Asus ProArt PA34VC (Asus lists
100 Hz and 1900R, but its stand and resolution were not verified), and anything else the shops carry.
Run `python main.py discover` on the laptop and the unmatched 34-inch titles will come back for
research.

How each entry was verified, and what the levels mean:

* **Full specification page read in its entirety** — Samsung LS34DG850 (the only entry whose source
  page was opened and read rather than summarised).
* **Maker's own spec sheet** — Asus PA348CGV, Asus PA34VCNV, MSI MPG341CQPX, Lenovo Y34WZ-30 (PSREF).
  The strongest source for claims and no source at all for measurements.
* **Lab review or measurement** — Samsung LS34BG850 (RTINGS measured the stand), AOC AG344UXM
  (TFTCentral), LG 34GP83A, Gigabyte M34WQ, LG 34GS95QE.
* **Retailer or distributor spec table** — Dell U3425WE, Dell AW3423DWF, Dell U3423WE, Philips, Samsung
  LS34C650. Weaker; the `notes` say so, and AW3423DWF is marked `confidence: low` for this reason.
* **Carried from a sibling** — LG 34GN850, every figure taken from the 34GP83A on one review's
  statement that the two are identical. `confidence: low`, and a deduction records it.

Unverified fields are `null`, not guessed, because the scoring's unknown bands are deliberately neutral
and a confident wrong number moves the ranking. Known gaps: no measured response time, contrast or
gamut figure for any model; no curvature radius for the PA348CGV or 34GP83A; no USB-C wattage for the
M34WQ; burn-in warranty unknown for the LG and Samsung OLEDs (Samsung's sources flatly contradict each
other, so the blank does **not** mean "no cover").

### Editing and rebuilding

* Edit on the **Watchlist** page, or rebuild from the research files:
  `python tools/build_watchlist.py` (reads `tools/research/*.json`, reviews from `tools/reviews/*.json`).
* The Watchlist form uses **yes / no / unverified** selects for the KVM, stand and VRR fields rather
  than checkboxes, because a checkbox cannot say "unverified" and editing a model would otherwise turn
  an unknown fact into a definite "no" — which both changes whether it qualifies and moves its score.
* **Discover** scans the shops for titles that fit the criteria but match nothing on the list. Always
  confirm the specs before adding one. Models that were checked and failed sit in the `rejected` list
  with the reason, so the scan does not keep suggesting them — which is exactly why a model that was
  merely *unverified* must never be put there.
* Aliases are the tokens a shop title contains. They are kept long enough to be unique, and the traps
  are specific to monitors: `341CQP` is deliberately **not** an alias of the `MPG341CQPX`, `AW3423` is
  not an alias of the `AW3423DWF`, and `G85SB` cannot match a `G85SD`, because in each case a shared
  prefix would let one entry claim a different and differently-priced product's listing. Tier and range
  words that span several panels (`UltraGear`, `Odyssey`, `34GP`, `G5`, `U34`, …) are dropped as aliases
  in `tools/build_watchlist.py`.
* `tools/archive/75_77inch_tv/` holds the 75/77-inch TV research and reviews, and
  `tools/archive/65inch/` the round before that. The builder reads neither.

## What breaks on monitors, and what was done about it

The things in the TV codebase that would have failed quietly:

* **The accessory filter was inverted.** It rejected `MONITOR` and `ΟΘΟΝΗ Η/Υ` as false positives. It
  now rejects monitor peripherals — arms, stands, mounts, docking stations, hubs sold alone, cables,
  webcams, KVM boxes, `ΒΡΑΧΙΟΝΑΣ`, `ΒΑΣΗ ΟΘΟΝΗΣ`, `ΚΑΛΩΔΙΟ` — plus televisions and projectors. Every
  marker is a phrase or a word a monitor's own title cannot contain: `HUB`, `DOCK` and `KVM` are all
  words real 34-inch work monitors advertise, so none can be a reject word on its own. An explicit
  pixel count vetoes the verdict, which is how *"34 UWQHD 3440x1440 monitor with USB-C hub and
  height-adjustable stand, HDMI cable included"* survives.
* **Greek accents.** `"Καλώδιο".upper()` is `ΚΑΛΏΔΙΟ`, which does not equal `ΚΑΛΩΔΙΟ`, so half the Greek
  keywords silently never matched. Titles are now accent-folded before any keyword comparison. This was
  a live bug, caught by the title test.
* **`UHD` is not a pixel count.** Using any resolution token as the accessory veto let `Samsung Smart
  TV 43" Crystal UHD` through. Only an explicit `3440x1440`-style count vetoes now.
* **The size list is monitor sizes** (21–57 inch in monitor steps), not TV sizes. 65 and 75 are gone,
  which also means `165Hz` and `75Hz` can no longer read as a size.
* **Aspect ratios.** `21:9` normalises to `21 9`, and 21 is a real monitor size — so every ultrawide
  read as a 21-inch panel. Aspect pairs (`21 9`, `32 9`, `16 9`, …) are stripped before any size test.
* **Model codes that hide their size.** The digit-boundary rule correctly refuses to read `34` out of
  `U3425WE` or `PA348CGV`. But a code that long identifies exactly one panel, and the watchlist knows
  how big it is, so a full model-key match of six characters or more now satisfies the size gate on the
  watchlist's authority. Codes that *do* carry the size readably (`34GP83A`, `LS34BG850`, `Y34WZ30`)
  work as before.
* **Resolution and panel family are tested exclusively, not inclusively.** A TV title names its panel
  family because that is the branding; a monitor title often names neither panel nor resolution. So a
  title fails only when it names a family or resolution that is *not* wanted. Demanding a match would
  have hidden most of the market from Discover.
* **An unverified requirement is reported as unverified, never as absent.** `validate` and the rejected
  list distinguish "no height-adjustable stand" from "height-adjustable stand unverified", because the
  rejected list is otherwise a list of untruths about real products.
* **Monitor brands** replace TV brands in the two search-driven shops: Dell, LG, Samsung, AOC, MSI,
  Gigabyte, Asus, Acer, BenQ, Philips, HP, Lenovo, Iiyama, ViewSonic, Corsair, Alienware.
* **A fresh ntfy topic**, so alerts do not go to the TV build's subscriber.

## Validate before you trust it

```bash
.venv\Scripts\python.exe main.py validate       # active criteria + every watchlist entry that falls short
.venv\Scripts\python.exe tests\test_titles.py   # 65 checks: matching, Discover, accessories, alert rules
.venv\Scripts\python.exe tests\test_web.py      # 35 checks: every page 200, settings round-trip
.venv\Scripts\python.exe main.py check-shops    # the one that needs your laptop: are the six categories right?
```

`tests/test_titles.py` feeds realistic shop titles — Greek and English, real EU SKU forms, centimetre
diagonals, aspect ratios and resolutions in the same string — through `engine.match_items` and the rule
engine, and asserts what matches, what reaches Discover, what is thrown away, and that all three alert
rules fire with the right percentages. `tests/test_web.py` runs against throwaway copies of
`config.json` and `watchlist.json`, so it never touches the real ones.

Three bugs were found by writing these: the Greek accent fold, the `UHD` veto, and a crash in the
watchlist form when a numeric field was absent from the POST (`str(None).strip()` is truthy, so
`int(None)` was reached). Four more were found by running the shops for real, and every one is now a
regression case in `test_titles.py`: category discovery matching blood-pressure monitors, DJ monitors
and monitor brackets; Electroline's gaming monitors being dropped because the menu only exposes
subcategories; "Ultra WQHD" read as the 2560×1440 "WQHD" inside it, which hid every Samsung ultrawide
from Discover; and an oven measured in litres ("71 Lt / 34 Lt") offered as a 34-inch candidate.

## The browsable ranking page

`tools/artifact/ranking.html` is a standalone page holding the watch list, the scoring, the evidence
and a dated cross-shop price snapshot. It has the profile switch, a specs-versus-reviews slider and a
multiplier for every individual component, so you can ask "what if docking mattered twice as much" and
watch the order change. Opening a row shows where each point came from, what every shop charges, the
full specification with each unverified field marked as unverified, and the critic sources behind the
review score. A second table lists every 34-inch monitor the six shops carry, watched or not, with the
spread between the cheapest and the dearest.

Prices there are frozen at the moment the snapshot was taken and stamped with it, and the page says so
in its own banner. The scrapers cannot run in a browser, so the dashboard on the laptop stays the only
live answer; `main.py compare` is the live version of that second table.

The scoring is ported to JavaScript in `tools/artifact/scoring.mjs`, and the page and the parity test
import that same file, so what is tested is what the page runs:

```bash
.venv\Scripts\python.exe tools\artifact\export_prices.py        # live scan -> dated price snapshot
.venv\Scripts\python.exe tools\artifact\export_scores.py > tools\artifact\expected_scores.json
node tools\artifact\parity.mjs      # JS vs Python: models, profiles, weights, value
.venv\Scripts\python.exe tools\artifact\build_page.py           # inject watchlist + prices into the page
```

`export_prices.py --from-db` reuses the last stored run instead of scanning the shops again.

**1,800 comparisons, all matching** — the fit total and every individual component for all 12 models
under both profiles, the pixel density, the review score, the overall score across eleven fit/review
weightings, the value-per-€1,000 figure against the real price snapshot, and the resulting rank order.
`build_page.py` refuses to rebuild the page if parity reports a mismatch, so the published page cannot
drift from the bot. Rerun all four after changing `watchlist.json` or either scoring file.

## Command line

```bash
.venv\Scripts\python.exe main.py run-once --dry-run      # one check, print what would alert, send nothing
.venv\Scripts\python.exe main.py run-once                # one real check
.venv\Scripts\python.exe main.py report                  # current prices per model and shop
.venv\Scripts\python.exe main.py discover                # titles that fit the criteria but are not watched
.venv\Scripts\python.exe main.py check-shops             # is each shop's monitor category reachable and parsing?
.venv\Scripts\python.exe main.py compare                 # cross-shop price comparison, every monitor at this size
.venv\Scripts\python.exe main.py test-notify             # test toast + ntfy push
.venv\Scripts\python.exe main.py validate                # active criteria + check watchlist.json
.venv\Scripts\python.exe main.py serve --open            # dashboard + background checks
```

## Start with the laptop

`main.py install-task` registers the Windows scheduled task **Monitor Deal Bot** (`scheduler/task.xml`):
at your logon, after one minute, it starts `pythonw.exe main.py serve` hidden, which serves the
dashboard and runs the first check two minutes later, then every 3 hours. `task-status`, `task-run`,
`task-restart` (use this after code or config changes) and `uninstall-task` manage it.
Logs: `logs/bot.log`. Price history: `prices.db` (SQLite).

## How each shop is read

| Shop | Method |
|---|---|
| Electroline | category page embeds a JSON blob of every product (`var pageProducts`); the monitor category is found in the site menu or pinned in `shops_config` |
| Scandia, MegaElectric | server-rendered catalog pages, same platform. Catalog URLs carry a numeric category id (`/catalog/Televisions-195-1.html`), so the monitor id is read from the menu or pinned |
| Stephanis | server-rendered category, 100 per page; category found in the menu or pinned, paging query string appended |
| Public | its search provider's JSON API (findbar.io) with Public's own front-end token; broad queries built from the criteria, titles matched locally |
| Kotsovolos | search page `__NEXT_DATA__` for part numbers, then the shop's product and availability JSON APIs; needs the Chrome-TLS tier (`curl_cffi`) because of Akamai. The selling price is the API's `Offer` entry; its `price_EUR` field holds stale values and must not be used |

Public and Kotsovolos are queried per product word, panel family and brand against each wanted size —
22 queries for one size with the current brand list, so adding 38 and 39 inch roughly triples it. A
query that finds nothing costs one request.

Fetching escalates `requests` → `curl_cffi` (Chrome TLS impersonation) → Playwright Chromium (only if
installed). A shop that fails is skipped for that run and its previous snapshot is kept; it never
triggers alerts from stale data.

## Setup from scratch

```bash
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py validate
.venv\Scripts\python.exe main.py check-shops
.venv\Scripts\python.exe main.py run-once --dry-run
.venv\Scripts\python.exe main.py install-task
```

Then open Settings and subscribe to the ntfy topic shown there in the ntfy phone app.

## File map

| Path | What it does |
|---|---|
| `monbot/criteria.py` | **The requirements live here.** Size class, panel families, resolution floor, spec floor, the Greek fold, the aspect-ratio strip — driven by the `criteria` block in `config.json` |
| `monbot/match.py` | Matches shop titles to watchlist models (alias matching, size gate, accessory rejection) |
| `monbot/engine.py` | One check: fetch shops → match → store → rules → notify. Also the discovery scan |
| `monbot/scoring.py` | Fit score, review score, overall; the `work` and `gaming` profiles |
| `monbot/watchlist.py` | Model and Specs dataclasses, the qualify gate, `watchlist.json` load/save/validate |
| `monbot/shops/*.py` | One adapter per shop. `base.py` has the price parser, the category finder and the brand list |
| `monbot/rules.py`, `store.py`, `notify.py`, `scheduler.py`, `fetch.py`, `tasksched.py` | Alert rules, SQLite, toast+ntfy, interval scheduler, tiered fetcher, Windows task |
| `monbot/web/` | Flask dashboard: Dashboard, Ranking, Watchlist, Alerts, Discover, Settings |
| `tools/research/*.json` | Hand-curated spec research, one array per file — the source of truth |
| `tools/reviews/*.json` | Critic/owner evidence and measured figures; `_fit_penalties.json` holds the deductions |
| `tools/build_watchlist.py` | Builds `watchlist.json` from research + reviews |
| `tools/archive/` | Previous rounds' research (75/77-inch TVs, 65-inch TVs), not read by the builder |
| `tests/` | The title/rule test and the dashboard test |
