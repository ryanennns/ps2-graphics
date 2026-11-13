"""Automated style.md section 8 self-check. Runs inside Blender on a saved asset .blend.

Hard failures (exit 1): broken MUST rules. Warnings: judgement calls to report in NOTES.md.
Not automatable, so review the previews for these: outward-facing normals on open shells,
real-world grounding, and whether the colours look right. For see-through gaps and openings,
probe the asset with rays() from the asset's validate.py.
"""
import math, os, sys
import numpy as np
import bpy

from .shading import CLASSES, CLASS_PARAMS, BAKE_LAYER
from .rig import RIG_COLL

BUDGETS = {  # style.md section 2 triangle budgets
    'small_prop': (12, 150),
    'large_prop': (300, 1500),
    'minor_building': (10, 200),
    'building': (200, 2000),
    'landmark': (5000, 40000),
    'character': (1000, 3000),
}


# median texel density (px/m) expected per class; outside = warning (style.md section 4: 8-12 px/m
# plain and 16-20 px/m detailed surfaces on buildings; small objects carry 128-256 px textures)
DENSITY = {
    'small_prop': (20, 640),
    'large_prop': (10, 160),
    'minor_building': (6, 32),
    'building': (6, 32),
    'landmark': (5, 32),
    'character': (16, 256),
}
STRETCH_RATIO = 1.5     # texel aspect (px/m along u vs v) above this counts as stretched
STRETCH_SHARE = 0.25    # warn when more than this share of an object's textured area is stretched
NEON_SHARE = 0.02       # warn when more than this share of a texture's pixels is neon-like
BELOW_GROUND = -0.05    # metres; geometry below this can never be seen


class Report:
    def __init__(s):
        s.fail, s.warn, s.info = [], [], []

    def f(s, m): s.fail.append(m)
    def w(s, m):
        if m not in s.warn:
            s.warn.append(m)
    def i(s, m): s.info.append(m)

    def print(s):
        for tag, items in (("INFO", s.info), ("WARN", s.warn), ("FAIL", s.fail)):
            for m in items:
                print(f"[{tag}] {m}")
        print(f"CHECK RESULT: {'FAIL' if s.fail else 'PASS'} ({len(s.fail)} failures, {len(s.warn)} warnings)")


def _tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


def _check_pixels(r, label, w, h, ch, px):
    if w & (w - 1) or h & (h - 1):
        r.f(f"texture {label}: {w}x{h} not power-of-two")
    if ch != 3:
        r.f(f"texture {label}: {ch} channels (must be RGB, no alpha)")
    if max(w, h) > 512:
        r.w(f"texture {label}: {w}x{h} larger than the 512 facade size")
    if ch >= 3:
        check_saturation(r, label, px)
    n = len(np.unique(np.asarray(px).reshape(-1, ch)[:, :3], axis=0))
    if n > 64:
        r.f(f"texture {label}: {n} colours (> 64; not palette-quantized)")
    elif n > 48:
        r.w(f"texture {label}: {n} colours (target 32-48)")


def _read(path):
    import OpenImageIO as oiio
    img = oiio.ImageInput.open(path)
    if img is None:
        return None
    spec = img.spec()
    px = img.read_image('uint8')
    img.close()
    return spec.width, spec.height, spec.nchannels, px


def check_textures(r, images, tex_dir=None):
    """Checks the images packed into the .blend (what ships). tex_dir, if given, is checked too."""
    import tempfile
    n = 0
    for im in images:
        if im.packed_file is None:
            r.f(f"image {im.name}: not packed into the .blend")
            continue
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(im.filepath)[1] or '.png', delete=False) as t:
            t.write(im.packed_file.data)
        res = _read(t.name)
        os.unlink(t.name)
        if res is None:
            r.f(f"image {im.name}: packed data unreadable")
            continue
        _check_pixels(r, im.name, *res)
        n += 1
    r.i(f"{n} packed textures checked")
    if tex_dir and os.path.isdir(tex_dir):
        for f in sorted(f for f in os.listdir(tex_dir) if f.lower().endswith('.png')):
            res = _read(os.path.join(tex_dir, f))
            if res:
                _check_pixels(r, f, *res)


