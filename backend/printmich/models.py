"""Pydantic models shared by the API, the scheduler and the renderer."""
from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .text import title_label


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class Model(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


# ---------------------------------------------------------------- color / adjustments

class Adjustments(Model):
    """Canon-driver-style color controls. Ranges mirror the PRO-310 driver (−50…50)."""
    brightness: int = Field(0, ge=-50, le=50)
    contrast: int = Field(0, ge=-50, le=50)
    saturation: int = Field(0, ge=-50, le=50)   # "Intensity" in Canon's driver
    cyan: int = Field(0, ge=-50, le=50)
    magenta: int = Field(0, ge=-50, le=50)
    yellow: int = Field(0, ge=-50, le=50)
    shadows: int = Field(0, ge=-50, le=50)
    highlights: int = Field(0, ge=-50, le=50)

    def is_neutral(self) -> bool:
        return not any(getattr(self, f) for f in type(self).model_fields)

    def plus(self, other: Adjustments) -> Adjustments:
        data = {}
        for f in type(self).model_fields:
            data[f] = max(-50, min(50, getattr(self, f) + getattr(other, f)))
        return Adjustments(**data)


class Tone(Model):
    """Black & white toning, same coordinate system as Canon's monochrome X/Y pad."""
    preset: Literal["neutral", "cool", "warm", "custom"] = "neutral"
    x: int = Field(0, ge=-100, le=100)   # − cool … + warm
    y: int = Field(0, ge=-50, le=50)     # − green … + magenta

    def resolved(self) -> tuple[int, int]:
        if self.preset == "cool":
            return -30, 0
        if self.preset == "warm":
            return 30, 0
        if self.preset == "neutral":
            return 0, 0
        return self.x, self.y


Intent = Literal["perceptual", "relative", "saturation", "absolute"]
Sharpening = Literal["off", "low", "standard", "high"]


class ColorSettings(Model):
    mode: Literal["color", "bw", "bw-toned"] = "color"
    space: Literal["auto", "srgb", "adobe-rgb"] = "auto"
    intent: Literal["paper", "perceptual", "relative", "saturation", "absolute"] = "paper"
    bpc: bool = True
    management: Literal["managed", "custom-icc", "passthrough"] = "managed"
    icc_profile: str | None = None
    tone: Tone = Field(default_factory=Tone)
    send_rendering_intent: bool = True


# ---------------------------------------------------------------- layout

class Margins(Model):
    top: float = Field(6.0, ge=0, le=200)
    right: float = Field(6.0, ge=0, le=200)
    bottom: float = Field(6.0, ge=0, le=200)
    left: float = Field(6.0, ge=0, le=200)


class Caption(Model):
    enabled: bool = False
    template: str = "{place}, {date:%B %Y}"
    font: Literal["serif", "sans", "mono"] = "serif"
    size_pt: float = Field(9.0, ge=4, le=72)
    color: str = "#3c3a36"
    align: Literal["left", "center", "right"] = "center"
    italic: bool = True
    letter_spacing: float = Field(0.0, ge=0, le=0.5)


class Layout(Model):
    borderless: bool = True
    margins: Margins = Field(default_factory=Margins)
    fit: Literal["fill", "fit"] = "fill"
    crop: Literal["smart", "faces", "attention", "center"] = "smart"
    orientation: Literal["auto", "portrait", "landscape"] = "auto"
    keyline: bool = False
    keyline_color: str = "#1d1d1f"
    keyline_width_pt: float = Field(0.5, ge=0.1, le=6)
    border_color: str = "#ffffff"
    caption: Caption = Field(default_factory=Caption)


# ---------------------------------------------------------------- output / preset

class OutputSettings(Model):
    paper_id: str = "canon-lu-101"
    media_size: str = "na_index-4x6_4x6in"
    media_source: str = "auto"
    media_type: str = "auto"
    quality: Literal["high", "normal", "draft"] = "high"
    resolution: int = Field(0, ge=0, le=2400)         # 0 = automatic
    document_format: Literal["auto", "pwg", "jpeg"] = "auto"
    bit_depth: Literal[8, 16] = 8
    copies: int = Field(1, ge=1, le=99)
    sharpening: Literal["paper", "off", "low", "standard", "high"] = "paper"
    extra_ipp: dict[str, Any] = Field(default_factory=dict)


class Preset(Model):
    id: str = Field(default_factory=new_id)
    name: str = "New preset"
    description: str = ""
    output: OutputSettings = Field(default_factory=OutputSettings)
    layout: Layout = Field(default_factory=Layout)
    color: ColorSettings = Field(default_factory=ColorSettings)
    adjust: Adjustments = Field(default_factory=Adjustments)
    sort: int = 0
    created_at: str | None = None
    updated_at: str | None = None


# ---------------------------------------------------------------- papers

Finish = Literal["high-gloss", "glossy", "luster", "semi-gloss", "baryta", "matte", "premium-matte",
                 "fine-art-smooth", "fine-art-rough", "canvas", "washi", "plain"]


class PaperCalibration(Model):
    intent: Intent = "relative"
    bpc: bool = True
    sharpening: Sharpening = "low"
    adjust: Adjustments = Field(default_factory=Adjustments)
    notes: str = ""
    calibrated_at: str | None = None


class Paper(Model):
    id: str
    name: str
    brand: str = "Canon"
    code: str = ""
    finish: Finish = "glossy"
    weight_gsm: int | None = None
    black_ink: Literal["photo", "matte"] = "photo"
    feeds: list[Literal["top", "manual"]] = Field(default_factory=lambda: ["top", "manual"])
    default_feed: Literal["top", "manual"] = "top"
    borderless: bool = True
    recommended_margins: Margins | None = None
    media_type_hints: list[str] = Field(default_factory=list)
    media_type_generic: list[str] = Field(default_factory=list)
    media_type: str = "auto"
    calibration: PaperCalibration = Field(default_factory=PaperCalibration)
    cost_per_sheet: dict[str, float] = Field(default_factory=dict)
    sizes: list[str] = Field(default_factory=list)
    notes: str = ""
    tint: str = "#f6f4ef"
    sheen: float = 0.5
    builtin: bool = True
    customized: bool = False

    @field_validator("name")
    @classmethod
    def _proper_name(cls, v: str) -> str:
        return title_label(v.strip())


# ---------------------------------------------------------------- sources & schedules

SourceKind = Literal["favorites", "album", "person", "tag", "on_this_day", "memories", "smart", "rating",
                     "recent", "random"]


class SourceSpec(Model):
    id: str = Field(default_factory=new_id)
    kind: SourceKind = "favorites"
    weight: int = Field(1, ge=0, le=100)
    album_ids: list[str] = Field(default_factory=list)
    person_ids: list[str] = Field(default_factory=list)
    person_mode: Literal["any", "all"] = "any"
    tag_ids: list[str] = Field(default_factory=list)
    query: str = ""
    min_rating: int = Field(4, ge=1, le=5)
    recent_days: int = Field(30, ge=1, le=3650)
    window_days: int = Field(3, ge=0, le=30)
    favorites_only: bool = False
    label: str = ""


class PickFilters(Model):
    include_archived: bool = False
    taken_after: str | None = None
    taken_before: str | None = None
    min_ppi: int = Field(180, ge=0, le=600)
    orientation: Literal["any", "landscape", "portrait"] = "any"
    exclude_screenshots: bool = True
    avoid_repeats_days: int = Field(365, ge=-1, le=36500)   # -1 = never repeat, 0 = allow repeats
    exclude_album_ids: list[str] = Field(default_factory=list)
    require_people: bool = False
    smart_pick: bool = True
    candidates: int = Field(8, ge=1, le=30)
    skip_blurry: bool = True


class Timing(Model):
    frequency: Literal["daily", "weekly", "monthly", "every_n_days", "cron"] = "daily"
    time: str = "08:00"
    weekdays: list[int] = Field(default_factory=lambda: [5])     # 0 = Monday
    day_of_month: int = Field(1, ge=1, le=28)
    every_n_days: int = Field(3, ge=1, le=60)
    cron: str = "0 8 * * *"

    @field_validator("time")
    @classmethod
    def _time(cls, v: str) -> str:
        hh, mm = v.split(":")
        h, m = int(hh), int(mm)
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("time must be HH:MM")
        return f"{h:02d}:{m:02d}"


class Approval(Model):
    mode: Literal["auto", "preview", "manual"] = "preview"
    lead_hours: int = Field(12, ge=1, le=72)


class ScheduleNotify(Model):
    on_pick: bool = True
    on_print: bool = True
    on_error: bool = True


class Schedule(Model):
    id: str = Field(default_factory=new_id)
    name: str = "Photo of the Day"
    enabled: bool = False
    preset_id: str = ""
    timing: Timing = Field(default_factory=Timing)
    sources: list[SourceSpec] = Field(default_factory=list)
    filters: PickFilters = Field(default_factory=PickFilters)
    approval: Approval = Field(default_factory=Approval)
    verify_paper: bool = False
    catch_up_hours: int = Field(6, ge=0, le=72)
    notify: ScheduleNotify = Field(default_factory=ScheduleNotify)
    next_run_at: str | None = None
    last_run_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ---------------------------------------------------------------- assets

class AssetSummary(Model):
    id: str
    filename: str = ""
    taken_at: str | None = None
    width: int | None = None
    height: int | None = None
    mime: str = ""
    favorite: bool = False
    rating: int | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    description: str | None = None
    make: str | None = None
    model: str | None = None
    lens: str | None = None
    f_number: float | None = None
    exposure_time: str | None = None
    iso: int | None = None
    focal_length: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    people: list[str] = Field(default_factory=list)
    thumbhash: str | None = None
    edited: bool = False
    owner: str | None = None


# ---------------------------------------------------------------- settings

class NotificationSettings(Model):
    urls: list[str] = Field(default_factory=list)
    on_pick: bool = True
    on_print: bool = True
    on_error: bool = True
    on_supplies: bool = True
    attach_preview: bool = True


class WritebackSettings(Model):
    album_enabled: bool = False
    album_name: str = "Printed with Printmich"
    tag_enabled: bool = False
    tag_name: str = "Printmich/Printed"


class CostSettings(Model):
    currency: str = "$"
    ink_per_sq_in: float = Field(0.0, ge=0, le=10)
    ink_per_ml: float = Field(0.0, ge=0, le=100)   # used instead of ink_per_sq_in when set


class InkSettings(Model):
    levels: Literal["printer", "estimate"] = "printer"   # where ink levels come from
    tank_ml: float = Field(14.4, gt=0, le=1000)          # PFI-5100 / PFI-300 tanks hold 14.4 ml
    remind_below: int = Field(20, ge=0, le=90)           # % — "refill soon" reminder
    hold_below: int = Field(3, ge=0, le=50)              # % — scheduled prints wait for a refill below this
    remind_days: int = Field(0, ge=0, le=365)            # periodic "check the ink" reminder; 0 = off
    hide_printer_warnings: bool = True                   # ignore the chips' low/empty warnings while estimating


class Settings(Model):
    immich_url: str = ""
    immich_api_key: str = ""
    immich_public_url: str = ""
    printer_uri: str = ""
    printer_name: str = ""
    units: Literal["in", "mm"] = "in"
    theme: Literal["auto", "dark", "light"] = "dark"
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    writeback: WritebackSettings = Field(default_factory=WritebackSettings)
    cost: CostSettings = Field(default_factory=CostSettings)
    ink: InkSettings = Field(default_factory=InkSettings)
    retry_minutes: int = Field(5, ge=1, le=120)
    retry_hours: int = Field(6, ge=0, le=72)
    password_hash: str = ""
    api_token_hash: str = ""
    session_secret: str = ""
    onboarded: bool = False
    wall_title: str = "Printed moments"
