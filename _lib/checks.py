"""Automated style.md section 8 self-check. Runs inside Blender on a saved asset .blend.

Hard failures (exit 1): broken MUST rules. Warnings: judgement calls to report in NOTES.md.
Not automatable, so review the previews for these: outward-facing normals on open shells,
see-through gaps, real-world grounding, and whether the colours look right.
"""
import os, sys
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


class Report:
    def __init__(s):
        s.fail, s.warn, s.info = [], [], []

    def f(s, m): s.fail.append(m)
    def w(s, m): s.warn.append(m)
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
    imgs = {n.image for m in mats if m.node_tree for n in m.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image}
    check_textures(r, sorted(imgs, key=lambda i: i.name), tex_dir)
    r.print()
    return r


def exit_with(report):
    sys.stdout.flush()
    os._exit(1 if report.fail else 0)
