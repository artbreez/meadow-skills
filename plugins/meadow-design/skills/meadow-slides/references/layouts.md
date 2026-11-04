# Layouts and the deck spec

A deck is one JSON file:

```json
{
  "title": "Креаторская кампания",   // file metadata
  "lang": "ru",                      // optional; auto: any Cyrillic -> ru
  "footer": true,                    // logo + page counter on content slides
  "slides": [ { "layout": "cover", ... }, ... ]
}
```

Every slide accepts `"notes"` (speaker notes) and `"name"` (layer/frame name).
Text fields are plain strings; `\n` forces a line break. Image fields take a bundled short
name (`wave-05`) or a path. Icon lists take glyph names (`instagram`, `tiktok`, `youtube`, `vk`,
`telegram`, `x`, `linkedin`, `twitch`).

Copy budgets below are what fits at the designed size. Over budget, the script warns.

---

## cover
Full-bleed image, logo, optional lime chip, huge title, subtitle, up to 4 stats along the bottom.
```json
{"layout":"cover","background":"wave-05","scrim":"left",
 "chip":"UGC · вертикальные видео","title":"Креаторская кампания",
 "subtitle":"Поток коротких видео от реальных авторов",
 "stats":[{"value":"10 000+","label":"авторов в подборке"},
          {"value":"3","icons":["instagram","tiktok","youtube"],"label":"площадки"}]}
```
Title ≤ 2 short lines (`title_size` defaults to 160). Subtitle ≤ 2 lines. `scrim`: `left`
(default: dark behind the copy), `bottom`, `full`, or `null` for a dark image.

## section
Divider between parts of a long deck: image, eyebrow, 112px title, subtitle.
`{"layout":"section","background":"wave-02","eyebrow":"Часть 2","title":"Кейсы","subtitle":"…"}`

## statement
One big sentence (96px) + an optional paragraph. Use it for a thesis, a promise, a quote from the brief.
`{"layout":"statement","eyebrow":"Почему сейчас","title":"…","text":"…"}`

## text-cards
The two-column intro slide. Header, 1–2 text columns, then 1–3 cards side by side.
```json
{"layout":"text-cards","eyebrow":"Что такое контент-завод","title":"…",
 "columns":["Абзац слева","Абзац справа"],
 "cards":[{"title":"Почему это работает","rows":["Объём","Регулярность"],"note":"…"},
          {"title":"Почему Meadow","accent":"lime","bullets":["…","…"]}]}
```
Columns ≤ 4 lines each. Cards (all layouts) accept: `number`, `label`, `value` (Syne KPI),
`title`, `text`, `rows` (numbered dark rows), `bullets`, `note`, `image`, `accent` (`"lime"`,
or `"blue"` only when someone asks for blue).

## cards
Header, optional intro, a grid of 2–8 cards (columns auto: ≤4 in one row, 5/6/9 → 3 columns,
else 4; force with `columns_count`). Use it for formats, offers, features, team, numbered benefits.
`{"layout":"cards","eyebrow":"Форматы","title":"…","intro":"…","cards":[{"number":"01","title":"…","text":"…"}]}`

## steps
The process slide. Numbered step cards (auto 4 per row) plus an optional callout plate:
```json
{"layout":"steps","eyebrow":"Процесс","title":"Как это работает",
 "steps":["Подбор креаторов по брифу", {"title":"Отчётность","text":"еженедельно"}],
 "callout":{"value":"2","label":"ролика на согласование","title":"…","text":"…","accent":"lime"}}
```
Columns auto: 5 → one row of 5, 6 → 3+3, 7 → 4+3, 8 → 4+4. Override with `columns_count`.
Step titles ≤ 3 lines of ~22 characters at 4 per row. Up to 8 steps. With one- or two-word
titles the cards look empty: give each step a short `text`, built from the user's own brief
where possible, and tell them which lines you wrote.

## kpi
The offer/package slide. Lime plate with 3 big + up to 4 small dark KPI tiles, a note line, and an
optional strip of next steps under the plate.
```json
{"layout":"kpi","eyebrow":"Минимальный пакет","title":"Старт сотрудничества",
 "tiles":[{"label":"Бюджет","value":"$5 000","caption":"в месяц"}, …],
 "note_left":"Права на ролики — бессрочно","note_right":"Есть пакеты больше",
 "steps_title":"Готовы начать?","steps_text":"Пять шагов до публикаций","steps":["Договор","Подбор", …]}
```
Values are set in Syne, so keep them to digits, `$`, `%`, `K`, `M`, `+`. Labels are Geist Mono caps.

## case
The case-study slide. Left: 2–3 dark blocks (text or a facts table). Right: lime result plate
with a big number, unit, caption + badge, a bar chart, and up to 3 KPI tiles.
```json
{"layout":"case","eyebrow":"Кейс 01 · Beauty","title":"…",
 "blocks":[{"label":"Задача","text":"…"},
           {"facts":[["Период","3 месяца"],["Бюджет","$5 000 в месяц"]]},
           {"label":"Что сделали","text":"…"}],
 "result":{"label":"Результат за 3 месяца","value":"1,5","unit":"млн","caption":"просмотров",
           "badge":"+50% к первому месяцу",
           "bars":[{"label":"Месяц 1","value":400,"display":"400K"}, …],
           "tiles":[{"label":"CPM","value":"$10"},{"label":"Роликов","value":"450"}]}}
```
Bars: 2–6, `value` numeric (heights are proportional), `display` is what's printed.

## table
Header + table; `highlight_column` turns one column into the lime plate (e.g. "Meadow" in a
package comparison). `widths` are relative.
`{"layout":"table","title":"…","columns":["","Start","Pro"],"rows":[["Креаторы","6","15"]],"highlight_column":2}`
Up to ~8 rows.

## quotes
1–3 testimonial cards: `{"layout":"quotes","title":"Клиенты о нас","quotes":[{"text":"…","author":"…","role":"…","logo":"path.png"}]}`
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
{"layout":"contacts","background":"people-02-camera-blue","title":"Готовы запустить?",
 "subtitle":"Напишите нам — обсудим задачу","buttons":[{"label":"Сайт · mymeadow.ai","url":"https://mymeadow.ai"},
 {"label":"Бриф"}]}
```
Buttons without a `url` get no ↗ arrow.
Don't invent contact addresses: leave `url` out and tell the user which buttons need links.
