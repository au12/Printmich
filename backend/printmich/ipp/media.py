"""PWG media size names (PWG 5101.1) with friendly labels."""
from __future__ import annotations

import re

from ..text import title_label

# keyword -> (width_mm, height_mm, label)
KNOWN_SIZES: dict[str, tuple[float, float, str]] = {
    "oe_photo-l_3.5x5in": (88.9, 127.0, "3.5 × 5 in (L)"),
    "na_index-4x6_4x6in": (101.6, 152.4, "4 × 6 in"),
    "oe_square-photo_4x4in": (101.6, 101.6, "4 × 4 in square"),
    "om_square-photo_89x89mm": (89.0, 89.0, "89 × 89 mm square"),
    "oe_square-photo_5x5in": (127.0, 127.0, "5 × 5 in square"),
    "na_5x7_5x7in": (127.0, 177.8, "5 × 7 in (2L)"),
    "na_govt-letter_8x10in": (203.2, 254.0, "8 × 10 in"),
    "oe_photo-8x8_8x8in": (203.2, 203.2, "8 × 8 in square"),
    "na_letter_8.5x11in": (215.9, 279.4, "8.5 × 11 in (Letter)"),
    "na_legal_8.5x14in": (215.9, 355.6, "8.5 × 14 in (Legal)"),
    "na_10x12_10x12in": (254.0, 304.8, "10 × 12 in"),
    "na_11x14_11x14in": (279.4, 355.6, "11 × 14 in"),
    "na_edp_11x14in": (279.4, 355.6, "11 × 14 in"),
    "na_ledger_11x17in": (279.4, 431.8, "11 × 17 in (Ledger)"),
    "na_super-b_13x19in": (330.2, 482.6, "13 × 19 in (A3+)"),
    "na_arch-b_12x18in": (304.8, 457.2, "12 × 18 in"),
    "jpn_hagaki_100x148mm": (100.0, 148.0, "100 × 148 mm (Hagaki)"),
    "iso_a6_105x148mm": (105.0, 148.0, "A6"),
    "iso_a5_148x210mm": (148.0, 210.0, "A5"),
    "iso_a4_210x297mm": (210.0, 297.0, "A4"),
    "iso_a3_297x420mm": (297.0, 420.0, "A3"),
    "iso_a3-extra_322x445mm": (322.0, 445.0, "A3 Extra"),
    "om_super-a3-b_330x483mm": (330.0, 483.0, "329 × 483 mm (A3+)"),
    "om_a3plus_329x483mm": (329.0, 483.0, "329 × 483 mm (A3+)"),
    "jis_b5_182x257mm": (182.0, 257.0, "B5"),
    "jis_b4_257x364mm": (257.0, 364.0, "B4"),
    "om_210x594mm_210x594mm": (210.0, 594.0, "210 × 594 mm (panorama)"),
    "na_number-10_4.125x9.5in": (104.775, 241.3, "#10 Envelope"),
}

# Order used when presenting sizes in the UI (photo sizes first).
POPULAR_ORDER = [
    "na_index-4x6_4x6in", "na_5x7_5x7in", "oe_photo-l_3.5x5in", "oe_square-photo_5x5in",
    "na_govt-letter_8x10in", "na_letter_8.5x11in", "iso_a4_210x297mm", "na_10x12_10x12in",
    "na_11x14_11x14in", "na_ledger_11x17in", "iso_a3_297x420mm", "na_super-b_13x19in",
]

_DIM_RE = re.compile(r"_(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)(mm|in)$")


def size_from_keyword(kw: str) -> tuple[float, float] | None:
    if kw in KNOWN_SIZES:
        w, h, _ = KNOWN_SIZES[kw]
        return w, h
    m = _DIM_RE.search(kw)
    if not m:
        return None
    w, h, unit = float(m.group(1)), float(m.group(2)), m.group(3)
    f = 25.4 if unit == "in" else 1.0
    return w * f, h * f


def _fmt(v: float) -> str:
    return (f"{v:.2f}".rstrip("0").rstrip(".")) if v % 1 else str(int(v))


