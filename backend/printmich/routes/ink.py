"""Estimated ink levels and the refill log (for refilled or third-party tanks)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from ..ink import INK_KEYS, INKS
from .common import get_app, not_found

router = APIRouter(prefix="/api/ink", tags=["ink"])


def _state(app: Any) -> dict[str, Any]:
    return {
        "settings": app.store.settings().ink.model_dump(),
        "tanks": app.ink.tanks(),
        "events": app.ink.events(80),
        "printer": app.printer.last_markers(),
        "inks": [{"ink": k, "name": n, "color": c} for k, n, c in INKS],
    }


@router.get("")
async def get_ink(app=Depends(get_app)) -> dict[str, Any]:
    return _state(app)


@router.post("/start")
async def start(body: dict[str, Any] = Body(default={}), app=Depends(get_app)) -> dict[str, Any]:
    """Start estimating from the printer's current readings ("printer") or from full tanks ("full")."""
    source = body.get("from", "printer")
    if source not in ("printer", "full"):
        raise HTTPException(400, "from must be 'printer' or 'full'")
    app.ink.start(source)
    return _state(app)


@router.post("/refill")
async def refill(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    """Log refilled tanks. Optional added_ml {ink: ml} (or grams from weighing) calibrates the estimate."""
    inks = [i for i in body.get("inks", []) if i in INK_KEYS]
    if not inks:
        raise HTTPException(400, "Choose at least one tank")
    added: dict[str, float] = {}
    for k, v in (body.get("added_ml") or {}).items():
        try:
            if k in INK_KEYS and v not in (None, "") and float(v) > 0:
                added[k] = float(v)
        except (TypeError, ValueError):
            raise HTTPException(400, f"Amount for {k} isn't a number") from None
    app.ink.refill(inks, added, str(body.get("note") or ""))
    return _state(app)


@router.post("/level")
async def set_level(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    try:
        app.ink.set_level(str(body.get("ink")), max(0.0, min(100.0, float(body.get("percent", 100)))))
    except (TypeError, ValueError) as e:
        raise HTTPException(400, str(e)) from None
    return _state(app)


@router.post("/checked")
async def checked(app=Depends(get_app)) -> dict[str, Any]:
    """'I checked the ink' — restarts the periodic reminder without logging a refill."""
    app.ink.acknowledge_check()
    return _state(app)


@router.delete("/events/{event_id}")
async def delete_event(event_id: int, app=Depends(get_app)) -> dict[str, Any]:
    if not app.store.delete_ink_event(event_id):
        raise not_found("No such entry")
    return _state(app)
