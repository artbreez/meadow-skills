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
import os
import re
import sys
import tempfile
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

C = {
    "bg": "#0E1013",
    "card": "#1A1D21",
    "row": "#23262B",
    "lime": "#D3FF31",
    "blue": "#4E5BCF",       # rare secondary plate, only when asked for
    "white": "#FFFFFF",
    "text2": "#C9CDD3",      # body copy on dark
    "muted": "#9AA1AB",      # captions, labels
    "dim": "#6B7280",        # page numbers
    "ink": "#0E1013",        # text on lime
    "ink2": "#3D4713",       # secondary text on lime
    "stroke": "#FFFFFF2E",   # 18% white hairline (outline chips)
}

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
    return f"{family} {STYLE_NAME[weight]}", False


_font_cache: dict = {}


def font(family, weight, size):
    key = (family, weight, round(size))
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(os.path.join(FONTS, FONT_FILES[(family, weight)]), round(size))
    return _font_cache[key]


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


def wrap(text, f, width):
    """Greedy word wrap; NBSP-joined words never split. Returns lines."""
    lines = []
    for para in text.split("\n"):
        words = para.split(" ")
        cur = ""
        for w_ in words:
            trial = w_ if not cur else cur + " " + w_
            if f.getlength(trial) <= width or not cur:
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
    def __init__(self, index, total, bg=C["bg"]):
        self.index, self.total, self.bg = index, total, bg
        self.prims: list[Prim] = []
        self.notes = ""
        self.warnings: list[str] = []
        self.accents = 0

    def rect(self, x, y, w, h, fill, radius=0, stroke=None, name="", link=None):
        self.prims.append(Prim("rect", x, y, w, h, {"fill": fill, "radius": radius, "stroke": stroke, "link": link}, name))

    def ellipse(self, x, y, d, fill, name=""):
        self.prims.append(Prim("ellipse", x, y, d, d, {"fill": fill}, name))

    def image(self, path, x, y, w, h, radius=0, name="", scrim=None, fit="cover"):
        self.prims.append(Prim("image", x, y, w, h, {"src": path, "radius": radius, "scrim": scrim, "fit": fit}, name))

    def text(self, x, y, w, text, *, family="Geist", weight=400, size=28, color=C["white"], lh=1.3,
             align="left", tracking=0.0, caps=False, max_h=None, name="", typo=True, valign="top", h=None, link=None):
        """Place a text block, return its measured height."""
        if text is None:
            return 0
        text = str(text)
        if caps:
            text = text.upper()
        if typo:
            text = typograph(text)
        f = font(family, weight, size)
        lines = wrap(text, f, w)
        mh = len(lines) * size * lh
        bh = h if h is not None else mh
        if max_h is not None and mh > max_h + 1:
            self.warnings.append(f"slide {self.index}: text overflows ({int(mh)}>{int(max_h)}px): {text[:50]!r}")
        if family == "Syne" and CYR.search(text):
            self.warnings.append(f"slide {self.index}: Syne has no Cyrillic, use Geist for {text[:40]!r}")
        self.prims.append(Prim("text", x, y, w, bh, {
            "text": text, "family": family, "weight": weight, "size": size, "color": color, "lh": lh,
            "align": align, "tracking": tracking, "valign": valign, "lines": len(lines), "link": link}, name))
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
    for ext in ("", ".jpg", ".png", "-white.png"):
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
        return C["blue"], C["white"], "#D9DDF7", C["white"]
    return C["card"], C["white"], C["muted"], C["lime"]


def logo(s: Slide, x, y, w, dark=False):
    s.image(asset("meadow-logo-black.png" if dark else "meadow-logo-lime.png", "logo"), x, y, w, w * 19.001 / 150, fit="contain", name="Logo")


