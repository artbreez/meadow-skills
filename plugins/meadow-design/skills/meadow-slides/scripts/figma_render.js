// Meadow deck -> Figma. Paste into a use_figma call AFTER defining two constants:
//
//   const SLIDE = <one entry of layout.json "slides">;   // from meadow_deck.py --figma-json
//   const AT = { x: 0, y: 0, pageId: null };             // where to put the 1920x1080 frame
//
// Draws one slide per call (keeps the payload small). Images become grey placeholder
// rectangles named "IMG <file>"; fill them afterwards with upload_assets (see references/figma.md).
// Returns { frameId, images: [{ nodeId, file }] }.

const STYLE = { 400: "Regular", 500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold" };

function paint(hex) {
  const h = hex.replace("#", "");
  const c = { r: parseInt(h.slice(0, 2), 16) / 255, g: parseInt(h.slice(2, 4), 16) / 255, b: parseInt(h.slice(4, 6), 16) / 255 };
  const opacity = h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1;
  return { type: "SOLID", color: c, opacity };
}

const page = AT.pageId ? await figma.getNodeByIdAsync(AT.pageId) : figma.currentPage;
if (AT.pageId) await figma.setCurrentPageAsync(page);

const fonts = new Set();
for (const it of SLIDE.items) if (it.kind === "text") fonts.add(it.family + "|" + STYLE[it.weight]);
for (const f of fonts) {
  const [family, style] = f.split("|");
  await figma.loadFontAsync({ family, style });
}

const frame = figma.createFrame();
frame.name = SLIDE.name;
frame.resize(1920, 1080);
frame.x = AT.x; frame.y = AT.y;
frame.fills = [paint(SLIDE.bg)];
frame.clipsContent = true;
page.appendChild(frame);

const images = [];
for (const it of SLIDE.items) {
  let n;
  if (it.kind === "rect" || it.kind === "image") {
    n = figma.createRectangle();
    n.resize(Math.max(1, it.w), Math.max(1, it.h));
    n.cornerRadius = it.radius || 0;
    if (it.kind === "rect") {
      n.fills = [paint(it.fill)];
      if (it.stroke) { n.strokes = [paint(it.stroke)]; n.strokeWeight = 1; n.strokeAlign = "INSIDE"; }
    } else {
      n.fills = [paint("#2A2E35")];
      n.name = "IMG " + it.file.split("/").pop();
      images.push({ nodeId: n.id, file: it.file, fit: it.fit || "cover" });
    }
  } else if (it.kind === "ellipse") {
    n = figma.createEllipse();
    n.resize(it.w, it.h);
    n.fills = [paint(it.fill)];
  } else if (it.kind === "text") {
    n = figma.createText();
    n.fontName = { family: it.family, style: STYLE[it.weight] };
    n.fontSize = it.size;
    n.lineHeight = { value: it.size * it.lh, unit: "PIXELS" };
    if (it.tracking) n.letterSpacing = { value: it.tracking * 100, unit: "PERCENT" };
    n.characters = it.text;
    n.fills = [paint(it.color)];
    n.textAlignHorizontal = { left: "LEFT", center: "CENTER", right: "RIGHT" }[it.align || "left"];
    n.textAutoResize = "HEIGHT";
    n.resize(Math.max(1, it.w + 4), n.height);
    if (it.link) n.hyperlink = { type: "URL", value: it.link };
  }
  if (!n) continue;
  if (it.name && it.kind !== "image") n.name = it.name;
  n.x = it.x; n.y = it.y;
  frame.appendChild(n);
}
return { frameId: frame.id, images };
