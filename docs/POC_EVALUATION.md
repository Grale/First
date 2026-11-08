# POC Evaluation — first run

**Run:** `run-20261108-094131` · 8 November 2026 · 26 seconds
**Artifact:** `out/job_evaluation_run-20261108-094131.xlsx`

---

## Headline

The engine works. The market reachable through compliant sources does not
currently contain your job.

Of 223 unique postings discovered, **three** survived every eligibility gate,
and **none** reached the quality bar of 62/100. Every one of the 220 exclusions
was reviewed by hand and every one is correct — there are no false negatives
among the geographically eligible set.

That is not a scoring problem. It is a **source coverage** problem, and it is
concentrated on exactly the places you care about most. Only 3 of 223 postings
even mentioned Greece, Austria or Cyprus in their location field, and all three
were sales or narrow-analytics roles.

**The most important thing this run produced is not the shortlist. It is the
finding in §6 about your compensation floor.**

---

## 1. Funnel

| Stage | Count |
|---|---:|
| Fetched (after title prefilter) | 297 |
| Unique after deduplication | 223 |
| — duplicates collapsed | 74 |
| Excluded — geography | 195 |
| Excluded — professional mismatch | 25 |
| Excluded — compensation | 0 |
| **Eligible** | **3** |
| **High-quality matches (≥62)** | **0** |

### Exclusion breakdown

| Reason | Count |
|---|---:|
| On-site / hybrid outside Athens or Vienna | 139 |
| US-based, US-only remote, or US work authorisation | 38 |
| Remote restricted to a country outside GR/CY/AT | 18 |
| Not a data role — title denotes a different function | 13 |
| Not a data role — too few data-platform references | 5 |
| Analytics confined to one business function | 3 |
| Engineering leadership with no data scope | 2 |
| Primarily data science / ML | 2 |

Compensation excluded nothing because no eligible posting published a salary
below the floor — not because the rule is inactive. It was verified separately
against a synthetic €45–60k Athens posting, which it correctly excluded.

## 2. Source quality

| Source | Fetched | Eligible | Verdict |
|---|---:|---:|---|
| Arbeitnow | 109 | 3 | **Best source.** DACH-heavy, good Austria potential |
| Greenhouse (69 boards) | 106 | 0 | High volume, almost entirely US or non-permitted EU cities |
| Ashby (39 boards) | 37 | 0 | Useful, same geographic problem |
| Lever (9 boards) | 20 | 0 | Thin |
| Jobicy | 8 | 0 | Works; mostly US |
| We Work Remotely | 7 | 0 | Works; mostly US |
| Himalayas | 6 | 0 | 1,200 postings paged, 6 passed the title filter |
| Recruitee (10 boards) | 3 | 0 | Thin |
| Remote OK | 1 | 0 | Near-useless for leadership roles |
| Remotive | 0 | 0 | **Dead.** Free tier now returns ~12 live postings total |
| Working Nomads | 0 | 0 | **Dead.** Returns 17 postings regardless of parameters |

Greenhouse covered 6,028 live postings across 69 company boards; 268 had a data
word in the title and 91 passed the prefilter. The funnel is healthy — the
geography is not.

## 3. The coverage gap

Your actual market is in four places this POC cannot legally or technically reach:

1. **Workable** — most Greek tech employers (Persado, Skroutz, Blueground,
   Viva Wallet, Hellas Direct and similar) publish there. Its public job-board
   API returned HTTP 429 to every request from this environment. **This is the
   single biggest gap.**
2. **Greek and Cypriot local boards** — kariera.gr, skywalker.gr,
   carierista.com. No public API, and their terms prohibit scraping.
3. **Austrian boards** — karriere.at, StepStone.at, devjobs.at. StepStone and
   Xing prohibit automated access.
4. **LinkedIn** — where most senior data-leadership roles in your markets are
   actually advertised. Terms prohibit automated access.

EURES, the official EU job-mobility portal, was also tried and returned
403/404 — its API is not open.

## 4. The three eligible roles

None is worth acting on. They are shown because suppressing them would hide how
the engine behaves at the margin.

