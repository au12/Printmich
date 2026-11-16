"""A small Immich-compatible API for development, demos and screenshots.

    MOCK_LIB=/tmp/demo/lib uvicorn mock_immich:app --port 2283 --app-dir dev

API key: "demo-key" (override with MOCK_KEY). Implements just the endpoints
Printmich uses, with realistic payload shapes from the Immich OpenAPI spec.
"""
from __future__ import annotations

import datetime as dt
import os
import random
import sys
import uuid
from pathlib import Path
from typing import Any

import pyvips
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

sys.path.insert(0, str(Path(__file__).parent))
from demo_photos import CAMERAS, PHOTOS

LIB = Path(os.environ.get("MOCK_LIB", "/tmp/demo/lib"))
API_KEY = os.environ.get("MOCK_KEY", "demo-key")
NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
PERMISSIONS = ["asset.read", "asset.view", "asset.download", "album.read", "person.read", "tag.read",
               "memory.read", "face.read"]
FACES = {"Biscuit": (0.33, 0.18, 0.72, 0.62), "Pepper": (0.3, 0.12, 0.72, 0.6), "Waffles": (0.28, 0.25, 0.74, 0.78)}


def uid(s: str) -> str:
    return str(uuid.uuid5(NS, s))


ASSETS: list[dict[str, Any]] = []
FILES: dict[str, Path] = {}
ALBUMS: dict[str, dict[str, Any]] = {}
PEOPLE: dict[str, dict[str, Any]] = {}

for i, (pid, fname, city, state, country, taken, fav, rating, albums, people, desc) in enumerate(PHOTOS):
    path = LIB / f"{pid}.jpg"
    if not path.exists():
        continue
    hdr = pyvips.Image.new_from_file(str(path))
    rng = random.Random(i)
    make, model, lens = CAMERAS[i % len(CAMERAS)] if not fname.startswith("DJI") else CAMERAS[4]
    if fname.startswith("IMG_"):
        make, model, lens = CAMERAS[1]
    aid = uid(pid)
    FILES[aid] = path
    person_objs = []
    for name in people:
        p = PEOPLE.setdefault(name, {"id": uid("person:" + name), "name": name, "isFavorite": True,
                                     "isHidden": False, "thumbnailPath": "", "assets": [], "face": FACES.get(name)})
        p["assets"].append(aid)
        person_objs.append({"id": p["id"], "name": name, "birthDate": None, "isHidden": False,
                            "thumbnailPath": "", "updatedAt": "2026-01-01T00:00:00.000Z"})
    for a in albums:
        alb = ALBUMS.setdefault(a, {"id": uid("album:" + a), "albumName": a, "assets": []})
        alb["assets"].append(aid)
    exif = {
        "make": make, "model": model, "lensModel": lens,
        "fNumber": rng.choice([1.8, 2.8, 4.0, 5.6, 8.0, 11.0]),
        "exposureTime": rng.choice(["1/60", "1/125", "1/250", "1/500", "1/1000", "1/30", "15"]),
        "iso": rng.choice([64, 100, 200, 400, 800, 3200]),
        "focalLength": rng.choice([16.0, 24.0, 35.0, 50.0, 70.0, 85.0, 6.765]),
        "dateTimeOriginal": taken + ".000Z", "exifImageWidth": hdr.width, "exifImageHeight": hdr.height,
        "orientation": "1", "city": city, "state": state, "country": country, "description": desc,
        "rating": rating or None, "latitude": None, "longitude": None, "timeZone": "America/New_York",
        "fileSizeInByte": path.stat().st_size,
    }
    ASSETS.append({
        "id": aid, "type": "IMAGE", "originalFileName": fname, "originalMimeType": "image/jpeg",
        "originalPath": f"/library/{fname}", "fileCreatedAt": taken + ".000Z", "fileModifiedAt": taken + ".000Z",
        "localDateTime": taken + ".000Z", "createdAt": taken + ".000Z", "updatedAt": taken + ".000Z",
        "isFavorite": bool(fav), "isArchived": False, "isTrashed": False, "isOffline": False, "isEdited": False,
        "visibility": "timeline", "width": hdr.width, "height": hdr.height, "thumbhash": None,
        "owner": {"id": uid("user"), "name": "Demo", "email": "demo@example.com"},
        "ownerId": uid("user"), "exifInfo": exif, "people": person_objs, "tags": [], "duration": "0:00:00.00000",
        "_taken": dt.datetime.fromisoformat(taken).replace(tzinfo=dt.UTC),
    })

