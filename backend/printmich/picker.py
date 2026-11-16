"""Photo picker: weighted sources → eligibility filters → smart scoring."""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import random
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .immich import ImmichClient, ImmichError, oriented_dims, summarize
from .ipp import media
from .models import Paper, PickFilters, Preset, Schedule, SourceSpec
from .store import now_utc

if TYPE_CHECKING:  # pragma: no cover
    from .state import App

log = logging.getLogger("printmich.picker")

SOURCE_LABELS = {
    "favorites": "Favorites", "album": "Album", "person": "People", "tag": "Tag", "on_this_day": "On this day",
    "memories": "Immich memories", "smart": "Smart search", "rating": "Star rating", "recent": "Recent",
    "random": "Whole library",
}
SCREENSHOT_RE = re.compile(r"(screen ?shot|screenrecording|bildschirmfoto|captura)", re.I)


class NoCandidates(Exception):
    pass


@dataclass
class PickResult:
    asset: dict[str, Any]
    score: dict[str, Any]
    source: str
    considered: int = 0
    notes: list[str] = field(default_factory=list)


def photo_area_mm(preset: Preset, paper_w: float, paper_h: float) -> tuple[float, float]:
    lay = preset.layout
    if lay.borderless:
        return paper_w, paper_h
    m = lay.margins
    return max(10.0, paper_w - m.left - m.right), max(10.0, paper_h - m.top - m.bottom)


def fit_metrics(w: int | None, h: int | None, area_w_mm: float, area_h_mm: float,
                orientation: str = "auto") -> tuple[float | None, float | None]:
    """Effective ppi and fraction of the photo cropped away when filling the area (auto-rotated)."""
    if not w or not h:
        return None, None
    aw, ah = area_w_mm, area_h_mm
    if orientation == "auto" and (w > h) != (aw > ah) and abs(aw - ah) > 0.5:
        aw, ah = ah, aw
    aspect = aw / ah
    if w / h > aspect:
        cw, ch = h * aspect, h
    else:
        cw, ch = w, w / aspect
    ppi = cw / (aw / 25.4)
    lost = 1.0 - (cw * ch) / (w * h)
    return ppi, lost