| Score | Role | Company | Why it is not a match |
|---:|---|---|---|
| 41.2 | Data & AI Architect (m/w/d) | Windhoff Group | German Mittelstand IT services; remote scope unstated; location Neu-Ulm |
| 41.1 | Staff Data Analyst, Marketing | Quince | Individual-contributor analyst scoped to marketing — a clear step down |
| 40.0 | Data Strategy & Advisory Leader | Capco | Consulting advisory/sales rather than owning a data function |

There is no Top 20. Padding the list would defeat the purpose.

## 5. False positives and false negatives

### False positives still present

- **"Staff Data Analyst, Marketing" (41.1)** — survives because "Staff" reads as
  principal seniority and the description carries enough stakeholder language to
  clear the leadership gate. It is an IC analyst role. *Fix: treat analyst
  titles at staff level as IC regardless of leadership vocabulary.*
- **"Data Strategy & Advisory Leader" (40.0)** — consulting advisory roles look
  like data leadership in vocabulary but sell work rather than own a function.
  *Fix: a dedicated consulting-advisory penalty.*
- **"Data & AI Architect" (41.2)** — "Neu-Ulm" is not in the city vocabulary, so
  an on-site German role fell through to "remote, scope unstated". *Fix: treat
  an unrecognised single-token location with no remote keyword as on-site.*

All three score in the low 40s, so the 62 threshold already contains them.

### False negatives found and fixed during the build

Four scoring bugs were caught by auditing the top of the ranking, not by tests:

1. **"Athens, Greece" with no stated arrangement scored as *remote Greece* (88)
   rather than on-site Athens (54)** — inflating every local job with an
   unstated arrangement.
2. **"London", "Frankfurt am Main", "Amsterdam" were not recognised as
   countries**, so three on-site roles were ranked as remote-Europe. Fixed with
   a 180-city vocabulary.
3. **A single stray "remote" anywhere in a description marked the whole role
   remote.** Spotify's London role was ranked #2 because of it.
4. **ZoomInfo ranked #1 at 72.4 with "Headquarters: Remote-US" in its
   description** — the US gate only inspected the location field.

Two genuine false negatives were also recovered: Spotify's *Engineering Manager
— Data Platform* (killed by a too-narrow data vocabulary) and *Data Platform
Engineer* titles (killed by a "platform engineer" rule that ignored the
preceding "data"). **"Data Architect" roles were invisible entirely** —
"architect" was missing from the leadership vocabulary despite being tier-1 in
your brief.

## 6. The compensation finding — read this one

Modelling your net income across the three markets, assuming the 50% relief
applies:

| Gross | Greece net/mo | Cyprus net/mo | Austria net/mo |
|---:|---:|---:|---:|
| €80,000 | €5,185 | €5,834 | €4,235 |
| €100,000 | €6,431 | €7,260 | €5,222 |
| €120,000 | €7,773 | €8,648 | €6,189 |
| €150,000 | €9,749 | €10,726 | €7,605 |

**To stand still at €7,000/month net you need roughly €110,000 gross in Greece,
€97,000 in Cyprus, or €140,000 in Austria.**

Your stated €80,000 floor corresponds to about €5,200/month net in Greece — a
**26% pay cut**. The floor is not a floor on a sideways move; it is a floor on a
significant financial downgrade. Austria is worse than it looks: with no
equivalent relief, it needs ~40% more gross than Cyprus for the same net, which
compounds the reasons it is already your last resort.

Against the Greek benchmark for a Head of Data (€70–105k, median €85k), a
break-even move to Greece sits at roughly the 75th percentile of the market.
That is achievable, but it means the realistic target is a **Europe-wide remote
employer paying a European salary while you live in Greece** — not a Greek
employer. Which is exactly what your geographic priority order already says.

### A tax point that needs checking before anything else

The Cyprus 50% exemption is a **once-in-a-lifetime** relief tied to **first**
employment in Cyprus, requiring 15 consecutive years of prior non-residency.
You are *already* employed in Cyprus. So the question is not whether you can
claim it — it is whether an **existing** claim survives an employer change.

