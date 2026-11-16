"""Repositories on top of SQLite."""
from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from typing import Any

from .config import AppConfig
from .db import Database, dumps, loads
from .models import Paper, Preset, Schedule, Settings
from .papers import BUILTIN_BY_ID, BUILTIN_PAPERS


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def now_iso() -> str:
    return now_utc().isoformat(timespec="seconds")


def parse_iso(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.UTC)


JSON_PRINT_FIELDS = ("preset", "paper", "asset", "render", "ink")


class Store:
    def __init__(self, db: Database, cfg: AppConfig):
        self.db = db
        self.cfg = cfg

    # ------------------------------------------------------------ settings
    def raw_settings(self) -> Settings:
        row = self.db.one("SELECT value FROM settings WHERE key = 'settings'")
        return Settings(**(loads(row["value"], {}) if row else {}))

    def settings(self) -> Settings:
        s = self.raw_settings()
        c = self.cfg
        if c.immich_url:
            s.immich_url = c.immich_url
        if c.immich_api_key:
            s.immich_api_key = c.immich_api_key
        if c.immich_public_url:
            s.immich_public_url = c.immich_public_url
        if c.printer_uri:
            s.printer_uri = c.printer_uri
        if c.demo and not s.printer_uri:
            s.printer_uri = "virtual://pro-310"
        return s

    def save_settings(self, s: Settings) -> None:
        self.db.execute("INSERT INTO settings(key, value) VALUES('settings', ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (s.model_dump_json(),))

    def update_settings(self, **changes: Any) -> Settings:
        s = self.raw_settings()
        data = s.model_dump()
        for k, v in changes.items():
            if isinstance(v, dict) and isinstance(data.get(k), dict):
                data[k] = {**data[k], **v}
            else:
                data[k] = v
        s = Settings(**data)
        self.save_settings(s)
        return s

    def kv_get(self, key: str, default: Any = None) -> Any:
        row = self.db.one("SELECT value FROM settings WHERE key = ?", (key,))
        return loads(row["value"], default) if row else default

    def kv_set(self, key: str, value: Any) -> None:
        self.db.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, dumps(value)))

    # ------------------------------------------------------------ presets
    def presets(self) -> list[Preset]:
        rows = self.db.query("SELECT * FROM presets ORDER BY sort, created_at")
        out = []
        for r in rows:
            p = Preset(**loads(r["data"], {}))
            p.id, p.name, p.sort = r["id"], r["name"], r["sort"]
            p.created_at, p.updated_at = r["created_at"], r["updated_at"]
            out.append(p)
        return out

    def preset(self, preset_id: str) -> Preset | None:
        r = self.db.one("SELECT * FROM presets WHERE id = ?", (preset_id,))
        if not r:
            return None
        p = Preset(**loads(r["data"], {}))
        p.id, p.name, p.sort, p.created_at, p.updated_at = r["id"], r["name"], r["sort"], r["created_at"], r["updated_at"]
        return p

    def save_preset(self, p: Preset) -> Preset:
        now = now_iso()
        existing = self.db.one("SELECT created_at FROM presets WHERE id = ?", (p.id,))
        p.created_at = existing["created_at"] if existing else now
        p.updated_at = now
        data = p.model_dump_json(exclude={"created_at", "updated_at"})
        self.db.execute(
            "INSERT INTO presets(id, name, data, sort, created_at, updated_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, data=excluded.data, sort=excluded.sort, "
            "updated_at=excluded.updated_at", (p.id, p.name, data, p.sort, p.created_at, p.updated_at))
        return p

    def delete_preset(self, preset_id: str) -> None:
        self.db.execute("DELETE FROM presets WHERE id = ?", (preset_id,))

    # ------------------------------------------------------------ papers
    def paper_overrides(self) -> dict[str, dict[str, Any]]:
        return {r["id"]: loads(r["data"], {}) for r in self.db.query("SELECT * FROM papers")}

    def papers(self) -> list[Paper]:
        overrides = self.paper_overrides()
        out: list[Paper] = []
        for base in BUILTIN_PAPERS:
            if base.id in overrides:
                data = {**base.model_dump(), **overrides[base.id], "id": base.id, "builtin": True, "customized": True}
                out.append(Paper(**data))
            else:
                out.append(base.model_copy(deep=True))
        for pid, data in overrides.items():
            if pid not in BUILTIN_BY_ID:
                out.append(Paper(**{**data, "id": pid, "builtin": False}))
        return out

    def paper(self, paper_id: str) -> Paper | None:
        for p in self.papers():
            if p.id == paper_id:
                return p
        return None

    def save_paper(self, p: Paper) -> Paper:
        data = p.model_dump(exclude={"builtin", "customized"})
        self.db.execute("INSERT INTO papers(id, data, updated_at) VALUES(?,?,?) "
                        "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                        (p.id, dumps(data), now_iso()))
        return self.paper(p.id) or p

    def reset_paper(self, paper_id: str) -> None:
        self.db.execute("DELETE FROM papers WHERE id = ?", (paper_id,))

    # ------------------------------------------------------------ schedules
    def schedules(self) -> list[Schedule]:
        out = []
        for r in self.db.query("SELECT * FROM schedules ORDER BY created_at"):
            s = Schedule(**loads(r["data"], {}))
            s.id, s.name, s.enabled = r["id"], r["name"], bool(r["enabled"])
            s.next_run_at, s.last_run_at = r["next_run_at"], r["last_run_at"]
            s.created_at, s.updated_at = r["created_at"], r["updated_at"]
            out.append(s)
        return out

    def schedule(self, schedule_id: str) -> Schedule | None:
        for s in self.schedules():
            if s.id == schedule_id:
                return s
        return None

    def save_schedule(self, s: Schedule) -> Schedule:
        now = now_iso()
        existing = self.db.one("SELECT created_at FROM schedules WHERE id = ?", (s.id,))
        s.created_at = existing["created_at"] if existing else now
        s.updated_at = now
        data = s.model_dump_json(exclude={"next_run_at", "last_run_at", "created_at", "updated_at"})
        self.db.execute(
            "INSERT INTO schedules(id, name, enabled, data, next_run_at, last_run_at, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, enabled=excluded.enabled, "
            "data=excluded.data, next_run_at=excluded.next_run_at, updated_at=excluded.updated_at",
            (s.id, s.name, int(s.enabled), data, s.next_run_at, s.last_run_at, s.created_at, s.updated_at))
        return s

    def set_schedule_times(self, schedule_id: str, next_run: str | None, last_run: str | None = None) -> None:
        if last_run is None:
            self.db.execute("UPDATE schedules SET next_run_at = ? WHERE id = ?", (next_run, schedule_id))
        else:
            self.db.execute("UPDATE schedules SET next_run_at = ?, last_run_at = ? WHERE id = ?",
                            (next_run, last_run, schedule_id))

    def delete_schedule(self, schedule_id: str) -> None:
        self.db.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        self.db.execute("UPDATE picks SET status = 'expired' WHERE schedule_id = ? AND status IN ('pending','approved')",
                        (schedule_id,))

    # ------------------------------------------------------------ picks
    def add_pick(self, pick_id: str, schedule_id: str | None, asset: dict[str, Any], score: dict[str, Any],
                 source: str, due_at: str | None, status: str = "pending") -> dict[str, Any]:
        self.db.execute(
            "INSERT INTO picks(id, schedule_id, asset_id, asset, score, source, status, due_at, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (pick_id, schedule_id, asset["id"], dumps(asset), dumps(score), source, status, due_at, now_iso()))
        return self.pick(pick_id) or {}

    def pick(self, pick_id: str) -> dict[str, Any] | None:
        r = self.db.one("SELECT * FROM picks WHERE id = ?", (pick_id,))
        return self._pick_row(r) if r else None

    @staticmethod
    def _pick_row(r: dict[str, Any]) -> dict[str, Any]:
        r = dict(r)
        r["asset"] = loads(r["asset"], {})
        r["score"] = loads(r["score"], {})
        return r

    def active_pick(self, schedule_id: str) -> dict[str, Any] | None:
        r = self.db.one("SELECT * FROM picks WHERE schedule_id = ? AND status IN ('pending','approved','skipped') "
                        "ORDER BY created_at DESC LIMIT 1", (schedule_id,))
        return self._pick_row(r) if r else None

    def update_pick(self, pick_id: str, **fields: Any) -> None:
        if not fields:
            return
        if "status" in fields and "decided_at" not in fields and fields["status"] != "pending":
            fields["decided_at"] = now_iso()
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(f"UPDATE picks SET {cols} WHERE id = ?", (*fields.values(), pick_id))

    def expire_picks(self, schedule_id: str, statuses: Iterable[str] = ("pending", "approved", "skipped")) -> None:
        q = ",".join("?" for _ in statuses)
        self.db.execute(f"UPDATE picks SET status = 'expired', decided_at = ? WHERE schedule_id = ? "
                        f"AND status IN ({q})", (now_iso(), schedule_id, *statuses))

    # ------------------------------------------------------------ prints
    def add_print(self, row: dict[str, Any]) -> None:
        data = dict(row)
        for f in JSON_PRINT_FIELDS:
            if f in data and not isinstance(data[f], str):
                data[f] = dumps(data[f])
        data.setdefault("created_at", now_iso())
        cols = ", ".join(data)
        q = ", ".join("?" for _ in data)
        self.db.execute(f"INSERT INTO prints({cols}) VALUES({q})", tuple(data.values()))

    def update_print(self, print_id: str, **fields: Any) -> None:
        if not fields:
            return
        for f in JSON_PRINT_FIELDS:
            if f in fields and not isinstance(fields[f], str):
                fields[f] = dumps(fields[f])
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(f"UPDATE prints SET {cols} WHERE id = ?", (*fields.values(), print_id))

    @staticmethod
    def _print_row(r: dict[str, Any]) -> dict[str, Any]:
        r = dict(r)
        for f in JSON_PRINT_FIELDS:
            r[f] = loads(r.get(f), {}) if r.get(f) else ({} if f != "asset" else None)
        r["hidden"] = bool(r.get("hidden"))
        return r

    def print_row(self, print_id: str) -> dict[str, Any] | None:
        r = self.db.one("SELECT * FROM prints WHERE id = ?", (print_id,))
        return self._print_row(r) if r else None

    def prints(self, *, limit: int = 60, offset: int = 0, statuses: list[str] | None = None,
               include_hidden: bool = False, include_tests: bool = False, year: int | None = None,
               paper_id: str | None = None, q: str | None = None) -> tuple[list[dict[str, Any]], int]:
        where, params = ["1=1"], []
        if not include_hidden:
            where.append("hidden = 0")
        if not include_tests:
            where.append("COALESCE(source,'') != 'test'")
        if statuses:
            where.append("status IN (" + ",".join("?" for _ in statuses) + ")")
            params.extend(statuses)
        if year:
            where.append("substr(created_at,1,4) = ?")
            params.append(str(year))
        if paper_id:
            where.append("json_extract(paper, '$.id') = ?")
            params.append(paper_id)
        if q:
            where.append("(asset LIKE ? OR preset_name LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%"])
        w = " AND ".join(where)
        total = self.db.scalar(f"SELECT COUNT(*) FROM prints WHERE {w}", tuple(params)) or 0
        rows = self.db.query(f"SELECT * FROM prints WHERE {w} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                             (*params, limit, offset))
        return [self._print_row(r) for r in rows], int(total)

    def delete_print(self, print_id: str) -> None:
        self.db.execute("DELETE FROM prints WHERE id = ?", (print_id,))

    def printed_asset_ids(self, since: dt.datetime | None = None) -> set[str]:
        if since is None:
            rows = self.db.query("SELECT DISTINCT asset_id FROM prints WHERE asset_id IS NOT NULL "
                                 "AND status NOT IN ('failed','canceled')")
        else:
            rows = self.db.query("SELECT DISTINCT asset_id FROM prints WHERE asset_id IS NOT NULL "
                                 "AND status NOT IN ('failed','canceled') AND created_at >= ?",
                                 (since.isoformat(timespec="seconds"),))
        return {r["asset_id"] for r in rows}

    def active_prints(self) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM prints WHERE status IN ('queued','preparing','rendering','sending',"
                             "'printing','waiting','held') ORDER BY created_at")
        return [self._print_row(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        done = "status = 'completed' AND COALESCE(source,'') != 'test'"
        total = self.db.scalar(f"SELECT COUNT(*) FROM prints WHERE {done}") or 0
        sheets = self.db.scalar(f"SELECT COALESCE(SUM(copies),0) FROM prints WHERE {done}") or 0
        month = now_utc().strftime("%Y-%m")
        this_month = self.db.scalar(f"SELECT COUNT(*) FROM prints WHERE {done} AND substr(created_at,1,7) = ?",
                                    (month,)) or 0
        cost = self.db.scalar(f"SELECT COALESCE(SUM(cost),0) FROM prints WHERE {done}") or 0.0
        first = self.db.scalar(f"SELECT MIN(created_at) FROM prints WHERE {done}")
        by_paper = self.db.query(
            f"SELECT json_extract(paper,'$.name') AS name, COUNT(*) AS n, COALESCE(SUM(copies),0) AS sheets "
            f"FROM prints WHERE {done} GROUP BY name ORDER BY n DESC")
        by_size = self.db.query(
            f"SELECT json_extract(preset,'$.output.media_size') AS size, COUNT(*) AS n FROM prints WHERE {done} "
            f"GROUP BY size ORDER BY n DESC")
        days = [r["d"] for r in self.db.query(
            f"SELECT DISTINCT substr(created_at,1,10) AS d FROM prints WHERE {done} ORDER BY d DESC LIMIT 400")]
        streak = 0
        if days:
            cur = now_utc().date()
            dayset = set(days)
            if cur.isoformat() not in dayset:
                cur -= dt.timedelta(days=1)
            while cur.isoformat() in dayset:
                streak += 1
                cur -= dt.timedelta(days=1)
        years = [r["y"] for r in self.db.query(
            f"SELECT DISTINCT substr(json_extract(asset,'$.taken_at'),1,4) AS y FROM prints WHERE {done} "
            f"AND json_extract(asset,'$.taken_at') IS NOT NULL ORDER BY y")]
        return {"total": total, "sheets": sheets, "this_month": this_month, "cost": round(float(cost), 2),
                "since": first, "by_paper": by_paper, "by_size": by_size, "streak": streak,
                "years": [y for y in years if y]}

    # ------------------------------------------------------------ events
    # ------------------------------------------------------------ ink ledger
    INK_EVENT_FIELDS = ("at", "ink", "kind", "level_ml", "level_before_ml", "added_ml", "used_ml", "used_est_ml", "note")

    def add_ink_event(self, **fields: Any) -> int:
        data = {k: fields.get(k) for k in self.INK_EVENT_FIELDS}
        data["at"] = data["at"] or now_iso()
        cur = self.db.execute(f"INSERT INTO ink_events({', '.join(data)}) VALUES({', '.join('?' for _ in data)})",
                              tuple(data.values()))
        return int(cur.lastrowid or 0)

    def ink_events(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM ink_events ORDER BY at DESC, id DESC LIMIT ?", (limit,))

    def delete_ink_event(self, event_id: int) -> bool:
        return self.db.execute("DELETE FROM ink_events WHERE id = ?", (event_id,)).rowcount > 0

    # ------------------------------------------------------------ activity log
    def log(self, level: str, kind: str, message: str, data: dict[str, Any] | None = None) -> None:
        self.db.execute("INSERT INTO events(ts, level, kind, message, data) VALUES(?,?,?,?,?)",
                        (now_iso(), level, kind, message, dumps(data) if data else None))
        self.db.execute("DELETE FROM events WHERE id IN (SELECT id FROM events ORDER BY id DESC LIMIT -1 OFFSET 2000)")

    def events(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))
        for r in rows:
            r["data"] = loads(r["data"], None)
        return rows
