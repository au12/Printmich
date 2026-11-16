"""PWG Raster (PWG 5102.4) encoder/decoder.

PWG raster is the native page format of IPP Everywhere printers. Sending fully
rendered raster pages at the printer's native resolution gives Printmich exact
control over every output pixel (crop, borders, color transform, sharpening).

The encoder is vectorised with numpy: each line is run-length coded with the
PackBits-like scheme from the spec, and identical consecutive lines are folded
using the line-repeat byte.
"""
from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import BinaryIO

import numpy as np

SYNC = b"RaS2"
HEADER_SIZE = 1796

# cups_cspace_t values used by PWG raster
CSPACE_SGRAY = 18
CSPACE_SRGB = 19
CSPACE_ADOBERGB = 20

QUALITY = {"draft": 3, "normal": 4, "high": 5}


@dataclass
class PwgPage:
    width: int                     # pixels
    height: int                    # pixels
    dpi: int
    page_w_pt: int                 # media width in points (1/72")
    page_h_pt: int                 # media height in points
    color_space: int = CSPACE_SRGB
    bits_per_color: int = 8
    media_type: str = ""
    media_color: str = ""
    content_optimize: str = "photo"
    rendering_intent: str = ""
    page_size_name: str = ""
    quality: int = 0               # 0 default, 3 draft, 4 normal, 5 high
    total_pages: int = 1
    copies: int = 1
    vendor: dict = field(default_factory=dict)

    @property
    def num_colors(self) -> int:
        return 1 if self.color_space == CSPACE_SGRAY else 3

    @property
    def bytes_per_pixel(self) -> int:
        return self.num_colors * self.bits_per_color // 8

    @property
    def bytes_per_line(self) -> int:
        return self.width * self.bytes_per_pixel


def _cstr(s: str, n: int = 64) -> bytes:
    b = s.encode("utf-8")[: n - 1]
    return b + b"\x00" * (n - len(b))


def build_header(p: PwgPage) -> bytes:
    h = bytearray(HEADER_SIZE)
    h[0:64] = _cstr("PwgRaster")
    h[64:128] = _cstr(p.media_color)
    h[128:192] = _cstr(p.media_type)
    h[192:256] = _cstr(p.content_optimize)
    # 256..267 reserved
    struct.pack_into(">I", h, 268, 0)                 # CutMedia
    struct.pack_into(">I", h, 272, 0)                 # Duplex
    struct.pack_into(">II", h, 276, p.dpi, p.dpi)     # HWResolution
    struct.pack_into(">I", h, 300, 0)                 # InsertSheet
    struct.pack_into(">I", h, 304, 0)                 # Jog
    struct.pack_into(">I", h, 308, 0)                 # LeadingEdge (ShortEdgeFirst)
    struct.pack_into(">I", h, 324, 0)                 # MediaPosition (auto)
    struct.pack_into(">I", h, 328, 0)                 # MediaWeightMetric
    struct.pack_into(">I", h, 340, max(1, p.copies))  # NumCopies
    struct.pack_into(">I", h, 344, 0)                 # Orientation (portrait)
    struct.pack_into(">II", h, 352, p.page_w_pt, p.page_h_pt)  # PageSize (points)
    struct.pack_into(">I", h, 368, 0)                 # Tumble
    struct.pack_into(">I", h, 372, p.width)           # Width
    struct.pack_into(">I", h, 376, p.height)          # Height
    struct.pack_into(">I", h, 384, p.bits_per_color)  # BitsPerColor
    struct.pack_into(">I", h, 388, p.bits_per_color * p.num_colors)  # BitsPerPixel
    struct.pack_into(">I", h, 392, p.bytes_per_line)  # BytesPerLine
    struct.pack_into(">I", h, 396, 0)                 # ColorOrder chunky
    struct.pack_into(">I", h, 400, p.color_space)     # ColorSpace
    struct.pack_into(">I", h, 420, p.num_colors)      # NumColors
    struct.pack_into(">I", h, 452, p.total_pages)     # TotalPageCount
    struct.pack_into(">i", h, 456, 1)                 # CrossFeedTransform
    struct.pack_into(">i", h, 460, 1)                 # FeedTransform
    struct.pack_into(">IIII", h, 464, 0, 0, p.width, p.height)  # ImageBox L,T,R,B
    struct.pack_into(">I", h, 480, 0x00FFFFFF)        # AlternatePrimary (white)
    struct.pack_into(">I", h, 484, p.quality)         # PrintQuality
    h[1668:1732] = _cstr(p.rendering_intent)
    h[1732:1796] = _cstr(p.page_size_name)
    return bytes(h)


def parse_header(h: bytes) -> dict:
    def cs(a: int, b: int) -> str:
        return h[a:b].split(b"\x00", 1)[0].decode("utf-8", "replace")

    u = lambda off: struct.unpack_from(">I", h, off)[0]  # noqa: E731
    return {
        "magic": cs(0, 64), "media_color": cs(64, 128), "media_type": cs(128, 192),
        "content_optimize": cs(192, 256), "hw_resolution": (u(276), u(280)),
        "num_copies": u(340), "page_size": (u(352), u(356)), "width": u(372), "height": u(376),
        "bits_per_color": u(384), "bits_per_pixel": u(388), "bytes_per_line": u(392),
        "color_order": u(396), "color_space": u(400), "num_colors": u(420),
        "total_page_count": u(452), "print_quality": u(484),
        "rendering_intent": cs(1668, 1732), "page_size_name": cs(1732, 1796),
    }


# ---------------------------------------------------------------- line coding

