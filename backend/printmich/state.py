"""Application container wiring all services together."""
from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from .auth import Auth
from .config import AppConfig
from .db import Database
from .defaults import default_presets, default_schedule
from .immich import ImmichClient, ImmichError
from .notify import Notifier
from .picker import Picker
from .printer import PrinterService
from .printing import PrintManager
from .scheduler import Scheduler
from .store import Store

log = logging.getLogger("printmich")


class App:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        cfg.ensure_dirs()
        self.db = Database(cfg.db_path)
        self.store = Store(self.db, cfg)
        self.auth = Auth(self)
        self.printer = PrinterService(self)
        self.prints = PrintManager(self)
        self.picker = Picker(self)
        self.scheduler = Scheduler(self)
        self.notifier = Notifier(self)
        self._immich: ImmichClient | None = None
        self._immich_key: tuple[str, str] | None = None
        try:
            self.tz = ZoneInfo(cfg.timezone)
        except Exception:
            log.warning("unknown TZ '%s', using UTC", cfg.timezone)
            self.tz = ZoneInfo("UTC")
        self._seed()

    def _seed(self) -> None:
        if self.store.kv_get("seeded"):
            return
        for p in default_presets():
            self.store.save_preset(p)
        self.store.save_schedule(default_schedule())
        self.store.kv_set("seeded", True)
        self.store.log("info", "system", "Welcome to Printmich! Default presets and a Photo of the Day schedule "
                                         "were created.")

    def immich(self) -> ImmichClient:
        s = self.store.settings()
        if not s.immich_url or not s.immich_api_key:
            raise ImmichError("Immich isn't connected yet — add your server URL and API key in Settings.")
        key = (s.immich_url, s.immich_api_key)
        if self._immich is None or self._immich_key != key:
            self._immich = ImmichClient(s.immich_url, s.immich_api_key)
            self._immich_key = key
        return self._immich

    @property
    def immich_configured(self) -> bool:
        s = self.store.settings()
        return bool(s.immich_url and s.immich_api_key)

    async def start(self) -> None:
        for s in self.store.schedules():
            if s.enabled and not s.next_run_at:
                self.scheduler.reschedule(s)
        await self.prints.start()
        await self.scheduler.start()

    async def stop(self) -> None:
        await self.scheduler.stop()
        await self.prints.stop()
        if self._immich:
            await self._immich.close()
        self.db.close()
