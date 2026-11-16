"""Printer service: connection, capability cache, status, and print planning."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from .ipp import media
from .ipp.capabilities import QUALITY_VALUES, Capabilities, parse_capabilities
from .ipp.client import IppClient, IppError, normalize_uri
from .ipp.protocol import Attr, attrs_to_json, boolean, collection, enum, integer, keyword, resolution
from .ipp.virtual import VirtualPrinter
from .models import Paper, Preset
from .papers import resolve_media_source, resolve_media_type

if TYPE_CHECKING:  # pragma: no cover
    from .state import App

log = logging.getLogger("printmich.printer")

VIRTUAL_URI = "virtual://pro-310"


@dataclass
class OutputPlan:
    kind: str                      # pwg | jpeg
    document_format: str
    dpi: int
    bits: int
    space: str                     # srgb | adobe-rgb | sgray
    page_keyword: str
    page_w_mm: float
    page_h_mm: float
    page_label: str
    borderless: bool
    media_type: str | None
    media_type_label: str
    media_type_how: str
    media_source: str | None
    media_source_label: str
    quality: str
    color_mode_ipp: str | None
    rendering_intent_ipp: str | None
    intent: str
    copies: int
    copies_ipp: bool
    hw_margins: dict[str, float]
    warnings: list[str] = field(default_factory=list)

    def describe(self) -> dict[str, Any]:
        d = asdict(self)
        space = {"srgb": "sRGB", "adobe-rgb": "Adobe RGB", "sgray": "Gray"}[self.space]
        fmt = "PWG raster" if self.kind == "pwg" else "JPEG"
        d["summary"] = f"{fmt}, {self.dpi} dpi, {space}, {self.bits}-bit"
        return d


class PrinterService:
    def __init__(self, app: App):
        self.app = app
        self._caps: Capabilities | None = None
        self._caps_uri: str | None = None
        self._caps_at = 0.0
        self._raw: dict[str, list[Any]] | None = None
        self._strings: dict[str, dict[str, str]] = {}
        self._status: dict[str, Any] | None = None
        self._status_at = 0.0
        self._lock = asyncio.Lock()
        self._virtual: VirtualPrinter | None = None

    # ------------------------------------------------------------ connection
    @property
    def uri(self) -> str:
        return (self.app.store.settings().printer_uri or "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.uri)

    def is_virtual(self, uri: str | None = None) -> bool:
        return (uri or self.uri).startswith("virtual://")

    def client(self, uri: str | None = None) -> IppClient | VirtualPrinter:
        uri = uri or self.uri
        if not uri:
            raise IppError("No printer configured yet — add one under Printer.")
        if uri.startswith("virtual://"):
            if self._virtual is None:
                self._virtual = VirtualPrinter(self.app.cfg.virtual_dir, VIRTUAL_URI)
            return self._virtual
        return IppClient(uri)

    def invalidate(self) -> None:
        self._caps = None
        self._raw = None
        self._status = None
        self._caps_at = self._status_at = 0.0

    async def capabilities(self, force: bool = False, uri: str | None = None) -> Capabilities:
        uri = uri or self.uri
        async with self._lock:
            fresh = time.time() - self._caps_at < 600
            if self._caps is not None and self._caps_uri == uri and fresh and not force:
                return self._caps
            client = self.client(uri)
            attrs = await client.get_printer_attributes()
            strings = await self._load_strings(client, attrs, uri)
            caps = parse_capabilities(attrs, client.printer_uri, strings, virtual=self.is_virtual(uri))
            if uri == self.uri:
                self._caps, self._caps_uri, self._caps_at, self._raw = caps, uri, time.time(), attrs
                self._status, self._status_at = self._status_from_caps(caps), time.time()
                await self._cache_icon(client, caps)
            return caps

    async def raw_attributes(self) -> dict[str, Any]:
        if self._raw is None:
            await self.capabilities(force=True)
        return attrs_to_json(self._raw or {})

    async def _load_strings(self, client: IppClient | VirtualPrinter, attrs: dict[str, list[Any]],
                            uri: str) -> dict[str, str]:
        if uri in self._strings:
            return self._strings[uri]
        out: dict[str, str] = {}
        url = (attrs.get("printer-strings-uri") or [None])[0]
        if url:
            try:
                out = media.parse_strings_file(await client.fetch(str(url)))
            except Exception as e:  # pragma: no cover - printer dependent
                log.info("could not load printer strings from %s: %s", url, e)
        self._strings[uri] = out
        return out

    async def _cache_icon(self, client: IppClient | VirtualPrinter, caps: Capabilities) -> None:
        dest = self.app.cfg.cache_dir / "printer-icon.png"
        if not caps.icons:
            dest.unlink(missing_ok=True)
            return
        if dest.exists() and dest.stat().st_mtime > time.time() - 86400:
            return
        for url in reversed(caps.icons):  # largest is usually last
            try:
                data = await client.fetch(url)
                if data[:8] == b"\x89PNG\r\n\x1a\n":
                    dest.write_bytes(data)
                    return
            except Exception:
                continue

    # ------------------------------------------------------------ status
    @staticmethod
    def _status_from_caps(caps: Capabilities) -> dict[str, Any]:
        return {
            "state": caps.state, "reasons": caps.state_reasons, "message": caps.state_message,
            "accepting": caps.accepting, "markers": [asdict(m) for m in caps.markers], "ready": caps.ready,
        }

    def last_markers(self) -> list[dict[str, Any]]:
        """Ink levels from the most recent status, as the printer reported them."""
        return list((self._status or {}).get("markers", []))

    async def status(self, max_age: float = 8.0) -> dict[str, Any]:
        """Printer state, alerts, loaded paper and ink — estimated ink when the user tracks refills."""
        return self.app.ink.decorate(await self._status_now(max_age))

    async def _status_now(self, max_age: float) -> dict[str, Any]:
        if not self.configured:
            return {"configured": False}
        if self._status is not None and time.time() - self._status_at < max_age:
            return {"configured": True, "online": True, **self._status}
        try:
            if self._caps is None or self._caps_uri != self.uri:
                await self.capabilities()
                return {"configured": True, "online": True, **(self._status or {})}
            attrs = await self.client().get_state()
            caps = parse_capabilities({**(self._raw or {}), **attrs}, self.uri,
                                      self._strings.get(self.uri), virtual=self.is_virtual())
            self._status, self._status_at = self._status_from_caps(caps), time.time()
            return {"configured": True, "online": True, **self._status}
        except IppError as e:
            return {"configured": True, "online": False, "error": str(e), "state": "offline", "reasons": [],
                    "markers": (self._status or {}).get("markers", []), "ready": []}

    # ------------------------------------------------------------ planning
    def plan(self, preset: Preset, paper: Paper, caps: Capabilities, *, source_wide: bool | None = None) -> OutputPlan:
        out = preset.output
        warnings: list[str] = []

        # page
        size = caps.size(out.media_size)
        if size:
            pw, ph, label = size.width_mm, size.height_mm, size.label
        else:
            dims = media.size_from_keyword(out.media_size)
            if not dims:
                raise IppError(f"Unknown paper size '{out.media_size}'")
            pw, ph = dims
            label = media.label_for(out.media_size)
            if caps.sizes:
                warnings.append(f"The printer doesn't list {label}; it may substitute another size.")

        # document format
        has_pwg = caps.supports_format("image/pwg-raster") and bool(caps.pwg_types)
        has_jpeg = caps.supports_format("image/jpeg")
        kind = out.document_format
        if kind == "auto":
            kind = "pwg" if has_pwg else "jpeg" if has_jpeg else ""
        elif kind == "pwg" and not has_pwg:
            warnings.append("PWG raster isn't supported by this printer — using JPEG.")
            kind = "jpeg" if has_jpeg else ""
        elif kind == "jpeg" and not has_jpeg:
            warnings.append("JPEG isn't supported by this printer — using PWG raster.")
            kind = "pwg" if has_pwg else ""
        if not kind:
            raise IppError("This printer accepts neither PWG raster nor JPEG documents.")

        # color space & depth
        mode = preset.color.mode
        bits = out.bit_depth if kind == "pwg" else 8
        if kind == "pwg":
            if mode == "bw":
                space = "sgray" if "sgray" in caps.raster_color_spaces(bits) else "srgb"
            else:
                want = preset.color.space
                avail = caps.raster_color_spaces(bits)
                if want == "auto":
                    want = "adobe-rgb" if (source_wide and "adobe-rgb" in avail) else "srgb"
                if want == "adobe-rgb" and "adobe-rgb" not in avail:
                    warnings.append("Adobe RGB isn't offered by this printer — using sRGB.")
                    want = "srgb"
                space = want
            if space not in caps.raster_color_spaces(bits):
                if bits == 16 and space in caps.raster_color_spaces(8):
                    warnings.append("16-bit raster isn't supported — using 8-bit.")
                    bits = 8
                elif "srgb" in caps.raster_color_spaces(bits):
                    space = "srgb"
                else:
                    bits = 8
                    space = "srgb"
        else:
            space = "srgb"
            if preset.color.space == "adobe-rgb":
                warnings.append("Adobe RGB output needs PWG raster; JPEG is sent as sRGB.")
        if preset.color.management == "custom-icc":
            space = "srgb"

        # resolution
        if kind == "pwg":
            choices = caps.pwg_resolutions or [300]
            if out.resolution:
                dpi = min(choices, key=lambda r: (abs(r - out.resolution), -r))
                if dpi != out.resolution:
                    warnings.append(f"{out.resolution} dpi isn't offered — using {dpi} dpi.")
            else:
                le600 = [r for r in choices if r <= 600]
                dpi = max(le600) if le600 else min(choices)
        else:
            dpi = out.resolution or 300
            limit_x = caps.jpeg_max_x or 100000
            limit_y = caps.jpeg_max_y or 100000
            while dpi > 150 and (pw / 25.4 * dpi > limit_x or ph / 25.4 * dpi > limit_y):
                dpi -= 30

        # media mapping
        mt = resolve_media_type(paper, caps.types, out.media_type)
        src = resolve_media_source(paper, caps.source_keywords(), out.media_source)
        if paper.feeds == ["manual"] and src and src not in ("manual", "by-pass-tray", "rear", "alternate"):
            warnings.append(f"{paper.name} usually needs the manual feed.")

        # borderless
        borderless = preset.layout.borderless
        if borderless:
            capable = (size.borderless if size else caps.borderless_capable) or caps.virtual
            if not capable and caps.sizes:
                warnings.append(f"Borderless isn't available for {label} — printing with minimum margins.")
                borderless = False
            elif not paper.borderless:
                warnings.append(f"{paper.name} isn't rated for borderless printing; edges may be weaker.")

        quality = out.quality
        if caps.qualities and quality not in caps.qualities:
            quality = "high" if "high" in caps.qualities else caps.qualities[-1]

        color_mode = None
        if caps.color_modes:
            if mode == "bw" and "monochrome" in caps.color_modes:
                color_mode = "monochrome"
            elif "color" in caps.color_modes:
                color_mode = "color"

        intent = preset.color.intent if preset.color.intent != "paper" else paper.calibration.intent
        ipp_intent = None
        if preset.color.send_rendering_intent and caps.rendering_intents:
            cand = intent
            bpc = preset.color.bpc if preset.color.intent != "paper" else paper.calibration.bpc
            if intent == "relative" and bpc and "relative-bpc" in caps.rendering_intents:
                cand = "relative-bpc"
            if cand in caps.rendering_intents:
                ipp_intent = cand

        copies = max(1, out.copies)
        copies_ipp = copies > 1 and caps.copies_max >= copies and (
            "copies" in caps.job_attributes or not caps.job_attributes)

        src_label = media.media_source_label(src) if src else "Printer default"
        return OutputPlan(
            kind=kind, document_format="image/pwg-raster" if kind == "pwg" else "image/jpeg", dpi=dpi, bits=bits,
            space=space, page_keyword=out.media_size, page_w_mm=pw, page_h_mm=ph, page_label=label,
            borderless=borderless, media_type=mt["keyword"], media_type_label=mt["label"] or "Printer default",
            media_type_how=mt["how"], media_source=src, media_source_label=src_label, quality=quality,
            color_mode_ipp=color_mode, rendering_intent_ipp=ipp_intent, intent=intent, copies=copies,
            copies_ipp=copies_ipp, hw_margins=dict(caps.hw_margins), warnings=warnings,
        )

    def job_attributes(self, plan: OutputPlan, caps: Capabilities, preset: Preset) -> list[Attr]:
        size = caps.size(plan.page_keyword)
        w_hmm = round((size.width_mm if size else plan.page_w_mm) * 100)
        h_hmm = round((size.height_mm if size else plan.page_h_mm) * 100)
        members: list[Attr] = [collection("media-size", [integer("x-dimension", w_hmm), integer("y-dimension", h_hmm)])]
        if plan.media_type:
            members.append(keyword("media-type", plan.media_type))
        if plan.media_source:
            members.append(keyword("media-source", plan.media_source))
        if plan.borderless:
            for side in ("top", "bottom", "left", "right"):
                members.append(integer(f"media-{side}-margin", 0))
        else:
            hm = plan.hw_margins
            for side in ("top", "bottom", "left", "right"):
                members.append(integer(f"media-{side}-margin", round(hm.get(side, 3.0) * 100)))
        attrs: list[Attr] = [collection("media-col", members)]
        supported = set(caps.job_attributes)

        def ok(name: str) -> bool:
            return not supported or name in supported

        if caps.qualities and ok("print-quality"):
            attrs.append(enum("print-quality", QUALITY_VALUES[plan.quality]))
        if plan.color_mode_ipp and ok("print-color-mode"):
            attrs.append(keyword("print-color-mode", plan.color_mode_ipp))
        if "photo" in caps.content_optimize and ok("print-content-optimize"):
            attrs.append(keyword("print-content-optimize", "photo"))
        if plan.rendering_intent_ipp and ok("print-rendering-intent"):
            attrs.append(keyword("print-rendering-intent", plan.rendering_intent_ipp))
        if plan.kind == "jpeg" and caps.scaling and ok("print-scaling"):
            want = "fill" if plan.borderless else "fit"
            if want in caps.scaling:
                attrs.append(keyword("print-scaling", want))
        if plan.dpi in caps.resolutions and ok("printer-resolution"):
            attrs.append(resolution("printer-resolution", plan.dpi))
        if plan.copies_ipp:
            attrs.append(integer("copies", plan.copies))
        if ok("orientation-requested") and plan.kind == "jpeg":
            attrs.append(enum("orientation-requested", 3))
        for k, v in (preset.output.extra_ipp or {}).items():
            k = str(k).strip()
            if not k:
                continue
            if isinstance(v, bool):
                attrs.append(boolean(k, v))
            elif isinstance(v, int):
                attrs.append(integer(k, v))
            else:
                attrs.append(keyword(k, str(v)))
        return attrs

    # ------------------------------------------------------------ misc
    async def test(self, uri: str) -> dict[str, Any]:
        uri = normalize_uri(uri)
        caps = await self.capabilities(force=True, uri=uri)
        return {"uri": uri, "make_model": caps.make_model, "name": caps.info or caps.name,
                "formats": caps.formats, "virtual": caps.virtual}

    def media_check(self, plan: OutputPlan, status: dict[str, Any]) -> dict[str, Any] | None:
        """Compare the planned paper with what the printer reports as loaded (media-col-ready)."""
        ready = status.get("ready") or []
        if not ready:
            return None
        cands = [r for r in ready if not plan.media_source or not r.get("source") or r.get("source") == plan.media_source]
        if not cands:
            return None
        r = cands[0]
        size_ok = True
        if r.get("width_mm") and r.get("height_mm"):
            size_ok = (abs(r["width_mm"] - plan.page_w_mm) < 1.5 and abs(r["height_mm"] - plan.page_h_mm) < 1.5) or (
                abs(r["width_mm"] - plan.page_h_mm) < 1.5 and abs(r["height_mm"] - plan.page_w_mm) < 1.5)
        type_ok = not r.get("type") or not plan.media_type or r["type"] == plan.media_type
        return {"ok": size_ok and type_ok, "size_ok": size_ok, "type_ok": type_ok, "loaded": r,
                "wanted": {"size": plan.page_label, "type": plan.media_type_label, "source": plan.media_source_label}}
