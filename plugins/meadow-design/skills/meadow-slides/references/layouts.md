# Layouts and the deck spec

A deck is one JSON file:

```json
{
  "title": "Creator campaign",       // file metadata
  "lang": "en",                      // optional; auto: any Cyrillic -> ru
  "theme": "dark",                   // "dark" (default) or "light"; any slide can override it
  "footer": true,                    // logo + page counter on content slides
  "flowers": true,                   // optional; default: on for light-theme slides only
  "flowers_seed": 7,                 // optional; another number = another arrangement
  "slides": [ { "layout": "cover", ... }, ... ]
}
```

Every slide accepts `"notes"` (speaker notes), `"name"` (layer/frame name), `"theme"`
(e.g. one dark appendix slide in a light deck) and `"flower": true / false` (force a flower
onto this slide, or keep it off).

**Light theme:** cover, section and contacts hold their `background` as a rounded 720px panel
on the right instead of full-bleed, so the copy column is narrower (the cover title shrinks
until its longest word fits). `"background": null` gives a clean white slide with no image.

**Flowers:** the brand accents from `assets/flowers/` (asterisk, 4-point star, blob outline,
petals, blob) drawn as native vectors. They are sprinkled sparingly: about one slide in three,
never two slides in a row, one per slide, 80–150px, slightly rotated, and only in clear space
(at least 40px from any text, card or image; no room = no flower). Two looks: solid (lime or
blue) and glass, a see-through tint with a border in the same colour (blue on light; white or lime
on dark). Outline shapes are always glass, filled ones about half the time. The arrangement is seeded from the
deck title, so a rebuild keeps it; change `flowers_seed` to reshuffle.

Text fields are plain strings; `\n` forces a line break. Image fields take a bundled short
name (`wave-05`) or a path. Icon lists take glyph names (`instagram`, `tiktok`, `youtube`, `vk`,
`telegram`, `x`, `linkedin`, `twitch`).

Copy budgets below are what fits at the designed size. Over budget, the script warns.

---

## cover
Full-bleed image, logo, optional lime chip, huge title, subtitle, up to 4 stats along the bottom.
```json
{"layout":"cover","background":"wave-05","scrim":"left",
 "chip":"UGC · vertical video","title":"Creator campaign",
 "subtitle":"A steady stream of short videos from real creators",
 "stats":[{"value":"10,000+","label":"creators to choose from"},
          {"value":"3","icons":["instagram","tiktok","youtube"],"label":"platforms"}]}
```
Title ≤ 2 short lines (`title_size` defaults to 160). Subtitle ≤ 2 lines. `scrim`: `left`
(default: dark behind the copy), `bottom`, `full`, or `null` for a dark image.

## section
Divider between parts of a long deck: image, eyebrow, 112px title, subtitle.
`{"layout":"section","background":"wave-02","eyebrow":"Part 2","title":"Case studies","subtitle":"…"}`

## statement
One big sentence (96px) + an optional paragraph. Use it for a thesis, a promise, a quote from the brief.
`{"layout":"statement","eyebrow":"Why now","title":"…","text":"…"}`

## text-cards
The two-column intro slide. Header, 1–2 text columns, then 1–3 cards side by side.
```json
{"layout":"text-cards","eyebrow":"The approach","title":"…",
 "columns":["Left paragraph","Right paragraph"],
 "cards":[{"title":"Why it works","rows":["Volume","Consistency"],"note":"…"},
          {"title":"Why Meadow","accent":"lime","bullets":["…","…"]}]}
```
Columns ≤ 4 lines each. Cards (all layouts) accept: `number`, `label`, `value` (Syne KPI),
`title`, `text`, `rows` (numbered dark rows), `bullets`, `note`, `image`, `accent` (`"lime"`,
or `"blue"` only when someone asks for blue).