BY_ID = {a["id"]: a for a in ASSETS}
_thumb_cache: dict[tuple[str, str], bytes] = {}

app = FastAPI(title="Mock Immich")


@app.middleware("http")
async def check_key(request: Request, call_next):  # type: ignore[no-untyped-def]
    open_paths = ("/api/server/version", "/api/server/ping", "/api/server/features", "/api/server/config")
    if request.url.path.startswith("/api") and request.url.path not in open_paths:
        if request.headers.get("x-api-key") != API_KEY:
            return JSONResponse({"message": "Invalid API key", "statusCode": 401}, status_code=401)
    return await call_next(request)


def public(a: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in a.items() if not k.startswith("_")}


def _date(v: str | None) -> dt.datetime | None:
    if not v:
        return None
    d = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=dt.UTC)


def matches(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if b.get("type") and a["type"] != b["type"]:
        return False
    if b.get("isFavorite") is not None and a["isFavorite"] != b["isFavorite"]:
        return False
    for alb in b.get("albumIds") or []:
        if not any(x["id"] == alb and a["id"] in x["assets"] for x in ALBUMS.values()):
            return False
    pids = [p["id"] for p in a["people"]]
    if any(p not in pids for p in b.get("personIds") or []):
        return False
    if b.get("tagIds"):
        return False
    if b.get("rating") is not None and a["exifInfo"].get("rating") != b["rating"]:
        return False
    after, before = _date(b.get("takenAfter")), _date(b.get("takenBefore"))
    if after and a["_taken"] < after:
        return False
    return not (before and a["_taken"] > before)


def page(items: list[dict[str, Any]], b: dict[str, Any]) -> dict[str, Any]:
    size = int(b.get("size") or 250)
    pg = int(b.get("page") or 1)
    chunk = items[(pg - 1) * size: pg * size]
    nxt = str(pg + 1) if len(items) > pg * size else None
    return {"albums": {"items": [], "count": 0, "total": 0, "facets": []},
            "assets": {"items": [public(a) for a in chunk], "count": len(chunk), "total": len(items),
                       "nextPage": nxt, "facets": []}}


@app.get("/api/server/version")
def version() -> dict[str, int]:
    return {"major": 2, "minor": 3, "patch": 1}


@app.get("/api/server/ping")
def ping() -> dict[str, str]:
    return {"res": "pong"}


@app.get("/api/server/features")
def features() -> dict[str, bool]:
    return {"smartSearch": True, "facialRecognition": True, "map": True}


@app.get("/api/api-keys/me")
def key_me() -> dict[str, Any]:
    return {"id": uid("key"), "name": "Printmich (read-only)", "permissions": PERMISSIONS,
            "createdAt": "2026-11-01T00:00:00.000Z", "updatedAt": "2026-11-01T00:00:00.000Z"}


@app.get("/api/users/me")
def me() -> JSONResponse:
    return JSONResponse({"message": "Missing required permission: user.read", "statusCode": 403}, status_code=403)


@app.post("/api/search/random")
def search_random(b: dict[str, Any] = Body(...)) -> list[dict[str, Any]]:
    items = [a for a in ASSETS if matches(a, b)]
    random.shuffle(items)
    return [public(a) for a in items[: int(b.get("size") or 250)]]


@app.post("/api/search/metadata")
def search_metadata(b: dict[str, Any] = Body(...)) -> dict[str, Any]:
    items = sorted([a for a in ASSETS if matches(a, b)], key=lambda a: a["_taken"],
                   reverse=(b.get("order", "desc") == "desc"))
    return page(items, b)


@app.post("/api/search/smart")
def search_smart(b: dict[str, Any] = Body(...)) -> dict[str, Any]:
    words = [w for w in (b.get("query") or "").lower().split() if len(w) > 2]
    scored = []
    for a in ASSETS:
        if not matches(a, {k: v for k, v in b.items() if k != "query"}):
            continue
        e = a["exifInfo"]
        albums = " ".join(x["albumName"] for x in ALBUMS.values() if a["id"] in x["assets"])
        hay = " ".join(str(v or "") for v in (e["description"], e["city"], e["state"], e["country"], albums,
                                               a["originalFileName"])).lower()
        score = sum(hay.count(w) for w in words) + random.random() * 0.1
        scored.append((score, a))
    scored.sort(key=lambda t: -t[0])
    return page([a for _, a in scored], b)


@app.get("/api/albums")
def albums() -> list[dict[str, Any]]:
    out = []
    for a in ALBUMS.values():
        dates = sorted(BY_ID[x]["_taken"] for x in a["assets"])
        out.append({"id": a["id"], "albumName": a["albumName"], "assetCount": len(a["assets"]),
                    "albumThumbnailAssetId": a["assets"][0], "shared": False, "hasSharedLink": False,
                    "startDate": dates[0].isoformat(), "endDate": dates[-1].isoformat(), "description": "",
                    "albumUsers": [], "isActivityEnabled": False})
    return out


@app.get("/api/albums/{album_id}")
def album(album_id: str) -> dict[str, Any]:
    for a in ALBUMS.values():
        if a["id"] == album_id:
            return {"id": a["id"], "albumName": a["albumName"], "assetCount": len(a["assets"]),
                    "assets": [public(BY_ID[x]) for x in a["assets"]]}
    raise HTTPException(404, "Album not found")


@app.get("/api/people")
def people() -> dict[str, Any]:
    return {"people": [{k: v for k, v in p.items() if k not in ("assets", "face")} for p in PEOPLE.values()],
            "total": len(PEOPLE), "hidden": 0, "hasNextPage": False}


@app.get("/api/people/{person_id}/thumbnail")
def person_thumb(person_id: str) -> Response:
    for p in PEOPLE.values():
        if p["id"] == person_id:
            img = pyvips.Image.new_from_file(str(FILES[p["assets"][0]]))
            x1, y1, x2, y2 = p["face"] or (0.25, 0.25, 0.75, 0.75)
            crop = img.crop(int(x1 * img.width), int(y1 * img.height), int((x2 - x1) * img.width),
                            int((y2 - y1) * img.height))
            return Response(crop.thumbnail_image(250, height=250, crop="centre").jpegsave_buffer(Q=85),
                            media_type="image/jpeg")
    raise HTTPException(404)


@app.get("/api/tags")
def tags() -> list[dict[str, Any]]:
    return []


@app.get("/api/memories")
def memories(request: Request) -> list[dict[str, Any]]:
    day = dt.date.fromisoformat(request.query_params.get("for") or dt.date.today().isoformat())
    groups: dict[int, list[dict[str, Any]]] = {}
    for a in ASSETS:
        t = a["_taken"].date()
        if t.year < day.year and (t.month, t.day) == (day.month, day.day):
            groups.setdefault(t.year, []).append(public(a))
    return [{"id": uid(f"mem:{y}"), "type": "on_this_day", "data": {"year": y}, "assets": items,
             "isSaved": False, "memoryAt": f"{y}-{day:%m-%d}T00:00:00.000Z"} for y, items in sorted(groups.items())]


@app.get("/api/assets/{asset_id}")
def asset(asset_id: str) -> dict[str, Any]:
    if asset_id not in BY_ID:
        raise HTTPException(404, "Asset not found")
    return public(BY_ID[asset_id])


@app.get("/api/faces")
def faces(id: str) -> list[dict[str, Any]]:
    a = BY_ID.get(id)
    if not a:
        return []
    out = []
    for p in a["people"]:
        face = PEOPLE[p["name"]].get("face")
        if not face:
            continue
        iw, ih = (1440, round(1440 * a["height"] / a["width"])) if a["width"] >= a["height"] else (
            round(1440 * a["width"] / a["height"]), 1440)
        out.append({"id": uid("face:" + id + p["name"]), "imageWidth": iw, "imageHeight": ih,
                    "boundingBoxX1": int(face[0] * iw), "boundingBoxY1": int(face[1] * ih),
                    "boundingBoxX2": int(face[2] * iw), "boundingBoxY2": int(face[3] * ih),
                    "person": {"id": p["id"], "name": p["name"]}, "sourceType": "machine-learning"})
    return out


@app.get("/api/assets/{asset_id}/thumbnail")
def thumbnail(asset_id: str, size: str = "thumbnail") -> Response:
    if asset_id not in FILES:
        raise HTTPException(404)
    if size in ("fullsize", "original"):
        return Response(FILES[asset_id].read_bytes(), media_type="image/jpeg")
    key = (asset_id, size)
    if key not in _thumb_cache:
        px = 1440 if size == "preview" else 250
        img = pyvips.Image.thumbnail(str(FILES[asset_id]), px, height=px)
        _thumb_cache[key] = img.jpegsave_buffer(Q=82 if size == "preview" else 75)
    return Response(_thumb_cache[key], media_type="image/jpeg")


@app.get("/api/assets/{asset_id}/original")
def original(asset_id: str) -> Response:
    if asset_id not in FILES:
        raise HTTPException(404)
    return Response(FILES[asset_id].read_bytes(), media_type="image/jpeg")
