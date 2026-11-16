from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from .. import __version__
from ..auth import COOKIE, MAX_AGE, hash_password, hash_token
from ..models import Paper, Preset, Schedule, Settings
from ..scheduler import describe_timing
from ..store import now_utc, parse_iso
from .common import get_app, print_out

router = APIRouter()


@router.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "version": __version__}


# ---------------------------------------------------------------- auth

class LoginBody(BaseModel):
    password: str


@router.get("/api/auth/status")
async def auth_status(request: Request, app=Depends(get_app)) -> dict[str, Any]:
    authed = app.auth.valid_session(request.cookies.get(COOKIE)) or not app.auth.enabled
    return {"enabled": app.auth.enabled, "authenticated": authed, "env_password": bool(app.cfg.password)}


@router.post("/api/auth/login")
async def login(body: LoginBody, response: Response, request: Request, app=Depends(get_app)) -> dict[str, Any]:
    if not app.auth.enabled:
        return {"ok": True}
    if not app.auth.check_password(body.password):
        raise HTTPException(401, "Wrong password")
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(COOKIE, app.auth.make_session(), max_age=MAX_AGE, httponly=True, samesite="lax",
                        secure=secure)
    return {"ok": True}


@router.post("/api/auth/logout")
async def logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(COOKIE)
    return {"ok": True}


class PasswordBody(BaseModel):
    password: str = ""


@router.post("/api/auth/password")
async def set_password(body: PasswordBody, request: Request, app=Depends(get_app)) -> dict[str, Any]:
    if app.cfg.password:
        raise HTTPException(400, "The password is set by the PRINTMICH_PASSWORD environment variable.")
    if app.auth.enabled and not app.auth.valid_session(request.cookies.get(COOKIE)):
        raise HTTPException(401, "Log in first")
    app.store.update_settings(password_hash=hash_password(body.password) if body.password else "")
    return {"enabled": bool(body.password)}


@router.post("/api/auth/token")
async def make_token(app=Depends(get_app)) -> dict[str, Any]:
    token = "pm_" + secrets.token_urlsafe(24)
    app.store.update_settings(api_token_hash=hash_token(token))
    return {"token": token}


@router.delete("/api/auth/token")
async def revoke_token(app=Depends(get_app)) -> dict[str, Any]:
    app.store.update_settings(api_token_hash="")
    return {"ok": True}


# ---------------------------------------------------------------- settings

def settings_out(app: Any) -> dict[str, Any]:
    s = app.store.settings()
    key = s.immich_api_key
    data = s.model_dump(exclude={"password_hash", "api_token_hash", "session_secret", "immich_api_key"})
    data["immich_api_key_set"] = bool(key)
    data["immich_api_key_hint"] = ("…" + key[-4:]) if len(key) >= 8 else ("set" if key else "")
    data["env_locked"] = sorted(app.cfg.env_locked)
    data["api_token_set"] = bool(s.api_token_hash)
    data["password_set"] = app.auth.enabled
    data["timezone"] = app.cfg.timezone
    data["public_url"] = app.cfg.public_url
    data["demo"] = app.cfg.demo
    return data


@router.get("/api/settings")
async def get_settings(app=Depends(get_app)) -> dict[str, Any]:
    return settings_out(app)


ALLOWED_SETTINGS = {"immich_url", "immich_api_key", "immich_public_url", "printer_uri", "printer_name", "units",
                    "theme", "notifications", "writeback", "cost", "ink", "retry_minutes", "retry_hours", "onboarded",
                    "wall_title"}


