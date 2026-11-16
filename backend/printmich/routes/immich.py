from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Response
from fastapi.responses import RedirectResponse

from ..immich import ImmichClient, summarize
from ..store import now_utc
from .common import get_app

router = APIRouter(prefix="/api/immich")

CACHE = {"Cache-Control": "private, max-age=86400"}


@router.post("/test")
async def test(body: dict[str, Any] = Body(default={}), app=Depends(get_app)) -> dict[str, Any]:
    s = app.store.settings()
    url = body.get("url") or s.immich_url
    key = body.get("api_key") or s.immich_api_key
    if not key or str(key).startswith("…"):
        key = s.immich_api_key
    client = ImmichClient(url, key)
    try:
        return await client.check()
    finally:
        await client.close()


@router.get("/albums")
async def albums(app=Depends(get_app)) -> list[dict[str, Any]]:
    return await app.immich().albums()


@router.get("/people")
async def people(app=Depends(get_app)) -> list[dict[str, Any]]:
    return await app.immich().people()


@router.get("/tags")
async def tags(app=Depends(get_app)) -> list[dict[str, Any]]:
    return await app.immich().tags()


@router.get("/browse")
async def browse(source: str = "favorites", page: int = 1, id: str | None = None, q: str | None = None,
                 rating: int = 5, app=Depends(get_app)) -> dict[str, Any]:
    im = app.immich()
    size = 72
    nxt: int | None = None
    base = {"visibility": "timeline"}
    if source == "favorites":
        items, nxt = await im.metadata(page=page, size=size, isFavorite=True, order="desc", **base)
    elif source == "recent":
        items, nxt = await im.metadata(page=page, size=size, order="desc", **base)
    elif source == "album" and id:
        if await im.version_at_least(1, 135):
            items, nxt = await im.metadata(page=page, size=size, albumIds=[id], order="desc")
        else:
            all_items = await im.album_assets(id)
            items = all_items[(page - 1) * size: page * size]
            nxt = page + 1 if len(all_items) > page * size else None
    elif source == "person" and id:
        items, nxt = await im.metadata(page=page, size=size, personIds=[id], order="desc", **base)
    elif source == "tag" and id:
        items, nxt = await im.metadata(page=page, size=size, tagIds=[id], order="desc", **base)
    elif source == "rating":
        items, nxt = await im.metadata(page=page, size=size, rating=rating, order="desc", **base)
    elif source == "search" and q:
        items, nxt = await im.smart(q, page=page, size=size, **base)
    elif source == "on_this_day":
        today = now_utc().astimezone(app.tz).date()
        items = await app.picker._on_this_day(im, today, 3, base) if page == 1 else []
        items.sort(key=lambda a: a.get("localDateTime") or "", reverse=True)
    elif source == "memories":
        items = await im.memories(now_utc().astimezone(app.tz).date().isoformat()) if page == 1 else []
    elif source == "random":
        items = await im.random(size=size, **base)
        nxt = page + 1
    else:
        items = []
    printed = app.store.printed_asset_ids()
    out = []
    for a in items:
        if a.get("type", "IMAGE") != "IMAGE":
            continue
        s = summarize(a).model_dump()
        s["printed"] = a["id"] in printed
        out.append(s)
    return {"items": out, "next_page": nxt}


@router.get("/assets/{asset_id}")
async def asset(asset_id: str, app=Depends(get_app)) -> dict[str, Any]:
    raw = await app.immich().asset(asset_id)
    s = summarize(raw).model_dump()
    s["printed_count"] = len([1 for r in app.store.db.query(
        "SELECT id FROM prints WHERE asset_id = ? AND status = 'completed'", (asset_id,))])
    return s


@router.get("/assets/{asset_id}/thumbnail")
async def thumbnail(asset_id: str, size: str = Query("thumbnail", pattern="^(thumbnail|preview|fullsize)$"),
                    app=Depends(get_app)) -> Response:
    if size == "preview":
        data = await app.prints.immich_preview(asset_id)
        return Response(data, media_type="image/jpeg", headers=CACHE)
    data, ctype = await app.immich().thumbnail(asset_id, size)
    return Response(data, media_type=ctype, headers=CACHE)


@router.get("/people/{person_id}/thumbnail")
async def person_thumb(person_id: str, app=Depends(get_app)) -> Response:
    data, ctype = await app.immich().person_thumbnail(person_id)
    return Response(data, media_type=ctype, headers=CACHE)


@router.get("/link/{asset_id}")
async def link(asset_id: str, app=Depends(get_app)) -> RedirectResponse:
    s = app.store.settings()
    base = (s.immich_public_url or s.immich_url or "").rstrip("/")
    if base.endswith("/api"):
        base = base[:-4]
    return RedirectResponse(f"{base}/photos/{asset_id}")



