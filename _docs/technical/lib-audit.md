# `_lib` audit: what should become shared

Audit date 2026-11-12, branch `lib-audit`. Scope: every `models/*/*/` and `scenes/**` asset
(38 script dirs, 39 `.blend` files; `models/monument/_old` excluded). `_lib/` itself was **not
modified**. This document only proposes changes.

Method: (1) AST scan of every model/scene `.py` for locally defined helpers repeated across asset
dirs; (2) reading the representative implementations; (3) a headless-Blender pass over all 39
`.blend` files measuring style rules `checks.py` does not enforce; (4) two small reproductions of
suspected `_lib` bugs. Scratch scripts live in `/tmp/libaudit/`, outside the repo.

Priority: **P0** = `_lib` bug or correctness hazard. **P1** = re-implemented in many asset dirs.
**P2** = style rules nobody checks yet. **P3** = scenes/rig/housekeeping.

---

## P0: bugs and hazards in the current `_lib`

### 1. `MB(smooth=True)` cannot produce smooth shading

`MB.poly` gives every face its own vertices, and `build()` never welds them. Vertex normals
therefore equal face normals: "organic" meshes render faceted, and `bake(me, smooth=True)` bakes
face normals. Reproduction (8-sided prism, `smooth=True`):

```
AUDIT verts 32 faces 8 (welded prism would have 16 verts)
AUDIT face0 normal (0.924, 0.383, 0.0) vertex normals [(0.924, 0.383, 0.0) x4]
```

This explains why every organic asset bypasses `MB` and hand-rolls `from_pydata` + `bmesh` +
`bake()`: `small_tree/gpt-6.1-sol`, `monument/gpt-6.1-sol`, `monument/gpt-6-astra` (and
`monument/claude-opus-5.5` subclasses `MB` to override `poly`).

**Proposal:** when `smooth=True`, weld coincident vertices before shading and baking
(`bmesh.ops.remove_doubles` with a small distance, keeping per-loop UVs), or let `poly()` share
indices through a position-keyed vertex map. Flat (hard-surface) meshes stay unwelded.

### 2. Path bootstrap and local-module caching (`_lib.boot`)

- All 38 asset dirs paste the same `HERE`/`REPO`/`sys.path` boilerplate. The `REPO` depth is
  hard-coded, so it breaks for `scenes/`, which mixes `scenes/<scene>/` (casino, 2 levels) and
  `scenes/<scene>/<family>/` (strip_club, 3 levels). `scenes/casino/*.py` falls back to a
  hard-coded `/Users/ryanenns/code/game`.
