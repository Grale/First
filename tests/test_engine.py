"""Regression suite for the matching engine.

Run:  python -m pytest tests/ -q      (or: python tests/test_engine.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobradar.config import load_profile                      # noqa: E402
from jobradar.dedupe import dedupe                            # noqa: E402
from jobradar.enrich.salary import net_monthly                # noqa: E402
from jobradar.models import Job                               # noqa: E402
from jobradar.normalize import canonical_url, parse_salary    # noqa: E402
from jobradar.scoring.scorer import evaluate                  # noqa: E402
from jobradar.sources.base import is_candidate_title, make_job  # noqa: E402

CFG = load_profile()
FAILS: list[str] = []


def check(cond, label):
    if not cond:
        FAILS.append(label)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")


def job(title, loc, desc, src="greenhouse", **kw):
    j = make_job(src, "1", "https://example.com/j/1", title, kw.pop("company", "Acme"),
                 loc, desc, "2026-11-01")
    for k, v in kw.items():
        setattr(j, k, v)
    evaluate(j, CFG)
    return j


def test_salary_parser():
    print("\n[salary parser]")
    cases = [
        ("Salary: EUR90,000 - EUR120,000 per year", 90000, 120000),
        ("We offer 75.000 - 95.000 EUR gross annually", 75000, 95000),
        ("range of 80k - 110k EUR", 80000, 110000),
        ("between 42 and 55K gross annually", 42000, 55000),
        ("5,500 EUR to 10,000 EUR gross per month", 66000, 120000),
    ]
    for text, lo, hi in cases:
        a, b, _, _ = parse_salary(text)
        check((a, b) == (lo, hi), f"{text[:40]!r} -> {lo}-{hi} (got {a}-{b})")
    for text in ("$30 - $45 per hour", "competitive salary", ""):
        a, _, _, _ = parse_salary(text)
        check(a is None, f"{text[:30]!r} -> no salary")


def test_canonical_url():
    print("\n[canonical url]")
    check(canonical_url("https://WWW.X.com/j/1/?utm_source=a&id=7#top")
          == "https://x.com/j/1?id=7", "tracking params and fragment stripped")


def test_geography():
    print("\n[geography gates]")
    cases = [
        ("Remote, United States", "401(k), must be authorized to work in the US", False, None),
        ("Anywhere in the World", "Headquarters: Remote-US", False, None),
        ("Remote - Europe", "Work from anywhere in Europe", True, "remote_europe"),
        ("Remote (Greece)", "We hire in Greece", True, "remote_greece"),
        ("Remote - Cyprus", "Remote within Cyprus", True, "remote_cyprus"),
        ("Berlin, Germany", "On-site in Berlin", False, None),
        ("Remote - Germany", "You must be based in Germany", False, None),
        ("London", "Data Platform studio. Some people work remote sometimes.", False, None),
        ("Frankfurt am Main", "A leading index provider", False, None),
        ("Athens, Greece", "Join our Athens office", True, "onsite_athens"),
        ("Vienna, Austria", "On-site in our Vienna HQ", True, "onsite_vienna"),
    ]
    base = ("data warehouse dbt airflow power bi business intelligence pipeline "
            "data governance team of 6 stakeholder budget roadmap mentor hiring strategy")
    for loc, desc, want_elig, want_tier in cases:
        j = job("Head of Data", loc, f"{desc}\n{base}")
        ok = j.eligible == want_elig and (want_tier is None or j.geo_tier == want_tier)
        check(ok, f"{loc[:28]:30} -> eligible={j.eligible} tier={j.geo_tier}")


def test_professional_exclusions():
    print("\n[professional gates]")
    base = ("data warehouse dbt airflow power bi business intelligence data governance "
            "team of 6 stakeholder budget roadmap mentor hiring data strategy")
    check(not job("Chief Data Officer", "Remote - Europe", base).eligible, "CDO excluded")
    check(not job("Director of Data & Analytics", "Remote - Europe", base,
                  company_employees_est=5000).eligible,
          "Director of D&A at >1000 employees excluded")
    check(job("Director of Data & Analytics", "Remote - Europe", base,
              company_employees_est=300).eligible,
          "Director of D&A at a smaller company kept")
    check(not job("Senior Data Scientist", "Remote - Europe",
                  "pytorch tensorflow bayesian statistical model phd mathematics").eligible,
          "Data Scientist excluded")
    check(not job("Head of AI Transformation", "Remote - Europe",
                  "ai transformation enterprise-wide ai ai strategy ai operating model").eligible,
          "AI transformation lead excluded")
    check(not job("Product Manager - Data Platform", "Remote - Europe", base).eligible,
          "Product Manager excluded")
    check(not job("Staff Platform Security Engineer", "Remote - Europe", base).eligible,
          "Security Engineer excluded")
    check(job("Engineering Manager - Data Platform", "Remote - Europe", base).eligible,
          "data-scoped Engineering Manager kept")
    check(job("Data Architect", "Remote - Europe", base).eligible, "Data Architect kept")
    check(is_candidate_title("Data Architect"), "Data Architect passes the title prefilter")


def test_forex():
    print("\n[forex rules]")
    fx = ("CFDs contracts for difference MetaTrader MT5 CySEC leverage spreads "
          "trading platform liquidity provider data warehouse dbt airflow etl "
          "business intelligence team of 6 strategy budget mentor stakeholder")
    j = job("Head of Data Engineering", "Limassol, Cyprus", fx + " Hybrid, 3 days per week in the office")
    check(not j.eligible, "on-site/hybrid Cyprus forex excluded")
    j = job("Head of Data Engineering", "Remote - Europe", fx)
    check(j.eligible and j.industry == "forex_cfd", "remote forex kept but flagged")
    check(any("Forex" in n for n in j.negatives), "forex penalty recorded")


def test_salary_floor():
    print("\n[salary floor]")
    j = job("BI Manager", "Athens, Greece",
            "Power BI reporting dashboards SQL data warehouse business intelligence "
            "team of 3 stakeholder budget. Salary 45.000 - 60.000 EUR gross per year.")
    check(not j.eligible, "published salary below the floor excluded")
    j = job("Head of Business Intelligence", "Athens, Greece",
            "Own the BI strategy, data warehouse, dimensional modelling Kimball, Power BI, "
            "dbt, Airflow, SQL, Python, data governance, lead a team of 6, stakeholder "
            "management, budget, roadmap. Salary 95.000 - 115.000 EUR gross annually.")
    check(j.eligible and j.salary_confidence == "High", "published salary above the floor kept")


def test_statutory_minimum_salary():
    """Austrian ads must publish the collective-agreement MINIMUM. Treating it
    as the real salary would wrongly exclude good roles on a legal formality."""
    print("\n[Austrian statutory minimum]")
    base = ("data warehouse dbt airflow power bi business intelligence data platform "
            "architecture data governance lead a team of 6 stakeholder budget roadmap "
            "mentor hiring data strategy")
    j = job("Data Platform Manager", "Wien, Wien, AT", base, company="Firma",
            salary_published_min=35490, salary_published_max=35490,
            salary_is_floor=True, company_size_bucket="enterprise",
            industry="technology_saas")
    check(j.eligible, "KV-minimum role is NOT excluded on salary")
    check(j.salary_confidence == "Medium", "KV minimum downgrades confidence to Medium")
    check(j.salary_est_max > 35490, f"benchmark used above the floor ({j.salary_est_max:,.0f})")
    check("MINIMUM" in j.salary_basis, "basis explains the statutory minimum")

    k = job("BI Manager", "Wien, Wien, AT", base, company="Firma",
            salary_published_min=45000, salary_published_max=52000,
            salary_is_floor=False, company_size_bucket="enterprise",
            industry="technology_saas")
    check(not k.eligible, "a genuine published range below the floor IS excluded")


def test_jsonld_parser():
    print("\n[schema.org JobPosting parser]")
    from jobradar.sources import jsonld                      # noqa: PLC0415
    html = ('<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"JobPosting",'
            '"title":"Head of Data","datePosted":"2026-11-02",'
            '"hiringOrganization":{"@type":"Organization","name":"ACME AG"},'
            '"jobLocation":[{"@type":"Place","address":{"@type":"PostalAddress",'
            '"addressLocality":"Wien","addressRegion":"Wien","addressCountry":"AT"}}],'
            '"baseSalary":{"@type":"MonetaryAmount","currency":"EUR","value":'
            '{"@type":"QuantitativeValue","unitText":"MONTH","value":2535}}}'
            '</script>')
    post = jsonld.extract(html)
    check(post is not None and post["title"] == "Head of Data", "JobPosting extracted")
    check(jsonld.company(post) == "ACME AG", "hiringOrganization read")
    check(jsonld.location_string(post) == "Wien, Wien, AT", "jobLocation flattened")
    lo, hi, cur = jsonld.salary(post, months_per_year=14)
    check((lo, cur) == (35490.0, "EUR"),
          f"monthly salary annualised at 14 instalments (got {lo}, {cur})")
    check(jsonld.extract("<html>no ld+json here</html>") is None, "absent JSON-LD -> None")


def test_linkedin_alert_parser():
    print("\n[LinkedIn alert email parser]")
    from jobradar.sources.linkedin_alerts import parse_alert  # noqa: PLC0415
    html = ("<html><body><table>"
            "<tr><td><a href='https://www.linkedin.com/comm/jobs/view/4123456789/?trk=eml'>"
            "Head of Data Platform</a><div>Acme SaaS · Athens, Greece (Remote)</div></td></tr>"
            "<tr><td><a href='https://www.linkedin.com/comm/jobs/view/4111111111/?trk=eml'>"
            "Warehouse Associate</a><div>Gamma · Berlin</div></td></tr>"
            "</table></body></html>")
    jobs = parse_alert(html, "2026-11-07")
    check(len(jobs) == 1, f"one candidate extracted, noise dropped (got {len(jobs)})")
    check(jobs[0].title == "Head of Data Platform", "title parsed")
    check(jobs[0].company == "Acme SaaS", "company parsed")
    check(not jobs[0].assessment_complete,
          "email-sourced jobs are flagged as incomplete assessments")


def test_net_income():
    print("\n[net income model]")
    for country, lo, hi in (("GR", 6300, 6600), ("CY", 7100, 7400), ("AT", 5100, 5400)):
        n = net_monthly(100000, country, CFG)
        check(lo <= n <= hi, f"{country} EUR100k -> EUR{n:,.0f}/mo in [{lo:,}, {hi:,}]")
    check(net_monthly(90000, "GR", CFG) > net_monthly(90000, "GR", CFG, apply_exemption=False),
          "50% relief increases net")


def test_dedupe():
    print("\n[dedupe]")
    a = Job(source="a", source_id="1", url="https://x.com/1", canonical_url="https://x.com/1",
            title="Head of Data Platform", company="Acme GmbH", description="short")
    b = Job(source="b", source_id="2", url="https://y.com/2", canonical_url="https://y.com/2",
            title="Head of Data Platform (m/f/d)", company="Acme Technologies GmbH",
            description="a much longer description")
    c = Job(source="c", source_id="3", url="https://z.com/3", canonical_url="https://z.com/3",
            title="BI Manager", company="Other Ltd")
    kept, removed = dedupe([a, b, c])
    check(len(kept) == 2 and removed == 1, "fuzzy duplicate collapsed")
    check(kept[0].description == "a much longer description", "richest record retained")


def test_reference_calibration():
    print("\n[reference documents]")
    root = Path(__file__).resolve().parent.parent
    ideal = job("Head of Data & Analytics", "Remote - Europe",
                (root / "profile/ideal_job.md").read_text(),
                company="Ideal", company_size_bucket="enterprise", industry="ecommerce_retail",
                company_employees_est=90000)
    avoid = job("Data Platforms & Analytics Section Manager", "Athens, Greece",
                (root / "profile/avoid_job.md").read_text(),
                company="Avoid", company_size_bucket="enterprise", industry="energy",
                company_employees_est=1200)
    check(ideal.eligible and avoid.eligible, "both reference postings are eligible")
    check(ideal.score > avoid.score,
          f"ideal ({ideal.score}) outranks avoid ({avoid.score})")
    check(avoid.dimension_scores["compensation"] < 20,
          f"avoid is penalised on compensation ({avoid.dimension_scores['compensation']})")


def test_explainability():
    print("\n[explainability]")
    j = job("Head of Data Platform", "Remote - Europe",
            "We can hire in Greece and Cyprus. Own the data platform architecture, dbt, "
            "Airflow, Snowflake, AWS, data warehouse, dimensional modelling, Power BI, SQL, "
            "Python, data governance, data contracts, lead a team of 7, hiring, mentor, "
            "stakeholder management, budget, data strategy roadmap. Equity and bonus.",
            company_size_bucket="saas_product", industry="technology_saas")
    check(len(j.dimension_scores) >= 6, "all six dimensions scored")
    check(bool(j.positives) and bool(j.job_fit), "positives and fit summary populated")
    check(j.geo_tier == "remote_europe" and "GR" in j.remote_countries,
          "explicit GR/CY hiring detected")
    check(j.score > 80, f"strong match scores high ({j.score})")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print(f"\n{'=' * 56}")
    if FAILS:
        print(f"{len(FAILS)} FAILURE(S):")
        for f in FAILS:
            print("  -", f)
        raise SystemExit(1)
    print("All checks passed.")