## cards
Header, optional intro, a grid of 2–8 cards (columns auto: ≤4 in one row, 5/6/9 → 3 columns,
else 4; force with `columns_count`). Use it for formats, offers, features, team, numbered benefits.
`{"layout":"cards","eyebrow":"Formats","title":"…","intro":"…","cards":[{"number":"01","title":"…","text":"…"}]}`

## steps
The process slide. Numbered step cards (auto 4 per row) plus an optional callout plate:
```json
{"layout":"steps","eyebrow":"Process","title":"How it works",
 "steps":["Creator match from the brief", {"title":"Reporting","text":"weekly"}],
 "callout":{"value":"2","label":"videos to approve","title":"…","text":"…","accent":"lime"}}
```
Columns auto: 5 → one row of 5, 6 → 3+3, 7 → 4+3, 8 → 4+4. Override with `columns_count`.
Step titles ≤ 3 lines of ~22 characters at 4 per row. Up to 8 steps. With one- or two-word
titles the cards look empty: give each step a short `text`, built from the user's own brief
where possible, and tell them which lines you wrote.

## kpi
The offer/package slide. Lime plate with 3 big + up to 4 small dark KPI tiles, a note line, and an
optional strip of next steps under the plate.
```json
{"layout":"kpi","eyebrow":"Starter package","title":"Getting started",
 "tiles":[{"label":"Budget","value":"$5,000","caption":"per month"}, …],
 "note_left":"Video rights in perpetuity","note_right":"Larger packages available",
 "steps_title":"Ready to start?","steps_text":"Five steps to the first posts","steps":["Contract","Match", …]}
```
Values are set in Syne, so keep them to digits, `$`, `%`, `K`, `M`, `+`. Labels are Geist Mono caps.

## case
The case-study slide. Left: 2–3 dark blocks (text or a facts table). Right: lime result plate
with a big number, unit, caption + badge, a bar chart, and up to 3 KPI tiles.
```json
{"layout":"case","eyebrow":"Case 01 · Beauty","title":"…",
 "blocks":[{"label":"Goal","text":"…"},
           {"facts":[["Period","3 months"],["Budget","$5,000 per month"]]},
           {"label":"What we did","text":"…"}],
 "result":{"label":"Result in 3 months","value":"1.5","unit":"M","caption":"views",
           "badge":"+50% vs month 1",
           "bars":[{"label":"Month 1","value":400,"display":"400K"}, …],
           "tiles":[{"label":"CPM","value":"$10"},{"label":"Videos","value":"300"}]}}
```
Bars: 2–6, `value` numeric (heights are proportional), `display` is what's printed.

## table
Header + table; `highlight_column` turns one column into the lime plate (e.g. "Meadow" in a
package comparison). `widths` are relative.
`{"layout":"table","title":"…","columns":["","Start","Pro"],"rows":[["Creators","6","15"]],"highlight_column":2}`
Up to ~8 rows.

## quotes
1–3 testimonial cards: `{"layout":"quotes","title":"What clients say","quotes":[{"text":"…","author":"…","role":"…","logo":"path.png"}]}`
Only with quotes the user supplied.

## image-text
Image on one side (860px wide, rounded), header + text + bullets on the other.
`{"layout":"image-text","title":"…","text":"…","bullets":["…"],"image":"people-01-lime-dress","image_side":"right"}`

## logos
Header + a grid of client logos (paths to PNG/SVG-rasterised files, white or light versions on
the dark canvas, no tiles behind them). `columns_count` defaults to 6.

## contacts
Closing slide: a photo held on the right and fading into the canvas (or a wide image
full-bleed), logo, big title, subtitle, pill buttons with links. The first button is the lime one.
```json
{"layout":"contacts","background":"people-02-camera-blue","title":"Ready to launch?",
 "subtitle":"Write to us and we'll scope the task","buttons":[{"label":"Site · mymeadow.ai","url":"https://mymeadow.ai"},
 {"label":"Brief"}]}
```
Buttons without a `url` get no ↗ arrow.
Don't invent contact addresses: leave `url` out and tell the user which buttons need links.
