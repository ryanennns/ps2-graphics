"""Mesh building in world-space metres: boxes, prisms, quads with world-tiled or fit UVs,
flat shading and the shared baked lighting. Plus scene helpers (reset, collections, tri counts)."""
import math
import bpy
from mathutils import Vector

from .shading import bake

FACES = {  # face key: (right R, up U) with R x U = outward normal
    '+x': ((0, 1, 0), (0, 0, 1)), '-x': ((0, -1, 0), (0, 0, 1)),
    '+y': ((-1, 0, 0), (0, 0, 1)), '-y': ((1, 0, 0), (0, 0, 1)),
    '+z': ((1, 0, 0), (0, 1, 0)), '-z': ((1, 0, 0), (0, -1, 0)),
}


class MB:
    """Accumulates faces for one object. `table` is the asset's MaterialTable (for UV mapping).
    smooth=True only for organic forms (foliage, terrain, characters)."""

    def __init__(s, name, coll, table, smooth=False):
        s.name, s.coll, s.table, s.smooth = name, coll, table, smooth
        s.verts, s.faces, s.uvs, s.fmat = [], [], [], []

    def poly(s, pts, mat, uvs):
        base = len(s.verts)
        s.verts.extend(pts)
        s.faces.append(list(range(base, base + len(pts))))
        s.uvs.append(uvs)
        s.fmat.append(mat)

    def quad(s, o, R, U, w, h, mat, rep=(1, 1)):
        o, R, U = Vector(o), Vector(R), Vector(U)
        pts = [o, o + R * w, o + R * w + U * h, o + U * h]
        mp = s.table[mat]['map']
        if mp[0] == 'w':
            _, tw, th, ou, ov = mp
            su, sv = R.x + R.y + R.z, U.x + U.y + U.z
            uvs = [((p.dot(R) - ou * su) / tw, (p.dot(U) - ov * sv) / th) for p in pts]
        else:
            uvs = [(0, 0), (rep[0], 0), (rep[0], rep[1]), (0, rep[1])]
        s.poly([tuple(p) for p in pts], mat, uvs)

    def box(s, x0, y0, z0, x1, y1, z1, mats, skip=(), rep=None):
        """mats: str, or dict keyed by face ('+x', ...) with optional 'side'/'default'.
        skip: faces that can never be seen (against walls, floors, other solids)."""
        rep = rep or {}
        for f, (R, U) in FACES.items():
            if f in skip:
                continue
            if isinstance(mats, str):
                mat = mats
            else:
                mat = mats.get(f) or (mats.get('side') if f[1] in 'xy' else None) or mats.get('default')
            if mat is None:
                continue
            if f == '+x': o, w, h = (x1, y0, z0), y1 - y0, z1 - z0
            elif f == '-x': o, w, h = (x0, y1, z0), y1 - y0, z1 - z0
            elif f == '+y': o, w, h = (x1, y1, z0), x1 - x0, z1 - z0
            elif f == '-y': o, w, h = (x0, y0, z0), x1 - x0, z1 - z0
            elif f == '+z': o, w, h = (x0, y0, z1), x1 - x0, y1 - y0
            else: o, w, h = (x0, y1, z0), x1 - x0, y1 - y0
            s.quad(o, R, U, w, h, mat, rep.get(f, (1, 1)))

    def prism(s, cx, cy, r, z0, z1, n, mat, cap=True, top_mat=None, phase=0.0):
        """n-sided vertical prism (6-8 sides for poles/columns/trunks)."""
        mp = s.table[mat]['map']
        tw = mp[1] if mp[0] == 'w' else 2 * math.pi * r
        th = mp[2] if mp[0] == 'w' else (z1 - z0)
        pts = [(cx + r * math.cos(phase + 2 * math.pi * i / n), cy + r * math.sin(phase + 2 * math.pi * i / n)) for i in range(n)]
        seg = 2 * r * math.sin(math.pi / n)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            u0, u1 = i * seg / tw, (i + 1) * seg / tw
            s.poly([(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)], mat,
                   [(u0, z0 / th), (u1, z0 / th), (u1, z1 / th), (u0, z1 / th)])
        if cap:
            tm = top_mat or mat
            t = s.table[tm]['map']
            ts = t[1] if t[0] == 'w' else 2 * r
            s.poly([(p[0], p[1], z1) for p in pts], tm, [(p[0] / ts, p[1] / ts) for p in pts])

    def build(s, mats):
        """Create the object: materials, UVs, flat/smooth shading, baked 'Bake' layer."""
        me = bpy.data.meshes.new(s.name)
        me.from_pydata(s.verts, [], s.faces)
        names = sorted(set(s.fmat), key=s.fmat.index)
        for n in names:
            me.materials.append(mats[n])
        idx = {n: i for i, n in enumerate(names)}
        me.polygons.foreach_set('material_index', [idx[m] for m in s.fmat])
        uvl = me.uv_layers.new(name='UVMap')
        flat = [uv for f in s.uvs for uv in f]
        uvl.data.foreach_set('uv', [c for uv in flat for c in uv])
        me.update()
        if s.smooth:
            me.shade_smooth()
        else:
            me.shade_flat()
        bake(me, s.smooth)
        ob = bpy.data.objects.new(s.name, me)
        ob['organic'] = bool(s.smooth)
        s.coll.objects.link(ob)
        return ob


# ---------------------------------------------------------------- scene helpers
def reset_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras,
                bpy.data.images, bpy.data.worlds):
        for x in list(blk):
            blk.remove(x)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def coll(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def report_tris(objs):
    total = 0
    for o in objs:
        t = tri_count(o); total += t
        print(f"TRIS {o.name:22s} {t}")
    print("TRIS TOTAL", total)
    return total


def save(path):
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    print("SAVED", path)
