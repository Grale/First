"""Role classification, seniority, skills alignment and the professional
hard-exclusions (CDO / data-science-primary / AI-transformation-primary).

Everything keys off the JOB DESCRIPTION, not just the title - a 'Head of Data'
that is really a reporting role must score lower than a 'Data Platform Manager'
that owns architecture and a team.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------
# Skills vocabulary, derived from the CV.
# --------------------------------------------------------------------------
SKILL_GROUPS: dict[str, tuple[float, list[str]]] = {
    "core_platform": (3.0, [
        "redshift", "snowflake", "bigquery", "databricks", "synapse", "data lake",
        "lakehouse", "data warehouse", "data warehousing", "data platform",
        "dimensional model", "kimball", "star schema", "data mart", "data modelling",
        "data modeling", "medallion"]),
    "pipelines": (2.5, [
        "dbt", "airflow", "dagster", "prefect", "etl", "elt", "ingestion", "pipeline",
        "kafka", "debezium", "cdc", "change data capture", "msk", "streaming", "spark",
        "fivetran", "airbyte", "talend", "ssis", "data integration", "orchestration"]),
    "bi": (2.5, [
        "power bi", "powerbi", "tableau", "looker", "qlik", "business intelligence",
        "dashboard", "reporting", "self-serve", "self service analytics", "dax",
        "semantic layer", "metrics layer", "ssas", "analytics engineering"]),
    "cloud": (1.5, ["aws", "azure", "gcp", "google cloud", "cloud-native", "terraform",
                    "dms", "s3", "glue", "lambda", "kubernetes", "docker"]),
    "languages": (1.5, ["sql", "python"]),
    "governance": (2.0, [
        "data governance", "data quality", "data contract", "data catalog", "lineage",
        "master data", "mdm", "gdpr", "regulatory reporting", "compliance",
        "single source of truth", "data stewardship", "metadata"]),
    "leadership": (3.0, [
        "lead a team", "manage a team", "team leadership", "line management",
        "mentor", "coaching", "hiring", "recruit", "stakeholder", "roadmap",
        "data strategy", "budget", "vendor", "cross-functional", "direct reports",
        "people management", "grow the team", "build the team", "headcount"]),
    "ai_applied": (1.5, [
        "llm", "rag", "retrieval augmented", "embedding", "vector", "genai",
        "generative ai", "agentic", "mcp", "ai-assisted", "copilot", "ai agent"]),
}

# --------------------------------------------------------------------------
# Exclusion vocabularies
# --------------------------------------------------------------------------
RE_CDO = re.compile(r"\b(chief data officer|chief data (and|&) analytics officer|\bcdo\b|"
                    r"chief analytics officer|chief ai officer)\b", re.I)
RE_DIRECTOR_DA = re.compile(r"\bdirector[, ]{0,3}(of )?(data (and|&) analytics|analytics (and|&) data|"
                            r"data \+ analytics)\b", re.I)

DS_TITLE = re.compile(r"\b(data scien(ce|tist)|machine learning|ml engineer|ml scientist|"
                      r"research scientist|applied scientist|quant(itative)?|ai research|"
                      r"deep learning|nlp engineer|computer vision|statistician|econometric)\b", re.I)
DS_BODY = re.compile(r"\b(pytorch|tensorflow|scikit[- ]learn|keras|xgboost|bayesian|"
                     r"statistical model|predictive model|hypothesis test|a/b test(ing)? framework|"
                     r"time series forecast|optimi[sz]ation model|linear programming|"
                     r"stochastic|ph\.?d\.?|mathematic(s|al)|operations research|"
                     r"feature engineering|model training|mlops|model deployment)\b", re.I)
DATA_ENG_BODY = re.compile(
    r"\b(data (warehouse|warehousing|platform|lake|lakehouse|mesh|infrastructure|"
    r"architecture|engineering|modelling|modeling|governance|quality|catalog|"
    r"contract|pipeline|product|stack|ingestion|collection|integration|"
    r"strategy|team|estate|asset)s?|"
    r"dbt|airflow|dagster|etl|elt|business intelligence|\bbi\b|"
    r"power bi|tableau|looker|qlik|superset|metabase|"
    r"snowflake|redshift|bigquery|databricks|synapse|clickhouse|"
    r"kafka|spark|flink|streaming|event (delivery|streaming|pipeline)|"
    r"analytics engineering|dimensional model|star schema|semantic layer|"
    r"self[- ]serve analytics|reporting|dashboard|kpi|single source of truth|"
    r"pipelines?|query engine|olap|data[- ]driven decision)\b", re.I)

# Titles that are strong enough evidence on their own to skip the density gate.
STRONG_DATA_TITLE = re.compile(
    r"\b(head of (data|bi|business intelligence|analytics|reporting|insight)|"
    r"data (platform|warehouse|engineering|architecture|analytics|governance)|"
    r"business intelligence|analytics engineering|bi (manager|lead|director|developer)|"
    r"(director|vp|head) of (data|analytics)|chief data)\b", re.I)

AI_TRANSFORM = re.compile(
    r"\b(ai transformation|enterprise[- ]wide ai|ai[- ]first transformation|ai strategy|"
    r"ai adoption (programme|program)|ai centre of excellence|ai center of excellence|"
    r"ai operating model|head of ai|chief ai|ai roadmap for the (company|organi))\b", re.I)

MGMT_SIGNALS = re.compile(
    r"\b(lead(ing)? a team|manage(ment)? of|direct reports|line manage|team of \d+|"
    r"hire|hiring|recruit|mentor|coach|performance review|budget|headcount|"
    r"people (management|leadership)|grow(ing)? (the|a) team|build(ing)? (the|a) team|"
    r"stakeholder management|senior stakeholder|executive|c-level|board|strategy|"
    r"roadmap|vendor management|organisational|organizational)\b", re.I)
HANDSON_SIGNALS = re.compile(
    r"\b(hands[- ]on|write code|coding daily|individual contributor|\bic\b|"
    r"you will (build|code|develop|implement)|day[- ]to[- ]day (coding|development)|"
    r"80% (coding|hands)|primarily technical)\b", re.I)

# --------------------------------------------------------------------------
# Role-DOMAIN gate. The title prefilter is deliberately wide, so this is where
# non-data functions that merely contain a data word get removed:
# "Product Manager, Analytics", "Key Account Manager - Data Center",
# "Staff Platform Security Engineer", "Clinical Data Manager".
# --------------------------------------------------------------------------
OTHER_FUNCTION = re.compile(
    r"\b(product (manager|owner|lead|director|designer)|"
    r"(key |enterprise |strategic )?account (manager|executive|director)|"
    r"partner (manager|director|lead)|gtm engineer|go[- ]to[- ]market|"
    r"projektmanager|projektleiter|vertrieb|kundenbetreuer|"
    r"sales (manager|director|lead|engineer)|business development|partnership|"
    r"customer (success|support|experience)|"
    r"(?<!data )(?<!analytics )(?<!warehouse )"
    r"(software|security|network|platform|solutions?|support|systems|cloud|"
    r"site reliability|qa|test|frontend|front-end|backend|back-end|full[- ]stack|"
    r"mobile|firmware|hardware|devops)\s+engineer|"
    r"engineer,\s*(software|security|platform|infrastructure)|"
    r"clinical data|regulatory affairs|medical (writer|affairs)|"
    r"content (manager|lead|strategist)|community manager|"
    r"mentor|tutor|instructor|curriculum|teaching|"
    r"recruiter|talent acquisition|office manager|project manager)\b", re.I)

# Engineering-leadership titles only count when they are data-scoped.
ENG_LEAD = re.compile(r"\b(head of engineering|director of engineering|"
                      r"engineering (manager|director|lead)|vp of engineering)\b", re.I)
DATA_SCOPED = re.compile(r"\b(data|analytics|bi\b|business intelligence|warehouse|"
                         r"lakehouse|etl|insight)\b", re.I)

# Analytics confined to a single business function is not the data leadership
# remit the candidate is targeting.
NARROW_ANALYTICS = re.compile(
    r"\b(people|talent|hr|human resources|workforce|marketing|growth|sales|"
    r"revenue|customer|supply chain|clinical|risk|fraud)\s+"
    r"(analytics|insights?|reporting|data)\b", re.I)

SENIORITY_PATTERNS = [
    ("director", re.compile(r"\b(director|vp|vice president)\b", re.I)),
    ("principal", re.compile(r"\b(principal|lead|chief) (data |solution |enterprise )?architect\b", re.I)),
    ("head", re.compile(r"\bhead of\b", re.I)),
    ("principal", re.compile(r"\b(principal|staff)\b", re.I)),
    ("manager", re.compile(r"\b(manager|management)\b", re.I)),
    ("lead", re.compile(r"\b(lead|leader|team lead|architect)\b", re.I)),
    ("senior_ic", re.compile(r"\b(senior|sr\.?)\b", re.I)),
]

JUNIOR = re.compile(r"\b(junior|graduate|intern|entry[- ]level|associate|trainee|working student)\b", re.I)


def _count_hits(text: str, words: list[str]) -> tuple[int, list[str]]:
    hits = [w for w in words if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", text)]
    return len(hits), hits


def classify(job, cfg) -> None:
    title = job.title or ""
    body = (job.description or "")
    low_body = body.lower()
    low_all = f"{title}\n{body}".lower()

    # -------- seniority ---------------------------------------------------
    job.seniority = "ic"
    for name, rx in SENIORITY_PATTERNS:
        if rx.search(title):
            job.seniority = name
            break
    if JUNIOR.search(title):
        job.seniority = "ic"

    # -------- category tier -----------------------------------------------
    tl = title.lower()
    tier, label, matched = "", "", ""
    for key in ("tier1", "tier2", "tier3"):
        for t in cfg["categories"][key]["titles"]:
            if t in tl:
                tier, label, matched = key, cfg["categories"][key]["label"], t
                break
        if tier:
            break
    if not tier:
        # Fall back to responsibilities when the title is non-standard.
        bi_dw = len(re.findall(r"business intelligence|data warehouse|analytics engineering|"
                               r"data platform|dimensional|power bi|tableau|semantic layer", low_body))
        de = len(re.findall(r"data engineer|pipeline|etl|elt|airflow|dbt|kafka|spark", low_body))
        an = len(re.findall(r"analytics|reporting|insight|dashboard|kpi", low_body))
        if bi_dw >= 3:
            tier, label = "tier1", cfg["categories"]["tier1"]["label"]
        elif de >= 3:
            tier, label = "tier2", cfg["categories"]["tier2"]["label"]
        elif an >= 3:
            tier, label = "tier3", cfg["categories"]["tier3"]["label"]
        matched = "inferred from responsibilities"
    job.category_tier = tier
    job.job_category = label or "Unclassified"

    # -------- hard exclusions --------------------------------------------
    ex = cfg["exclusions"]
    if ex["cdo"]["enabled"] and RE_CDO.search(title):
        job.eligible = False
        job.exclusion_reasons.append(f"{ex['cdo']['reason']} (title: {title[:60]})")

    if ex["director_large_company"]["enabled"] and RE_DIRECTOR_DA.search(title):
        thr = ex["director_large_company"]["employee_threshold"]
        n = job.company_employees_est
        if n and n > thr:
            job.eligible = False
            job.exclusion_reasons.append(
                f"{ex['director_large_company']['reason']} (~{n:,} employees)")
        elif n is None:
            job.missing_info.append(
                f"Company headcount unknown - cannot apply the >{thr}-employee "
                "Director of D&A exclusion")

    # Data science primary: strong DS signals that clearly outweigh data/BI ones.
    ds_t = bool(DS_TITLE.search(title))
    ds_hits = len(DS_BODY.findall(body))
    de_hits = len(DATA_ENG_BODY.findall(body))
    if ex["data_science_primary"]["enabled"]:
        explicit_ds_title = re.search(
            r"\b(data scientist|machine learning (engineer|scientist|manager|lead)|"
            r"ml engineer|research scientist|applied scientist|quantitative analyst|"
            r"(head|director|vp) of (data science|machine learning|ai research))\b",
            title, re.I)
        if explicit_ds_title:
            job.eligible = False
            job.exclusion_reasons.append(
                f"{ex['data_science_primary']['reason']} "
                f"(title is explicitly '{explicit_ds_title.group(0)}')")
        elif ds_t and de_hits < 4:
            job.eligible = False
            job.exclusion_reasons.append(
                f"{ex['data_science_primary']['reason']} (title indicates DS/ML; "
                f"only {de_hits} data-platform signals in the JD)")
        elif ds_hits >= 6 and ds_hits > de_hits * 1.5:
            job.eligible = False
            job.exclusion_reasons.append(
                f"{ex['data_science_primary']['reason']} "
                f"({ds_hits} DS/ML signals vs {de_hits} data-platform signals)")
        elif ds_hits >= 3 and de_hits >= 4:
            job.negatives.append(
                f"Includes some data-science/ML scope ({ds_hits} signals) alongside "
                "the data-platform remit")

    # AI transformation primary
    if ex["ai_transformation_primary"]["enabled"]:
        ai_t = len(AI_TRANSFORM.findall(f"{title} {body[:4000]}"))
        if re.search(r"\b(head of ai|chief ai|director of ai|vp of ai|ai transformation lead)\b", tl):
            job.eligible = False
            job.exclusion_reasons.append(
                f"{ex['ai_transformation_primary']['reason']} (title: {title[:60]})")
        elif ai_t >= 3 and de_hits < 5:
            job.eligible = False
            job.exclusion_reasons.append(
                f"{ex['ai_transformation_primary']['reason']} "
                f"({ai_t} enterprise-AI-strategy signals, {de_hits} data-platform signals)")

    # ---- role-domain gate: is this actually a DATA role? ----------------
    if ex["not_leadership"]["enabled"]:
        if OTHER_FUNCTION.search(title):
            job.eligible = False
            job.exclusion_reasons.append(
                f"Not a data role - the title denotes a different function "
                f"({OTHER_FUNCTION.search(title).group(0)})")
        elif ENG_LEAD.search(title) and not DATA_SCOPED.search(title):
            job.eligible = False
            job.exclusion_reasons.append(
                "Engineering-leadership role with no data/analytics scope in the title")

    # Data-vocabulary density: a genuine data role talks about data systems.
    # Skipped when the TITLE is already unambiguous evidence of a data role.
    if (job.eligible and ex["not_leadership"]["enabled"] and body.strip()
            and not STRONG_DATA_TITLE.search(title)):
        de_hits = len(DATA_ENG_BODY.findall(body))      # recount, broader vocab
        if de_hits < 3:
            job.eligible = False
            job.exclusion_reasons.append(
                f"Not a data role - only {de_hits} data-platform/BI references in "
                "the whole job description")

    # Analytics scoped to a single business function (people/marketing/sales).
    if job.eligible:
        narrow = NARROW_ANALYTICS.search(f"{title} {body[:2500]}")
        platform_own = re.search(
            r"\b(data platform|data warehouse|data architecture|data engineering|"
            r"analytics engineering|data governance)\b", low_body)
        if narrow and NARROW_ANALYTICS.search(title) and not platform_own:
            job.eligible = False
            job.exclusion_reasons.append(
                f"Analytics confined to one business function ('{narrow.group(0)}') "
                "with no data-platform ownership")
        elif narrow and NARROW_ANALYTICS.search(title):
            job.negatives.append(
                f"Scope is {narrow.group(0)} rather than the whole data function")

    # Not a leadership role at all
    if ex["not_leadership"]["enabled"] and job.eligible:
        mgmt = len(MGMT_SIGNALS.findall(body))
        ic_like = job.seniority in ("ic", "senior_ic") or (
            job.seniority == "principal" and
            re.search(r"\b((software|data|platform|analytics) engineer|"
                      r"(data|business|bi) analyst|scientist|developer)\b", title, re.I))
        if ic_like and mgmt < 3:
            job.eligible = False
            job.exclusion_reasons.append(
                f"{ex['not_leadership']['reason']} (seniority '{job.seniority}', "
                f"{mgmt} leadership signals)")

    if not body.strip():
        job.assessment_complete = False
        job.missing_info.append("Full job description could not be retrieved")


def skills_score(job, cfg) -> tuple[float, list[str], list[str]]:
    """0-100 alignment against the CV. Returns (score, positives, negatives)."""
    text = f"{job.title}\n{job.description}".lower()
    if not job.description.strip():
        return 35.0, [], ["Scored on title only - no job description available"]

    total_w, got_w, pos, neg = 0.0, 0.0, [], []
    detail: list[str] = []
    for name, (weight, words) in SKILL_GROUPS.items():
        n, hits = _count_hits(text, words)
        total_w += weight
        # Saturating credit. Denominator is capped at the group size so small
        # groups (e.g. languages = sql/python) can still reach full credit.
        need = min(3.0, float(len(words)))
        got_w += weight * min(1.0, n / need)
        if n:
            detail.append(f"{name}:{n}")
        if n >= 3:
            pos.append(f"Strong {name.replace('_', ' ')} overlap ({', '.join(hits[:4])})")
    base = 100.0 * got_w / total_w if total_w else 0.0

    # Category tier modifies alignment: tier1 is the candidate's core expertise.
    tier_bonus = {"tier1": 12.0, "tier2": 6.0, "tier3": 0.0, "": -10.0}.get(job.category_tier, 0.0)
    score = base + tier_bonus

    if job.category_tier == "tier1":
        pos.append(f"Core-expertise role type: {job.job_category}")
    elif job.category_tier == "tier2":
        pos.append(f"Second-priority role type: {job.job_category}")
    elif not job.category_tier:
        neg.append("Role type does not map to any target job category")

    # Penalise heavy maths/DS requirements that remain after the hard filter.
    ds_hits = len(DS_BODY.findall(job.description))
    if ds_hits >= 4:
        score -= min(14.0, ds_hits * 2.0)
        neg.append(f"Job description carries {ds_hits} statistical/ML requirement signals")

    if detail:
        pos.append("Skill-group hits -> " + ", ".join(detail))
    return max(0.0, min(100.0, round(score, 1))), pos, neg


def seniority_score(job, cfg) -> tuple[float, list[str], list[str]]:
    ladder = cfg["seniority"]["ladder"]
    base = float(ladder.get(job.seniority, 20))
    pos, neg = [], []
    body = job.description or ""
    mgmt = len(MGMT_SIGNALS.findall(body))
    hands = len(HANDSON_SIGNALS.findall(body))

    if mgmt >= 5:
        base += cfg["seniority"]["management_signal_bonus"]
        pos.append(f"Strong management/ownership scope ({mgmt} leadership signals)")
    elif mgmt >= 2:
        base += cfg["seniority"]["management_signal_bonus"] / 2
        pos.append(f"Some management scope ({mgmt} leadership signals)")
    else:
        neg.append("Little explicit team-leadership or ownership language")

    if hands >= 3 and mgmt < 3:
        base -= cfg["seniority"]["pure_handson_penalty"]
        neg.append(f"Reads as predominantly hands-on ({hands} IC signals, {mgmt} mgmt signals)")

    team = re.search(r"team of (\d+)", body, re.I)
    if team:
        pos.append(f"Team size stated: {team.group(1)}")
    else:
        job.missing_info.append("Team size / reporting line not stated")

    return max(0.0, min(100.0, round(base, 1))), pos, neg


def career_score(job, cfg) -> tuple[float, list[str], list[str]]:
    """Strategic ownership & progression beyond the candidate's current role."""
    body = (job.description or "").lower()
    pos, neg, s = [], [], 50.0
    strategic = {
        "owns the data strategy": r"(own|define|shape|set)[^.]{0,40}data (strategy|vision)",
        "builds a function": r"(build|grow|scale|establish)[^.]{0,40}(team|function|department|capability)",
        "budget ownership": r"(budget|p&l|cost (centre|center)|spend)",
        "exec/board exposure": r"(c-level|executive (team|committee)|board|leadership team|cto|cdo|cfo)",
        "platform ownership": r"(own|accountable for)[^.]{0,40}(platform|architecture|data estate)",
        "governance ownership": r"(data governance|data quality framework|data contracts)",
        "transformation mandate": r"(transformation|modernis|moderniz|re-?platform|greenfield)",
    }
    for label, rx in strategic.items():
        if re.search(rx, body):
            s += 8
            pos.append(f"Strategic scope: {label}")
    if job.seniority in ("director", "head"):
        s += 6
        pos.append(f"Step up / lateral at {job.seniority} level")
    if job.seniority in ("manager", "lead") and job.category_tier == "tier1":
        pos.append("Manager-level but in the candidate's core discipline")
    if job.seniority in ("ic", "senior_ic"):
        s -= 25
        neg.append("Individual-contributor level - a step back from Head of D&A")
    return max(0.0, min(100.0, round(s, 1))), pos, neg
