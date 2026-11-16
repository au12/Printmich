"""Notifications through Apprise (ntfy, Gotify, Discord, Telegram, Pushover, Home Assistant, email …)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .state import App

log = logging.getLogger("printmich.notify")


class Notifier:
    def __init__(self, app: App):
        self.app = app

    async def send(self, title: str, body: str, *, kind: str = "info", event: str = "print",
                   attach: Path | None = None, urls: list[str] | None = None, force: bool = False) -> bool:
        settings = self.app.store.settings().notifications
        targets = urls if urls is not None else settings.urls
        targets = [u.strip() for u in targets if u and u.strip()]
        if not targets:
            return False
        if not force:
            enabled = {"pick": settings.on_pick, "print": settings.on_print, "error": settings.on_error,
                       "supplies": settings.on_supplies}.get(event, True)
            if not enabled:
                return False
        try:
            import apprise
        except Exception:  # pragma: no cover
            log.warning("apprise not installed; notification dropped")
            return False
        ap = apprise.Apprise()
        for u in targets:
            ap.add(u)
        ntype = {"success": apprise.NotifyType.SUCCESS, "warning": apprise.NotifyType.WARNING,
                 "failure": apprise.NotifyType.FAILURE}.get(kind, apprise.NotifyType.INFO)
        att = None
        if attach is not None and settings.attach_preview and Path(attach).exists():
            att = apprise.AppriseAttachment()
            att.add(str(attach))
        if self.app.cfg.public_url:
            body = f"{body}\n{self.app.cfg.public_url.rstrip('/')}"
        try:
            ok = await ap.async_notify(body=body, title=title, notify_type=ntype, attach=att)
        except Exception as e:
            log.warning("notification failed: %s", e)
            return False
        if not ok:
            log.warning("one or more notification targets failed")
        return bool(ok)
