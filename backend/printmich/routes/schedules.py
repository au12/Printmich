from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from ..models import Schedule, Timing
from ..scheduler import describe_timing, next_runs
from ..store import now_utc, parse_iso
from .common import get_app, not_found, print_out

router = APIRouter(prefix="/api")


def schedule_out(app: Any, s: Schedule) -> dict[str, Any]:
    d = s.model_dump()
    d["timing_text"] = describe_timing(s)
    d["upcoming_runs"] = [r.isoformat() for r in next_runs(s, now_utc(), app.tz, 3)] if s.enabled else []
    d["pick"] = app.store.active_pick(s.id)
    preset = app.store.preset(s.preset_id)
    d["preset_name"] = preset.name if preset else None
    rows = app.store.db.query("SELECT * FROM prints WHERE schedule_id = ? ORDER BY created_at DESC LIMIT 1", (s.id,))
    d["last_print"] = print_out(app, app.store._print_row(rows[0])) if rows else None
    d["print_count"] = app.store.db.scalar("SELECT COUNT(*) FROM prints WHERE schedule_id = ? AND status = 'completed'",
                                           (s.id,))
    return d


@router.get("/schedules")
async def schedules(app=Depends(get_app)) -> list[dict[str, Any]]:
    return [schedule_out(app, s) for s in app.store.schedules()]


@router.get("/schedules/{schedule_id}")
async def get_schedule(schedule_id: str, app=Depends(get_app)) -> dict[str, Any]:
    s = app.store.schedule(schedule_id)
    if not s:
        raise not_found("Unknown schedule")
    return schedule_out(app, s)


def _save(app: Any, s: Schedule) -> dict[str, Any]:
    if s.preset_id and not app.store.preset(s.preset_id):
        raise HTTPException(400, "Choose a preset for this schedule")
    if s.timing.frequency == "cron":
        from croniter import croniter
        if not croniter.is_valid(s.timing.cron):
            raise HTTPException(400, "That cron expression isn't valid")
    old = app.store.schedule(s.id)
    if s.enabled:
        runs = next_runs(s, now_utc(), app.tz)
        s.next_run_at = runs[0].isoformat(timespec="seconds") if runs else None
    else:
        s.next_run_at = None
    if old:
        s.last_run_at = old.last_run_at
        if old.next_run_at != s.next_run_at:
            app.store.expire_picks(s.id, ("pending",))
    app.store.save_schedule(s)
    return schedule_out(app, app.store.schedule(s.id))


@router.post("/schedules")
async def create(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    body = {k: v for k, v in body.items() if k not in ("id", "next_run_at", "last_run_at")}
    return _save(app, Schedule(**body))


@router.put("/schedules/{schedule_id}")
async def update(schedule_id: str, body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    if not app.store.schedule(schedule_id):
        raise not_found("Unknown schedule")
    return _save(app, Schedule(**{**body, "id": schedule_id}))


@router.delete("/schedules/{schedule_id}")
async def delete(schedule_id: str, app=Depends(get_app)) -> dict[str, Any]:
    app.store.delete_schedule(schedule_id)
    return {"ok": True}


@router.post("/schedules/preview-times")
async def preview_times(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    s = Schedule(timing=Timing(**body.get("timing", {})))
    try:
        runs = next_runs(s, now_utc(), app.tz, 5)
    except Exception:
        runs = []
    return {"text": describe_timing(s), "runs": [r.isoformat() for r in runs], "timezone": app.cfg.timezone}


@router.post("/schedules/{schedule_id}/pick")
async def repick(schedule_id: str, app=Depends(get_app)) -> dict[str, Any]:
    s = app.store.schedule(schedule_id)
    if not s:
        raise not_found("Unknown schedule")
    if not s.next_run_at:
        runs = next_runs(s, now_utc(), app.tz)
        s.next_run_at = runs[0].isoformat(timespec="seconds") if runs else None
    current = app.store.active_pick(s.id)
    exclude = {current["asset_id"]} if current else set()
    pick = await app.scheduler.make_pick(s, notify=False, exclude=exclude)
    if pick is None:
        raise HTTPException(404, "Couldn't find an eligible photo — check the schedule's sources and filters "
                                 "(Activity has details).")
    return pick


@router.post("/schedules/{schedule_id}/run")
async def run_now(schedule_id: str, app=Depends(get_app)) -> dict[str, Any]:
    s = app.store.schedule(schedule_id)
    if not s:
        raise not_found("Unknown schedule")
    pid = await app.scheduler.run_now(s)
    if not pid:
        raise HTTPException(404, "Couldn't find an eligible photo to print.")
    return {"print_id": pid}


@router.post("/schedules/{schedule_id}/skip")
async def skip(schedule_id: str, app=Depends(get_app)) -> dict[str, Any]:
    s = app.store.schedule(schedule_id)
    if not s:
        raise not_found("Unknown schedule")
    pick = app.store.active_pick(s.id)
    if pick:
        app.store.update_pick(pick["id"], status="skipped")
    elif s.enabled and s.next_run_at:
        nxt = parse_iso(s.next_run_at) or now_utc()
        runs = next_runs(s, nxt + dt.timedelta(seconds=30), app.tz)
        app.store.set_schedule_times(s.id, runs[0].isoformat(timespec="seconds") if runs else None)
    app.store.log("info", "schedule", f"{s.name}: next print skipped.")
    return schedule_out(app, app.store.schedule(s.id))


# ---------------------------------------------------------------- picks

def _pick(app: Any, pick_id: str) -> dict[str, Any]:
    p = app.store.pick(pick_id)
    if not p:
        raise not_found("Unknown pick")
    return p


@router.post("/picks/{pick_id}/approve")
async def approve(pick_id: str, app=Depends(get_app)) -> dict[str, Any]:
    _pick(app, pick_id)
    app.store.update_pick(pick_id, status="approved")
    return app.store.pick(pick_id)


@router.post("/picks/{pick_id}/skip")
async def skip_pick(pick_id: str, app=Depends(get_app)) -> dict[str, Any]:
    _pick(app, pick_id)
    app.store.update_pick(pick_id, status="skipped")
    return app.store.pick(pick_id)


@router.post("/picks/{pick_id}/unskip")
async def unskip_pick(pick_id: str, app=Depends(get_app)) -> dict[str, Any]:
    _pick(app, pick_id)
    app.store.update_pick(pick_id, status="pending", decided_at=None)
    return app.store.pick(pick_id)
