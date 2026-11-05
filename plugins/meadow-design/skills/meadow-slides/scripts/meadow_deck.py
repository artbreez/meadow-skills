#!/usr/bin/env python3
"""Meadow deck engine: deck spec (JSON) -> PPTX, and optionally a layout dump for Figma.

    python3 meadow_deck.py deck.json -o deck.pptx [--figma-json layout.json] [--portable]

The layout is computed once, in Figma pixels on a 1920x1080 canvas, as a list of
primitives (rect / text / image / ellipse). The PPTX writer and the Figma renderer
both draw those same primitives, so the two outputs match.

Every slide layout is a function `layout_<name>(spec, ctx)` below. Measurement uses
the bundled fonts, so the script can warn when text does not fit its box.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import random
import tempfile
import zlib
from dataclasses import dataclass, field

from PIL import ImageChops, Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")
FONTS = os.path.join(ASSETS, "fonts")

# ---------------------------------------------------------------- tokens
W, H = 1920, 1080
M = 96                      # outer margin
GAP = 24                    # gap between cards
CONTENT_TOP = 264
CONTENT_BOTTOM = 944
R_CARD = 24
R_ROW = 16
PAD = 40                    # card padding

THEMES = {
    "dark": {
        "bg": "#0E1013",
        "card": "#1A1D21",
        "row": "#23262B",
        "lime": "#D3FF31",
        "lime2": "#C4EE2A",      # zebra stripe inside the lime table column
        "blue": "#4E5BCF",       # rare secondary plate, only when asked for
        "blue2": "#D9DDF7",      # secondary text on blue
        "blue3": "#4552C2",      # zebra stripe inside a blue table column
        "white": "#FFFFFF",      # text on blue
        "fg": "#FFFFFF",         # primary text on the canvas and cards
        "hi": "#D3FF31",         # accent as ink: eyebrows, numbers, bullets, KPI values
        "text2": "#C9CDD3",      # body copy
        "muted": "#9AA1AB",      # captions, labels
        "dim": "#6B7280",        # page numbers
        "ink": "#0E1013",        # text on lime
        "ink2": "#3D4713",       # secondary text on lime
        "tile": "#0E1013",       # KPI tiles on the lime plate
        "tile_value": "#D3FF31",
        "rule": "#FFFFFF26",     # hairline between rows (ruled layouts)
        "bar_past": "#3A3F47",   # bars that are history, next to accent bars
        "stroke": "#FFFFFF2E",   # 18% hairline (outline chips)
        "glass": "#FFFFFF1F",    # secondary button
        "glass_stroke": "#FFFFFF33",
        "scrim": (14, 16, 19),   # photo scrims fade into this
        "logo": "meadow-logo-lime.png",
        "icon": "white",
    },
    # Light: the investor-deck look. White canvas, ink type, blue #5260DA as the accent *ink*
    # (lime type vanishes on white), lime stays the one plate.
    "light": {
        "bg": "#FFFFFF",
        "card": "#F2F3F5",
        "row": "#E6E8EC",
        "lime": "#D3FF31",
        "lime2": "#C4EE2A",
        "blue": "#5260DA",
        "blue2": "#D4D8F7",
        "blue3": "#4A57CF",
        "white": "#FFFFFF",
        "fg": "#0A0A0A",
        "hi": "#5260DA",
        "text2": "#3D3D3D",
        "muted": "#6B7280",
        "dim": "#9AA1AB",
        "ink": "#0E1013",
        "ink2": "#3D4713",
        "tile": "#FFFFFF",
        "tile_value": "#0A0A0A",
        "rule": "#DCDDE6",
        "bar_past": "#DCDDE6",
        "stroke": "#0A0A0A2E",
        "glass": "#0A0A0A0F",
        "glass_stroke": "#0A0A0A26",
        "scrim": (255, 255, 255),
        "logo": "meadow-logo-black.png",
        "icon": "black",
    },
}
C = dict(THEMES["dark"])   # current slide's tokens; build() swaps them per slide


def use_theme(name):
    if name not in THEMES:
        raise SystemExit(f"unknown theme {name!r}; choose from {sorted(THEMES)}")
    C.clear()
    C.update(THEMES[name])

# family, style  -> font file + PPTX (family, bold) in exact / portable mode
FONT_FILES = {
    ("Geist", 400): "Geist-Regular.ttf",
    ("Geist", 500): "Geist-Medium.ttf",
    ("Geist", 600): "Geist-SemiBold.ttf",
    ("Geist", 700): "Geist-Bold.ttf",
    ("Geist Mono", 400): "GeistMono-Regular.ttf",
    ("Geist Mono", 500): "GeistMono-Medium.ttf",
    ("Syne", 500): "Syne-Medium.ttf",
    ("Syne", 600): "Syne-SemiBold.ttf",
    ("Syne", 700): "Syne-Bold.ttf",
    ("Syne", 800): "Syne-ExtraBold.ttf",
}
STYLE_NAME = {400: "Regular", 500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold"}


def pptx_font(family: str, weight: int, portable: bool):
    """Static font family names as PowerPoint/Keynote see them (name ID 1)."""
    if portable:  # Google Slides / machines without the fonts: only Regular + Bold
        return family, weight >= 600
    if weight == 400:
        return family, False
    if weight == 700:
        return family, True
    if family == "Syne":
        # A variable Syne installed next to the static files (Google Fonts ships one) claims the
        # family name "Syne ExtraBold" and Keynote then draws the Regular instance. The
        # PostScript name always resolves to the static face.
        return f"Syne-{STYLE_NAME[weight]}", False
    return f"{family} {STYLE_NAME[weight]}", False


_font_cache: dict = {}


def font(family, weight, size):
    key = (family, weight, round(size))
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(os.path.join(FONTS, FONT_FILES[(family, weight)]), round(size))
    return _font_cache[key]


_vm_cache = {}


def vmetrics(family, weight):
    """(ascender, descender, cap height) in em, from the bundled font."""
    k = (family, weight)
    if k not in _vm_cache:
        f = font(family, weight, 1000)
        a, d = f.getmetrics()
        _vm_cache[k] = (a / 1000, d / 1000, -f.getbbox("H", anchor="ls")[1] / 1000)
    return _vm_cache[k]


def ink_x(text, family, weight, size, tracking=0.0):
    """Left/right ink edges of one line drawn from x=0, letter-spacing included."""
    f = font(family, weight, size * 4)                      # 4x for sub-pixel precision
    bb = f.getbbox(text or " ", anchor="ls")
    return bb[0] / 4, bb[2] / 4 + tracking * size * max(0, len(text) - 1)


def line_width(text, family, weight, size, tracking=0.0):
    """Advance width of one line as the renderers lay it out (unhinted, like Keynote)."""
    return font(family, weight, size * 4).getlength(text) / 4 + tracking * size * max(0, len(text) - 1)


# ---------------------------------------------------------------- typography helpers
CYR = re.compile(r"[А-Яа-яЁё]")
SHORT_RU = {
    "а", "в", "во", "и", "к", "ко", "о", "об", "от", "с", "со", "у", "на", "по", "за", "из", "до",
    "не", "ни", "но", "для", "при", "про", "без", "под", "над", "или", "что", "как", "это", "мы",
    "вы", "их", "его", "её", "же", "ли", "бы", "the", "a", "an", "of", "to", "in", "on", "by", "for",
}


def typograph(text: str) -> str:
    """Glue short words to the next word and dashes to the previous one with NBSP,
    so no line ends on a hanging preposition. Idempotent."""
    if not text:
        return text
    text = re.sub(r" +([—–])", "\u00a0\\1", text)  # dash sticks to previous word
    def glue(m):
        return m.group(1) + "\u00a0"
    pattern = r"(?<![\w\u00a0])(" + "|".join(sorted(SHORT_RU, key=len, reverse=True)) + r") "
    prev = None
    while prev != text:
        prev = text
        text = re.sub(pattern, glue, text, flags=re.IGNORECASE)
    text = re.sub(r"(\d) (\d{3})", "\\1\u00a0\\2", text)  # 350 000 stays together
    return text


_hi_cache = {}


def _adv(f, text):
    """Unhinted advance width (measured at 4x), the way Keynote and PowerPoint lay text out."""
    k = (f.path, f.size)
    if k not in _hi_cache:
        _hi_cache[k] = f.font_variant(size=f.size * 4)
    return _hi_cache[k].getlength(text) / 4


def wrap(text, f, width):
    """Greedy word wrap; NBSP-joined words never split. Returns lines."""
    lines = []
    for para in text.split("\n"):
        words = para.split(" ")
        cur = ""
        for w_ in words:
            trial = w_ if not cur else cur + " " + w_
            if _adv(f, trial) <= width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w_
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- primitives
@dataclass
class Prim:
    kind: str                 # rect | ellipse | text | image
    x: float
    y: float
    w: float
    h: float
    props: dict = field(default_factory=dict)
    name: str = ""


class Slide:
    def __init__(self, index, total, bg=None):
        self.index, self.total, self.bg = index, total, bg or C["bg"]
        self.prims: list[Prim] = []
        self.notes = ""
        self.warnings: list[str] = []
        self.accents = 0
        self.theme = "dark"
        self.flower = None

    def rect(self, x, y, w, h, fill, radius=0, stroke=None, name="", link=None, flow=False):
        self.prims.append(Prim("rect", x, y, w, h, {"fill": fill, "radius": radius, "stroke": stroke, "link": link, "flow": flow}, name))

    def pill(self, x, y, h, text, *, fill, color, family="Geist", weight=500, size=26, pad=24,
             tracking=0.0, caps=False, stroke=None, link=None, name="Pill", typo=True, flow=False):
        """Rounded pill sized to its text, with the text optically centred: equal ink padding
        left/right, cap height centred top/bottom. The line box is the font's natural height,
        anchored middle, so Keynote, PowerPoint and the Pillow render agree. Returns width."""
        t = str(text)
        t = t.upper() if caps else t
        t = typograph(t) if typo else t
        l, r = ink_x(t, family, weight, size, tracking)
        w = (r - l) + 2 * pad
        self.rect(x, y, w, h, fill, h / 2, stroke=stroke, name=name, link=link)
        self.prims[-1].props.update(pill=True, flow=flow)
        a, d, cap = vmetrics(family, weight)
        L = size * (a + d)
        baseline = y + h / 2 + cap * size / 2                  # caps centred on the pill
        by = baseline - a * size - (h - L) / 2                # box whose middle-anchored line lands there
        self.text(x + pad - l, by, line_width(t, family, weight, size, tracking) + 40, t, family=family,
                  weight=weight, size=size, color=color, lh=a + d, tracking=tracking, typo=False,
                  valign="middle", h=h, link=link, name=name + " label", flow=flow)
        return w

    def path(self, subpaths, *, fill=None, stroke=None, stroke_w=0, name=""):
        """Vector shape. subpaths: [[("M",x,y), ("L",x,y), ("C",x1,y1,x2,y2,x,y), ("Z",)], ...] in
        slide px; filled even-odd. Box = bounds of the points (control points included)."""
        xs = [v for sp in subpaths for seg in sp for v in seg[1::2]]
        ys = [v for sp in subpaths for seg in sp for v in seg[2::2]]
        x0, y0 = min(xs), min(ys)
        self.prims.append(Prim("path", x0, y0, max(xs) - x0, max(ys) - y0,
                               {"subpaths": subpaths, "fill": fill, "stroke": stroke, "stroke_w": stroke_w}, name))

    def ellipse(self, x, y, d, fill, name=""):
        self.prims.append(Prim("ellipse", x, y, d, d, {"fill": fill}, name))

    def image(self, path, x, y, w, h, radius=0, name="", scrim=None, fit="cover", flow=False):
        self.prims.append(Prim("image", x, y, w, h, {"src": path, "radius": radius, "scrim": scrim, "fit": fit, "flow": flow,
                                                     "scrim_rgb": C["scrim"] if scrim else None}, name))

    def text(self, x, y, w, text, *, family="Geist", weight=400, size=28, color=None, lh=1.3,
             align="left", tracking=0.0, caps=False, max_h=None, name="", typo=True, valign="top", h=None, link=None,
             flow=False):
        """Place a text block, return its measured height."""
        if text is None:
            return 0
        color = color or C["fg"]
        text = str(text)
        if caps:
            text = text.upper()
        if typo:
            text = typograph(text)
        f = font(family, weight, size)
        lines = wrap(text, f, w)
        mh = len(lines) * size * lh
        bh = h if h is not None else mh
        wide = max(lines, key=lambda l_: _adv(f, l_))
        if not flow and _adv(f, wide) + tracking * size * max(0, len(wide) - 1) > w + 1:
            self.warnings.append(f"slide {self.index}: {wide[:40]!r} is wider than its {w:.0f}px box and cannot wrap")
        if max_h is not None and mh > max_h + 1:
            self.warnings.append(f"slide {self.index}: text overflows ({int(mh)}>{int(max_h)}px): {text[:50]!r}")
        if family == "Syne" and CYR.search(text):
            self.warnings.append(f"slide {self.index}: Syne has no Cyrillic, use Geist for {text[:40]!r}")
        self.prims.append(Prim("text", x, y, w, bh, {
            "text": text, "family": family, "weight": weight, "size": size, "color": color, "lh": lh,
            "align": align, "tracking": tracking, "valign": valign, "lines": len(lines), "link": link, "flow": flow}, name))
        return mh

    def measure(self, text, w, *, family="Geist", weight=400, size=28, lh=1.3, caps=False):
        if not text:
            return 0
        text = typograph(str(text).upper() if caps else str(text))
        return len(wrap(text, font(family, weight, size), w)) * size * lh


# ---------------------------------------------------------------- shared chrome
class Ctx:
    def __init__(self, deck):
        self.deck = deck
        self.lang = deck.get("lang") or ("ru" if CYR.search(json.dumps(deck, ensure_ascii=False)) else "en")
        self.total = len(deck["slides"])

    # Headings follow their own text, not the deck language: a Latin-only heading is Syne
    # even in a Russian deck; any Cyrillic means Geist (Syne has no Cyrillic glyphs).
    @staticmethod
    def is_latin(text):
        return bool(re.search(r"[A-Za-z]", text or "")) and not CYR.search(text or "")

    def head_family(self, text):
        return "Syne" if self.is_latin(text) else "Geist"

    def head_weight(self, text, geist=600, syne=700):
        return syne if self.is_latin(text) else geist


def asset(name, folder):
    """Resolve a bundled asset by short name, or pass a path through."""
    if not name:
        return None
    if os.path.exists(name):
        return os.path.abspath(name)
    exts = ("", ".jpg", ".png", f"-{C['icon']}.png", "-white.png") if folder == "icons" else ("", ".jpg", ".png")
    for ext in exts:
        p = os.path.join(ASSETS, folder, name + ext)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"asset not found: {name} (looked in assets/{folder}/)")


def is_light(hexcolor):
    h = hexcolor.lstrip("#")[:6]
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150


def accent_colors(accent):
    """Fill, primary text, secondary text, and number colour for a plate."""
    if accent == "lime":
        return C["lime"], C["ink"], C["ink2"], C["ink"]
    if accent == "blue":
        return C["blue"], C["white"], C["blue2"], C["white"]
    return C["card"], C["fg"], C["muted"], C["hi"]


def plate(accent):
    """Colours for a hero plate: lime (default) or blue. Text on lime is ink, on blue white;
    the badge flips to lime on blue so it still reads as the accent."""
    if accent == "blue":
        return {"fill": C["blue"], "fg": C["white"], "fg2": C["blue2"], "bar": C["white"],
                "badge": C["lime"], "badge_text": C["ink"], "stripe": C["blue3"]}
    return {"fill": C["lime"], "fg": C["ink"], "fg2": C["ink2"], "bar": C["ink"],
            "badge": C["ink"], "badge_text": C["lime"], "stripe": C["lime2"]}


def logo(s: Slide, x, y, w, dark=False):
    s.image(asset("meadow-logo-black.png" if dark else C["logo"], "logo"), x, y, w, w * 19.001 / 150, fit="contain", name="Logo")


def header(s: Slide, ctx: Ctx, spec, width=1728):
    """Eyebrow + title. Returns y where content may start."""
    y = 88
    if spec.get("eyebrow"):
        s.text(M, y, width, spec["eyebrow"], family="Geist Mono", weight=500, size=20, color=C["hi"],
               lh=1.2, caps=True, tracking=0.04, name="Eyebrow")
    y = 124
    th = s.text(M, y, width, spec.get("title", ""), family=ctx.head_family(spec.get("title", "")), weight=ctx.head_weight(spec.get("title", "")), size=64,
                lh=1.1, tracking=-0.02, max_h=150, name="Title")
    y += th
    if spec.get("subtitle"):
        y += 12 + s.text(M, y + 12, width, spec["subtitle"], size=28, color=C["text2"], lh=1.35, max_h=80, name="Subtitle")
    return max(CONTENT_TOP, y + 56)


def footer(s: Slide, ctx: Ctx, dark=False):
    if ctx.deck.get("footer", True) is False:
        return
    logo(s, M, 990, 144, dark=dark)
    s.text(W - M - 300, 988, 300, f"{s.index:02d} / {s.total:02d}", family="Geist Mono", weight=500, size=20,
           color=C["ink2"] if dark else C["dim"], lh=1.2, align="right", typo=False, name="Page")


def bullets(s: Slide, x, y, w, items, *, size=26, color=None, dot=None, gap=18, lh=1.35):
    color, dot = color or C["fg"], dot or C["hi"]
    for it in items:
        s.ellipse(x, y + size * lh / 2 - 5, 10, dot)
        y += s.text(x + 28, y, w - 28, it, size=size, color=color, lh=lh) + gap
    return y


def numbered_rows(s: Slide, x, y, w, items, *, size=28, h=76):
    for i, it in enumerate(items, 1):
        s.rect(x, y, w, h, C["row"], R_ROW)
        s.text(x + 24, y + (h - 24) / 2, 50, f"{i:02d}", family="Geist Mono", weight=500, size=20, color=C["hi"], lh=1.2, typo=False)
        s.text(x + 80, y + (h - size * 1.2) / 2, w - 104, it, weight=500, size=size, lh=1.2)
        y += h + 12
    return y


def card(s: Slide, x, y, w, h, c, *, title_size=32):
    """Generic card: optional number, label, title, text, bullets, rows, note, image."""
    accent = c.get("accent")
    if accent:
        s.accents += 1
    fill, fg, fg2, num = accent_colors(accent)
    s.rect(x, y, w, h, fill, R_CARD, name="Card")
    cx, cy, cw = x + PAD, y + PAD, w - 2 * PAD
    if c.get("image"):
        ih = c.get("image_height", round(h * 0.45))
        s.image(asset(c["image"], "backgrounds"), x + 16, y + 16, w - 32, ih, radius=R_ROW)
        cy = y + 16 + ih + 28
    if c.get("number") is not None:
        s.text(cx, cy, cw, str(c["number"]), family="Geist Mono", weight=500, size=20, color=num, lh=1.2, typo=False)
        cy += 24 + 20
    if c.get("label"):
        s.text(cx, cy, cw, c["label"], family="Geist Mono", weight=500, size=18, color=fg2, lh=1.2, caps=True, tracking=0.04)
        cy += 22 + 18
    if c.get("value"):
        vh = s.text(cx, cy, cw, c["value"], family="Syne", weight=700, size=c.get("value_size", 64), color=num if not accent else fg, lh=1.0, typo=False)
        cy += vh + 12
    if c.get("title"):
        cy += s.text(cx, cy, cw, c["title"], weight=600, size=title_size, color=fg, lh=1.25) + 20
    if c.get("text"):
        cy += s.text(cx, cy, cw, c["text"], size=26, color=fg if accent in ("lime", "blue") else C["text2"], lh=1.4) + 20
    if c.get("rows"):
        cy = numbered_rows(s, cx - 16, cy, cw + 32, c["rows"]) + 8
    if c.get("bullets"):
        cy = bullets(s, cx, cy, cw, c["bullets"], color=fg, dot=fg if accent in ("lime", "blue") else C["hi"])
    if c.get("note"):
        s.text(cx, cy + 4, cw, c["note"], size=22, color=fg2, lh=1.4)
        cy += s.measure(c["note"], cw, size=22, lh=1.4)
    if cy > y + h - PAD + 24:
        s.warnings.append(f"slide {s.index}: card content taller than card ({int(cy - y)}>{int(h)}px): {c.get('title') or c.get('label') or ''!r}")


def grid(n, cols, x, y, w, h, gap=GAP, rows_h=None):
    """Return boxes for n cells in `cols` columns; last row stretches to fill width."""
    rows = (n + cols - 1) // cols
    rh = (h - gap * (rows - 1)) / rows
    boxes, i = [], 0
    for r in range(rows):
        k = min(cols, n - i)
        cw = (w - gap * (k - 1)) / k
        for j in range(k):
            boxes.append((x + j * (cw + gap), y + r * (rh + gap), cw, rh))
        i += k
    return boxes


# ---------------------------------------------------------------- layouts
LIGHT_PANEL_W = 720


def backdrop(s: Slide, spec, default, bottom=H - M):
    """The image behind a cover / section / contacts slide. Returns the width the copy may use.
    Dark theme: wide images go full-bleed under a scrim, portrait ones sit on the right and fade
    into the canvas. Light theme: the image is a rounded panel on the right (a white scrim over
    a dark image only greys it out), or nothing at all with "background": null."""
    name = spec.get("background", default)
    if not name:
        return W - 2 * M
    bg = asset(name, "backgrounds")
    if C["bg"] != THEMES["dark"]["bg"]:
        s.image(bg, W - M - LIGHT_PANEL_W, M, LIGHT_PANEL_W, bottom - M, radius=R_CARD, name="Photo")
        return W - 2 * M - LIGHT_PANEL_W - 96
    with Image.open(bg) as im_:
        wide = im_.width / im_.height > 1.5
    if wide:
        s.image(bg, 0, 0, W, H, scrim=spec.get("scrim", "left"), name="Background")
        return W - 2 * M
    s.image(bg, W - 1040, 0, 1040, H, scrim="fade-left", name="Photo")
    return 900


def layout_cover(spec, ctx, s: Slide):
    room = backdrop(s, spec, "wave-05")
    logo(s, M, 96, 280)
    y = 300
    if spec.get("chip"):
        s.pill(M, y, 44, spec["chip"], fill=C["lime"], color=C["ink"], family="Geist Mono", weight=500,
               size=20, pad=24, tracking=0.04, caps=True, name="Chip")
        y += 44 + 32
    title, size = spec.get("title", ""), spec.get("title_size", 160)
    fam, wt = ctx.head_family(title), ctx.head_weight(title, 700, 800)
    while size > 72 and max(line_width(w_, fam, wt, size, -0.03) for w_ in (typograph(title).replace("\n", " ").split(" "))) > min(1300, room):
        size -= 8   # the longest word must fit the column (narrower next to a light-theme panel)
    th = s.text(M, y, min(1300, room), title, family=ctx.head_family(spec.get("title", "")), weight=wt,
                size=size, lh=1.0, tracking=-0.03, max_h=340, name="Title")
    y += th + 32
    if spec.get("subtitle"):
        s.text(M, y, min(860, room), spec["subtitle"], size=40, color=C["text2"], lh=1.3, max_h=160)
    stats = spec.get("stats", [])
    if stats:
        sx = M
        base_w = min(440, room / len(stats))
        for st in stats:
            vw = line_width(str(st["value"]), "Syne", 700, 48)
            sw = max(base_w, vw + 38 * len(st.get("icons", [])) + 56)   # a wide value pushes the next stat over
            s.text(sx, 900, sw, str(st["value"]), family="Syne", weight=700, size=48, color=C["hi"], lh=1.0, typo=False)
            ix = sx + vw + 20
            for ic in st.get("icons", []):
                s.image(asset(ic, "icons"), ix, 912, 26, 26, fit="contain", name=f"Icon {ic}")
                ix += 38
            s.text(sx, 962, sw - 24, st.get("label", ""), size=24, color=C["text2"], lh=1.3)
            sx += sw
        if sx - M > room + 24:
            s.warnings.append(f"slide {s.index}: cover stats are {sx - M:.0f}px wide, the column has {room:.0f}; shorten the values or drop one")


def layout_section(spec, ctx, s: Slide):
    room = backdrop(s, spec, "wave-02", bottom=CONTENT_BOTTOM)
    y = 400
    if spec.get("eyebrow"):
        s.text(M, y - 56, 1200, spec["eyebrow"], family="Geist Mono", weight=500, size=24, color=C["hi"], caps=True, tracking=0.04, lh=1.2)
    y += s.text(M, y, min(1400, room), spec.get("title", ""), family=ctx.head_family(spec.get("title", "")), weight=ctx.head_weight(spec.get("title", "")), size=112, lh=1.05, tracking=-0.03, max_h=360) + 32
    if spec.get("subtitle"):
        s.text(M, y, min(1000, room), spec["subtitle"], size=36, color=C["text2"], lh=1.35)
    footer(s, ctx)


def layout_statement(spec, ctx, s: Slide):
    if spec.get("eyebrow"):
        s.text(M, 240, 1200, spec["eyebrow"], family="Geist Mono", weight=500, size=20, color=C["hi"], caps=True, tracking=0.04, lh=1.2)
    y = 300
    y += s.text(M, y, 1500, spec.get("title", ""), family=ctx.head_family(spec.get("title", "")), weight=ctx.head_weight(spec.get("title", "")), size=96, lh=1.1, tracking=-0.03, max_h=440) + 48
    if spec.get("text"):
        s.text(M, y, 1100, spec["text"], size=36, color=C["text2"], lh=1.4, max_h=CONTENT_BOTTOM - y)
    footer(s, ctx)


def layout_text_cards(spec, ctx, s: Slide):
    """Slide 02 of the content-factory deck: 1–2 text columns on top, 1–3 cards below."""
    y = header(s, ctx, spec)
    cols = spec.get("columns", [])
    cards = spec.get("cards", [])
    if cols:
        if len(cards) == len(cols):   # columns start on the card edges below them
            boxes = [(bx, bw - 56) for bx, _, bw, _ in grid(len(cols), len(cols), M, 0, W - 2 * M, 1)]
        else:
            cw = (W - 2 * M - 96 * (len(cols) - 1)) / len(cols)
            boxes = [(M + i * (cw + 96), cw) for i in range(len(cols))]
        hmax = 0
        for (cx, cw), para in zip(boxes, cols):
            hmax = max(hmax, s.text(cx, y, cw, para, size=28, color=C["text2"], lh=1.45))
        y += hmax + 56
    if cards:
        for box, c in zip(grid(len(cards), len(cards), M, y, W - 2 * M, CONTENT_BOTTOM - y), cards):
            card(s, *box, c)
    footer(s, ctx)


def layout_cards(spec, ctx, s: Slide):
    y = header(s, ctx, spec)
    if spec.get("intro"):
        y += s.text(M, y, 1300, spec["intro"], size=28, color=C["text2"], lh=1.45) + 40
    cards = spec.get("cards", [])
    cols = spec.get("columns_count") or (len(cards) if len(cards) <= 4 else (3 if len(cards) in (5, 6, 9) else 4))
    ts = 32 if cols <= 3 else 28
    for box, c in zip(grid(len(cards), cols, M, y, W - 2 * M, CONTENT_BOTTOM - y), cards):
        card(s, *box, c, title_size=ts)
    footer(s, ctx)


def layout_steps(spec, ctx, s: Slide):
    """Slide 05: numbered steps as a grid of cards + optional callout plate below."""
    y = header(s, ctx, spec)
    steps = spec.get("steps", [])
    callout = spec.get("callout")
    bottom = CONTENT_BOTTOM - (248 + GAP if callout else 0)
    cols = spec.get("columns_count") or {5: 5, 6: 3, 7: 4, 8: 4}.get(len(steps), min(4, len(steps)))
    for i, (box, st) in enumerate(zip(grid(len(steps), cols, M, y, W - 2 * M, bottom - y), steps), 1):
        x, yy, w, h = box
        st = st if isinstance(st, dict) else {"title": st}
        s.rect(x, yy, w, h, C["card"], R_CARD)
        s.text(x + 32, yy + 28, w - 64, f"{i:02d}", family="Geist Mono", weight=500, size=20, color=C["hi"], lh=1.2, typo=False)
        th = s.text(x + 32, yy + 68, w - 64, st["title"], weight=500, size=28, lh=1.3, max_h=h - 68 - 12)
        if st.get("text"):
            s.text(x + 32, yy + 68 + th + 12, w - 64, st["text"], size=22, color=C["muted"], lh=1.4, max_h=h - 92 - th)
    if callout:
        accent = callout.get("accent", "lime")
        s.accents += 1
        fill, fg, fg2, _ = accent_colors(accent)
        cy = CONTENT_BOTTOM - 248
        s.rect(M, cy, W - 2 * M, 248, fill, R_CARD, name="Callout")
        if callout.get("value"):
            s.text(M + 48, cy + 48, 260, callout["value"], family="Syne", weight=700, size=120, color=fg, lh=1.0, typo=False)
            s.text(M + 48, cy + 176, 240, callout.get("label", ""), size=20, color=fg2, lh=1.3)
        tx = M + 316 if callout.get("value") else M + 48
        th = s.text(tx, cy + 64, W - 2 * M - (tx - M) - 48, callout.get("title", ""), weight=600, size=34, color=fg, lh=1.25)
        if callout.get("text"):
            s.text(tx, cy + 64 + th + 16, W - 2 * M - (tx - M) - 200, callout["text"], size=24, color=fg2, lh=1.4)
    footer(s, ctx)


def kpi_tile(s, x, y, w, h, t, dark_on_lime=True):
    s.rect(x, y, w, h, C["tile"] if dark_on_lime else C["card"], R_ROW + 4)
    s.text(x + 28, y + 28, w - 56, t.get("label", ""), family="Geist Mono", weight=500, size=16, color=C["muted"], caps=True, tracking=0.04, lh=1.2)
    vs = t.get("size") or (64 if h >= 180 else 44)
    vy = y + 28 + 19 + (24 if h >= 180 else 14)
    vw = s.text(x + 28, vy, w - 56, str(t.get("value", "")), family="Syne", weight=700, size=vs, color=C["tile_value"] if dark_on_lime else C["hi"], lh=1.0, typo=False)
    ix = x + 28 + line_width(str(t.get("value", "")), "Syne", 700, vs) + 16
    for ic in t.get("icons", []):
        s.image(asset(ic, "icons"), ix, vy + vs * 0.3, vs * 0.42, vs * 0.42, fit="contain", flow=True)
        ix += vs * 0.42 + 12
    if t.get("caption") and h >= 140:
        s.text(x + 28, vy + vs + 14, w - 56, t["caption"], size=22, color=C["text2"], lh=1.3)


def layout_kpi(spec, ctx, s: Slide):
    """Slide 10: lime plate with dark KPI tiles (2 rows), a note line, optional steps strip."""
    y = header(s, ctx, spec)
    steps = spec.get("steps", [])
    plate_bottom = CONTENT_BOTTOM - (208 + GAP if steps else 0)
    s.accents += 1
    P = plate(spec.get("accent", "lime"))
    s.rect(M, y, W - 2 * M, plate_bottom - y, P["fill"], R_CARD + 8, name="KPI plate")
    tiles = spec.get("tiles", [])
    big, small = tiles[:3], tiles[3:]
    note_h = 56 if (spec.get("note_left") or spec.get("note_right")) else 0
    ih = plate_bottom - y - 2 * 24 - note_h
    r1 = ih * 0.56 if small else ih
    for box, t in zip(grid(len(big), len(big), M + 24, y + 24, W - 2 * M - 48, r1), big):
        kpi_tile(s, *box, t)
    if small:
        for box, t in zip(grid(len(small), len(small), M + 24, y + 24 + r1 + 16, W - 2 * M - 48, ih - r1 - 16), small):
            kpi_tile(s, *box, t)
    if note_h:
        ny = plate_bottom - 24 - 36
        s.text(M + 32, ny, 1100, spec.get("note_left", ""), weight=600, size=24, color=P["fg"], lh=1.3)
        s.text(W - M - 32 - 700, ny, 700, spec.get("note_right", ""), size=24, color=P["fg2"], lh=1.3, align="right")
    if steps:
        sy = CONTENT_BOTTOM - 208
        lw = 300 if spec.get("steps_title") else 0
        tile_edges = [e for p in s.prims if p.kind == "rect" and p.y < sy for e in (p.x, p.x + p.w)]
        for d_ in (0, -8, 8, -16, 16, -24, 24):   # edges either meet exactly or sit clearly apart
            xs = [e for b_ in grid(len(steps), len(steps), M + lw + d_, sy, W - 2 * M - lw - d_, 208) for e in (b_[0], b_[0] + b_[2])]
            if not any(0.5 < abs(a_ - b_) <= 6 for a_ in xs for b_ in tile_edges):
                lw += d_
                break
        if lw:
            s.text(M, sy + 20, lw - 24, spec["steps_title"], weight=600, size=40, lh=1.15)
            if spec.get("steps_text"):
                s.text(M, sy + 20 + s.measure(spec["steps_title"], lw - 24, weight=600, size=40, lh=1.15) + 16, lw - 40, spec["steps_text"], size=22, color=C["muted"], lh=1.35)
        for i, (box, st) in enumerate(zip(grid(len(steps), len(steps), M + lw, sy, W - 2 * M - lw, 208), steps), 1):
            x, yy, w, h = box
            s.rect(x, yy, w, h, C["card"], R_CARD)
            s.text(x + 28, yy + 28, w - 56, f"{i:02d}", family="Geist Mono", weight=500, size=18, color=C["hi"], lh=1.2, typo=False)
            s.text(x + 28, yy + h - 28 - s.measure(st, w - 56, weight=500, size=24, lh=1.3), w - 56, st, weight=500, size=24, lh=1.3)
    footer(s, ctx)


def layout_case(spec, ctx, s: Slide):
    """Slides 11–12: facts on the left, lime result plate with bars + KPI tiles on the right."""
    y = header(s, ctx, spec)
    lw = 1020
    blocks = spec.get("blocks", [])
    hs = []
    for b in blocks:
        if b.get("facts"):
            hs.append(2 * 36 + len(b["facts"]) * 40)
        else:
            hs.append(2 * 36 + 34 + s.measure(b.get("text", ""), lw - 72, size=26, lh=1.45))
    free = CONTENT_BOTTOM - y - GAP * (len(blocks) - 1) - sum(hs)
    hs = [h_ + free / len(blocks) for h_ in hs] if blocks else hs
    by = y
    for b, bh in zip(blocks, hs):
        s.rect(M, by, lw, bh, C["card"], R_CARD)
        if b.get("facts"):
            fy = by + 36 + (bh - 72 - len(b["facts"]) * 40) / 2
            for k, v in b["facts"]:
                s.text(M + 36, fy + 4, 220, k, family="Geist Mono", weight=500, size=16, color=C["muted"], caps=True, tracking=0.04, lh=1.3)
                s.text(M + 36 + 240, fy, lw - 312, v, weight=500, size=24, lh=1.35)
                fy += 40
        else:
            s.text(M + 36, by + 36, lw - 72, b.get("label", ""), family="Geist Mono", weight=500, size=16, color=C["muted"], caps=True, tracking=0.04, lh=1.3)
            s.text(M + 36, by + 36 + 34, lw - 72, b.get("text", ""), size=26, lh=1.45)
        by += bh + GAP
    r = spec.get("result", {})
    rx, rw = M + lw + GAP, W - 2 * M - lw - GAP
    s.accents += 1
    P = plate(r.get("accent", "lime"))
    s.rect(rx, y, rw, CONTENT_BOTTOM - y, P["fill"], R_CARD, name="Result plate")
    px = rx + 40
    s.text(px, y + 40, rw - 80, r.get("label", ""), family="Geist Mono", weight=500, size=16, color=P["fg2"], caps=True, tracking=0.04, lh=1.3)
    vy = y + 84
    vs = 120
    s.text(px, vy, rw - 80, str(r.get("value", "")), family="Syne", weight=700, size=vs, color=P["fg"], lh=1.0, typo=False)
    vw = line_width(str(r.get("value", "")), "Syne", 700, vs)
    if r.get("unit"):
        s.text(px + vw + 20, vy + vs - 60, rw - 120 - vw, r["unit"], family=ctx.head_family(r["unit"]), weight=700, size=52, color=P["fg"], lh=1.0, flow=True)
    a_, d_, _ = vmetrics("Syne", 700)
    base_y = vy + a_ * vs                          # baseline of the hero number (lh 1.0)
    cy = base_y + 28                               # caption row: clear air under the digits
    if r.get("caption"):
        row_h = 36 if r.get("badge") else 24 * 1.3
        s.text(px, cy + (row_h - 24 * 1.3) / 2, 300, r["caption"], size=24, color=P["fg"], lh=1.3)
        cwid = line_width(typograph(r["caption"]), "Geist", 400, 24)
        if r.get("badge"):
            s.pill(px + cwid + 16, cy, 36, r["badge"], fill=P["badge"], color=P["badge_text"], size=18, pad=16, name="Badge", flow=True)
        cy += row_h
    tiles = r.get("tiles", [])
    tiles_h = 112 if tiles else 0
    ty = CONTENT_BOTTOM - 40 - tiles_h
    bars = r.get("bars", [])
    if bars:
        top, base = cy + 28, ty - 24 - 24
        vmax = max(b_["value"] for b_ in bars)
        bw_ = (rw - 80 - 32 * (len(bars) - 1)) / len(bars)
        colw = min(bw_, 84)
        for i, b_ in enumerate(bars):
            cx = px + i * (bw_ + 32) + (bw_ - colw) / 2
            bh = (base - top - 56) * b_["value"] / vmax  # zero baseline: heights stay proportional
            s.rect(cx, base - bh, colw, bh, P["bar"], 16)
            s.text(cx - 40, base - bh - 52, colw + 80, b_.get("display", str(b_["value"])), family="Syne", weight=700, size=34, color=P["fg"], align="center", lh=1.1, typo=False)
            s.text(cx - 40, base + 12, colw + 80, b_.get("label", ""), family="Geist Mono", weight=500, size=14, color=P["fg2"], align="center", caps=True, tracking=0.04, lh=1.2)
    for box, t in zip(grid(len(tiles), len(tiles), px - 16, ty, rw - 48, tiles_h, gap=16), tiles):
        kpi_tile(s, *box, {**t, "size": 40})
    footer(s, ctx)


def layout_table(spec, ctx, s: Slide):
    y = header(s, ctx, spec)
    cols = spec["columns"]
    rows = spec["rows"]
    widths = spec.get("widths") or [1] * len(cols)
    tw = W - 2 * M
    ws = [tw * w_ / sum(widths) for w_ in widths]
    hl = spec.get("highlight_column")
    P = plate(spec.get("accent", "lime"))
    rh = min(88, (CONTENT_BOTTOM - y - 64) / max(1, len(rows)))
    if hl is not None:
        s.accents += 1
        hx = M + sum(ws[:hl])
        s.rect(hx, y - 8, ws[hl], 64 + rh * len(rows) + 16, P["fill"], R_CARD)
    x = M
    for i, (c_, w_) in enumerate(zip(cols, ws)):
        s.text(x + 24, y + 18, w_ - 48, c_, family="Geist Mono", weight=500, size=16, color=P["fg2"] if i == hl else C["muted"], caps=True, tracking=0.04, lh=1.3)
        x += w_
    y += 64
    for r_i, row in enumerate(rows):
        if r_i % 2 == 0:
            s.rect(M, y, tw, rh, C["card"], R_ROW)
            if hl is not None:
                s.rect(M + sum(ws[:hl]), y, ws[hl], rh, P["stripe"], 0)
        x = M
        for i, (val, w_) in enumerate(zip(row, ws)):
            s.text(x + 24, y + (rh - 24 * 1.3) / 2, w_ - 48, val, weight=600 if i == 0 else 400, size=24,
                   color=P["fg"] if i == hl else (C["fg"] if i == 0 else C["text2"]), lh=1.3, max_h=rh)
            x += w_
        y += rh
    footer(s, ctx)


def layout_quotes(spec, ctx, s: Slide):
    y = header(s, ctx, spec)
    qs = spec.get("quotes", [])
    for box, q in zip(grid(len(qs), len(qs), M, y, W - 2 * M, CONTENT_BOTTOM - y), qs):
        x, yy, w, h = box
        s.rect(x, yy, w, h, C["card"], R_CARD)
        s.text(x + 40, yy + 24, 80, "“", family="Syne", weight=700, size=120, color=C["hi"], lh=1.0, typo=False)
        qs_ = 36 if len(qs) <= 2 else 28
        s.text(x + 40, yy + 140, w - 80, q["text"], size=qs_, lh=1.4, max_h=h - 280)
        if q.get("logo"):
            s.image(asset(q["logo"], "logo"), x + 40, yy + h - 40 - 96, 160, 40, fit="contain")
        s.text(x + 40, yy + h - 40 - 48, w - 80, q.get("author", ""), weight=600, size=24, lh=1.2)
        s.text(x + 40, yy + h - 40 - 18, w - 80, q.get("role", ""), size=20, color=C["muted"], lh=1.0)
    footer(s, ctx)


def layout_image_text(spec, ctx, s: Slide):
    y = header(s, ctx, spec, width=860)
    right = spec.get("image_side", "right") == "right"
    iw = 860
    ix = W - M - iw if right else M
    tx = M if right else M + iw + 96
    tw = W - 2 * M - iw - 96
    s.image(asset(spec["image"], "backgrounds"), ix, 88 if right else y, iw, CONTENT_BOTTOM - (88 if right else y), radius=R_CARD)
    if spec.get("text"):
        y += s.text(tx, y, tw, spec["text"], size=30, color=C["text2"], lh=1.45) + 40
    if spec.get("bullets"):
        bullets(s, tx, y, tw, spec["bullets"], size=28)
    footer(s, ctx)


def layout_logos(spec, ctx, s: Slide):
    y = header(s, ctx, spec)
    logos = spec.get("logos", [])
    cols = spec.get("columns_count", 6)
    for box, lg in zip(grid(len(logos), cols, M, y, W - 2 * M, CONTENT_BOTTOM - y, gap=48), logos):
        x, yy, w, h = box
        s.image(asset(lg, "logo"), x + w * 0.15, yy + h * 0.25, w * 0.7, h * 0.5, fit="contain")
    footer(s, ctx)


def layout_contacts(spec, ctx, s: Slide):
    room = backdrop(s, spec, "people-02-camera-blue")
    logo(s, M, 96, 280)
    y = 400
    tw_ = min(1300, room)
    y += s.text(M, y, tw_, spec.get("title", ""), family=ctx.head_family(spec.get("title", "")), weight=ctx.head_weight(spec.get("title", ""), 600, 700), size=128 if room > 1000 else 112, lh=1.05, tracking=-0.03, max_h=260) + 28
    if spec.get("subtitle"):
        y += s.text(M, y, tw_, spec["subtitle"], size=36, color=C["text2"], lh=1.35) + 48
    x = M
    for i, b in enumerate(spec.get("buttons", [])):
        primary = b.get("primary", i == 0)
        label = b["label"] + ("  ↗" if b.get("url") else "")
        bw = s.pill(x, y, 72, label, fill=C["lime"] if primary else C["glass"], color=C["ink"] if primary else C["fg"],
                    size=26, pad=36, stroke=None if primary else C["glass_stroke"], link=b.get("url"), typo=False, name="Button")
        x += bw + 20


# ---------------------------------------------------------------- ruled layouts (investor deck)
# Airy slides held together by thin rules instead of cards: accent rule on top of a block,
# accent caps label, big Syne value, grey copy, and a takeaway line above the footer.
def rule(s: Slide, x, y, w, color=None, h=2):
    s.rect(x, y, w, h, color or C["hi"], 0, name="Rule")


def label(s: Slide, x, y, w, text, color=None, size=20):
    return s.text(x, y, w, text, family="Geist Mono", weight=500, size=size, color=color or C["hi"], caps=True,
                  tracking=0.04, lh=1.2, name="Label")


def takeaway(s: Slide, ctx: Ctx, spec, bottom=CONTENT_BOTTOM, ruled=True):
    """The slide's conclusion at the bottom: rule, optional label, a line in Syne/Geist, a grey line.
    `spec["takeaway"]` is a string or {"label","title","text"}. Returns the y the content above must stop at."""
    t = spec.get("takeaway")
    if not t:
        return bottom
    t = {"title": t} if isinstance(t, str) else t
    w = W - 2 * M
    fam, wt = ctx.head_family(t.get("title", "")), ctx.head_weight(t.get("title", ""))
    th = s.measure(t.get("title", ""), w, family=fam, weight=wt, size=36, lh=1.3)
    xh = s.measure(t.get("text", ""), w, size=24, lh=1.4)
    lh_ = 24 + 16 if t.get("label") else 0
    top = bottom - th - (xh + 10 if xh else 0) - lh_
    y = top
    if t.get("label"):
        label(s, M, y, w, t["label"])
        y += lh_
    y += s.text(M, y, w, t.get("title", ""), family=fam, weight=wt, size=36, lh=1.3, name="Takeaway")
    if xh:
        s.text(M, y + 10, w, t["text"], size=24, color=C["text2"], lh=1.4)
    if ruled:
        rule(s, M, top - 40, w)
        return top - 40 - 56
    return top - 56


def fit_size(text, fam, wt, size, width, floor=32):
    while size > floor and line_width(text, fam, wt, size) > width:
        size -= 4
    return size


def layout_team(spec, ctx, s: Slide):
    """Investor deck 02: people in columns. Round photo on a lime disc (a cut-out PNG shows the
    disc, a plain photo just crops round), name, role in accent caps, a short bio."""
    y = header(s, ctx, spec)
    bottom = takeaway(s, ctx, spec)
    people = spec.get("people", [])
    n = max(1, len(people))
    gap = 64
    cw = (W - 2 * M - gap * (n - 1)) / n
    d = min(spec.get("photo_size", 240), cw * 0.7)
    for i, pp in enumerate(people):
        x = M + i * (cw + gap)
        yy = y
        if pp.get("photo") is not None:
            s.ellipse(x, yy, d, C["lime"], name="Photo disc")
            if pp.get("photo"):
                s.image(asset(pp["photo"], "backgrounds"), x, yy, d, d, radius=d / 2, name="Photo")
            yy += d + 32
        nm = pp.get("name", "")
        yy += s.text(x, yy, cw, nm, family=ctx.head_family(nm), weight=ctx.head_weight(nm), size=36, lh=1.2, name="Name") + 12
        if pp.get("role"):
            yy += label(s, x, yy, cw, pp["role"]) + 16
        if pp.get("bio"):
            s.text(x, yy, cw, pp["bio"], size=24, color=C["text2"], lh=1.45, max_h=bottom - yy, name="Bio")
    footer(s, ctx)


def layout_stats(spec, ctx, s: Slide):
    """Investor deck 'Playbook': 3-5 big numbers in one band, each under its own accent rule."""
    y = header(s, ctx, spec)
    bottom = takeaway(s, ctx, spec)
    stats = spec.get("stats", [])
    n = max(1, len(stats))
    gap = 56
    cw = (W - 2 * M - gap * (n - 1)) / n
    vs = min(fit_size(str(st.get("value", "")), "Syne", 700, 72 if n <= 3 else 64, cw) for st in stats) if stats else 64
    lab_h = max([s.measure(st.get("label", ""), cw, size=26, lh=1.4) for st in stats] or [0])
    band_h = 2 + 40 + vs + 24 + lab_h
    by = y + max(0, (bottom - y - band_h) / 2)    # the band floats in the middle of the free space
    for i, st in enumerate(stats):
        x = M + i * (cw + gap)
        rule(s, x, by, cw)
        s.text(x, by + 42, cw, str(st.get("value", "")), family="Syne", weight=700, size=vs, lh=1.0, typo=False, name="Value")
        s.text(x, by + 42 + vs + 24, cw, st.get("label", ""), size=26, color=C["text2"], lh=1.4, name="Stat label")
    footer(s, ctx)


def layout_chart(spec, ctx, s: Slide):
    """Investor deck 'Traction': bars on the left (history grey, the bars that matter in the
    accent colour), a column of headline numbers on the right, takeaway below.
    Heights are proportional to the values with a zero baseline."""
    y = header(s, ctx, spec)
    bottom = takeaway(s, ctx, spec)
    stats = spec.get("stats", [])
    lw = (W - 2 * M) * (0.48 if stats else 1.0)
    rule(s, M, y, lw)
    label(s, M, y + 24, lw, spec.get("chart_label", ""))
    bars = spec.get("bars", [])
    if bars:
        notes = any(b_.get("note") for b_ in bars)
        foot = 16 + 32 * 1.1 + 8 + 22 * 1.3 + (22 * 1.3 if notes else 0)
        top, base = y + 24 + 24 + 40, bottom - foot
        vmax = max(b_["value"] for b_ in bars) or 1
        gap = 40
        bw = min(140, (lw - gap * (len(bars) - 1)) / len(bars))
        for i, b_ in enumerate(bars):
            x = M + i * (bw + gap)
            bh = max(3, (base - top) * b_["value"] / vmax)
            s.rect(x, base - bh, bw, bh, C["hi"] if b_.get("accent") else C["bar_past"], 0, name="Bar", flow=True)  # data, not grid
            ty = base + 16
            ty += s.text(x, ty, bw + gap - 8, b_.get("display", str(b_["value"])), family="Syne", weight=700, size=32, lh=1.1, typo=False, flow=True) + 8
            ty += s.text(x, ty, bw + gap - 8, b_.get("label", ""), size=22, color=C["text2"], lh=1.3, flow=True)
            if b_.get("note"):
                s.text(x, ty, bw + gap - 8, b_["note"], size=22, color=C["text2"], lh=1.3, flow=True)
    if stats:
        rx = M + lw + 96
        rw = W - M - rx
        rh = (bottom - y) / len(stats)
        for i, st in enumerate(stats):
            yy = y + i * rh
            rule(s, rx, yy, rw, C["rule"], 2)
            label(s, rx, yy + 24, rw, st.get("label", ""), size=18)
            vs = fit_size(str(st.get("value", "")), "Syne", 700, 56, rw)
            s.text(rx, yy + 24 + 22 + 20, rw, str(st.get("value", "")), family="Syne", weight=700, size=vs, lh=1.0, typo=False)
            if st.get("note"):
                s.text(rx, yy + 24 + 22 + 20 + vs + 14, rw, st["note"], size=22, color=C["hi"], lh=1.3)
    footer(s, ctx)


def layout_highlight(spec, ctx, s: Slide):
    """Investor deck 'Why now': a big blue (or lime) block with the claim, one line of it on a
    marker, a source line; optional stats and a takeaway under the block."""
    accent = spec.get("accent", "blue")
    P = plate(accent)
    s.accents += 1
    lines = spec.get("lines") or str(spec.get("title", "")).split("\n")
    mark = spec.get("mark")
    size = spec.get("title_size", 88)
    pad = 72
    fams = [(ctx.head_family(l_), ctx.head_weight(l_)) for l_ in lines]
    lh = size * 1.2
    h = pad + (24 + 28 if spec.get("eyebrow") else 0) + len(lines) * lh + (24 + 22 * 1.3 if spec.get("source") else 0) + pad
    y0 = 88
    s.rect(M, y0, W - 2 * M, h, P["fill"], R_CARD, name="Highlight plate")
    y = y0 + pad
    if spec.get("eyebrow"):
        label(s, M + pad, y, W - 2 * M - 2 * pad, spec["eyebrow"], color=C["lime"] if accent == "blue" else P["fg2"])
        y += 24 + 28
    for i, (l_, (fam, wt)) in enumerate(zip(lines, fams)):
        # no negative tracking here: QuickLook/Google ignore it, and the marker must hug the line
        # in every renderer, so the line is measured and drawn at its natural width
        t = typograph(l_)
        if i == mark:
            il, ir = ink_x(t, fam, wt, size)
            a_, _, cap = vmetrics(fam, wt)
            base = y + (lh - size) / 2 + a_ * size           # baseline of this line
            mp = 0.28 * size                                  # equal air above the caps and below the baseline
            mfill, mtext = (C["lime"], C["ink"]) if accent == "blue" else (C["ink"], C["lime"])
            s.rect(M + pad + il - mp, base - cap * size - mp, ir - il + 2 * mp, cap * size + 2 * mp, mfill, 16, name="Marker", flow=True)
            s.text(M + pad, y, W - 2 * M - 2 * pad, l_, family=fam, weight=wt, size=size, color=mtext, lh=1.2, flow=True)
        else:
            s.text(M + pad, y, W - 2 * M - 2 * pad, l_, family=fam, weight=wt, size=size, color=P["fg"], lh=1.2)
        y += lh
    if spec.get("source"):
        s.text(M + pad, y + 24, W - 2 * M - 2 * pad, spec["source"], weight=500, size=22, color=P["fg2"], lh=1.3)
    bottom = takeaway(s, ctx, spec, ruled=False)
    stats = spec.get("stats", [])
    if stats:
        sy = y0 + h + 56
        cw = (W - 2 * M - 56 * (len(stats) - 1)) / len(stats)
        for i, st in enumerate(stats):
            x = M + i * (cw + 56)
            s.text(x, sy, cw, str(st.get("value", "")), family="Syne", weight=700, size=48, lh=1.0, typo=False)
            s.text(x, sy + 48 + 16, cw, st.get("label", ""), size=24, color=C["text2"], lh=1.35)
        if sy + 48 + 16 + 64 > bottom + 56:
            s.warnings.append(f"slide {s.index}: highlight stats run into the takeaway; shorten the block")
    footer(s, ctx)


LAYOUTS = {k[7:].replace("_", "-"): v for k, v in globals().items() if k.startswith("layout_")}


# ---------------------------------------------------------------- alignment gate
def _text_lines(t):
    pr = t.props
    return wrap(pr["text"], font(pr["family"], pr["weight"], pr["size"]), t.w)


def _ink_box(t):
    """Ink box of a text primitive: x from the glyphs, y from baseline to cap height
    (the optical box designers centre). Same model as the renderers."""
    pr = t.props
    a, d, cap = vmetrics(pr["family"], pr["weight"])
    L = pr["size"] * pr["lh"]
    lines = _text_lines(t)
    if pr.get("valign") == "middle":
        top = t.y + (t.h - len(lines) * L) / 2
        first = top + L * a / (a + d)
    else:
        first = t.y + (L - pr["size"]) / 2 + a * pr["size"]
    xs = []
    for line in lines:
        lw_ = line_width(line, pr["family"], pr["weight"], pr["size"], pr["tracking"])
        off = {"left": 0, "center": (t.w - lw_) / 2, "right": t.w - lw_}[pr["align"]]
        l, r = ink_x(line, pr["family"], pr["weight"], pr["size"], pr["tracking"])
        xs.append((t.x + off + l, t.x + off + r))
    return (min(x[0] for x in xs), first - cap * pr["size"],
            max(x[1] for x in xs), first + (len(lines) - 1) * L)


def check_alignment(s: Slide, tol=1.5, near=4):
    """Layout lint, run on every build. Adds WARN lines for:
    - text not optically centred in a pill / chip / button / badge,
    - content outside the 96px side margins (bleeding images are fine),
    - edges that almost line up (off by 1-4px): a near miss is always a bug,
    - same-size cards in a row or a stack with uneven gaps."""
    out = s.warnings.append
    rects = [p for p in s.prims if p.kind in ("rect", "image")]
    texts = [p for p in s.prims if p.kind == "text" and p.props["text"].strip()]
    bleed = lambda p: p.x <= 0.5 or p.y <= 0.5 or p.x + p.w >= W - 0.5 or p.y + p.h >= H - 0.5

    # 1. pills: anything fully rounded and short, holding one single-line text
    for r in rects:
        if r.kind != "rect" or r.h > 96 or r.props.get("radius", 0) < r.h / 2 - 1:
            continue
        inside = [t for t in texts if r.x - 1 <= t.x <= r.x + r.w and r.y - 8 <= t.y + t.props["size"] / 2 <= r.y + r.h + 8]
        if len(inside) != 1 or len(_text_lines(inside[0])) != 1:
            continue
        il, it, ir, ib = _ink_box(inside[0])
        dl, dr, dt, db = il - r.x, r.x + r.w - ir, it - r.y, r.y + r.h - ib
        if abs(dl - dr) > tol or abs(dt - db) > tol:
            out(f"slide {s.index}: text off-centre in a pill ({inside[0].props['text'][:30]!r}): "
                f"left {dl:.1f} / right {dr:.1f}, top {dt:.1f} / bottom {db:.1f}px; build it with Slide.pill()")

    # 2. side margins
    for p in rects + texts:
        if p.kind == "image" and bleed(p) or p.kind == "rect" and p.w >= W - 1:
            continue
        l, _, r, _ = _ink_box(p) if p.kind == "text" else (p.x, 0, p.x + p.w, 0)
        if l < M - tol or r > W - M + tol:
            what = p.props["text"][:30] if p.kind == "text" else (p.name or p.kind)
            out(f"slide {s.index}: {what!r} crosses the {M}px side margin ({l:.0f}..{r:.0f})")

    # 3. near-miss edges
    boxes = [p for p in rects if not bleed(p) and not p.props.get("flow")]
    label = lambda p: (p.props["text"][:24] if p.kind == "text" else (p.name or p.kind))
    edges = {
        "left": [(p.x, p) for p in boxes] + [(t.x, t) for t in texts if t.props["align"] == "left" and not t.props.get("flow")],
        "right": [(p.x + p.w, p) for p in boxes],
        "top": [(p.y, p) for p in boxes],
        "bottom": [(p.y + p.h, p) for p in boxes],
    }
    for side, vals in edges.items():
        by = {}
        for v, p in vals:
            by.setdefault(round(v, 1), p)
        keys = sorted(by)
        for a_, b_ in zip(keys, keys[1:]):
            if 0.5 < b_ - a_ <= near:
                out(f"slide {s.index}: {side} edges almost line up: {label(by[a_])!r} at {a_:g} vs "
                    f"{label(by[b_])!r} at {b_:g}px; snap them")

    # 4. rows and stacks of same-size boxes: equal gaps
    cards = [p for p in boxes if p.kind == "rect" and p.props.get("radius", 0) >= R_ROW and not p.props.get("pill")]
    for key, axis in (((lambda p: (round(p.y), round(p.h), round(p.w))), "x"), ((lambda p: (round(p.x), round(p.w), round(p.h))), "y")):
        groups = {}
        for p in cards:
            groups.setdefault(key(p), []).append(p)
        for g in groups.values():
            if len(g) < 3:
                continue
            g.sort(key=lambda p: getattr(p, axis))
            size = "w" if axis == "x" else "h"
            gaps = [getattr(b_, axis) - getattr(a_, axis) - getattr(a_, size) for a_, b_ in zip(g, g[1:])]
            if max(gaps) - min(gaps) > tol:
                out(f"slide {s.index}: uneven gaps in a {'row' if axis == 'x' else 'stack'} of {len(g)} boxes: "
                    + ", ".join(f"{v:.0f}" for v in gaps) + "px")


def build(deck):
    ctx = Ctx(deck)
    slides = []
    for i, spec in enumerate(deck["slides"], 1):
        theme = spec.get("theme") or deck.get("theme", "dark")
        use_theme(theme)
        s = Slide(i, ctx.total)
        s.theme, s.flower = theme, spec.get("flower")
        name = spec.get("layout")
        if name not in LAYOUTS:
            raise SystemExit(f"slide {i}: unknown layout {name!r}; choose from {sorted(LAYOUTS)}")
        LAYOUTS[name](spec, ctx, s)
        s.notes = spec.get("notes", "")
        s.name = spec.get("name") or f"{i:02d} — {spec.get('title', name)}".replace("\n", " ")[:80]
        check_alignment(s)
        if s.accents > 1:
            s.warnings.append(f"slide {i}: {s.accents} accent plates; Meadow slides carry at most one")
        slides.append(s)
    sprinkle_flowers(slides, deck)
    use_theme("dark")
    return ctx, slides


# ---------------------------------------------------------------- flowers
# Meadow's brand accents (assets/flowers/*.svg, from the investor deck). Drawn as native vectors.
# Each SVG keeps its geometry; colour comes from the theme. An SVG with a stroke is an outline
# flower, otherwise a filled one.
FLOWER_COLORS = {
    # solid fills, and "glass": a see-through tint with a border in the same colour (the original
    # asterisk was white 10% + white stroke over a background blur; PPTX has no backdrop blur)
    "light": {"fill": ["#D3FF31", "#5260DA"], "glass": [("#5260DA1F", "#5260DA")]},
    "dark": {"fill": ["#D3FF31", "#4E5BCF"], "glass": [("#FFFFFF1A", "#FFFFFF"), ("#D3FF311F", "#D3FF31")]},
}
GLASS_SHARE = 0.5   # share of filled flowers drawn as glass; outline flowers are always glass
_flower_cache = {}


def _svg_path(d):
    """Absolute M/L/H/V/C/Z path data -> subpaths of M/L/C/Z segments."""
    toks = re.findall(r"[MLHVCZmlhvcz]|-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?", d)
    subs, cur, x, y, i, cmd = [], None, 0.0, 0.0, 0, None
    num = lambda k: float(toks[k])
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            if t.islower():
                raise ValueError("flower SVGs must use absolute path commands")
            cmd = t
            i += 1
            if cmd == "Z":
                cur.append(("Z",))
            continue
        if cmd == "M":
            x, y = num(i), num(i + 1); i += 2
            cur = [("M", x, y)]; subs.append(cur); cmd = "L"
        elif cmd == "L":
            x, y = num(i), num(i + 1); i += 2; cur.append(("L", x, y))
        elif cmd == "H":
            x = num(i); i += 1; cur.append(("L", x, y))
        elif cmd == "V":
            y = num(i); i += 1; cur.append(("L", x, y))
        elif cmd == "C":
            seg = tuple(num(i + k) for k in range(6)); i += 6
            x, y = seg[4], seg[5]; cur.append(("C",) + seg)
        else:
            raise ValueError(f"unsupported path command {cmd!r}")
    return subs


def flower_shapes():
    if not _flower_cache:
        folder = os.path.join(ASSETS, "flowers")
        for f in sorted(os.listdir(folder)):
            if not f.endswith(".svg"):
                continue
            svg = open(os.path.join(folder, f)).read()
            vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]
            el = re.search(r'<path\b[^>]*\bd="([^"]+)"[^>]*>', svg)
            outline = "stroke=" in el.group(0)
            sw = float(re.search(r'stroke-width="([\d.]+)"', el.group(0)).group(1)) if outline else 0
            _flower_cache[f[:-4]] = {"size": max(vb[2], vb[3]), "subpaths": _svg_path(el.group(1)), "outline": outline, "stroke_w": sw}
    return _flower_cache


def _place_flower(s: Slide, name, cx, cy, size, angle, color, glass=None):
    """color = solid fill, or the border when `glass` (a translucent fill) is given."""
    sh = flower_shapes()[name]
    k = size / sh["size"]
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    h = sh["size"] / 2

    def tr(px_, py_):
        dx, dy = (px_ - h) * k, (py_ - h) * k
        return cx + dx * ca - dy * sa, cy + dx * sa + dy * ca
    subs = []
    for sp in sh["subpaths"]:
        out = []
        for seg in sp:
            pts = [tr(seg[j], seg[j + 1]) for j in range(1, len(seg), 2)]
            out.append((seg[0],) + tuple(v for pt in pts for v in pt))
        subs.append(out)
    if sh["outline"]:
        s.path(subs, fill=glass, stroke=color, stroke_w=max(1.5, sh["stroke_w"] * k * 0.8), name=f"Flower {name}")
    elif glass:
        s.path(subs, fill=glass, stroke=color, stroke_w=max(1.5, size / 60), name=f"Flower {name}")
    else:
        s.path(subs, fill=color, name=f"Flower {name}")


def _occupied(s: Slide, pad=40):
    boxes = []
    for p in s.prims:
        if p.kind == "text":
            if not p.props["text"].strip():
                continue
            l, t, r, b = _ink_box(p)
            boxes.append((l - pad, t - pad, r + pad, b + pad + p.props["size"] * 0.3))
        else:
            boxes.append((p.x - pad, p.y - pad, p.x + p.w + pad, p.y + p.h + pad))
    return boxes


def sprinkle_flowers(slides, deck):
    """A few flowers, not many: about one slide in three gets one, never two slides in a row,
    and only where it lands in clear space. Seeded from the deck, so rebuilds don't reshuffle.
    Deck "flowers": true / false (default: on for light-theme slides only), "flowers_seed": n;
    a slide's "flower": true / false forces it in or out."""
    mode = deck.get("flowers")
    if mode is False:
        return
    rng = random.Random(deck.get("flowers_seed", zlib.crc32(deck.get("title", "").encode())))
    names = sorted(flower_shapes())
    want = lambda s: s.flower if s.flower is not None else (mode is True or s.theme == "light")
    pool = [s for s in slides if want(s)]
    forced = [s for s in pool if s.flower is True]
    budget = max(len(forced), round(len(pool) * 0.3))
    order = forced + rng.sample([s for s in pool if s not in forced], len(pool) - len(forced))
    placed, last = 0, set()
    for s in order:
        if placed >= budget:
            break
        if s.flower is not True and (s.index - 1 in last or s.index + 1 in last):
            continue
        boxes = _occupied(s)
        for _ in range(300):
            size = rng.uniform(80, 150)
            cx, cy = rng.uniform(M / 2 + size / 2, W - M / 2 - size / 2), rng.uniform(56 + size / 2, H - 56 - size / 2)
            r = size * 0.72   # rotation-safe half extent
            if not any(cx + r > l and cx - r < rr and cy + r > t and cy - r < b for l, t, rr, b in boxes):
                break
        else:
            continue
        name = rng.choice(names)
        pal = FLOWER_COLORS[s.theme]
        if flower_shapes()[name]["outline"] or rng.random() < GLASS_SHARE:
            glass, color = rng.choice(pal["glass"])
        else:
            glass, color = None, rng.choice(pal["fill"])
        _place_flower(s, name, cx, cy, size, rng.uniform(-30, 30), color, glass)
        placed += 1
        last.add(s.index)


