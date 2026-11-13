# 3D asset style guide (for agents)

Follow this guide when creating or editing any 3D asset for this game: buildings,
props, vehicles, terrain, foliage, characters. Treat every MUST as a hard
requirement. If a rule conflicts with a request, follow the request and report
the deviation.

## Target aesthetic

Early PS2 era, specifically the look of GTA San Andreas (2004): lo-poly,
grounded, soft and slightly faded. A real place seen through a 2004 open-world
game. NOT stylized, cartoonish, cel-shaded, cinematic, or "modern game imitating retro".

Core principle: **simplify reality, don't invent.** Every asset depicts a real
or realistic object with true proportions, reduced to few polygons and few colours.

## 1. Grounding

- MUST base proportions, dimensions and layout on real measurements, a reference
  photo, or documented facts about the subject. Never eyeball "plausible" sizes.
- MUST take colours from reference photos of the actual subject when one exists.
- When no reference exists, MAY fit from typical examples (era, type, region),
  but MUST say so in the asset's notes. A guess must never pass for research.
- Use real-world units (metres) and real scale.

## 2. Geometry

- Build a simplified outer shell. No interiors, no hidden geometry, no faces
  that can never be seen.
- Do NOT model detail smaller than ~0.6 m (window frames, mullions, railings,
  trim, bolts, grilles). Paint it into the texture instead.
- Triangle budget scales with prominence, not a fixed target:

  | Asset class                          | Triangles    |
  |--------------------------------------|--------------|
  | Small prop (bin, sign, hydrant)      | 12-150       |
  | Large prop / vehicle                 | 300-1,500    |
  | Infill / minor building              | 10-200       |
  | Typical building                     | 200-2,000    |
  | Skyline landmark (seen near and far) | 5,000-40,000 |
  | Character                            | 1,000-3,000  |

- Prefer flat faces and hard edges. Use few curve segments: 6-8 sides for
  round columns, poles and trunks; 8-12 for large curves.
- All faces MUST point outward. Enable backface culling. No double-sided faces
  unless the surface is genuinely visible from both sides.
- MUST be watertight from every normal viewpoint: no see-through gaps or slits.
- Use flat (per-face) shading, not smooth normals, except on organic forms
  (characters, foliage, terrain).

## 3. Lighting (baked, never dynamic)

- MUST NOT rely on real-time lights. Bake shading into a vertex-colour layer
  and multiply it onto the texture.
- Use ONE fixed, low sun, identical for every asset in the game. Brightness by
  face normal:
  - Up-facing (n.z > 0.7): 1.0
  - Down-facing (n.z < -0.7): 0.6
  - Walls: 0.76-1.0, brightest toward the sun, dimmer on the shadow side.
- Darken toward the ground: ×0.84 at ground level, rising to ×1.0 at 2.5 m height.
- Final vertex brightness = sun × ground term, clamped to [0, 1].
- Keep contrast mild and shadows soft. Never dramatic lighting.

## 4. Textures

- Small, power-of-two sizes. Typical: 512×512 for a full facade, 64×128 for a
  tileable bay/panel, 32-64 px for plain surfaces, 128-256 for props.
- Texel density: ~8-12 px/m on plain surfaces, ~16-20 px/m on detailed ones
  (carved stone, ornament). Choose deliberately per texture.
- MUST palette-quantize to 32-48 colours (16-64 allowed) with **NO dithering**.
  Flat colour banding is the strongest single marker of the era.
- MUST look slightly soft: paint at 4× resolution, then box-filter down. No
  crisp aliased edges, no sharpening.
- MUST be RGB with **no alpha**. Fake transparency (glass, foliage gaps, fences)
  with dark or tinted opaque colour.
- Tile textures cleanly on the real grid (bays, floors, panels). Never stretch
  them, and never cut a window in half at a corner.
- Weathering: small correlated brightness shifts with a faint warm/cool tint.
  NEVER independent per-pixel RGB noise ("confetti").
- Masonry: real block structure with varied course heights, lighter top/left
  edges, darker bottom/right edges, and mortar mixed toward near-black (not flat grey).
