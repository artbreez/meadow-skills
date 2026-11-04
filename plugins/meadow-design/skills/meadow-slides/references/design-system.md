# Meadow deck design system

Distilled from Meadow's own sales decks (1920×1080 frames), which follow the Meadow product
and landing system.
All values are Figma px on a 1920×1080 frame. In PPTX 1px = 0.5pt (the script converts).

## Colour

| token | hex | use |
|---|---|---|
| bg | #0E1013 | slide canvas, KPI tiles on lime |
| card | #1A1D21 | cards, blocks |
| row | #23262B | rows inside a card |
| lime | #D3FF31 | the one accent plate, eyebrows, numbers, bullets, logo |
| ink | #0E1013 | text on lime |
| ink2 | #3D4713 | secondary text / labels on lime |
| white | #FFFFFF | headings, primary text on dark |
| text2 | #C9CDD3 | body copy on dark |
| muted | #9AA1AB | captions, mono labels, note lines |
| dim | #6B7280 | page counter |
| blue | #4E5BCF | secondary plate, only when someone asks for blue: lime is the default accent |
| brand blue | #5282FF | product UI "interactive" colour; don't use it on slides |

Lime is for meaning, not decoration: one plate per slide at most, and none is fine. Lime text
on dark is for eyebrows, step numbers, KPI values and bullets.

## Type

| role | font | size / line height | notes |
|---|---|---|---|
| cover title | Syne ExtraBold (Latin) / Geist Bold (Cyrillic) | 160 / 1.0, −3% | ≤ 2 lines |
| section / contacts title | Syne Bold (Latin) / Geist SemiBold (Cyrillic) | 112–128 / 1.05, −3% | |
| slide title | Syne Bold (Latin) / Geist SemiBold (Cyrillic) | 64 / 1.1, −2% | y=124, ≤ 2 lines |
| eyebrow | Geist Mono Medium, caps | 20 / 1.2, +4% | lime, y=88 |
| card title | Geist SemiBold | 32 (28 when 4+ per row) / 1.25 | |
| body | Geist Regular | 26–28 / 1.4–1.45 | text2 on dark |
| row / step text | Geist Medium | 28 / 1.2–1.3 | |
| note | Geist Regular | 22 / 1.4 | muted |
| mono label | Geist Mono Medium, caps | 16–18 / 1.2, +4% | muted / ink2 |
| KPI value | Syne Bold | 40–64 (hero 120) / 1.0 | lime on dark, ink on lime |
| page counter | Geist Mono Medium | 20 | `02 / 16`, dim |

Syne has **no Cyrillic glyphs**: in Figma they fall back to a stand-in grotesque, in a browser to
system fonts. Russian text is always Geist. Headings pick their font from their own text:
Latin-only → Syne, even in a Russian deck; any Cyrillic → Geist. Syne digits inside a Russian sentence look foreign
(0 and 1 read like «o» and «l»), so Syne is used only for standalone numbers from ~36px.

## Grid

- Canvas 1920×1080, margins 96 left/right.
- Header: eyebrow y=88, title y=124. Content starts at y=264, or 56px under a two-line title.
- Content area ends at y=944. Footer: logo 144px wide at (96, 990), counter right-aligned to 1824.
- Gaps 24 between cards, 12 between rows, 16 between tiles on a plate.
- Radii: card 24, row 16, tile 20, plate 24–32, pills fully round.
- Card padding 40, plate padding 24 (tiles) or 40 (content).

## Components

- **Card**: card fill, no stroke. Optional mono number in lime, title, body, rows, bullets, note.
- **Numbered row**: row fill, mono `01` in lime, Geist Medium text.
- **Bullet**: 10px dot (lime on dark, ink on lime) + text.
- **Lime plate**: the hero block (offer, result, callout). On it: dark KPI tiles (bg fill)
  with lime Syne values, and solid dark bars for charts.
- **Chip** (cover): lime pill, Geist Mono caps, ink text. **Category chip**: outlined, 1px white
  18%, no fill, text muted. That's the one place a stroke is right.
- **Buttons** (contacts): lime pill (primary) or white 12% glass pill with a 20% hairline.
- **Platform glyphs**: white simple-icons glyphs next to a count or a handle, 22–28px.
- **Logo**: `assets/logo/meadow-logo.svg` (one path, #D3FF31), 280px on cover/contacts, 144 in
  the footer. Black version for light plates. App mark: `meadow-mark.svg`.

## Imagery

- Abstract waves (blue + lime silk on black) for covers and section breaks.
- Night meadows with lime and blue flowers for closings and contacts.
- Lifestyle: models in lime or blue clothing, white Mediterranean architecture, daylight,
  for people-centric slides.
- Thematic 3D renders in the house style (matte black studio, dark glass, one lime light
  trail + cool-blue glow), e.g. the content-factory floor on the cover.
- Behind copy, always darken: the scrim is baked into the image by the script.

## Copy

- Re-layouts keep the source text verbatim. Propose cuts separately.
- No competitor or rival-tool names. The user's own clients and partners are fine when supplied.
- Russian: NBSP after short words and before dashes (the script does it), `10 000+`, `$5 000`,
  decimal comma `1,5`. English: `10,000+`, `$5,000`, `1.5M`.
- Recheck derived numbers (CPM, CPV, totals) and flag mismatches to the user.
