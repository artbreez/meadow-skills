# Figma output (optional)

Use this when the user wants editable Figma frames, either in addition to the PPTX or
instead of it. It needs the Figma MCP (`use_figma`, `upload_assets`). Load the `figma-use`
skill before the first `use_figma` call.

Only write into a Figma file the user named for this. Ask for the file and page if they
didn't say. Never move or overwrite existing frames; place the new slides in empty canvas
space, to the right of or below what's there.

## Recipe

1. Build the layout once: `python3 scripts/meadow_deck.py deck.json -o deck.pptx --figma-json layout.json`.
   This also writes `figma-images/` next to `layout.json`, with every image already cropped to
   its box and the scrim baked in.
2. `create_session` for the target file, then find free canvas space (`get_metadata` on the page,
   take max x + width + 200).
3. For each slide `i` (one `use_figma` call per slide keeps payloads small): send the contents of
   `scripts/figma_render.js`, prefixed with
   ```js
   const SLIDE = /* layout.json .slides[i] */;
   const AT = { x: X0 + (i % 3) * 2040, y: Y0 + Math.floor(i / 3) * 1200, pageId: "<page id>" };
   ```
   This is the reference deck's arrangement: 3 per row, 120px apart. The call returns the frame id and
   the image placeholders `{nodeId, file}`.
4. Images: `upload_assets` each `file` with its `nodeId`. **Then check the node's fills.** The
   upload returns an `imageHash` but often doesn't apply it. If the fill isn't an IMAGE paint, set
   it with `use_figma`: `node.fills = [{ type: 'IMAGE', imageHash, scaleMode: 'FILL' }]`
   (`'FIT'` for logos and glyphs).
5. Screenshot each frame (`get_screenshot`) and compare it with the PPTX preview.

## Gotchas

- Fonts: Geist, Geist Mono and Syne are Google Fonts, so they load in any Figma file. Styles are
  `Regular / Medium / SemiBold / Bold / ExtraBold`.
- `figma.createAutoLayout()` wrappers come with a white fill: set `fills = []`.
- Cyrillic in Syne renders with a fallback font. The script already warns about it; don't
  override it in Figma.
- Flipped icons (an icon cut in half) are mirrored nodes: fix `relativeTransform`, not
  rotation.
- If something "disappears" after plugin edits in the desktop app, it's usually the
  canvas raster cache. Verify with `get_screenshot` before "fixing" it, and suggest a Figma restart.
- Figma Slides files: rather than drawing, the user can import the generated .pptx
  (File → Import), which keeps text editable.
