"""Built-in paper library for the Canon imagePROGRAF PRO-310 (and PRO-300/PRO-1000 class
printers), plus logic for mapping each paper onto the media types a printer advertises.

Calibration values are *starting points*: matte and fine-art media have a lower
maximum density (Dmax) and a smaller gamut than glossy media, so they default to
perceptual rendering, a gentle midtone lift and stronger output sharpening. Refine
them with the calibration chart and color-pattern prints in the Papers screen.
"""
from __future__ import annotations

import re
from typing import Any

from .models import Adjustments, Margins, Paper, PaperCalibration

GLOSSY_GENERIC = ["photographic-high-gloss", "photographic-glossy", "photographic"]
LUSTER_GENERIC = ["photographic-satin", "photographic-semi-gloss", "photographic-glossy", "photographic"]
SEMI_GENERIC = ["photographic-semi-gloss", "photographic-satin", "photographic-glossy", "photographic"]
MATTE_GENERIC = ["photographic-matte", "stationery-fine", "photographic", "stationery-heavyweight", "stationery"]
PLAIN_GENERIC = ["stationery", "stationery-inkjet", "auto"]

FA_MARGINS = Margins(top=25, bottom=25, left=6, right=6)

PHOTO_SIZES = ["na_index-4x6_4x6in", "na_5x7_5x7in", "na_govt-letter_8x10in", "na_letter_8.5x11in",
               "iso_a4_210x297mm", "na_ledger_11x17in", "iso_a3_297x420mm", "na_super-b_13x19in"]
LARGE_SIZES = ["na_letter_8.5x11in", "iso_a4_210x297mm", "na_ledger_11x17in", "iso_a3_297x420mm",
               "na_super-b_13x19in"]


def _cal(intent: str, sharp: str, notes: str = "", **adj: int) -> PaperCalibration:
    return PaperCalibration(intent=intent, bpc=True, sharpening=sharp, adjust=Adjustments(**adj), notes=notes)


