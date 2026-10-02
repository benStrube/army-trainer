"""Palette, fonts and sizes for the decks (D9 in docs/decisions/no-api-key.md).

Best-guess Army-style look: mostly white/gray/black with Army gold. No Army star, seal or
wordmark. Official values replace these if the brand guide is ever obtained.
"""

from __future__ import annotations

from dataclasses import dataclass

FONT = "Arial"
DISCLAIMER = "Unofficial training aid — the publication is the authoritative source"


@dataclass(frozen=True)
class Palette:
    army_black: str = "222021"
    army_gold: str = "FFCD01"
    gold_dark: str = "8A6D00"
    olive_gray: str = "58574E"
    mid_gray: str = "6B6B6B"
    light_gray: str = "E6E6E6"
    pale_gray: str = "F2F2F2"
    white: str = "FFFFFF"
    do_green: str = "2E6B30"
    dont_red: str = "B3261E"


PALETTE = Palette()

# Slide geometry (16:9, inches)
SLIDE_W = 13.333
SLIDE_H = 7.5
MARGIN = 0.5
TITLE_BAR_H = 1.1
GOLD_RULE_H = 0.07
FOOTER_Y = 7.05
CONTENT_TOP = TITLE_BAR_H + GOLD_RULE_H + 0.3
CONTENT_BOTTOM = 6.9

# Type sizes (pt). Body text is never below 18 pt; footers/citations are the exception.
TITLE_PT = 28
BODY_PT = 20
MIN_BODY_PT = 18
FOOTER_PT = 11

# Text/background pairs the template relies on; checked by tests.
TEXT_PAIRS: dict[str, tuple[str, str, float]] = {
    "body on white": ("army_black", "white", 4.5),
    "title on black bar": ("white", "army_black", 4.5),
    "black on gold": ("army_black", "army_gold", 4.5),
    "white on olive": ("white", "olive_gray", 4.5),
    "footer gray on white": ("mid_gray", "white", 4.5),
    "black on light gray": ("army_black", "light_gray", 4.5),
    "black on pale gray": ("army_black", "pale_gray", 4.5),
    "dark gold on white": ("gold_dark", "white", 4.5),
    "green on white": ("do_green", "white", 4.5),
    "red on white": ("dont_red", "white", 4.5),
    "white on green": ("white", "do_green", 4.5),
    "white on red": ("white", "dont_red", 4.5),
}


def _lin(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(fg: str, bg: str) -> float:
    """WCAG contrast ratio between two hex colors (no leading #)."""
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)