class Picker:
    def __init__(self, app: App):
        self.app = app

    # ------------------------------------------------------------ sources
    def _base_filters(self, f: PickFilters, src: SourceSpec) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if not f.include_archived:
            out["visibility"] = "timeline"
        if f.taken_after:
            out["takenAfter"] = f"{f.taken_after}T00:00:00.000Z" if len(f.taken_after) == 10 else f.taken_after
        if f.taken_before:
            out["takenBefore"] = f"{f.taken_before}T23:59:59.999Z" if len(f.taken_before) == 10 else f.taken_before
        if src.favorites_only:
            out["isFavorite"] = True
        return out

    async def fetch(self, im: ImmichClient, src: SourceSpec, f: PickFilters,
                    today: dt.date | None = None) -> tuple[list[dict[str, Any]], str]:
        base = self._base_filters(f, src)
        today = today or now_utc().astimezone(self.app.tz).date()
        kind = src.kind
        label = src.label or SOURCE_LABELS.get(kind, kind)
        if kind == "favorites":
            return await im.random(size=60, isFavorite=True, **{k: v for k, v in base.items() if k != "isFavorite"}), label
        if kind == "random":
            return await im.random(size=60, **base), label
        if kind == "album":
            if not src.album_ids:
                return [], label
            album = random.choice(src.album_ids)
            if await im.version_at_least(1, 135):
                items = await im.random(size=80, albumIds=[album], **base)
            else:
                items = await im.album_assets(album)
            return items, label
        if kind == "person":
            if not src.person_ids:
                return [], label
            ids = src.person_ids if src.person_mode == "all" else [random.choice(src.person_ids)]
            return await im.random(size=60, personIds=ids, **base), label
        if kind == "tag":
            if not src.tag_ids:
                return [], label
            return await im.random(size=60, tagIds=[random.choice(src.tag_ids)], **base), label
        if kind == "rating":
            results = await asyncio.gather(*[im.random(size=40, rating=r, **base)
                                             for r in range(src.min_rating, 6)], return_exceptions=True)
            items = [a for r in results if isinstance(r, list) for a in r]
            return items, label
        if kind == "recent":
            after = (now_utc() - dt.timedelta(days=src.recent_days)).isoformat()
            items, _ = await im.metadata(size=250, takenAfter=after, order="desc",
                                         **{k: v for k, v in base.items() if k != "takenAfter"})
            return items, label
        if kind == "smart":
            if not src.query.strip():
                return [], label
            items, _ = await im.smart(src.query.strip(), size=60, **base)
            return items, f"{label}: “{src.query.strip()}”"
        if kind == "memories":
            return await im.memories(today.isoformat()), label
        if kind == "on_this_day":
            return await self._on_this_day(im, today, src.window_days, base), label
        return [], label

    async def _on_this_day(self, im: ImmichClient, today: dt.date, window: int,
                           base: dict[str, Any]) -> list[dict[str, Any]]:
        async def year(back: int) -> list[dict[str, Any]]:
            try:
                center = today.replace(year=today.year - back)
            except ValueError:  # Feb 29
                center = today.replace(year=today.year - back, day=28)
            start = dt.datetime.combine(center - dt.timedelta(days=window), dt.time.min, dt.UTC)
            end = dt.datetime.combine(center + dt.timedelta(days=window), dt.time.max, dt.UTC)
            extra = {k: v for k, v in base.items() if k not in ("takenAfter", "takenBefore")}
            items, _ = await im.metadata(size=100, takenAfter=start.isoformat(), takenBefore=end.isoformat(), **extra)
            return items

        out: list[dict[str, Any]] = []
        for chunk in (range(1, 11), range(11, 21), range(21, 31)):
            res = await asyncio.gather(*[year(b) for b in chunk], return_exceptions=True)
            for r in res:
                if isinstance(r, list):
                    out.extend(r)
                elif isinstance(r, ImmichError) and r.status in (401, 403):
                    raise r
        return out

    # ------------------------------------------------------------ eligibility
    def eligible(self, assets: list[dict[str, Any]], f: PickFilters, preset: Preset, excluded: set[str],
                 page_mm: tuple[float, float]) -> tuple[list[dict[str, Any]], dict[str, int]]:
        aw, ah = photo_area_mm(preset, *page_mm)
        reasons: dict[str, int] = {}
        out, seen = [], set()

        def drop(why: str) -> None:
            reasons[why] = reasons.get(why, 0) + 1

        for a in assets:
            aid = a.get("id")
            if not aid or aid in seen:
                continue
            seen.add(aid)
            if a.get("type", "IMAGE") != "IMAGE" or a.get("isTrashed"):
                drop("not a photo")
                continue
            if aid in excluded:
                drop("printed recently / excluded")
                continue
            exif = a.get("exifInfo") or {}
            if f.exclude_screenshots:
                fn = a.get("originalFileName") or ""
                mime = a.get("originalMimeType") or ""
                if SCREENSHOT_RE.search(fn) or (not exif.get("make") and mime in ("image/png", "image/gif")):
                    drop("screenshot")
                    continue
            w, h = oriented_dims(a)
            if f.orientation != "any" and w and h:
                if (f.orientation == "landscape" and w <= h) or (f.orientation == "portrait" and h <= w):
                    drop("orientation")
                    continue
            ppi, lost = fit_metrics(w, h, aw, ah, preset.layout.orientation)
            if f.min_ppi and ppi is not None and ppi < f.min_ppi:
                drop("too low resolution")
                continue
            if f.require_people and not a.get("people"):
                drop("no people")
                continue
            a["_ppi"], a["_lost"] = ppi, lost
            out.append(a)
        return out, reasons

    async def excluded_ids(self, im: ImmichClient, f: PickFilters) -> set[str]:
        store = self.app.store
        if f.avoid_repeats_days < 0:
            ex = store.printed_asset_ids()
        elif f.avoid_repeats_days > 0:
            ex = store.printed_asset_ids(now_utc() - dt.timedelta(days=f.avoid_repeats_days))
        else:
            ex = set()
        for album in f.exclude_album_ids:
            try:
                ex |= {a["id"] for a in await im.album_assets(album)}
            except ImmichError as e:
                log.warning("could not read excluded album %s: %s", album, e)
        return ex

    # ------------------------------------------------------------ scoring
    async def score(self, im: ImmichClient, a: dict[str, Any]) -> dict[str, Any]:
        from .imaging.analyze import analyze

        q: dict[str, float] = {}
        try:
            data, _ = await im.thumbnail(a["id"], "preview")
            q = await asyncio.to_thread(analyze, data)
        except Exception as e:
            log.debug("analysis failed for %s: %s", a.get("id"), e)
        ppi, lost = a.get("_ppi"), a.get("_lost")
        rating = (a.get("exifInfo") or {}).get("rating")
        comp = {
            "sharpness": q.get("sharpness", 0.6),
            "exposure": q.get("exposure", 0.7),
            "framing": 1.0 - (lost or 0.0) if lost is not None else 0.75,
            "resolution": min(1.0, (ppi or 240) / 300.0),
            "favorite": 1.0 if a.get("isFavorite") else (rating / 5.0 if rating else 0.35),
            "people": 1.0 if a.get("people") else 0.5,
            "color": q.get("colorfulness", 0.5),
        }
        weights = {"sharpness": 0.26, "exposure": 0.18, "framing": 0.16, "resolution": 0.12, "favorite": 0.12,
                   "people": 0.08, "color": 0.08}
        total = sum(comp[k] * w for k, w in weights.items())
        return {"total": round(total, 3), "components": {k: round(v, 3) for k, v in comp.items()},
                "ppi": round(ppi) if ppi else None, "crop": round(lost, 3) if lost is not None else None,
                "analyzed": bool(q)}

    # ------------------------------------------------------------ main entry
    async def pick(self, schedule: Schedule, preset: Preset, paper: Paper,
                   extra_exclude: set[str] | None = None) -> PickResult:
        im = self.app.immich()
        f = schedule.filters
        sources = [s for s in schedule.sources if s.weight > 0] or [SourceSpec(kind="favorites")]
        dims = media.size_from_keyword(preset.output.media_size) or (101.6, 152.4)
        try:
            caps = self.app.printer._caps  # use cached sizes if available (exact printer dimensions)
            sz = caps.size(preset.output.media_size) if caps else None
            if sz:
                dims = (sz.width_mm, sz.height_mm)
        except Exception:
            pass
        excluded = await self.excluded_ids(im, f) | (extra_exclude or set())
        remaining = list(sources)
        reasons_total: dict[str, int] = {}
        considered = 0
        while remaining:
            src = random.choices(remaining, weights=[s.weight for s in remaining], k=1)[0]
            try:
                items, label = await self.fetch(im, src, f)
            except ImmichError as e:
                if e.status in (401, 403):
                    raise
                log.warning("source %s failed: %s", src.kind, e)
                remaining.remove(src)
                continue
            considered += len(items)
            elig, reasons = self.eligible(items, f, preset, excluded, dims)
            for k, v in reasons.items():
                reasons_total[k] = reasons_total.get(k, 0) + v
            if not elig:
                remaining.remove(src)
                continue
            pool = elig[:max(6, f.candidates * 2)] if src.kind == "smart" else elig
            sample = random.sample(pool, min(len(pool), f.candidates if f.smart_pick else 1))
            if f.smart_pick and len(sample) > 1:
                scored = await asyncio.gather(*[self.score(im, a) for a in sample])
                ranked = sorted(zip(sample, scored, strict=False), key=lambda t: t[1]["total"], reverse=True)
                if f.skip_blurry:
                    sharp = [t for t in ranked if t[1]["components"]["sharpness"] >= 0.2]
                    ranked = sharp or ranked
                best, sc = ranked[0]
                sc["runner_up"] = [{"id": t[0]["id"], "total": t[1]["total"]} for t in ranked[1:4]]
            else:
                best = sample[0]
                sc = await self.score(im, best) if f.smart_pick else {"total": None, "components": {}}
            sc["pool"] = len(elig)
            summary = summarize(best).model_dump()
            src_label = label
            if src.kind == "on_this_day" and summary.get("taken_at"):
                years = now_utc().year - int(summary["taken_at"][:4])
                src_label = f"On this day, {years} year{'s' if years != 1 else ''} ago" if years > 0 else label
            return PickResult(asset=summary, score=sc, source=src_label, considered=considered)
        detail = ", ".join(f"{v} {k}" for k, v in sorted(reasons_total.items(), key=lambda t: -t[1])) or "no results"
        raise NoCandidates(f"No eligible photos from this schedule's sources ({detail}).")