- Windows, painted in this order: frame/sill, then dark glass, then a pale sky
  glint on the upper part, then a dark mullion line. Light ~10% of panes in a muted
  warm tone around RGB (138,122,92). NEVER bright orange or yellow.
- Give each distinct ornament (cornice, band, door, sign, clock) its own small
  texture, detailed only enough to read at final resolution.
- **Typography: MUST NOT use or consider pixel/bitmap/Minecraft-style fonts for
  non-digital lettering.** This includes the shared 5×7 `Canvas.led_text` /
  `led_text_c` helper (legacy names `text` / `text_c`): it is not a general-purpose
  signage font. Use a real, era-appropriate serif, sans-serif, script, or
  sign-painter typeface for physical signs, posters, labels, printed numbers,
  painted lettering, and mechanical reel symbols. The shared `Canvas.type` does
  this (see `documentation/technical/lib.md`).
- Pixel/bitmap fonts are allowed **only for genuinely digital circumstances**
  where the depicted hardware or reference warrants them (for example, a dot-matrix
  display or an electronic scoreboard). Low texture resolution, a retro game
  aesthetic, convenience, or the presence of a machine does not qualify.
- Rasterize ordinary type smoothly at the working resolution, then apply the same
  soft downsampling and palette quantization as the rest of the texture. Do not
  manufacture chunky glyphs or deliberate stair-step edges to suggest age.
- Do NOT use normal maps, specular/roughness maps, PBR texture sets, photo
  textures pasted raw, or high-resolution detail.

## 5. Materials

- One shader for everything: texture × baked vertex colour, then a basic surface shader.
- Matte by default: roughness 1.0, specular 0.
- Glass only: roughness ~0.45, specular ~0.2-0.25.
- Metal only: metallic 1.0. Everything else: metallic 0.
- Classify every material as exactly one of: `concrete` (incl. stone, brick,
  plaster), `glass`, `metal`, `wood`.
- No reflections, emission, subsurface, or screen-space effects.

## 6. Colour

- Naturalistic and muted. Nothing neon or fully saturated.
- Overall feel: slightly washed-out daylight.
- Reference palette (Toronto): red, buff and yellow brick; grey and pale precast
  concrete; beige/grey-brown sandstone; blue-tinted glass; white modern
  cladding; dark asphalt; dull green foliage.
- Keep sunlit and shaded versions of a material consistent with the single sun.

## 7. Preview / review renders

Use the same rig for every asset so assets compare side by side:
- Soft, low-energy sun with a wide angle (soft shadows), flat pale-blue sky background.
- 32 mm lens, 900×600.
- Views: 4 cardinal eye-level shots (camera at ~45% of asset height, distance
  max(18 m, 1.25 × bounding diagonal)) plus one 3/4 aerial; add a steeper top
  shot for anything over ~35 m tall.
- Documentary and even. No glamour lighting, depth of field, bloom or post effects.

## 8. Self-check before finishing

- [ ] Proportions and colours trace to a reference, or are explicitly marked as fitted.
- [ ] Triangle count is within budget for the asset class, and reported.
- [ ] No sub-0.6 m modelled detail; small detail is painted.
- [ ] No interior or invisible faces; all faces outward; no see-through gaps.
- [ ] Shading is baked into vertex colour with the shared sun; no dynamic lights.
- [ ] Textures: power-of-two, RGB, no alpha, 32-48 colours, no dither, soft edges.
- [ ] No stretched or misaligned UVs; tiles land on the real grid.
- [ ] Physical lettering uses appropriate real typefaces; any bitmap font is
  restricted to a justified actual digital display, not general signage.
- [ ] Materials matte except glass/metal; each classified into one of the four classes.
- [ ] Lit windows muted, not orange; nothing neon.
- [ ] Previews rendered with the standard rig and visually reviewed.
- [ ] Deviations, guesses and judgement calls reported.

## Anti-patterns (reject on sight)

High-poly or subdivided meshes; smooth-shaded hard-surface objects; PBR or
normal-mapped surfaces; glossy or reflective materials; real-time or
dramatic lighting; dithered or noisy textures; alpha transparency;
oversaturated or neon colour; invented dimensions; modern "retro filter" looks
(pixel art, CRT effects, deliberate jaggies).
