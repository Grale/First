# Source access policy

Each site below was checked against its live `robots.txt` and, where relevant,
its Content-Signal declarations. This records what was found and the decision
taken, so the reasoning can be re-examined if a site changes its policy.

Checked 8 November 2026.

---

## Open — included

| Site | What its robots.txt says | How we read it |
|---|---|---|
| **karriere.at** | `User-agent: * / Disallow:` — an *empty* Disallow, i.e. everything allowed. Publishes 8 sitemaps for crawling. No Content-Signal restrictions. | Keyword search pages → schema.org `JobPosting` JSON-LD on each detail page |
| **carierista.com** | `User-agent: * / Disallow:` — everything allowed. | Category listings → schema.org `JobPosting` JSON-LD |
| **workable.com** | `Content-Signal: search=yes, ai-input=yes, ai-train=no`. Disallows only `/j/`, `/admin`, `/auth/google`, `/user_password_resets`. | Documented public account API endpoints (not `/j/`) |
| Remotive, Remote OK, Himalayas, Jobicy, Working Nomads, Arbeitnow | Public JSON APIs offered for exactly this use | Official API |
| We Work Remotely | Public RSS category feeds | Official feed |
| Greenhouse, Lever, Ashby, Recruitee | Public job-board APIs that employers use to publish their own career pages | Official API |

`ai-train=no` is respected: nothing here is used to train anything. This is a
personal job search — retrieval and reference only, which is what
`ai-input=yes` / `use=reference` permit.

---

## Closed — excluded, and why

### kariera.gr and skywalker.gr — will not crawl

Both carry this, by name:

```
User-agent: ClaudeBot
Disallow: /

User-agent: anthropic-ai
Disallow: /

User-agent: Claude-Web
Disallow: /
```

These two Greek job boards have explicitly told Claude not to crawl them. That
is a direct instruction from the site operator to this exact client, not
general terms-of-service boilerplate.

**They are therefore excluded, and the exclusion is not worked around.**
Sending a different `User-Agent` string, routing through a proxy, or using a
headless browser would all be deliberate evasion of an access control aimed
specifically at us. The fact that it is technically easy does not make it
legitimate.

This is a real cost: together these two are the largest Greek job boards, and
Greek coverage suffers for it. The honest mitigations are:

- **Workable** (below) — most Greek *tech* employers publish there, and it is
  open. This recovers much of the gap.
- Direct company career pages via the ATS APIs, which are open.
- Subscribing to kariera.gr / skywalker.gr email alerts yourself and pointing
  the email adapter at them — the same pattern used for LinkedIn. Mail they
  send you is yours to read.

### LinkedIn — will not crawl; reached via its own emails instead

LinkedIn's robots.txt states: *"The use of robots or other automated means to
access LinkedIn without the express permission of LinkedIn is strictly
prohibited."* It permits only approved search-engine crawlers.

So the site is not crawled. Instead, `jobradar/sources/linkedin_alerts.py`
parses **LinkedIn's own job-alert emails** — messages LinkedIn deliberately
sends you, in your own mailbox. Reading your own mail is not scraping, and it
surfaces the same postings.

This requires you to switch job alerts on (setup instructions are in that
module's docstring and in the README). A mailbox search on 8 November 2026
found no LinkedIn job alerts currently configured on your account — only page
suggestions — so this source yields nothing until you create them.

Trade-off: alert emails carry title, company, location and link, but **not the
full job description**. Jobs from this source are flagged
`assessment_complete = False`, carry an explicit "limited evidence" note, and
take the incomplete-assessment penalty. They are leads to open manually, not
fully scored matches.

### Indeed, Glassdoor, StepStone, Xing

Terms prohibit automated access. Not included. Indeed and Glassdoor both offer
commercial partner APIs if this ever justifies the cost.

---

## Blocked by infrastructure, not policy

### apply.workable.com

Returns **HTTP 429 to every request from this project's cloud egress IP**,
including `robots.txt` itself. That is shared-datacenter rate limiting, not a
policy decision about this project — `workable.com/robots.txt` explicitly
permits what we want to do.

The adapter is written and registered. It is expected to work normally from a
residential IP, so **run the app from your own machine to get Greek coverage.**
The run summary reports the 429s explicitly rather than silently returning
nothing.

### EURES

The official EU job-mobility portal. Its search endpoints returned 403/404 —
the API is not publicly open. No further attempt made.

---

## Politeness

For the two HTML sources (karriere.at, carierista.com):

- Titles are filtered on the **listing page** first, so a detail page is only
  fetched for a genuine candidate — typically 10–25 detail requests per run
  rather than hundreds.
- Concurrency is capped at 3, with pacing between listing requests.
- A hard cap of 60 detail fetches per source per run.
- The User-Agent identifies the tool honestly and is never set to impersonate
  a browser or another crawler.
- Only publicly visible pages are read. No login, no paywall, no access
  control is circumvented anywhere in this project.
