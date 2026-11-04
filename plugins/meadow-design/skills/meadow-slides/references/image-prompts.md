# Image prompts for Meadow decks

A prompt = **style prefix** + **scene** + **composition for the slot**. The prefix keeps a
series coherent, so reuse it verbatim. Write the scene about the slide's idea, not
generic "technology". Always end with the "no text, no logos" clause: generated lettering is
garbage and logos are a legal problem.

If an image tool is connected (Magnific MCP: `images_generate`, 4 variants per prompt works
well), offer to run it. Otherwise give the user the prompts as a list: slot, aspect, prompt.
Save results next to the deck and reference them by path in the spec.

## Style prefixes

**A. 3D studio (default for illustrations, covers, process scenes)**
> Premium cinematic 3D render, matte black studio (#0E1013), volumetric darkness, glossy
> dark-glass panels, soft key light, one acid-lime (#D3FF31) neon light trail plus a cool-blue
> secondary glow, shallow depth of field, photoreal, ultra detailed, no text, no logos, no
> readable UI copy.

**B. Abstract wave (covers, section breaks)**
> Abstract premium background, flowing glossy silk ribbons in deep electric blue and acid lime
> (#D3FF31) on a pure black background, soft studio lighting, elegant motion, high-end tech
> brand aesthetic, ultra detailed, no text, no logos.

**C. Night meadow (closing, contacts, "growth" metaphors)**
> Ultra-photorealistic night meadow under a deep blue-black sky, soft moonlight, wild grass with
> small glowing acid-lime (#D3FF31) and cobalt-blue flowers in the foreground, gentle rolling
> hills, low mist, calm cinematic mood, high dynamic range, no people, no text, no logos.

**D. Lifestyle editorial (people, creators, contacts)**
> Premium 2026 lifestyle editorial photograph, a confident model wearing an acid-lime (or
> soft cobalt-blue) outfit, white minimalist Mediterranean architecture, natural golden daylight,
> shot on 85mm, shallow depth of field, authentic and warm, magazine quality, no text, no logos,
> no brand marks on clothing.

**E. UGC creator (content-factory, creator decks)**
> Authentic vertical smartphone video still, an everyday creator filming selfie-style at home /
> street / gym, warm natural light, candid expression, diverse people, plain unbranded products,
> real-life UGC look, no text overlays, no logos.

## Composition by slot

| slot (layout) | aspect / size | composition note to append |
|---|---|---|
| cover | 16:9, 2752×1536 | Keep the left 55% dark and empty for the headline; subject in the right half; dark floor at the bottom for stats. |
| section | 16:9 | Calm, low detail on the left two thirds; one focal element on the right. |
| contacts | 1:1 or 4:5 portrait | Subject in the right half facing slightly left, dark or deep-blue background that can fade to black on the left edge. |
| image-text | 1:1, 2048×2048 | Single clear subject, centred, uncluttered background. |
| card image | 16:9 or 4:3 | Simple, readable at 400px; one object, strong silhouette. |
| LinkedIn square | 1:1, 2160×2160 | Upper 40% dark and empty for the logo and one line. |

## Proven scenes (reuse or adapt)

- **Content factory (the content-factory deck cover)**, prefix A: "A sleek futuristic content factory
  floor seen from a low three-quarter angle: a long glossy black conveyor belt with robotic
  arms and dark-glass inspection gates, carrying a steady stream of vertical 9:16 phone screens
  standing upright like products on an assembly line. Each screen shows a different everyday
  creator filming selfie-style, warm natural daylight, authentic UGC look. At a scanning gate a
  lime laser beam passes over the screens; the ones that pass glow with lime rims. Clean,
  premium, not grimy industrial."
- **Brief → route**, prefix A: "A single lime light trail enters from the lower left, passes
  through a floating dark-glass brief document and runs deep into the space toward five faint
  glowing stations in the distance."
- **AI planning**, prefix A: "The lime trail hits a faceted AI core / prism that splits it into
  several parallel structured lines forming a plan grid across a dark-glass board."
- **Discovery & outreach**, prefix A: "The lime trail runs through a field of floating dark-glass
  creator cards with softly blurred portraits; three cards light up lime, and two streams of light
  meet in a handshake above a glowing message bubble."
- **Content & monitoring**, prefix A: "The lime trail feeds a compact camera rig on a dark-glass
  stage with three vertical video frames, then turns into a live glowing monitoring wave with
  small lime and blue data peaks."
- **Results loop**, prefix A: "A results wave curves back into a glowing dark-glass data vault,
  which sends a brighter trail back toward the start of the route: a calm infinite loop."
- **AI avatar / virtual creator**, prefix A: "Three floating vertical smartphones, each showing
  the same friendly host in a different short video; a faint lime wireframe shimmer along the
  edge of his silhouette hints he is digital." Describe the persona once and repeat it word for
  word in every prompt of the series, or the face drifts.
- **Creator at work (contacts)**, prefix D: "a young man in a cobalt-blue blazer and white tee
  raising a vintage film camera to his eye, blue-tinted modern villa interior."

## Don'ts

- No text, numbers, UI copy, logos, or real brands in prompts. Put them on the slide as type.
- No real people's likeness by name.
- Don't mix prefixes inside one deck section. Two families per deck at most (e.g. B for
  structure + A for scenes).
- Large PNGs from generators are 5–7 MB: the script downsizes on build. For Figma, compress to
  JPEG first (`sips -s format jpeg -s formatOptions 85 -Z 2752 in.png --out out.jpg`).
