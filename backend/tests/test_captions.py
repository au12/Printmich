from __future__ import annotations

from printmich.captions import render_caption
from printmich.models import AssetSummary


def asset(**kw) -> AssetSummary:
    base = {"id": "a1", "filename": "IMG_0001.HEIC", "taken_at": "2023-07-24T19:42:00Z", "city": "Banff",
            "state": "Alberta", "country": "Canada", "make": "SONY", "model": "ILCE-7RM5"}
    base.update(kw)
    return AssetSummary(**base)


def test_place_and_date():
    assert render_caption("{place}, {date:%B %Y}", asset()) == "Banff, Alberta, July 2023"


def test_missing_values_drop_with_their_separator():
    a = asset(city=None, state=None, country=None)
    assert render_caption("{place}, {date:%Y}", a) == "2023"
    assert render_caption("{description} · {place} · {year}", asset(description="")) == "Banff, Alberta · 2023"
    assert render_caption("{place}, {date:%Y}", asset(taken_at=None)) == "Banff, Alberta"


def test_people_and_camera():
    a = asset(people=["Ann", "Bob"])
    text = render_caption("{people} | {camera}", a)
    assert text.startswith("Ann, Bob | ")
    assert "ILCE-7RM5" in text
