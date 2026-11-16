"""Estimated ink use for the PRO-310's ten inks, and a ledger of refills.

A Canon tank reports its level from a chip that counts the ink drawn from it. A refilled tank still
counts as empty, so the printer stops once (support code 1699) until its Stop button is held for five
seconds; after that it no longer tracks that tank at all, and won't warn before it runs dry.

Printmich estimates every tank from the pages it actually prints instead:

    ml = area × (ML_PER_SQ_IN[ink] × coverage[ink] + CLEAN_ML_PER_SQ_IN)

`coverage` comes from a simple separation of the finished page into the ten inks: light inks for
highlights, gray and black for neutrals, red for saturated reds and oranges, and chroma optimizer over
the printed area on glossy papers. The per-ink constants reproduce Canon's published PRO-310 yields
(4×6 on Photo Paper Pro Platinum, ISO/IEC 29102) on a typical mix of photos; the cleaning term is the
matte black those yields use on glossy paper, where it is never printed. `dev/fit_ink_model.py` re-fits
them. Each refill logged with the amount of ink it took calibrates that tank from then on.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pyvips

from .db import loads
from .store import now_iso, now_utc, parse_iso

if TYPE_CHECKING:  # pragma: no cover
    from .state import App

log = logging.getLogger("printmich.ink")

INKS: list[tuple[str, str, str]] = [
    ("MBK", "Matte Black", "#2b2b2b"),
    ("PBK", "Photo Black", "#060606"),
    ("GY", "Gray", "#8e8e8e"),
    ("C", "Cyan", "#00a3e0"),
    ("PC", "Photo Cyan", "#73cdeb"),
    ("M", "Magenta", "#e2007a"),
    ("PM", "Photo Magenta", "#f28dc0"),
    ("Y", "Yellow", "#ffdd00"),
    ("R", "Red", "#e4002b"),
    ("CO", "Chroma Optimizer", "#d9d9d9"),
]
INK_KEYS = [k for k, _, _ in INKS]
INK_NAMES = {k: n for k, n, _ in INKS}

# ml of ink per square inch at 100% coverage of that ink (fitted by dev/fit_ink_model.py).
ML_PER_SQ_IN = {"PBK": 0.0042, "GY": 0.0061, "C": 0.0017, "PC": 0.0057, "M": 0.0103, "PM": 0.0058,
                "Y": 0.0045, "R": 0.0023, "CO": 0.0058}
ML_PER_SQ_IN["MBK"] = ML_PER_SQ_IN["PBK"]  # matte black does photo black's job on matte papers
# Automatic head cleaning draws on every tank: 14.4 ml of MBK per 1,679 glossy 4×6 prints.
CLEAN_ML_PER_SQ_IN = 14.4 / 1679 / 24

# Separation model parameters (see fit_ink_model.py).
GCR = 0.7          # share of the neutral component moved from C/M/Y to gray and black
LIGHT_INK = 2.5    # light inks need ~2.5× the volume for the same density
INK_LIMIT = 2.6    # total ink coverage a pixel can carry


def _smooth(x: np.ndarray, a: float, b: float) -> np.ndarray:
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def coverage(rgb: np.ndarray, *, matte: bool) -> dict[str, float]:
    """Mean coverage of each ink (0 = none, 1 = the ink's maximum) for an sRGB page (H×W×3 uint8)."""
    x = rgb.reshape(-1, 3).astype(np.float32) / 255.0
    c, m, y = 1 - x[:, 0], 1 - x[:, 1], 1 - x[:, 2]
    k = np.minimum(np.minimum(c, m), y)
    c, m, y = c - GCR * k, m - GCR * k, y - GCR * k
    black = _smooth(k, 0.35, 1.0) ** 1.3
    gray = GCR * np.clip(k * 1.6, 0, 1) * (1 - 0.6 * black)
    red = np.minimum(m, y) * 0.7
    m, y = m - red * 0.6, y - red * 0.6

    def split(v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        dark = v * _smooth(v, 0.04, 0.3)
        return dark, np.clip((v - dark) * LIGHT_INK, 0, 1)

    cd, pc = split(c)
    md, pm = split(m)
    zero = np.zeros_like(k)
    printed = np.clip((c + m + y + k) * 4, 0, 1)
    ch = {"MBK": zero, "PBK": zero, "GY": gray, "C": cd, "PC": pc, "M": md, "PM": pm, "Y": y, "R": red,
          "CO": zero if matte else printed * 0.35}
    ch["MBK" if matte else "PBK"] = black
    total = sum(ch.values())
    scale = np.minimum(1.0, INK_LIMIT / np.maximum(total, 1e-6))
    return {ink: float(np.mean(v * scale)) for ink, v in ch.items()}


def image_array(src: pyvips.Image | Path | str | bytes, size: int = 192) -> np.ndarray:
    """A small sRGB array of an image, enough for coverage statistics."""
    if isinstance(src, pyvips.Image):
        img = src.thumbnail_image(size)
    elif isinstance(src, bytes):
        img = pyvips.Image.thumbnail_buffer(src, size)
    else:
        img = pyvips.Image.thumbnail(str(src), size)
    if img.hasalpha():
        img = img.flatten(background=[255, 255, 255])
    if img.interpretation not in ("srgb", "b-w"):
        img = img.colourspace("srgb")
    if img.bands == 1:
        img = img.bandjoin([img, img])
    img = img.extract_band(0, n=3).cast("uchar")
    return np.ndarray(buffer=img.write_to_memory(), dtype=np.uint8, shape=[img.height, img.width, 3])


def estimate_ml(rgb: np.ndarray, page_w_mm: float, page_h_mm: float, *, matte: bool, copies: int = 1) -> dict[str, float]:
    """Estimated ml of each ink for a printed page (all copies), before calibration."""
    area = page_w_mm * page_h_mm / 645.16
    cov = coverage(rgb, matte=matte)
    per_copy = {ink: area * (ML_PER_SQ_IN[ink] * cov[ink] + CLEAN_ML_PER_SQ_IN) for ink in INK_KEYS}
    return {ink: round(v * max(1, copies), 5) for ink, v in per_copy.items()}


def marker_ink(name: str, color: str = "") -> str | None:
    """Map a printer's marker name (e.g. "PBK", "Photo Black", "MBK · Matte Black") to an ink key."""
    s = name.lower()
    head = name.strip().split()[0].upper() if name.strip() else ""
    if head in INK_KEYS:
        return head
    for words, key in ((("matte black", "mat black"), "MBK"), (("photo black",), "PBK"),
                       (("gray", "grey"), "GY"), (("photo cyan", "light cyan"), "PC"), (("cyan",), "C"),
                       (("photo magenta", "light magenta"), "PM"), (("magenta",), "M"), (("yellow",), "Y"),
                       (("chroma", "optimizer", "optimiser", "gloss"), "CO"), (("red",), "R")):
        if any(w in s for w in words):
            return key
    return None


class InkTracker:
    """Estimated tank levels from prints and logged refills, plus refill reminders."""

    def __init__(self, app: App):
        self.app = app
        self._checked_at = 0.0

    # ------------------------------------------------------------ settings & helpers
    @property
    def settings(self):
        return self.app.store.settings().ink

    @property
    def estimating(self) -> bool:
        return self.settings.levels == "estimate"

    def _virtual(self) -> bool:
        return self.app.printer.is_virtual()

    def estimate_print(self, page: Path | pyvips.Image, page_w_mm: float, page_h_mm: float, *, black_ink: str,
                       copies: int = 1) -> dict[str, float]:
        return estimate_ml(image_array(page), page_w_mm, page_h_mm, matte=black_ink == "matte", copies=copies)

    async def backfill(self, limit: int = 2000) -> int:
        """Estimate ink for prints made before ink estimates existed, from their saved page previews."""
        rows = self.app.db.query("SELECT id, render, paper, copies FROM prints WHERE ink IS NULL AND status = 'completed' "
                                 "ORDER BY completed_at DESC LIMIT ?", (limit,))
        done = 0
        for r in rows:
            page = self.app.cfg.prints_dir / f"{r['id']}.page.jpg"
            plan = (loads(r["render"], {}) or {}).get("plan") or {}
            if not page.exists() or not plan.get("page_w_mm") or not plan.get("page_h_mm"):
                continue
            paper = loads(r["paper"], {}) or {}
            try:
                ml = await asyncio.to_thread(self.estimate_print, page, plan["page_w_mm"], plan["page_h_mm"],
                                             black_ink=paper.get("black_ink", "photo"), copies=r.get("copies") or 1)
            except Exception as e:  # a damaged preview shouldn't stop the rest
                log.debug("ink backfill skipped %s: %s", r["id"], e)
                continue
            self.app.store.update_print(r["id"], ink=ml)
            done += 1
        if done:
            log.info("estimated ink for %d earlier prints", done)
        return done

    # ------------------------------------------------------------ ledger
    def events(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.app.store.ink_events(limit)

    def factors(self) -> dict[str, dict[str, float]]:
        """Per-ink calibration from refills logged with the amount added: actual ÷ estimated use."""
        actual = dict.fromkeys(INK_KEYS, 0.0)
        est = dict.fromkeys(INK_KEYS, 0.0)
        n = dict.fromkeys(INK_KEYS, 0)
        for e in self.app.store.ink_events(10_000):
            if (e["kind"] == "refill" and e["ink"] in actual and e.get("used_ml") is not None
                    and (e.get("used_est_ml") or 0) >= 0.5):
                actual[e["ink"]] += e["used_ml"]
                est[e["ink"]] += e["used_est_ml"]
                n[e["ink"]] += 1
        return {k: {"factor": round(min(3.0, max(0.33, actual[k] / est[k])) if n[k] else 1.0, 3), "samples": n[k]}
                for k in INK_KEYS}

    def _usage(self, since: dict[str, str]) -> tuple[dict[str, float], dict[str, int]]:
        """Raw estimated ml and print count per ink since each ink's reference time."""
        used = dict.fromkeys(INK_KEYS, 0.0)
        count = dict.fromkeys(INK_KEYS, 0)
        if not since:
            return used, count
        earliest = min(since.values())
        virtual = self._virtual()
        rows = self.app.db.query("SELECT ink, printer, completed_at FROM prints WHERE status = 'completed' "
                                 "AND ink IS NOT NULL AND completed_at > ?", (earliest,))
        for r in rows:
            if str(r.get("printer") or "").startswith("virtual://") != virtual:
                continue
            ml = loads(r["ink"], {}) or {}
            for ink, t in since.items():
                if r["completed_at"] > t and ml.get(ink):
                    used[ink] += float(ml[ink])
                    count[ink] += 1
        return used, count

    def tanks(self) -> list[dict[str, Any]]:
        s = self.settings
        cap = s.tank_ml
        last: dict[str, dict[str, Any]] = {}
        for e in self.app.store.ink_events(10_000):
            if e["kind"] in ("refill", "set") and e["ink"] not in last:
                last[e["ink"]] = e  # newest first
        used, count = self._usage({k: e["at"] for k, e in last.items()})
        factors = self.factors()
        now = now_utc()
        out = []
        for key, name, color in INKS:
            e = last.get(key)
            f = factors.get(key, {"factor": 1.0, "samples": 0})
            item: dict[str, Any] = {"ink": key, "name": name, "color": color, "capacity_ml": cap,
                                    "factor": f["factor"], "calibrations": f["samples"]}
            if e is None:
                item.update(level_ml=None, percent=None, since=None, used_ml=0.0, prints=0, days=None,
                            status="unknown")
            else:
                used_ml = used[key] * f["factor"]
                level = (e["level_ml"] if e["level_ml"] is not None else cap) - used_ml
                pct = max(0.0, min(100.0, level / cap * 100))
                at = parse_iso(e["at"]) or now
                status = ("empty" if pct <= max(s.hold_below, 2) else "low" if pct <= s.remind_below else "ok")
                item.update(level_ml=round(max(level, 0.0), 2), percent=round(pct, 1), since=e["at"],
                            since_kind=e["kind"], used_ml=round(used_ml, 2), prints=count[key],
                            days=round((now - at).total_seconds() / 86400, 1), status=status)
            out.append(item)
        return out

    def calibrated(self, raw: dict[str, float] | None) -> dict[str, float] | None:
        if not raw:
            return None
        f = self.factors()
        return {k: round(float(v) * f.get(k, {}).get("factor", 1.0), 4) for k, v in raw.items()}

    def start(self, source: str) -> list[dict[str, Any]]:
        """Begin tracking: take today's levels from the printer's readings or assume full tanks."""
        cap = self.settings.tank_ml
        readings: dict[str, float] = {}
        if source == "printer":
            for m in (self.app.printer.last_markers() or []):
                key = marker_ink(m.get("name", ""), m.get("color", ""))
                lvl, high = m.get("level", -1), m.get("high") or 100
                if key and isinstance(lvl, int) and lvl >= 0:
                    readings[key] = max(0.0, min(1.0, lvl / high))
        at = now_iso()
        for key in INK_KEYS:
            frac = readings.get(key, 1.0)
            note = "From the printer's reading" if key in readings else "Assumed full"
            self.app.store.add_ink_event(at=at, ink=key, kind="set", level_ml=round(cap * frac, 2), note=note)
        self.app.store.log("info", "ink", "Started estimating ink levels")
        return self.tanks()

    def refill(self, inks: list[str], added_ml: dict[str, float] | None = None, note: str = "") -> list[dict[str, Any]]:
        """Log refilled tanks (topped up to full). With the amount added, the estimate calibrates itself."""
        cap = self.settings.tank_ml
        before = {t["ink"]: t for t in self.tanks()}
        prev = {}
        for e in self.app.store.ink_events(10_000):
            if e["kind"] in ("refill", "set") and e["ink"] not in prev:
                prev[e["ink"]] = e
        raw_used, _ = self._usage({k: e["at"] for k, e in prev.items()})
        at = now_iso()
        names = []
        for key in inks:
            if key not in INK_KEYS:
                continue
            added = (added_ml or {}).get(key)
            used_ml = used_est = None
            if added is not None and added > 0 and key in prev:
                start_level = prev[key]["level_ml"] if prev[key]["level_ml"] is not None else cap
                used_ml = round(max(0.0, start_level - (cap - float(added))), 3)
                used_est = round(raw_used.get(key, 0.0), 3)
            self.app.store.add_ink_event(at=at, ink=key, kind="refill", level_ml=cap, added_ml=added,
                                         used_ml=used_ml, used_est_ml=used_est, note=note,
                                         level_before_ml=(before.get(key) or {}).get("level_ml"))
            names.append(INK_NAMES[key])
        if names:
            self.app.store.log("info", "ink", "Refilled " + ", ".join(names))
            self.app.store.kv_set("ink_reminders", {**self._reminder_state(), "periodic": at})
        return self.tanks()

    def set_level(self, ink: str, percent: float, note: str = "") -> list[dict[str, Any]]:
        if ink not in INK_KEYS:
            raise ValueError(f"Unknown ink {ink}")
        cap = self.settings.tank_ml
        self.app.store.add_ink_event(at=now_iso(), ink=ink, kind="set", level_ml=round(cap * percent / 100, 2),
                                     note=note or "Set by hand")
        return self.tanks()

    # ------------------------------------------------------------ holds & reminders
    def hold_reason(self, raw_ml: dict[str, float] | None) -> str | None:
        """Why a scheduled print should wait for a refill, if any tank would drop below the hold level."""
        s = self.settings
        if not self.estimating or s.hold_below <= 0 or not raw_ml:
            return None
        factors = self.factors()
        short = []
        for t in self.tanks():
            if t["level_ml"] is None:
                continue
            need = float(raw_ml.get(t["ink"], 0.0)) * factors.get(t["ink"], {}).get("factor", 1.0)
            after = (t["level_ml"] - need) / t["capacity_ml"] * 100
            if after < s.hold_below:
                short.append(f"{t['name']} ({max(0, round(t['percent']))}%)")
        if not short:
            return None
        return ("Estimated ink is too low: " + ", ".join(short) +
                ". Refill and log it on the Printer page, or release this print to print anyway.")

    def _reminder_state(self) -> dict[str, Any]:
        st = self.app.store.kv_get("ink_reminders", {}) or {}
        st.setdefault("low", {})
        st.setdefault("empty", {})
        return st

    async def check(self, *, force: bool = False) -> list[str]:
        """Send refill reminders that are due. Returns the messages sent."""
        if not self.estimating:
            return []
        if not force and time.time() - self._checked_at < 300:
            return []
        self._checked_at = time.time()
        s = self.settings
        tanks = [t for t in self.tanks() if t["level_ml"] is not None]
        if not tanks:
            return []
        st = self._reminder_state()
        sent: list[str] = []

        empty = [t for t in tanks if t["status"] == "empty" and st["empty"].get(t["ink"]) != t["since"]]
        low = [t for t in tanks if t["status"] == "low" and st["low"].get(t["ink"]) != t["since"]]
        if empty:
            body = "\n".join(f"{t['name']}: about {t['level_ml']:.1f} ml ({round(t['percent'])}%)" for t in empty)
            msg = "Refill now. Scheduled prints wait until these tanks are refilled and logged.\n" + body
            await self.app.notifier.send("Printmich: ink nearly empty", msg, kind="warning", event="supplies")
            self.app.store.log("warning", "ink", "Ink nearly empty: " + ", ".join(t["name"] for t in empty))
            for t in empty:
                st["empty"][t["ink"]] = t["since"]
                st["low"][t["ink"]] = t["since"]
            sent.append(msg)
        if low:
            body = "\n".join(f"{t['name']}: about {t['level_ml']:.1f} ml ({round(t['percent'])}%)" for t in low)
            await self.app.notifier.send("Printmich: refill ink soon", body, kind="warning", event="supplies")
            self.app.store.log("info", "ink", "Ink running low: " + ", ".join(t["name"] for t in low))
            for t in low:
                st["low"][t["ink"]] = t["since"]
            sent.append(body)

        if s.remind_days > 0:
            ref = max([parse_iso(t["since"]) for t in tanks if t["since"]] + [parse_iso(st.get("periodic"))],
                      key=lambda d: d or dt.datetime.min.replace(tzinfo=dt.UTC))
            if ref and now_utc() - ref >= dt.timedelta(days=s.remind_days):
                lowest = sorted(tanks, key=lambda t: t["percent"])[:3]
                body = (f"It's been {s.remind_days} days since you last refilled or checked the ink. Lowest now: " +
                        ", ".join(f"{t['name']} {round(t['percent'])}%" for t in lowest) + ".")
                await self.app.notifier.send("Printmich: time to check the ink", body, kind="info", event="supplies")
                self.app.store.log("info", "ink", "Ink check reminder")
                st["periodic"] = now_iso()
                sent.append(body)

        self.app.store.kv_set("ink_reminders", st)
        return sent

    def acknowledge_check(self) -> None:
        """'I checked the ink' resets the periodic reminder without logging a refill."""
        self.app.store.kv_set("ink_reminders", {**self._reminder_state(), "periodic": now_iso()})

    # ------------------------------------------------------------ status decoration
    def decorate(self, status: dict[str, Any]) -> dict[str, Any]:
        """Add estimated levels to a printer status; hide the chips' ink warnings while estimating."""
        if not self.estimating or not status.get("configured"):
            return status
        out = dict(status)
        if self.settings.hide_printer_warnings:
            out["reasons"] = [r for r in status.get("reasons", [])
                              if not (str(r.get("base", "")).startswith("marker-supply") and r.get("severity") != "error")]
        tanks = self.tanks()
        out["ink"] = {"mode": "estimate", "tanks": tanks, "tracking": any(t["level_ml"] is not None for t in tanks)}
        return out
