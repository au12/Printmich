"""Page renderer: crop → resize → color-manage → adjust → sharpen → lay out → encode.

Everything is done with libvips, which streams the image in tiles so even a
13×19" page at 600 dpi (≈89 MP) renders in bounded memory.
"""
from __future__ import annotations

import html
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pyvips

from ..ipp import pwg
from ..models import Adjustments, Layout
from . import icc
from .adjust import adjust_lab, apply_cmy, sharpen_lab

log = logging.getLogger("printmich.render")

FONTS = {"serif": "EB Garamond", "sans": "Inter", "mono": "DejaVu Sans Mono"}


class RenderError(Exception):
    pass


@dataclass
class Face:
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class RenderSpec:
    page_w_mm: float
    page_h_mm: float
    page_keyword: str = ""
    dpi: int = 300
    bit_depth: int = 8
    out_space: str = "srgb"            # srgb | adobe-rgb | sgray
    management: str = "managed"        # managed | custom-icc | passthrough
    icc_profile: str | None = None
    intent: str = "relative"
    bpc: bool = True
    adjust: Adjustments = field(default_factory=Adjustments)
    color_mode: str = "color"          # color | bw | bw-toned
    tone: tuple[int, int] = (0, 0)
    sharpening: str = "low"
    layout: Layout = field(default_factory=Layout)
    caption_text: str = ""
    hw_margins: dict[str, float] = field(default_factory=lambda: {"top": 3.0, "bottom": 5.0, "left": 3.4,
                                                                   "right": 3.4})
    focus: tuple[float, float] | None = None
    faces: list[Face] = field(default_factory=list)
    media_type: str = ""
    quality: int = 0
    rendering_intent_kw: str = ""
    pages: int = 1                     # copies emitted inside the PWG document
    output: str = "pwg"                # pwg | jpeg | none
    jpeg_quality: int = 95


@dataclass
class RenderResult:
    document: Path | None = None
    mime: str | None = None
    preview: Path | None = None
    preview_bytes: bytes | None = None
    width_px: int = 0
    height_px: int = 0
    geometry: dict[str, Any] = field(default_factory=dict)
    crop: dict[str, Any] = field(default_factory=dict)
    effective_ppi: float = 0.0
    source_px: tuple[int, int] = (0, 0)
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)

    def meta(self) -> dict[str, Any]:
        return {"width_px": self.width_px, "height_px": self.height_px, "geometry": self.geometry,
                "crop": self.crop, "effective_ppi": round(self.effective_ppi, 1),
                "source_px": list(self.source_px), "warnings": self.warnings, "timings": self.timings}


# ---------------------------------------------------------------- loading

def load_source(src: Path | str | bytes, max_dim: int | None = None) -> pyvips.Image:
    try:
        if isinstance(src, (bytes, bytearray)):
            img = (pyvips.Image.thumbnail_buffer(src, max_dim, size="down") if max_dim
                   else pyvips.Image.new_from_buffer(src, "", access="random"))
        else:
            img = (pyvips.Image.thumbnail(str(src), max_dim, size="down") if max_dim
                   else pyvips.Image.new_from_file(str(src), access="random"))
    except pyvips.Error as e:
        raise RenderError(f"Can't decode this image ({str(e).splitlines()[0]})") from e
    if not max_dim:
        img = img.autorot()
    if img.hasalpha():
        bg = 65535 if img.format == "ushort" else 255
        img = img.flatten(background=[bg] * (img.bands - 1))
    if img.format not in ("uchar", "ushort"):
        img = img.cast("ushort" if img.format in ("uint", "int", "float", "double") else "uchar")
    return img


def _to_rgb(img: pyvips.Image) -> pyvips.Image:
    if img.bands == 1 or img.interpretation in ("b-w", "grey16"):
        return img.colourspace("rgb16" if img.format == "ushort" else "srgb")
    return img


# ---------------------------------------------------------------- geometry

def _mm_px(mm: float, dpi: int) -> int:
    return round(mm / 25.4 * dpi)


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = (h or "#ffffff").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return 255, 255, 255


