"""Schedules: computes run times, prepares 'up next' picks, and fires prints."""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import TYPE_CHECKING, Any

from croniter import croniter

from .immich import ImmichError
from .models import Schedule, new_id
from .picker import NoCandidates
from .store import now_iso, now_utc, parse_iso

if TYPE_CHECKING:  # pragma: no cover
    from .state import App

log = logging.getLogger("printmich.scheduler")


def cron_for(s: Schedule) -> str | None:
    t = s.timing
    hh, mm = (int(x) for x in t.time.split(":"))
    if t.frequency == "daily":
        return f"{mm} {hh} * * *"
    if t.frequency == "weekly":
        days = sorted({(d + 1) % 7 for d in (t.weekdays or [5])})
        return f"{mm} {hh} * * {','.join(map(str, days))}"
    if t.frequency == "monthly":
        return f"{mm} {hh} {t.day_of_month} * *"
    if t.frequency == "cron":
        return t.cron.strip()
    return None


def next_runs(s: Schedule, after: dt.datetime, tz: dt.tzinfo, count: int = 1) -> list[dt.datetime]:
    local_after = after.astimezone(tz)
    expr = cron_for(s)
    out: list[dt.datetime] = []
    if expr:
        if not croniter.is_valid(expr):
            return []
        it = croniter(expr, local_after)
        for _ in range(count):
            out.append(it.get_next(dt.datetime).astimezone(dt.UTC))
        return out
    # every N days, anchored on the last run (or today)
    hh, mm = (int(x) for x in s.timing.time.split(":"))
    anchor = parse_iso(s.last_run_at) or after
    base = anchor.astimezone(tz).replace(hour=hh, minute=mm, second=0, microsecond=0)
    cand = base
    step = dt.timedelta(days=max(1, s.timing.every_n_days))
    while cand <= local_after:
        cand += step
    for _ in range(count):
        out.append(cand.astimezone(dt.UTC))
        cand += step
    return out


def describe_timing(s: Schedule) -> str:
    t = s.timing
    try:
        h, m = (int(x) for x in t.time.split(":"))
        clock = dt.time(h, m).strftime("%-I:%M %p")
    except ValueError:
        clock = t.time
    if t.frequency == "daily":
        return f"Every day at {clock}"
    if t.frequency == "weekly":
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        days = ", ".join(names[d] for d in sorted(set(t.weekdays or [5])))
        return f"Every {days} at {clock}"
    if t.frequency == "monthly":
        n = t.day_of_month
        suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"Monthly on the {n}{suffix} at {clock}"
    if t.frequency == "every_n_days":
        return f"Every {t.every_n_days} days at {clock}"
    return f"Cron schedule ({t.cron})"


