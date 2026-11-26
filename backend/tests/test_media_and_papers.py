from __future__ import annotations

from printmich.ipp.media import keyword_for_dims, label_for, size_from_keyword
from printmich.papers import BUILTIN_BY_ID, resolve_media_source, resolve_media_type


def test_size_lookup():
    w, h = size_from_keyword("na_index-4x6_4x6in")
    assert round(w, 1) == 101.6 and round(h, 1) == 152.4
    assert keyword_for_dims(21590, 27940) == "na_letter_8.5x11in"  # IPP sizes are in 1/100 mm
    assert label_for("na_letter_8.5x11in") == "8.5 × 11 in (Letter)"
    # Unknown keywords still parse their dimensions
    w, h = size_from_keyword("custom_photo_6x8in")
    assert round(w, 1) == 152.4 and round(h, 1) == 203.2


CANON_TYPES = [
    {"keyword": "stationery", "label": "Plain Paper"},
    {"keyword": "photographic-high-gloss", "label": "Photo Paper Pro Platinum"},
    {"keyword": "photographic-glossy", "label": "Photo Paper Plus Glossy II"},
    {"keyword": "photographic-semi-gloss", "label": "Photo Paper Plus Semi-gloss"},
    {"keyword": "photographic-satin", "label": "Photo Paper Pro Luster"},
    {"keyword": "photographic-matte", "label": "Matte Photo Paper"},
    {"keyword": "com.canon.fine-art-smooth", "label": "Premium Fine Art Smooth"},
]


def test_canon_papers_map_to_matching_media_types():
    expect = {
        "canon-pt-101": "photographic-high-gloss",
        "canon-pp-201": "photographic-glossy",
        "canon-lu-101": "photographic-satin",
        "canon-sg-201": "photographic-semi-gloss",
        "canon-mp-101": "photographic-matte",
        "canon-fa-sm": "com.canon.fine-art-smooth",
    }
    for paper_id, keyword in expect.items():
        got = resolve_media_type(BUILTIN_BY_ID[paper_id], CANON_TYPES)
        assert got["keyword"] == keyword, (paper_id, got)


def test_override_and_generic_fallback():
    paper = BUILTIN_BY_ID["canon-pt-101"]
    assert resolve_media_type(paper, CANON_TYPES, "photographic-glossy")["how"] == "override"
    got = resolve_media_type(paper, [])
    assert got["how"] in ("generic", "none")


def test_fine_art_prefers_manual_feed():
    paper = BUILTIN_BY_ID["canon-fa-rg"]
    assert resolve_media_source(paper, ["main", "manual", "top"]) in ("manual", "rear")


def test_paper_names_are_title_cased():
    from printmich.ipp.media import MEDIA_SOURCE_LABELS, MEDIA_TYPE_LABELS, media_type_label, title_label
    from printmich.models import Paper

    assert title_label("semi-gloss photo paper") == "Semi-Gloss Photo Paper"
    assert title_label("satin / luster photo paper") == "Satin / Luster Photo Paper"
    assert title_label("Photo Paper Plus Glossy II") == "Photo Paper Plus Glossy II"  # already-capitalized words are left alone
    assert title_label("hahnemühle photo rag 308") == "Hahnemühle Photo Rag 308"
    assert title_label("canson's baryta") == "Canson's Baryta"
    # every built-in label and paper already reads that way
    for label in [*MEDIA_TYPE_LABELS.values(), *MEDIA_SOURCE_LABELS.values(), *(p.name for p in BUILTIN_BY_ID.values())]:
        assert label == title_label(label), label
    # names a printer supplies in its strings file are normalized too
    assert media_type_label("photographic-semi-gloss", {"media-type.photographic-semi-gloss": "Photo Paper Plus Semi-gloss"}) \
        == "Photo Paper Plus Semi-Gloss"
    # and so are papers people add themselves
    assert Paper(id="custom-x", name="red river polar pearl metallic").name == "Red River Polar Pearl Metallic"
    got = resolve_media_type(BUILTIN_BY_ID["canon-sg-201"], CANON_TYPES)
    assert got["label"] == "Photo Paper Plus Semi-Gloss"