def header(s: Slide, ctx: Ctx, spec, width=1728):
    """Eyebrow + title. Returns y where content may start."""
    y = 88
    if spec.get("eyebrow"):
        s.text(M, y, width, spec["eyebrow"], family="Geist Mono", weight=500, size=20, color=C["lime"],
               lh=1.2, caps=True, tracking=0.04, name="Eyebrow")
    y = 124
    th = s.text(M, y, width, spec.get("title", ""), family=ctx.head_family(spec.get("title", "")), weight=ctx.head_weight(spec.get("title", "")), size=64,
                lh=1.1, tracking=-0.02, max_h=150, name="Title")
    return max(CONTENT_TOP, y + th + 56)


def footer(s: Slide, ctx: Ctx, dark=False):
    if ctx.deck.get("footer", True) is False:
        return
    logo(s, M, 990, 144, dark=dark)
    s.text(W - M - 300, 988, 300, f"{s.index:02d} / {s.total:02d}", family="Geist Mono", weight=500, size=20,
           color=C["ink2"] if dark else C["dim"], lh=1.2, align="right", typo=False, name="Page")


def bullets(s: Slide, x, y, w, items, *, size=26, color=C["white"], dot=C["lime"], gap=18, lh=1.35):
    for it in items:
        s.ellipse(x, y + size * lh / 2 - 5, 10, dot)
        y += s.text(x + 28, y, w - 28, it, size=size, color=color, lh=lh) + gap
    return y


def numbered_rows(s: Slide, x, y, w, items, *, size=28, h=76):
    for i, it in enumerate(items, 1):
        s.rect(x, y, w, h, C["row"], R_ROW)
        s.text(x + 24, y + (h - 24) / 2, 50, f"{i:02d}", family="Geist Mono", weight=500, size=20, color=C["lime"], lh=1.2, typo=False)
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
        cy += s.text(cx, cy, cw, c["text"], size=26, color=fg if accent == "lime" else C["text2"], lh=1.4) + 20
    if c.get("rows"):
        cy = numbered_rows(s, cx - 16, cy, cw + 32, c["rows"]) + 8
    if c.get("bullets"):
        cy = bullets(s, cx, cy, cw, c["bullets"], color=fg, dot=fg if accent == "lime" else C["lime"])
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
def layout_cover(spec, ctx, s: Slide):
    bg = asset(spec.get("background", "wave-05"), "backgrounds")
    s.image(bg, 0, 0, W, H, scrim=spec.get("scrim", "left"), name="Background")
    logo(s, M, 96, 280)
    y = 300
    if spec.get("chip"):
        f = font("Geist Mono", 500, 20)
        cw = f.getlength(typograph(spec["chip"].upper())) * 1.04 + 48
        s.rect(M, y, cw, 44, C["lime"], 22, name="Chip")
        s.text(M + 24, y + 11, cw - 40, spec["chip"], family="Geist Mono", weight=500, size=20, color=C["ink"], lh=1.1, caps=True, tracking=0.04)
        y += 44 + 32
    th = s.text(M, y, 1300, spec.get("title", ""), family=ctx.head_family(spec.get("title", "")), weight=ctx.head_weight(spec.get("title", ""), 700, 800),
                size=spec.get("title_size", 160), lh=1.0, tracking=-0.03, max_h=340, name="Title")
    y += th + 32
    if spec.get("subtitle"):
        s.text(M, y, 860, spec["subtitle"], size=40, color=C["text2"], lh=1.3, max_h=160)
    stats = spec.get("stats", [])
    if stats:
        sx = M
        sw = min(440, (W - 2 * M) / len(stats))
        for st in stats:
            vw = font("Syne", 700, 48).getlength(str(st["value"]))
            s.text(sx, 900, sw, str(st["value"]), family="Syne", weight=700, size=48, color=C["lime"], lh=1.0, typo=False)
            ix = sx + vw + 20
            for ic in st.get("icons", []):
                s.image(asset(ic, "icons"), ix, 912, 26, 26, fit="contain", name=f"Icon {ic}")
                ix += 38
            s.text(sx, 962, sw - 24, st.get("label", ""), size=24, color=C["text2"], lh=1.3)
            sx += sw


