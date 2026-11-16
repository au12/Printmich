"""Caption templates, e.g. "{place}, {date:%B %Y}".

Tokens: {date} {date:<strftime>} {year} {month} {day} {place} {city} {state} {country}
{description} {camera} {lens} {exposure} {people} {filename} {title}

Separators (", " " · " " | " " — ") next to empty tokens are dropped automatically, so
"{place}, {date:%Y}" renders "2019" when a photo has no location.
"""
from __future__ import annotations

import datetime as dt
import re

from .models import AssetSummary

TOKEN = re.compile(r"\{([a-z_]+)(?::([^}]*))?\}")
SEPARATORS = (" · ", " | ", " — ", " – ", ", ")


def _date(a: AssetSummary) -> dt.datetime | None:
    if not a.taken_at:
        return None
    try:
        return dt.datetime.fromisoformat(a.taken_at.replace("Z", "+00:00"))
    except ValueError:
        return None


def camera_name(a: AssetSummary) -> str:
    make, model = (a.make or "").strip(), (a.model or "").strip()
    if not model:
        return make
    if make and model.lower().startswith(make.split()[0].lower()):
        return model
    return f"{make} {model}".strip()


def exposure_line(a: AssetSummary) -> str:
    parts = []
    if a.focal_length:
        parts.append(f"{a.focal_length:g} mm")
    if a.f_number:
        parts.append(f"ƒ/{a.f_number:g}")
    if a.exposure_time:
        et = str(a.exposure_time)
        parts.append(et if et.endswith("s") else f"{et} s")
    if a.iso:
        parts.append(f"ISO {a.iso}")
    return "  ".join(parts)


def place(a: AssetSummary) -> str:
    city = (a.city or "").strip()
    region = (a.state or a.country or "").strip()
    if city and region and region.lower() != city.lower():
        return f"{city}, {region}"
    return city or region


def render_caption(template: str, a: AssetSummary | None) -> str:
    if a is None:
        return ""
    d = _date(a)

    def sub(m: re.Match[str]) -> str:
        key, fmt = m.group(1), m.group(2)
        if key == "date":
            if not d:
                return ""
            try:
                return d.strftime(fmt or "%B %-d, %Y")
            except ValueError:
                return d.strftime("%B %d, %Y")
        vals = {
            "year": d.strftime("%Y") if d else "",
            "month": d.strftime("%B") if d else "",
            "day": str(d.day) if d else "",
            "place": place(a),
            "city": a.city or "",
            "state": a.state or "",
            "country": a.country or "",
            "description": (a.description or "").strip(),
            "camera": camera_name(a),
            "lens": a.lens or "",
            "exposure": exposure_line(a),
            "people": ", ".join(a.people[:4]),
            "filename": a.filename or "",
            "title": (a.description or "").strip() or re.sub(r"\.[A-Za-z0-9]+$", "", a.filename or ""),
        }
        return vals.get(key, m.group(0))

    text = TOKEN.sub(sub, template)
    for sep in SEPARATORS:
        parts = [p.strip() for p in text.split(sep)]
        text = sep.join(p for p in parts if p)
    return re.sub(r"\s{3,}", "  ", text).strip(" ·|—–,")
