"""Print queue: fetch → render → send → monitor, with history, retries and notifications."""
from __future__ import annotations

import asyncio
import collections
import logging
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyvips

from .captions import render_caption
from .imaging import icc
from .imaging.render import Face, RenderError, RenderSpec, load_source, plan_layout, render, thumbnail_jpeg
from .imaging.testchart import calibration_chart, chart_subtitle, color_pattern
from .immich import ImmichError, summarize
from .ipp.capabilities import Capabilities
from .ipp.client import IppError
from .models import Adjustments, AssetSummary, Margins, Paper, Preset, new_id
from .papers import BUILTIN_BY_ID
from .printer import OutputPlan
from .store import now_iso

if TYPE_CHECKING:  # pragma: no cover
    from .state import App

log = logging.getLogger("printmich.printing")

ACTIVE = ("queued", "preparing", "rendering", "sending", "printing", "waiting", "held")


class Canceled(Exception):
    pass


def build_spec(preset: Preset, paper: Paper, plan: OutputPlan, *, caption: str = "", faces: list[Face] | None = None,
               focus: tuple[float, float] | None = None, dpi: int | None = None, output: str | None = None,
               neutral: bool = False) -> RenderSpec:
    cal = paper.calibration
    adjust = Adjustments() if neutral else cal.adjust.plus(preset.adjust)
    sharpen = preset.output.sharpening if preset.output.sharpening != "paper" else cal.sharpening
    intent = plan.intent
    bpc = preset.color.bpc if preset.color.intent != "paper" else cal.bpc
    mode = preset.color.mode
    management = preset.color.management
    icc_path = None
    if management == "custom-icc" and preset.color.icc_profile:
        icc_path = preset.color.icc_profile
    layout = preset.layout.model_copy(deep=True)
    if plan.borderless != layout.borderless:
        layout.borderless = plan.borderless
    return RenderSpec(
        page_w_mm=plan.page_w_mm, page_h_mm=plan.page_h_mm, page_keyword=plan.page_keyword,
        dpi=dpi or plan.dpi, bit_depth=plan.bits, out_space=plan.space, management=management,
        icc_profile=icc_path, intent=intent, bpc=bpc, adjust=adjust, color_mode=mode,
        tone=preset.color.tone.resolved(), sharpening=sharpen, layout=layout, caption_text=caption,
        hw_margins=plan.hw_margins, focus=focus, faces=faces or [], media_type=plan.media_type or "",
        quality={"draft": 3, "normal": 4, "high": 5}[plan.quality],
        rendering_intent_kw=plan.rendering_intent_ipp or "",
        pages=1 if (plan.copies_ipp or plan.kind != "pwg") else plan.copies,
        output=output or plan.kind,
    )