def layout_section(spec, ctx, s: Slide):
    s.image(asset(spec.get("background", "wave-02"), "backgrounds"), 0, 0, W, H, scrim=spec.get("scrim", "left"))
    y = 400
    if spec.get("eyebrow"):
        s.text(M, y - 56, 1200, spec["eyebrow"], family="Geist Mono", weight=500, size=24, color=C["lime"], caps=True, tracking=0.04, lh=1.2)
    y += s.text(M, y, 1400, spec.get("title", ""), family=ctx.head_family(spec.get("title", "")), weight=ctx.head_weight(spec.get("title", "")), size=112, lh=1.05, tracking=-0.03, max_h=360) + 32
    if spec.get("subtitle"):
        s.text(M, y, 1000, spec["subtitle"], size=36, color=C["text2"], lh=1.35)
    footer(s, ctx)


def layout_statement(spec, ctx, s: Slide):
    if spec.get("eyebrow"):
        s.text(M, 240, 1200, spec["eyebrow"], family="Geist Mono", weight=500, size=20, color=C["lime"], caps=True, tracking=0.04, lh=1.2)
    y = 300
    y += s.text(M, y, 1500, spec.get("title", ""), family=ctx.head_family(spec.get("title", "")), weight=ctx.head_weight(spec.get("title", "")), size=96, lh=1.1, tracking=-0.03, max_h=440) + 48
    if spec.get("text"):
        s.text(M, y, 1100, spec["text"], size=36, color=C["text2"], lh=1.4, max_h=CONTENT_BOTTOM - y)
    footer(s, ctx)


def layout_text_cards(spec, ctx, s: Slide):
    """Slide 02 of the content-factory deck: 1–2 text columns on top, 1–3 cards below."""
    y = header(s, ctx, spec)
    cols = spec.get("columns", [])
    if cols:
        cw = (W - 2 * M - 96 * (len(cols) - 1)) / len(cols)
        hmax = 0
        for i, para in enumerate(cols):
            hmax = max(hmax, s.text(M + i * (cw + 96), y, cw, para, size=28, color=C["text2"], lh=1.45))
        y += hmax + 56
    cards = spec.get("cards", [])
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
        s.text(x + 32, yy + 28, w - 64, f"{i:02d}", family="Geist Mono", weight=500, size=20, color=C["lime"], lh=1.2, typo=False)
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
    s.rect(x, y, w, h, C["bg"] if dark_on_lime else C["card"], R_ROW + 4)
    s.text(x + 28, y + 28, w - 56, t.get("label", ""), family="Geist Mono", weight=500, size=16, color=C["muted"], caps=True, tracking=0.04, lh=1.2)
    vs = t.get("size") or (64 if h >= 180 else 44)
    vy = y + 28 + 19 + (24 if h >= 180 else 14)
    vw = s.text(x + 28, vy, w - 56, str(t.get("value", "")), family="Syne", weight=700, size=vs, color=C["lime"], lh=1.0, typo=False)
    ix = x + 28 + font("Syne", 700, vs).getlength(str(t.get("value", ""))) + 16
    for ic in t.get("icons", []):
        s.image(asset(ic, "icons"), ix, vy + vs * 0.3, vs * 0.42, vs * 0.42, fit="contain")
        ix += vs * 0.42 + 12
    if t.get("caption") and h >= 140:
        s.text(x + 28, vy + vs + 14, w - 56, t["caption"], size=22, color=C["text2"], lh=1.3)


