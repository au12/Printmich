"""Papers, presets and live print previews."""
from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Response

from ..ipp import media
from ..ipp.client import IppError
from ..models import Paper, Preset, new_id
from ..papers import BUILTIN_BY_ID, resolve_media_source, resolve_media_type
from .common import get_app, not_found

router = APIRouter(prefix="/api")


async def _caps(app: Any):
    try:
        if app.printer.configured:
            return await app.printer.capabilities()
    except IppError:
        pass
    return None


# ---------------------------------------------------------------- papers

def paper_out(p: Paper, caps: Any) -> dict[str, Any]:
    d = p.model_dump()
    if caps is not None:
        mt = resolve_media_type(p, caps.types, "auto")
        src = resolve_media_source(p, caps.source_keywords(), "auto")
        d["resolved"] = {"media_type": mt, "media_source": src,
                         "media_source_label": media.media_source_label(src) if src else None}
    else:
        d["resolved"] = None
    d["size_labels"] = {s: media.label_for(s) for s in p.sizes}
    return d


@router.get("/papers")
async def papers(app=Depends(get_app)) -> list[dict[str, Any]]:
    caps = await _caps(app)
    return [paper_out(p, caps) for p in app.store.papers()]


@router.put("/papers/{paper_id}")
async def save_paper(paper_id: str, body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    current = app.store.paper(paper_id)
    if not current:
        raise not_found("Unknown paper")
    data = {**current.model_dump(), **body, "id": paper_id}
    p = app.store.save_paper(Paper(**data))
    return paper_out(p, await _caps(app))


@router.post("/papers")
async def create_paper(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    base = app.store.paper(body.get("base_id") or "") or BUILTIN_BY_ID["canon-lu-101"]
    name = (body.get("name") or f"{base.name} (custom)").strip()
    pid = "custom-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] + "-" + new_id()[:4]
    data = {**base.model_dump(), **{k: v for k, v in body.items() if k != "base_id"}, "id": pid, "name": name,
            "builtin": False}
    p = app.store.save_paper(Paper(**data))
    return paper_out(p, await _caps(app))


@router.post("/papers/{paper_id}/reset")
async def reset_paper(paper_id: str, app=Depends(get_app)) -> dict[str, Any]:
    if paper_id not in BUILTIN_BY_ID:
        raise HTTPException(400, "Only built-in papers can be reset")
    app.store.reset_paper(paper_id)
    return paper_out(app.store.paper(paper_id), await _caps(app))


@router.delete("/papers/{paper_id}")
async def delete_paper(paper_id: str, app=Depends(get_app)) -> dict[str, Any]:
    if paper_id in BUILTIN_BY_ID:
        raise HTTPException(400, "Built-in papers can't be deleted (reset them instead)")
    used = [p.name for p in app.store.presets() if p.output.paper_id == paper_id]
    if used:
        raise HTTPException(400, f"Used by preset(s): {', '.join(used)}")
    app.store.reset_paper(paper_id)
    return {"ok": True}


# ---------------------------------------------------------------- presets

@router.get("/presets")
async def presets(app=Depends(get_app)) -> list[dict[str, Any]]:
    out = []
    for p in app.store.presets():
        d = p.model_dump()
        d["size_label"] = media.label_for(p.output.media_size)
        paper = app.store.paper(p.output.paper_id)
        d["paper_name"] = paper.name if paper else p.output.paper_id
        out.append(d)
    return out


@router.post("/presets")
async def create_preset(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    body = {k: v for k, v in body.items() if k not in ("id", "created_at", "updated_at")}
    p = Preset(**body)
    p.sort = len(app.store.presets())
    return app.store.save_preset(p).model_dump()


@router.put("/presets/{preset_id}")
async def update_preset(preset_id: str, body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    if not app.store.preset(preset_id):
        raise not_found("Unknown preset")
    p = Preset(**{**body, "id": preset_id})
    return app.store.save_preset(p).model_dump()


@router.post("/presets/{preset_id}/duplicate")
async def duplicate_preset(preset_id: str, app=Depends(get_app)) -> dict[str, Any]:
    p = app.store.preset(preset_id)
    if not p:
        raise not_found("Unknown preset")
    copy = p.model_copy(deep=True)
    copy.id = new_id()
    copy.name = f"{p.name} copy"
    copy.sort = len(app.store.presets())
    return app.store.save_preset(copy).model_dump()


@router.delete("/presets/{preset_id}")
async def delete_preset(preset_id: str, app=Depends(get_app)) -> dict[str, Any]:
    used = [s.name for s in app.store.schedules() if s.preset_id == preset_id]
    if used:
        raise HTTPException(400, f"Used by schedule(s): {', '.join(used)}")
    app.store.delete_preset(preset_id)
    return {"ok": True}


@router.post("/presets/plan")
async def plan_preset(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    preset = Preset(**body.get("preset", body))
    paper = app.store.paper(preset.output.paper_id) or BUILTIN_BY_ID["canon-pt-101"]
    caps = await app.prints._preview_caps()
    plan = app.printer.plan(preset, paper, caps, source_wide=body.get("source_wide"))
    out = plan.describe()
    out["paper"] = {"name": paper.name, "black_ink": paper.black_ink, "feeds": paper.feeds,
                    "calibration": paper.calibration.model_dump(), "recommended_margins":
                    paper.recommended_margins.model_dump() if paper.recommended_margins else None}
    out["virtual_caps"] = caps.virtual and not app.printer.is_virtual() if app.printer.configured else caps.virtual
    return out


@router.post("/presets/validate")
async def validate_preset(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    preset = Preset(**body.get("preset", body))
    paper = app.store.paper(preset.output.paper_id) or BUILTIN_BY_ID["canon-pt-101"]
    caps = await app.printer.capabilities()
    plan = app.printer.plan(preset, paper, caps)
    attrs = app.printer.job_attributes(plan, caps, preset)
    resp = await app.printer.client().validate_job(plan.document_format, attrs)
    return {"ok": resp.ok, "status": resp.status_text, "message": resp.message,
            "unsupported": sorted(resp.unsupported.keys()), "plan": plan.describe()}


@router.post("/render/preview")
async def render_preview(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> Response:
    preset = Preset(**body["preset"]) if body.get("preset") else app.store.preset(body.get("preset_id", ""))
    if preset is None:
        raise not_found("Unknown preset")
    focus = tuple(body["focus"]) if body.get("focus") else None
    max_px = int(min(2000, max(400, body.get("max_px", 1400))))
    data, info = await app.prints.preview(body.get("asset_id"), preset, focus=focus, max_px=max_px,
                                          test=body.get("test"))
    return Response(data, media_type="image/jpeg",
                    headers={"X-Printmich-Info": urllib.parse.quote(json.dumps(info, default=str)),
                             "Cache-Control": "no-store"})


@router.get("/sizes")
async def sizes(app=Depends(get_app)) -> list[dict[str, Any]]:
    caps = await app.prints._preview_caps()
    return [{"keyword": s.keyword, "label": s.label, "width_mm": s.width_mm, "height_mm": s.height_mm,
             "borderless": s.borderless} for s in caps.sizes]