- `import textures` / `import render_previews` are cached in `sys.modules`. In the long-lived
  MCP-connected Blender, the second model built in a session silently gets the **first** model's
  textures. Reproduction (two dirs, one interpreter, same pattern as the repo's `build.py`):

  ```
  AUDIT running build in a -> got model A textures
  AUDIT running build in b -> got model A textures
  ```

  7 dirs already work around this with their own `importlib` loaders (`local_module` / `load`):
  mechanical_slot_machine/gpt-6.1-sol, monument/gpt-6-astra, niva/gpt-6-astra,
  niva/gpt-6.1-terra, telephone_booth/gpt-6.1-sol, ttc_bus/gpt-6.1-sol and scenes/casino.
  The other 31 are exposed.

**Proposal:** `_lib/boot.py` with `here, repo = boot.init(__file__)` (walk up until a dir
containing `_lib/` is found) and `textures = boot.local(__file__, 'textures')` (load by path under
a unique module name, always fresh). Update the `lib.md` template to use it.

---

## P1: helpers re-implemented across many asset dirs

Counts are distinct asset dirs that define the helper locally (AST scan).

| # | Helper | Dirs | Evidence / notes |
|---|--------|------|------------------|
| 3 | **Canvas vector shapes**: `polygon`, `ellipse`/`disc`/ring, thick `line`/polyline, `rrect`, `star`, linear gradient `vgrad`/`gmul` | ellipse 11, line 10, polygon 9, rrect/star/grad 2-3 | Near-identical even-odd scanline fills. The gpt-family copies allocate a full-canvas `np.mgrid` per call. The claude copies clip to the shape's bbox (`_grid` + `_blend_at`), which is the version to adopt. Add `alpha=` and `wrap=` (horizontal tiling, like `rect_wrap`). |
| 4 | **Real-typeface lettering** | 8 files, 3 incompatible approaches | `_lib` ships only the 5×7 font, which the style guide forbids for non-digital signage, so every lettered asset had to improvise: (a) subprocess to system Python + Pillow (streetcar/bus/strip_club gpt-6.1-sol, casino); streetcar hard-codes `/opt/homebrew/bin/rtk`, casino needs Pillow in `/usr/bin/python3`. (b) `blf` + `imbuf` in-process (mechanical_slot_machine/claude-opus-5.5): no external deps, supports cap-height sizing, tracking, condensing, alignment. (c) font-curve → triangles (ttc_streetcar & strip_club claude-opus-5.5). **Proposal:** `Canvas.type(txt, x, y, cap_h, col, font='sans', align='l', track=0, sx=1)` built on (b), with a small font registry (`sans`, `cond`, `serif`, `slab`, `script`) mapped to macOS Supplemental fonts and Blender's bundled font as fallback. Rename `text`/`text_c` to `led_text`/`led_text_c` (keep aliases) so the digital-only intent is in the name. |
| 5 | **Metric/atlas painting frame** (metres → pixels, z-up → row-down) | ~14 textures.py | Classes `P`, `Bay`, `Fac`, `Meter`, `Proj`, `SideMap`, `Ref`, plus inline `p()/sp()/X()/Y()` mappers (niva ×3, bus, streetcar, stalinka ×4, apartment ×2, slot machine). **Proposal:** `Canvas.frame(x0, z0, x1, z1)` returning a view whose `rect/mul/polygon/line/ellipse/type` take metres. |
| 6 | **Arbitrary polygons in `MB`**: Newell-normal auto-winding + projected UVs | face/poly/newell in ~14 dirs | `MB` only offers `box/quad/prism`. 28 of 38 `build.py` files call raw `MB.poly()` and hand-compute winding (`newell` copied 5×) and UVs. **Proposal:** `MB.face(pts, mat, out=None, uv=None)`, plus a planar-projection mapping `P(origin, R, U, w, h)` in `shading` alongside `W`/`F`, for vehicle/facade atlases. |
| 7 | **`MB` shape ops**: `extrude(outline, z0, z1)`, `loft(rings)`, `tube(a, b, r, n)` / spine tube on any axis, `transform(tx, ty, angle)`, mirror-in-x/y | loft 4, tube 5, beam 4, wheels 7 (all vehicles), `for s in (-1,1)` mirroring in 4 | `prism` is vertical only, so every vehicle reinvents a horizontal cylinder for its wheels. Casino repositions props by rewriting `m.verts` (`transform`). |
| 8 | **Painted window** following the §4 order (frame/sill → dark glass → sky glint → mullion), with a shared `LIT = (138, 122, 92)` | window painters in 18 textures.py; the lit RGB literal in 16 | Every building model encodes the same style rule by hand. **Proposal:** `paint.window(canvas_or_frame, x0, z0, x1, z1, panes=, lit=, frame=, glass=)` and `paint.LIT`, `paint.GLASS`, `paint.SKY` constants. A masonry/coursed-block painter (§4 masonry rule) is implemented only in `gas_station/claude`, so it's a lower priority but the rule is equally mandatory. |

Not proposed for `_lib`: asset-specific builders (balcony, facade, bay, crest, plinth, roof_box,
stool, door layouts). They share names, but not code or meaning.

---

## P2: style rules that `checks.py` does not enforce, and measured violations

One headless-Blender pass over all 39 `.blend` files (`/tmp/libaudit/measure.py`). Per textured
face it computes the UV→world Jacobian. Texel density is √(σ₁σ₂) px/m; **stretch** is σ₁/σ₂ > 1.5
(texels not square in world space, i.e. §4 "never stretch").

| asset | px/m p10 / median / p90 | stretched faces | min z (m) | textures with >2 % neon pixels |
|---|---|---|---|---|
| apartment_block/claude-haiku-5.5 | 10.7 / 23.9 / 23.9 | 0.0 % | 0.000 | 0/15 |
| apartment_block/claude-opus-5.5 | 16.0 / 21.4 / 25.1 | 5.8 % | 0.000 | 0/31 |
| apartment_block/claude-sonnet-5.5 | 10.7 / 10.7 / 32.0 | 1.1 % | 0.000 | 0/16 |
| apartment_block/deepseek-v4-pro | 16.0 / 21.3 / 88.3 | 5.6 % | **-0.150** | 0/15 |
| apartment_block/deepseek-v4.1-flash | 10.7 / 31.0 / 116.4 | **69.1 %** | 0.000 | 0/30 |
| apartment_block/gemini-4-argon | 21.3 / 47.6 / 54.3 | 0.9 % | 0.000 | 0/15 |
| apartment_block/gpt-6-luna | 20.2 / 22.6 / 71.6 | **94.6 %** | **-1.000** | 0/12 |
| apartment_block/gpt-6.1-sol | 10.7 / 22.1 / 35.2 | 13.7 % | 0.000 | 0/30 |
| apartment_block/gpt-6.1-terra | 10.7 / 45.1 / 74.7 | 8.7 % | 0.000 | 0/10 |
| gas_station/claude | 8.0 / 13.9 / 32.0 | 30.3 % | **-0.120** | 0/59 |
| mechanical_slot_machine/claude-opus-5.5 | 320 / 640 / 998 | 22.7 % | 0.000 | 0/8 |
| mechanical_slot_machine/gpt-6.1-sol | 516 / 1646 / 2304 | **67.7 %** | 0.000 | 0/10 |
| monument/claude-opus-5.5 | 14.2 / 15.9 / 16.0 | 42.9 % | 0.000 | 0/7 |
| monument/gpt-6-astra | 7.5 / 9.0 / 9.9 | 17.5 % | 0.000 | 0/7 |
| monument/gpt-6.1-sol | 10.8 / 12.0 / 12.7 | 2.5 % | 0.000 | 0/4 |
| niva/claude-opus-5.5 | 15.5 / 93.3 / 126.4 | 55.6 % | 0.000 | 0/13 |
| niva/gpt-6-astra | 84.9 / 189.3 / 305.8 | 65.5 % | 0.000 | 0/9 |
| niva/gpt-6-luna | 63.2 / 63.2 / 506.0 | **73.4 %** | -0.025 | 0/12 |
| niva/gpt-6.1-sol | 85.5 / 136.5 / 238.0 | 57.8 % | 0.000 | 0/13 |
| niva/gpt-6.1-terra | 69.3 / 146.8 / 211.8 | 13.3 % | 0.000 | 0/9 |
| niva/kimi-k3.1-pro | 79.0 / 388.2 / 616.0 | 59.8 % | 0.000 | 0/15 |
| small_tree/gpt-6.1-sol | 42.5 / 47.9 / 52.2 | 12.9 % | -0.003 | 0/3 |
| stalinka/claude-opus-5.5 | 15.2 / 20.3 / 26.7 | 4.4 % | 0.000 | 0/42 |
| stalinka/gemini-4-argon | 16.0 / 24.1 / 103.5 | 38.2 % | 0.000 | 0/16 |
| stalinka/glm-5.3-flash | 16.0 / 16.0 / 54.9 | 27.3 % | 0.000 | 0/16 |
| stalinka/gpt-6-astra | 12.0 / 25.3 / 45.3 | 61.5 % | 0.000 | 0/11 |
| stalinka/gpt-6.1-sol | 15.0 / 19.6 / 42.2 | 37.2 % | 0.000 | 0/17 |
| stalinka/grok-4.7 | 10.7 / 18.3 / 37.3 | 11.0 % | 0.000 | **16/25** |
| stalinka/kimi-k3.1-pro | 17.0 / 26.7 / 31.0 | 13.9 % | 0.000 | 0/23 |
| stalinka/qwen-3.8-max | 6.7 / 13.3 / 39.4 | 16.6 % | 0.000 | 0/15 |
| telephone_booth/gpt-6.1-sol | 130.0 / 136.2 / 170.0 | 64.0 % | 0.000 | 0/7 |
| telephone_booth/gpt-6.1-terra | 40.0 / 45.7 / 149.9 | 14.3 % | 0.000 | 0/8 |
| ttc_bus/gpt-6.1-sol | 39.2 / 48.0 / 71.9 | **71.7 %** | 0.005 | 1/14 |
| ttc_streetcar/claude-opus-5.5 | 16.0 / 19.4 / 43.4 | 13.1 % | 0.000 | 8/19 |
| ttc_streetcar/gpt-6.1-sol | 40.2 / 80.1 / 219.4 | 55.3 % | 0.000 | 0/18 |
| scenes/casino (casino.blend) | 32.0 / 32.0 / 184.3 | 16.6 % | **-0.160** | 0/26 |
| scenes/casino (casino_assets.blend) | 32.0 / 32.0 / 184.3 | 18.0 % | 0.000 | 0/15 |
| scenes/strip_club/claude-opus-5.5 | 16.0 / 16.0 / 121.3 | 16.6 % | 0.000 | 0/41 |
| scenes/strip_club/gpt-6.1-sol | 20.0 / 220.7 / 490.9 | **80.7 %** | 0.000 | 0/24 |

"Neon" = pixels with HSV saturation > 0.75 and value > 0.75. Non-identity object rotation/scale:
0 in all files (the bake assumes world-space meshes, so this is worth guarding anyway).

Caveats: the §4 density targets (8-20 px/m) are written for buildings. Small props and vehicles
legitimately run denser, so density should be checked **per budget class** and as a warning.
Thin trim strips mapped with `F` produce some intended anisotropy. The neon metric flags
legitimate saturated brand colour (TTC red), so it should be a warning too.

Proposed additions to `checks.py` (all **warnings** unless noted):

| # | Check | Why |
|---|-------|-----|
| 9 | Texel density per budget class (report p10/median/p90; warn outside class range) | §4 texel density; spreads above show 10-100× variation within one asset |
| 10 | UV stretch: warn when > N % of the textured area has σ₁/σ₂ > 1.5 | §4 "never stretch"; 9 assets over 60 % |
| 11 | Geometry below ground (z < -0.05 m) | §2 "no faces that can never be seen"; 4 assets (down to -1.0 m) |
| 12 | `checks.rays(report, origin_dir_pairs, objects, expect_hit=True)` see-through / enclosure probe helper | §2 watertight is listed "not automatable", yet 4 validators already ray-cast by hand (telephone_booth/gpt-6.1-terra, mechanical_slot_machine/gpt-6.1-sol, scenes/casino, + coverage grid) |
| 13 | Closed-volume sanity for organic meshes: non-manifold edges, negative signed volume (**fail**) | small_tree/gpt-6.1-sol and monument/gpt-6-astra each implement this |
| 14 | Neon / over-saturation share per texture | §6 "nothing neon"; flags stalinka/grok-4.7 16/25 |
| 15 | Object transform must be identity rotation/scale (**fail**) | `bake()` reads world normals from mesh data; one stray rotation silently breaks lighting |
| 16 | `exit_with(report, json_path=None)` to also write `validation.json` | 4+ validators serialize the report by hand |

---

## P3: rig, scenes and housekeeping

| # | Item | Evidence |
|---|------|----------|
| 17 | `rig.render(..., cutaway={cam_name: [collections]})` / `hide=` to hide removable ceilings or walls per shot | scenes/casino wraps `rig.render` to toggle `hide_render` on 3 collections. Interiors otherwise work with the rig because backface culling drops the near wall. |
| 18 | Interior budget convention | Both strip_club models and casino budget a room as `building` (shell) plus `large_prop`/`small_prop` groups with a `total_max`. Document it in `checks.BUDGETS`/`lib.md` (or add a `room` class) so scenes stop inventing it. |
| 19 | `reset_scene()` misses curves, fonts, texts, node groups, extra scenes, actions | telephone_booth/gpt-6.1-sol renames every old datablock instead of resetting; opus text-via-curve code cleans up after itself manually |
| 20 | `rig.viewport_defaults(camera_view=True)` to open in the default camera | `finalize()` in 3 gpt-6.1-sol models + casino set `view_perspective='CAMERA'` by hand |
| 21 | Optional `rig.contact_sheet(names, out)` | strip_club/gpt-6.1-sol produced `ReviewSheet.png`; useful for side-by-side review |

### Outside `_lib` (tooling/docs, not Blender code)

- **`usage.json` calculator.** Every asset follows the long manual procedure in
  `project-structure.md`. 36 files exist; 24 lack `effort` (the doc says "exactly these six fields"
  but later "retain the five-field JSON format", which contradicts it). Missing: deepseek-v4-pro
  apartment_block, gpt-6-astra monument. A plain-Python `tools/usage.py <sessionID> <asset dir>`
  would standardize this.
- **`scenes/` layout is undocumented.** `project-structure.md` only defines `models/`. Casino sits
  at `scenes/casino/` with no family dir; strip_club uses `scenes/<scene>/<family>/`.
- **`.gitignore`** ignores `models/**/textures|previews` but not `scenes/**`: 33 scene preview
  files (plus textures and `__pycache__`) are tracked.

---

## Suggested order

1. P0 #1 (smooth welding) and #2 (`boot`). Small, fixes silent wrong output.
2. P1 #3 shapes + #4 `Canvas.type` + #5 `frame`. These remove the most duplicated code and the
   style-guide/lib contradiction on typography.
3. P1 #6-#7 `MB.face`/projection/extrude/tube.
4. P2 checks as **warnings first**, so existing assets don't start failing. Promote to failures
   once the thresholds are tuned against the table above.
5. Then extract the `/ps2-graphics` skill on top of the expanded `_lib`.
