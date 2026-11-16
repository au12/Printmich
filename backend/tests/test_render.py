"""The page renderer: page geometry, rotation, captions and encoded output."""
from __future__ import annotations

from pathlib import Path

import pyvips

from printmich.imaging.icc import profile_description
from printmich.imaging.render import RenderSpec, compute_crop, render
from printmich.ipp.pwg import read_document
from printmich.models import Caption, Layout


def test_borderless_4x6_fills_the_sheet(photo_bytes, tmp_path: Path):
    spec = RenderSpec(page_w_mm=101.6, page_h_mm=152.4, dpi=300, output="jpeg", layout=Layout(borderless=True))
    r = render(photo_bytes, spec, tmp_path, "borderless")
    # Page pixels are in feed (portrait) orientation; the landscape photo is turned to fit.
    assert (r.width_px, r.height_px) == (1200, 1800)
    assert r.geometry["rotated"] is True
    assert r.geometry["photo_px"] == [1800, 1200]
    assert r.effective_ppi == 300
    out = pyvips.Image.new_from_file(str(r.document))
    assert (out.width, out.height) == (1200, 1800)


def test_bordered_letter_with_caption_as_pwg(photo_bytes, tmp_path: Path):
    lay = Layout(borderless=False, caption=Caption(enabled=True))
    spec = RenderSpec(page_w_mm=215.9, page_h_mm=279.4, dpi=300, output="pwg", layout=lay, out_space="adobe-rgb",
                      caption_text="Banff, Alberta, July 2023", media_type="photographic-satin", quality=5)
    r = render(photo_bytes, spec, tmp_path, "letter")
    assert r.mime == "image/pwg-raster"
    assert (r.width_px, r.height_px) == (2550, 3300)
    g = r.geometry
    assert g["caption"] is True
    # The caption needs room, so the bottom margin is deeper than the others.
    assert g["margins_mm"]["bottom"] > g["margins_mm"]["top"]
    # Upsampled to fill the page, so effective detail drops below the device resolution.
    assert 100 < r.effective_ppi < 300
    (header, pixels), = read_document(r.document.read_bytes())
    assert header["width"] == 2550 and header["height"] == 3300
    assert header["color_space"] == 20  # Adobe RGB
    assert header["media_type"] == "photographic-satin"
    # Margins are paper white.
    assert pixels.reshape(3300, 2550, 3)[5, 5].tolist() == [255, 255, 255]


def test_black_and_white_is_neutral(photo_bytes, tmp_path: Path):
    spec = RenderSpec(page_w_mm=101.6, page_h_mm=152.4, dpi=150, output="jpeg", color_mode="bw",
                      layout=Layout(borderless=True))
    r = render(photo_bytes, spec, tmp_path, "bw")
    img = pyvips.Image.new_from_file(str(r.document))
    if img.bands >= 3:
        diff = (img[0] - img[1]).abs().max() + (img[1] - img[2]).abs().max()
        assert diff <= 2


def test_jpeg_output_embeds_the_profile(photo_bytes, tmp_path: Path):
    spec = RenderSpec(page_w_mm=127, page_h_mm=177.8, dpi=300, output="jpeg", out_space="adobe-rgb",
                      layout=Layout(borderless=True))
    r = render(photo_bytes, spec, tmp_path, "wide")
    img = pyvips.Image.new_from_file(str(r.document))
    assert img.get_typeof("icc-profile-data") != 0
    assert "Adobe RGB" in profile_description(img.get("icc-profile-data"))


def test_crop_keeps_focus_inside_frame():
    x, y, w, h = compute_crop(6000, 4000, 1.0, 0.95, 0.5)
    assert (w, h) == (4000, 4000)
    assert x == 2000  # clamped to the right edge
    x, y, w, h = compute_crop(4000, 6000, 1.5, 0.5, 0.1)
    assert (w, h) == (4000, round(4000 / 1.5))
    assert y == 0