def check_materials(r, mats):
    for m in mats:
        cls = m.get('style_class')
        if cls not in CLASSES:
            r.f(f"material {m.name}: missing/invalid style_class {cls!r}")
            continue
        if not m.use_backface_culling:
            r.f(f"material {m.name}: backface culling off")
        nodes = m.node_tree.nodes if m.node_tree else []
        bsdf = [n for n in nodes if n.type == 'BSDF_PRINCIPLED']
        if len(bsdf) != 1:
            r.f(f"material {m.name}: expected one Principled BSDF")
            continue
        b = bsdf[0]
        met, rough, spec = CLASS_PARAMS[cls]
        got = (b.inputs['Metallic'].default_value, b.inputs['Roughness'].default_value,
               b.inputs['Specular IOR Level'].default_value)
        if any(abs(a - e) > 0.06 for a, e in zip(got, (met, rough, spec))):
            r.f(f"material {m.name} ({cls}): metallic/rough/spec {tuple(round(g, 2) for g in got)} != {(met, rough, spec)}")
        if b.inputs['Emission Strength'].default_value > 0 and tuple(b.inputs['Emission Color'].default_value)[:3] != (0, 0, 0):
            r.f(f"material {m.name}: emission enabled")
        if any(n.type in ('EMISSION', 'NORMAL_MAP', 'BUMP') for n in nodes):
            r.f(f"material {m.name}: uses emission/normal/bump node")
        if not any(n.type == 'VERTEX_COLOR' and n.layer_name == BAKE_LAYER for n in nodes):
            r.f(f"material {m.name}: does not multiply the '{BAKE_LAYER}' vertex colour")
        imgs = [n.image for n in nodes if n.type == 'TEX_IMAGE' and n.image]
        if not imgs:
            r.f(f"material {m.name}: no texture")
        for im in imgs:
            if im.depth not in (24, 0) and im.packed_file is not None:
                r.f(f"material {m.name}: image {im.name} depth {im.depth} (alpha?)")


def check_meshes(r, objs):
    for o in objs:
        me = o.data
        if not me.uv_layers:
            r.f(f"{o.name}: no UVs")
        attr = me.color_attributes.get(BAKE_LAYER)
        if attr is None or attr.domain != 'CORNER':
            r.f(f"{o.name}: missing per-corner '{BAKE_LAYER}' layer")
        else:
            vals = np.zeros(len(attr.data) * 4, np.float32)
            attr.data.foreach_get('color', vals)
            lin = vals.reshape(-1, 4)[:, 0]
            srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(np.maximum(lin, 0), 1 / 2.4) - 0.055)
            if srgb.min() < 0.6 * 0.84 - 0.01 or srgb.max() > 1.0001:
                r.f(f"{o.name}: baked brightness {srgb.min():.2f}..{srgb.max():.2f} outside sun-rule range 0.50..1.00")
        organic = bool(o.get('organic', False))
        smooth = sum(p.use_smooth for p in me.polygons)
        if not organic and smooth:
            r.f(f"{o.name}: {smooth} smooth-shaded faces on a hard-surface object")
        if any(m.type == 'SUBSURF' for m in o.modifiers):
            r.f(f"{o.name}: subdivision modifier")
        zero = sum(1 for p in me.polygons if p.area < 1e-6)
        if zero:
            r.f(f"{o.name}: {zero} zero-area faces")
        mw = o.matrix_world
        keys, dups = set(), 0
        for p in me.polygons:
            k = tuple(sorted(tuple(round(c, 3) for c in (mw @ me.vertices[v].co)) for v in p.vertices))
            if k in keys:
                dups += 1
            keys.add(k)
        if dups:
            r.f(f"{o.name}: {dups} duplicate/coincident faces (z-fighting or double-sided)")


def _img_size(m):
    nodes = m.node_tree.nodes if m and m.node_tree else []
    for n in nodes:
        if n.type == 'TEX_IMAGE' and n.image and n.image.size[0]:
            return n.image.size[0], n.image.size[1]
    return None


def face_texels(o):
    """[(world area, texel density px/m, texel aspect)] per textured face of a mesh object."""
    me = o.data
    uv = me.uv_layers.active
    if uv is None:
        return []
    mw = o.matrix_world
    sizes = [_img_size(m) for m in me.materials]
    out = []
    for p in me.polygons:
        if p.area < 1e-5 or p.material_index >= len(sizes) or sizes[p.material_index] is None:
            continue
        W, H = sizes[p.material_index]
        L = list(p.loop_indices)
        A = [mw @ me.vertices[me.loops[i].vertex_index].co for i in L]
        Uv = [uv.data[i].uv for i in L]
        # area-weighted fan of triangles
        acc_a = acc_d = 0.0
        acc_s = []
        for k in range(1, len(L) - 1):
            e1, e2 = A[k] - A[0], A[k + 1] - A[0]
            ax = e1.normalized() if e1.length > 1e-9 else None
            if ax is None:
                continue
            ay = e2 - ax * e2.dot(ax)
            if ay.length < 1e-9:
                continue
            ay.normalize()
            Pm = np.array([[e1.dot(ax), e2.dot(ax)], [e1.dot(ay), e2.dot(ay)]])
            Tm = np.array([[(Uv[k].x - Uv[0].x) * W, (Uv[k + 1].x - Uv[0].x) * W],
                           [(Uv[k].y - Uv[0].y) * H, (Uv[k + 1].y - Uv[0].y) * H]])
            if abs(np.linalg.det(Pm)) < 1e-12:
                continue
            sv = np.linalg.svd(Tm @ np.linalg.inv(Pm), compute_uv=False)
            if sv[1] < 1e-6:
                continue
            a = abs(np.linalg.det(Pm)) / 2
            acc_a += a; acc_d += a * math.sqrt(sv[0] * sv[1]); acc_s.append((a, sv[0] / sv[1]))
        if acc_a > 0:
            out.append((acc_a, acc_d / acc_a, max(s for _, s in acc_s)))
    return out


