from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or not v.strip():
        return default
    return v.strip()


def _env_bool(name: str, default: bool = False) -> bool:
    v = _env(name)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on")


@dataclass
class AppConfig:
    data_dir: Path
    static_dir: Path
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "info"
    timezone: str = "UTC"
    immich_url: str | None = None
    immich_api_key: str | None = None
    immich_public_url: str | None = None
    printer_uri: str | None = None
    password: str | None = None
    public_url: str | None = None
    demo: bool = False
    env_locked: set[str] = field(default_factory=set)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "printmich.db"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def prints_dir(self) -> Path:
        return self.data_dir / "prints"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def profiles_dir(self) -> Path:
        return self.data_dir / "profiles"

    @property
    def virtual_dir(self) -> Path:
        return self.data_dir / "virtual-printer"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.cache_dir, self.prints_dir, self.tmp_dir, self.profiles_dir,
                  self.virtual_dir, self.cache_dir / "thumbs"):
            d.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    pkg_dir = Path(__file__).resolve().parent
    default_static = pkg_dir.parent.parent / "frontend" / "dist"
    if not default_static.exists():
        default_static = Path("/app/static")
    cfg = AppConfig(
        data_dir=Path(_env("PRINTMICH_DATA", "/config") or "/config"),
        static_dir=Path(_env("PRINTMICH_STATIC", str(default_static)) or str(default_static)),
        host=_env("PRINTMICH_HOST", "0.0.0.0") or "0.0.0.0",
        port=int(_env("PRINTMICH_PORT", "8080") or "8080"),
        log_level=(_env("PRINTMICH_LOG_LEVEL", "info") or "info").lower(),
        timezone=_env("TZ", "UTC") or "UTC",
        immich_url=_env("IMMICH_URL"),
        immich_api_key=_env("IMMICH_API_KEY"),
        immich_public_url=_env("IMMICH_PUBLIC_URL"),
        printer_uri=_env("PRINTER_URI"),
        password=_env("PRINTMICH_PASSWORD"),
        public_url=_env("PRINTMICH_PUBLIC_URL"),
        demo=_env_bool("PRINTMICH_DEMO"),
    )
    for key, val in (("immich_url", cfg.immich_url), ("immich_api_key", cfg.immich_api_key),
                     ("immich_public_url", cfg.immich_public_url), ("printer_uri", cfg.printer_uri),
                     ("password", cfg.password)):
        if val:
            cfg.env_locked.add(key)
    return cfg
