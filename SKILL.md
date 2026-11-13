---
name: ps2-graphics
description: Create or edit lo-poly 3D game assets (buildings, props, vehicles, foliage, characters, interior scenes) in Blender in the early-PS2 / GTA San Andreas (2004) look, with baked vertex lighting, small palette-quantized textures and real typefaces, using the shared _lib pipeline (build, texture, bake, preview, validate). Use for any request to model, texture, light, render previews of or validate an asset in this style, from a reference image or a description.
---

# PS2-era asset pipeline

Your job is to create 3D models with Blender, faithfully to the user's reference image or
description, following the rules below. Target look: early PS2, specifically GTA San Andreas
(2004). Lo-poly, grounded, soft and slightly faded. **Simplify reality, don't invent.**

Paths below are relative to this skill's directory (`SKILL.md`'s folder) unless they say "project".
The skill bundles:

| Folder | Contents | How it's used |
|--------|----------|---------------|
| `documentation/` | Style guide (+ look-reference images), `_lib` API, default project conventions | Read by you, from here |
| `scripts/` | The pipeline code (Python package for Blender) | **Copied into each project as `<project>/_lib/`**; asset scripts import it as `_lib` |
| `references/` | Subject reference material (photos, drawings, measurements) | Read by you when it covers the subject; may be empty |

## 1. Read before starting (mandatory)

1. `documentation/style-preferences/style.md` in full, and view the reference images in
   `documentation/style-preferences/images/`. Its MUSTs are hard requirements. If a rule conflicts with the
   user's request, follow the request and report the deviation.
2. `documentation/technical/lib.md` in full. It is the API for everything below.
3. The code in `scripts/` (`paint.py`, `shading.py`, `geometry.py`, `rig.py`, `checks.py`, `boot.py`).
4. Anything in `references/` that covers the subject you're building. It is grounding (real
   dimensions, colours, details), on the same footing as a reference image from the user.
5. The project's own conventions, if any (see section 3 for where to look). They win over the
   defaults here. The defaults (asset layout, `NOTES.md`, usage tracking) are spelled out in
   `documentation/project-preferences/project-structure.md`.

## 2. Project setup

- Asset scripts import the pipeline from a `_lib/` folder in the project root (they find it by
  walking up from their own directory), so the project carries its own copy of `_lib`:
  - **If `<project>/_lib/` already exists, use it as is.** Do not overwrite or update it unless the
    user asks; existing assets were built against that version.
  - **Otherwise copy this skill's `scripts/` into the project root as `_lib/`** (a copy, not a
    symlink, so the project stays self-contained and rebuilds the same way later), and record where
    it came from:
    ```sh
    rsync -a --exclude __pycache__ "<skill dir>/scripts/" "<project>/_lib/"
    git -C "<skill dir>" rev-parse --short HEAD > "<project>/_lib/VERSION" 2>/dev/null || date +%F > "<project>/_lib/VERSION"
    ```
  - To update a project's `_lib` later (only when asked), re-run the copy, then rebuild and
    re-validate every asset and report what changed.
- **Do not modify `_lib/` unless the user explicitly asks.** It is shared by every asset in the
  project. If you need something it lacks, write it in the asset's own scripts and tell the user
  what's missing.
- Blender 5.2+ (`/Applications/Blender.app/Contents/MacOS/Blender` on macOS). Its bundled Python
  has numpy, OpenImageIO, blf and imbuf.

## 3. Asset layout

**Where the asset goes.** Decide this before writing anything, in this order:

1. **The project defines it: follow the project.** Look in the project's agent/contributor
   instructions (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `CONTRIBUTING.md`, `README.md`), its docs
   folder (e.g. `docs/`, `_docs/`, a `project-structure.md`), and the layout of the assets it
   already has. Whatever it specifies (another root such as `assets/3d/`, extra levels such as a
   per-AI-model folder `models/<asset>/<ai_model>/`, naming rules) overrides the default below,
   and so do its rules for notes, usage files and commits.
2. **Otherwise, use the default:** one folder per asset, named after the asset in lowercase
   `snake_case`:
   - `models/<asset>/` for props, vehicles, buildings, foliage and characters, e.g. `models/cat/`;
   - `scenes/<scene>/` for interiors and multi-prop sets, e.g. `scenes/diner/`.
3. **Unclear or conflicting** (e.g. the instructions and the existing folders disagree): ask the
   user rather than guess.

If the folder already exists, you are editing that asset: work in it, don't create a sibling.
State the folder you chose (and why, if a project rule decided it) at the start of your work and
in `NOTES.md`.

Each asset folder holds exactly four scripts plus outputs:

| File | Role |
|------|------|
| `textures.py` | `TextureSet` painters and the `MaterialTable` (texture, class, UV mapping) |
| `build.py` | Geometry, collections, materials, bake, preview rig; the only script that writes `<asset>.blend` |
| `render_previews.py` | `EXTRA_CAMS`, `DEFAULT_CAM`, renders into `previews/` |
| `validate.py` | Triangle budgets + `checks.run(...)`; exits 1 on failure |
| `NOTES.md` | Grounding sources, guesses, deviations, triangle counts, judgement calls |

