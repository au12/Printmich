"""Calibration tools: calibration chart, color-pattern prints, profiling targets and ICC uploads."""
from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Response, UploadFile

from ..imaging import icc
from ..imaging.testchart import pattern_variants
from ..models import Adjustments, Preset, new_id
from .common import get_app, not_found

router = APIRouter(prefix="/api/tools")


def _preset(app: Any, body: dict[str, Any]) -> Preset:
    preset = Preset(**body["preset"]) if body.get("preset") else app.store.preset(body.get("preset_id", ""))
    if preset is None:
        raise not_found("Unknown preset")
    if body.get("paper_id"):
        preset.output.paper_id = body["paper_id"]
    return preset


def _test(body: dict[str, Any], kind: str) -> dict[str, Any]:
    t: dict[str, Any] = {"kind": kind}
    if body.get("asset_id"):
        t["asset_id"] = body["asset_id"]
    if kind == "pattern":
        if not body.get("asset_id"):
            raise HTTPException(400, "Choose a photo for the color pattern")
        t["mode"] = body.get("mode", "color")
        t["step"] = int(body.get("step", 10))
        if isinstance(body.get("base"), dict):
            t["base"] = body["base"]
    return t


@router.post("/chart")
async def print_chart(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    preset = _preset(app, body)
    paper = app.store.paper(preset.output.paper_id)
    preset.name = f"Calibration chart, {paper.name}" if paper else "Calibration chart"
    pid = await app.prints.submit(asset_id=None, preset=preset, source="test", test=_test(body, "chart"), hidden=True)
    return {"id": pid}


@router.post("/pattern")
async def print_pattern(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    preset = _preset(app, body)
    paper = app.store.paper(preset.output.paper_id)
    t = _test(body, "pattern")
    preset.name = f"Color pattern, {paper.name}" if paper else "Color pattern"
    pid = await app.prints.submit(asset_id=None, preset=preset, source="test", test=t, hidden=True)
    base = (Adjustments(**t["base"]) if t.get("base") else paper.calibration.adjust) if paper else None
    tiles = [{"index": i + 1, "label": lbl, "adjust": adj.model_dump()}
             for i, (lbl, adj) in enumerate(pattern_variants(base, t["mode"], t["step"]))] if base else []
    return {"id": pid, "tiles": tiles}


@router.post("/preview")
async def preview(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> Response:
    preset = _preset(app, body)
    kind = body.get("kind", "chart")
    t = _test(body, kind)
    data, info = await app.prints.preview(None, preset, test=t, max_px=int(body.get("max_px", 1400)))
    if kind == "pattern":
        paper = app.store.paper(preset.output.paper_id)
        base = Adjustments(**t["base"]) if t.get("base") else paper.calibration.adjust
        info["tiles"] = [{"index": i + 1, "label": lbl, "adjust": adj.model_dump()}
                         for i, (lbl, adj) in enumerate(pattern_variants(base, t["mode"], t["step"]))]
    return Response(data, media_type="image/jpeg",
                    headers={"X-Printmich-Info": urllib.parse.quote(json.dumps(info, default=str)),
                             "Cache-Control": "no-store"})


@router.post("/target")
async def print_target(file: UploadFile = File(...), preset_id: str = Form(...), app=Depends(get_app)) -> dict[str, Any]:
    preset = app.store.preset(preset_id)
    if preset is None:
        raise not_found("Unknown preset")
    dest_dir = app.cfg.data_dir / "targets"
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", file.filename or "target.tif")[-80:]
    dest = dest_dir / f"{new_id()}-{name}"
    with open(dest, "wb") as fh:
        while chunk := await file.read(1 << 20):
            fh.write(chunk)
    preset = preset.model_copy(deep=True)
    preset.name = f"Profiling target, {name}"
    pid = await app.prints.submit(asset_id=None, preset=preset, source="test",
                                  test={"kind": "target", "path": str(dest)}, hidden=True)
    return {"id": pid}


# ---------------------------------------------------------------- ICC profiles

@router.get("/profiles")
async def profiles(app=Depends(get_app)) -> list[dict[str, Any]]:
    out = []
    for p in sorted(app.cfg.profiles_dir.glob("*.ic[cm]")):
        data = p.read_bytes()
        out.append({"name": p.name, "path": str(p), "description": icc.profile_description(data),
                    "space": icc.profile_color_space(data), "size": len(data)})
    return out


@router.post("/profiles")
async def upload_profile(file: UploadFile = File(...), app=Depends(get_app)) -> dict[str, Any]:
    data = await file.read()
    if len(data) < 132 or data[36:40] != b"acsp":
        raise HTTPException(400, "That doesn't look like an ICC profile")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", file.filename or "profile.icc")
    if not name.lower().endswith((".icc", ".icm")):
        name += ".icc"
    dest = app.cfg.profiles_dir / name
    dest.write_bytes(data)
    return {"name": name, "path": str(dest), "description": icc.profile_description(data),
            "space": icc.profile_color_space(data)}


@router.delete("/profiles/{name}")
async def delete_profile(name: str, app=Depends(get_app)) -> dict[str, Any]:
    if "/" in name or ".." in name:
        raise not_found()
    (app.cfg.profiles_dir / name).unlink(missing_ok=True)
    return {"ok": True}
