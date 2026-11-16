"""Render the Printmich icon (the ten PRO-310 inks as a level meter) to SVG and PNG.

    python dev/make_icons.py

Writes icon.svg / icon.png (512 px) at the repo root and the favicon + PWA icons in frontend/public.
"""
from __future__ import annotations

from pathlib import Path

import pyvips

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "frontend" / "public"

# Same order and heights as InkMark in frontend/src/components/Ink.tsx.
# Both blacks are drawn in paper white so they read on graphite; matte black is dimmed.
BARS = [
    ("#ededed", 0.62, 0.55), ("#ededed", 0.78, 1), ("#8e8e8e", 0.52, 1), ("#00a3e0", 1.0, 1), ("#73cdeb", 0.84, 1),
    ("#e2007a", 0.94, 1), ("#f28dc0", 0.70, 1), ("#ffdd00", 0.88, 1), ("#e4002b", 0.60, 1), ("#d9d9d9", 0.44, 1),
]


def svg(size: int = 512, radius: float = 0.22, bar_w: float = 0.043, gap: float = 0.0156, max_h: float = 0.5) -> str:
    s = size
    total_w = len(BARS) * bar_w * s + (len(BARS) - 1) * gap * s
    x0 = (s - total_w) / 2
    base = s / 2 + max_h * s / 2
    rects = []
    for i, (color, h, alpha) in enumerate(BARS):
        bh = h * max_h * s
        x = x0 + i * (bar_w + gap) * s
        rects.append(f'<rect x="{x:.2f}" y="{base - bh:.2f}" width="{bar_w * s:.2f}" height="{bh:.2f}" '
                     f'rx="{bar_w * s * 0.22:.2f}" fill="{color}" fill-opacity="{alpha}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{s}" height="{s}" viewBox="0 0 {s} {s}">'
            f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="#2c2c2c"/><stop offset="1" stop-color="#1b1b1b"/></linearGradient></defs>'
            f'<rect width="{s}" height="{s}" rx="{radius * s:.2f}" fill="url(#g)"/>'
            f'<rect x="0.5" y="0.5" width="{s - 1}" height="{s - 1}" rx="{radius * s - 0.5:.2f}" fill="none" '
            f'stroke="#ffffff" stroke-opacity="0.07"/>' + "".join(rects) + "</svg>")


def png(path: Path, size: int, **kw) -> None:
    img = pyvips.Image.svgload_buffer(svg(512, **kw).encode(), scale=size / 512)
    img.pngsave(str(path), compression=9, strip=True)


def main() -> None:
    (ROOT / "icon.svg").write_text(svg(512))
    png(ROOT / "icon.png", 512)
    png(PUBLIC / "icon-512.png", 512)
    png(PUBLIC / "icon-192.png", 192)
    # iOS draws its own rounded mask, so the touch icon is full-bleed.
    png(PUBLIC / "apple-touch-icon.png", 180, radius=0)
    # Favicon: fewer, chunkier bars would lose the idea; keep all ten, slightly taller.
    (PUBLIC / "favicon.svg").write_text(svg(64, bar_w=0.06, gap=0.02, max_h=0.56))
    print("icons written")


if __name__ == "__main__":
    main()