def _wmedian(vals, weights):
    o = np.argsort(vals)
    v, w = np.asarray(vals)[o], np.asarray(weights)[o]
    c = np.cumsum(w)
    return float(v[np.searchsorted(c, c[-1] / 2)])


def check_texels(r, objs, budgets):
    """Texel density per budget class and UV stretch per object (warnings)."""
    per = {o.name: face_texels(o) for o in objs}
    for o in objs:
        f = per[o.name]
        tot = sum(a for a, _, _ in f)
        if tot <= 0:
            continue
        bad = sum(a for a, _, s in f if s > STRETCH_RATIO) / tot
        if bad > STRETCH_SHARE:
            r.w(f"{o.name}: {bad:.0%} of textured area has stretched texels (aspect > {STRETCH_RATIO}); "
                f"texture should tile on the real grid, not stretch")
    for label, names, cls in budgets:
        f = [t for n in names for t in per.get(n, [])]
        if not f or cls not in DENSITY:
            continue
        med = _wmedian([d for _, d, _ in f], [a for a, _, _ in f])
        lo, hi = DENSITY[cls]
        msg = f"texel density {label}: median {med:.1f} px/m"
        (r.i if lo <= med <= hi else r.w)(msg + ("" if lo <= med <= hi else f" outside {lo}-{hi} ({cls})"))


