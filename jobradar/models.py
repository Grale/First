"""Core data model for a discovered job."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any


@dataclass
class Job:
    # --- identity / provenance -------------------------------------------
    source: str
    source_id: str
    url: str
    canonical_url: str = ""
    title: str = ""
    company: str = ""
    raw_location: str = ""
    description: str = ""          # plain text, full JD where available
    description_html: str = ""
    date_published: str = ""       # ISO date
    date_discovered: str = ""
    tags: list[str] = field(default_factory=list)
    published_salary_raw: str = ""

    # --- enrichment -------------------------------------------------------
    work_arrangement: str = "unknown"      # remote | hybrid | onsite | unknown
    geo_tier: str = ""                     # remote_europe | remote_greece | ...
    geo_tier_rank: int = 99
    remote_eligibility: str = ""           # human readable
    remote_countries: list[str] = field(default_factory=list)
    country: str = ""
    city: str = ""
    legal_entity: str = ""
    has_gr_entity: bool | None = None
    has_cy_entity: bool | None = None

    job_category: str = ""                 # tier1/tier2/tier3 label
    category_tier: str = ""
    seniority: str = ""
    industry: str = "other"
    company_size_bucket: str = ""
    company_employees_est: int | None = None

    salary_published_min: float | None = None
    salary_published_max: float | None = None
    salary_currency: str = ""
    salary_est_min: float | None = None
    salary_est_max: float | None = None
    salary_confidence: str = "low"
    salary_basis: str = ""
    total_comp_est: str = ""
    net_monthly_gr: float | None = None
    net_monthly_cy: float | None = None
    meets_80k: str = "unknown"

    # --- scoring ----------------------------------------------------------
    eligible: bool = True
    exclusion_reasons: list[str] = field(default_factory=list)
    dimension_scores: dict[str, float] = field(default_factory=dict)
    penalties: list[tuple[str, float]] = field(default_factory=list)
    score: float = 0.0
    positives: list[str] = field(default_factory=list)
    negatives: list[str] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)
    job_fit: str = ""
    assessment_complete: bool = True
    application_status: str = "New"

    def fingerprint(self) -> str:
        """Stable identity for dedup: canonical url first, else company+title+loc."""
        base = (self.canonical_url or self.url or "").strip().lower()
        if base:
            return hashlib.sha256(base.encode()).hexdigest()[:20]
        key = f"{self.company.lower()}|{self.title.lower()}|{self.country.lower()}"
        return hashlib.sha256(key.encode()).hexdigest()[:20]

    def content_hash(self) -> str:
        """Detects material changes (salary / location / remote eligibility)."""
        key = "|".join([
            str(self.salary_published_min), str(self.salary_published_max),
            self.raw_location, self.work_arrangement, self.remote_eligibility,
        ])
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