class Scheduler:
    def __init__(self, app: App):
        self.app = app
        self.task: asyncio.Task[None] | None = None
        self._busy: set[str] = set()

    async def start(self) -> None:
        self.task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()

    async def _loop(self) -> None:
        await asyncio.sleep(3)
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("scheduler tick failed")
            await asyncio.sleep(20)

    def reschedule(self, s: Schedule) -> Schedule:
        runs = next_runs(s, now_utc(), self.app.tz)
        s.next_run_at = runs[0].isoformat(timespec="seconds") if runs else None
        self.app.store.set_schedule_times(s.id, s.next_run_at)
        return s

    async def tick(self) -> None:
        store = self.app.store
        now = now_utc()
        for s in store.schedules():
            if not s.enabled or s.id in self._busy:
                continue
            due = parse_iso(s.next_run_at)
            if due is None:
                self.reschedule(s)
                continue
            active = store.active_pick(s.id)
            if active and active.get("due_at") and active["due_at"] != s.next_run_at and active["status"] != "approved":
                store.update_pick(active["id"], status="expired")
                active = None
            lead = dt.timedelta(hours=s.approval.lead_hours)
            if s.approval.mode in ("preview", "manual") and not active and due - lead <= now < due:
                self._busy.add(s.id)
                try:
                    await self.make_pick(s, notify=True)
                finally:
                    self._busy.discard(s.id)
                continue
            if now >= due:
                self._busy.add(s.id)
                try:
                    late = now - due
                    if s.catch_up_hours and late > dt.timedelta(hours=s.catch_up_hours):
                        store.log("warning", "schedule", f"{s.name}: missed the {due:%b %-d %H:%M} UTC run "
                                  f"(Printmich was offline) — skipping to the next one.")
                        store.expire_picks(s.id)
                    else:
                        await self.fire(s, active)
                    runs = next_runs(s, max(now, due), self.app.tz)
                    store.set_schedule_times(s.id, runs[0].isoformat(timespec="seconds") if runs else None,
                                             due.isoformat(timespec="seconds"))
                finally:
                    self._busy.discard(s.id)

    async def make_pick(self, s: Schedule, *, notify: bool = True, exclude: set[str] | None = None,
                        status: str = "pending") -> dict[str, Any] | None:
        store = self.app.store
        preset = store.preset(s.preset_id)
        if not preset:
            store.log("error", "schedule", f"{s.name}: its preset no longer exists.")
            return None
        paper = store.paper(preset.output.paper_id)
        if not paper:
            store.log("error", "schedule", f"{s.name}: unknown paper {preset.output.paper_id}.")
            return None
        try:
            res = await self.app.picker.pick(s, preset, paper, exclude)
        except NoCandidates as e:
            store.log("warning", "schedule", f"{s.name}: {e}")
            if notify and s.notify.on_error:
                await self.app.notifier.send(f"Printmich: {s.name}", str(e), kind="warning", event="error")
            return None
        except ImmichError as e:
            store.log("error", "immich", f"{s.name}: {e}")
            if notify and s.notify.on_error:
                await self.app.notifier.send(f"Printmich: {s.name}", f"Couldn't pick a photo: {e}",
                                             kind="failure", event="error")
            return None
        active = store.active_pick(s.id)
        if active:
            store.update_pick(active["id"], status="swapped")
        pick = store.add_pick(new_id(), s.id, res.asset, {**res.score, "considered": res.considered},
                              res.source, s.next_run_at, status)
        store.log("info", "pick", f"{s.name}: picked {res.asset.get('filename')} from {res.source}",
                  {"pick_id": pick["id"], "schedule_id": s.id})
        if notify and s.notify.on_pick and s.approval.mode != "auto":
            when = parse_iso(s.next_run_at)
            when_txt = when.astimezone(self.app.tz).strftime("%a %-I:%M %p") if when else "soon"
            verb = "will print" if s.approval.mode == "preview" else "is waiting for your approval to print"
            attach = None
            try:
                data = await self.app.prints.immich_preview(res.asset["id"])
                attach = self.app.cfg.tmp_dir / f"pick-{pick['id']}.jpg"
                attach.write_bytes(data)
            except Exception:
                attach = None
            await self.app.notifier.send(f"Up next: {s.name}",
                                         f"{_label(res.asset)} {verb} {when_txt} ({res.source}).",
                                         kind="info", event="pick", attach=attach)
            if attach:
                attach.unlink(missing_ok=True)
        return pick

    async def fire(self, s: Schedule, active: dict[str, Any] | None) -> str | None:
        store = self.app.store
        mode = s.approval.mode
        pick = active
        if pick and pick["status"] == "skipped":
            store.update_pick(pick["id"], status="expired")
            store.log("info", "schedule", f"{s.name}: skipped this time.")
            return None
        if mode == "manual" and (not pick or pick["status"] != "approved"):
            if pick:
                store.update_pick(pick["id"], status="expired")
            store.log("info", "schedule", f"{s.name}: not approved in time — nothing printed.")
            return None
        if pick is None:
            pick = await self.make_pick(s, notify=False, status="approved")
            if pick is None:
                return None
        return await self.print_pick(s, pick)

    async def print_pick(self, s: Schedule, pick: dict[str, Any]) -> str | None:
        store = self.app.store
        preset = store.preset(s.preset_id)
        if not preset:
            return None
        store.update_pick(pick["id"], status="printing")
        pid = await self.app.prints.submit(asset_id=pick["asset_id"], preset=preset, source="schedule",
                                           schedule_id=s.id, pick_id=pick["id"], asset=pick["asset"],
                                           verify_paper=s.verify_paper)
        store.update_pick(pick["id"], print_id=pid)
        return pid

    async def run_now(self, s: Schedule) -> str | None:
        """Print the up-next pick (or a fresh one) immediately and consume this occurrence."""
        store = self.app.store
        active = store.active_pick(s.id)
        pick = active if active and active["status"] in ("pending", "approved") else None
        if pick is None:
            pick = await self.make_pick(s, notify=False, status="approved")
            if pick is None:
                return None
        pid = await self.print_pick(s, pick)
        if s.enabled:
            runs = next_runs(s, now_utc() + dt.timedelta(minutes=1), self.app.tz)
            if s.approval.mode != "auto" and runs:
                # the occurrence we just satisfied is the next one; move past it
                nxt = parse_iso(s.next_run_at)
                if nxt and nxt - now_utc() < dt.timedelta(hours=s.approval.lead_hours):
                    runs = next_runs(s, nxt, self.app.tz)
            store.set_schedule_times(s.id, runs[0].isoformat(timespec="seconds") if runs else None, now_iso())
        return pid


def _label(asset: dict[str, Any]) -> str:
    from .captions import place
    from .models import AssetSummary
    a = AssetSummary(**asset)
    p = place(a)
    d = (a.taken_at or "")[:10]
    return ", ".join(x for x in (p, d) if x) or a.filename or "A photo"
