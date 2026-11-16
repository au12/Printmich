"""PWG Raster (PWG 5102.4) encoder round trips through the decoder."""
from __future__ import annotations

import io

import numpy as np

from printmich.ipp.pwg import CSPACE_SGRAY, CSPACE_SRGB, PwgPage, pack_line, read_document, write_document


def _page(w: int, h: int, **kw) -> PwgPage:
    return PwgPage(width=w, height=h, dpi=300, page_w_pt=round(w / 300 * 72), page_h_pt=round(h / 300 * 72), **kw)


def test_rgb8_round_trip():
    rng = np.random.default_rng(1)
    px = rng.integers(0, 256, size=(120, 90, 3), dtype=np.uint8)
    px[40:60] = 200  # repeated lines exercise line-repeat folding
    buf = io.BytesIO()
    write_document(buf, [(_page(90, 120, media_type="photographic-glossy", quality=5), px)])
    data = buf.getvalue()
    assert data[:4] == b"RaS2"
    pages = read_document(data)
    assert len(pages) == 1
    header, out = pages[0]
    assert header["width"] == 90 and header["height"] == 120
    assert header["color_space"] == CSPACE_SRGB
    assert header["media_type"] == "photographic-glossy"
    assert header["print_quality"] == 5
    np.testing.assert_array_equal(out.reshape(px.shape), px)


def test_rgb16_and_gray_round_trip():
    rng = np.random.default_rng(2)
    px16 = rng.integers(0, 65536, size=(40, 33, 3), dtype=np.uint16)
    gray = rng.integers(0, 256, size=(25, 31, 1), dtype=np.uint8)
    buf = io.BytesIO()
    write_document(buf, [(_page(33, 40, bits_per_color=16), px16), (_page(31, 25, color_space=CSPACE_SGRAY), gray)])
    (h1, o1), (h2, o2) = read_document(buf.getvalue())
    assert h1["bits_per_color"] == 16
    np.testing.assert_array_equal(o1.reshape(px16.shape), px16)
    assert h2["num_colors"] == 1
    np.testing.assert_array_equal(o2.reshape(gray.shape), gray)


def test_uniform_line_compresses_well():
    line = np.full((5100, 3), 255, dtype=np.uint8)
    packed = pack_line(line)
    assert len(packed) < 5100 * 3 / 50