The 2026 Cyprus amendment law (published 6 March 2026) is reported to extend the
relief to emoluments from *any* Cyprus employment rather than only the first,
which would resolve this favourably. Sources conflict. **Confirm with the Cyprus
Tax Department before treating any Cypriot offer as 50%-relieved** — every
Cyprus net figure in the artifact depends on it.

## 7. Calibration questions for you

1. **On-site Limassol is currently excluded** by your own rules ("on-site
   outside Athens and Vienna"). You live there. Deliberate?
2. **Is €80,000 still the floor** given it implies a 26% net cut? A floor of
   ~€100,000 for Greece and ~€135,000 for Austria would encode "no financial
   downgrade".
3. **Should hybrid roles in Athens or Vienna outrank remote-Europe roles whose
   hiring countries are unconfirmed?** Today an unconfirmed Europe-wide role
   scores 82 on geography and a hybrid Athens role scores 54.
4. **Consulting firms** — in or out? They match on vocabulary but the work is
   advisory, not ownership.
5. **Is a 45-day posting window right?** Tightening it would cut noise; widening
   it would raise volume.

## 8. Recommended next iteration, in priority order

1. **Fix source coverage. Nothing else matters as much.**
   - Get Workable working — retry from a different IP, with backoff and caching.
     It alone would transform Greek coverage.
   - Add LinkedIn through a compliant route: saved-search email alerts parsed
     from a mailbox, or an official partner API.
   - Add Adzuna and Jooble (both have free API tiers covering GR/AT/CY and need
     only a key).
   - Grow the ATS registry from 149 to ~400 boards, weighted towards employers
     with Greek, Cypriot or Austrian entities.
2. **Resolve the two tax questions** in §6 — they change every net figure.
3. **Fix the skills-scoring bias.** The reference *avoid* posting (Enerwave)
   scores **78.7** on skills while the reference *ideal* posting (L'Oréal)
   scores **37.7**, purely because the first enumerates tooling and the second
   describes strategy. This directly contradicts "do not penalise a position
   because it is not hands-on". Weight responsibility-shaped language, not
   keyword density.
4. **Verify remote scope explicitly.** 22 of 26 geographically eligible roles
   did not state which countries they can hire in. This is the dominant source
   of uncertainty, and it is what the optional LLM pass exists for — run it with
   `--llm` once an API key is available.
5. **Re-tune the thresholds** once sources improve. With current coverage the
   62 floor yields nothing; the right response is more supply, not a lower bar.

### Calibration reference

After the fixes above, the engine separates the two reference documents as:

| Posting | Score | Geography |
|---|---:|---|
| Ideal (L'Oréal Head of Data & Analytics) | 66.7 | Remote Europe |
| Avoid (Enerwave Data Platforms Manager) | 53.0 | On-site Athens |

A 13.7-point gap. The *avoid* example is correctly penalised to zero on
compensation (€55–85k ⇒ ~€4,586/month net, a 34% cut) — which is precisely the
behaviour you asked for.

## 9. What was verified to work

- Hard exclusions, checked against a 12-case regression suite plus a synthetic
  below-floor Athens posting.
- Deduplication: 74 duplicates collapsed from 297 postings; a second run
  correctly reported 218 seen / 5 new.
- Telegram: message rendering verified, notification ledger prevents repeats,
  missing credentials handled cleanly. Messages were not sent because no bot
  token is configured in this environment — `README.md` has the setup steps and
  `--notify-dry-run` renders the exact payloads.
- Excel artifact: five sheets (Shortlist, All Opportunities, Excluded, Score
  Breakdown, Run Summary) with the full 21-column schema.
- Salary parser: 10-case suite covering European `75.000` notation, `90k–110k`,
  monthly-to-annual, 14-salary schemes, hourly rejection and currency
  conversion.


---

# Addendum — run 2, after expanding source access

**Run:** `run-20261108-192256` · 38 seconds · 15 sources (was 11)

After the first run concluded that *source coverage*, not scoring, was the
binding constraint, each blocked site was re-examined against its actual
`robots.txt` rather than assumed terms. That changed the picture materially.
Full findings in `docs/SOURCES.md`.

## What opened up

| Site | Finding | Result |
|---|---|---|
| **karriere.at** | `Disallow:` is *empty* — everything allowed; sitemaps published | **Austria coverage solved.** 30 postings/run with schema.org JSON-LD and published salaries |
| **carierista.com** | `Disallow:` empty — everything allowed | **Cyprus coverage solved.** Declares its own `industry` field, which flags Forex employers directly |
| **Workable** | `search=yes, ai-input=yes`; only `/j/` disallowed | Adapter written; blocked by IP, not policy (below) |
| **LinkedIn** | Automated access prohibited | Not crawled. Adapter parses LinkedIn's **own job-alert emails** from your mailbox instead |

## What stays closed, and why

**kariera.gr and skywalker.gr name `ClaudeBot`, `anthropic-ai` and
`Claude-Web` with `Disallow: /`.** Those operators have told this client
specifically not to crawl them. The block is respected and deliberately not
worked around — a spoofed user-agent or a proxy would be evasion of an access
control aimed at us, and the fact that it would be trivial does not make it
legitimate. This costs real Greek coverage; `docs/SOURCES.md` lists the honest
mitigations (Workable, ATS boards, and subscribing to those boards' own email
alerts, which you are entitled to read).

## Results

| | Run 1 | Run 2 |
|---|---:|---:|
| Sources | 11 | 15 |
| Fetched | 297 | 342 |
| Unique | 223 | 262 |
| **Eligible** | **3** | **8** |
| Vienna roles surfaced | 0 | 11 |
| Greece / Cyprus roles surfaced | 0 | 2 |
| Above the 62 bar | 0 | 0 |

**Vienna appeared for the first time.** Five of the top eight are Austrian, led
by *Lead ETL Developer / Technical Architect – Big Data* at Erste Bank (56.3).
That posting was **excluded entirely in run 1** — see the salary bug below.

## The Austrian salary bug this surfaced

Austrian law obliges employers to publish the collective-agreement minimum.
Red Bull's *Data & AI Platform Architect* publishes **EUR 2,535/month** — and
the same posting says real packages *"liegen deutlich über"* it. Volksbank
publishes **EUR 43,465.52** alongside *"das tatsächliche Gehalt bereden wir in
einem persönlichen Gespräch"*.

Read literally, those figures hard-excluded good Vienna roles on the EUR 80,000
floor. The engine now distinguishes:

- **Single-point value** → collective-agreement minimum. Used as a lower bound
  only; the range becomes the benchmark floored at that value, confidence drops
  to Medium, and the below-floor exclusion does not apply.
- **A stated range** → the employer's real band, kept as published at High
  confidence with the exclusion applying normally.

Of 30 karriere.at postings, 24 were statutory minimums and 5 were genuine
ranges. Monthly Austrian figures are now annualised at 14 instalments, not 12.

## Why nothing still clears 62

This is now a *calibration* question rather than a coverage one, and it is
worth your decision:

1. **Austria is ranked last in your own priority order** (geography score 40 of
   100). Even a perfect Vienna role caps at about 85, and after realistic
   skills and compensation scores it lands in the 50s. Erste Bank at 56.3 is
   close to the practical ceiling for Vienna.
2. **Austrian net income is the real blocker.** EUR 100,000 gross in Austria
   nets about EUR 5,222/month against your current EUR 7,000 — a 25% cut, and
   there is no Austrian equivalent of the 50% relief. The compensation
   dimension correctly scores these near zero.

So the engine is not failing on Austria; it is telling you, consistently, that
Austria does not work financially unless the gross is near EUR 140,000. That
matches your own description of Austria as a last resort.

## Revised next steps

1. **Run the app from your own machine.** This single change switches on Greek
   coverage via Workable — the largest remaining gap — because the block is an
   IP rate limit, not a policy.
2. **Create the LinkedIn job alerts** and set `LINKEDIN_IMAP_*`. A mailbox check
   found none configured, so that source currently yields nothing.
3. **Decide the Vienna question.** If Austrian roles should be able to clear the
   bar, either raise the on-site Vienna tier score above 40 or lower the
   threshold — but note that the compensation maths, not the geography score,
   is what actually holds them down.
4. Items 2–5 from the original evaluation (tax verification, the skills-scoring
   bias, remote-scope verification, threshold re-tuning) all still stand.
