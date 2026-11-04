---
name: meadow-slides
description: Build presentation decks in the Meadow brand design system (black canvas, acid-lime #D3FF31 plate, Geist/Syne type, 1920×1080 grid) as PowerPoint .pptx, and optionally as editable Figma frames, plus image-generation prompts for the deck's backgrounds and illustrations. Use this whenever someone at Meadow asks for slides, a deck, a pitch, a commercial offer (КП), a case study, a one-pager in slide form, a client presentation, or wants an existing deck re-laid out "in Meadow style" — in Russian or English, even if they don't say "skill", "PPTX" or "design system". Also use it when they need prompts for deck imagery (cover art, backgrounds, people shots) in the Meadow look.
---

# Meadow slides

Decks in the Meadow look, built from a small JSON spec by a script, so every slide lands on the
same grid, type scale and colours as Meadow's own sales decks. You write the content
and pick layouts; the script does the pixel work and warns when copy doesn't fit.

```
scripts/meadow_deck.py   spec.json -> .pptx (+ --figma-json layout for Figma)
scripts/preview.py       .pptx -> PNG per slide + contact sheet (LibreOffice or Keynote)
scripts/figma_render.js  draws one slide of the layout dump through use_figma
scripts/install_fonts.sh installs Geist / Geist Mono / Syne for the current user
references/layouts.md    every layout, its fields, and when to use it   <- read before writing a spec
references/design-system.md  tokens and rules behind the layouts       <- read when going off-layout
references/image-prompts.md  prompt library for deck imagery           <- read when the deck needs new images
references/figma.md      Figma output recipe and its gotchas            <- read only if Figma is wanted
examples/sample-deck.json      a six-slide deck covering the main layouts (fictional data)
```

## Workflow

1. **Get the content first.** Ask for (or extract from the brief / old deck / doc) the
   message of each slide. If the user hands you a source deck to re-lay out, keep its copy
   word for word: change only what they asked to change, and offer cuts or new headlines as
   a separate suggestion. People notice when their text was silently rewritten.
2. **Outline.** One idea per slide. Map each slide to a layout from `references/layouts.md`
   (cover → content slides → contacts is the usual arc). Show the outline to the user when
   the deck is longer than ~6 slides or the brief is vague; otherwise go straight to building.
3. **Check the numbers.** Commercial decks live on budgets, CPM/CPV, views. Recompute
   derived figures (CPM = budget / views × 1000, totals, percentages) before typesetting. If
   they don't add up, still typeset what the user gave, and tell them which numbers disagree
   and by how much. A client will do the same arithmetic.
4. **Write the spec** (`deck.json`), see the example and `references/layouts.md`. Images
   are bundled short names (`wave-05`, `meadow-night-02`, `people-02-camera-blue`) or paths.
5. **Build:** `python3 scripts/meadow_deck.py deck.json -o deck.pptx`.
   Treat every `WARN` as a bug: shorten copy, split the slide, or switch layout, then rebuild.
   `WARN` lines cover overflowing text, Cyrillic set in Syne (no Cyrillic glyphs), and more than one
   accent plate on a slide.
6. **Look at it.** Fastest, and works everywhere: add `--png preview/` to the build. It draws
   the same layout with Pillow (exact geometry, approximate text). For a real office render, run
   `python3 scripts/preview.py deck.pptx` (LibreOffice, or Keynote on macOS). Open
   `contact-sheet.png` and the single slides. Check alignment, crowding, contrast over
   photos, empty half-cards, and collisions with the footer. Office renders need the fonts
   installed (`scripts/install_fonts.sh`).
7. **Deliver** the .pptx. Mention that recipients need the fonts (`assets/fonts`, all free
   under the OFL) or should use the `--portable` build (see below).
8. **Figma (optional)** when asked: follow `references/figma.md`.
   Don't write to someone's Figma file unless they asked for it.

## Rules that make it look like Meadow

These are the rules people check first. The layouts already apply them, so they matter
mostly when you write copy or bend a layout.

- **Dark canvas, one lime plate.** Background #0E1013, cards #1A1D21, inner rows #23262B.
  Lime #D3FF31 marks the *one* thing the slide is about (the offer, the result, the key
  callout). Two lime plates on a slide flatten the hierarchy. Don't paint a random card lime
  just to have an accent: a slide can have none. Text on lime is near-black, never white.
- **Fonts.** Syne has no Cyrillic, so in Russian decks headings and body are set in **Geist**,
  labels in **Geist Mono** caps, and only standalone numbers/KPIs in **Syne** (from ~36px). In
  English decks headings switch to Syne automatically. The script picks this from `lang`
  (auto-detected).
- **Grid.** 96px margins, header (mono eyebrow + 64px title) on top, content between y=264
  and y=944, footer = logo + `NN / NN`. Gaps 24, card radius 24, padding 40.
- **Say it with surfaces, not strokes.** Cards are separated by fill, not outlines. The only
  outlined element is a category chip (1px white 18%).
- **No competitor names** in copy. Client logos/testimonials only if the user supplied them.
- **Typography:** the script glues short prepositions/conjunctions and dashes with NBSP so
  lines don't end on «в», «и», «—». Write numbers as `10 000+`, `$5 000`, `1,5 млн` in
  Russian decks.
- **Charts** are solid dark bars on lime or lime on dark, zero baseline, heights
  proportional to the data. A semi-transparent black on lime turns muddy, so don't use one.

## Images

Bundled: 6 abstract blue/lime waves (`wave-01…06`), 3 night meadows (`meadow-night-01…03`),
4 lifestyle people shots (`people-…`), and white platform glyphs (`instagram`, `tiktok`,
`youtube`, `vk`, `telegram`, `x`, `linkedin`, `twitch`). Waves suit covers and section
breaks, meadows suit contacts and closing slides, people shots suit contacts and image-text
slides.

When the deck needs something new (a themed cover like the content-factory floor, a scene for
a case), write prompts from `references/image-prompts.md`: house-style prefix + scene +
composition note for the slot it fills. If an image-generation tool is connected (e.g. the
Magnific MCP `images_generate`), offer to generate; otherwise hand the prompts over and wire
the returned files into the spec by path.

## Output variants

- `--portable`: maps every weight to Regular/Bold of the same family. Use it for Google
  Slides import or for recipients who can't install fonts. Hierarchy survives, nuance doesn't.
- `--figma-json layout.json`: dumps the computed layout for the Figma renderer.
- Speaker notes: add `"notes"` to any slide. They go to `deck-notes.md` next to the PPTX,
  because Keynote refuses to open a PPTX that has notes slides written by python-pptx.
  `--embed-notes` puts them inside, for decks that will only be opened in PowerPoint.
- **PDF**: add `--pdf deck.pdf` (full 1920×1080 render of every slide, text not selectable).
  Use it when someone asks for a PDF to send or read; no Keynote or LibreOffice needed.

## When the layouts don't fit

Prefer splitting content across two slides over squeezing it. If a slide truly needs a new
arrangement, add a `layout_<name>` function to `scripts/meadow_deck.py` built from the same
helpers (`header`, `card`, `grid`, `bullets`, `kpi_tile`, `footer`) and tokens, so it inherits
the system. Read `references/design-system.md` before doing that.
