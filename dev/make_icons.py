"""Draw the Printmich logo: the PRO-310's ten ink tanks arched over a printer that is
handing you a photo, with a sweep arrow for "again tomorrow".

    python dev/make_icons.py

Writes icon.svg / icon.png (512 px) at the repo root, the favicon + PWA icons in
frontend/public, and frontend/src/assets/logo-mark.svg, the simplified mark the web UI
inlines and animates (its parts carry lm-* classes for that).
"""
from __future__ import annotations

import math
from pathlib import Path

import pyvips

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "frontend" / "public"
ASSETS = ROOT / "frontend" / "src" / "assets"

# key, light, dark — left to right as they sit in the arch.
TANKS = [
    ("mbk", "#4a5162", "#2a2e39"),
    ("pbk", "#2b2f3a", "#111318"),
    ("c", "#3cc0fa", "#0f8fdc"),
    ("m", "#fa52a4", "#d51f7a"),
    ("y", "#ffd84a", "#f4a800"),
    ("r", "#fb5a4c", "#d6281f"),
    ("gy", "#a9b0bc", "#727a87"),
    ("pc", "#86d2fb", "#45a4e6"),
    ("pm", "#fb93c6", "#ea5aa0"),
    ("co", "#ffffff", "#cfd8e6"),
]

ARROW_C = (250.0, 240.0)
ARROW_R = (222.0, 166.0)


def _arrow(start: float = 138.0, end: float = 318.0, w0: float = 3.0, w1: float = 21.0, head: float = 50.0) -> str:
    """A sweep arrow along an ellipse that swells from tail to head (angles in degrees, y down)."""
    cx, cy = ARROW_C
    rx, ry = ARROW_R
    n = 72
    outer, inner = [], []
    for i in range(n + 1):
        f = i / n
        t = math.radians(start + (end - start) * f)
        w = w0 + (w1 - w0) * f ** 0.85
        x, y = cx + rx * math.cos(t), cy + ry * math.sin(t)
        # unit normal of the ellipse at t
        nx, ny = math.cos(t) / rx, math.sin(t) / ry
        m = math.hypot(nx, ny)
        nx, ny = nx / m, ny / m
        outer.append((x + nx * w / 2, y + ny * w / 2))
        inner.append((x - nx * w / 2, y - ny * w / 2))
    t = math.radians(end)
    x, y = cx + rx * math.cos(t), cy + ry * math.sin(t)
    tx, ty = -rx * math.sin(t), ry * math.cos(t)
    m = math.hypot(tx, ty)
    tx, ty = tx / m, ty / m
    nx, ny = -ty, tx
    tip = (x + tx * head, y + ty * head)
    a = (x - nx * head * 0.52, y - ny * head * 0.52)
    b = (x + nx * head * 0.52, y + ny * head * 0.52)
    pts = [*outer, a, tip, b, *inner[::-1]]
    return "M" + " L".join(f"{px:.1f} {py:.1f}" for px, py in pts) + " Z"


def _tank_pos(i: int, w: float, pitch: float) -> tuple[float, float]:
    """Top-left corner of tank i: an arch that peaks over the middle of the printer."""
    x = 256 - (9 * pitch + w) / 2 + i * pitch
    u = (i - 4.5) / 4.5
    return x, 140 + 56 * u * u