def _caption_mask(text: str, layout: Layout, dpi: int, width_px: int) -> pyvips.Image | None:
    cap = layout.caption
    if not text.strip():
        return None
    family = FONTS.get(cap.font, "EB Garamond")
    style = " Italic" if cap.italic else ""
    font = f"{family}{style} {cap.size_pt:g}"
    markup = html.escape(text)
    if cap.letter_spacing:
        markup = f'<span letter_spacing="{int(cap.letter_spacing * cap.size_pt * 1024)}">{markup}</span>'
    align = {"left": "low", "center": "centre", "right": "high"}[cap.align]
    try:
        return pyvips.Image.text(markup, font=font, dpi=dpi, width=max(16, width_px), align=align)
    except pyvips.Error:
        return pyvips.Image.text(html.escape(text), dpi=dpi, width=max(16, width_px), align=align)


def plan_layout(spec: RenderSpec, src_w: int, src_h: int) -> dict[str, Any]:
    lay = spec.layout
    portrait_page = spec.page_w_mm <= spec.page_h_mm
    if lay.orientation == "auto":
        landscape = src_w > src_h and abs(spec.page_w_mm - spec.page_h_mm) > 0.5
    else:
        landscape = lay.orientation == "landscape"
    rotate = (landscape and portrait_page) or (not landscape and not portrait_page)
    lw, lh = (spec.page_h_mm, spec.page_w_mm) if rotate else (spec.page_w_mm, spec.page_h_mm)
    hw = spec.hw_margins
    if rotate:  # layout is rotated 90° clockwise into the feed direction
        floor = {"top": hw["right"], "right": hw["bottom"], "bottom": hw["left"], "left": hw["top"]}
    else:
        floor = dict(hw)
    if lay.borderless:
        m = {"top": 0.0, "right": 0.0, "bottom": 0.0, "left": 0.0}
    else:
        m = {k: max(getattr(lay.margins, k), floor[k]) for k in ("top", "right", "bottom", "left")}
    caption = None
    if not lay.borderless and lay.caption.enabled and spec.caption_text.strip():
        width_px = _mm_px(lw - m["left"] - m["right"], spec.dpi)
        mask = _caption_mask(spec.caption_text, lay, spec.dpi, width_px)
        if mask is not None:
            text_h = mask.height / spec.dpi * 25.4
            gap = min(8.0, max(2.5, m["bottom"] * 0.22))
            need = gap + text_h + max(floor["bottom"], 3.0)
            if m["bottom"] < need:
                m["bottom"] = need
            caption = {"mask": mask, "gap_mm": gap, "height_mm": text_h}
    # keep at least a sensible photo area
    pw = max(10.0, lw - m["left"] - m["right"])
    ph = max(10.0, lh - m["top"] - m["bottom"])
    return {"landscape": landscape, "rotate": rotate, "layout_w_mm": lw, "layout_h_mm": lh, "margins": m,
            "photo_w_mm": pw, "photo_h_mm": ph, "caption": caption}


def compute_crop(src_w: int, src_h: int, aspect: float, fx: float, fy: float) -> tuple[int, int, int, int]:
    if src_w / src_h > aspect:
        ch = src_h
        cw = max(1, min(src_w, round(src_h * aspect)))
    else:
        cw = src_w
        ch = max(1, min(src_h, round(src_w / aspect)))
    cx = round(min(max(fx * src_w - cw / 2, 0), src_w - cw))
    cy = round(min(max(fy * src_h - ch / 2, 0), src_h - ch))
    return cx, cy, cw, ch


def find_focus(img: pyvips.Image, spec: RenderSpec, aspect: float) -> tuple[float, float, str]:
    if spec.focus:
        return min(max(spec.focus[0], 0.0), 1.0), min(max(spec.focus[1], 0.0), 1.0), "manual"
    strategy = spec.layout.crop
    if strategy in ("smart", "faces") and spec.faces:
        x1 = min(f.x1 for f in spec.faces)
        y1 = min(f.y1 for f in spec.faces)
        x2 = max(f.x2 for f in spec.faces)
        y2 = max(f.y2 for f in spec.faces)
        # bias slightly upward so heads keep some headroom
        return (x1 + x2) / 2, max(0.0, (y1 + y2) / 2 - (y2 - y1) * 0.15), "faces"
    if strategy in ("smart", "attention"):
        try:
            small = img.thumbnail_image(320) if max(img.width, img.height) > 320 else img
            _, _, cw, ch = compute_crop(small.width, small.height, aspect, 0.5, 0.5)
            if cw < small.width or ch < small.height:
                _, opts = small.smartcrop(cw, ch, interesting="attention", attention_x=True, attention_y=True)
                ax, ay = opts.get("attention_x", 0), opts.get("attention_y", 0)
                if ax or ay:
                    return ax / small.width, ay / small.height, "attention"
        except pyvips.Error as e:  # pragma: no cover - defensive
            log.debug("attention crop failed: %s", e)
    return 0.5, 0.5, "center"