def _components(o):
    """Per connected part (by vertex position): (closed, non-manifold edge count, signed volume)."""
    me, mw = o.data, o.matrix_world
    key = [tuple(round(c, 4) for c in (mw @ v.co)) for v in me.vertices]
    ids = {}
    vk = [ids.setdefault(k, len(ids)) for k in key]
    parent = list(range(len(ids)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    edges = {}
    for p in me.polygons:
        vs = [vk[v] for v in p.vertices]
        for a, b in zip(vs, vs[1:] + vs[:1]):
            if a != b:
                edges.setdefault((min(a, b), max(a, b)), []).append(p.index)
                parent[find(a)] = find(b)
    comp = {}
    for p in me.polygons:
        c = find(vk[p.vertices[0]])
        d = comp.setdefault(c, [0.0, set()])
        pts = [mw @ me.vertices[v].co for v in p.vertices]
        for k in range(1, len(pts) - 1):
            d[0] += pts[0].dot(pts[k].cross(pts[k + 1])) / 6
        d[1].add(p.index)
    ecount = {}
    for (a, b), f in edges.items():
        ecount.setdefault(find(a), []).append(len(f))
    out = []
    for c, (vol, faces) in comp.items():
        ce = ecount.get(c, [])
        out.append((bool(ce) and all(n == 2 for n in ce), sum(n > 2 for n in ce), vol))
    return out


def check_volumes(r, objs):
    """Closed parts must enclose positive volume (outward winding). Non-manifold edges: warning."""
    for o in objs:
        if len(o.data.polygons) > 20000:
            r.i(f"{o.name}: volume check skipped ({len(o.data.polygons)} faces)")
            continue
        inv = nm = 0
        for closed, nonman, vol in _components(o):
            nm += nonman
            if closed and vol < -1e-6:
                inv += 1
        if inv:
            r.f(f"{o.name}: {inv} closed part(s) wound inward (negative volume); faces point inside")
        if nm:
            r.w(f"{o.name}: {nm} non-manifold edges (shared by 3+ faces)")


def check_placement(r, objs):
    """Bake reads world-space mesh data: objects must not be rotated or scaled. Nothing below ground."""
    zmin = 1e9
    for o in objs:
        m3 = o.matrix_world.to_3x3()
        if any(abs(m3[i][j] - (1.0 if i == j else 0.0)) > 1e-5 for i in range(3) for j in range(3)):
            r.f(f"{o.name}: object is rotated/scaled; build in world space (the bake ignores object transforms)")
        for v in o.data.vertices:
            zmin = min(zmin, (o.matrix_world @ v.co).z)
    if objs and zmin < BELOW_GROUND:
        r.w(f"asset geometry reaches z = {zmin:.2f} m, below ground (faces there can never be seen)")


def check_saturation(r, label, px):
    a = np.asarray(px, np.float32).reshape(-1, np.asarray(px).shape[-1])[:, :3] / 255.0
    mx, mn = a.max(1), a.min(1)
    share = float((((mx - mn) / np.maximum(mx, 1e-6) > 0.75) & (mx > 0.75)).mean())
    if share > NEON_SHARE:
        r.w(f"texture {label}: {share:.0%} near-neon pixels (style.md section 6: muted, nothing neon)")


def rays(r, tests, objects, label="ray"):
    """Probe the asset with segments, from validate.py. tests: [(origin, target, expect_hit)].
    expect_hit=True: something must block the segment (enclosure, no see-through gap);
    False: it must be clear (an opening, a hollow interior). objects: mesh objects or names.
    Returns the list of (hit?, ok?) per test."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    verts, polys = [], []
    for o in objects:
        o = bpy.data.objects[o] if isinstance(o, str) else o
        base = len(verts)
        verts += [tuple(o.matrix_world @ v.co) for v in o.data.vertices]
        polys += [[base + i for i in p.vertices] for p in o.data.polygons]
    bvh = BVHTree.FromPolygons(verts, polys)
    res = []
    for origin, target, expect in tests:
        o, t = Vector(origin), Vector(target)
        d = t - o
        hit = bvh.ray_cast(o, d.normalized(), d.length)[0] is not None
        ok = hit == bool(expect)
        res.append((hit, ok))
        if not ok:
            r.f(f"{label} {tuple(origin)} -> {tuple(target)}: " + ("blocked, expected clear" if hit else "clear, expected blocked (see-through gap?)"))
    if all(ok for _, ok in res):
        r.i(f"{label}: {len(res)} probes as expected")
    return res


def run(asset_root_name, tex_dir=None, budgets=(), total_max=None):
    """tex_dir: optional loose texture folder (packed images are always checked).
    budgets: [(label, [object names], class key)]; total_max: optional cap on whole asset."""
    r = Report()
    root = bpy.data.collections.get(asset_root_name)
    if root is None:
        r.f(f"asset collection {asset_root_name!r} not found")
        r.print()
        return r
    objs = [o for o in root.all_objects]
    meshes = [o for o in objs if o.type == 'MESH']
    for o in objs:
        if o.type in ('LIGHT', 'CAMERA'):
            r.f(f"{o.name}: {o.type.lower()} inside the asset (lights/cameras belong in {RIG_COLL!r})")
    for o in bpy.data.objects:
        if o.type == 'LIGHT' and not any(c.name == RIG_COLL for c in o.users_collection):
            r.f(f"{o.name}: real-time light outside the preview rig")
    by_name = {o.name: o for o in meshes}
    total = sum(_tris(o) for o in meshes)
    for label, names, cls in budgets:
        lo, hi = BUDGETS[cls]
        missing = [n for n in names if n not in by_name]
        if missing:
            r.f(f"budget {label}: objects not found {missing}")
            continue
        t = sum(_tris(by_name[n]) for n in names)
        if t > hi:
            r.f(f"budget {label}: {t} tris > {hi} ({cls})")
        elif t < lo:
            r.w(f"budget {label}: {t} tris < {lo} ({cls}); under budget")
        else:
            r.i(f"budget {label}: {t} tris within {lo}-{hi} ({cls})")
    if total_max is not None and total > total_max:
        r.f(f"asset total {total} tris > {total_max}")
    r.i(f"asset total {total} tris in {len(meshes)} meshes")
    mats = {m for o in meshes for m in o.data.materials if m}
    check_materials(r, sorted(mats, key=lambda m: m.name))
    check_meshes(r, meshes)
    check_placement(r, meshes)
    check_volumes(r, meshes)
    check_texels(r, meshes, [b for b in budgets if all(n in by_name for n in b[1])])
    imgs = {n.image for m in mats if m.node_tree for n in m.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image}
    check_textures(r, sorted(imgs, key=lambda i: i.name), tex_dir)
    r.print()
    return r


def exit_with(report, json_path=None):
    """Exit 1 on failure, 0 on pass (background Blender). json_path: also write the report there.
    Inside an interactive Blender (e.g. the MCP session) it returns the code instead of killing it."""
    code = 1 if report.fail else 0
    if json_path:
        import json
        with open(json_path, 'w') as fh:
            json.dump({'pass': not report.fail, 'failures': report.fail, 'warnings': report.warn,
                       'info': report.info}, fh, indent=2)
    sys.stdout.flush()
    if bpy.app.background:
        os._exit(code)
    return code
