"""SQLite cache: daily/monthly view series and metadata lookups.

Past pageview counts never change, so series are cached forever and only the
missing date ranges are fetched on repeat or extended queries.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import date
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent


def _default_cache_dir() -> Path:
    """Skill-local .cache, or ~/.cache/wiki-interest when the skill folder is read-only."""
    if os.environ.get("WIKITREND_CACHE_DIR"):
        return Path(os.environ["WIKITREND_CACHE_DIR"])
    local = SKILL_DIR / ".cache"
    try:
        local.mkdir(exist_ok=True)
        if os.access(local, os.W_OK):
            return local
    except OSError:
        pass
    return Path.home() / ".cache" / "wiki-interest"


DEFAULT_CACHE_DIR = _default_cache_dir()
META_TTL_SECONDS = 30 * 24 * 3600


class Cache:
    def __init__(self, cache_dir: Path | str = DEFAULT_CACHE_DIR):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.dir / "cache.sqlite", check_same_thread=False)
        self.lock = threading.RLock()
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS points (
                key TEXT, day TEXT, views INTEGER, PRIMARY KEY (key, day));
            CREATE TABLE IF NOT EXISTS coverage (
                key TEXT PRIMARY KEY, first TEXT, last TEXT);
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY, fetched REAL, body TEXT);
            """
        )

    # ---- series -----------------------------------------------------------
    def coverage(self, key: str) -> tuple[date, date] | None:
        with self.lock:
            row = self.db.execute("SELECT first, last FROM coverage WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        return date.fromisoformat(row[0]), date.fromisoformat(row[1])

    def store_series(self, key: str, first: date, last: date, points: dict[date, int]) -> None:
        """Store points fetched for [first, last] and extend the covered range."""
        with self.lock, self.db:
            self.db.executemany(
                "INSERT OR REPLACE INTO points VALUES (?,?,?)",
                [(key, d.isoformat(), int(v)) for d, v in points.items()],
            )
            cov = self.coverage(key)
            if cov:
                first, last = min(first, cov[0]), max(last, cov[1])
            self.db.execute(
                "INSERT OR REPLACE INTO coverage VALUES (?,?,?)",
                (key, first.isoformat(), last.isoformat()),
            )

    def load_series(self, key: str, first: date, last: date) -> dict[date, int]:
        with self.lock:
            rows = self.db.execute(
                "SELECT day, views FROM points WHERE key=? AND day BETWEEN ? AND ?",
                (key, first.isoformat(), last.isoformat()),
            ).fetchall()
        return {date.fromisoformat(d): v for d, v in rows}

    # ---- metadata (search results, sitelinks, redirects) -------------------
    def get_meta(self, key: str):
        with self.lock:
            row = self.db.execute("SELECT fetched, body FROM meta WHERE key=?", (key,)).fetchone()
        if row and time.time() - row[0] < META_TTL_SECONDS:
            return json.loads(row[1])
        return None

    def put_meta(self, key: str, value) -> None:
        with self.lock, self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO meta VALUES (?,?,?)",
                (key, time.time(), json.dumps(value, ensure_ascii=False)),
            )

    def stats(self) -> dict:
        q = lambda sql: self.db.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "series": q("SELECT COUNT(*) FROM coverage"),
            "points": q("SELECT COUNT(*) FROM points"),
            "meta_entries": q("SELECT COUNT(*) FROM meta"),
            "path": str(self.dir / "cache.sqlite"),
        }

    def clear(self) -> None:
        with self.lock, self.db:
            for t in ("points", "coverage", "meta"):
                self.db.execute(f"DELETE FROM {t}")


def missing_ranges(requested: tuple[date, date], covered: tuple[date, date] | None):
    """Return the ranges to fetch so that coverage spans `requested` without gaps.

    Ranges always touch the covered block, so the cache stays one contiguous
    interval per series (a request far before the covered block also fetches
    the days in between).
    """
    start, end = requested
    if covered is None:
        return [(start, end)]
    c0, c1 = covered
    out = []
    if start < c0:
        out.append((start, date.fromordinal(c0.toordinal() - 1)))
    if end > c1:
        out.append((date.fromordinal(c1.toordinal() + 1), end))
    return out