# ---------------------------------------------------------------- image prep
def prep_image(p: Prim, tmpdir, scale=1.0):
    """Cover/contain-fit the source into the box at 1x, bake the scrim in. Returns a file path."""
    src = p.props["src"]
    im = Image.open(src)
    has_alpha = im.mode in ("RGBA", "LA", "P")
    im = im.convert("RGBA" if has_alpha else "RGB")
    bw, bh = max(1, round(p.w * scale)), max(1, round(p.h * scale))
    if p.props.get("fit") == "contain":
        return src
    r = max(bw / im.width, bh / im.height)
    im = im.resize((max(bw, round(im.width * r)), max(bh, round(im.height * r))), Image.LANCZOS)
    left, top = (im.width - bw) // 2, (im.height - bh) // 2
    im = im.crop((left, top, left + bw, top + bh)).convert("RGB")
    sc = p.props.get("scrim")
    if sc:
        ov = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        base = p.props.get("scrim_rgb") or (14, 16, 19)
        if sc == "left":       # dark behind the copy on the left, image breathes on the right
            side, floor = Image.new("L", (bw, bh), 0), Image.new("L", (bw, bh), 0)
            ds, df = ImageDraw.Draw(side), ImageDraw.Draw(floor)
            for x in range(bw):
                t = x / bw
                ds.line([(x, 0), (x, bh)], fill=240 if t < 0.32 else max(0, int(240 * (1 - (t - 0.32) / 0.43))))
            for y in range(bh):  # and a floor so footer/stats stay readable
                t = y / bh
                if t > 0.7:
                    df.line([(0, y), (bw, y)], fill=int(200 * (t - 0.7) / 0.3))
            ov = Image.new("RGBA", (bw, bh), (*base, 0))
            ov.putalpha(ImageChops.lighter(side, floor))  # max of the two, so the floor never lightens the side
        elif sc == "fade-left":
            for x in range(bw):
                t = x / bw
                d.line([(x, 0), (x, bh)], fill=(*base, int(255 * max(0, 1 - t / 0.45) ** 1.6)))
        elif sc == "bottom":
            for y in range(bh):
                t = y / bh
                d.line([(0, y), (bw, y)], fill=(*base, int(235 * max(0, (t - 0.35) / 0.65))))
        elif sc == "full":
            d.rectangle([0, 0, bw, bh], fill=(*base, 150))
        im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
    out = os.path.join(tmpdir, f"img_{id(p)}.jpg")
    im.save(out, quality=86)
    return out


