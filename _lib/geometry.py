"""Mesh building in world-space metres: boxes, prisms, quads, arbitrary polygons (auto-wound by
Newell normal), extrusions, lofts and tubes on any axis, with world-tiled / fit / projected UVs,
flat shading (smooth + welded for organic forms) and the shared baked lighting.
Plus scene helpers (reset, collections, tri counts, origins)."""
import math
import bpy
from mathutils import Vector, Matrix

from .shading import bake, map_uv

def newell(pts):
    """Newell normal (unnormalized; length = 2 x area) of a planar-ish polygon."""
    n = Vector((0.0, 0.0, 0.0))
    for i, a in enumerate(pts):
        b = pts[(i + 1) % len(pts)]
        n.x += (a[1] - b[1]) * (a[2] + b[2])
        n.y += (a[2] - b[2]) * (a[0] + b[0])
        n.z += (a[0] - b[0]) * (a[1] + b[1])
    return n


def face_axes(n):
    """In-plane texture axes (R, U) for unit normal n with R x U = n, matching box() faces:
    walls get U = up; up/down faces get R = +x."""
    n = Vector(n).normalized()
    if abs(n.z) < 0.7:
        U = (Vector((0, 0, 1)) - n * n.z).normalized()
    else:
        U = (Vector((0, 1 if n.z > 0 else -1, 0)) - n * (n.y if n.z > 0 else -n.y)).normalized()
    R = U.cross(n).normalized()
    return R, U


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

    # ------------------------------------------------------------ general polygons
    def face(s, pts, mat, out=None, uv=None, rep=(1, 1), R=None, U=None):
        """Add one polygon (3+ world points). out: a direction the face must point along (the
        winding is flipped if needed; omit to keep the given order). uv: list of (u, v), or a
        callable p -> (u, v); default is the material's mapping (W world-tiled along the face axes,
        P planar projection, F fit to the face bbox x rep). Returns False for degenerate input."""
        pts = [tuple(float(c) for c in p) for p in pts]
        n = newell(pts)
        if n.length < 1e-12:
            return False
        if uv is not None and not callable(uv):
            uv = list(uv)
        if out is not None and n.dot(Vector(out)) < 0:
            pts = pts[::-1]
            n = -n
            if isinstance(uv, list):
                uv = uv[::-1]
        if callable(uv):
            uvs = [tuple(uv(p)) for p in pts]
        elif uv is not None:
            uvs = [tuple(t) for t in uv]
        else:
            if R is None or U is None:
                R, U = face_axes(n)
            uvs = map_uv(s.table[mat]['map'], pts, R, U, rep)
        s.poly(pts, mat, uvs)
        return True

    def extrude(s, outline, z0, z1, side, top=None, bottom=None, rep=(1, 1)):
        """Vertical extrusion of a 2D outline [(x, y), ...] (either winding) from z0 to z1.
        Sides use `side` (world-tiled maps run continuously around the perimeter); top/bottom
        caps are added only if given (leave bottom None on the ground: it can never be seen)."""
        pts = [(float(x), float(y)) for x, y in outline]
        area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
        if area < 0:
            pts = pts[::-1]
        mp = s.table[side]['map']
        cum = 0.0
        for a, b in zip(pts, pts[1:] + pts[:1]):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L < 1e-9:
                continue
            q = [(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)]
            if mp[0] == 'w':
                _, tw, th, ou, ov = mp
                uvs = [((cum - ou) / tw, (z0 - ov) / th), ((cum + L - ou) / tw, (z0 - ov) / th),
                       ((cum + L - ou) / tw, (z1 - ov) / th), ((cum - ou) / tw, (z1 - ov) / th)]
                s.poly(q, side, uvs)
            else:
                s.face(q, side, rep=rep)
            cum += L
        if top:
            s.face([(x, y, z1) for x, y in pts], top, out=(0, 0, 1))
        if bottom:
            s.face([(x, y, z0) for x, y in pts], bottom, out=(0, 0, -1))

    def loft(s, rings, mat, cap0=None, cap1=None, rep=(1, 1), closed=True):
        """Skin consecutive rings (lists of the same number of world points) with quads.
        Winding is chosen so faces point away from the rings' centre line. World-tiled maps run
        around (u, arc length) and along (v, distance between ring centres); fit maps span the
        whole loft x rep. cap0/cap1: material for the first/last ring cap (None = open)."""
        rings = [[Vector(p) for p in r] for r in rings]
        n, m = len(rings[0]), len(rings)
        cen = [sum(r, Vector()) / n for r in rings]
        segs = n if closed else n - 1
        vote = 0.0
        for j in range(m - 1):
            mid = (cen[j] + cen[j + 1]) / 2
            for i in range(segs):
                a, b = rings[j][i], rings[j][(i + 1) % n]
                c, d = rings[j + 1][(i + 1) % n], rings[j + 1][i]
                vote += newell([a, b, c, d]).dot((a + b + c + d) / 4 - mid)
        flip = vote < 0
        mp = s.table[mat]['map']
        vcum = [0.0]
        for j in range(1, m):
            vcum.append(vcum[-1] + (cen[j] - cen[j - 1]).length)
        for j in range(m - 1):
            ucum = [0.0]
            for i in range(segs):
                ucum.append(ucum[-1] + (rings[j][(i + 1) % n] - rings[j][i]).length)
            for i in range(segs):
                q = [rings[j][i], rings[j][(i + 1) % n], rings[j + 1][(i + 1) % n], rings[j + 1][i]]
                if mp[0] == 'w':
                    tw, th = mp[1], mp[2]
                    uv = [(ucum[i] / tw, vcum[j] / th), (ucum[i + 1] / tw, vcum[j] / th),
                          (ucum[i + 1] / tw, vcum[j + 1] / th), (ucum[i] / tw, vcum[j + 1] / th)]
                elif mp[0] == 'f':
                    uv = [(i / segs * rep[0], j / (m - 1) * rep[1]), ((i + 1) / segs * rep[0], j / (m - 1) * rep[1]),
                          ((i + 1) / segs * rep[0], (j + 1) / (m - 1) * rep[1]), (i / segs * rep[0], (j + 1) / (m - 1) * rep[1])]
                else:
                    uv = map_uv(mp, q, Vector((1, 0, 0)), Vector((0, 0, 1)))
                if flip:
                    q, uv = q[::-1], uv[::-1]
                s.poly([tuple(p) for p in q], mat, uv)
        if cap0:
            s.face([tuple(p) for p in rings[0]], cap0, out=cen[0] - cen[1])
        if cap1:
            s.face([tuple(p) for p in rings[-1]], cap1, out=cen[-1] - cen[-2])

    def tube(s, path, r, n, mat, cap=True, cap_mat=None, phase=0.0, rep=(1, 1)):
        """n-sided tube along a polyline `path` of world points (any direction: wheels, axles,
        rails, branches, statue limbs). r: radius, or one radius per path point.
        Ring frames are parallel-transported, so tubes do not twist."""
        path = [Vector(p) for p in path]
        rs = list(r) if isinstance(r, (list, tuple)) else [r] * len(path)
        tans = []
        for j in range(len(path)):
            t = path[min(j + 1, len(path) - 1)] - path[max(j - 1, 0)]
            tans.append(t.normalized())
        ref = Vector((0, 0, 1)) if abs(tans[0].z) < 0.9 else Vector((1, 0, 0))
        nrm = (ref - tans[0] * ref.dot(tans[0])).normalized()
        rings = []
        for j, (p, t) in enumerate(zip(path, tans)):
            if j:
                nrm = (nrm - t * nrm.dot(t)).normalized()
            bi = t.cross(nrm)
            rings.append([p + (nrm * math.cos(phase + 2 * math.pi * i / n) + bi * math.sin(phase + 2 * math.pi * i / n)) * rs[j]
                          for i in range(n)])
        cm = (cap_mat or mat) if cap else None
        s.loft(rings, mat, cm, cm, rep)

    def cylinder(s, a, b, r, n, mat, cap=True, cap_mat=None, phase=0.0, rep=(1, 1)):
        """n-sided cylinder from point a to point b (e.g. a wheel: a/b = inner/outer hub centres)."""
        s.tube([a, b], r, n, mat, cap, cap_mat, phase, rep)

    # ------------------------------------------------------------ placement of what was added
    def mark(s):
        """Bookmark (vertex count, face count); pass to transform()/mirror() to act on later parts."""
        return (len(s.verts), len(s.faces))

    def transform(s, tx=0.0, ty=0.0, tz=0.0, angle=0.0, origin=(0.0, 0.0), start=(0, 0)):
        """Rotate (about the vertical axis through origin, radians) then translate the vertices
        added since `start` (a mark()). Build a prop once at the origin, then place it."""
        c, sn = math.cos(angle), math.sin(angle)
        ox, oy = origin
        for i in range(start[0], len(s.verts)):
            x, y, z = s.verts[i]
            x, y = x - ox, y - oy
            s.verts[i] = (ox + c * x - sn * y + tx, oy + sn * x + c * y + ty, z + tz)

    def mirror(s, axis='x', about=0.0, start=(0, 0)):
        """Add a mirrored copy (across the plane axis = about) of the faces added since `start`.
        Winding is reversed so the copy still faces outward; UVs are kept (painted lettering
        will read backwards on the copy: give it its own material if that matters)."""
        k = 'xyz'.index(axis)
        for fi in range(start[1], len(s.faces)):
            pts = []
            for vi in s.faces[fi]:
                p = list(s.verts[vi]); p[k] = 2 * about - p[k]; pts.append(tuple(p))
            s.poly(pts[::-1], s.fmat[fi], list(s.uvs[fi])[::-1])

    def build(s, mats):
        """Create the object: materials, UVs, flat/smooth shading, baked 'Bake' layer.
        smooth=True (organic) welds coincident vertices first so normals really are smooth."""
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
            weld(me)
            me.shade_smooth()
        else:
            me.shade_flat()
        bake(me, s.smooth)
        ob = bpy.data.objects.new(s.name, me)
        ob['organic'] = bool(s.smooth)
        s.coll.objects.link(ob)
        return ob


