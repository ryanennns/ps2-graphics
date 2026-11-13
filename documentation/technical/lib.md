# `_lib`: shared asset pipeline

> **Where it lives.** The ps2-graphics skill ships this code in its `scripts/` folder. Each project
> gets its own copy at `<project>/_lib/` (see the skill's `SKILL.md`, "Project setup"), and asset
> scripts import it as the `_lib` package. Every `_lib/...` path and `from _lib import ...` below
> refers to that project copy.

`_lib/` (at the repo root) is the shared Python code that every model uses, whatever agent or model
family made it. It implements the mechanical parts of `documentation/style-preferences/style.md`, so every
asset gets the same sun, shader, texture processing, lettering, preview rig and self-check.

> **Agents must not modify anything in `_lib/` unless the user explicitly asks them to.**
> Treat it as read-only. If your model needs something `_lib` doesn't provide, write it in your
> model's own scripts (see `documentation/project-preferences/project-structure.md`). If you think `_lib`
> has a bug or a missing feature, say so to the user and don't change it yourself. Changing `_lib`
> changes every model in the repo, including other agents' models.

Everything runs inside Blender (5.2+) with its bundled Python (`numpy`, `OpenImageIO`, `blf` and
`imbuf` are included). The exception is `usage.py`, which is plain Python.

## Modules

| Module        | What it gives you                                                                                                                                                                                                                                                                                                         | Style rules it enforces                                                                                                                                                |
|---------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `boot.py`     | `init(__file__)` → `(HERE, REPO)` at any depth, `local(__file__, 'textures')` (fresh load by path), `run(path)` (run any asset script inside a live Blender), `purge()`                                                                                                                                                   | none (prevents a live Blender from handing one asset another asset's cached `textures` module)                                                                        |
| `paint.py`    | `Canvas`: `rect`, `rect_wrap`, `mul`, `polygon`, `ellipse`/`disc` (rings), `rrect`, `line` (polylines), `star`, `grad`, `gmul`, **`type`** (real typefaces), `window`, `masonry`, `weather`, `frame()` (metre-space view); `FONTS`, colour constants `LIT GLASS SKY FRAME DARK SILL`; `tile_noise`, `plain()`, `shade()`, `mix()`, `quantize()`, `save_png()`, `TextureSet` | §4: paint at 4× then box-filter, palette-quantize with no dither, RGB with no alpha, power-of-two sizes, correlated weathering, window paint order, masonry, real typefaces |
| `shading.py`  | The one shared sun (`SUN`, `SUN_ELEV`), `bake()`, `MaterialTable` with `W()` / `F` / `P()` UV mappings, `map_uv()`, `build_materials()`                                                                                                                                                                                    | §3: baked vertex light (up 1.0, down 0.6, walls 0.76–1.0, ground ×0.84→1.0 over 2.5 m). §5: texture × `Bake` → Principled; matte unless glass/metal; four classes only |
| `geometry.py` | `MB` mesh builder (`box`, `quad`, `prism`, **`face`**, `extrude`, `loft`, `tube`, `cylinder`, `mark`/`transform`/`mirror`, `poly`, `build`), `newell()`, `face_axes()`, `weld()`, `coll()`, `reset_scene()`, `place_origin()`, `report_tris()`, `save()`                                                                    | §2: flat shading (smooth and welded for organic forms), outward winding, per-face `skip` for hidden faces, world-space metres                                          |
| `rig.py`      | `setup(asset_root, extra_cams, default_cam)`, `render(names, out_dir, hide=)`, `contact_sheet(names, out_dir)`, `viewport_defaults(camera_view=)`                                                                                                                                                                          | §7: same sun/sky/32 mm/900×600 for everything, 4 cardinal + 3/4 aerial (+ top above 35 m)                                                                              |
| `checks.py`   | `run(asset_root, tex_dir=None, budgets, total_max)`, `rays(report, tests, objects)`, `exit_with(report, json_path=None)`, `BUDGETS`, `DENSITY`                                                                                                                                                                             | §8 self-check (see below)                                                                                                                                              |
| `view.py`     | Opens a `.blend` split into one Material Preview panel per camera                                                                                                                                                                                                                                                         | none (viewing helper)                                                                                                                                                  |
| `usage.py`    | Plain-Python CLI that writes `usage.json` from an OpenCode session and the official rates you looked up                                                                                                                                                                                                                    | project-structure.md "Usage tracking"                                                                                                                                  |

## How a model uses it

Each script gets `_lib` importable, then lets `boot` do the rest. `boot.find_repo` walks up to the
directory containing `_lib/`, so the same lines work in `models/<asset>/` (the default),
`scenes/<scene>/`, a deeper project-specific layout such as `models/<asset>/<ai_model>/`, or anywhere
else:

```python
import os, sys
_d = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_d, "_lib")):
    _d = os.path.dirname(_d)
sys.path.insert(0, _d)
from _lib import boot
HERE, REPO = boot.init(__file__)
```

Load sibling scripts with `boot.local`, not `import textures`. A live Blender (the MCP session)
caches modules by name, so a plain import in a second asset silently returns the first asset's
textures:

```python
textures = boot.local(__file__, "textures")
render_previews = boot.local(__file__, "render_previews")
```

To run an asset script inside a live Blender session (MCP `execute_blender_code`), use
`from _lib import boot; boot.run("/abs/path/models/<asset>/build.py")`. It purges stale
sibling modules first, which makes older scripts that still use plain imports safe too.

### `textures.py`: painters plus the material table

```python
from _lib.paint import Canvas, TextureSet, plain, shade, mix, LIT
from _lib.shading import MaterialTable, W, F, P

tex = TextureSet(colors=40)          # 32-48 colours per texture

@tex
def t_brick():                       # saved as textures/brick.png
    c = Canvas(64, 64, (150, 80, 60))   # final size; painting happens at 4x internally
    c.masonry(0, 0, 64, 64, (150, 80, 60), course=(5, 7), length=(14, 22), joint=0.8)
    c.weather(0.05, 6, seed=1)
    return c

@tex
def t_shopfront():
    c = Canvas(256, 128, (150, 82, 62))
    f = c.frame(0, 0, 8.0, 4.0)          # metres: this texture covers 8 m x 4 m of facade, z up
    f.masonry(0, 0, 8.0, 4.0, (150, 82, 62))
    f.window(0.6, 0.9, 2.0, 2.9)                 # frame/sill, dark glass, sky glint, mullion
    f.window(3.0, 0.9, 4.4, 2.9, lit=True)       # muted LIT tone (~10% of panes)
    f.rect(0, 3.3, 8.0, 3.9, (60, 64, 58))
    f.type("Hardware & Paint", 4.0, 3.45, 0.32, (226, 218, 196), font='serif_bold', align='c')
    return c

MAT = MaterialTable()
MAT.add('brick', 'brick', 'concrete', W(3.2, 3.2))   # world-tiled: 1 repeat per 3.2 x 3.2 m
MAT.add('sign', 'sign', 'metal', F)                  # fit to the face (per-face repeat optional)
MAT.add('side', 'side', 'metal', P((-2.1, -0.9, 0), (1, 0, 0), (0, 0, 1), 4.2, 1.9))  # atlas projection
```

**Shapes.** All `Canvas` coordinates are final pixels, x right, **y down**. Every shape takes
`alpha=`, and most take `wrap=True` to repeat horizontally across a tiling seam. `polygon(pts)`,
`ellipse(cx, cy, rx, ry, inner=)` (rings), `disc`, `rrect(…, r)`, `line(pts, width)` (polylines),
`star`, `grad(…, c0, c1, axis)`, `gmul(…, f0, f1, axis)`. `Canvas.frame(x0, z0, x1, z1, px=)`
returns a `Frame` with the same methods in **metres, z up**; `px=(px0, py0, px1, py1)` maps onto a
sub-rectangle for atlases.

**Lettering.** Use `Canvas.type(txt, x, y, cap, colour, font=, align=, valign=, track=, sx=, max_w=)`
for every physical sign, poster, label, number or painted letter. It sets a real typeface through
Blender's font engine at 4× and is then softened and quantized with the rest of the texture.
`cap` is the capital height. `font` is a `paint.FONTS` short name (`sans`, `sans_bold`, `cond`,
`din`, `humanist`, `geometric`, `serif`, `serif_bold`, `times`, `didone`, `slab`, `engraved`,
`script`, `black`, `unicode`) or a font file path. `max_w` condenses the type to fit, and
`type_width()` measures. Cyrillic and other scripts work with fonts that contain them. **Do not use
the 5×7 bitmap `Canvas.led_text` / `led_text_c`** (legacy names `text` / `text_c`) except for a
genuinely digital display (dot-matrix, LED, scoreboard) whose reference calls for it.

**Architecture.** `window(x0, y0, x1, y1, panes=, rows=, lit=, frame=, glass=, curtain=, fw=)` paints
in the §4 order. `masonry(x0, y0, x1, y1, colour, course=, length=, joint=, bond=)` gives varied
courses, lit top/left and dark bottom/right edges, and mortar mixed toward near-black. On a full
canvas it tiles seamlessly.

### `build.py`: geometry, then save

```python
import bpy
textures = boot.local(__file__, "textures")
render_previews = boot.local(__file__, "render_previews")
MAT, tex = textures.MAT, textures.tex
from _lib.geometry import MB, coll, reset_scene, report_tris, save
from _lib.shading import build_materials
from _lib import rig

reset_scene()
mats = build_materials(MAT, tex.build(os.path.join(HERE, "textures")))   # images are packed into the .blend
root = coll("MyAsset")                                   # one top collection = the asset
m = MB("Walls", coll("Walls", root), MAT)                # smooth=True only for organic forms
m.box(0, 0, 0, 10, 8, 3, {'side': 'brick', '+z': 'roof'}, skip=('-z',))   # skip faces that can never be seen
m.extrude([(0, 8), (10, 8), (5, 11)], 3, 3.4, 'brick', top='roof')         # any outline, either winding
m.face([(0, 0, 3), (10, 0, 3), (5, -1, 4)], 'roof', out=(0, -1, 1))         # wound to face `out`
objs = [m.build(mats)]                                   # flat shading + baked 'Bake' layer
report_tris(objs)
rig.setup(root, render_previews.EXTRA_CAMS, render_previews.DEFAULT_CAM)
save(os.path.join(HERE, "my_asset.blend"))
```

`MB.box(x0, y0, z0, x1, y1, z1, mats, skip, rep)`: `mats` is a material name or a dict keyed by face
(`'+x' '-x' '+y' '-y' '+z' '-z'`, plus `'side'` and `'default'` fallbacks). `rep` gives per-face
`(u, v)` repeats for fit-mapped materials. Build everything in world coordinates, because the bake
reads world normals and heights. `checks` fails rotated or scaled objects.

Beyond boxes:

- `face(pts, mat, out=, uv=, rep=)`: any polygon. `out` fixes the winding (Newell normal). UVs come
  from the material mapping: `W` is world-tiled along the face's axes (walls: u horizontal,
  v up), `P` is a planar projection shared by every face of an atlas, and `F` fits the face. You can
  also pass an explicit list or a `p -> (u, v)` callable.
- `extrude(outline, z0, z1, side, top=, bottom=)`: world-tiled sides run continuously around the
  perimeter.
- `loft(rings, mat, cap0=, cap1=)`, `tube(path, r, n, mat)` (r per point allowed; frames don't
  twist) and `cylinder(a, b, r, n, mat)` on any axis (wheels, axles, rails, limbs). Winding is
  chosen to face outward automatically.
- `k = m.mark()` then `m.transform(tx, ty, tz, angle, origin, start=k)` builds a prop once and
  places it. `m.mirror('y', 0, start=k)` adds a mirrored copy (winding fixed; painted lettering
  reads backwards on it).
- `smooth=True` (organic forms only) welds coincident vertices, so normals and the bake really are
  smooth.
- `place_origin(ob)` moves a reusable prop's origin to its bottom centre without moving its baked
  geometry. Do this after `build()`.

### `render_previews.py`

Define `EXTRA_CAMS = ((name, loc, target, lens), ...)` and `DEFAULT_CAM`, then under
`if __name__ == "__main__":` call `rig.setup(...)` and `rig.render(names, HERE + "/previews")`.
For interiors, pass cutaways: `rig.render(names, out, hide={'*': ['Ceiling'], 'Cam_Interior': []})`
hides the `Ceiling` collection for every shot except `Cam_Interior` and restores it afterwards.
The standard cardinal shots already see into a room, because backface culling drops the near wall.
`rig.contact_sheet(names, out)` tiles the renders into `ReviewSheet.png`, and
`rig.viewport_defaults(camera_view=True)` makes the saved file open looking through the default camera.

### `validate.py`

```python
from _lib import checks
BUDGETS = [("building", ["Walls", "Roof"], "building")]   # keys of checks.BUDGETS
r = checks.run("MyAsset", budgets=BUDGETS)                 # checks the textures packed in the .blend
checks.rays(r, [((5, 4, 1.5), (5, 20, 1.5), True)], ["Walls"], "enclosure")  # optional probes
checks.exit_with(r, json_path=os.path.join(HERE, "validation.json"))       # json optional
```

It exits 0 on pass and 1 on any failure (background Blender). Inside an interactive Blender it
returns the code instead of quitting.

- **Hard failures:** triangles over budget, non-power-of-two textures, alpha channel, more than
  64 colours, a missing or invalid material class, class parameters that don't match, backface
  culling off, emission/normal/bump nodes, a missing `Bake` layer or baked values outside the
  sun-rule range, smooth faces on hard-surface objects, subdivision modifiers, zero-area or
  duplicate faces, lights or cameras inside the asset, **rotated/scaled objects** (the bake
  ignores object transforms), **closed parts wound inward** (negative volume), and failed
  `rays()` probes.
- **Warnings:** under budget; 49-64 colours; textures larger than 512; **texel density** outside
  the `checks.DENSITY` range for a budget group's class (median px/m); **stretched texels** on more
  than 25% of an object's textured area; geometry **below ground** (z < −0.05 m); **near-neon**
  textures; non-manifold edges.
- **Not automatable** (review the previews): outward normals on open shells, grounding of
  dimensions and colours. For see-through gaps and openings, add `rays()` probes:
  `(origin, target, True)` must be blocked, `(origin, target, False)` must be clear.

**Scenes / interiors** have no single asset class. Budget the room shell (walls, floor, ceiling,
built-in structure) as `building` and each furnishing group as `large_prop` or `small_prop`, and
cap the whole scene with `total_max`.

## Commands

```sh
B=/Applications/Blender.app/Contents/MacOS/Blender
$B -b --python models/<asset>/build.py
$B -b models/<asset>/<asset>.blend --python models/<asset>/validate.py
$B -b models/<asset>/<asset>.blend --python models/<asset>/render_previews.py [-- Cam_Name ...]
$B models/<asset>/<asset>.blend --python _lib/view.py -- Cam_A Cam_B      # GUI viewer
python3 _lib/usage.py <sessionID> models/<asset> --model <ai_model> --input-rate … --output-rate … --cache-read-rate …
```

Paths above use the default layout, `models/<asset>/`. Substitute the project's own asset folder
if it defines one.
