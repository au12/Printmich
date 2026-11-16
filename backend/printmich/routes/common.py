from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, Request

from ..ipp import media

if TYPE_CHECKING:  # pragma: no cover
    from ..state import App


def get_app(request: Request) -> App:
    return request.app.state.pm


def not_found(what: str = "Not found") -> HTTPException:
    return HTTPException(status_code=404, detail=what)


def print_out(app: App, row: dict[str, Any]) -> dict[str, Any]:
    r = row.get("render") or {}
    plan = r.get("plan") or {}
    preset = row.get("preset") or {}
    paper = row.get("paper") or {}
    out_settings = preset.get("output") or {}
    pid = row["id"]
    pdir = app.cfg.prints_dir
    has_thumb = (pdir / f"{pid}.thumb.jpg").exists()
    has_page = (pdir / f"{pid}.page.jpg").exists()
    return {
        "id": pid,
        "status": row["status"],
        "detail": row.get("status_detail") or "",
        "error": row.get("error"),
        "source": row.get("source"),
        "created_at": row.get("created_at"),
        "started_at": row.get("started_at"),
        "completed_at": row.get("completed_at"),
        "asset": row.get("asset"),
        "asset_id": row.get("asset_id"),
        "schedule_id": row.get("schedule_id"),
        "pick_id": row.get("pick_id"),
        "preset_id": row.get("preset_id"),
        "preset_name": row.get("preset_name"),
        "paper": {k: paper.get(k) for k in ("id", "name", "code", "finish", "brand", "tint")},
        "media_size": out_settings.get("media_size"),
        "size_label": plan.get("page_label") or media.label_for(out_settings.get("media_size")),
        "borderless": plan.get("borderless", (preset.get("layout") or {}).get("borderless")),
        "plan": plan,
        "geometry": r.get("geometry"),
        "effective_ppi": r.get("effective_ppi"),
        "crop": r.get("crop"),
        "notes": r.get("notes") or [],
        "copies": row.get("copies") or 1,
        "cost": row.get("cost"),
        "ipp_job_id": row.get("ipp_job_id"),
        "hidden": bool(row.get("hidden")),
        "thumb": f"/api/prints/{pid}/thumb" if has_thumb else None,
        "page": f"/api/prints/{pid}/page" if has_page else None,
        "thumb_w": row.get("thumb_w"),
        "thumb_h": row.get("thumb_h"),
    }