class PrintManager:
    def __init__(self, app: App):
        self.app = app
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.worker: asyncio.Task[None] | None = None
        self.current: str | None = None
        self._album_id: str | None = None
        self._preview_cache: collections.OrderedDict[str, bytes] = collections.OrderedDict()
        self._faces_cache: collections.OrderedDict[str, list[Face]] = collections.OrderedDict()
        self._background: set[asyncio.Task] = set()

    def _spawn(self, coro: Any) -> asyncio.Task:
        """Run a coroutine in the background, keeping a reference so it isn't garbage-collected mid-flight."""
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        return task

    # ------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        for row in self.app.store.active_prints():
            if row["status"] == "printing" and row.get("ipp_job_id"):
                self._spawn(self._resume_monitor(row))
            elif row["status"] == "held":
                continue
            else:
                self.app.store.update_print(row["id"], status="queued", status_detail="Re-queued after restart")
                await self.queue.put(row["id"])
        self.worker = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self.worker:
            self.worker.cancel()

    async def _run(self) -> None:
        while True:
            pid = await self.queue.get()
            self.current = pid
            try:
                await self._process(pid)
            except Canceled:
                self._set(pid, "canceled", "Canceled")
            except Exception as e:
                log.exception("print %s failed", pid)
                self._fail(pid, str(e))
            finally:
                self.current = None
                shutil.rmtree(self.app.cfg.tmp_dir / pid, ignore_errors=True)

    # ------------------------------------------------------------ helpers
    def _set(self, pid: str, status: str, detail: str = "", **extra: Any) -> None:
        self.app.store.update_print(pid, status=status, status_detail=detail, **extra)

    def _check_canceled(self, pid: str) -> None:
        row = self.app.store.print_row(pid)
        if not row or row["status"] == "canceled":
            raise Canceled()

    def _fail(self, pid: str, message: str) -> None:
        row = self.app.store.print_row(pid)
        self._set(pid, "failed", message, error=message, completed_at=now_iso())
        name = self._title(row)
        self.app.store.log("error", "print", f"Print failed: {name} — {message}", {"print_id": pid})
        if row and row.get("source") != "test":
            self._spawn(self.app.notifier.send(
                "Printmich: print failed", f"{name}\n{message}", kind="failure", event="error"))

    @staticmethod
    def _title(row: dict[str, Any] | None) -> str:
        if not row:
            return "print"
        a = row.get("asset") or {}
        return a.get("filename") or row.get("preset_name") or "print"

    # ------------------------------------------------------------ submit
    async def submit(self, *, asset_id: str | None, preset: Preset, source: str = "manual",
                     schedule_id: str | None = None, pick_id: str | None = None,
                     focus: tuple[float, float] | None = None, test: dict[str, Any] | None = None,
                     hidden: bool = False, asset: dict[str, Any] | None = None, skip_verify: bool = False,
                     verify_paper: bool = False) -> str:
        paper = self.app.store.paper(preset.output.paper_id) or BUILTIN_BY_ID["canon-pt-101"]
        pid = new_id()
        self.app.store.add_print({
            "id": pid, "asset_id": asset_id, "schedule_id": schedule_id, "pick_id": pick_id,
            "preset_id": preset.id, "preset_name": preset.name, "preset": preset.model_dump(),
            "paper": paper.model_dump(), "asset": asset, "status": "queued", "status_detail": "Waiting in queue",
            "copies": preset.output.copies, "source": source, "hidden": int(hidden),
            "render": {"request": {"focus": list(focus) if focus else None, "test": test,
                                   "skip_verify": skip_verify, "verify_paper": verify_paper, "attempts": 0}},
        })
        await self.queue.put(pid)
        return pid

    async def cancel(self, pid: str) -> bool:
        row = self.app.store.print_row(pid)
        if not row or row["status"] not in ACTIVE:
            return False
        if row["status"] == "printing" and row.get("ipp_job_id"):
            try:
                await self.app.printer.client().cancel_job(int(row["ipp_job_id"]))
            except IppError as e:
                log.warning("cancel at printer failed: %s", e)
        self._set(pid, "canceled", "Canceled", completed_at=now_iso())
        return True

    async def release(self, pid: str) -> bool:
        """Print a held job anyway (overrides the paper and ink checks)."""
        row = self.app.store.print_row(pid)
        if not row or row["status"] != "held":
            return False
        render_meta = row.get("render") or {}
        req = render_meta.get("request") or {}
        req["skip_verify"] = True
        req["skip_ink"] = True
        render_meta["request"] = req
        self.app.store.update_print(pid, status="queued", status_detail="Released", render=render_meta)
        await self.queue.put(pid)
        return True

    # ------------------------------------------------------------ source acquisition
    async def immich_preview(self, asset_id: str) -> bytes:
        if asset_id in self._preview_cache:
            self._preview_cache.move_to_end(asset_id)
            return self._preview_cache[asset_id]
        data, _ = await self.app.immich().thumbnail(asset_id, "preview")
        self._preview_cache[asset_id] = data
        while len(self._preview_cache) > 24:
            self._preview_cache.popitem(last=False)
        return data

    async def faces(self, asset_id: str) -> list[Face]:
        if asset_id in self._faces_cache:
            return self._faces_cache[asset_id]
        out: list[Face] = []
        try:
            for f in await self.app.immich().faces(asset_id):
                iw, ih = f.get("imageWidth"), f.get("imageHeight")
                if iw and ih:
                    out.append(Face(f["boundingBoxX1"] / iw, f["boundingBoxY1"] / ih,
                                    f["boundingBoxX2"] / iw, f["boundingBoxY2"] / ih))
        except ImmichError:
            pass
        self._faces_cache[asset_id] = out
        while len(self._faces_cache) > 200:
            self._faces_cache.popitem(last=False)
        return out

    async def _fetch_original(self, asset_id: str, tmp: Path) -> tuple[AssetSummary, Path, list[str]]:
        im = self.app.immich()
        raw = await im.asset(asset_id)
        summary = summarize(raw)
        notes: list[str] = []
        dest = tmp / "original"
        try:
            await im.download_original(asset_id, dest, edited=bool(raw.get("isEdited")))
            ok = await asyncio.to_thread(_decodable, dest)
            if not ok:
                raise RenderError("original format can't be decoded")
        except (ImmichError, RenderError) as e:
            notes.append(f"Printed from Immich's full-size preview ({e}).")
            for size in ("fullsize", "preview"):
                try:
                    data, _ = await im.thumbnail(asset_id, size)
                    dest.write_bytes(data)
                    break
                except ImmichError:
                    continue
            else:
                raise RenderError("Couldn't download this photo from Immich.")
        return summary, dest, notes

    # ------------------------------------------------------------ process
    async def _process(self, pid: str) -> None:
        store = self.app.store
        row = store.print_row(pid)
        if not row or row["status"] == "canceled":
            return
        preset = Preset(**row["preset"])
        paper = Paper(**row["paper"])
        meta = row.get("render") or {}
        req = meta.get("request") or {}
        tmp = self.app.cfg.tmp_dir / pid
        tmp.mkdir(parents=True, exist_ok=True)

        self._set(pid, "preparing", "Checking the printer")
        try:
            caps = await self.app.printer.capabilities()
        except IppError as e:
            if await self._maybe_retry(pid, row, req, str(e)):
                return
            raise
        self._check_canceled(pid)

        notes: list[str] = []
        summary: AssetSummary | None = None
        faces: list[Face] = []
        test = req.get("test")
        neutral = False
        if test:
            src_img, preset, extra = await self._test_source(test, preset, paper, caps, tmp)
            neutral = test.get("kind") in ("pattern", "target")
            notes += extra
        else:
            self._set(pid, "preparing", "Downloading the original from Immich")
            summary, path, n = await self._fetch_original(row["asset_id"], tmp)
            notes += n
            if preset.layout.crop in ("smart", "faces"):
                faces = await self.faces(row["asset_id"])
            src_img = await asyncio.to_thread(load_source, path)
        self._check_canceled(pid)

        wide = _is_wide(src_img)
        plan = self.app.printer.plan(preset, paper, caps, source_wide=wide)
        caption = render_caption(preset.layout.caption.template, summary) if preset.layout.caption.enabled else ""
        focus = tuple(req["focus"]) if req.get("focus") else None
        spec = build_spec(preset, paper, plan, caption=caption, faces=faces, focus=focus, neutral=neutral)  # type: ignore[arg-type]
        if test and test.get("kind") == "target":
            spec.management = "passthrough"
            spec.sharpening = "off"
        self._set(pid, "rendering", f"Rendering {plan.page_label} at {plan.dpi} dpi")
        result = await asyncio.to_thread(render, src_img, spec, tmp, "page")
        self._check_canceled(pid)

        prints_dir = self.app.cfg.prints_dir
        page_path = prints_dir / f"{pid}.page.jpg"
        if result.preview:
            shutil.copyfile(result.preview, page_path)
        thumb_w = thumb_h = None
        try:
            if summary is not None:
                data = await self.immich_preview(summary.id)
                tb, thumb_w, thumb_h = await asyncio.to_thread(thumbnail_jpeg, data, 1280)
            else:
                tb, thumb_w, thumb_h = await asyncio.to_thread(thumbnail_jpeg, page_path, 1280)
            (prints_dir / f"{pid}.thumb.jpg").write_bytes(tb)
        except Exception as e:
            log.warning("thumbnail failed: %s", e)
        ink_ml: dict[str, float] | None = None
        if page_path.exists():
            try:
                ink_ml = await asyncio.to_thread(self.app.ink.estimate_print, page_path, plan.page_w_mm,
                                                 plan.page_h_mm, black_ink=paper.black_ink,
                                                 copies=max(1, preset.output.copies))
            except Exception as e:
                log.warning("ink estimate failed: %s", e)
        meta.update({"plan": plan.describe(), **result.meta(), "notes": notes + plan.warnings + result.warnings})
        store.update_print(pid, asset=summary.model_dump() if summary else None, render=meta, thumb_w=thumb_w,
                           thumb_h=thumb_h, started_at=now_iso(), ink=ink_ml,
                           cost=self._cost(paper, preset, result.geometry, ink_ml))

        # paper verification for scheduled prints
        if req.get("verify_paper") and not req.get("skip_verify"):
            status = await self.app.printer.status(max_age=0)
            check = self.app.printer.media_check(plan, status)
            if check and not check["ok"]:
                loaded = check["loaded"]
                msg = (f"Load {plan.page_label} {plan.media_type_label} in the {plan.media_source_label} "
                       f"(printer reports {loaded.get('size_label') or '?'} {loaded.get('type_label') or ''}).")
                self._set(pid, "held", msg)
                store.log("warning", "paper", msg, {"print_id": pid})
                await self.app.notifier.send("Printmich: paper check", msg, kind="warning", event="error")
                return

        # estimated ink: scheduled prints wait for a refill rather than run a tank dry
        if row.get("source") == "schedule" and not req.get("skip_ink"):
            reason = self.app.ink.hold_reason(ink_ml)
            if reason:
                self._set(pid, "held", reason)
                store.log("warning", "ink", reason, {"print_id": pid})
                await self.app.notifier.send("Printmich: print waiting for ink", reason, kind="warning",
                                             event="supplies")
                return

        self._set(pid, "sending", "Sending to the printer")
        attrs = self.app.printer.job_attributes(plan, caps, preset)
        client = self.app.printer.client()
        title = (summary.filename if summary else preset.name) or "photo"
        try:
            resp = await client.print_job(result.document, result.mime or plan.document_format, attrs,
                                          job_name=f"Printmich: {title}", document_name=title)
        except IppError as e:
            if await self._maybe_retry(pid, row, req, str(e)):
                return
            raise
        job_id = (resp.job.get("job-id") or [None])[0]
        if resp.status == 0x0001:
            meta.setdefault("notes", []).append("The printer substituted some settings it doesn't support.")
            store.update_print(pid, render=meta)
        self._set(pid, "printing", "Printing", ipp_job_id=job_id, printer=self.app.printer.uri)
        store.log("info", "print", f"Sent {title} ({plan.page_label}, {paper.name})", {"print_id": pid})
        # Follow the job in the background so a printer waiting for a hand doesn't hold up the queue.
        self._spawn(self._watch(pid, client, job_id))

    async def _watch(self, pid: str, client: Any, job_id: int | None) -> None:
        try:
            state, detail = await self._monitor(pid, client, job_id)
            await self._finish(pid, state, detail)
        except Exception as e:
            log.exception("watching print %s failed", pid)
            self._fail(pid, str(e))

    async def _maybe_retry(self, pid: str, row: dict[str, Any], req: dict[str, Any], error: str) -> bool:
        """Scheduled prints wait for an offline printer; manual prints fail fast."""
        if row.get("source") != "schedule":
            return False
        settings = self.app.store.settings()
        attempts = int(req.get("attempts", 0)) + 1
        max_attempts = max(1, settings.retry_hours * 60 // max(1, settings.retry_minutes))
        if attempts > max_attempts:
            return False
        req["attempts"] = attempts
        meta = (self.app.store.print_row(pid) or {}).get("render") or {}
        meta["request"] = req
        when = time.strftime("%H:%M", time.localtime(time.time() + settings.retry_minutes * 60))
        self._set(pid, "waiting", f"Printer unavailable — retrying at {when} ({error})", render=meta)
        if attempts == 1:
            await self.app.notifier.send("Printmich: printer unavailable",
                                         f"{error}\nI'll keep retrying for {settings.retry_hours} h.",
                                         kind="warning", event="error")

        async def later() -> None:
            await asyncio.sleep(settings.retry_minutes * 60)
            cur = self.app.store.print_row(pid)
            if cur and cur["status"] == "waiting":
                await self.queue.put(pid)

        self._spawn(later())
        return True

    async def _monitor(self, pid: str, client: Any, job_id: int | None) -> tuple[str, str]:
        """Follow a job until it finishes. A job stopped at the printer (ink out, no paper, jam) is kept
        alive for up to three days and the user is told what to do; printing resumes on its own."""
        if job_id is None:
            return "completed", "Sent (the printer didn't report a job id)"
        started = time.time()
        busy = 0.0  # seconds spent printing normally; times out after 45 minutes
        failures = 0
        last = ""
        notified = ""
        virtual = self.app.printer.is_virtual()
        while busy < 45 * 60 and time.time() - started < 72 * 3600:
            interval = 1.5 if virtual else 4 if time.time() - started < 600 else 15
            await asyncio.sleep(interval)
            row = self.app.store.print_row(pid)
            if row and row["status"] == "canceled":
                return "canceled", "Canceled"
            try:
                job = await client.get_job(int(job_id))
                failures = 0
            except IppError:
                failures += 1
                busy += interval
                if failures >= 4:
                    st = await self.app.printer.status(max_age=0)
                    if st.get("state") == "idle":
                        return "completed", "Printed"
                continue
            state = (job.get("job-state") or [0])[0]
            reasons = [str(r) for r in job.get("job-state-reasons", []) if str(r) != "none"]
            if state == 9:
                return "completed", "Printed"
            if state == 8:
                return "failed", "The printer aborted the job" + (f" ({', '.join(reasons)})" if reasons else "")
            if state == 7:
                return "canceled", "Canceled at the printer"
            st = await self.app.printer.status(max_age=6)
            alerts = [r for r in st.get("reasons", []) if r.get("severity") == "error"]
            stuck = state == 6 or st.get("state") == "stopped" or (state in (3, 4) and bool(alerts))
            if stuck:
                a = alerts[0] if alerts else None
                detail = (f"Waiting at the printer: {a['text']}. {a.get('hint', '')}".strip() if a
                          else "Waiting at the printer: check the printer's screen.")
                if detail != notified:
                    notified = detail
                    row = self.app.store.print_row(pid)
                    self.app.store.log("warning", "printer", detail, {"print_id": pid})
                    await self.app.notifier.send("Printmich: printer needs attention",
                                                 f"{self._title(row)}\n{detail}\nIt will finish printing once the "
                                                 "printer is ready.", kind="warning", event="error")
            else:
                busy += interval
                msgs = [r["text"] for r in st.get("reasons", []) if r.get("severity") == "warning"]
                detail = msgs[0] if msgs else ("Printing" if state == 5 else "Queued at the printer")
            if detail != last:
                self._set(pid, "printing", detail)
                last = detail
        return "failed", "Timed out waiting for the printer to finish"

    async def _resume_monitor(self, row: dict[str, Any]) -> None:
        try:
            state, detail = await self._monitor(row["id"], self.app.printer.client(), int(row["ipp_job_id"]))
            await self._finish(row["id"], state, detail)
        except Exception as e:
            self._fail(row["id"], str(e))

    async def _finish(self, pid: str, state: str, detail: str) -> None:
        store = self.app.store
        row = store.print_row(pid) or {}
        if state == "completed":
            store.update_print(pid, status="completed", status_detail=detail, completed_at=now_iso())
            if row.get("pick_id"):
                store.update_pick(row["pick_id"], status="printed", print_id=pid)
            if row.get("source") != "test":
                name = _describe_asset(row.get("asset"))
                store.log("success", "print", f"Printed {name}", {"print_id": pid})
                await self.app.notifier.send(
                    "Printmich: printed", f"{name}\n{row.get('preset_name', '')}", kind="success", event="print",
                    attach=self.app.cfg.prints_dir / f"{pid}.page.jpg")
                await self._writeback(row)
            if row.get("ink"):
                await self.app.ink.check(force=True)
        elif state == "canceled":
            store.update_print(pid, status="canceled", status_detail=detail, completed_at=now_iso())
        else:
            self._fail(pid, detail)

    async def _writeback(self, row: dict[str, Any]) -> None:
        wb = self.app.store.settings().writeback
        aid = row.get("asset_id")
        if not aid or not (wb.album_enabled or wb.tag_enabled):
            return
        im = self.app.immich()
        try:
            if wb.album_enabled:
                if not self._album_id:
                    self._album_id = await im.ensure_album(wb.album_name)
                await im.add_to_album(self._album_id, [aid])
            if wb.tag_enabled:
                await im.tag_assets(wb.tag_name, [aid])
        except ImmichError as e:
            self._album_id = None
            self.app.store.log("warning", "immich", f"Write-back to Immich failed: {e}")

    def _cost(self, paper: Paper, preset: Preset, geometry: dict[str, Any],
              ink_ml: dict[str, float] | None = None) -> float | None:
        copies = max(1, preset.output.copies)
        cost = 0.0
        sheet = paper.cost_per_sheet.get(preset.output.media_size)
        if sheet:
            cost += sheet * copies
        prices = self.app.store.settings().cost
        ink = prices.ink_per_sq_in
        per_ml = prices.ink_per_ml
        if per_ml and ink_ml:
            cost += per_ml * sum((self.app.ink.calibrated(ink_ml) or {}).values())
        elif ink and geometry.get("photo_mm"):
            w, h = geometry["photo_mm"]
            cost += ink * (w * h / 645.16) * copies
        return round(cost, 3) if cost else None

    # ------------------------------------------------------------ test pages
    async def _test_source(self, test: dict[str, Any], preset: Preset, paper: Paper, caps: Capabilities,
                           tmp: Path) -> tuple[pyvips.Image, Preset, list[str]]:
        kind = test.get("kind")
        preset = preset.model_copy(deep=True)
        preset.layout.caption.enabled = False
        preset.layout.keyline = False
        preset.layout.fit = "fill"
        preset.layout.crop = "center"
        preset.layout.orientation = "landscape"
        plan = self.app.printer.plan(preset, paper, caps)
        spec = build_spec(preset, paper, plan, output="none")
        geo = plan_layout(spec, 3, 2)
        dpi = min(plan.dpi, 300)
        w_px = round(geo["photo_w_mm"] / 25.4 * dpi)
        h_px = round(geo["photo_h_mm"] / 25.4 * dpi)
        notes: list[str] = []
        if kind == "chart":
            sample = None
            if test.get("asset_id"):
                try:
                    sample = load_source(await self.immich_preview(test["asset_id"]))
                except Exception:
                    sample = None
            img = await asyncio.to_thread(calibration_chart, w_px, h_px, dpi, f"{paper.name}, {plan.page_label}",
                                          chart_subtitle(paper.name, preset.name), sample)
            return img, preset, notes
        if kind == "pattern":
            sample = load_source(await self.immich_preview(test["asset_id"]))
            base = Adjustments(**test["base"]) if test.get("base") else paper.calibration.adjust
            img, _tiles = await asyncio.to_thread(color_pattern, w_px, h_px, dpi, sample, base,
                                                  test.get("mode", "color"), int(test.get("step", 10)), paper.name)
            return img, preset, notes
        if kind == "target":
            path = Path(test["path"])
            img = load_source(path)
            preset.layout.fit = "fit"
            preset.layout.orientation = "auto"
            preset.layout.borderless = False
            try:
                xres = img.xres * 25.4  # pixels per inch
            except Exception:
                xres = 0
            if xres and xres > 30:
                w_mm, h_mm = img.width / xres * 25.4, img.height / xres * 25.4
                pw, ph = plan.page_w_mm, plan.page_h_mm
                if (w_mm > h_mm) != (pw > ph):
                    pw, ph = ph, pw
                mx, my = (pw - w_mm) / 2, (ph - h_mm) / 2
                if mx >= 3 and my >= 3:
                    preset.layout.margins = Margins(top=my, bottom=my, left=mx, right=mx)
                    notes.append(f"Target printed at actual size ({w_mm:.0f} × {h_mm:.0f} mm, {xres:.0f} ppi).")
                else:
                    notes.append("Target is larger than the printable area — scaled to fit.")
            return img, preset, notes
        raise RenderError(f"Unknown test print '{kind}'")

    # ------------------------------------------------------------ interactive preview
    async def preview(self, asset_id: str | None, preset: Preset, *, focus: tuple[float, float] | None = None,
                      max_px: int = 1400, test: dict[str, Any] | None = None) -> tuple[bytes, dict[str, Any]]:
        paper = self.app.store.paper(preset.output.paper_id) or BUILTIN_BY_ID["canon-pt-101"]
        caps = await self._preview_caps()
        summary = None
        faces: list[Face] = []
        neutral = False
        if test:
            img, preset, _ = await self._test_source(test, preset, paper, caps, self.app.cfg.tmp_dir)
            neutral = test.get("kind") in ("pattern", "target")
        else:
            data = await self.immich_preview(asset_id or "")
            img = await asyncio.to_thread(load_source, data)
            try:
                summary = summarize(await self.app.immich().asset(asset_id or ""))
            except ImmichError:
                summary = None
            if preset.layout.crop in ("smart", "faces"):
                faces = await self.faces(asset_id or "")
        plan = self.app.printer.plan(preset, paper, caps, source_wide=_is_wide(img))
        dpi = max(30, int(max_px / (max(plan.page_w_mm, plan.page_h_mm) / 25.4)))
        caption = render_caption(preset.layout.caption.template, summary) if preset.layout.caption.enabled else ""
        spec = build_spec(preset, paper, plan, caption=caption, faces=faces, focus=focus, dpi=dpi, output="none",
                          neutral=neutral)
        spec.sharpening = "off"
        spec.bit_depth = 8
        result = await asyncio.to_thread(render, img, spec, self.app.cfg.tmp_dir, f"preview-{new_id()}", max_px)
        info = {"plan": plan.describe(), "geometry": result.geometry, "crop": result.crop,
                "warnings": plan.warnings + result.warnings, "caption": caption,
                "effective_ppi": None if test else _scale_ppi(summary, result)}
        return result.preview_bytes or b"", info

    async def _preview_caps(self) -> Capabilities:
        if self.app.printer.configured:
            try:
                return await self.app.printer.capabilities()
            except IppError:
                pass
        return await self.app.printer.capabilities(uri="virtual://pro-310")


def _decodable(path: Path) -> bool:
    try:
        img = pyvips.Image.new_from_file(str(path), access="sequential")
        return img.width > 0 and img.height > 0
    except pyvips.Error:
        return False


def _is_wide(img: pyvips.Image) -> bool:
    try:
        if img.get_typeof("icc-profile-data"):
            return icc.is_wide_gamut(bytes(img.get("icc-profile-data")))
    except pyvips.Error:
        pass
    return False


def _scale_ppi(summary: AssetSummary | None, result: Any) -> float | None:
    """The preview renders from a ~1440 px Immich preview; scale ppi up to the original's size."""
    if not summary or not summary.width or not result.source_px[0]:
        return None
    longest_src = max(result.source_px)
    longest_orig = max(summary.width or 0, summary.height or 0)
    if not longest_src or not longest_orig:
        return None
    return round(result.effective_ppi * longest_orig / longest_src, 1)


def _describe_asset(asset: dict[str, Any] | None) -> str:
    if not asset:
        return "test page"
    from .captions import place
    a = AssetSummary(**asset)
    bits = [p for p in (place(a), (a.taken_at or "")[:10]) if p]
    return ", ".join(bits) or a.filename or "photo"

