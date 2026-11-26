"""First-run presets and schedule."""
from __future__ import annotations

from .models import (
    Adjustments,
    Approval,
    Caption,
    ColorSettings,
    Layout,
    Margins,
    OutputSettings,
    PickFilters,
    Preset,
    Schedule,
    SourceSpec,
    Timing,
)


def default_presets() -> list[Preset]:
    return [
        Preset(
            id="p-daily-4x6", name="Daily 4×6, Pro Platinum", sort=0,
            description="Edge-to-edge 4×6 on Canon's deepest-black high-gloss paper. The photo-of-the-day classic.",
            output=OutputSettings(paper_id="canon-pt-101", media_size="na_index-4x6_4x6in", quality="high"),
            layout=Layout(borderless=True, crop="smart"),
        ),
        Preset(
            id="p-instant", name="Instant frame 4×6", sort=1,
            description="Instant-film style frame with a thick bottom border and a handwritten-feel caption.",
            output=OutputSettings(paper_id="canon-pp-201", media_size="na_index-4x6_4x6in", quality="high"),
            layout=Layout(borderless=False, orientation="portrait",
                          margins=Margins(top=6, right=6, bottom=26, left=6),
                          caption=Caption(enabled=True, template="{place}, {date:%b %Y}", font="serif",
                                          size_pt=10, italic=True, color="#2f2d2a")),
        ),
        Preset(
            id="p-5x7", name="5×7 Semi-Gloss", sort=2,
            description="A little bigger for the fridge or a desk frame.",
            output=OutputSettings(paper_id="canon-sg-201", media_size="na_5x7_5x7in", quality="high"),
            layout=Layout(borderless=True),
        ),
        Preset(
            id="p-gallery-letter", name="Gallery mat, Letter Pro Luster", sort=3,
            description="Matted look with a quiet serif caption — ready for an 11×14 frame.",
            output=OutputSettings(paper_id="canon-lu-101", media_size="na_letter_8.5x11in", quality="high"),
            layout=Layout(borderless=False, margins=Margins(top=22, right=22, bottom=30, left=22),
                          caption=Caption(enabled=True, template="{place}, {date:%B %Y}", font="serif",
                                          size_pt=9, italic=True)),
        ),
        Preset(
            id="p-bw-matte", name="Black & White, Letter Matte", sort=4,
            description="Neutral monochrome on matte paper using the printer's gray inks.",
            output=OutputSettings(paper_id="canon-mp-101", media_size="na_letter_8.5x11in", quality="high"),
            layout=Layout(borderless=False, margins=Margins(top=25, right=25, bottom=32, left=25),
                          caption=Caption(enabled=True, template="{date:%Y}", font="sans", size_pt=7,
                                          italic=False, letter_spacing=0.25, color="#5a5752")),
            color=ColorSettings(mode="bw"),
            adjust=Adjustments(contrast=6),
        ),
        Preset(
            id="p-exhibition", name="Exhibition 13×19, Fine Art Smooth", sort=5,
            description="Museum-style print with Canon's recommended 25 mm+ fine-art margins.",
            output=OutputSettings(paper_id="canon-fa-sm", media_size="na_super-b_13x19in", quality="high"),
            layout=Layout(borderless=False, margins=Margins(top=38, right=32, bottom=50, left=32),
                          caption=Caption(enabled=True, template="{description}, {place}, {date:%Y}",
                                          font="serif", size_pt=11, italic=True)),
        ),
    ]


def default_schedule() -> Schedule:
    return Schedule(
        id="s-photo-of-the-day", name="Photo of the Day", enabled=False, preset_id="p-daily-4x6",
        timing=Timing(frequency="daily", time="08:00"),
        sources=[
            SourceSpec(kind="favorites", weight=3, label="Favorites"),
            SourceSpec(kind="on_this_day", weight=2, window_days=3, label="On this day"),
            SourceSpec(kind="rating", weight=1, min_rating=4, label="4★ and up"),
        ],
        filters=PickFilters(min_ppi=180, avoid_repeats_days=365, smart_pick=True, candidates=8),
        approval=Approval(mode="preview", lead_hours=12),
    )
