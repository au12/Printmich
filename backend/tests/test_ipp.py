"""IPP wire encoding, URI handling and capability parsing (against the built-in virtual PRO-310)."""
from __future__ import annotations

import asyncio

import pytest

from printmich.ipp import protocol as p
from printmich.ipp.capabilities import describe_reasons, parse_capabilities
from printmich.ipp.client import normalize_uri
from printmich.ipp.virtual import VirtualPrinter


def test_request_round_trip_with_collection():
    media_col = p.collection("media-col", [
        p.collection("media-size", [p.integer("x-dimension", 10160), p.integer("y-dimension", 15240)]),
        p.keyword("media-type", "photographic-glossy"),
        p.integer("media-top-margin", 0),
    ])
    data = p.encode_request(p.Op.PRINT_JOB, 7, [
        (p.Tag.OPERATION, [p.charset("attributes-charset", "utf-8"), p.language("attributes-natural-language", "en"),
                           p.uri("printer-uri", "ipp://10.0.0.5:631/ipp/print"), p.name_attr("job-name", "Banff, Alberta")]),
        (p.Tag.JOB, [media_col, p.enum("print-quality", 5), p.resolution("printer-resolution", 600),
                     p.keyword("print-color-mode", "color"), p.boolean("print-scaling-auto", False)]),
    ])
    msg = p.decode_message(data)
    assert msg.request_id == 7
    op = msg.operation
    assert op["job-name"] == ["Banff, Alberta"]
    job = msg.job
    col = job["media-col"][0]
    assert col["media-type"] == ["photographic-glossy"]
    assert col["media-top-margin"] == [0]
    assert col["media-size"][0]["x-dimension"] == [10160]
    assert job["print-quality"] == [5]
    assert job["printer-resolution"][0].dpi == (600, 600)
    assert job["print-scaling-auto"] == [False]


@pytest.mark.parametrize(("raw", "expected"), [
    ("10.0.10.42", "ipp://10.0.10.42:631/ipp/print"),
    ("printer.local", "ipp://printer.local:631/ipp/print"),
    ("http://10.0.0.9:631/ipp/print", "ipp://10.0.0.9:631/ipp/print"),
    ("ipps://pro-310.lan/ipp/print", "ipps://pro-310.lan:631/ipp/print"),
    ("virtual://", "virtual://pro-310"),
])
def test_normalize_uri(raw, expected):
    assert normalize_uri(raw) == expected


def test_normalize_uri_rejects_other_schemes():
    with pytest.raises(ValueError):
        normalize_uri("lpd://10.0.0.5/queue")


def test_virtual_printer_capabilities(tmp_path):
    vp = VirtualPrinter(tmp_path)
    attrs = asyncio.run(vp.get_printer_attributes())
    caps = parse_capabilities(attrs, "virtual://pro-310")
    keywords = {s.keyword for s in caps.sizes}
    assert "na_index-4x6_4x6in" in keywords
    assert "na_letter_8.5x11in" in keywords
    four_by_six = next(s for s in caps.sizes if s.keyword == "na_index-4x6_4x6in")
    assert four_by_six.borderless
    assert caps.borderless_capable
    assert any(t.startswith("adobe-rgb") for t in caps.pwg_types)
    assert len(caps.markers) == 10
    assert caps.hw_margins["bottom"] >= caps.hw_margins["top"] > 0


def test_reason_descriptions_are_readable():
    reasons = describe_reasons(["media-empty-error", "marker-supply-low-warning", "none"])
    texts = [r["text"] for r in reasons]
    assert any("ink" in t.lower() for t in texts)
    assert all(r["severity"] in ("error", "warning", "report") for r in reasons)