def layout_kpi(spec, ctx, s: Slide):
    """Slide 10: lime plate with dark KPI tiles (2 rows), a note line, optional steps strip."""
    y = header(s, ctx, spec)
    steps = spec.get("steps", [])
    plate_bottom = CONTENT_BOTTOM - (208 + GAP if steps else 0)
    s.accents += 1
    s.rect(M, y, W - 2 * M, plate_bottom - y, C["lime"], R_CARD + 8, name="KPI plate")
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
        s.text(M + 32, ny, 1100, spec.get("note_left", ""), weight=600, size=24, color=C["ink"], lh=1.3)
        s.text(W - M - 32 - 700, ny, 700, spec.get("note_right", ""), size=24, color=C["ink2"], lh=1.3, align="right")
    if steps:
        sy = CONTENT_BOTTOM - 208
        lw = 300 if spec.get("steps_title") else 0
        if lw:
            s.text(M, sy + 20, lw - 24, spec["steps_title"], weight=600, size=40, lh=1.15)
            if spec.get("steps_text"):
                s.text(M, sy + 20 + s.measure(spec["steps_title"], lw - 24, weight=600, size=40, lh=1.15) + 16, lw - 40, spec["steps_text"], size=22, color=C["muted"], lh=1.35)
        for i, (box, st) in enumerate(zip(grid(len(steps), len(steps), M + lw, sy, W - 2 * M - lw, 208), steps), 1):
            x, yy, w, h = box
            s.rect(x, yy, w, h, C["card"], R_CARD)
            s.text(x + 28, yy + 28, w - 56, f"{i:02d}", family="Geist Mono", weight=500, size=18, color=C["lime"], lh=1.2, typo=False)
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
    s.rect(rx, y, rw, CONTENT_BOTTOM - y, C["lime"], R_CARD, name="Result plate")
    px = rx + 40
    s.text(px, y + 40, rw - 80, r.get("label", ""), family="Geist Mono", weight=500, size=16, color=C["ink2"], caps=True, tracking=0.04, lh=1.3)
    vy = y + 84
    vs = 120
    s.text(px, vy, rw - 80, str(r.get("value", "")), family="Syne", weight=700, size=vs, color=C["ink"], lh=1.0, typo=False)
    vw = font("Syne", 700, vs).getlength(str(r.get("value", "")))
    if r.get("unit"):
        s.text(px + vw + 20, vy + vs - 60, rw - 120 - vw, r["unit"], family=ctx.head_family(r["unit"]), weight=700, size=52, color=C["ink"], lh=1.0)
    cy = vy + vs + 16
    if r.get("caption"):
        s.text(px, cy, 300, r["caption"], size=24, color=C["ink"], lh=1.3)
        cwid = font("Geist", 400, 24).getlength(typograph(r["caption"]))
        if r.get("badge"):
            bw = font("Geist", 500, 18).getlength(r["badge"]) + 32
            s.rect(px + cwid + 16, cy - 4, bw, 36, C["ink"], 18)
            s.text(px + cwid + 32, cy + 4, bw - 24, r["badge"], weight=500, size=18, color=C["lime"], lh=1.1)
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
            s.rect(cx, base - bh, colw, bh, C["ink"], 16)
            s.text(cx - 40, base - bh - 52, colw + 80, b_.get("display", str(b_["value"])), family="Syne", weight=700, size=34, color=C["ink"], align="center", lh=1.1, typo=False)
            s.text(cx - 40, base + 12, colw + 80, b_.get("label", ""), family="Geist Mono", weight=500, size=14, color=C["ink2"], align="center", caps=True, tracking=0.04, lh=1.2)
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
    rh = min(88, (CONTENT_BOTTOM - y - 64) / max(1, len(rows)))
    if hl is not None:
        s.accents += 1
        hx = M + sum(ws[:hl])
        s.rect(hx, y - 8, ws[hl], 64 + rh * len(rows) + 16, C["lime"], R_CARD)
    x = M
    for i, (c_, w_) in enumerate(zip(cols, ws)):
        s.text(x + 24, y + 18, w_ - 48, c_, family="Geist Mono", weight=500, size=16, color=C["ink2"] if i == hl else C["muted"], caps=True, tracking=0.04, lh=1.3)
        x += w_
    y += 64
    for r_i, row in enumerate(rows):
        if r_i % 2 == 0:
            s.rect(M, y, tw, rh, C["card"], R_ROW)
            if hl is not None:
                s.rect(M + sum(ws[:hl]), y, ws[hl], rh, "#C4EE2A", 0)
        x = M
        for i, (val, w_) in enumerate(zip(row, ws)):
            s.text(x + 24, y + (rh - 24 * 1.3) / 2, w_ - 48, val, weight=600 if i == 0 else 400, size=24,
                   color=C["ink"] if i == hl else (C["white"] if i == 0 else C["text2"]), lh=1.3, max_h=rh)
            x += w_
        y += rh
    footer(s, ctx)