def label_for(kw: str | None, width_mm: float | None = None, height_mm: float | None = None) -> str:
    if kw and kw in KNOWN_SIZES:
        return KNOWN_SIZES[kw][2]
    if kw:
        m = _DIM_RE.search(kw)
        if m:
            unit = m.group(3)
            return f"{_fmt(float(m.group(1)))} × {_fmt(float(m.group(2)))} {unit}"
    if width_mm and height_mm:
        wi, hi = width_mm / 25.4, height_mm / 25.4
        if abs(wi * 4 - round(wi * 4)) < 0.02 and abs(hi * 4 - round(hi * 4)) < 0.02:
            return f"{_fmt(round(wi * 4) / 4)} × {_fmt(round(hi * 4) / 4)} in"
        return f"{_fmt(round(width_mm, 1))} × {_fmt(round(height_mm, 1))} mm"
    return kw or "Custom"


def keyword_for_dims(width_hmm: int, height_hmm: int) -> str | None:
    """Find a known keyword for a size given in hundredths of millimetres (±0.6 mm)."""
    for kw, (w, h, _) in KNOWN_SIZES.items():
        if abs(w * 100 - width_hmm) <= 60 and abs(h * 100 - height_hmm) <= 60:
            return kw
    return None


def sort_key(kw: str) -> tuple[int, float]:
    try:
        return (POPULAR_ORDER.index(kw), 0.0)
    except ValueError:
        dims = size_from_keyword(kw) or (9999.0, 9999.0)
        return (len(POPULAR_ORDER), dims[0] * dims[1])


MEDIA_TYPE_LABELS = {
    "stationery": "Plain Paper",
    "stationery-lightweight": "Plain Paper (Lightweight)",
    "stationery-heavyweight": "Plain Paper (Heavyweight)",
    "stationery-fine": "Fine Paper",
    "stationery-coated": "Coated Paper",
    "stationery-inkjet": "Inkjet Paper",
    "photographic": "Photo Paper",
    "photographic-glossy": "Glossy Photo Paper",
    "photographic-high-gloss": "High-Gloss Photo Paper",
    "photographic-semi-gloss": "Semi-Gloss Photo Paper",
    "photographic-satin": "Satin / Luster Photo Paper",
    "photographic-matte": "Matte Photo Paper",
    "photographic-film": "Photo Film",
    "cardstock": "Card Stock",
    "envelope": "Envelope",
    "labels": "Labels",
    "transparency": "Transparency",
    "auto": "Automatic",
}

MEDIA_SOURCE_LABELS = {
    "auto": "Automatic",
    "main": "Main Tray",
    "top": "Top Feed",
    "rear": "Rear Tray",
    "manual": "Manual Feed",
    "by-pass-tray": "Bypass Tray",
    "alternate": "Alternate Tray",
    "photo": "Photo Tray",
    "tray-1": "Tray 1",
    "tray-2": "Tray 2",
    "disc": "Disc Tray",
    "envelope": "Envelope Feeder",
}

def humanize_keyword(kw: str) -> str:
    """'com.canon-photo-paper-pro-luster' -> 'Photo Paper Pro Luster'."""
    base = kw
    for prefix in ("com.", "org.", "custom-media-type-", "custom-"):
        if base.startswith(prefix):
            base = base[len(prefix):]
    if "-" in base and "." in base.split("-", 1)[0]:
        base = base.split("-", 1)[1]
    if base.startswith("canon-") or base.startswith("canon_"):
        base = base[6:]
    words = re.split(r"[-_.]+", base)
    return " ".join(w.upper() if len(w) <= 2 and w.isalpha() and w not in ("of", "on", "in") else w.capitalize()
                    for w in words if w)


def media_type_label(kw: str, strings: dict[str, str] | None = None) -> str:
    if strings:
        for key in (f"media-type.{kw}", kw):
            if key in strings:
                return title_label(strings[key])
    return MEDIA_TYPE_LABELS.get(kw) or humanize_keyword(kw)


def media_source_label(kw: str, strings: dict[str, str] | None = None) -> str:
    if strings:
        for key in (f"media-source.{kw}", kw):
            if key in strings:
                return title_label(strings[key])
    return MEDIA_SOURCE_LABELS.get(kw) or humanize_keyword(kw)


def parse_strings_file(data: bytes) -> dict[str, str]:
    """Parse an Apple-style .strings file served at printer-strings-uri."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-16", "replace")
    out: dict[str, str] = {}
    for m in re.finditer(r'"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"\s*;', text):
        out[m.group(1).replace('\\"', '"')] = m.group(2).replace('\\"', '"')
    return out