@router.put("/api/settings")
async def put_settings(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    changes = {k: v for k, v in body.items() if k in ALLOWED_SETTINGS}
    for locked in app.cfg.env_locked:
        changes.pop(locked, None)
    if "immich_api_key" in changes and (not changes["immich_api_key"] or str(changes["immich_api_key"]).startswith("…")):
        changes.pop("immich_api_key")
    if "printer_uri" in changes:
        from ..ipp.client import normalize_uri
        uri = (changes["printer_uri"] or "").strip()
        changes["printer_uri"] = normalize_uri(uri) if uri else ""
        app.printer.invalidate()
    app.store.update_settings(**changes)
    return settings_out(app)


@router.post("/api/settings/test-notification")
async def test_notification(body: dict[str, Any] = Body(default={}), app=Depends(get_app)) -> dict[str, Any]:
    urls = body.get("urls")
    ok = await app.notifier.send("Printmich test", "Notifications are working. 🖨️", kind="success",
                                 urls=urls, force=True)
    if not ok:
        raise HTTPException(400, "Couldn't deliver the test notification — check the Apprise URLs.")
    return {"ok": True}


@router.get("/api/settings/export")
async def export_settings(app=Depends(get_app)) -> dict[str, Any]:
    s = app.store.raw_settings().model_dump(exclude={"password_hash", "api_token_hash", "session_secret",
                                                     "immich_api_key"})
    return {
        "printmich": __version__, "exported_at": now_utc().isoformat(),
        "settings": s,
        "presets": [p.model_dump() for p in app.store.presets()],
        "papers": [p.model_dump() for p in app.store.papers() if p.customized or not p.builtin],
        "schedules": [x.model_dump(exclude={"next_run_at", "last_run_at"}) for x in app.store.schedules()],
    }


@router.post("/api/settings/import")
async def import_settings(body: dict[str, Any] = Body(...), app=Depends(get_app)) -> dict[str, Any]:
    n = {"presets": 0, "papers": 0, "schedules": 0}
    for p in body.get("presets", []):
        app.store.save_preset(Preset(**p))
        n["presets"] += 1
    for p in body.get("papers", []):
        app.store.save_paper(Paper(**p))
        n["papers"] += 1
    for s in body.get("schedules", []):
        sch = Schedule(**s)
        app.store.save_schedule(sch)
        if sch.enabled:
            app.scheduler.reschedule(sch)
        n["schedules"] += 1
    if isinstance(body.get("settings"), dict):
        safe = {k: v for k, v in body["settings"].items() if k in ALLOWED_SETTINGS and k != "immich_api_key"}
        app.store.update_settings(**safe)
    return {"imported": n}


# ---------------------------------------------------------------- overview

@router.get("/api/status")
async def status(app=Depends(get_app)) -> dict[str, Any]:
    s: Settings = app.store.settings()
    return {
        "version": __version__, "immich": app.immich_configured, "printer": bool(s.printer_uri),
        "virtual_printer": app.printer.is_virtual() if s.printer_uri else False,
        "onboarded": s.onboarded, "demo": app.cfg.demo, "timezone": app.cfg.timezone, "units": s.units,
        "theme": s.theme, "wall_title": s.wall_title,
        "immich_public_url": s.immich_public_url or s.immich_url,
    }


@router.get("/api/events")
async def events(limit: int = 50, app=Depends(get_app)) -> list[dict[str, Any]]:
    return app.store.events(min(limit, 500))


@router.get("/api/stats")
async def stats(app=Depends(get_app)) -> dict[str, Any]:
    return app.store.stats()


@router.get("/api/dashboard")
async def dashboard(app=Depends(get_app)) -> dict[str, Any]:
    store = app.store
    schedules = []
    upcoming = None
    for s in store.schedules():
        pick = store.active_pick(s.id)
        item = {"id": s.id, "name": s.name, "enabled": s.enabled, "next_run_at": s.next_run_at,
                "timing_text": describe_timing(s), "approval": s.approval.mode, "preset_id": s.preset_id,
                "preset_name": (store.preset(s.preset_id).name if store.preset(s.preset_id) else None),
                "pick": pick}
        schedules.append(item)
        if s.enabled and s.next_run_at:
            if upcoming is None or (parse_iso(s.next_run_at) or now_utc()) < (parse_iso(upcoming["next_run_at"]) or now_utc()):
                upcoming = item
    recent, _ = store.prints(limit=12)
    queue = [print_out(app, r) for r in store.active_prints()]
    printer = await app.printer.status()
    st = store.settings()
    checklist = [
        {"key": "immich", "label": "Connect Immich", "done": app.immich_configured},
        {"key": "printer", "label": "Connect your printer", "done": bool(st.printer_uri)},
        {"key": "preset", "label": "Choose your paper & preset", "done": bool(store.presets())},
        {"key": "schedule", "label": "Turn on a schedule", "done": any(s.enabled for s in store.schedules())},
    ]
    return {
        "upcoming": upcoming, "schedules": schedules, "queue": queue,
        "recent": [print_out(app, r) for r in recent], "printer": printer, "stats": store.stats(),
        "events": store.events(15), "checklist": checklist,
    }
