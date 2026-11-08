"""Optional LLM adjudication layer.

The rules engine is the primary scorer: it is deterministic, free, fully
explainable and reproducible. This layer is an OPTIONAL second pass that uses
Claude to review the shortlist for the judgement calls rules handle badly:

  * is the remote scope genuinely open to Greece / Cyprus / Austria?
  * is this really a data-platform/BI role, or a data-science role in disguise?
  * is the seniority real, or title inflation?

Enabled with --llm and an ANTHROPIC_API_KEY in the environment. The prompt
requires the model to answer "unknown" when the posting does not say, so this
layer never invents facts.
"""
from __future__ import annotations

import json
import os
import re

MODEL = os.environ.get("JOBRADAR_LLM_MODEL", "claude-opus-5")

SYSTEM = """You audit job postings for a specific candidate. You are given the
candidate profile and one job description. Answer ONLY from the job description.
If the posting does not state something, answer "unknown" - never guess, never
infer from the company name.

Return strict JSON with these keys:
  geo_ok            : true/false/"unknown"  - can someone resident in Greece,
                      Cyprus or Austria realistically be employed in this role?
  geo_evidence      : short quote from the posting, or ""
  role_is_data_platform : true/false  - is the PRIMARY remit data platform /
                      BI / data warehousing / analytics engineering / data
                      engineering leadership (as opposed to data science, ML
                      research, or enterprise AI transformation)?
  role_evidence     : short quote, or ""
  seniority_real    : "director"|"head"|"manager"|"lead"|"ic"|"unknown"
  handson_vs_mgmt   : 0-100, where 100 = purely strategic/managerial
  red_flags         : array of short strings
  verdict           : "strong"|"possible"|"weak"|"reject"
  one_line          : one sentence on fit
"""


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def adjudicate(jobs: list, cfg, limit: int = 25) -> int:
    """Review the top `limit` eligible jobs in place. Returns count reviewed."""
    if not available():
        return 0
    try:
        import anthropic
    except ImportError:
        return 0
    client = anthropic.Anthropic()
    cv = (cfg.get("_cv_text") or "")[:3000]
    reviewed = 0
    for job in jobs[:limit]:
        prompt = (
            f"CANDIDATE PROFILE\n{cv}\n\n"
            f"Permitted locations: fully remote in Europe, or remote/on-site in "
            f"Greece, Cyprus or Austria only. US roles are disqualifying.\n\n"
            f"JOB POSTING\nTitle: {job.title}\nCompany: {job.company}\n"
            f"Location field: {job.raw_location}\n\n{job.description[:12000]}"
        )
        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=900, system=SYSTEM,
                messages=[{"role": "user", "content": prompt}])
            text = "".join(b.text for b in resp.content if b.type == "text")
            data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
        except Exception as exc:                      # noqa: BLE001
            job.missing_info.append(f"LLM review unavailable ({type(exc).__name__})")
            continue
        _apply(job, data, cfg)
        reviewed += 1
    return reviewed


def _apply(job, d: dict, cfg) -> None:
    job.tags.append("llm_reviewed")
    if d.get("geo_ok") is False:
        job.eligible = False
        job.score = 0.0
        job.exclusion_reasons.append(
            f"LLM review: not employable from GR/CY/AT. {d.get('geo_evidence', '')[:120]}")
        return
    if d.get("geo_ok") == "unknown":
        job.missing_info.append("LLM review: remote scope still unverified")
    if d.get("role_is_data_platform") is False:
        job.score = round(job.score * 0.75, 1)
        job.negatives.append(
            f"LLM review: primary remit is not data platform/BI. "
            f"{d.get('role_evidence', '')[:120]}")
    hv = d.get("handson_vs_mgmt")
    if isinstance(hv, (int, float)):
        job.dimension_scores["llm_strategic_pct"] = float(hv)
        if hv < 35:
            job.negatives.append(f"LLM review: reads as {100 - hv:.0f}% hands-on delivery")
    for flag in (d.get("red_flags") or [])[:4]:
        job.negatives.append(f"LLM flag: {flag}")
    if d.get("one_line"):
        job.job_fit = f"{job.job_fit} | LLM: {d['one_line']}"
    verdict = d.get("verdict")
    if verdict == "reject":
        job.score = round(job.score * 0.6, 1)
        job.negatives.append("LLM verdict: reject")
    elif verdict == "strong":
        job.positives.append("LLM verdict: strong match")