# ---------------------------------------------------------------- PPTX writer
def write_pptx(slides, out, portable=False, title="", embed_notes=False):
    from pptx import Presentation
    from pptx.util import Emu, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.oxml.ns import qn
    from lxml import etree

    PX = 6350  # EMU per Figma px on a 13.333in-wide slide
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(W * PX), Emu(H * PX)
    prs.core_properties.title = title
    blank = prs.slide_layouts[6]
    tmp = tempfile.mkdtemp(prefix="meadow_deck_")

    def rgb(hexc):
        h = hexc.lstrip("#")
        return RGBColor.from_string(h[:6].upper()), (int(h[6:8], 16) / 255 if len(h) == 8 else 1.0)

    def set_alpha(fill_elm, a):
        if a >= 1:
            return
        clr = fill_elm.find(qn("a:srgbClr"))
        al = etree.SubElement(clr, qn("a:alpha"))
        al.set("val", str(int(a * 100000)))

    def fill_shape(shp, hexc):
        col, a = rgb(hexc)
        shp.fill.solid()
        shp.fill.fore_color.rgb = col
        set_alpha(shp._element.spPr.find(qn("a:solidFill")), a)

    for s in slides:
        sl = prs.slides.add_slide(blank)
        bgfill = sl.background.fill
        bgfill.solid()
        bgfill.fore_color.rgb = rgb(s.bg)[0]
        for p in s.prims:
            x, y, w, h = (Emu(round(v * PX)) for v in (p.x, p.y, p.w, p.h))
            if p.kind in ("rect", "ellipse"):
                r = p.props.get("radius", 0) if p.kind == "rect" else 0
                kind = MSO_SHAPE.OVAL if p.kind == "ellipse" else (MSO_SHAPE.ROUNDED_RECTANGLE if r else MSO_SHAPE.RECTANGLE)
                shp = sl.shapes.add_shape(kind, x, y, w, h)
                if r:
                    shp.adjustments[0] = min(0.5, r / max(1, min(p.w, p.h)))
                fill_shape(shp, p.props["fill"])
                st = p.props.get("stroke")
                if st:
                    col, a = rgb(st)
                    shp.line.color.rgb = col
                    shp.line.width = Emu(PX)
                    ln = shp._element.spPr.find(qn("a:ln"))
                    set_alpha(ln.find(qn("a:solidFill")), a)
                else:
                    shp.line.fill.background()
                shp.shadow.inherit = False
                if p.props.get("link"):
                    shp.click_action.hyperlink.address = p.props["link"]
                if p.name:
                    shp.name = p.name
            elif p.kind == "path":
                w, h = max(w, Emu(1)), max(h, Emu(1))
                shp = sl.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
                spPr = shp._element.spPr
                geom = spPr.find(qn("a:prstGeom"))
                U = PX    # path units = EMU, same as the shape extent: QuickLook ignores any path scale
                cg = etree.Element(qn("a:custGeom"))
                for tag in ("a:avLst", "a:gdLst", "a:ahLst", "a:cxnLst"):
                    etree.SubElement(cg, qn(tag))
                rc = etree.SubElement(cg, qn("a:rect"))
                for k_, v_ in (("l", "0"), ("t", "0"), ("r", "r"), ("b", "b")):
                    rc.set(k_, v_)
                pa = etree.SubElement(etree.SubElement(cg, qn("a:pathLst")), qn("a:path"))
                pa.set("w", str(w))
                pa.set("h", str(h))
                if not p.props.get("fill"):
                    pa.set("fill", "none")
                for sp in p.props["subpaths"]:
                    for seg in sp:
                        if seg[0] == "Z":
                            etree.SubElement(pa, qn("a:close"))
                            continue
                        el = etree.SubElement(pa, qn({"M": "a:moveTo", "L": "a:lnTo", "C": "a:cubicBezTo"}[seg[0]]))
                        for j in range(1, len(seg), 2):
                            pt = etree.SubElement(el, qn("a:pt"))
                            pt.set("x", str(round((seg[j] - p.x) * U)))
                            pt.set("y", str(round((seg[j + 1] - p.y) * U)))
                geom.addprevious(cg)
                spPr.remove(geom)
                if p.props.get("fill"):
                    fill_shape(shp, p.props["fill"])
                else:
                    shp.fill.background()
                if p.props.get("stroke"):
                    shp.line.color.rgb = rgb(p.props["stroke"])[0]
                    shp.line.width = Emu(round(p.props["stroke_w"] * PX))
                else:
                    shp.line.fill.background()
                shp.shadow.inherit = False
                shp.name = p.name or "Flower"
            elif p.kind == "image":
                path = prep_image(p, tmp, scale=1.0 if p.w * p.h > 400_000 else 2.0)
                if p.props.get("fit") == "contain":
                    im = Image.open(path)
                    r_ = min(p.w / im.width, p.h / im.height)
                    iw, ih = im.width * r_, im.height * r_
                    pic = sl.shapes.add_picture(path, Emu(round((p.x + (p.w - iw) / 2) * PX)), Emu(round((p.y + (p.h - ih) / 2) * PX)), Emu(round(iw * PX)), Emu(round(ih * PX)))
                else:
                    pic = sl.shapes.add_picture(path, x, y, w, h)
                r = p.props.get("radius", 0)
                if r:
                    geom = pic._element.spPr.find(qn("a:prstGeom"))
                    geom.set("prst", "roundRect")
                    av = geom.find(qn("a:avLst"))
                    if av is None:
                        av = etree.SubElement(geom, qn("a:avLst"))
                    gd = etree.SubElement(av, qn("a:gd"))
                    gd.set("name", "adj")
                    gd.set("fmla", f"val {int(50000 * min(1, 2 * r / min(p.w, p.h)))}")
                if p.name:
                    pic.name = p.name
            elif p.kind == "text":
                pr = p.props
                extra = 8  # PowerPoint wraps a touch earlier than our measurement
                tb = sl.shapes.add_textbox(Emu(round(p.x * PX)), y, Emu(round((p.w + extra) * PX)), h)
                tf = tb.text_frame
                tf.word_wrap = True
                tf.auto_size = None
                for side in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
                    setattr(tf, side, 0)
                tf.vertical_anchor = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}[pr["valign"]]
                fam, bold = pptx_font(pr["family"], pr["weight"], portable)
                col, _ = rgb(pr["color"])
                mfont = font(pr["family"], pr["weight"], pr["size"])
                for i, paragraph in enumerate(pr["text"].split("\n")):
                    para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                    para.alignment = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}[pr["align"]]
                    para.line_spacing = Pt(pr["size"] * pr["lh"] / 2)
                    # Our own wrap, written as soft line breaks: Keynote and PowerPoint would
                    # otherwise re-wrap (Keynote breaks at hyphens), and the slide drifts from
                    # the layout the checks approved. Editing still reflows within a line.
                    for j, line in enumerate(wrap(paragraph, mfont, p.w)):
                        if j:
                            para.add_line_break()
                        run = para.add_run()
                        run.text = line
                        f = run.font
                        f.size = Pt(pr["size"] / 2)
                        f.name = fam
                        f.bold = bold
                        f.color.rgb = col
                        rpr = run._r.get_or_add_rPr()
                        for tag in ("a:ea", "a:cs"):
                            e = etree.SubElement(rpr, qn(tag))
                            e.set("typeface", fam)
                        if pr["tracking"]:
                            rpr.set("spc", str(int(pr["tracking"] * pr["size"] / 2 * 100)))
                if pr.get("link"):
                    tb.click_action.hyperlink.address = pr["link"]
                if p.name:
                    tb.name = p.name
        if s.notes and embed_notes:
            sl.notes_slide.notes_text_frame.text = s.notes
    prs.save(out)


