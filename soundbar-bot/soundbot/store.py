"""SQLite persistence: runs, per-shop run status, offers, alerts."""
from __future__ import annotations
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Iterator, Optional

from .models import Offer, Alert
from .paths import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  dry_run INTEGER NOT NULL DEFAULT 0,
  notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS shop_runs (
  run_id INTEGER NOT NULL,
  shop TEXT NOT NULL,
  ok INTEGER NOT NULL,
  n_items INTEGER NOT NULL DEFAULT 0,
  n_offers INTEGER NOT NULL DEFAULT 0,
  tier TEXT DEFAULT '',
  error TEXT DEFAULT '',
  seconds REAL DEFAULT 0,
  PRIMARY KEY (run_id, shop)
);
CREATE TABLE IF NOT EXISTS offers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  shop TEXT NOT NULL,
  model_key TEXT NOT NULL,
  title TEXT NOT NULL,
  price REAL,
  list_price REAL,
  in_stock INTEGER,
  url TEXT NOT NULL,
  shop_sku TEXT DEFAULT '',
  seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_offers_model ON offers(model_key, shop, seen_at);
CREATE INDEX IF NOT EXISTS ix_offers_run ON offers(run_id);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rule TEXT NOT NULL,
  shop TEXT NOT NULL,
  model_key TEXT NOT NULL,
  price REAL,
  title TEXT DEFAULT '',
  message TEXT NOT NULL,
  url TEXT DEFAULT '',
  dedupe_key TEXT NOT NULL,
  sent_at TEXT NOT NULL,
  channels TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_alerts_dedupe ON alerts(dedupe_key, sent_at);