No helper modules or scratch scripts in the asset dir. Shared code lives in `_lib/`.
Start every script with the `boot` bootstrap from `lib.md`, and load siblings with
`boot.local(__file__, "textures")`, never a plain `import textures`.

## 4. Workflow

1. **Ground it.** Take proportions, dimensions and colours from the reference or documented facts,
   in metres. Where you must fit from typical examples, say so in `NOTES.md`. A guess must never
   pass for research.
2. **Plan the shell.** A simplified outer shell only. Nothing under ~0.6 m is modelled (paint it).
   Pick the asset class and its triangle budget (style.md §2).
3. **Textures** (`textures.py`). Small power-of-two canvases at a deliberate texel density. Use
   `Canvas.frame()` to paint in metres, `window()` and `masonry()` for architecture, shapes for
   everything else, and `Canvas.type()` for all lettering. Weather with `c.weather(...)`
   (correlated, never per-pixel noise). 32-48 colours (`TextureSet(colors=40)`).
4. **Geometry** (`build.py`). World-space metres. `MB.box`/`face`/`extrude`/`loft`/`tube`/`cylinder`,
   with `skip=` on faces that can never be seen. `smooth=True` only for organic forms. Never rotate
   or scale objects (the bake reads world-space mesh data); place parts with `mark()`/`transform()`.
5. **Build, validate, render** headless (`<dir>` is the asset folder chosen in section 3):
   ```sh
   B=/Applications/Blender.app/Contents/MacOS/Blender
   $B -b --factory-startup --python <dir>/build.py
   $B -b --factory-startup <dir>/<asset>.blend --python <dir>/validate.py
   $B -b --factory-startup <dir>/<asset>.blend --python <dir>/render_previews.py
   ```
   Blender exits 0 even when a `--python` script raises: grep the log for `Traceback`.
6. **Look at the previews** (read the PNGs) against the reference. Fix proportions, gaps, stretched
   or misaligned textures, and colour. Iterate until it matches and `validate.py` passes. Treat
   warnings as review items: fix them or justify them in `NOTES.md`.
7. **Finish.** Run style.md §8's self-check. Write `NOTES.md` with the triangle count, grounding,
   guesses and deviations. If the project tracks usage, write `usage.json` with
   `python3 _lib/usage.py <sessionID> <dir> --model <your model name> --input-rate … --output-rate … --cache-read-rate …`
   using officially looked-up rates (never invent prices). Commit per the project's convention; if
   it has none, only commit when the user asks.

### Using the live Blender MCP session

`build.py` calls `reset_scene()`, which **empties the open file**. Build headless (step 5) by
default. If you must run a script in the user's connected Blender, ask first, then use
`from _lib import boot; boot.run("/abs/path/build.py")` (it purges stale cached modules). Use the
MCP session for inspection, not destructive builds.

## 5. Hard rules (summary; style.md is authoritative)

- **Geometry:** outward faces, backface culling, watertight from normal viewpoints, flat shading
  on hard surfaces, 6-8 sides for poles/columns/trunks, no interiors or hidden faces, no
  subdivision.
- **Lighting:** never real-time. One shared sun baked into the `Bake` vertex colour layer
  (`_lib/shading.py`); never override it per asset.
- **Textures:** RGB, no alpha (fake transparency with dark or tinted opaque colour), no dithering,
  soft (painted at 4× then box-filtered), tiled on the real grid, never stretched. Lit windows use
  the muted `LIT` tone (138,122,92), never orange.
- **Materials:** one shader (texture × bake). Exactly one class each: `concrete`, `glass`,
  `metal`, `wood`. Matte except glass and metal. No emission, normal maps or PBR sets.
- **Colour:** naturalistic, muted, slightly washed-out daylight. Nothing neon or fully saturated.
- **Typography:** do not use or consider pixel/bitmap/Minecraft-style fonts for ordinary
  signage, labels, print, or painted lettering. Choose an appropriate real typeface
  (`Canvas.type`, `font=` one of `paint.FONTS` or a font path). Pixel/bitmap fonts
  (`Canvas.led_text`) are permitted only on genuinely digital displays whose hardware or
  reference calls for them. A low-resolution texture is not a digital display.
- **Previews:** the standard rig only (`rig.setup`): soft sun, pale-blue sky, 32 mm, 900×600, four
  cardinal shots plus a 3/4 aerial. Interiors use `rig.render(..., hide=)` cutaways.

Reject on sight: high-poly or subdivided meshes, smooth-shaded hard surfaces, PBR/normal maps,
glossy materials, dynamic or dramatic lighting, dithered/noisy textures, alpha, neon, invented
dimensions, and "retro filter" looks (pixel art, CRT effects, deliberate jaggies).
