# Methodology: scoring, salary estimation and tax modelling

Everything here is parameterised in `profile/profile.yaml`. This document
explains where the numbers come from and what they assume, so the model can be
challenged and recalibrated rather than trusted blindly.

---

## 1. Hard exclusions

These run **before** scoring. A hard exclusion can never be overridden by a high
score. Excluded jobs are kept and reported on their own sheet with the reason,
so false negatives surface during calibration.

| Rule | Trigger |
|---|---|
| USA | US location, US state abbreviation, US work-authorisation or 401(k)/W-2 language, a stated US headquarters, or a remote scope limited to the US — unless the role is explicitly Europe-wide or explicitly includes GR/CY/AT |
| Country-restricted | Remote scope confined to countries outside Greece, Cyprus and Austria |
| On-site outside permitted | On-site or hybrid anywhere other than Athens or Vienna |
| CDO | Chief Data Officer / Chief Analytics Officer / Chief AI Officer titles |
| Large-company Director | "Director of Data & Analytics" where the employer has more than 1,000 employees. Where headcount is unknown the rule is **not** applied and the gap is recorded as missing information |
| Data Science primary | An explicit DS/ML title, or DS/ML signal density exceeding data-platform density by 1.5× |
| AI transformation primary | Head/Chief/Director of AI titles, or enterprise-AI-strategy language dominating the data-platform remit |
| Forex in Cyprus | Forex/CFD brokerage in Cyprus that is on-site or hybrid. Remote Forex stays eligible but takes an 18-point penalty |
| Below salary floor | A **published** maximum below €80,000 for Greece or Austria. An *estimated* shortfall is a penalty, not an exclusion |
| Not a data role | A non-data function in the title (Product/Account/Sales/Software/Security/Clinical), engineering leadership with no data scope, fewer than three data-platform references in the whole description, analytics confined to one business function with no platform ownership, or an IC-level role with little leadership language |

### Forex detection

Deliberately conservative, because the brief warns against confusing ordinary
banking and fintech with Forex/CFD brokerage. Classification requires
brokerage-specific evidence — CFDs, MetaTrader/MT4/MT5, spreads, leverage,
liquidity providers, CySEC-regulated brokerage, or a known broker name — not
merely the words "trading" or "broker".

---

## 2. Geographic tiers

| Rank | Tier | Score |
|---:|---|---:|
| 1 | Fully remote, Europe-wide | 100 |
| 2 | Fully remote, Greece | 88 |
| 3 | Fully remote, Austria | 76 |
| 4 | Fully remote, Cyprus | 66 |
| 5 | On-site / hybrid, Athens | 54 |
| 6 | On-site / hybrid, Vienna | 40 |

A Europe-wide role that does **not** confirm it can hire in Greece, Cyprus or
Austria is multiplied by **0.82** and flagged, because "remote in Europe"
routinely means "remote in the countries where we hold an entity". Remote scope
that is not stated anywhere also attracts an 8-point penalty.

Work arrangement is inferred from the title, location field, tags and
description. A posting that names a concrete office location and never says
"remote" is treated as on-site — without this, every unstated-arrangement local
job was wrongly credited with the much higher remote-country tier score.

---

## 3. Salary benchmarks

Gross annual EUR for a head/manager-level data role, as `[p25, median, p75]`,
in `profile/profile.yaml`.

| Market | Head | Director | Manager |
|---|---|---|---|
| Greece | 70–105k (med 85k) | 85–130k | 55–85k |
| Cyprus | 65–105k (med 82k) | 80–125k | 55–85k |
| Austria | 95–140k (med 115k) | 110–165k | 80–115k |
| EU remote | 85–135k (med 105k) | 100–155k | 70–110k |

These were anchored on, and should be re-validated against:

- TalentUp: Head of Data — Athens ≈ €74,800; Greece €74,700–89,800; Cyprus
  ≈ €71,100; Vienna ≈ €109,300 (base, aggregator data, gross/net not stated)
- WhereWeWork.gr: Head of Data & Analytics, Thessaloniki €5,500–10,000 gross
  per month (≈ €86,000/yr at the €7,200 average)
- Payscale: Senior Data Engineer, Austria ≈ €75,000 average base (2026)
- Jobicy: Data Engineer medians — Greece ≈ $65,150, Austria ≈ €70,900
- Emerald Zebra / Cyprus postings: Data Analyst, Limassol €42–55k gross