def weld(me, dist=1e-5):
    """Merge coincident vertices (keeps per-corner UVs and material indices)."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=dist)
    bm.to_mesh(me)
    bm.free()
    me.update()


# ---------------------------------------------------------------- scene helpers
def reset_scene():
    """Empty the file for a fresh build (objects, meshes, curves, fonts, materials, node groups,
    lights, cameras, images, worlds, actions, collections, and any extra scenes)."""
    keep = bpy.context.scene
    for sc in list(bpy.data.scenes):
        if sc != keep:
            bpy.data.scenes.remove(sc)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for blk in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.node_groups,
                bpy.data.lights, bpy.data.cameras, bpy.data.images, bpy.data.worlds, bpy.data.actions):
        for x in list(blk):
            blk.remove(x)
    for f in list(bpy.data.fonts):
        if f.users == 0:
            bpy.data.fonts.remove(f)
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


def place_origin(ob, mode='bottom_centre'):
    """Move an object's origin without moving its (already baked, world-space) geometry, e.g. to
    make reusable props easy to place. mode: 'bottom_centre' or 'centre'. Translation only."""
    co = [v.co.copy() for v in ob.data.vertices]
    mn = Vector([min(v[i] for v in co) for i in range(3)])
    mx = Vector([max(v[i] for v in co) for i in range(3)])
    o = (mn + mx) / 2
    if mode == 'bottom_centre':
        o.z = mn.z
    ob.data.transform(Matrix.Translation(-o))
    ob.location = ob.location + o
    return o


def save(path):
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    print("SAVED", path)
