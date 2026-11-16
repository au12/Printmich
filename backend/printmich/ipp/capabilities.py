"""Turn raw IPP printer attributes into a normalised capability model."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from . import media
from .protocol import Range, Resolution

QUALITY_NAMES = {3: "draft", 4: "normal", 5: "high"}
QUALITY_VALUES = {v: k for k, v in QUALITY_NAMES.items()}

REASON_TEXT = {
    "none": "Ready",
    "media-empty": "Out of paper — load paper",
    "media-needed": "Load paper to continue",
    "media-jam": "Paper jam",
    "media-low": "Paper is running low",
    "media-misfeed": "Paper misfeed",
    "media-mismatch": "Loaded paper doesn't match the job",
    "marker-supply-empty": "An ink tank is empty",
    "marker-supply-low": "An ink tank is low",
    "marker-waste-almost-full": "Maintenance cartridge almost full",
    "marker-waste-full": "Maintenance cartridge full",
    "toner-empty": "Ink empty",
    "toner-low": "Ink low",
    "cover-open": "A cover is open",
    "door-open": "A door is open",
    "input-tray-missing": "Paper tray missing",
    "output-tray-missing": "Output tray closed or missing",
    "output-area-full": "Output tray is full",
    "paused": "Printer is paused",
    "shutdown": "Printer is shutting down",
    "offline": "Printer is offline",
    "connecting-to-device": "Connecting to printer",
    "timed-out": "Printer timed out",
    "stopped-partly": "Printer partly stopped",
    "stopping": "Printer is stopping",
    "moving-to-paused": "Pausing",
    "spool-area-full": "Printer memory is full",
    "interpreter-resource-unavailable": "Printer busy",
    "cleaning": "Cleaning print head",
    "identify-printer-requested": "Identifying",
    "other": "Printer needs attention",
}


def first(attrs: dict[str, list[Any]], name: str, default: Any = None) -> Any:
    v = attrs.get(name)
    return v[0] if v else default


def strs(attrs: dict[str, list[Any]], name: str) -> list[str]:
    return [str(v) for v in attrs.get(name, []) if not hasattr(v, "tag")]


def _hmm_to_mm(v: Any) -> float | None:
    return round(v / 100.0, 2) if isinstance(v, int) else None


def split_reason(reason: str) -> tuple[str, str]:
    for sev in ("error", "warning", "report"):
        if reason.endswith("-" + sev):
            return reason[: -len(sev) - 1], sev
    return reason, "error" if reason not in ("none",) else "none"


def describe_reasons(reasons: list[str]) -> list[dict[str, str]]:
    out = []
    for r in reasons:
        if r == "none":
            continue
        base, sev = split_reason(r)
        out.append({"keyword": r, "base": base, "severity": sev,
                    "text": REASON_TEXT.get(base, media.humanize_keyword(base))})
    return out


def normalize_raster_type(kw: str) -> tuple[str, int] | None:
    s = re.sub(r"[^a-z0-9]", "", kw.lower())
    m = re.match(r"^(adobergb|srgb|sgray|rgb|black|cmyk|sw|device\d+)(\d+)$", s)
    if not m:
        return None
    color = {"adobergb": "adobe-rgb", "sw": "sgray"}.get(m.group(1), m.group(1))
    return color, int(m.group(2))


@dataclass
class MediaSizeCap:
    keyword: str
    label: str
    width_mm: float
    height_mm: float
    borderless: bool = False
    sources: list[str] = field(default_factory=list)


@dataclass
class Marker:
    name: str
    color: str
    level: int
    low: int
    high: int
    type: str


@dataclass
class Capabilities:
    uri: str = ""
    make_model: str = ""
    name: str = ""
    info: str = ""
    location: str = ""
    uuid: str = ""
    firmware: str = ""
    admin_url: str = ""
    icons: list[str] = field(default_factory=list)
    strings_uri: str = ""
    state: str = "unknown"
    state_reasons: list[dict[str, str]] = field(default_factory=list)
    state_message: str = ""
    accepting: bool = True
    formats: list[str] = field(default_factory=list)
    pwg_resolutions: list[int] = field(default_factory=list)
    pwg_types: list[str] = field(default_factory=list)
    urf: list[str] = field(default_factory=list)
    jpeg_max_kb: int | None = None
    jpeg_max_x: int | None = None
    jpeg_max_y: int | None = None
    sizes: list[MediaSizeCap] = field(default_factory=list)
    types: list[dict[str, str]] = field(default_factory=list)
    sources: list[dict[str, str]] = field(default_factory=list)
    ready: list[dict[str, Any]] = field(default_factory=list)
    qualities: list[str] = field(default_factory=list)
    resolutions: list[int] = field(default_factory=list)
    color_modes: list[str] = field(default_factory=list)
    scaling: list[str] = field(default_factory=list)
    content_optimize: list[str] = field(default_factory=list)
    rendering_intents: list[str] = field(default_factory=list)
    copies_max: int = 1
    job_attributes: list[str] = field(default_factory=list)
    hw_margins: dict[str, float] = field(default_factory=lambda: {"top": 3.0, "bottom": 5.0, "left": 3.4, "right": 3.4})
    borderless_capable: bool = False
    markers: list[Marker] = field(default_factory=list)
    defaults: dict[str, Any] = field(default_factory=dict)
    virtual: bool = False

    # ------------------------------------------------------------ queries
    def supports_format(self, mime_type: str) -> bool:
        return mime_type in self.formats

    def raster_color_spaces(self, bits: int = 8) -> list[str]:
        out = []
        for t in self.pwg_types:
            c, b = t.rsplit("_", 1)
            if int(b) == bits and c in ("srgb", "adobe-rgb", "sgray") and c not in out:
                out.append(c)
        return out

    def urf_color_spaces(self) -> list[str]:
        out = []
        for u in self.urf:
            if u.startswith("SRGB"):
                out.append("srgb")
            elif u.startswith("ADOBERGB"):
                out.append("adobe-rgb")
            elif u.startswith("W8"):
                out.append("sgray")
        return out

    def size(self, keyword: str) -> MediaSizeCap | None:
        for s in self.sizes:
            if s.keyword == keyword:
                return s
        return None

    def type_keywords(self) -> list[str]:
        return [t["keyword"] for t in self.types]

    def source_keywords(self) -> list[str]:
        return [s["keyword"] for s in self.sources]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def _parse_sizes(attrs: dict[str, list[Any]], db: list[dict[str, list[Any]]]) -> list[MediaSizeCap]:
    sizes: dict[tuple[int, int], MediaSizeCap] = {}
    kw_for_dims: dict[tuple[int, int], str] = {}

    for kw in strs(attrs, "media-supported"):
        if kw.startswith("custom_"):
            continue
        dims = media.size_from_keyword(kw)
        if dims:
            key = (round(dims[0] * 100), round(dims[1] * 100))
            kw_for_dims.setdefault(_bucket(key), kw)

    def add(x: int, y: int, borderless: bool = False, source: str | None = None) -> None:
        key = _bucket((x, y))
        cap = sizes.get(key)
        if cap is None:
            kw = kw_for_dims.get(key) or media.keyword_for_dims(x, y) or f"custom_{x/100:g}x{y/100:g}mm"
            cap = MediaSizeCap(keyword=kw, label=media.label_for(kw, x / 100, y / 100),
                               width_mm=round(x / 100, 2), height_mm=round(y / 100, 2))
            sizes[key] = cap
        if borderless:
            cap.borderless = True
        if source and source not in cap.sources:
            cap.sources.append(source)

    for coll in attrs.get("media-size-supported", []):
        if not isinstance(coll, dict):
            continue
        x, y = first(coll, "x-dimension"), first(coll, "y-dimension")
        if isinstance(x, int) and isinstance(y, int):
            add(x, y)

    for entry in db:
        ms = first(entry, "media-size")
        if not isinstance(ms, dict):
            continue
        x, y = first(ms, "x-dimension"), first(ms, "y-dimension")
        if not (isinstance(x, int) and isinstance(y, int)):
            continue
        margins = [first(entry, f"media-{s}-margin") for s in ("top", "bottom", "left", "right")]
        borderless = all(m == 0 for m in margins if m is not None) and any(m is not None for m in margins)
        add(x, y, borderless, first(entry, "media-source"))

    # sizes only advertised as keywords
    for key, _kw in kw_for_dims.items():
        if key not in sizes:
            add(*key)

    out = list(sizes.values())
    out.sort(key=lambda s: media.sort_key(s.keyword))
    return out


def _marker_color(c: str) -> str:
    m = re.search(r"#[0-9a-fA-F]{6}", c or "")
    return m.group(0).upper() if m else "#888888"


def _bucket(key: tuple[int, int]) -> tuple[int, int]:
    # Group near-identical sizes (rounding differences of a few hundredths of a mm).
    return (round(key[0] / 50) * 50, round(key[1] / 50) * 50)


def parse_capabilities(attrs: dict[str, list[Any]], uri: str = "", strings: dict[str, str] | None = None,
                       virtual: bool = False) -> Capabilities:
    caps = Capabilities(uri=uri, virtual=virtual)
    caps.make_model = str(first(attrs, "printer-make-and-model", "") or "")
    caps.name = str(first(attrs, "printer-name", "") or "")
    caps.info = str(first(attrs, "printer-info", "") or "")
    caps.location = str(first(attrs, "printer-location", "") or "")
    caps.uuid = str(first(attrs, "printer-uuid", "") or "")
    caps.firmware = ", ".join(strs(attrs, "printer-firmware-string-version"))
    caps.admin_url = str(first(attrs, "printer-more-info", "") or "")
    caps.icons = strs(attrs, "printer-icons")
    caps.strings_uri = str(first(attrs, "printer-strings-uri", "") or "")
    caps.state = {3: "idle", 4: "processing", 5: "stopped"}.get(first(attrs, "printer-state", 0), "unknown")
    caps.state_reasons = describe_reasons(strs(attrs, "printer-state-reasons"))
    caps.state_message = str(first(attrs, "printer-state-message", "") or "")
    caps.accepting = bool(first(attrs, "printer-is-accepting-jobs", True))
    caps.formats = strs(attrs, "document-format-supported")

    caps.pwg_resolutions = sorted({r.dpi[0] for r in attrs.get("pwg-raster-document-resolution-supported", [])
                                   if isinstance(r, Resolution) and r.dpi[0] == r.dpi[1]})
    types = []
    for t in strs(attrs, "pwg-raster-document-type-supported"):
        n = normalize_raster_type(t)
        if n:
            types.append(f"{n[0]}_{n[1]}")
    caps.pwg_types = sorted(set(types))
    caps.urf = strs(attrs, "urf-supported")

    for name, attr in (("jpeg_max_kb", "jpeg-k-octets-supported"), ("jpeg_max_x", "jpeg-x-dimension-supported"),
                       ("jpeg_max_y", "jpeg-y-dimension-supported")):
        v = first(attrs, attr)
        if isinstance(v, Range):
            setattr(caps, name, v.upper)

    db = [e for e in attrs.get("media-col-database", []) if isinstance(e, dict)]
    caps.sizes = _parse_sizes(attrs, db)

    caps.types = [{"keyword": t, "label": media.media_type_label(t, strings)}
                  for t in dict.fromkeys(strs(attrs, "media-type-supported"))]
    caps.sources = [{"keyword": s, "label": media.media_source_label(s, strings)}
                    for s in dict.fromkeys(strs(attrs, "media-source-supported"))]

    for coll in attrs.get("media-col-ready", []):
        if not isinstance(coll, dict):
            continue
        ms = first(coll, "media-size")
        x = first(ms, "x-dimension") if isinstance(ms, dict) else None
        y = first(ms, "y-dimension") if isinstance(ms, dict) else None
        kw = None
        if isinstance(x, int) and isinstance(y, int):
            kw = media.keyword_for_dims(x, y)
        mtype = first(coll, "media-type")
        src = first(coll, "media-source")
        caps.ready.append({
            "source": src, "source_label": media.media_source_label(str(src), strings) if src else None,
            "size": kw, "size_label": media.label_for(kw, (x or 0) / 100, (y or 0) / 100) if x else None,
            "width_mm": _hmm_to_mm(x), "height_mm": _hmm_to_mm(y),
            "type": mtype, "type_label": media.media_type_label(str(mtype), strings) if mtype else None,
        })
    if not caps.ready:
        for kw in strs(attrs, "media-ready"):
            dims = media.size_from_keyword(kw)
            caps.ready.append({"source": None, "source_label": None, "size": kw, "size_label": media.label_for(kw),
                               "width_mm": dims[0] if dims else None, "height_mm": dims[1] if dims else None,
                               "type": None, "type_label": None})

    caps.qualities = [QUALITY_NAMES[q] for q in attrs.get("print-quality-supported", []) if q in QUALITY_NAMES]
    caps.resolutions = sorted({r.dpi[0] for r in attrs.get("printer-resolution-supported", [])
                               if isinstance(r, Resolution)})
    caps.color_modes = strs(attrs, "print-color-mode-supported")
    caps.scaling = strs(attrs, "print-scaling-supported")
    caps.content_optimize = strs(attrs, "print-content-optimize-supported")
    caps.rendering_intents = strs(attrs, "print-rendering-intent-supported")
    cs = first(attrs, "copies-supported")
    caps.copies_max = cs.upper if isinstance(cs, Range) else (cs if isinstance(cs, int) else 1)
    caps.job_attributes = strs(attrs, "job-creation-attributes-supported")

    margins: dict[str, float] = {}
    zero_all = True
    for side in ("top", "bottom", "left", "right"):
        vals = [v for v in attrs.get(f"media-{side}-margin-supported", []) if isinstance(v, int)]
        nz = [v for v in vals if v > 0]
        if nz:
            margins[side] = round(min(nz) / 100.0, 2)
        if 0 not in vals:
            zero_all = False
    if margins:
        caps.hw_margins.update(margins)
    caps.borderless_capable = zero_all or any(s.borderless for s in caps.sizes)
    if zero_all and not any(s.borderless for s in caps.sizes):
        for s in caps.sizes:
            s.borderless = True

    names = strs(attrs, "marker-names")
    colors = strs(attrs, "marker-colors")
    levels = attrs.get("marker-levels", [])
    lows = attrs.get("marker-low-levels", [])
    highs = attrs.get("marker-high-levels", [])
    mtypes = strs(attrs, "marker-types")
    for i, nm in enumerate(names):
        caps.markers.append(Marker(
            name=nm,
            color=_marker_color(colors[i] if i < len(colors) else ""),
            level=int(levels[i]) if i < len(levels) and isinstance(levels[i], int) else -1,
            low=int(lows[i]) if i < len(lows) and isinstance(lows[i], int) else 10,
            high=int(highs[i]) if i < len(highs) and isinstance(highs[i], int) else 100,
            type=mtypes[i] if i < len(mtypes) else "ink-cartridge",
        ))

    mcd = first(attrs, "media-col-default")
    dflt: dict[str, Any] = {}
    if isinstance(mcd, dict):
        ms = first(mcd, "media-size")
        if isinstance(ms, dict):
            x, y = first(ms, "x-dimension"), first(ms, "y-dimension")
            if isinstance(x, int) and isinstance(y, int):
                dflt["media_size"] = media.keyword_for_dims(x, y)
        dflt["media_type"] = first(mcd, "media-type")
        dflt["media_source"] = first(mcd, "media-source")
    dflt["media"] = first(attrs, "media-default")
    dflt["quality"] = QUALITY_NAMES.get(first(attrs, "print-quality-default", 0))
    dflt["color_mode"] = first(attrs, "print-color-mode-default")
    caps.defaults = {k: v for k, v in dflt.items() if v is not None}
    return caps
