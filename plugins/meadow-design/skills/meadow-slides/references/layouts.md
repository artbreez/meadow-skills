# Layouts and the deck spec

A deck is one JSON file:

```json
{
  "title": "Creator campaign",       // file metadata
  "lang": "en",                      // optional; auto: any Cyrillic -> ru
  "theme": "dark",                   // "dark" (default) or "light"; any slide can override it
  "footer": true,                    // logo + page counter on content slides
  "flowers": false,                  // optional; default: on (both themes), false turns them off
  "flowers_seed": 7,                 // optional; another number = another arrangement
  "slides": [ { "layout": "cover", ... }, ... ]
}
```

Every slide accepts `"notes"` (speaker notes), `"name"` (layer/frame name), `"theme"`
(e.g. one dark appendix slide in a light deck) and `"flower": true / false` (force a flower
onto this slide, or keep it off).

**Light theme:** cover and section default to `light-wave-01` (glass waves on white), contacts
to `light-flowers-01` (3D flowers on white); light pictures like these go full-bleed with no scrim
and the copy keeps to the left. A dark picture (`wave-05`, a photo) becomes a rounded 720px panel
on the right instead, with a narrower copy column (the cover title shrinks until its longest word
fits). `"background": null` gives a clean white slide with no image.

**Flowers:** the brand accents from `assets/flowers/` (asterisk, 4-point star, blob outline,
petals, blob) drawn as native vectors. They are sprinkled sparingly: about one slide in three,
never two slides in a row, one per slide, 80–150px, slightly rotated, and only in clear space
(at least 40px from any text, card or image; no room = no flower). Two looks: solid (lime or
blue) and outline, a border only with a fully transparent inside (blue on light; white or lime
on dark). Outline shapes always use it, filled ones about half the time. The arrangement is seeded from the
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

## Blue plates
Every hero plate can be blue instead of lime: `"accent": "blue"` on a card, on the steps
`callout`, on the `kpi` slide, on the `case` `result`, and on a `table` with `highlight_column`.
On blue the text is white, the badge and the marker turn lime. Still one plate per slide, lime
or blue: pick blue when the deck already leans blue (the light theme) or when two
neighbouring slides would both be lime.

## kpi
The offer/package slide. Lime (or `"accent": "blue"`) plate with 3 big + up to 4 small dark KPI tiles, a note line, and an
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

## Ruled layouts
Four airy layouts held together by thin rules instead of cards: an accent rule on top of a
block, an accent caps label, a big Syne value, grey copy. Built for the light theme, work on dark.
Each takes an optional `"subtitle"` under the title and a `"takeaway"` at the bottom: a string,
or `{"label":"Two strengths","title":"The one line to remember","text":"a grey line under it"}`,
drawn under an accent rule above the footer.

### team
2–4 people in columns. `photo` is a round crop on a lime disc: a cut-out PNG with transparency
shows the disc around the person, a plain photo is cropped round. Name in Syne, role as an accent
caps label, bio ~3 lines (over budget warns).
```json
{"layout":"team","title":"The people behind it",
 "people":[{"photo":"path/person.png","name":"…","role":"CEO","bio":"…"}, …],
 "takeaway":{"label":"Why us","title":"…"}}
```

### stats
3–5 big numbers in one band, each under its own accent rule, label underneath; the band floats in
the middle of the free space. Values shrink together until the widest fits its column.
```json
{"layout":"stats","eyebrow":"Track record","title":"…","subtitle":"…",
 "stats":[{"value":"8x","label":"Revenue growth in two years"}, …],
 "takeaway":{"title":"…","text":"…"}}
```

### chart
Bars on the left, a column of headline numbers on the right (`stats`, 2–4 rows between hairlines,
optional accent `note`). Bars: zero baseline, heights proportional; history is grey, bars with
`"accent": true` (forecast, the year that matters) are in the accent colour. Without `stats` the
chart takes the full width.
```json
{"layout":"chart","eyebrow":"Traction","title":"$340K to $1.9M in two years","chart_label":"Revenue",
 "bars":[{"label":"2025","value":340,"display":"$340K"},{"label":"2027","note":"forecast","value":1900,"display":"$1.9M","accent":true}],
 "stats":[{"label":"Average order","value":"$3K → $14K"},{"label":"Gross profit","value":"$0.4M → $0.9M","note":"Half of it from repeat clients"}],
 "takeaway":"Target: break even in 2027"}
```
Don't put ~400x apart values on one chart (the small bars vanish): split the story across two slides.

### highlight
A big blue block with the claim: eyebrow, 2–4 short lines in large type, one of them (`mark`,
0-based) on a lime marker, a source line; optional `stats` (2–3) and a takeaway under the block.
`"accent": "lime"` makes the block lime with an ink marker.
```json
{"layout":"highlight","eyebrow":"Why now","lines":["Short video takes","4 of every 10 ad dollars","in our segment"],
 "mark":1,"source":"Sample source, 2026",
 "stats":[{"value":"$90B → $310B","label":"Market today and in eight years"}],
 "takeaway":"The money has moved. The tools have not."}
```

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
