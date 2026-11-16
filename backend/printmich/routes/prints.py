from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse

from ..models import Preset
from .common import get_app, not_found, print_out

router = APIRouter(prefix="/api/prints")


@router.get("")
async def list_prints(offset: int = 0, limit: int = 60, year: int | None = None, paper: str | None = None,
                      q: str | None = None, status: str | None = None, include_hidden: bool = False,
                      include_tests: bool = False, app=Depends(get_app)) -> dict[str, Any]:
    statuses = [s for s in (status or "").split(",") if s] or None
    rows, total = app.store.prints(limit=min(limit, 200), offset=offset, statuses=statuses,
                                   include_hidden=include_hidden, include_tests=include_tests, year=year,
                                   paper_id=paper, q=q)
    return {"items": [print_out(app, r) for r in rows], "total": total}


@router.get("/{print_id}")
async def get_print(print_id: str, app=Depends(get_app)) -> dict[str, Any]:
    row = app.store.print_row(print_id)
    if not row:
        raise not_found("Unknown print")
    return print_out(app, row)


@router.post("")
async def create_print(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    preset = Preset(**body["preset"]) if body.get("preset") else app.store.preset(body.get("preset_id", ""))
    if preset is None:
        raise not_found("Unknown preset")
    if body.get("copies"):
        preset.output.copies = max(1, min(99, int(body["copies"])))
    asset_id = body.get("asset_id")
    if not asset_id:
        raise HTTPException(400, "asset_id is required")
    focus = tuple(body["focus"]) if body.get("focus") else None
    pid = await app.prints.submit(asset_id=asset_id, preset=preset, source="manual", focus=focus)
    return {"id": pid}


@router.post("/{print_id}/reprint")
async def reprint(print_id: str, body: dict[str, Any] = Body(default={}), app=Depends(get_app)) -> dict[str, Any]:
    row = app.store.print_row(print_id)
    if not row or not row.get("asset_id"):
        raise not_found("Unknown print")
    preset = app.store.preset(body["preset_id"]) if body.get("preset_id") else Preset(**row["preset"])
    if preset is None:
        raise not_found("Unknown preset")
    focus = ((row.get("render") or {}).get("request") or {}).get("focus")
    pid = await app.prints.submit(asset_id=row["asset_id"], preset=preset, source="reprint",
                                  focus=tuple(focus) if focus else None, asset=row.get("asset"))
    return {"id": pid}


@router.post("/{print_id}/cancel")
async def cancel(print_id: str, app=Depends(get_app)) -> dict[str, Any]:
    return {"ok": await app.prints.cancel(print_id)}


@router.post("/{print_id}/release")
async def release(print_id: str, app=Depends(get_app)) -> dict[str, Any]:
    return {"ok": await app.prints.release(print_id)}


@router.patch("/{print_id}")
async def patch(print_id: str, body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    row = app.store.print_row(print_id)
    if not row:
        raise not_found("Unknown print")
    if "hidden" in body:
        app.store.update_print(print_id, hidden=int(bool(body["hidden"])))
    return print_out(app, app.store.print_row(print_id))


@router.delete("/{print_id}")
async def delete(print_id: str, app=Depends(get_app)) -> dict[str, Any]:
    row = app.store.print_row(print_id)
    if not row:
        raise not_found("Unknown print")
    if row["status"] in ("queued", "preparing", "rendering", "sending", "printing", "waiting", "held"):
        raise HTTPException(400, "Cancel the print before deleting it")
    app.store.delete_print(print_id)
    for suffix in ("thumb.jpg", "page.jpg"):
        (app.cfg.prints_dir / f"{print_id}.{suffix}").unlink(missing_ok=True)
    return {"ok": True}


@router.get("/{print_id}/thumb")
async def thumb(print_id: str, app=Depends(get_app)) -> FileResponse:
    p = app.cfg.prints_dir / f"{print_id}.thumb.jpg"
    if not p.exists():
        raise not_found()
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800, immutable"})


@router.get("/{print_id}/page")
async def page(print_id: str, app=Depends(get_app)) -> FileResponse:
    p = app.cfg.prints_dir / f"{print_id}.page.jpg"
    if not p.exists():
        raise not_found()
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800, immutable"})