BUILTIN_PAPERS: list[Paper] = [
    Paper(
        id="canon-pt-101", name="Photo Paper Pro Platinum", code="PT-101", finish="high-gloss",
        feeds=["top", "manual"], default_feed="top", borderless=True,
        media_type_hints=["pro platinum", "platinum"], media_type_generic=GLOSSY_GENERIC,
        calibration=_cal("relative", "low", "Neutral starting point; Chroma Optimizer evens out gloss."),
        sizes=["na_index-4x6_4x6in", "na_5x7_5x7in", "na_letter_8.5x11in", "iso_a4_210x297mm",
               "iso_a3_297x420mm", "na_super-b_13x19in"],
        notes="Canon's deepest-black, highest-gloss paper. Load printable side up in the top feed; let prints "
              "dry about 24 hours before framing or stacking.",
        tint="#fbfbfa", sheen=1.0,
    ),
    Paper(
        id="canon-pp-201", name="Photo Paper Plus Glossy II", code="PP-201 / PP-208 / PP-301", finish="glossy",
        feeds=["top", "manual"], default_feed="top", borderless=True,
        media_type_hints=["plus glossy ii", "glossy ii", "plus glossy", "glossyii"],
        media_type_generic=["photographic-glossy", "photographic-high-gloss", "photographic"],
        calibration=_cal("relative", "low"),
        sizes=["na_index-4x6_4x6in", "na_5x7_5x7in", "na_govt-letter_8x10in", "na_letter_8.5x11in",
               "iso_a4_210x297mm", "na_super-b_13x19in"],
        notes="Everyday high-gloss photo paper — perfect for 4×6 snapshots and the photo-of-the-day.",
        tint="#fafaf8", sheen=0.9,
    ),
    Paper(
        id="canon-lu-101", name="Photo Paper Pro Luster", code="LU-101", finish="luster",
        feeds=["top", "manual"], default_feed="top", borderless=True,
        media_type_hints=["pro luster", "luster", "lustre"], media_type_generic=LUSTER_GENERIC,
        calibration=_cal("relative", "low"),
        sizes=LARGE_SIZES,
        notes="Pearl-like lab finish that resists glare and fingerprints. A great default for framed prints.",
        tint="#f8f7f3", sheen=0.6,
    ),
    Paper(
        id="canon-sg-201", name="Photo Paper Plus Semi-gloss", code="SG-201", finish="semi-gloss",
        feeds=["top", "manual"], default_feed="top", borderless=True,
        media_type_hints=["plus semi gloss", "semi gloss", "semigloss", "satin"], media_type_generic=SEMI_GENERIC,
        calibration=_cal("relative", "low"),
        sizes=["na_index-4x6_4x6in", "na_5x7_5x7in", "na_govt-letter_8x10in", "na_letter_8.5x11in",
               "na_super-b_13x19in"],
        notes="Soft satin sheen with less glare than glossy.",
        tint="#f8f7f4", sheen=0.5,
    ),
    Paper(
        id="canon-mp-101", name="Matte Photo Paper", code="MP-101", finish="matte", black_ink="matte",
        feeds=["top", "manual"], default_feed="top", borderless=True,
        media_type_hints=["matte photo paper", "matte photo"], media_type_generic=MATTE_GENERIC,
        calibration=_cal("perceptual", "standard", "Matte prints read darker; midtones lifted slightly.",
                         brightness=6, contrast=4, saturation=6, shadows=4),
        sizes=["na_index-4x6_4x6in", "na_letter_8.5x11in", "iso_a4_210x297mm", "iso_a3_297x420mm",
               "na_super-b_13x19in"],
        notes="Glare-free matte surface printed with Matte Black ink. Lower density than glossy, so Printmich "
              "lifts midtones a touch by default.",
        tint="#f6f5f1", sheen=0.08,
    ),
    Paper(
        id="canon-pm-101", name="Photo Paper Pro Premium Matte", code="PM-101", finish="premium-matte",
        black_ink="matte", feeds=["manual"], default_feed="manual", borderless=True,
        media_type_hints=["pro premium matte", "premium matte", "propremiummatte"], media_type_generic=MATTE_GENERIC,
        calibration=_cal("perceptual", "standard", brightness=4, contrast=4, saturation=4, shadows=4),
        sizes=LARGE_SIZES,
        notes="Heavier, brighter premium matte for portfolios. Registered on the PRO-310 as "
              "“Photo Paper Pro Premium Matte A”.",
        tint="#f8f8f5", sheen=0.06,
    ),
    Paper(
        id="canon-fa-sm", name="Premium Fine Art Smooth", code="FA-SM1 / FA-SM2", finish="fine-art-smooth",
        black_ink="matte", feeds=["manual"], default_feed="manual", borderless=True,
        recommended_margins=FA_MARGINS,
        media_type_hints=["fine art smooth", "premium fine art smooth", "fineart smooth"],
        media_type_generic=MATTE_GENERIC,
        calibration=_cal("perceptual", "standard", brightness=8, contrast=6, saturation=8, shadows=6),
        sizes=LARGE_SIZES,
        notes="Smooth museum-grade fine art paper. Manual feed only. Canon recommends at least 25 mm top and "
              "bottom margins on fine art media.",
        tint="#f4f1e8", sheen=0.03,
    ),
    Paper(
        id="canon-fa-rg", name="Premium Fine Art Rough", code="FA-RG1", finish="fine-art-rough",
        black_ink="matte", feeds=["manual"], default_feed="manual", borderless=True,
        recommended_margins=FA_MARGINS,
        media_type_hints=["fine art rough", "premium fine art rough", "fineart rough"],
        media_type_generic=MATTE_GENERIC,
        calibration=_cal("perceptual", "high", "Textured surface softens detail — stronger sharpening.",
                         brightness=8, contrast=6, saturation=8, shadows=6),
        sizes=LARGE_SIZES,
        notes="Watercolor-style textured fine art paper. Manual feed only; 25 mm top/bottom margins recommended.",
        tint="#f3efe4", sheen=0.02,
    ),
    Paper(
        id="generic-baryta", name="Baryta Photo Paper", brand="Third-party", finish="baryta",
        feeds=["manual"], default_feed="manual", borderless=True,
        media_type_hints=["baryta"], media_type_generic=SEMI_GENERIC,
        calibration=_cal("relative", "low"),
        notes="Inkjet baryta papers (e.g. Canson Baryta Photographique, Hahnemühle Photo Rag Baryta). Use "
              "the printer's Baryta Photo Paper media type for consistent gloss.",
        tint="#f7f5ef", sheen=0.55,
    ),
    Paper(
        id="generic-light-photo", name="Lightweight Photo Paper", brand="Third-party", finish="glossy",
        feeds=["top", "manual"], default_feed="top", borderless=True,
        media_type_hints=["lightweight photo", "light photo"], media_type_generic=GLOSSY_GENERIC,
        calibration=_cal("relative", "low"),
        notes="Third-party photo papers about 0.1–0.3 mm thick.",
        tint="#fafaf8", sheen=0.8,
    ),
    Paper(
        id="generic-heavy-photo", name="Heavyweight Photo Paper", brand="Third-party", finish="luster",
        feeds=["manual"], default_feed="manual", borderless=True,
        media_type_hints=["heavyweight photo", "heavy photo"], media_type_generic=LUSTER_GENERIC,
        calibration=_cal("relative", "low"),
        notes="Third-party photo papers about 0.3–0.6 mm thick.",
        tint="#f8f7f3", sheen=0.6,
    ),
    Paper(
        id="generic-heavy-fineart", name="Heavyweight Fine Art Paper", brand="Third-party",
        finish="fine-art-smooth", black_ink="matte", feeds=["top", "manual"], default_feed="manual",
        borderless=True, recommended_margins=FA_MARGINS,
        media_type_hints=["heavyweight fine art", "heavy art"], media_type_generic=MATTE_GENERIC,
        calibration=_cal("perceptual", "standard", brightness=8, contrast=6, saturation=8, shadows=6),
        notes="Third-party fine art papers about 0.1–0.3 mm thick.",
        tint="#f4f1e8", sheen=0.03,
    ),
    Paper(
        id="generic-xheavy-fineart", name="Extra Heavyweight Fine Art Paper", brand="Third-party",
        finish="fine-art-rough", black_ink="matte", feeds=["manual"], default_feed="manual", borderless=True,
        recommended_margins=FA_MARGINS,
        media_type_hints=["extra heavyweight fine art", "ex hvy art", "extra heavy"], media_type_generic=MATTE_GENERIC,
        calibration=_cal("perceptual", "high", brightness=8, contrast=6, saturation=8, shadows=6),
        notes="Third-party fine art papers about 0.3–0.6 mm thick (e.g. Hahnemühle Photo Rag 308).",
        tint="#f3efe4", sheen=0.02,
    ),
    Paper(
        id="generic-hd-fineart", name="Highest Density Fine Art Paper", brand="Third-party",
        finish="fine-art-smooth", black_ink="matte", feeds=["manual"], default_feed="manual", borderless=True,
        recommended_margins=FA_MARGINS,
        media_type_hints=["highest density", "high density art"], media_type_generic=MATTE_GENERIC,
        calibration=_cal("perceptual", "standard", brightness=6, contrast=6, saturation=6, shadows=6),
        notes="For very thirsty, thick fine art stock that takes more ink.",
        tint="#f4f1e8", sheen=0.03,
    ),
    Paper(
        id="generic-canvas", name="Canvas", brand="Third-party", finish="canvas", black_ink="matte",
        feeds=["top", "manual"], default_feed="manual", borderless=True,
        media_type_hints=["canvas"], media_type_generic=MATTE_GENERIC,
        calibration=_cal("perceptual", "high", brightness=6, contrast=8, saturation=10, shadows=6),
        notes="Inkjet canvas. Strong texture — use generous sharpening and avoid fine captions.",
        tint="#efe9dc", sheen=0.1,
    ),
    Paper(
        id="generic-washi", name="Japanese Paper Washi", brand="Third-party", finish="washi", black_ink="matte",
        feeds=["top", "manual"], default_feed="manual", borderless=True,
        media_type_hints=["washi", "japanese paper"], media_type_generic=MATTE_GENERIC,
        calibration=_cal("perceptual", "standard", brightness=10, contrast=6, saturation=6, shadows=8),
        notes="Thin, absorbent washi. Expect softer blacks; lifted midtones by default.",
        tint="#f1ece0", sheen=0.02,
    ),
    Paper(
        id="canon-plain", name="Plain Paper", code="", finish="plain", black_ink="matte",
        feeds=["top"], default_feed="top", borderless=False,
        media_type_hints=["plain"], media_type_generic=PLAIN_GENERIC,
        calibration=_cal("perceptual", "standard", brightness=5),
        sizes=["na_letter_8.5x11in", "iso_a4_210x297mm"],
        notes="For proofs, layout checks and test pages.",
        tint="#fdfdfd", sheen=0.0,
    ),
]

