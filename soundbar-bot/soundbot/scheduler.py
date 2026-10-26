"""Background checker used by `serve`: runs a check on an interval and on demand."""
from __future__ import annotations
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

from . import config as config_mod
from .engine import run_check, RunResult
from .store import Store

log = logging.getLogger("soundbot.scheduler")


class Scheduler:
    def __init__(self, store: Store):
        self.store = store
        self._stop = threading.Event()
        self._kick = threading.Event()
        self._lock = threading.Lock()
        self.running = False
        self.progress = ""
        self.last_result: Optional[RunResult] = None
        self.last_error = ""
        self.last_run_at: Optional[datetime] = None
        self.next_run_at: Optional[datetime] = None
        self._thread: Optional[threading.Thread] = None

    # ---- control ----------------------------------------------------------
    def start(self) -> None:
        cfg = config_mod.load()
        delay = float(cfg.get("schedule", {}).get("first_run_delay_minutes", 2))
        self.next_run_at = datetime.now() + timedelta(minutes=delay)
        for r in self.store.last_runs(20):   # show the last real check after a restart
            if not r["dry_run"] and r["finished_at"]:
                self.last_run_at = datetime.fromisoformat(r["finished_at"])
                break
        self._thread = threading.Thread(target=self._loop, name="soundbot-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._kick.set()

    def run_now(self) -> bool:
        if self.running:
            return False
        self.next_run_at = datetime.now()
        self._kick.set()
        return True

    def reschedule(self) -> None:
        """Called after config save: next run = last run + new interval (or now + interval if never ran)."""
        cfg = config_mod.load()
        hours = float(cfg.get("schedule", {}).get("interval_hours", 3))
        base = self.last_run_at or datetime.now()
        self.next_run_at = base + timedelta(hours=hours)

    def status(self) -> dict:
        return {
            "running": self.running,
            "progress": self.progress,
            "last_run_at": self.last_run_at.isoformat(timespec="seconds") if self.last_run_at else None,
            "next_run_at": self.next_run_at.isoformat(timespec="seconds") if self.next_run_at else None,
            "last_summary": self.last_result.summary if self.last_result else "",
            "last_error": self.last_error,
        }

    # ---- loop ---------------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop.is_set():
            now = datetime.now()
            if self.next_run_at and now >= self.next_run_at:
                self._do_run()
            else:
                self._kick.wait(timeout=20)
                self._kick.clear()

    def _do_run(self) -> None:
        with self._lock:
            self.running = True
            self.progress = "starting…"
        try:
            self.last_result = run_check(self.store, progress=self._set_progress)
            self.last_error = ""
        except Exception as e:
            log.exception("scheduled check failed")
            self.last_error = f"{type(e).__name__}: {e}"
        finally:
            self.last_run_at = datetime.now()
            cfg = config_mod.load()
            hours = float(cfg.get("schedule", {}).get("interval_hours", 3))
            self.next_run_at = self.last_run_at + timedelta(hours=hours)
            with self._lock:
                self.running = False
                self.progress = ""

    def _set_progress(self, msg: str) -> None:
        self.progress = msg
