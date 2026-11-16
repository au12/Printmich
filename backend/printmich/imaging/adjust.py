"""Canon-driver-style tonal and color adjustments implemented on libvips Lab images.

All curves keep pure black and paper white fixed — exactly like the PRO-310 driver,
where "you cannot change the levels of pure white and black".
"""
from __future__ import annotations

import pyvips

from ..models import Adjustments

SHARPEN_M2 = {"off": 0.0, "low": 1.2, "standard": 2.2, "high": 3.4}
SHARPEN_RADIUS_MM = {"off": 0.0, "low": 0.06, "standard": 0.08, "high": 0.10}


def _curve_L(L: pyvips.Image, adj: Adjustments) -> pyvips.Image:
    x = _clamp01(L / 100.0)
    if adj.brightness:
        g = 1.45 ** (-adj.brightness / 50.0)
        x = x ** g
    if adj.contrast:
        smooth = x * x * (3.0 - 2.0 * x)
        if adj.contrast > 0:
            s = adj.contrast / 50.0 * 0.8
            x = x + (smooth - x) * s
        else:
            s = -adj.contrast / 50.0 * 0.6
            x = x - (smooth - x) * s
    if adj.shadows:
        k = adj.shadows / 50.0 * 0.6
        one_minus = 1.0 - x
        x = x + k * x * one_minus * one_minus * one_minus * 4.0
    if adj.highlights:
        k = adj.highlights / 50.0 * 0.6
        x = x + k * x * x * x * (1.0 - x) * 4.0
    return _clamp01(x) * 100.0


def _clamp01(img: pyvips.Image) -> pyvips.Image:
    return (img < 0).ifthenelse(0.0, (img > 1).ifthenelse(1.0, img))


def adjust_lab(lab: pyvips.Image, adj: Adjustments, mode: str = "color",
               tone: tuple[int, int] = (0, 0)) -> pyvips.Image:
    """Apply brightness/contrast/shadows/highlights/saturation and B&W conversion in Lab."""
    L, a, b = lab[0], lab[1], lab[2]
    tonal = any((adj.brightness, adj.contrast, adj.shadows, adj.highlights))
    if tonal:
        L = _curve_L(L, adj)
    if mode in ("bw", "bw-toned"):
        tx, ty = tone if mode == "bw-toned" else (0, 0)
        if tx or ty:
            x = L / 100.0
            weight = x * (1.0 - x) * 4.0          # strongest in the midtones, none at black/white
            b = weight * (tx * 0.12)
            a = weight * (ty * 0.12)
        else:
            a = L * 0.0
            b = L * 0.0
    elif adj.saturation:
        f = 1.0 + adj.saturation / 50.0 * 0.4
        a = a * f
        b = b * f
    if not tonal and mode == "color" and not adj.saturation:
        return lab
    out = L.bandjoin([a, b])
    return out.copy(interpretation="lab")


def apply_cmy(img: pyvips.Image, adj: Adjustments, max_value: float) -> pyvips.Image:
    """Cyan/Magenta/Yellow balance as per-channel midtone gamma in the output RGB space.
    +Cyan reduces red, +Magenta reduces green, +Yellow reduces blue."""
    if not (adj.cyan or adj.magenta or adj.yellow) or img.bands < 3:
        return img
    fmt = img.format
    gammas = [1.25 ** (adj.cyan / 50.0), 1.25 ** (adj.magenta / 50.0), 1.25 ** (adj.yellow / 50.0)]
    out = ((img / max_value) ** gammas) * max_value
    return out.cast(fmt).copy(interpretation=img.interpretation)


def sharpen_lab(lab: pyvips.Image, level: str, dpi: int) -> pyvips.Image:
    m2 = SHARPEN_M2.get(level, 0.0)
    if m2 <= 0:
        return lab
    sigma = max(0.5, SHARPEN_RADIUS_MM[level] / 25.4 * dpi)
    out = lab.sharpen(sigma=sigma, x1=2.0, y2=10.0, y3=20.0, m1=0.0, m2=m2)
    return out.colourspace("lab") if out.interpretation != "lab" else out
