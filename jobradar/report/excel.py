"""Excel evaluation artifact.

Sheets
  1. Shortlist         - the opportunities worth acting on, with the reason
  2. All Opportunities - every eligible job, highest score first
  3. Excluded          - everything filtered out, WITH the reason (calibration)
  4. Score Breakdown   - per-dimension scores and penalties (explainability)
  5. Run Summary       - funnel counts and per-source quality
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

HEAD_FILL = PatternFill("solid", fgColor="1F3864")
HEAD_FONT = Font(color="FFFFFF", bold=True, size=10)
TITLE_FONT = Font(bold=True, size=14, color="1F3864")
WRAP = Alignment(wrap_text=True, vertical="top")
TOP = Alignment(vertical="top")
THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

BANDS = [(80, "C6EFCE"), (70, "E2F0D9"), (60, "FFF2CC"), (50, "FCE4D6"), (0, "F2F2F2")]

COLUMNS = [
    ("Overall Score", "score", 11),
    ("Job Title", "title", 38),
    ("Company", "company", 22),
    ("Industry", "_industry", 18),
    ("Location", "raw_location", 26),
    ("Work Arrangement", "work_arrangement", 15),
    ("Remote Eligibility", "remote_eligibility", 40),
    ("Legal Entity", "_legal_entity", 24),
    ("Job Category", "job_category", 34),
    ("Seniority", "_seniority", 12),
    ("Estimated Salary", "_salary", 24),
    ("Salary Confidence", "salary_confidence", 12),
    ("Estimated Net", "_net", 30),
    ("Job Fit", "job_fit", 52),
    ("Positive Factors", "_positives", 58),
    ("Negative Factors", "_negatives", 58),
    ("Missing Information", "_missing", 48),
    ("Job Description", "url", 34),
    ("Date Published", "date_published", 13),
    ("Date Discovered", "date_discovered", 13),
    ("Application Status", "application_status", 14),
]


def _val(job, key):
    if key == "_industry":
        return (job.industry or "other").replace("_", " ").title()
    if key == "_seniority":
        return (job.seniority or "").replace("_", " ").title()
    if key == "_legal_entity":
        if job.legal_entity:
            return job.legal_entity
        hints = []
        if job.has_gr_entity:
            hints.append("GR entity: yes")
        if job.has_cy_entity:
            hints.append("CY entity: yes")
        return "; ".join(hints) or "Unknown"
    if key == "_salary":
        if not job.salary_est_min:
            return "Unknown"
        tag = "published" if job.salary_confidence == "High" else "estimated"
        return f"EUR {job.salary_est_min:,.0f} - {job.salary_est_max:,.0f} ({tag})"
    if key == "_net":
        if not job.net_monthly_gr:
            return ""
        return (f"GR EUR{job.net_monthly_gr:,.0f}/mo; "
                f"CY EUR{job.net_monthly_cy:,.0f}/mo (indicative)")
    if key == "_positives":
        return "\n".join(f"+ {p}" for p in job.positives[:9])
    if key == "_negatives":
        src = job.negatives if job.eligible else (job.exclusion_reasons + job.negatives)
        return "\n".join(f"- {n}" for n in src[:9])
    if key == "_missing":
        return "\n".join(f"? {m}" for m in job.missing_info[:7])
    return getattr(job, key, "")


def _sheet(wb, name, jobs, note=""):
    ws = wb.create_sheet(name)
    row = 1
    if note:
        ws.cell(row=1, column=1, value=note).font = Font(italic=True, size=9, color="595959")
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(COLUMNS))
        row = 2

    for ci, (head, _, width) in enumerate(COLUMNS, start=1):
        c = ws.cell(row=row, column=ci, value=head)
        c.fill, c.font, c.border = HEAD_FILL, HEAD_FONT, BORDER
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        ws.column_dimensions[get_column_letter(ci)].width = width
    header_row = row

    for job in jobs:
        row += 1
        for ci, (_, key, _w) in enumerate(COLUMNS, start=1):
            cell = ws.cell(row=row, column=ci, value=_val(job, key))
            cell.alignment = WRAP if key.startswith("_") or key in (
                "job_fit", "remote_eligibility", "title", "job_category") else TOP
            cell.border = BORDER
            if key == "score":
                cell.font = Font(bold=True, size=12)
                cell.alignment = Alignment(horizontal="center", vertical="center")
                for lo, colour in BANDS:
                    if (job.score or 0) >= lo:
                        cell.fill = PatternFill("solid", fgColor=colour)
                        break
            if key == "url" and job.url:
                cell.value = "Open posting"
                cell.hyperlink = job.url
                cell.font = Font(color="0563C1", underline="single")
        ws.row_dimensions[row].height = 118

    if jobs:
        ref = f"A{header_row}:{get_column_letter(len(COLUMNS))}{row}"
        t = Table(displayName=f"tbl_{name.replace(' ', '')[:20]}", ref=ref)
        t.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=False)
        try:
            ws.add_table(t)
        except ValueError:
            pass
    ws.freeze_panes = ws.cell(row=header_row + 1, column=3)
    ws.auto_filter.ref = ws.dimensions
    return ws


def _breakdown_sheet(wb, jobs, cfg):
    ws = wb.create_sheet("Score Breakdown")
    w = cfg["weights"]
    heads = (["Score", "Job Title", "Company"]
             + [f"{k} (w{w[k]})" for k in w]
             + ["Penalties", "Geo Tier", "Category Tier", "80k Met?"])
    for ci, h in enumerate(heads, start=1):
        c = ws.cell(row=1, column=ci, value=h)
        c.fill, c.font, c.border = HEAD_FILL, HEAD_FONT, BORDER
        c.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
    widths = [9, 36, 20] + [12] * len(w) + [46, 17, 12, 10]
    for ci, wd in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(ci)].width = wd

    for r, job in enumerate(jobs, start=2):
        ws.cell(row=r, column=1, value=job.score).font = Font(bold=True)
        ws.cell(row=r, column=2, value=job.title)
        ws.cell(row=r, column=3, value=job.company)
        for i, k in enumerate(w):
            ws.cell(row=r, column=4 + i, value=round(job.dimension_scores.get(k, 0), 1))
        ws.cell(row=r, column=4 + len(w),
                value="; ".join(f"-{v:.0f} {k}" for k, v in job.penalties)).alignment = WRAP
        ws.cell(row=r, column=5 + len(w), value=job.geo_tier)
        ws.cell(row=r, column=6 + len(w), value=job.category_tier)
        ws.cell(row=r, column=7 + len(w), value=job.meets_80k)
    ws.freeze_panes = "D2"
    return ws


def _summary_sheet(wb, stats, cfg):
    ws = wb.create_sheet("Run Summary", 0)
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 62
    ws["A1"] = "Job Discovery POC - Run Summary"
    ws["A1"].font = TITLE_FONT
    r = 3

    def section(title):
        nonlocal r
        c = ws.cell(row=r, column=1, value=title)
        c.font = Font(bold=True, size=11, color="FFFFFF")
        c.fill = HEAD_FILL
        ws.cell(row=r, column=2).fill = HEAD_FILL
        ws.cell(row=r, column=3).fill = HEAD_FILL
        r += 1

    def line(k, v, note=""):
        nonlocal r
        ws.cell(row=r, column=1, value=k)
        ws.cell(row=r, column=2, value=v).font = Font(bold=True)
        ws.cell(row=r, column=3, value=note).alignment = WRAP
        r += 1

    section("Discovery funnel")
    f = stats["funnel"]
    line("Jobs fetched (after title prefilter)", f["fetched"])
    line("Unique jobs after deduplication", f["unique"],
         f"{f['duplicates']} duplicate postings collapsed")
    line("Excluded - geography", f["excl_geo"], "US / wrong country / on-site outside Athens-Vienna")
    line("Excluded - professional mismatch", f["excl_prof"], "CDO / data science / AI transformation / not leadership")
    line("Excluded - compensation", f["excl_comp"], "published salary below the floor")
    line("Eligible jobs", f["eligible"])
    line("High-quality matches (score >= shortlist floor)", f["shortlist"])
    r += 1

    section("Configuration in force")
    line("Shortlist / notification floor", cfg["output"]["shortlist_min_score"])
    line("Salary floor (Greece & Austria)", f"EUR {cfg['compensation']['floor_gr_at_eur']:,}")
    line("Current net reference", f"EUR {cfg['compensation']['current_net_monthly_eur']:,}/month")
    line("Max posting age", f"{cfg['sources']['max_age_days']} days")
    line("Weights", ", ".join(f"{k} {v}" for k, v in cfg["weights"].items()))
    r += 1

    section("Source quality")
    ws.cell(row=r, column=1, value="Source").font = Font(bold=True)
    ws.cell(row=r, column=2, value="Fetched").font = Font(bold=True)
    ws.cell(row=r, column=3, value="Eligible after scoring / errors").font = Font(bold=True)
    r += 1
    for s in stats["sources"]:
        ws.cell(row=r, column=1, value=s["source"])
        ws.cell(row=r, column=2, value=s["fetched"])
        note = f"{s['eligible']} eligible"
        if s.get("errors"):
            note += f"  |  errors: {s['errors'][:120]}"
        ws.cell(row=r, column=3, value=note).alignment = WRAP
        r += 1
    r += 1

    section("Caveats")
    for note in stats.get("caveats", []):
        ws.cell(row=r, column=1, value=note).alignment = WRAP
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        ws.row_dimensions[r].height = 30
        r += 1
    return ws


def build(path, eligible, excluded, shortlist, stats, cfg) -> str:
    wb = Workbook()
    wb.remove(wb.active)
    _sheet(wb, "Shortlist", shortlist,
           "Best opportunities this run. Sorted by overall score. "
           "Net figures are indicative only and are not tax advice.")
    _sheet(wb, "All Opportunities", eligible,
           "Every eligible opportunity, highest score first.")
    _sheet(wb, "Excluded", excluded,
           "Filtered out by a hard rule. Kept so the exclusion logic can be "
           "calibrated - check this sheet for false negatives.")
    _breakdown_sheet(wb, eligible, cfg)
    _summary_sheet(wb, stats, cfg)
    wb.properties.title = "Job Discovery POC"
    wb.properties.created = datetime.now()
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return str(out)
