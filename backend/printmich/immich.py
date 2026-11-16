"""Read-only Immich API client (write-back to an album/tag is optional and off by default)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

from .models import AssetSummary

log = logging.getLogger("printmich.immich")

# Permissions Printmich needs (all read-only) and the optional extras.
REQUIRED_PERMISSIONS = {
    "asset.read": "Search your library and read photo metadata",
    "asset.view": "Show thumbnails and previews in Printmich",
    "asset.download": "Download full-resolution originals for printing",
}
RECOMMENDED_PERMISSIONS = {
    "album.read": "Use albums as photo sources",
    "person.read": "Use people as photo sources",
    "tag.read": "Use tags as photo sources",
    "memory.read": "Use Immich memories as a source",
    "face.read": "Keep faces in frame when cropping",
}
WRITEBACK_PERMISSIONS = {
    "album.create": "Create the “Printed” album (optional write-back)",
    "albumAsset.create": "Add printed photos to that album (optional write-back)",
    "tag.create": "Create the “Printed” tag (optional write-back)",
    "tag.asset": "Tag printed photos (optional write-back)",
}


class ImmichError(Exception):
    def __init__(self, message: str, status: int | None = None, permission: str | None = None):
        super().__init__(message)
        self.status = status
        self.permission = permission


def normalize_base(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url:
        raise ImmichError("Immich URL is not set")
    if "://" not in url:
        url = "http://" + url
    if url.endswith("/api"):
        url = url[:-4]
    return url


class ImmichClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0):
        self.base = normalize_base(base_url)
        self.api = self.base + "/api"
        self.api_key = api_key.strip()
        self.timeout = timeout
        self._version: tuple[int, int, int] | None = None
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------ transport
    def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.api,
                headers={"x-api-key": self.api_key, "Accept": "application/json",
                         "User-Agent": "Printmich/1.0"},
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def _request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        try:
            r = await self._http().request(method, path, **kw)
        except httpx.ConnectError as e:
            raise ImmichError(f"Can't reach Immich at {self.base} — check the URL and that the server is up.") from e
        except httpx.TimeoutException as e:
            raise ImmichError("Immich did not respond in time.") from e
        except httpx.HTTPError as e:
            raise ImmichError(f"Immich request failed: {e}") from e
        if r.status_code >= 400:
            msg = ""
            permission = None
            try:
                body = r.json()
                msg = body.get("message") or body.get("error") or ""
                if isinstance(msg, list):
                    msg = "; ".join(map(str, msg))
            except Exception:
                msg = r.text[:200]
            if r.status_code == 401:
                raise ImmichError("Immich rejected the API key (401). Create a new key in Account Settings → "
                                  "API Keys.", 401)
            if r.status_code == 403:
                if "permission" in msg.lower():
                    permission = msg.rsplit(" ", 1)[-1].strip("()'\"") or None
                raise ImmichError(f"Immich denied access: {msg or 'forbidden'}", 403, permission)
            raise ImmichError(f"Immich error {r.status_code} on {path}: {msg}", r.status_code)
        return r

    async def _json(self, method: str, path: str, **kw: Any) -> Any:
        r = await self._request(method, path, **kw)
        if not r.content:
            return None
        return r.json()

    # ------------------------------------------------------------ server
    async def version(self) -> tuple[int, int, int]:
        if self._version is None:
            v = await self._json("GET", "/server/version")
            self._version = (int(v.get("major", 0)), int(v.get("minor", 0)), int(v.get("patch", 0)))
        return self._version

    async def version_at_least(self, major: int, minor: int = 0) -> bool:
        try:
            v = await self.version()
        except ImmichError:
            return True
        return (v[0], v[1]) >= (major, minor)

    async def api_key_info(self) -> dict[str, Any] | None:
        try:
            return await self._json("GET", "/api-keys/me")
        except ImmichError as e:
            if e.status in (404, 400):
                return None
            raise

    async def me(self) -> dict[str, Any] | None:
        try:
            return await self._json("GET", "/users/me")
        except ImmichError as e:
            if e.status == 403:
                return None
            raise

    async def features(self) -> dict[str, Any]:
        try:
            return await self._json("GET", "/server/features") or {}
        except ImmichError:
            return {}

    async def check(self) -> dict[str, Any]:
        """Connection test used by the settings page."""
        v = await self.version()
        key = await self.api_key_info()
        perms: list[str] | None = key.get("permissions") if key else None
        everything = bool(perms) and "all" in perms

        def has(p: str) -> bool | None:
            if perms is None:
                return None
            return everything or p in perms

        probe_ok = True
        probe_error = None
        try:
            await self._json("POST", "/search/metadata", json={"size": 1, "type": "IMAGE"})
        except ImmichError as e:
            probe_ok = False
            probe_error = str(e)
        user = await self.me() if has("user.read") is not False else None
        feats = await self.features()
        return {
            "ok": probe_ok,
            "error": probe_error,
            "version": ".".join(map(str, v)),
            "key_name": key.get("name") if key else None,
            "full_access": everything,
            "read_only": None if perms is None else (not everything and all(
                p.endswith((".read", ".view", ".download", ".statistics")) for p in perms)),
            "user": {"name": user.get("name"), "email": user.get("email")} if user else None,
            "permissions": {
                "required": [{"name": k, "why": d, "granted": has(k)} for k, d in REQUIRED_PERMISSIONS.items()],
                "recommended": [{"name": k, "why": d, "granted": has(k)} for k, d in RECOMMENDED_PERMISSIONS.items()],
                "writeback": [{"name": k, "why": d, "granted": has(k)} for k, d in WRITEBACK_PERMISSIONS.items()],
            },
            "features": {"smart_search": feats.get("smartSearch", True),
                         "facial_recognition": feats.get("facialRecognition", True)},
            "album_search": (v[0], v[1]) >= (1, 135),
        }

    # ------------------------------------------------------------ search
    @staticmethod
    def _filters(**kw: Any) -> dict[str, Any]:
        body: dict[str, Any] = {"type": "IMAGE"}
        for k, v in kw.items():
            if v is None or v == [] or v == "":
                continue
            body[k] = v
        return body

    async def random(self, size: int = 50, **filters: Any) -> list[dict[str, Any]]:
        body = self._filters(size=size, withExif=True, withPeople=True, **filters)
        data = await self._json("POST", "/search/random", json=body)
        return data if isinstance(data, list) else []

    async def metadata(self, page: int = 1, size: int = 100, **filters: Any) -> tuple[list[dict[str, Any]], int | None]:
        body = self._filters(page=page, size=size, withExif=True, withPeople=True, **filters)
        data = await self._json("POST", "/search/metadata", json=body)
        assets = (data or {}).get("assets", {})
        nxt = assets.get("nextPage")
        return assets.get("items", []), int(nxt) if nxt else None

    async def smart(self, query: str, page: int = 1, size: int = 100, **filters: Any) -> tuple[list[dict[str, Any]], int | None]:
        body = self._filters(query=query, page=page, size=size, withExif=True, **filters)
        data = await self._json("POST", "/search/smart", json=body)
        assets = (data or {}).get("assets", {})
        nxt = assets.get("nextPage")
        return assets.get("items", []), int(nxt) if nxt else None

    # ------------------------------------------------------------ collections
    async def albums(self) -> list[dict[str, Any]]:
        own = await self._json("GET", "/albums") or []
        shared: list[dict[str, Any]] = []
        seen, out = set(), []
        for a in own + shared:
            if a.get("id") in seen:
                continue
            seen.add(a.get("id"))
            out.append({
                "id": a.get("id"), "name": a.get("albumName"), "count": a.get("assetCount", 0),
                "thumbnail": a.get("albumThumbnailAssetId"), "shared": bool(a.get("shared")),
                "start": a.get("startDate"), "end": a.get("endDate"),
            })
        out.sort(key=lambda a: (a["name"] or "").lower())
        return out

    async def album_assets(self, album_id: str) -> list[dict[str, Any]]:
        """Album contents via search (Immich ≥ 1.135) with a fallback for older servers."""
        if await self.version_at_least(1, 135):
            items: list[dict[str, Any]] = []
            page: int | None = 1
            while page and len(items) < 5000:
                batch, page = await self.metadata(page=page, size=500, albumIds=[album_id])
                items.extend(batch)
            return items
        data = await self._json("GET", f"/albums/{album_id}")
        return [a for a in (data or {}).get("assets", []) if a.get("type") == "IMAGE"]

    async def people(self, with_hidden: bool = False) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page = 1
        while page and page < 50:
            data = await self._json("GET", "/people", params={"withHidden": str(with_hidden).lower(),
                                                              "page": page, "size": 500})
            for p in (data or {}).get("people", []):
                out.append({"id": p.get("id"), "name": p.get("name") or "", "favorite": p.get("isFavorite", False),
                            "hidden": p.get("isHidden", False)})
            page = page + 1 if (data or {}).get("hasNextPage") else 0
        out.sort(key=lambda p: (not p["favorite"], p["name"] == "", p["name"].lower()))
        return out

    async def tags(self) -> list[dict[str, Any]]:
        data = await self._json("GET", "/tags") or []
        return sorted([{"id": t.get("id"), "name": t.get("value") or t.get("name"), "color": t.get("color")}
                       for t in data], key=lambda t: (t["name"] or "").lower())

    async def memories(self, for_date: str) -> list[dict[str, Any]]:
        try:
            data = await self._json("GET", "/memories", params={"for": for_date})
        except ImmichError as e:
            if e.status == 404:
                return []
            raise
        out = []
        for m in data or []:
            for a in m.get("assets", []):
                if a.get("type") == "IMAGE":
                    out.append(a)
        return out

    # ------------------------------------------------------------ assets
    async def asset(self, asset_id: str) -> dict[str, Any]:
        return await self._json("GET", f"/assets/{asset_id}")

    async def faces(self, asset_id: str) -> list[dict[str, Any]]:
        try:
            return await self._json("GET", "/faces", params={"id": asset_id}) or []
        except ImmichError as e:
            if e.status in (403, 404, 400):
                return []
            raise

    async def thumbnail(self, asset_id: str, size: str = "preview") -> tuple[bytes, str]:
        r = await self._request("GET", f"/assets/{asset_id}/thumbnail", params={"size": size})
        return r.content, r.headers.get("content-type", "image/jpeg")

    async def person_thumbnail(self, person_id: str) -> tuple[bytes, str]:
        r = await self._request("GET", f"/people/{person_id}/thumbnail")
        return r.content, r.headers.get("content-type", "image/jpeg")

    async def download_original(self, asset_id: str, dest: Path, edited: bool = False) -> str:
        params = {"edited": "true"} if edited else None
        try:
            async with self._http().stream("GET", f"/assets/{asset_id}/original", params=params,
                                           timeout=httpx.Timeout(300.0, connect=10.0)) as r:
                if r.status_code >= 400:
                    await r.aread()
                    if r.status_code == 403:
                        raise ImmichError("API key lacks asset.download — falling back to the full-size preview",
                                          403, "asset.download")
                    raise ImmichError(f"Download failed ({r.status_code})", r.status_code)
                with open(dest, "wb") as fh:
                    async for chunk in r.aiter_bytes(1 << 20):
                        fh.write(chunk)
                return r.headers.get("content-type", "application/octet-stream")
        except httpx.HTTPError as e:
            raise ImmichError(f"Download failed: {e}") from e

    # ------------------------------------------------------------ optional write-back
    async def ensure_album(self, name: str) -> str:
        for a in await self._json("GET", "/albums", params={"name": name}) or []:
            if a.get("albumName") == name:
                return a["id"]
        data = await self._json("POST", "/albums", json={"albumName": name,
                                                         "description": "Photos printed by Printmich"})
        return data["id"]

    async def add_to_album(self, album_id: str, asset_ids: list[str]) -> None:
        await self._json("PUT", f"/albums/{album_id}/assets", json={"ids": asset_ids})

    async def tag_assets(self, tag_name: str, asset_ids: list[str]) -> None:
        tags = await self._json("PUT", "/tags", json={"tags": [tag_name]}) or []
        if tags:
            await self._json("PUT", f"/tags/{tags[-1]['id']}/assets", json={"ids": asset_ids})


# ---------------------------------------------------------------- helpers

def oriented_dims(asset: dict[str, Any]) -> tuple[int | None, int | None]:
    exif = asset.get("exifInfo") or {}
    w = exif.get("exifImageWidth") or asset.get("width")
    h = exif.get("exifImageHeight") or asset.get("height")
    orient = str(exif.get("orientation") or "")
    if exif.get("exifImageWidth") and orient in ("5", "6", "7", "8", "90", "-90", "270"):
        w, h = h, w
    return (int(w) if w else None, int(h) if h else None)


def summarize(asset: dict[str, Any]) -> AssetSummary:
    exif = asset.get("exifInfo") or {}
    w, h = oriented_dims(asset)
    people = [p.get("name") for p in asset.get("people") or [] if p.get("name")]
    owner = (asset.get("owner") or {}).get("name")
    return AssetSummary(
        id=asset["id"],
        filename=asset.get("originalFileName") or "",
        taken_at=exif.get("dateTimeOriginal") or asset.get("localDateTime") or asset.get("fileCreatedAt"),
        width=w, height=h,
        mime=asset.get("originalMimeType") or "",
        favorite=bool(asset.get("isFavorite")),
        rating=exif.get("rating"),
        city=exif.get("city"), state=exif.get("state"), country=exif.get("country"),
        description=exif.get("description") or None,
        make=exif.get("make"), model=exif.get("model"), lens=exif.get("lensModel"),
        f_number=exif.get("fNumber"), exposure_time=exif.get("exposureTime"), iso=exif.get("iso"),
        focal_length=exif.get("focalLength"), latitude=exif.get("latitude"), longitude=exif.get("longitude"),
        people=people, thumbhash=asset.get("thumbhash"), edited=bool(asset.get("isEdited")), owner=owner,
    )
