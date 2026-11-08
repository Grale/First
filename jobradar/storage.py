"""SQLite persistence: jobs, run statistics, notification ledger, JD snapshots."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    fingerprint      TEXT PRIMARY KEY,
    source           TEXT,
    source_id        TEXT,
    url              TEXT,
    canonical_url    TEXT,
    title            TEXT,
    company          TEXT,
    country          TEXT,
    content_hash     TEXT,
    score            REAL,
    eligible         INTEGER,
    payload          TEXT,
    description      TEXT,
    first_seen       TEXT,
    last_seen        TEXT,
    date_published   TEXT,
    application_status TEXT DEFAULT 'New'
);
CREATE INDEX IF NOT EXISTS idx_jobs_score   ON jobs(score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);

CREATE TABLE IF NOT EXISTS notifications (
    fingerprint TEXT, kind TEXT, sent_at TEXT, detail TEXT,
    PRIMARY KEY (fingerprint, kind)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, stats TEXT
);

CREATE TABLE IF NOT EXISTS source_stats (
    run_id TEXT, source TEXT, fetched INTEGER, kept INTEGER,
    eligible INTEGER, errors TEXT
);
"""


class Store:
    def __init__(self, path: str | Path = "data/jobs.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # -- jobs -------------------------------------------------------------
    def get(self, fingerprint: str) -> sqlite3.Row | None:
        cur = self.conn.execute("SELECT * FROM jobs WHERE fingerprint = ?", (fingerprint,))
        return cur.fetchone()

    def upsert(self, job: Job) -> str:
        """Return 'new' | 'changed' | 'seen'."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        fp, ch = job.fingerprint(), job.content_hash()
        existing = self.get(fp)
        payload = json.dumps(job.to_dict(), ensure_ascii=False, default=str)
        if existing is None:
            self.conn.execute(
                """INSERT INTO jobs (fingerprint, source, source_id, url, canonical_url,
                   title, company, country, content_hash, score, eligible, payload,
                   description, first_seen, last_seen, date_published, application_status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (fp, job.source, job.source_id, job.url, job.canonical_url, job.title,
                 job.company, job.country, ch, job.score, int(job.eligible), payload,
                 job.description[:60000], now, now, job.date_published, job.application_status))
            self.conn.commit()
            return "new"
        status = "changed" if existing["content_hash"] != ch else "seen"
        self.conn.execute(
            """UPDATE jobs SET last_seen=?, content_hash=?, score=?, eligible=?,
               payload=?, description=? WHERE fingerprint=?""",
            (now, ch, job.score, int(job.eligible), payload,
             job.description[:60000], fp))
        self.conn.commit()
        return status

    def all_jobs(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT payload, first_seen FROM jobs ORDER BY score DESC").fetchall()
        out = []
        for r in rows:
            d = json.loads(r["payload"])
            d["_first_seen"] = r["first_seen"]
            out.append(d)
        return out

    # -- notifications ----------------------------------------------------
    def already_notified(self, fingerprint: str, kind: str = "new") -> bool:
        return self.conn.execute(
            "SELECT 1 FROM notifications WHERE fingerprint=? AND kind=?",
            (fingerprint, kind)).fetchone() is not None

    def mark_notified(self, fingerprint: str, kind: str = "new", detail: str = "") -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO notifications VALUES (?,?,?,?)",
            (fingerprint, kind, datetime.now(timezone.utc).isoformat(timespec="seconds"), detail))
        self.conn.commit()

    # -- runs -------------------------------------------------------------
    def start_run(self, run_id: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO runs (run_id, started_at) VALUES (?,?)",
                          (run_id, datetime.now(timezone.utc).isoformat(timespec="seconds")))
        self.conn.commit()

    def finish_run(self, run_id: str, stats: dict) -> None:
        self.conn.execute("UPDATE runs SET finished_at=?, stats=? WHERE run_id=?",
                          (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           json.dumps(stats, default=str), run_id))
        self.conn.commit()

    def record_source(self, run_id: str, source: str, fetched: int, kept: int,
                      eligible: int, errors: str = "") -> None:
        self.conn.execute("INSERT INTO source_stats VALUES (?,?,?,?,?,?)",
                          (run_id, source, fetched, kept, eligible, errors))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