# ---------------------------------------------------------------- color

def color_pipeline(img: pyvips.Image, spec: RenderSpec) -> pyvips.Image:
    bits = spec.bit_depth
    maxv = 255.0 if bits == 8 else 65535.0
    if spec.management == "passthrough":
        out = _to_rgb(img)
        if out.bands == 4:
            out = out.colourspace("srgb")
        if spec.out_space == "sgray":
            return out.colourspace("b-w" if bits == 8 else "grey16")
        target = "srgb" if bits == 8 else "rgb16"
        if out.interpretation != target:
            out = out.colourspace(target)
        return out
    src = _to_rgb(img)
    input_profile = "cmyk" if src.bands == 4 or src.interpretation == "cmyk" else "srgb"
    try:
        lab = src.icc_import(embedded=True, input_profile=input_profile, intent=spec.intent,
                             black_point_compensation=spec.bpc)
    except pyvips.Error:
        lab = src.icc_import(embedded=False, input_profile=input_profile, intent=spec.intent,
                             black_point_compensation=spec.bpc)
    lab = adjust_lab(lab, spec.adjust, spec.color_mode, spec.tone)
    lab = sharpen_lab(lab, spec.sharpening, spec.dpi)
    if spec.out_space == "sgray":
        return lab.colourspace("b-w" if bits == 8 else "grey16")
    profile = (spec.icc_profile if spec.management == "custom-icc" and spec.icc_profile
               else icc.profile_for_space(spec.out_space))
    try:
        out = lab.icc_export(output_profile=profile, intent=spec.intent, black_point_compensation=spec.bpc,
                             depth=bits)
    except pyvips.Error:
        out = lab.icc_export(output_profile=profile, intent="relative", black_point_compensation=spec.bpc,
                             depth=bits)
    return apply_cmy(out, spec.adjust, maxv)


# ---------------------------------------------------------------- composition

def _solid(w: int, h: int, bands: int, value: list[float], fmt: str, interp: str) -> pyvips.Image:
    base = pyvips.Image.black(max(1, w), max(1, h), bands=bands)
    return (base + value).cast(fmt).copy(interpretation=interp)


