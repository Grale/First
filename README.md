# Job Radar — Intelligent Job Discovery & Career Matching (POC)

A job-search engine, not a job aggregator. It discovers senior data-leadership
roles across job boards and company career pages, reads the full job
descriptions, applies hard geographic and professional eligibility rules,
estimates compensation, scores what survives on six weighted dimensions, and
pushes genuinely new matches to Telegram.

**Status: proof of concept.** It runs end-to-end against live job boards and
produces a real evaluation artifact. See `docs/POC_EVALUATION.md` for the first
run's results and what needs to change next.

---

## Quick start

```bash
pip install -r requirements.txt
```

```bash
python -m jobradar.cli run --notify-dry-run
```

That discovers, scores and writes `out/job_evaluation_<run-id>.xlsx` plus a JSON
dump, without sending anything.

To send real Telegram notifications:

```bash
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="987654321"
python -m jobradar.cli run --notify
```

Useful flags:

```bash
python -m jobradar.cli run --sources greenhouse,ashby,lever
```

```bash
python -m jobradar.cli run --shortlist-min-score 55 --notify-min-score 55
```

```bash
python -m jobradar.cli run --llm --llm-limit 25
```

---

## How it works

```
sources/ ──► dedupe ──► enrich ──────────────► score ──► storage ──► report
  │                       │                      │          │          │
  │                       ├ geo.py               │          │          ├ Excel (5 sheets)
  │                       ├ category.py          │          │          └ JSON
  │                       ├ industry.py          │          │
  │                       └ salary.py            │          └ SQLite ──► Telegram
  │                                              │                        (deduped)
  └ 7 job boards + 4 ATS APIs (149 company boards)
```

**Hard gates run before scoring and can never be overridden by a high score.**
A job that fails one is reported as excluded, with the reason, on its own sheet
so the rules can be calibrated against real misses.

| Stage | Module | What it does |
|---|---|---|
| Discovery | `jobradar/sources/` | 7 public job-board APIs + Greenhouse/Lever/Ashby/Recruitee company boards |
| Dedup | `jobradar/dedupe.py` | Canonical URL first, then fuzzy company+title+country; keeps the richest record |
| Geography | `jobradar/enrich/geo.py` | Work arrangement, remote scope, country/city resolution, US and country exclusions |
| Role | `jobradar/enrich/category.py` | Category tier, seniority, skills alignment, CDO / data-science / AI-transformation / non-data gates |
| Industry | `jobradar/enrich/industry.py` | Industry inference and Forex/CFD detection |
| Compensation | `jobradar/enrich/salary.py` | Published vs estimated salary, confidence, indicative GR/CY/AT net |
| Scoring | `jobradar/scoring/scorer.py` | Six weighted dimensions + penalties, fully explainable |
| LLM (optional) | `jobradar/llm.py` | Claude reviews the top matches for judgement calls rules handle badly |
| Output | `jobradar/report/excel.py` | Shortlist / All / Excluded / Score Breakdown / Run Summary |
| Notify | `jobradar/notify/telegram.py` | One message per genuinely new match, deduped via the ledger |

### Scoring

| Dimension | Weight |
|---|---:|
| Geography & remote eligibility | 25 |
| Professional experience & skills | 25 |
| Compensation | 20 |
| Seniority & management scope | 15 |
| Industry | 10 |
| Career progression | 5 |

Penalties are subtracted afterwards (Forex industry, salary below floor,
unverified remote scope, missing job description, low-confidence estimate).

---

## Tuning

**Everything tunable lives in `profile/profile.yaml`** — weights, geographic
tiers, exclusions, the €80,000 floor, salary benchmarks, tax parameters,
category titles and industry scores. No Python changes are needed to
recalibrate. `profile/ats_companies.yaml` holds the company career pages to
watch.

Reference documents used to calibrate the engine:
- `profile/cv.md` — the candidate profile
- `profile/ideal_job.md` — an example of a strong match
- `profile/avoid_job.md` — an example of a role to penalise

---

## Sources and terms of service

Only official public APIs and published feeds are used.

**Included:** Remotive, Remote OK, Himalayas, Jobicy, Working Nomads, We Work
Remotely (RSS), Arbeitnow, and 149 company career pages via the Greenhouse,
Lever, Ashby and Recruitee job-board APIs.

**Deliberately excluded:** LinkedIn, Indeed, Glassdoor, StepStone and Xing all
prohibit automated access in their terms. Adding them requires an official
partner API or a manual export — see `docs/POC_EVALUATION.md`.

Remote OK and Jobicy require attribution when their data is displayed.

---

## Configuration

Credentials are read from the environment only and are never written to config
or committed:

| Variable | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from `@BotFather` |
| `TELEGRAM_CHAT_ID` | Your chat id (message the bot, then read `getUpdates`) |
| `ANTHROPIC_API_KEY` | Only needed for `--llm` |
| `JOBRADAR_LLM_MODEL` | Optional model override |

### Setting up the Telegram bot

1. Message `@BotFather` on Telegram, send `/newbot`, and copy the token.
2. Send any message to your new bot.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` and read
   `result[0].message.chat.id`.
4. Export both values and run with `--notify`.

---

## Data and auditability

`data/jobs.db` (SQLite) keeps every posting seen, with the extracted job
description, the canonical URL, first/last seen timestamps, a content hash for
change detection, and a notification ledger so nothing is announced twice. A
material change to salary, location or remote eligibility is recorded as
`changed`.

---

## Caveats

Salary figures marked *estimated* are benchmark-derived, not employer-published.
Net monthly figures are **indicative only and are not tax advice**; they assume
the 50% expatriate relief applies, which must be confirmed case by case. See
`docs/METHODOLOGY.md` for the sources and assumptions behind both.