CREATE TABLE IF NOT EXISTS shop_state (
  shop TEXT PRIMARY KEY,
  last_ok_at TEXT,
  blocked_until TEXT,
  block_streak INTEGER NOT NULL DEFAULT 0,
  last_error TEXT DEFAULT ''
);
"""


class Store:
    def __init__(self, path=DB_PATH):
        self.path = str(path)
        self._lock = threading.RLock()
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            c = sqlite3.connect(self.path, timeout=30)
            c.row_factory = sqlite3.Row
            try:
                yield c
                c.commit()
            finally:
                c.close()

    # ---- runs -------------------------------------------------------------
    def start_run(self, dry_run: bool = False) -> int:
        with self.conn() as c:
            cur = c.execute("INSERT INTO runs(started_at, dry_run) VALUES (?, ?)",
                            (datetime.now().isoformat(timespec="seconds"), int(dry_run)))
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, notes: str = "") -> None:
        with self.conn() as c:
            c.execute("UPDATE runs SET finished_at=?, notes=? WHERE id=?",
                      (datetime.now().isoformat(timespec="seconds"), notes, run_id))

    def record_shop_run(self, run_id: int, shop: str, ok: bool, n_items: int, n_offers: int,
                        tier: str = "", error: str = "", seconds: float = 0.0) -> None:
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO shop_runs(run_id, shop, ok, n_items, n_offers, tier, error, seconds) "
                      "VALUES (?,?,?,?,?,?,?,?)",
                      (run_id, shop, int(ok), n_items, n_offers, tier, error[:500], seconds))

    def last_runs(self, limit: int = 20) -> list[sqlite3.Row]:
        with self.conn() as c:
            return c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def shop_runs(self, run_id: int) -> list[sqlite3.Row]:
        with self.conn() as c:
            return c.execute("SELECT * FROM shop_runs WHERE run_id=? ORDER BY shop", (run_id,)).fetchall()

    def last_ok_run_for_shop(self, shop: str, before_run: Optional[int] = None) -> Optional[int]:
        q = "SELECT run_id FROM shop_runs WHERE shop=? AND ok=1"
        args: list = [shop]
        if before_run is not None:
            q += " AND run_id<?"
            args.append(before_run)
        q += " ORDER BY run_id DESC LIMIT 1"
        with self.conn() as c:
            row = c.execute(q, args).fetchone()
            return int(row[0]) if row else None

    # ---- offers -----------------------------------------------------------
    def add_offers(self, run_id: int, offers: list[Offer]) -> None:
        with self.conn() as c:
            c.executemany(
                "INSERT INTO offers(run_id, shop, model_key, title, price, list_price, in_stock, url, shop_sku, seen_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(run_id, o.shop, o.model_key, o.title, o.price, o.list_price,
                  None if o.in_stock is None else int(o.in_stock), o.url, o.shop_sku, o.seen_at) for o in offers])

    def offers_for_run(self, run_id: int, shop: Optional[str] = None) -> list[sqlite3.Row]:
        q = "SELECT * FROM offers WHERE run_id=?"
        args: list = [run_id]
        if shop:
            q += " AND shop=?"
            args.append(shop)
        with self.conn() as c:
            return c.execute(q + " ORDER BY model_key, shop, price", args).fetchall()

    def current_offers(self) -> list[sqlite3.Row]:
        """Latest successful snapshot per shop (a failed shop keeps its previous snapshot)."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT o.* FROM offers o JOIN ("
                "  SELECT shop, MAX(run_id) AS run_id FROM shop_runs WHERE ok=1 GROUP BY shop"
                ") l ON o.shop=l.shop AND o.run_id=l.run_id "
                "ORDER BY o.model_key, o.price").fetchall()
            return rows

    def history(self, model_key: str, days: int = 120) -> list[sqlite3.Row]:
        since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        with self.conn() as c:
            return c.execute(
                "SELECT shop, price, list_price, in_stock, seen_at, url FROM offers "
                "WHERE model_key=? AND seen_at>=? ORDER BY seen_at", (model_key, since)).fetchall()

    def lowest_ever(self, model_key: str) -> Optional[sqlite3.Row]:
        with self.conn() as c:
            return c.execute(
                "SELECT shop, price, seen_at, url FROM offers WHERE model_key=? AND price IS NOT NULL "
                "ORDER BY price ASC LIMIT 1", (model_key,)).fetchone()

    # ---- alerts -----------------------------------------------------------
    def alert_sent_recently(self, dedupe_key: str, days: int) -> bool:
        since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        with self.conn() as c:
            row = c.execute("SELECT 1 FROM alerts WHERE dedupe_key=? AND sent_at>=? LIMIT 1",
                            (dedupe_key, since)).fetchone()
            return row is not None

    def last_alert_price(self, rule: str, shop: str, model_key: str) -> Optional[float]:
        with self.conn() as c:
            row = c.execute("SELECT price FROM alerts WHERE rule=? AND shop=? AND model_key=? "
                            "ORDER BY id DESC LIMIT 1", (rule, shop, model_key)).fetchone()
            return float(row[0]) if row and row[0] is not None else None

    def recent_price_changes(self, days: int = 21) -> dict[tuple[str, str], dict]:
        """The last price move per (shop, model): {'old', 'new', 'at'}.

        Walks each pair's history and keeps the most recent point where the price differed from the
        one before it, so a model whose price moved a week ago and has held since still shows the
        move. A pair that has only ever been seen at one price is not in the result.
        """
        since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        with self.conn() as c:
            rows = c.execute(
                "SELECT shop, model_key, price, seen_at FROM offers "
                "WHERE price IS NOT NULL AND seen_at >= ? ORDER BY seen_at", (since,)).fetchall()
        last: dict[tuple[str, str], float] = {}
        out: dict[tuple[str, str], dict] = {}
        for r in rows:
            key = (r["shop"], r["model_key"])
            price = float(r["price"])
            was = last.get(key)
            if was is not None and abs(was - price) >= 0.01:
                out[key] = {"old": was, "new": price, "at": r["seen_at"]}
            last[key] = price
        # Only report a move the current price still agrees with: anything else is already history.
        return {k: v for k, v in out.items() if abs(v["new"] - last[k]) < 0.01}

    # ---- per-shop state ---------------------------------------------------
    def shop_state(self, shop: str) -> Optional[sqlite3.Row]:
        with self.conn() as c:
            return c.execute("SELECT * FROM shop_state WHERE shop=?", (shop,)).fetchone()

    def shop_states(self) -> dict[str, sqlite3.Row]:
        with self.conn() as c:
            return {r["shop"]: r for r in c.execute("SELECT * FROM shop_state").fetchall()}

    def record_shop_ok(self, shop: str) -> None:
        """A successful read clears any block and resets the streak that lengthens the next one."""
        with self.conn() as c:
            c.execute("INSERT INTO shop_state(shop, last_ok_at, blocked_until, block_streak, last_error) "
                      "VALUES (?,?,NULL,0,'') ON CONFLICT(shop) DO UPDATE SET "
                      "last_ok_at=excluded.last_ok_at, blocked_until=NULL, block_streak=0, last_error=''",
                      (shop, datetime.now().isoformat(timespec="seconds")))

    def record_shop_blocked(self, shop: str, hours: float, error: str = "") -> datetime:
        """Mark the shop as not to be asked again until `hours` from now; returns that moment."""
        until = datetime.now() + timedelta(hours=hours)
        with self.conn() as c:
            c.execute("INSERT INTO shop_state(shop, blocked_until, block_streak, last_error) "
                      "VALUES (?,?,1,?) ON CONFLICT(shop) DO UPDATE SET "
                      "blocked_until=excluded.blocked_until, block_streak=shop_state.block_streak+1, "
                      "last_error=excluded.last_error",
                      (shop, until.isoformat(timespec="seconds"), error[:500]))
        return until

    def add_alert(self, a: Alert, channels: str) -> None:
        with self.conn() as c:
            c.execute("INSERT INTO alerts(rule, shop, model_key, price, title, message, url, dedupe_key, sent_at, channels) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (a.rule, a.shop, a.model_key, a.price, a.title, a.message, a.url, a.dedupe_key,
                       datetime.now().isoformat(timespec="seconds"), channels))

    def alerts(self, limit: int = 200, model_key: Optional[str] = None) -> list[sqlite3.Row]:
        q = "SELECT * FROM alerts"
        args: list = []
        if model_key:
            q += " WHERE model_key=?"
            args.append(model_key)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self.conn() as c:
            return c.execute(q, args).fetchall()
