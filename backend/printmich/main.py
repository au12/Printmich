"""FastAPI application factory and entrypoint."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from . import __version__
from .auth import COOKIE
from .config import AppConfig, load_config
from .imaging.render import RenderError
from .immich import ImmichError
from .ipp.client import IppError
from .picker import NoCandidates
from .routes import immich, ink, library, printer, prints, schedules, system, tools
from .state import App

log = logging.getLogger("printmich")


def create_app(cfg: AppConfig | None = None) -> FastAPI:
    cfg = cfg or load_config()
    logging.basicConfig(level=getattr(logging, cfg.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    # libvips narrates every operation at INFO; keep it to warnings unless debugging.
    for noisy in ("pyvips", "httpx", "httpx2", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.DEBUG if cfg.log_level.lower() == "debug" else logging.WARNING)

    @asynccontextmanager
    async def lifespan(fa: FastAPI) -> AsyncIterator[None]:
        pm = App(cfg)
        fa.state.pm = pm
        await pm.start()
        log.info("Printmich %s ready on port %s (data: %s)", __version__, cfg.port, cfg.data_dir)
        yield
        await pm.stop()

    app = FastAPI(title="Printmich", version=__version__, lifespan=lifespan, docs_url="/api/docs",
                  openapi_url="/api/openapi.json", redoc_url=None)

    @app.middleware("http")
    async def auth_guard(request: Request, call_next):  # type: ignore[no-untyped-def]
        pm: App | None = getattr(request.app.state, "pm", None)
        if pm is not None and not pm.auth.allowed(request.url.path, request.cookies.get(COOKIE),
                                                  request.headers.get("authorization"),
                                                  request.query_params.get("token")):
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        return await call_next(request)

    def handler(status: int, kind: str):  # type: ignore[no-untyped-def]
        async def _h(request: Request, exc: Exception) -> JSONResponse:
            return JSONResponse({"detail": str(exc), "kind": kind}, status_code=status)
        return _h

    app.add_exception_handler(ImmichError, handler(502, "immich"))
    app.add_exception_handler(IppError, handler(502, "printer"))
    app.add_exception_handler(RenderError, handler(422, "render"))
    app.add_exception_handler(NoCandidates, handler(404, "picker"))
    app.add_exception_handler(ValueError, handler(400, "value"))
    app.add_exception_handler(ValidationError, handler(422, "validation"))

    for r in (system.router, immich.router, printer.router, library.router, prints.router, schedules.router,
              tools.router, ink.router):
        app.include_router(r)

    static: Path = cfg.static_dir
    if static.exists():
        assets = static / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "Not found"}, status_code=404)  # type: ignore[return-value]
            candidate = (static / full_path).resolve()
            if full_path and candidate.is_file() and static.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(static / "index.html", headers={"Cache-Control": "no-cache"})
    else:
        log.warning("static UI not found at %s — API only", static)

    return app


def run() -> None:
    import uvicorn

    cfg = load_config()
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port, log_level=cfg.log_level, proxy_headers=True,
                forwarded_allow_ips="*")


if __name__ == "__main__":
    run()
