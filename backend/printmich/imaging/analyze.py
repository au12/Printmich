"""Cheap image-quality heuristics used by the smart picker (run on Immich previews)."""
from __future__ import annotations

import math

import numpy as np
import pyvips


def analyze(data: bytes) -> dict[str, float]:
    img = pyvips.Image.thumbnail_buffer(data, 512, size="down")
    if img.hasalpha():
        img = img.flatten(background=[255] * (img.bands - 1))
    rgb = img.colourspace("srgb") if img.bands < 3 else img
    if rgb.format != "uchar":
        rgb = rgb.cast("uchar")
    arr = np.ndarray(buffer=rgb.write_to_memory(), dtype=np.uint8, shape=(rgb.height, rgb.width, rgb.bands))
    arr = arr[..., :3].astype(np.float32)
    gray = arr @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

    lap = (gray[1:-1, :-2] + gray[1:-1, 2:] + gray[:-2, 1:-1] + gray[2:, 1:-1] - 4 * gray[1:-1, 1:-1])
    # Use the sharpest region (focus is rarely uniform): 90th percentile of block variances.
    h, w = lap.shape
    bs = 32
    variances = [float(lap[y:y + bs, x:x + bs].var()) for y in range(0, h - bs + 1, bs)
                 for x in range(0, w - bs + 1, bs)]
    var = float(np.percentile(variances, 90)) if variances else float(lap.var())
    sharpness = min(1.0, max(0.0, (math.log10(var + 1.0) - 1.6) / 1.6))

    total = gray.size
    hi = float((gray >= 250).sum()) / total
    lo = float((gray <= 4).sum()) / total
    mean = float(gray.mean())
    penalty = max(0.0, hi - 0.02) * 4 + max(0.0, lo - 0.06) * 3
    if mean < 45:
        penalty += (45 - mean) / 90
    elif mean > 215:
        penalty += (mean - 215) / 80
    exposure = max(0.0, 1.0 - penalty)

    rg = arr[..., 0] - arr[..., 1]
    yb = 0.5 * (arr[..., 0] + arr[..., 1]) - arr[..., 2]
    colorfulness = math.sqrt(float(rg.std()) ** 2 + float(yb.std()) ** 2) + 0.3 * math.sqrt(
        float(rg.mean()) ** 2 + float(yb.mean()) ** 2)
    return {
        "sharpness": round(sharpness, 3),
        "exposure": round(exposure, 3),
        "colorfulness": round(min(1.0, colorfulness / 100.0), 3),
        "brightness": round(mean / 255.0, 3),
        "width": img.width,
        "height": img.height,
    }
