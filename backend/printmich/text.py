"""Small text helpers shared by the models and the IPP layer (no imports, so anything can use it)."""
from __future__ import annotations

import re

_WORD_START = re.compile(r"(?<![\w'’])[a-z]")


def title_label(text: str | None) -> str:
    """Paper, paper-type and feed names read as proper names: capitalize the first letter of every
    word ("semi-gloss photo paper" -> "Semi-Gloss Photo Paper") and leave the rest as written, so
    "II", "PRO-310" or "A3+" survive."""
    if not text:
        return text or ""
    return _WORD_START.sub(lambda m: m.group().upper(), text)
