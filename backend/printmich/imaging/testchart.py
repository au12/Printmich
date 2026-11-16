"""Calibration chart and Canon-style color-pattern ("ring-around") pages.

Both are rendered as sRGB images and then printed through the exact same pipeline
as photos, so what you see on paper reflects the paper calibration you're tuning.
"""
from __future__ import annotations

import html
from datetime import datetime

import pyvips

from ..models import Adjustments
from .adjust import adjust_lab, apply_cmy

# Approximate sRGB values of the 24 ColorChecker Classic patches (BabelColor averages).
COLORCHECKER = [
    ("Dark skin", (115, 82, 68)), ("Light skin", (194, 150, 130)), ("Blue sky", (98, 122, 157)),
    ("Foliage", (87, 108, 67)), ("Blue flower", (133, 128, 177)), ("Bluish green", (103, 189, 170)),
    ("Orange", (214, 126, 44)), ("Purplish blue", (80, 91, 166)), ("Moderate red", (193, 90, 99)),
    ("Purple", (94, 60, 108)), ("Yellow green", (157, 188, 64)), ("Orange yellow", (224, 163, 46)),
    ("Blue", (56, 61, 150)), ("Green", (70, 148, 73)), ("Red", (175, 54, 60)),
    ("Yellow", (231, 199, 31)), ("Magenta", (187, 86, 149)), ("Cyan", (8, 133, 161)),
    ("White", (243, 243, 242)), ("Neutral 8", (200, 200, 200)), ("Neutral 6.5", (160, 160, 160)),
    ("Neutral 5", (122, 122, 121)), ("Neutral 3.5", (85, 85, 85)), ("Black", (52, 52, 52)),
]


def lstar_to_srgb(L: float) -> int:
    y = ((L + 16) / 116) ** 3 if L > 8 else L / 903.3
    v = 1.055 * y ** (1 / 2.4) - 0.055 if y > 0.0031308 else 12.92 * y
    return max(0, min(255, round(v * 255)))


def _solid(w: int, h: int, rgb: tuple[int, int, int]) -> pyvips.Image:
    return (pyvips.Image.black(max(1, w), max(1, h), bands=3) + list(rgb)).cast("uchar").copy(interpretation="srgb")


def _text(canvas: pyvips.Image, text: str, x: int, y: int, size_pt: float, dpi: int,
          color: tuple[int, int, int] = (40, 40, 40), font: str = "Inter", weight: str = "",
          width: int | None = None, align: str = "low") -> pyvips.Image:
    desc = f"{font} {weight} {size_pt:g}".replace("  ", " ")
    kw = {"font": desc, "dpi": dpi}
    if width:
        kw.update(width=width, align=align)
    try:
        mask = pyvips.Image.text(html.escape(text), **kw)
    except pyvips.Error:
        return canvas
    w = min(mask.width, canvas.width - x)
    h = min(mask.height, canvas.height - y)
    if w <= 0 or h <= 0:
        return canvas
    a = mask.crop(0, 0, w, h).cast("float") / 255.0
    under = canvas.crop(x, y, w, h).cast("float")
    out = under * (1 - a) + a * list(color)
    return canvas.insert(out.cast("uchar").copy(interpretation="srgb"), x, y)


def _gradient(w: int, h: int, start: tuple[int, int, int], end: tuple[int, int, int]) -> pyvips.Image:
    ramp = pyvips.Image.xyz(w, h)[0].cast("float") / max(1, w - 1)
    bands = [ramp * (e - s) + s for s, e in zip(start, end, strict=False)]
    return bands[0].bandjoin(bands[1:]).cast("uchar").copy(interpretation="srgb")


def _hue_sweep(w: int, h: int) -> pyvips.Image:
    xy = pyvips.Image.xyz(w, h)
    hue = xy[0].cast("float") / max(1, w - 1) * 360.0
    lch = (hue * 0 + 62).bandjoin([hue * 0 + 58, hue]).copy(interpretation="lch")
    return lch.colourspace("srgb").cast("uchar")


