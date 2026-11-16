from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from fastapi.responses import FileResponse

from ..ipp import JOB_STATES
from ..ipp.client import normalize_uri
from ..ipp.discovery import discover, probe
from ..ipp.virtual import VirtualPrinter
from .common import get_app, not_found

router = APIRouter(prefix="/api/printer")


def caps_out(caps: Any) -> dict[str, Any]:
    d = caps.to_dict()
    d["sizes"] = [asdict(s) for s in caps.sizes]
    d["markers"] = [asdict(m) for m in caps.markers]
    return d


@router.get("")
async def get_printer(app=Depends(get_app)) -> dict[str, Any]:
    if not app.printer.configured:
        return {"configured": False}
    out: dict[str, Any] = {"configured": True, "uri": app.printer.uri, "virtual": app.printer.is_virtual()}
    try:
        caps = await app.printer.capabilities()
        out["capabilities"] = caps_out(caps)
        out["status"] = await app.printer.status()
        out["icon"] = (app.cfg.cache_dir / "printer-icon.png").exists()
    except Exception as e:
        out["error"] = str(e)
        out["status"] = {"online": False, "state": "offline", "error": str(e)}
    return out


@router.get("/status")
async def printer_status(app=Depends(get_app)) -> dict[str, Any]:
    return await app.printer.status()


@router.post("/refresh")
async def refresh(app=Depends(get_app)) -> dict[str, Any]:
    app.printer.invalidate()
    return await get_printer(app)


@router.post("/test")
async def test(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    return await app.printer.test(body.get("uri", ""))


@router.put("")
async def set_printer(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    if "printer_uri" in app.cfg.env_locked:
        raise HTTPException(400, "The printer is set by the PRINTER_URI environment variable.")
    uri = (body.get("uri") or "").strip()
    uri = normalize_uri(uri) if uri else ""
    if uri:
        await app.printer.test(uri)
    app.store.update_settings(printer_uri=uri, printer_name=body.get("name", ""))
    app.printer.invalidate()
    return await get_printer(app)


@router.get("/discover")
async def do_discover() -> list[dict[str, Any]]:
    return await discover()


@router.post("/probe")
async def do_probe(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return await probe(body.get("address", ""))


@router.post("/identify")
async def identify(app=Depends(get_app)) -> dict[str, Any]:
    r = await app.printer.client().identify()
    return {"ok": r.ok, "status": r.status_text}


@router.get("/attributes")
async def attributes(app=Depends(get_app)) -> Response:
    data = await app.printer.raw_attributes()
    return Response(json.dumps(data, indent=2, default=str), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="printer-attributes.json"'})


@router.get("/jobs")
async def jobs(app=Depends(get_app)) -> dict[str, Any]:
    client = app.printer.client()

    def fmt(j: dict[str, list[Any]]) -> dict[str, Any]:
        st = (j.get("job-state") or [0])[0]
        return {"id": (j.get("job-id") or [None])[0], "name": (j.get("job-name") or [""])[0],
                "state": JOB_STATES.get(st, str(st)), "user": (j.get("job-originating-user-name") or [""])[0],
                "reasons": [str(r) for r in j.get("job-state-reasons", [])]}

    active = [fmt(j) for j in await client.get_jobs("not-completed")]
    try:
        done = [fmt(j) for j in await client.get_jobs("completed", 10)]
    except Exception:
        done = []
    return {"active": active, "completed": done}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: int, app=Depends(get_app)) -> dict[str, Any]:
    r = await app.printer.client().cancel_job(job_id)
    return {"ok": r.ok, "status": r.status_text}


@router.get("/icon")
async def icon(app=Depends(get_app)) -> FileResponse:
    p = app.cfg.cache_dir / "printer-icon.png"
    if not p.exists():
        raise not_found("No printer icon")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "max-age=3600"})


# ---------------------------------------------------------------- virtual printer helpers

def _virtual(app: Any) -> VirtualPrinter:
    client = app.printer.client("virtual://pro-310")
    assert isinstance(client, VirtualPrinter)
    return client


@router.get("/virtual/outputs")
async def virtual_outputs(app=Depends(get_app)) -> list[dict[str, Any]]:
    return _virtual(app).outputs()


@router.get("/virtual/outputs/{name}")
async def virtual_output(name: str, app=Depends(get_app)) -> FileResponse:
    if "/" in name or ".." in name:
        raise not_found()
    p = app.cfg.virtual_dir / name
    if not p.exists():
        raise not_found()
    return FileResponse(p)


@router.post("/virtual/load")
async def virtual_load(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    _virtual(app).set_loaded(body.get("size", "na_index-4x6_4x6in"), body.get("type", "photographic-satin"),
                             body.get("source", "top"))
    app.printer.invalidate()
    return {"ok": True}