def svg(size: int = 512, *, radius: float = 0.22, detail: bool = True, classes: bool = False, tile: bool = True) -> str:
    def cls(name: str, extra: str = "") -> str:
        return f' class="{name}"{extra}' if classes else ""

    w, h, pitch = (31.0, 74.0, 41.6) if detail else (33.0, 76.0, 41.6)
    defs = [
        '<radialGradient id="lm-bg" cx="50%" cy="46%" r="70%"><stop offset="0" stop-color="#1b3676"/>'
        '<stop offset="0.6" stop-color="#101d44"/><stop offset="1" stop-color="#0a1330"/></radialGradient>',
        '<linearGradient id="lm-arrow" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#2a6fe0"/>'
        '<stop offset="1" stop-color="#5aa9ff"/></linearGradient>',
        '<linearGradient id="lm-body" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3b4354"/>'
        '<stop offset="1" stop-color="#232833"/></linearGradient>',
        '<linearGradient id="lm-base" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1f2430"/>'
        '<stop offset="1" stop-color="#12151c"/></linearGradient>',
        '<linearGradient id="lm-sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2a3a94"/>'
        '<stop offset="0.3" stop-color="#e9788a"/><stop offset="0.6" stop-color="#ffc86b"/>'
        '<stop offset="1" stop-color="#3a4aa0"/></linearGradient>',
        '<clipPath id="lm-photo-clip"><path d="M221 343 L391 343 L408 387 Q314 397 213 388 Z"/></clipPath>',
    ]
    for key, light, dark in TANKS:
        defs.append(f'<linearGradient id="lm-{key}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{light}"/>'
                    f'<stop offset="1" stop-color="{dark}"/></linearGradient>')

    out: list[str] = []
    if tile:
        out.append(f'<rect width="512" height="512" rx="{radius * 512:.1f}" fill="url(#lm-bg)"/>')
        if radius:
            out.append(f'<rect x="1" y="1" width="510" height="510" rx="{radius * 512 - 1:.1f}" fill="none" '
                       f'stroke="#8fb4ff" stroke-opacity="0.14" stroke-width="2"/>')

    g: list[str] = []
    if detail:
        g.append('<ellipse cx="256" cy="336" rx="212" ry="150" fill="none" stroke="#5f93ff" stroke-opacity="0.16" stroke-width="1.5"/>')
        g.append('<ellipse cx="256" cy="336" rx="236" ry="172" fill="none" stroke="#5f93ff" stroke-opacity="0.08" stroke-width="1.5"/>')
    g.append(f'<path{cls("lm-arrow")} d="{_arrow()}" fill="url(#lm-arrow)"/>')

    # tanks
    dots = []
    for i, (key, _light, dark) in enumerate(TANKS):
        x, y = _tank_pos(i, w, pitch)
        black = key in ("mbk", "pbk")
        stroke = "#69728a" if black else "#ffffff"
        so = 0.9 if black else 0.28
        parts = [f'<rect x="{x:.1f}" y="{y:.1f}" width="{w}" height="{h}" rx="6.5" fill="url(#lm-{key})" '
                 f'stroke="{stroke}" stroke-opacity="{so}" stroke-width="1.6"/>']
        if detail:
            notch = "#0b0d12" if black else dark
            parts.append(f'<rect x="{x + w / 2 - 6.5:.1f}" y="{y + 8:.1f}" width="13" height="4" rx="2" fill="{notch}" fill-opacity="0.7"/>')
            parts.append(f'<circle cx="{x + w / 2:.1f}" cy="{y + h - 17:.1f}" r="4.6" fill="{"#0b0d12" if black else dark}" '
                         f'fill-opacity="{0.9 if key != "co" else 0.45}"/>')
            parts.append(f'<rect x="{x + 4:.1f}" y="{y + 16:.1f}" width="3" height="{h - 40}" rx="1.5" fill="#ffffff" fill-opacity="{0.1 if black else 0.3}"/>')
            dc = {"mbk": "#5b6477", "pbk": "#3a4152"}.get(key, dark)
            dots.append(f'<circle cx="{x + w / 2:.1f}" cy="{y + h + 13:.1f}" r="3.2" fill="{dc}"/>')
        g.append(f'<g{cls("lm-tank", f" style=\"--i:{i}\"")}>{"".join(parts)}</g>')
    if detail:
        g.append(f'<g{cls("lm-dots")}>{"".join(dots)}</g>')

    # printer
    p: list[str] = []
    if detail:
        p.append('<ellipse cx="258" cy="408" rx="196" ry="12" fill="#04070f" fill-opacity="0.5"/>')
    p.append('<path d="M150 256 H374 Q386 256 388 268 L390 280 H134 L136 268 Q138 256 150 256 Z" fill="#2a303d"/>')
    p.append('<path d="M150 256 H374 Q384 256 387 264 H137 Q140 256 150 256 Z" fill="#48516a"/>')
    p.append('<rect x="96" y="272" width="332" height="58" rx="13" fill="url(#lm-body)"/>')
    p.append('<rect x="96" y="272" width="332" height="14" rx="7" fill="#4a5368" fill-opacity="0.75"/>')
    p.append('<rect x="96" y="316" width="332" height="84" rx="13" fill="url(#lm-base)"/>')
    p.append('<path d="M109 316 H150 V400 H109 Q96 400 96 387 V329 Q96 316 109 316 Z" fill="#2b313e"/>')
    p.append('<rect x="204" y="303" width="116" height="4" rx="2" fill="#0a0c11"/>')
    p.append(f'<rect{cls("lm-led")} x="258" y="303" width="44" height="4" rx="2" fill="#4c9bff"/>')
    p.append('<rect x="194" y="330" width="206" height="38" rx="6" fill="#06080c"/>')
    p.append(f'<rect{cls("lm-led")} x="408" y="345" width="12" height="4" rx="2" fill="#4c9bff"/>')
    p.append('<path d="M200 392 L424 389 Q442 390 446 402 L446 405 Q322 420 196 408 Z" fill="#0e1118"/>')
    # the print coming out
    ph: list[str] = [
        '<path d="M214 338 L398 338 L418 392 Q316 404 204 394 Z" fill="#fbfcfe"/>',
        '<g clip-path="url(#lm-photo-clip)">',
        '<rect x="205" y="340" width="212" height="60" fill="url(#lm-sky)"/>',
        '<circle cx="318" cy="370" r="8" fill="#fff3cf"/>',
        '<path d="M205 380 L234 362 L250 370 L274 354 L298 372 L318 368 L342 357 L364 370 L384 361 L417 378 L417 382 L205 382 Z" fill="#222c66"/>',
        '<path d="M274 354 L281 361 L275 362 L268 359 Z M342 357 L349 363 L343 364 L336 361 Z" fill="#f4f7ff" fill-opacity="0.9"/>',
        '<path d="M205 381 H417 V400 H205 Z" fill="#2d3c8c"/>',
        '<path d="M290 383 H346 M298 387 H338 M306 391 H330" stroke="#ffc86b" stroke-opacity="0.7" stroke-width="1.6" stroke-linecap="round"/>',
        '</g>',
    ]
    p.append(f'<g{cls("lm-photo")}>{"".join(ph)}</g>')
    g.append(f'<g{cls("lm-printer")}>{"".join(p)}</g>')

    inner = "".join(g)
    if tile:
        # pull the drawing in from the rounded corners
        inner = f'<g transform="translate(256 258) scale(0.985) translate(-253 -246)">{inner}</g>'
        box = "0 0 512 512"
    else:
        box = "14 62 484 360"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size if tile else round(size * 360 / 484)}" '
            f'viewBox="{box}"><defs>{"".join(defs)}</defs>{"".join(out)}{inner}</svg>')


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
    (PUBLIC / "icon.svg").write_text(svg(512))
    # Small sizes drop the fine detail (tank notches, dots, rings) so the shapes stay readable.
    (PUBLIC / "favicon.svg").write_text(svg(64, detail=False))
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "logo-mark.svg").write_text(svg(512, detail=False, classes=True))
    print("icons written")


if __name__ == "__main__":
    main()