BUILTIN_BY_ID = {p.id: p for p in BUILTIN_PAPERS}

SOURCE_PREFERENCES = {
    "top": ["top", "main", "auto", "rear", "tray-1", "photo", "alternate"],
    "manual": ["manual", "by-pass-tray", "rear", "alternate", "envelope"],
}


def _norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"^(com|org)\.[a-z0-9]+-", "", s)
    s = re.sub(r"[-_.]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def resolve_media_type(paper: Paper, types: list[dict[str, str]], override: str = "auto") -> dict[str, Any]:
    """Pick the printer media-type keyword for a paper.

    Returns {"keyword", "label", "how"} where how is one of override/exact/hint/generic/none.
    """
    keywords = [t["keyword"] for t in types]
    labels = {t["keyword"]: t.get("label") or t["keyword"] for t in types}
    if override and override != "auto":
        return {"keyword": override, "label": labels.get(override, override), "how": "override"}
    if paper.media_type and paper.media_type != "auto" and (not keywords or paper.media_type in keywords):
        return {"keyword": paper.media_type, "label": labels.get(paper.media_type, paper.media_type),
                "how": "paper"}
    if not keywords:
        kw = paper.media_type_generic[0] if paper.media_type_generic else None
        return {"keyword": kw, "label": kw, "how": "generic" if kw else "none"}
    best: tuple[int, str] | None = None
    for kw in keywords:
        hay = f"{_norm(kw)} | {_norm(labels.get(kw, ''))}"
        for hint in paper.media_type_hints:
            h = _norm(hint)
            if h and h in hay:
                score = len(h) * 10 - len(hay) // 10
                if best is None or score > best[0]:
                    best = (score, kw)
    if best:
        return {"keyword": best[1], "label": labels.get(best[1], best[1]), "how": "hint"}
    for g in paper.media_type_generic:
        if g in keywords:
            return {"keyword": g, "label": labels.get(g, g), "how": "generic"}
    return {"keyword": None, "label": "Printer default", "how": "none"}


def resolve_media_source(paper: Paper, sources: list[str], requested: str = "auto") -> str | None:
    if requested and requested != "auto":
        return requested if (not sources or requested in sources) else None
    if not sources:
        return None
    for feed in [paper.default_feed] + [f for f in paper.feeds if f != paper.default_feed]:
        for cand in SOURCE_PREFERENCES.get(feed, []):
            if cand in sources:
                return cand
    return None
