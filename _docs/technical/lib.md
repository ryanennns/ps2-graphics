# `_lib`: shared asset pipeline

`_lib/` (at the repo root) is the shared Python code that every model uses, whatever agent or model
family made it. It implements the mechanical parts of `_docs/style-preferences/style.md`, so every
asset gets the same sun, shader, texture processing, preview rig and self-check.

> **Agents must not modify anything in `_lib/` unless the user explicitly asks them to.**
> Treat it as read-only. If your model needs something `_lib` doesn't provide, write it in your
> model's own scripts (see `_docs/project-preferences/project-structure.md`). If you think `_lib`
> has a bug or a missing feature, say so to the user and don't change it yourself. Changing `_lib`
> changes every model in the repo, including other agents' models.

Everything runs inside Blender (5.2+) with its bundled Python (`numpy` and `OpenImageIO` are included).

## Modules

| Module | What it gives you | Style rules it enforces |
|---|---|---|
| `paint.py` | `Canvas` (4× supersampled painting: `rect`, `rect_wrap`, `mul`, `text`, `text_c`, `weather`), `tile_noise`, `plain()`, `shade()`, `mix()`, `quantize()`, `save_png()`, `TextureSet` registry | §4: paint at 4× then box-filter, palette-quantize with no dither, RGB with no alpha, power-of-two sizes, correlated weathering, 5×7 bitmap font |
| `shading.py` | The one shared sun (`SUN`, `SUN_ELEV`), `bake()`, `MaterialTable` with `W()`/`F` UV mappings, `build_materials()` | §3: baked vertex light (up 1.0, down 0.6, walls 0.76–1.0, ground ×0.84→1.0 over 2.5 m). §5: texture × `Bake` → Principled; matte unless glass/metal; four classes only |
| `geometry.py` | `MB` mesh builder (`box`, `quad`, `prism`, `poly`, `build`), `coll()`, `reset_scene()`, `report_tris()`, `save()` | §2: flat shading, outward winding, per-face `skip` for hidden faces, world-space metres |
| `rig.py` | `setup(asset_root, extra_cams, default_cam)`, `render(names, out_dir)`, `viewport_defaults()` | §7: same sun/sky/32 mm/900×600 for everything, 4 cardinal + 3/4 aerial (+ top above 35 m) |
| `checks.py` | `run(asset_root, tex_dir=None, budgets, total_max)`, `exit_with(report)`, `BUDGETS` | §8 self-check (see below) |
| `view.py` | Opens a `.blend` split into one Material Preview panel per camera | none (viewing helper) |

## How a model uses it

Each model script puts the repo root on `sys.path` and imports from `_lib`:

```python
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))   # models/<family>/<asset>/ -> repo root
if REPO not in sys.path:
    sys.path.insert(0, REPO)
```

### `textures.py`: painters plus the material table

```python
from _lib.paint import Canvas, TextureSet, plain, shade, mix
from _lib.shading import MaterialTable, W, F

tex = TextureSet(colors=40)          # 32-48 colours per texture

@tex
def t_brick():                       # saved as textures/brick.png
    c = Canvas(64, 64, (150, 80, 60))   # final size; painting happens at 4x internally
    ...
    c.weather(0.05, 6, seed=1)
    return c

MAT = MaterialTable()
MAT.add('brick', 'brick', 'concrete', W(3.2, 3.2))   # world-tiled: 1 repeat per 3.2 x 3.2 m
MAT.add('sign', 'sign', 'metal', F)                  # fit to the face (per-face repeat optional)
```

### `build.py`: geometry, then save

```python
import bpy
import textures
from textures import MAT, tex
from _lib.geometry import MB, coll, reset_scene, report_tris, save
from _lib.shading import build_materials
from _lib import rig
import render_previews

reset_scene()
mats = build_materials(MAT, tex.build(os.path.join(HERE, "textures")))   # images are packed into the .blend
root = coll("MyAsset")                                   # one top collection = the asset
m = MB("Walls", coll("Walls", root), MAT)                # smooth=True only for organic forms
m.box(0, 0, 0, 10, 8, 3, {'side': 'brick', '+z': 'roof'}, skip=('-z',))   # skip faces that can never be seen
objs = [m.build(mats)]                                   # flat shading + baked 'Bake' layer
report_tris(objs)
rig.setup(root, render_previews.EXTRA_CAMS, render_previews.DEFAULT_CAM)
save(os.path.join(HERE, "my_asset.blend"))
```

`MB.box(x0, y0, z0, x1, y1, z1, mats, skip, rep)`: `mats` is a material name or a dict keyed by face
(`'+x' '-x' '+y' '-y' '+z' '-z'`, plus `'side'` and `'default'` fallbacks). `rep` gives per-face
`(u, v)` repeats for fit-mapped materials. Build everything in world coordinates, because the bake
reads world normals and heights.

### `render_previews.py`

Define `EXTRA_CAMS = ((name, loc, target, lens), ...)` and `DEFAULT_CAM`, then under
`if __name__ == "__main__":` call `rig.setup(...)` and `rig.render(names, HERE + "/previews")`.

### `validate.py`

```python
from _lib import checks
BUDGETS = [("building", ["Walls", "Roof"], "building")]   # keys of checks.BUDGETS
checks.exit_with(checks.run("MyAsset", budgets=BUDGETS))   # checks the textures packed in the .blend
```

It exits 0 on pass and 1 on any failure.

- **Hard failures:** triangles over budget, non-power-of-two textures, alpha channel, more than
  64 colours, a missing or invalid material class, class parameters that don't match, backface
  culling off, emission/normal/bump nodes, a missing `Bake` layer or baked values outside the
  sun-rule range, smooth faces on hard-surface objects, subdivision modifiers, zero-area or
  duplicate faces, and lights or cameras inside the asset.
- **Warnings:** under budget, 49-64 colours, textures larger than 512.
- **Not automatable** (review the previews): outward normals on open shells, see-through gaps,
  grounding of dimensions and colours.

## Commands

```sh
B=/Applications/Blender.app/Contents/MacOS/Blender
$B -b --python models/<family>/<asset>/build.py
$B -b models/<family>/<asset>/<asset>.blend --python models/<family>/<asset>/validate.py
$B -b models/<family>/<asset>/<asset>.blend --python models/<family>/<asset>/render_previews.py [-- Cam_Name ...]
$B models/<family>/<asset>/<asset>.blend --python _lib/view.py -- Cam_A Cam_B      # GUI viewer
```

Reference implementation: `models/claude/gas_station/`.