The benchmark midpoint is multiplied by a **company-size multiplier**
(bigtech 1.45 → nonprofit 0.78) and an **industry multiplier**
(Forex/CFD 1.18 → public/nonprofit 0.82).

**Known weakness:** the aggregator sources disagree with one another by 20–30%,
none is a proper salary survey, and the `EU_REMOTE` p75 of €135,000 is the least
evidenced figure in the table. Treat every "Medium"/"Low" confidence estimate as
a hypothesis to verify, not a number to negotiate against.

### Confidence levels

| Level | Meaning |
|---|---|
| High | Published in the posting |
| Medium | Benchmark estimate with country, seniority, industry and company size all known |
| Low | Benchmark estimate with one or more of those unknown |

---

## 4. Tax model

> **Indicative only. Not tax advice.** Every figure assumes the 50% expatriate
> relief applies, which must be confirmed case by case.

### Greece

- 2026 employment-income scale: 9% to €10k, 20% to €20k, 26% to €30k,
  34% to €40k, 39% to €60k, 44% above. The 2026 reform cut most bands by two
  points and introduced the 39% band; rates also vary by number of dependent
  children, which the model does **not** apply.
- e-EFKA employee contribution 13.37%, capped at €7,761.94/month (2026).
- **Article 5C L.4172/2013** exempts 50% of Greek employment income for seven
  years. It requires transfer of tax residency to Greece, no Greek tax residency
  in five of the previous six years, employment with a Greek entity or permanent
  establishment, and a two-year commitment.
- *Candidate position:* currently Cyprus-resident, so the non-residency test
  looks satisfiable. **Must be confirmed with AADE.** A 2026 public consultation
  proposed changes to the regime that were not confirmed as enacted.

### Cyprus

- 2026 scale as enacted on 22 December 2025: 0% to €22,000, 20% to €32,000,
  25% to €42,000, 30% to €72,000, 35% above.
- Social insurance 8.8% capped at €66,612/yr; GHS (GESY) 2.65% capped at
  €180,000/yr. **These two rates were not verified against an official source
  during this build and should be checked.**
- The 50% exemption applies to employment income above €55,000, for 17 years,
  **once in a lifetime**, and requires no Cyprus tax residency for 15
  consecutive years before **first** employment in Cyprus.
- *Candidate position — important:* Grigoris is **already employed in Cyprus**.
  A move to a new Cypriot employer is therefore a question of whether an
  **existing** claim continues across an employer change, not a fresh claim.
  The 2026 amendment law (published 6 March 2026) is reported to extend the
  relief to emoluments from *any* Cyprus employment rather than only the first,
  which would resolve this favourably — but that conflicts with other sources
  and **must be verified with the Cyprus Tax Department.**

### Austria

- Progressive scale to 55%; employee social security 18.07% capped at
  €6,450/month; 13th and 14th salaries taxed at 6% (modelled by splitting
  2/14ths of gross out of the progressive base).
- No equivalent 50% regime, which is why Austria needs a materially higher gross
  salary to match the same net.

### What this implies

Indicative monthly net, assuming the 50% relief applies:

| Gross | Greece | Cyprus | Austria |
|---:|---:|---:|---:|
| €80,000 | €5,185 | €5,834 | €4,235 |
| €100,000 | €6,431 | €7,260 | €5,222 |
| €120,000 | €7,773 | €8,648 | €6,189 |
| €150,000 | €9,749 | €10,726 | €7,605 |

**To match €7,000/month net, the approximate gross required is €110,000 in
Greece, €97,000 in Cyprus and €140,000 in Austria.** Without the relief, Greece
needs roughly €145,000. This is the single most important calibration number in
the project: the €80,000 floor is well below break-even on the candidate's
current package.

---

## 5. Skills alignment

Eight weighted vocabulary groups derived from the CV: core platform (3.0),
pipelines (2.5), BI (2.5), leadership (3.0), governance (2.0), cloud (1.5),
languages (1.5), applied AI (1.5). Each group saturates at three distinct hits
(or at the group size, whichever is smaller). A tier-1 role type adds 12 points,
tier-2 adds 6. Residual statistical/ML requirements subtract up to 14.

**Known bias:** this rewards job descriptions that enumerate tooling. A
management-oriented description that talks about strategy and stakeholders
without naming a stack scores *lower* than a tool-heavy description — the
opposite of the stated preference. Quantified in `docs/POC_EVALUATION.md`.
