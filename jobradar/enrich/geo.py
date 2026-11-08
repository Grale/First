"""Work arrangement + remote eligibility inference.

The single most important enrichment step: geography is a HARD gate, so this
module is deliberately conservative. When a signal is ambiguous we record it in
`missing_info` and lower confidence instead of guessing in the candidate's
favour.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------
# Country / city vocabulary
# --------------------------------------------------------------------------
EU_COUNTRIES = {
    "GR": ["greece", "greek", "hellas", "ελλάδα"],
    "CY": ["cyprus", "cypriot", "κύπρος"],
    "AT": ["austria", "austrian", "österreich", "oesterreich"],
    "DE": ["germany", "german", "deutschland"],
    "FR": ["france", "french"],
    "ES": ["spain", "spanish", "españa"],
    "PT": ["portugal", "portuguese"],
    "IT": ["italy", "italian", "italia"],
    "NL": ["netherlands", "dutch", "holland"],
    "BE": ["belgium", "belgian"],
    "IE": ["ireland", "irish"],
    "GB": ["united kingdom", "uk", "england", "scotland", "wales", "britain", "british"],
    "PL": ["poland", "polish", "polska"],
    "CZ": ["czech", "czechia"],
    "SK": ["slovakia", "slovak"],
    "HU": ["hungary", "hungarian"],
    "RO": ["romania", "romanian"],
    "BG": ["bulgaria", "bulgarian"],
    "HR": ["croatia", "croatian"],
    "SI": ["slovenia", "slovenian"],
    "RS": ["serbia", "serbian"],
    "SE": ["sweden", "swedish"],
    "NO": ["norway", "norwegian"],
    "DK": ["denmark", "danish"],
    "FI": ["finland", "finnish"],
    "EE": ["estonia", "estonian"],
    "LV": ["latvia", "latvian"],
    "LT": ["lithuania", "lithuanian"],
    "CH": ["switzerland", "swiss"],
    "MT": ["malta", "maltese"],
    "LU": ["luxembourg"],
    "IS": ["iceland"],
    "UA": ["ukraine", "ukrainian"],
    "TR": ["turkey", "türkiye"],
}
NON_EU_EXCL = {
    "US": ["united states", "usa", "u.s.a", "u.s.", "america", "american"],
    "CA": ["canada", "canadian"],
    "IN": ["india", "indian"],
    "AU": ["australia", "australian"],
    "NZ": ["new zealand"],
    "SG": ["singapore"],
    "BR": ["brazil", "brasil"],
    "MX": ["mexico"],
    "AE": ["united arab emirates", "dubai", "abu dhabi"],
    "ZA": ["south africa"],
    "PH": ["philippines"], "AR": ["argentina"], "CO": ["colombia"],
    "JP": ["japan"], "CN": ["china"], "IL": ["israel"], "SA": ["saudi"],
}

CITY_COUNTRY: dict[str, str] = {
    # permitted
    "athens": "GR", "thessaloniki": "GR", "patras": "GR", "piraeus": "GR",
    "vienna": "AT", "wien": "AT", "graz": "AT", "linz": "AT", "salzburg": "AT",
    "limassol": "CY", "nicosia": "CY", "larnaca": "CY", "paphos": "CY",
    # everywhere else
    "london": "GB", "manchester": "GB", "edinburgh": "GB", "bristol": "GB",
    "cambridge": "GB", "belfast": "GB", "glasgow": "GB", "leeds": "GB",
    "berlin": "DE", "munich": "DE", "münchen": "DE", "hamburg": "DE",
    "frankfurt": "DE", "cologne": "DE", "köln": "DE", "stuttgart": "DE",
    "düsseldorf": "DE", "dusseldorf": "DE", "leipzig": "DE", "heidelberg": "DE",
    "karlsruhe": "DE", "nuremberg": "DE", "dresden": "DE", "hannover": "DE",
    "paris": "FR", "lyon": "FR", "bordeaux": "FR", "toulouse": "FR",
    "lille": "FR", "nantes": "FR", "marseille": "FR", "rennes": "FR",
    "amsterdam": "NL", "rotterdam": "NL", "utrecht": "NL", "eindhoven": "NL",
    "den haag": "NL", "the hague": "NL", "haarlem": "NL",
    "madrid": "ES", "barcelona": "ES", "valencia": "ES", "malaga": "ES",
    "seville": "ES", "bilbao": "ES", "zaragoza": "ES",
    "lisbon": "PT", "lisboa": "PT", "porto": "PT", "braga": "PT",
    "milan": "IT", "milano": "IT", "rome": "IT", "roma": "IT", "turin": "IT",
    "bologna": "IT", "naples": "IT",
    "brussels": "BE", "antwerp": "BE", "ghent": "BE", "leuven": "BE",
    "dublin": "IE", "cork": "IE", "galway": "IE",
    "warsaw": "PL", "krakow": "PL", "kraków": "PL", "wroclaw": "PL",
    "gdansk": "PL", "poznan": "PL", "katowice": "PL", "lodz": "PL",
    "prague": "CZ", "praha": "CZ", "brno": "CZ", "ostrava": "CZ",
    "bratislava": "SK", "kosice": "SK",
    "budapest": "HU", "debrecen": "HU",
    "bucharest": "RO", "cluj": "RO", "timisoara": "RO", "iasi": "RO",
    "sofia": "BG", "plovdiv": "BG", "varna": "BG",
    "zagreb": "HR", "ljubljana": "SI", "belgrade": "RS", "novi sad": "RS",
    "stockholm": "SE", "gothenburg": "SE", "malmo": "SE", "malmö": "SE",
    "oslo": "NO", "bergen": "NO", "trondheim": "NO",
    "copenhagen": "DK", "aarhus": "DK", "odense": "DK",
    "helsinki": "FI", "espoo": "FI", "tampere": "FI", "oulu": "FI",
    "tallinn": "EE", "tartu": "EE", "riga": "LV", "vilnius": "LT", "kaunas": "LT",
    "zurich": "CH", "zürich": "CH", "geneva": "CH", "basel": "CH",
    "bern": "CH", "lausanne": "CH", "lugano": "CH", "fehraltorf": "CH",
    "valletta": "MT", "luxembourg": "LU", "reykjavik": "IS",
    "kyiv": "UA", "kiev": "UA", "lviv": "UA", "odesa": "UA",
    "istanbul": "TR", "ankara": "TR", "izmir": "TR",
    "tel aviv": "IL", "herzliya": "IL", "haifa": "IL", "jerusalem": "IL",
    "bangalore": "IN", "bengaluru": "IN", "mumbai": "IN", "delhi": "IN",
    "gurugram": "IN", "gurgaon": "IN", "hyderabad": "IN", "pune": "IN",
    "chennai": "IN", "noida": "IN",
    "toronto": "CA", "vancouver": "CA", "montreal": "CA", "ottawa": "CA",
    "sydney": "AU", "melbourne": "AU", "brisbane": "AU", "perth": "AU",
    "auckland": "NZ", "wellington": "NZ",
    "singapore": "SG", "tokyo": "JP", "osaka": "JP", "seoul": "KR",
    "hong kong": "HK", "shanghai": "CN", "beijing": "CN", "shenzhen": "CN",
    "dubai": "AE", "abu dhabi": "AE", "riyadh": "SA", "doha": "QA",
    "sao paulo": "BR", "são paulo": "BR", "rio de janeiro": "BR",
    "buenos aires": "AR", "mexico city": "MX", "bogota": "CO", "bogotá": "CO",
    "cape town": "ZA", "johannesburg": "ZA", "nairobi": "KE", "lagos": "NG",
    "manila": "PH", "jakarta": "ID", "bangkok": "TH", "kuala lumpur": "MY",
}

ATHENS = re.compile(r"\b(athens|athina|attica|attiki|marousi|maroussi|kallithea|piraeus|glyfada)\b", re.I)
VIENNA = re.compile(r"\b(vienna|wien|viennese)\b", re.I)

US_STATES = (r"alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|"
             r"georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|"
             r"massachusetts|michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|"
             r"new hampshire|new jersey|new mexico|new york|north carolina|north dakota|ohio|"
             r"oklahoma|oregon|pennsylvania|rhode island|south carolina|south dakota|tennessee|"
             r"texas|utah|vermont|virginia|washington|west virginia|wisconsin|wyoming")
US_CITIES = (r"san francisco|new york city|nyc|los angeles|seattle|boston|chicago|austin|denver|"
             r"atlanta|miami|dallas|houston|phoenix|portland|san diego|san jose|philadelphia|"
             r"washington,? d\.?c\.?|palo alto|mountain view|sunnyvale|bellevue|brooklyn")

RE_US_LOC = re.compile(rf"\b(united states|usa|u\.s\.a?\.?|{US_STATES}|{US_CITIES})\b", re.I)
RE_US_ABBR = re.compile(r"\b(US|U\.S\.)\b")
RE_US_STATE_ABBR = re.compile(
    r",\s?(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|"
    r"NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b")
RE_US_HQ = re.compile(
    r"(headquarters?|hq)\s*[:\-]?\s*(remote[- ])?(us\b|u\.s\.|usa|united states)",
    re.I)
RE_US_AUTH = re.compile(
    r"(authorized to work in the (united states|us)|us work authorization|"
    r"eligible to work in the (united states|us)|w-?2\b|401\(?k\)?|green card|"
    r"must be (located|based) in the (us|united states)|us[- ]only|"
    r"visa sponsorship is not available in the us)", re.I)
RE_US_TZ = re.compile(r"\b(est|pst|cst|mst|edt|pdt|et\b|pt\b)\b.{0,40}(time ?zone|hours|overlap)", re.I)

# Strong enough to appear anywhere, including deep in the body.
RE_REMOTE_STRONG = re.compile(
    r"\b(fully[- ]remote|100% remote|remote[- ]first|work from (home|anywhere)|"
    r"remote (position|role|opportunity|job)|telecommute|"
    r"(fully |globally )?distributed team|remote within|remote in)\b", re.I)
# Bare "remote" is only trusted in the location / tag fields.
RE_REMOTE = re.compile(r"\bremote\b", re.I)
RE_HYBRID = re.compile(r"\b(hybrid|\d\s?(days?|x)\s?(per|a|/)?\s?week\s?(in|at|from)?\s?(the\s)?(office|hq)|"
                       r"(in|at)\s(the\s)?office\s\d\s?days|partially remote|flexible office)\b", re.I)
RE_ONSITE = re.compile(r"\b(on[- ]?site|in[- ]?office|office[- ]based|relocation (is )?(required|to)|"
                       r"must relocate|presence in the office)\b", re.I)
RE_EUROPE = re.compile(r"\b(anywhere in europe|across europe|europe[- ]wide|remote,? europe|"
                       r"europe \(remote\)|emea|european union|\beu\b|european time ?zones?|"
                       r"cet|cest|gmt\+[0-3]|within europe|europe only|european remote)\b", re.I)
RE_WORLDWIDE = re.compile(r"\b(worldwide|anywhere in the world|globally distributed|"
                          r"work from anywhere|any ?where|global remote|fully distributed)\b", re.I)
RE_ELIGIBLE_PHRASE = re.compile(
    r"(must (be (based|located|resident)|reside)|eligible to work|right to work|"
    r"legally (able|authorised|authorized) to work|employment is (only )?(possible|available)|"
    r"we can (only )?(hire|employ)|hiring in|entity in|payroll in|located in)", re.I)


def _countries_in(text: str) -> set[str]:
    """Country codes named in `text`, by country name OR by major city."""
    found = set()
    low = text.lower()
    for code, names in {**EU_COUNTRIES, **NON_EU_EXCL}.items():
        for n in names:
            if re.search(rf"\b{re.escape(n)}\b", low):
                found.add(code)
                break
    for city, code in CITY_COUNTRY.items():
        if re.search(rf"\b{re.escape(city)}\b", low):
            found.add(code)
    return found


def classify(job, cfg) -> None:
    """Populate work_arrangement, geo_tier, remote_eligibility, country, city,
    and (if ineligible) exclusion_reasons."""
    loc = job.raw_location or ""
    desc = job.description or ""
    head = desc[:3500]                       # eligibility statements live up top
    tagtext = " ".join(job.tags)
    blob = f"{job.title}\n{loc}\n{tagtext}\n{head}"
    perm = set(cfg["geography"]["permitted_countries"])

    # ---------------- work arrangement -----------------------------------
    is_remote = bool(RE_REMOTE.search(f"{job.title} {loc} {tagtext}")) or \
        bool(RE_REMOTE_STRONG.search(head)) or job.source in (
            "remotive", "remoteok", "himalayas", "jobicy", "workingnomads", "weworkremotely")
    is_hybrid = bool(RE_HYBRID.search(blob))
    is_onsite = bool(RE_ONSITE.search(blob)) and not is_remote

    if is_hybrid:
        job.work_arrangement = "hybrid"
    elif is_remote:
        job.work_arrangement = "remote"
    elif is_onsite:
        job.work_arrangement = "onsite"
    else:
        job.work_arrangement = "unknown"
        job.missing_info.append("Work arrangement not stated")

    # ---------------- scope ----------------------------------------------
    scope_src = f"{loc} {tagtext} {' '.join(job.remote_countries)}"
    scope = _countries_in(scope_src)
    worldwide = bool(RE_WORLDWIDE.search(scope_src)) or \
        (not scope and re.search(r"\bremote\b", scope_src, re.I) and
         not RE_EUROPE.search(scope_src))
    europe = bool(RE_EUROPE.search(scope_src))

    # eligibility sentences in the JD refine (or contradict) the location field
    elig_sentences = [s for s in re.split(r"(?<=[.!?•\n])", head)
                      if RE_ELIGIBLE_PHRASE.search(s)]
    elig_text = " ".join(elig_sentences)[:1200]
    scope_jd = _countries_in(elig_text)
    if elig_text and RE_EUROPE.search(elig_text):
        europe = True
    if scope_jd:
        scope |= scope_jd

    job.remote_countries = sorted(scope)

    # A posting that names a concrete place and never says 'remote' is an
    # office role by default. Without this, unstated-arrangement local jobs
    # were being credited with the much higher remote-country tier score.
    if job.work_arrangement == "unknown" and not worldwide and not europe:
        names_a_place = bool(scope) or bool(
            re.search(r"[A-Za-zÀ-ſ]{3,},\s*[A-Za-zÀ-ſ]{2,}", loc))
        if names_a_place and not re.search(r"\bremote\b", f"{loc} {tagtext}", re.I):
            job.work_arrangement = "onsite"
            job.missing_info.append(
                "Arrangement not stated; a named office location is assumed to be "
                "on-site - confirm whether remote working is possible")

    # ---------------- USA hard exclusion ---------------------------------
    us_signals = []
    if RE_US_LOC.search(loc) or RE_US_STATE_ABBR.search(loc) or RE_US_ABBR.search(loc):
        us_signals.append(f"location '{loc[:60]}'")
    if RE_US_AUTH.search(head):
        us_signals.append("US work-authorisation / US benefits language")
    if RE_US_HQ.search(head):
        us_signals.append("posting states a US headquarters/base")
    if RE_US_TZ.search(head) and not europe:
        us_signals.append("US timezone overlap requirement")
    if "US" in scope and not (europe or perm & scope):
        us_signals.append("remote scope limited to the United States")

    if us_signals and cfg["exclusions"]["usa"]["enabled"]:
        # Europe-wide roles that merely mention a US HQ are not US-based.
        us_only = not (europe or (perm & scope) or
                       (worldwide and not RE_US_AUTH.search(head)
                        and not RE_US_HQ.search(head)))
        if us_only:
            job.eligible = False
            job.exclusion_reasons.append(
                f"{cfg['exclusions']['usa']['reason']} ({'; '.join(us_signals[:2])})")
            job.geo_tier = "excluded_us"
            job.remote_eligibility = "United States - excluded"
            return

    # ---------------- city for on-site / hybrid --------------------------
    in_athens = bool(ATHENS.search(f"{loc} {head[:1200]}"))
    in_vienna = bool(VIENNA.search(f"{loc} {head[:1200]}"))
    job.city = "Athens" if in_athens else ("Vienna" if in_vienna else "")

    if job.work_arrangement in ("onsite", "hybrid"):
        if in_athens:
            job.geo_tier, job.country = "onsite_athens", "GR"
            job.remote_eligibility = f"{job.work_arrangement.title()} - Athens, Greece"
        elif in_vienna:
            job.geo_tier, job.country = "onsite_vienna", "AT"
            job.remote_eligibility = f"{job.work_arrangement.title()} - Vienna, Austria"
        else:
            if cfg["exclusions"]["onsite_outside_permitted"]["enabled"]:
                job.eligible = False
                where = loc[:70] or "unspecified location"
                job.exclusion_reasons.append(
                    f"{cfg['exclusions']['onsite_outside_permitted']['reason']} ({where})")
                job.geo_tier = "excluded_onsite"
                job.remote_eligibility = f"{job.work_arrangement} - {where}"
                return
        _set_country(job, scope)
        return

    # ---------------- remote scope resolution ----------------------------
    non_perm_eu = {c for c in scope if c in EU_COUNTRIES and c not in perm}
    non_eu = {c for c in scope if c in NON_EU_EXCL}

    if europe or (worldwide and not non_eu - {"US"}):
        job.geo_tier = "remote_europe"
        job.country = "EU"
        if perm & scope:
            job.remote_eligibility = (
                "Remote - Europe; explicitly includes "
                + "/".join(sorted(perm & scope)))
        else:
            job.remote_eligibility = (
                "Remote - Europe/worldwide (specific hiring countries NOT stated)")
            job.missing_info.append(
                "Europe-wide remote, but the countries the employer can actually "
                "contract/payroll from are not stated - verify GR/CY/AT")
    elif perm & scope:
        hit = perm & scope
        if "GR" in hit:
            job.geo_tier, job.country = "remote_greece", "GR"
        elif "AT" in hit:
            job.geo_tier, job.country = "remote_austria", "AT"
        else:
            job.geo_tier, job.country = "remote_cyprus", "CY"
        job.remote_eligibility = "Remote - " + ", ".join(sorted(hit))
    elif non_perm_eu or non_eu:
        if cfg["exclusions"]["country_restricted"]["enabled"]:
            job.eligible = False
            lst = ", ".join(sorted(non_perm_eu | non_eu))
            job.exclusion_reasons.append(
                f"{cfg['exclusions']['country_restricted']['reason']} ({lst})")
            job.geo_tier = "excluded_country"
            job.remote_eligibility = f"Remote - restricted to {lst}"
            return
    else:
        # Remote with no stated scope at all.
        job.geo_tier = "remote_europe"
        job.country = "?"
        job.remote_eligibility = "Remote - scope not stated"
        job.missing_info.append("Remote scope not stated anywhere in the posting")
        job.tags.append("scope_unstated")

    _set_country(job, scope)


def _set_country(job, scope: set[str]) -> None:
    if not job.country:
        for c in ("GR", "CY", "AT"):
            if c in scope:
                job.country = c
                return
        job.country = next(iter(sorted(scope)), "?")


def tier_score(job, cfg) -> tuple[float, int, list[str], list[str]]:
    """Return (0-100 score, rank, positives, negatives)."""
    tiers = {t["id"]: t for t in cfg["geography"]["tiers"]}
    t = tiers.get(job.geo_tier)
    pos: list[str] = []
    neg: list[str] = []
    if not t:
        return 0.0, 99, pos, ["Geography could not be classified"]
    score = float(t["score"])
    if job.geo_tier == "remote_europe":
        perm = set(cfg["geography"]["permitted_countries"])
        if perm & set(job.remote_countries):
            pos.append(f"Remote scope explicitly covers {'/'.join(sorted(perm & set(job.remote_countries)))}")
        else:
            score *= cfg["geography"]["unverified_scope_multiplier"]
            neg.append("Europe-wide remote, but GR/CY/AT hiring not confirmed")
    if job.work_arrangement == "unknown":
        score *= 0.9
        neg.append("Work arrangement not explicitly stated")
    pos.append(f"Geography: {t['label']} (priority #{t['rank']})")
    return round(score, 1), t["rank"], pos, neg