def layout_quotes(spec, ctx, s: Slide):
    y = header(s, ctx, spec)
    qs = spec.get("quotes", [])
    for box, q in zip(grid(len(qs), len(qs), M, y, W - 2 * M, CONTENT_BOTTOM - y), qs):
        x, yy, w, h = box
        s.rect(x, yy, w, h, C["card"], R_CARD)
        s.text(x + 40, yy + 24, 80, "“", family="Syne", weight=700, size=120, color=C["lime"], lh=1.0, typo=False)
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
    bg = asset(spec.get("background", "people-02-camera-blue"), "backgrounds")
    with Image.open(bg) as im_:
        wide = im_.width / im_.height > 1.5
    if wide:
        s.image(bg, 0, 0, W, H, scrim=spec.get("scrim", "left"), name="Background")
    else:  # portrait/square photo: hold it on the right, fade into the dark canvas
        s.image(bg, W - 1040, 0, 1040, H, scrim="fade-left", name="Photo")
    logo(s, M, 96, 280)
    y = 400
    tw_ = 1300 if wide else 900
    y += s.text(M, y, tw_, spec.get("title", ""), family=ctx.head_family(spec.get("title", "")), weight=ctx.head_weight(spec.get("title", ""), 600, 700), size=128 if wide else 112, lh=1.05, tracking=-0.03, max_h=260) + 28
    if spec.get("subtitle"):
        y += s.text(M, y, tw_, spec["subtitle"], size=36, color=C["text2"], lh=1.35) + 48
    x = M
    for i, b in enumerate(spec.get("buttons", [])):
        primary = b.get("primary", i == 0)
        label = b["label"] + ("  ↗" if b.get("url") else "")
        bw = font("Geist", 500, 26).getlength(label) + 72
        s.rect(x, y, bw, 72, C["lime"] if primary else "#FFFFFF1F", 36, stroke=None if primary else "#FFFFFF33", link=b.get("url"))
        s.text(x + 36, y + 20, bw - 60, label, weight=500, size=26, color=C["ink"] if primary else C["white"], lh=1.2, typo=False, link=b.get("url"))
        x += bw + 20


LAYOUTS = {k[7:].replace("_", "-"): v for k, v in globals().items() if k.startswith("layout_")}


def build(deck):
    ctx = Ctx(deck)
    slides = []
    for i, spec in enumerate(deck["slides"], 1):
        s = Slide(i, ctx.total)
        name = spec.get("layout")
        if name not in LAYOUTS:
            raise SystemExit(f"slide {i}: unknown layout {name!r}; choose from {sorted(LAYOUTS)}")
        LAYOUTS[name](spec, ctx, s)
        s.notes = spec.get("notes", "")
        s.name = spec.get("name") or f"{i:02d} — {spec.get('title', name)}".replace("\n", " ")[:80]
        if s.accents > 1:
            s.warnings.append(f"slide {i}: {s.accents} accent plates; Meadow slides carry at most one")
        slides.append(s)
    return ctx, slides


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
        base = (14, 16, 19)
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
                for i, line in enumerate(pr["text"].split("\n")):
                    para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                    para.alignment = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}[pr["align"]]
                    para.line_spacing = Pt(pr["size"] * pr["lh"] / 2)
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


def render_png(slides, outdir, scale=0.5):
    """Draw the computed layout with Pillow. Approximates text metrics (no tracking),
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
                for line in wrap(pr["text"], font(pr["family"], pr["weight"], pr["size"]), p.w):
                    lw_ = f.getlength(line)
                    x = p.x * scale + {"left": 0, "center": (p.w * scale - lw_) / 2, "right": p.w * scale - lw_}[pr["align"]]
                    d.text((x, y + (lh - pr["size"] * scale) / 2), line, font=f, fill=_rgba(pr["color"]))
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