# ---------------------------------------------------------------- PNG renderer (Pillow)
def _rgba(hexc):
    h = hexc.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + ((int(h[6:8], 16),) if len(h) == 8 else (255,))


def write_pdf(slides, path):
    """Full-resolution Pillow render of every slide, saved as one PDF."""
    tmp = tempfile.mkdtemp(prefix="meadow_pdf_")
    render_png(slides, tmp, scale=1.0)
    pages = [Image.open(os.path.join(tmp, f)).convert("RGB")
             for f in sorted(os.listdir(tmp)) if f.startswith("slide-")]
    pages[0].save(path, save_all=True, append_images=pages[1:], resolution=144)


def _draw_line(im, line, x, baseline, hi, tr, asc, desc, width, color):
    """Draw one line supersampled: glyphs placed at exact fractional positions on a 4x layer,
    then box-filtered down. Drawing at 1x would round every glyph to a whole pixel and make
    letter-spacing jitter."""
    if not line.strip():
        return
    left, top = max(0, math.floor(x) - 2), max(0, math.floor(baseline - asc) - 2)
    w_, h_ = math.ceil(width + x - left) + 4, math.ceil(baseline + desc - top) + 4
    mask = Image.new("L", (w_ * 4, h_ * 4), 0)
    d4 = ImageDraw.Draw(mask)
    ox, oy = (x - left) * 4, (baseline - top) * 4
    if tr:
        for i, ch in enumerate(line):
            if ch.strip():
                d4.text((ox + hi.getlength(line[:i]) + tr * 4 * i, oy), ch, font=hi, fill=255, anchor="ls")
    else:
        d4.text((ox, oy), line, font=hi, fill=255, anchor="ls")
    mask = mask.resize((w_, h_), Image.BOX)
    if color[3] < 255:
        mask = mask.point(lambda v: v * color[3] // 255)
    layer = Image.new("RGBA", (w_, h_), color[:3] + (0,))
    layer.putalpha(mask)
    w_, h_ = min(w_, im.width - left), min(h_, im.height - top)
    if w_ > 0 and h_ > 0:
        im.alpha_composite(layer.crop((0, 0, w_, h_)), (left, top))


def _flatten(sp, k):
    pts, cur = [], (0, 0)
    for seg in sp:
        if seg[0] in ("M", "L"):
            cur = (seg[1] * k, seg[2] * k)
            pts.append(cur)
        elif seg[0] == "C":
            (x0, y0) = cur
            (x1, y1), (x2, y2), (x3, y3) = [(seg[j] * k, seg[j + 1] * k) for j in (1, 3, 5)]
            for i in range(1, 25):
                t = i / 24
                u = 1 - t
                pts.append((u**3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t**3 * x3,
                            u**3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * y3))
            cur = (x3, y3)
    return pts


def _draw_path(im, p, scale):
    """Even-odd fill and/or stroke, drawn at 4x and box-filtered down."""
    ss = 4
    k = scale * ss
    size = (im.width * ss, im.height * ss)
    fill = Image.new("1", size, 0)
    line = Image.new("L", size, 0)
    for sp in p.props["subpaths"]:
        pts = _flatten(sp, k)
        if len(pts) < 2:
            continue
        if p.props.get("fill"):
            one = Image.new("1", size, 0)
            ImageDraw.Draw(one).polygon(pts, fill=1)
            fill = ImageChops.logical_xor(fill, one)
        if p.props.get("stroke"):
            ImageDraw.Draw(line).line(pts + [pts[0]], fill=255, width=max(1, round(p.props["stroke_w"] * k)), joint="curve")
    for key, mask in (("fill", fill.convert("L")), ("stroke", line)):   # fill first, border on top
        if not p.props.get(key):
            continue
        col = _rgba(p.props[key])
        layer = Image.new("RGBA", im.size, col[:3] + (0,))
        layer.putalpha(mask.resize(im.size, Image.BOX).point(lambda v: v * col[3] // 255))
        im = Image.alpha_composite(im, layer)
    return im


def render_png(slides, outdir, scale=0.5):
    """Draw the computed layout with Pillow. Close to the PPTX (tracking included),
    but needs no office app, so it works in any sandbox."""
    os.makedirs(outdir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="meadow_png_")
    files = []
    for s in slides:
        im = Image.new("RGBA", (int(W * scale), int(H * scale)), _rgba(s.bg))
        for p in s.prims:
            box = [p.x * scale, p.y * scale, (p.x + p.w) * scale, (p.y + p.h) * scale]
            if p.kind in ("rect", "ellipse"):
                layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
                d = ImageDraw.Draw(layer)
                fill = _rgba(p.props["fill"])
                outline = _rgba(p.props["stroke"]) if p.props.get("stroke") else None
                if p.kind == "ellipse":
                    d.ellipse(box, fill=fill)
                else:
                    d.rounded_rectangle(box, radius=p.props.get("radius", 0) * scale, fill=fill, outline=outline)
                im = Image.alpha_composite(im, layer)
            elif p.kind == "path":
                im = _draw_path(im, p, scale)
            elif p.kind == "image":
                src = prep_image(p, tmp, scale=scale) if p.props.get("fit") != "contain" else p.props["src"]
                pic = Image.open(src).convert("RGBA")
                if p.props.get("fit") == "contain":
                    pic.thumbnail((max(1, int(p.w * scale)), max(1, int(p.h * scale))), Image.LANCZOS)
                    ox = int(box[0] + (p.w * scale - pic.width) / 2)
                    oy = int(box[1] + (p.h * scale - pic.height) / 2)
                else:
                    pic = pic.resize((max(1, int(p.w * scale)), max(1, int(p.h * scale))))
                    ox, oy = int(box[0]), int(box[1])
                mask = None
                if p.props.get("radius"):
                    mask = Image.new("L", pic.size, 0)
                    ImageDraw.Draw(mask).rounded_rectangle([0, 0, pic.width, pic.height], radius=p.props["radius"] * scale, fill=255)
                    if pic.mode == "RGBA":
                        mask = Image.composite(pic.getchannel("A"), Image.new("L", pic.size, 0), mask)
                im.paste(pic, (ox, oy), mask if mask is not None else pic)
            elif p.kind == "text":
                pr = p.props
                d = ImageDraw.Draw(im)
                f = font(pr["family"], pr["weight"], pr["size"] * scale)
                lh = pr["size"] * pr["lh"] * scale
                y = p.y * scale
                tr = pr.get("tracking", 0) * pr["size"] * scale   # letter-spacing in px, as in the PPTX
                lines = wrap(pr["text"], font(pr["family"], pr["weight"], pr["size"]), p.w)
                asc, desc, _ = vmetrics(pr["family"], pr["weight"])
                if pr.get("valign") == "middle":
                    y = (p.y + (p.h - len(lines) * pr["size"] * pr["lh"]) / 2) * scale
                sz = pr["size"] * scale
                hi = font(pr["family"], pr["weight"], sz * 4)   # 4x: unhinted advances, like Keynote
                adv = lambda t_: hi.getlength(t_) / 4
                color = _rgba(pr["color"])
                for line in lines:
                    lw_ = adv(line) + tr * max(0, len(line) - 1)
                    x = p.x * scale + {"left": 0, "center": (p.w * scale - lw_) / 2, "right": p.w * scale - lw_}[pr["align"]]
                    if pr.get("valign") == "middle":
                        bl = y + lh * asc / (asc + desc)
                    else:
                        bl = y + (lh - sz) / 2 + asc * sz
                    _draw_line(im, line, x, bl, hi, tr, asc * sz, desc * sz, lw_, color)
                    y += lh
        path = os.path.join(outdir, f"slide-{s.index:02d}.png")
        im.convert("RGB").save(path)
        files.append(path)
    tw, th, cols = 640, 360, 3
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * 16, rows * th + (rows + 1) * 16), "#2a2d33")
    for i, f_ in enumerate(files):
        t = Image.open(f_); t.thumbnail((tw, th))
        sheet.paste(t, (16 + (i % cols) * (tw + 16), 16 + (i // cols) * (th + 16)))
    sp = os.path.join(outdir, "contact-sheet.png")
    sheet.save(sp)
    return sp


# ---------------------------------------------------------------- Figma dump
def write_figma_json(slides, out, title=""):
    """Primitives in px for scripts/figma_render.js. Images are listed by local path;
    upload them with the Figma MCP upload_assets tool and fill the placeholders."""
    tmp = os.path.join(os.path.dirname(os.path.abspath(out)), "figma-images")
    if os.path.isdir(tmp):
        for f_ in os.listdir(tmp):
            os.remove(os.path.join(tmp, f_))
    os.makedirs(tmp, exist_ok=True)
    doc = {"title": title, "width": W, "height": H, "slides": []}
    for s in slides:
        items = []
        for p in s.prims:
            d = {"kind": p.kind, "x": round(p.x, 1), "y": round(p.y, 1), "w": round(p.w, 1), "h": round(p.h, 1), "name": p.name}
            if p.kind == "image":
                d["file"] = prep_image(p, tmp, scale=1.0) if p.props.get("fit") != "contain" else p.props["src"]
                d["radius"] = p.props.get("radius", 0)
                d["fit"] = p.props.get("fit")
            else:
                d.update({k: v for k, v in p.props.items() if v is not None})
            items.append(d)
        doc["slides"].append({"name": s.name, "bg": s.bg, "items": items, "notes": s.notes})
    with open(out, "w") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", nargs="?")
    ap.add_argument("-o", "--out", help="output .pptx (default: next to the spec)")
    ap.add_argument("--figma-json", help="also write a layout dump for scripts/figma_render.js")
    ap.add_argument("--portable", action="store_true", help="Regular/Bold only, for Google Slides or machines without the fonts")
    ap.add_argument("--embed-notes", action="store_true", help="put speaker notes into the PPTX (PowerPoint only: Keynote refuses to open such files)")
    ap.add_argument("--png", metavar="DIR", help="also draw every slide to PNG with Pillow (no Keynote/LibreOffice needed)")
    ap.add_argument("--pdf", metavar="FILE", help="also write a PDF (Pillow render at full 1920x1080; text is not selectable)")
    ap.add_argument("--list-layouts", action="store_true")
    a = ap.parse_args()
    if a.list_layouts:
        print("\n".join(sorted(LAYOUTS)))
        return
    with open(a.spec) as fh:
        deck = json.load(fh)
    ctx, slides = build(deck)
    out = a.out or os.path.splitext(a.spec)[0] + ".pptx"
    write_pptx(slides, out, portable=a.portable, title=deck.get("title", ""), embed_notes=a.embed_notes)
    print(f"wrote {out} ({len(slides)} slides, lang={ctx.lang})")
    if any(s.notes for s in slides) and not a.embed_notes:
        notes_path = os.path.splitext(out)[0] + "-notes.md"
        with open(notes_path, "w") as fh:
            for s in slides:
                if s.notes:
                    fh.write(f"## {s.name}\n\n{s.notes}\n\n")
        print(f"wrote {notes_path} (speaker notes; --embed-notes puts them in the PPTX for PowerPoint)")
    if a.png:
        sheet = render_png(slides, a.png)
        print(f"wrote {a.png}/ (contact sheet: {sheet})")
    if a.pdf:
        write_pdf(slides, a.pdf)
        print(f"wrote {a.pdf}")
    if a.figma_json:
        write_figma_json(slides, a.figma_json, title=deck.get("title", ""))
        print(f"wrote {a.figma_json}")
    warns = [w_ for s in slides for w_ in s.warnings]
    for w_ in warns:
        print("WARN", w_, file=sys.stderr)
    if warns:
        print(f"{len(warns)} warning(s): fix the copy or the layout choice, then rebuild.", file=sys.stderr)


if __name__ == "__main__":
    main()