def compose(img: pyvips.Image, spec: RenderSpec) -> tuple[pyvips.Image, dict[str, Any], RenderResult]:
    res = RenderResult(source_px=(img.width, img.height))
    t0 = time.perf_counter()
    plan = plan_layout(spec, img.width, img.height)
    dpi = spec.dpi
    lw_px, lh_px = _mm_px(plan["layout_w_mm"], dpi), _mm_px(plan["layout_h_mm"], dpi)
    m = plan["margins"]
    left_px, top_px = _mm_px(m["left"], dpi), _mm_px(m["top"], dpi)
    pw_px = max(1, lw_px - left_px - _mm_px(m["right"], dpi))
    ph_px = max(1, lh_px - top_px - _mm_px(m["bottom"], dpi))
    sw, sh = img.width, img.height

    if spec.layout.fit == "fill":
        aspect = pw_px / ph_px
        fx, fy, how = find_focus(img, spec, aspect)
        cx, cy, cw, ch = compute_crop(sw, sh, aspect, fx, fy)
        region = img.crop(cx, cy, cw, ch)
        tw, th = pw_px, ph_px
        ox, oy = left_px, top_px
        res.crop = {"x": cx / sw, "y": cy / sh, "w": cw / sw, "h": ch / sh, "focus": [round(fx, 4), round(fy, 4)],
                    "method": how}
        res.effective_ppi = cw / (pw_px / dpi)
        lost = 1.0 - (cw * ch) / (sw * sh)
        if lost > 0.25:
            res.warnings.append(f"Cropping {round(lost * 100)}% of the photo to fill the paper.")
    else:
        scale = min(pw_px / sw, ph_px / sh)
        tw, th = max(1, round(sw * scale)), max(1, round(sh * scale))
        region = img
        ox, oy = left_px + (pw_px - tw) // 2, top_px + (ph_px - th) // 2
        res.crop = {"x": 0, "y": 0, "w": 1, "h": 1, "focus": [0.5, 0.5], "method": "fit"}
        res.effective_ppi = sw / (tw / dpi)

    hscale, vscale = tw / region.width, th / region.height
    kernel = "lanczos3"
    resized = region.resize(hscale, vscale=vscale, kernel=kernel)
    if resized.width != tw or resized.height != th:
        resized = resized.crop(0, 0, min(tw, resized.width), min(th, resized.height))
        resized = resized.embed(0, 0, tw, th, extend="copy")
    if res.effective_ppi < 150:
        res.warnings.append(f"Low resolution for this size (≈{int(res.effective_ppi)} ppi) — expect softness.")

    photo = color_pipeline(resized, spec)
    bands = photo.bands
    fmt = photo.format
    maxv = 255.0 if fmt == "uchar" else 65535.0
    interp = photo.interpretation
    r, g, b = _hex_rgb(spec.layout.border_color)
    if bands == 1:
        paper = [round((0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 * maxv)]
    else:
        paper = [round(c / 255 * maxv) for c in (r, g, b)]
    canvas = _solid(lw_px, lh_px, bands, paper, fmt, interp)
    canvas = canvas.insert(photo, ox, oy)

    if spec.layout.keyline and not spec.layout.borderless:
        t = max(1, round(spec.layout.keyline_width_pt / 72 * dpi))
        kr, kg, kb = _hex_rgb(spec.layout.keyline_color)
        kval = ([round((0.2126 * kr + 0.7152 * kg + 0.0722 * kb) / 255 * maxv)] if bands == 1
                else [round(c / 255 * maxv) for c in (kr, kg, kb)])
        horiz = _solid(tw + 2 * t, t, bands, kval, fmt, interp)
        vert = _solid(t, th, bands, kval, fmt, interp)
        canvas = canvas.insert(horiz, ox - t, oy - t).insert(horiz, ox - t, oy + th)
        canvas = canvas.insert(vert, ox - t, oy).insert(vert, ox + tw, oy)

    cap = plan.get("caption")
    if cap:
        mask: pyvips.Image = cap["mask"]
        gap_px = _mm_px(cap["gap_mm"], dpi)
        align = spec.layout.caption.align
        if align == "left":
            tx = left_px
        elif align == "right":
            tx = left_px + pw_px - mask.width
        else:
            tx = left_px + (pw_px - mask.width) // 2
        ty = top_px + ph_px + gap_px
        tx = max(0, min(tx, lw_px - mask.width))
        ty = max(0, min(ty, lh_px - mask.height))
        cr, cg, cb = _hex_rgb(spec.layout.caption.color)
        col = ([(0.2126 * cr + 0.7152 * cg + 0.0722 * cb) / 255 * maxv] if bands == 1
               else [c / 255 * maxv for c in (cr, cg, cb)])
        w_ = min(mask.width, lw_px - tx)
        h_ = min(mask.height, lh_px - ty)
        alpha = mask.crop(0, 0, w_, h_).cast("float") / 255.0
        under = canvas.crop(tx, ty, w_, h_).cast("float")
        blended = under * (1.0 - alpha) + alpha * col
        canvas = canvas.insert(blended.cast(fmt).copy(interpretation=interp), tx, ty)

    res.geometry = {
        "page_mm": [spec.page_w_mm, spec.page_h_mm], "layout_mm": [plan["layout_w_mm"], plan["layout_h_mm"]],
        "landscape": plan["landscape"], "rotated": plan["rotate"],
        "margins_mm": {k: round(v, 2) for k, v in m.items()},
        "photo_mm": [round(tw / dpi * 25.4, 2), round(th / dpi * 25.4, 2)],
        "photo_px": [tw, th], "photo_offset_px": [ox, oy], "dpi": dpi,
        "caption": bool(cap),
    }
    res.timings["plan"] = round(time.perf_counter() - t0, 3)
    return canvas, plan, res


# ---------------------------------------------------------------- outputs

def _preview_from(layout_img: pyvips.Image, spec: RenderSpec, max_px: int) -> pyvips.Image:
    prev = layout_img.thumbnail_image(max_px) if max(layout_img.width, layout_img.height) > max_px else layout_img
    if prev.bands == 1:
        prev = prev.colourspace("srgb")
    elif spec.out_space == "adobe-rgb" and spec.management == "managed":
        prev = prev.icc_transform("srgb", input_profile=icc.adobe_rgb_path(), embedded=False, depth=8)
    if prev.format != "uchar":
        prev = prev.colourspace("srgb") if prev.interpretation == "rgb16" else (prev / 257).cast("uchar")
    return prev


def render(src: Path | str | bytes | pyvips.Image, spec: RenderSpec, out_dir: Path, stem: str,
           preview_px: int = 1600) -> RenderResult:
    t0 = time.perf_counter()
    img = src if isinstance(src, pyvips.Image) else load_source(src)
    canvas, plan, res = compose(img, spec)
    out_dir.mkdir(parents=True, exist_ok=True)

    if spec.output == "none":
        prev = _preview_from(canvas, spec, preview_px)
        res.preview_bytes = prev.jpegsave_buffer(Q=88, strip=True)
        res.width_px, res.height_px = canvas.width, canvas.height
        res.timings["total"] = round(time.perf_counter() - t0, 3)
        return res

    layout_path = out_dir / f"{stem}.layout.v"
    canvas.write_to_file(str(layout_path))
    res.timings["render"] = round(time.perf_counter() - t0, 3)
    layout_img = pyvips.Image.new_from_file(str(layout_path))
    prev = _preview_from(layout_img, spec, preview_px)
    res.preview = out_dir / f"{stem}.preview.jpg"
    prev.jpegsave(str(res.preview), Q=88, strip=True)

    final = layout_img.rot90() if plan["rotate"] else layout_img
    res.width_px, res.height_px = final.width, final.height
    bits = spec.bit_depth
    try:
        if spec.output == "pwg":
            raw_path = out_dir / f"{stem}.raw"
            final.rawsave(str(raw_path))
            dtype = np.uint8 if final.format == "uchar" else np.uint16
            arr = np.memmap(raw_path, dtype=dtype, mode="r", shape=(final.height, final.width, final.bands))
            cs = {"srgb": pwg.CSPACE_SRGB, "adobe-rgb": pwg.CSPACE_ADOBERGB, "sgray": pwg.CSPACE_SGRAY}
            space = spec.out_space if spec.management != "custom-icc" else "srgb"
            page = pwg.PwgPage(
                width=final.width, height=final.height, dpi=spec.dpi,
                page_w_pt=round(spec.page_w_mm / 25.4 * 72), page_h_pt=round(spec.page_h_mm / 25.4 * 72),
                color_space=cs.get(space, pwg.CSPACE_SRGB), bits_per_color=bits, media_type=spec.media_type or "",
                page_size_name=spec.page_keyword or "", quality=spec.quality,
                rendering_intent=spec.rendering_intent_kw or "", total_pages=max(1, spec.pages),
            )
            res.document = out_dir / f"{stem}.pwg"
            with open(res.document, "wb") as fh:
                fh.write(pwg.SYNC)
                for _ in range(max(1, spec.pages)):
                    pwg.write_page(fh, page, arr)
            del arr
            raw_path.unlink(missing_ok=True)
            res.mime = "image/pwg-raster"
        elif spec.output == "jpeg":
            j = final
            if j.format != "uchar":
                j = j.colourspace("srgb" if j.bands >= 3 else "b-w") if j.interpretation in ("rgb16", "grey16") \
                    else (j / 257).cast("uchar")
            j = j.copy(xres=spec.dpi / 25.4, yres=spec.dpi / 25.4)
            prof = icc.profile_bytes_for_space(spec.out_space if spec.management == "managed" else "srgb")
            if prof and j.bands >= 3:
                j = j.copy()
                j.set_type(pyvips.GValue.blob_type, "icc-profile-data", prof)
            res.document = out_dir / f"{stem}.jpg"
            j.jpegsave(str(res.document), Q=spec.jpeg_quality, subsample_mode="off", optimize_coding=True)
            res.mime = "image/jpeg"
    finally:
        try:
            os.unlink(layout_path)
        except OSError:
            pass
    res.timings["total"] = round(time.perf_counter() - t0, 3)
    return res


def thumbnail_jpeg(src: Path | str | bytes, max_px: int = 1024, quality: int = 84) -> tuple[bytes, int, int]:
    """Small sRGB JPEG for the photo wall."""
    if isinstance(src, (bytes, bytearray)):
        t = pyvips.Image.thumbnail_buffer(bytes(src), max_px, size="down")
    else:
        t = pyvips.Image.thumbnail(str(src), max_px, size="down")
    if t.hasalpha():
        t = t.flatten(background=[255] * (t.bands - 1))
    try:
        t = t.icc_transform("srgb", embedded=True, input_profile="srgb")
    except pyvips.Error:
        t = t.colourspace("srgb")
    if t.format != "uchar":
        t = t.cast("uchar")
    return t.jpegsave_buffer(Q=quality, strip=True, optimize_coding=True), t.width, t.height


def mm_to_in(v: float) -> float:
    return v / 25.4