def calibration_chart(width_px: int, height_px: int, dpi: int, title: str, subtitle: str,
                      sample: pyvips.Image | None = None) -> pyvips.Image:
    """Landscape chart sized to the printable area."""
    W, H = width_px, height_px
    pad = int(W * 0.035)
    u = lambda f: round(f * min(W, H))  # noqa: E731 - unit relative to the short side
    canvas = _solid(W, H, (255, 255, 255))
    pt = max(5.0, min(W, H) / dpi * 72 / 40)  # base font size scales with paper size

    canvas = _text(canvas, "Printmich calibration chart", pad, pad, pt * 1.6, dpi, (20, 20, 20), "Inter", "Semi-Bold")
    canvas = _text(canvas, subtitle, pad, pad + u(0.06), pt * 0.9, dpi, (90, 90, 90))
    canvas = _text(canvas, title, W // 2, pad + u(0.012), pt * 0.9, dpi, (90, 90, 90), width=W // 2 - pad,
                   align="high")

    left_w = int(W * 0.58) - pad
    px_pt = dpi / 72.0
    label_h = int(pt * 0.7 * px_pt * 1.9)
    small_h = int(pt * 0.45 * px_pt * 1.7)
    foot_h = int(pt * 0.55 * px_pt * 3.4)
    gap = u(0.012)
    y0 = pad + u(0.13)
    avail = H - pad - foot_h - y0
    fixed = 3 * label_h + small_h + 4 * (small_h + gap) + 3 * gap
    cw = left_w // 6
    patch_h = max(8, min(int(cw * 0.75), int((avail - fixed) / (4 + 0.6 + 0.5))))
    wedge_h, strip_h = int(patch_h * 0.6), int(patch_h * 0.5)

    y = y0
    canvas = _text(canvas, "Gray wedge, L* 0–100", pad, y, pt * 0.7, dpi, (60, 60, 60), weight="Medium")
    y += label_h
    steps = 21
    sw = left_w // steps
    for i in range(steps):
        canvas = canvas.insert(_solid(sw, wedge_h, (lstar_to_srgb(i * 5),) * 3), pad + i * sw, y)
        if i % 2 == 0:
            canvas = _text(canvas, str(i * 5), pad + i * sw + 2, y + wedge_h + 2, pt * 0.45, dpi, (110, 110, 110))
    y += wedge_h + small_h + gap

    canvas = _text(canvas, "Reference colors", pad, y, pt * 0.7, dpi, (60, 60, 60), weight="Medium")
    y += label_h
    for idx, (name, rgb) in enumerate(COLORCHECKER):
        cx, cy = pad + (idx % 6) * cw, y + (idx // 6) * (patch_h + small_h + gap)
        canvas = canvas.insert(_solid(cw - u(0.008), patch_h, rgb), cx, cy)
        canvas = _text(canvas, name, cx, cy + patch_h + 2, pt * 0.42, dpi, (120, 120, 120))
    y += 4 * (patch_h + small_h + gap) + gap

    half = left_w // 2 - u(0.02)
    shadow = [0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 14]
    hi = [86, 88, 90, 92, 94, 95, 96, 97, 98, 99, 100]
    bw = half // len(shadow)
    canvas = _text(canvas, "Shadow detail, L* 0–14", pad, y, pt * 0.7, dpi, (60, 60, 60), weight="Medium")
    canvas = _text(canvas, "Highlight detail, L* 86–100", pad + half + u(0.04), y, pt * 0.7, dpi, (60, 60, 60),
                   weight="Medium")
    y += label_h
    for i, L in enumerate(shadow):
        canvas = canvas.insert(_solid(bw, strip_h, (lstar_to_srgb(L),) * 3), pad + i * bw, y)
    for i, L in enumerate(hi):
        canvas = canvas.insert(_solid(bw, strip_h, (lstar_to_srgb(L),) * 3), pad + half + u(0.04) + i * bw, y)

    # right column
    rx = pad + left_w + u(0.04)
    rw = W - rx - pad
    ry = y0
    r_avail = H - pad - foot_h - y0
    gh = max(8, min(u(0.06), int((r_avail - 6 * label_h) / 7.5)))
    for label, img in (("Neutral ramp", _gradient(rw, gh, (0, 0, 0), (255, 255, 255))),
                       ("Hue sweep", _hue_sweep(rw, gh)),
                       ("Skin tones", _gradient(rw, gh, (92, 58, 42), (246, 214, 194))),
                       ("Sky", _gradient(rw, gh, (40, 80, 150), (210, 228, 245)))):
        canvas = _text(canvas, label, rx, ry, pt * 0.6, dpi, (90, 90, 90))
        ry += label_h
        canvas = canvas.insert(img, rx, ry)
        ry += gh + gap

    lines_h = gh
    target = _solid(rw, lines_h, (255, 255, 255))
    x = 0
    for width in (1, 1, 1, 2, 2, 2, 3, 3, 3):
        for _ in range(6):
            if x + width >= rw:
                break
            target = target.insert(_solid(width, lines_h, (0, 0, 0)), x, 0)
            x += width * 2
        x += 6
    canvas = _text(canvas, "Fine lines: 1, 2 and 3 px", rx, ry, pt * 0.6, dpi, (90, 90, 90))
    ry += label_h
    canvas = canvas.insert(target, rx, ry)
    ry += lines_h + gap * 2

    box_h = H - pad - foot_h - ry
    if sample is not None and box_h > u(0.08):
        s = sample if sample.bands >= 3 else sample.colourspace("srgb")
        if s.interpretation != "srgb":
            s = s.colourspace("srgb")
        if s.format != "uchar":
            s = s.cast("uchar")
        s = s.thumbnail_image(rw, height=box_h, crop="attention")
        canvas = canvas.insert(s.extract_band(0, n=3).copy(interpretation="srgb"), rx, ry)

    foot = ("Neutral grays should stay neutral; steps 0–4 in the shadow strip should separate. Darker than your "
            "screen → raise Brightness. Muddy shadows → raise Shadows. Color cast → nudge Cyan/Magenta/Yellow.")
    canvas = _text(canvas, foot, pad, H - pad - foot_h + int(pt * px_pt * 0.4), pt * 0.55, dpi, (110, 110, 110),
                   width=W - 2 * pad)
    return canvas


def _adjust_tile(tile: pyvips.Image, adj: Adjustments) -> pyvips.Image:
    lab = tile.icc_import(embedded=True, input_profile="srgb")
    lab = adjust_lab(lab, adj)
    out = lab.icc_export(output_profile="srgb", depth=8)
    return apply_cmy(out, adj, 255.0)


def pattern_variants(base: Adjustments, mode: str, step: int) -> list[tuple[str, Adjustments]]:
    def mk(**delta: int) -> Adjustments:
        return base.plus(Adjustments(**delta))
    if mode == "tone":
        out = []
        for b in (step, 0, -step):
            for c in (-step, 0, step):
                label = ("Current" if not b and not c else
                         ", ".join(p for p in (f"Brightness {b:+d}" if b else "", f"Contrast {c:+d}" if c else "")
                                    if p))
                out.append((label, mk(brightness=b, contrast=c)))
        return out
    return [
        (f"Blue  C{step:+d} M{step:+d}", mk(cyan=step, magenta=step)),
        (f"Magenta  M{step:+d}", mk(magenta=step)),
        (f"Red  M{step:+d} Y{step:+d}", mk(magenta=step, yellow=step)),
        (f"Cyan  C{step:+d}", mk(cyan=step)),
        ("Current", base),
        (f"Yellow  Y{step:+d}", mk(yellow=step)),
        (f"Green  C{step:+d} Y{step:+d}", mk(cyan=step, yellow=step)),
        (f"Lighter  Brightness {step:+d}", mk(brightness=step)),
        (f"Darker  Brightness {-step:+d}", mk(brightness=-step)),
    ]


def color_pattern(width_px: int, height_px: int, dpi: int, sample: pyvips.Image, base: Adjustments,
                  mode: str = "color", step: int = 10, title: str = "") -> tuple[pyvips.Image, list[dict]]:
    W, H = width_px, height_px
    pad = int(min(W, H) * 0.045)
    canvas = _solid(W, H, (255, 255, 255))
    pt = max(5.0, min(W, H) / dpi * 72 / 42)
    head = (f"Color pattern: {'color balance' if mode == 'color' else 'brightness and contrast'}, step {step}"
            + (f", {title}" if title else ""))
    canvas = _text(canvas, head, pad, pad // 2, pt, dpi, (50, 50, 50), weight="Medium")
    grid_top = pad // 2 + int(pt / 72 * dpi * 2.2)
    label_h = int(pt * 0.8 / 72 * dpi * 1.8)
    gap = int(pad * 0.4)
    tw = (W - 2 * pad - 2 * gap) // 3
    th = (H - grid_top - pad - 2 * gap - 3 * label_h) // 3
    s = sample if sample.bands >= 3 else sample.colourspace("srgb")
    if s.format != "uchar":
        s = s.colourspace("srgb")
    tile_src = s.thumbnail_image(tw, height=th, crop="attention").extract_band(0, n=3)
    tile_src = tile_src.copy(interpretation="srgb")
    variants = pattern_variants(base, mode, step)
    tiles = []
    for i, (label, adj) in enumerate(variants):
        col, row = i % 3, i // 3
        x = pad + col * (tw + gap)
        y = grid_top + row * (th + gap + label_h)
        canvas = canvas.insert(_adjust_tile(tile_src, adj), x, y)
        if label == "Current":
            # thin frame marks the current calibration
            t = max(2, int(dpi / 150))
            for (fx, fy, fw, fh) in ((x - 2 * t, y - 2 * t, tile_src.width + 4 * t, t),
                                     (x - 2 * t, y + tile_src.height + t, tile_src.width + 4 * t, t),
                                     (x - 2 * t, y - 2 * t, t, tile_src.height + 4 * t),
                                     (x + tile_src.width + t, y - 2 * t, t, tile_src.height + 4 * t)):
                canvas = canvas.insert(_solid(fw, fh, (20, 20, 20)), max(0, fx), max(0, fy))
        canvas = _text(canvas, f"{i + 1}. {label}", x, y + tile_src.height + int(label_h * 0.15), pt * 0.8, dpi,
                       (60, 60, 60))
        tiles.append({"index": i + 1, "label": label, "adjust": adj.model_dump()})
    return canvas, tiles


def chart_subtitle(paper: str, preset: str) -> str:
    return f"{paper}, {preset}, {datetime.now():%Y-%m-%d %H:%M}"