def pack_line(px: np.ndarray) -> bytes:
    """Encode one raster line. ``px`` is a (width, bytes_per_pixel) uint8 array."""
    width, bpp = px.shape
    if width == 0:
        return b""
    if width > 1:
        diff = np.any(px[1:] != px[:-1], axis=1)
        starts = np.concatenate(([0], np.flatnonzero(diff) + 1))
    else:
        starts = np.zeros(1, dtype=np.int64)
    lengths = np.diff(np.append(starts, width))
    is_rep = lengths >= 2
    # Each repeated run is its own block; consecutive single pixels merge into literal blocks.
    class_change = np.empty(is_rep.size, dtype=bool)
    class_change[0] = True
    class_change[1:] = is_rep[1:] != is_rep[:-1]
    block_start = class_change | is_rep
    first_run = np.flatnonzero(block_start)
    blk_px = starts[first_run]
    blk_len = np.add.reduceat(lengths, first_run)
    blk_rep = is_rep[first_run]
    # Split blocks into chunks of at most 128 pixels.
    nchunks = (blk_len + 127) // 128
    chunk_blk = np.repeat(np.arange(blk_len.size), nchunks)
    chunk_first = np.cumsum(nchunks) - nchunks
    k = np.arange(chunk_blk.size) - np.repeat(chunk_first, nchunks)
    c_start = blk_px[chunk_blk] + 128 * k
    c_len = np.minimum(128, blk_len[chunk_blk] - 128 * k)
    c_rep = blk_rep[chunk_blk]
    ctrl = np.where(c_rep, c_len - 1, (257 - c_len) & 0xFF).astype(np.uint8)
    emit = np.where(c_rep, 1, c_len)
    sizes = 1 + emit * bpp
    out = np.empty(int(sizes.sum()), dtype=np.uint8)
    offs = np.cumsum(sizes) - sizes
    out[offs] = ctrl
    chunk_of = np.repeat(np.arange(emit.size), emit)
    j = np.arange(chunk_of.size) - (np.cumsum(emit) - emit)[chunk_of]
    src = c_start[chunk_of] + j
    dst = offs[chunk_of] + 1 + j * bpp
    for b in range(bpp):
        out[dst + b] = px[src, b]
    return out.tobytes()


def iter_encoded_lines(rows: Iterator[np.ndarray]) -> Iterator[bytes]:
    """Yield encoded line groups (line-repeat byte + packed line) from an iterator of
    (width, bpp) uint8 rows, folding identical consecutive lines (max 256 per group)."""
    prev: np.ndarray | None = None
    count = 0
    for row in rows:
        if prev is not None and count < 256 and np.array_equal(row, prev):
            count += 1
            continue
        if prev is not None:
            yield bytes([count - 1]) + pack_line(prev)
        prev = row
        count = 1
    if prev is not None:
        yield bytes([count - 1]) + pack_line(prev)


def write_page(out: BinaryIO, page: PwgPage, pixels: np.ndarray, *, band_rows: int = 256) -> None:
    """Write one page. ``pixels`` is (height, width, channels) uint8 or uint16
    (native endian; converted to big-endian for 16-bit)."""
    if pixels.shape[0] != page.height or pixels.shape[1] != page.width:
        raise ValueError("pixel array does not match page geometry")
    out.write(build_header(page))
    bpp = page.bytes_per_pixel

    def rows() -> Iterator[np.ndarray]:
        for y0 in range(0, page.height, band_rows):
            band = np.asarray(pixels[y0:y0 + band_rows])
            if page.bits_per_color == 16:
                band = band.astype(">u2", copy=False)
            band = np.ascontiguousarray(band).view(np.uint8).reshape(band.shape[0], page.width, bpp)
            yield from band

    buf = bytearray()
    for chunk in iter_encoded_lines(rows()):
        buf += chunk
        if len(buf) > (1 << 20):
            out.write(buf)
            buf.clear()
    if buf:
        out.write(buf)


def write_document(out: BinaryIO, pages: list[tuple[PwgPage, np.ndarray]]) -> None:
    out.write(SYNC)
    for page, pixels in pages:
        write_page(out, page, pixels)


# ---------------------------------------------------------------- decoding

def _unpack_line(data: memoryview, pos: int, width: int, bpp: int) -> tuple[bytes, int]:
    line = bytearray()
    need = width * bpp
    while len(line) < need:
        c = data[pos]
        pos += 1
        if c <= 127:
            px = bytes(data[pos:pos + bpp])
            pos += bpp
            line += px * (c + 1)
        elif c == 128:  # not produced by our encoder; treat as fill with white
            line += b"\xff" * (need - len(line))
        else:
            n = 257 - c
            line += data[pos:pos + n * bpp]
            pos += n * bpp
    return bytes(line[:need]), pos


def read_document(data: bytes) -> list[tuple[dict, np.ndarray]]:
    """Decode a PWG raster stream into a list of (header dict, pixel array)."""
    if data[:4] != SYNC:
        raise ValueError("not a PWG raster stream")
    mv = memoryview(data)
    pos = 4
    pages = []
    while pos + HEADER_SIZE <= len(data):
        hdr = parse_header(bytes(mv[pos:pos + HEADER_SIZE]))
        pos += HEADER_SIZE
        w, h = hdr["width"], hdr["height"]
        bpp = hdr["bits_per_pixel"] // 8
        rows: list[bytes] = []
        while len(rows) < h:
            repeat = mv[pos] + 1
            pos += 1
            line, pos = _unpack_line(mv, pos, w, bpp)
            rows.extend([line] * repeat)
        arr = np.frombuffer(b"".join(rows[:h]), dtype=np.uint8)
        if hdr["bits_per_color"] == 16:
            arr = arr.view(">u2").astype(np.uint16)
        arr = arr.reshape(h, w, hdr["num_colors"])
        pages.append((hdr, arr))
    return pages
