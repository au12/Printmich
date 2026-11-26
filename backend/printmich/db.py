"""Tiny SQLite layer (WAL, single shared connection guarded by a lock)."""
from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

MIGRATIONS = [
    # v1
    """
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE presets (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, data TEXT NOT NULL, sort INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE papers (id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE schedules (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0, data TEXT NOT NULL,
        next_run_at TEXT, last_run_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE picks (
        id TEXT PRIMARY KEY, schedule_id TEXT, asset_id TEXT NOT NULL, asset TEXT NOT NULL, score TEXT,
        source TEXT, status TEXT NOT NULL, due_at TEXT, created_at TEXT NOT NULL, decided_at TEXT, print_id TEXT
    );
    CREATE INDEX picks_schedule ON picks(schedule_id, status);
    CREATE TABLE prints (
        id TEXT PRIMARY KEY, asset_id TEXT, schedule_id TEXT, pick_id TEXT, preset_id TEXT, preset_name TEXT,
        preset TEXT, paper TEXT, asset TEXT, status TEXT NOT NULL, status_detail TEXT, ipp_job_id INTEGER,
        printer TEXT, render TEXT, error TEXT, copies INTEGER NOT NULL DEFAULT 1, cost REAL, source TEXT,
        thumb_w INTEGER, thumb_h INTEGER, created_at TEXT NOT NULL, started_at TEXT, completed_at TEXT,
        hidden INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX prints_created ON prints(created_at);
    CREATE INDEX prints_asset ON prints(asset_id);
    CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, level TEXT NOT NULL, kind TEXT NOT NULL,
        message TEXT NOT NULL, data TEXT
    );
    CREATE INDEX events_ts ON events(ts);
    """,
    # v2: estimated ink per print and the refill ledger
    """
    ALTER TABLE prints ADD COLUMN ink TEXT;
    CREATE TABLE ink_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, ink TEXT NOT NULL, kind TEXT NOT NULL,
        level_ml REAL, level_before_ml REAL, added_ml REAL, used_ml REAL, used_est_ml REAL, note TEXT
    );
    CREATE INDEX ink_events_at ON ink_events(at);
    """,
    # v3 (1.2.0): paper names are proper names, so the two built-in presets named after one follow suit
    """
    UPDATE presets SET name = '5×7 Semi-Gloss' WHERE id = 'p-5x7' AND name = '5×7 Semi-gloss';
    UPDATE presets SET name = 'Black & White, Letter Matte' WHERE id = 'p-bw-matte' AND name = 'Black & white, Letter Matte';
    UPDATE prints SET preset_name = '5×7 Semi-Gloss' WHERE preset_name = '5×7 Semi-gloss';
    UPDATE prints SET preset_name = 'Black & White, Letter Matte' WHERE preset_name = 'Black & white, Letter Matte';
    """,
]


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None, timeout=30)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        with self.lock:
            version = self.conn.execute("PRAGMA user_version").fetchone()[0]
            for i, sql in enumerate(MIGRATIONS[version:], start=version + 1):
                self.conn.executescript(f"BEGIN; {sql}; PRAGMA user_version={i}; COMMIT;")

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.conn.execute(sql, params)

    def query(self, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def scalar(self, sql: str, params: tuple | dict = ()) -> Any:
        with self.lock:
            row = self.conn.execute(sql, params).fetchone()
            return row[0] if row else None

    @contextmanager
    def tx(self) -> Iterator[None]:
        with self.lock:
            self.conn.execute("BEGIN")
            try:
                yield
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self.lock:
            self.conn.close()


def dumps(v: Any) -> str:
    return json.dumps(v, separators=(",", ":"), default=str)


def loads(s: str | None, default: Any = None) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default
