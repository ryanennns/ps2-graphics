"""Shared shading rules (style.md sections 3 and 5).

- ONE fixed sun for every asset: SUN / SUN_ELEV below. Never override per asset.
- Baked lighting: per-corner vertex colour layer 'Bake' = sun term x ground term.
- One shader for everything: texture x Bake -> Principled, matte unless glass/metal.
"""
import math
import bpy
from mathutils import Vector

# ---------------------------------------------------------------- the shared sun
SUN = Vector((-0.5, -0.85, 0.0)).normalized()  # horizontal direction toward the sun (SSW)
SUN_ELEV = math.radians(35)                     # low sun; used by the preview rig light

UP, DOWN = 1.0, 0.6            # brightness of up (n.z > 0.7) and down (n.z < -0.7) faces
WALL_MIN, WALL_MAX = 0.76, 1.0  # walls: shadow side -> sun side
GROUND_MIN, GROUND_H = 0.84, 2.5  # darken toward ground: x0.84 at z=0 rising to 1.0 at 2.5 m

BAKE_LAYER = 'Bake'
CLASSES = ('concrete', 'glass', 'metal', 'wood')


def srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def sun_term(n):
    hl = math.hypot(n.x, n.y)
    hd = (n.x * SUN.x + n.y * SUN.y) / hl if hl > 1e-6 else 0.0
    wall = WALL_MIN + (WALL_MAX - WALL_MIN) * (hd + 1) / 2
    if n.z > 0.7:
        return UP
    if n.z < -0.7:
        return DOWN
    if n.z > 0.3:
        t = (n.z - 0.3) / 0.4; return wall * (1 - t) + UP * t
    if n.z < -0.3:
        t = (-n.z - 0.3) / 0.4; return wall * (1 - t) + DOWN * t
    return wall


def ground_term(z):
    return GROUND_MIN + (1 - GROUND_MIN) * min(max(z / GROUND_H, 0.0), 1.0)


def brightness(n, z):
    """Final display-space brightness for a corner, clamped to [0, 1]."""
    return min(max(sun_term(n) * ground_term(z), 0.0), 1.0)


def bake(me, smooth):
    """Write the 'Bake' corner colour layer. Mesh must be in world space (object at identity).
    Stored linear so texture(sRGB) x Bake multiplies in display space, like PS2 vertex colour."""
    attr = me.color_attributes.new(BAKE_LAYER, 'FLOAT_COLOR', 'CORNER')
    cols = []
    for p in me.polygons:
        for li in p.loop_indices:
            vi = me.loops[li].vertex_index
            n = me.vertices[vi].normal if smooth else p.normal
            l = srgb_to_lin(brightness(n, me.vertices[vi].co.z))
            cols.extend((l, l, l, 1.0))
    attr.data.foreach_set('color', cols)
    me.color_attributes.active_color = attr
    me.color_attributes.render_color_index = 0


# ---------------------------------------------------------------- material table
def W(tw, th, ou=0.0, ov=0.0):
    """World-tiled mapping: one texture repeat per tw x th metres, origin (ou, ov) along the face axes."""
    return ('w', tw, th, ou, ov)


F = ('f',)  # fit: 0..1 across the face (times a per-face repeat)


def P(origin, R, U, w, h):
    """Planar projection (atlases: vehicle sides, facades): uv = ((p - origin).R / w, (p - origin).U / h).
    One texture spans w x h metres of the plane through `origin` spanned by unit axes R (u) and U (v).
    Faces anywhere on/near that plane sample the same atlas, so seams land where the painting puts them."""
    o, r, u = Vector(origin), Vector(R).normalized(), Vector(U).normalized()
    return ('p', tuple(o), tuple(r), tuple(u), w, h)


def map_uv(mapping, pts, R, U, rep=(1, 1)):
    """UVs for world points `pts` on a face with in-plane axes R (u) and U (v), per material mapping:
    'w' world-tiled along the face axes, 'p' planar projection, 'f' fit the face bbox (x rep)."""
    pts = [Vector(p) for p in pts]
    R, U = Vector(R), Vector(U)
    if mapping[0] == 'w':
        _, tw, th, ou, ov = mapping
        su, sv = R.x + R.y + R.z, U.x + U.y + U.z
        return [((p.dot(R) - ou * su) / tw, (p.dot(U) - ov * sv) / th) for p in pts]
    if mapping[0] == 'p':
        _, o, r, u, w, h = mapping
        o, r, u = Vector(o), Vector(r), Vector(u)
        return [((p - o).dot(r) / w, (p - o).dot(u) / h) for p in pts]
    us = [p.dot(R) for p in pts]; vs = [p.dot(U) for p in pts]
    u0, v0 = min(us), min(vs)
    du, dv = max(max(us) - u0, 1e-9), max(max(vs) - v0, 1e-9)
    return [((a - u0) / du * rep[0], (b - v0) / dv * rep[1]) for a, b in zip(us, vs)]


class MaterialTable(dict):
    """name -> {tex, cls, map}. One entry per material; every material has exactly one class."""

    def add(s, name, texn, cls, mapping):
        assert cls in CLASSES, f"{name}: class must be one of {CLASSES}"
        s[name] = dict(tex=texn, cls=cls, map=mapping)


CLASS_PARAMS = {  # metallic, roughness, specular
    'concrete': (0.0, 1.0, 0.0),
    'wood': (0.0, 1.0, 0.0),
    'metal': (1.0, 1.0, 0.0),
    'glass': (0.0, 0.45, 0.22),
}


def build_materials(table, tex_paths):
    """Create one Blender material per table entry; images are packed into the .blend."""
    out = {}
    for name, d in table.items():
        m = bpy.data.materials.new(name)
        m.use_backface_culling = True
        try:
            m.use_backface_culling_shadow = False
        except AttributeError:
            pass
        nt = m.node_tree
        nt.nodes.clear()
        img = bpy.data.images.load(tex_paths[d['tex']], check_existing=True)
        img.pack()
        ti = nt.nodes.new('ShaderNodeTexImage'); ti.image = img; ti.interpolation = 'Linear'; ti.location = (-600, 200)
        vc = nt.nodes.new('ShaderNodeVertexColor'); vc.layer_name = BAKE_LAYER; vc.location = (-600, -100)
        mx = nt.nodes.new('ShaderNodeMix'); mx.data_type = 'RGBA'; mx.blend_type = 'MULTIPLY'; mx.location = (-300, 100)
        mx.inputs[0].default_value = 1.0
        a = [i for i in mx.inputs if i.name == 'A' and i.type == 'RGBA'][0]
        b = [i for i in mx.inputs if i.name == 'B' and i.type == 'RGBA'][0]
        res = [o for o in mx.outputs if o.type == 'RGBA'][0]
        bs = nt.nodes.new('ShaderNodeBsdfPrincipled'); bs.location = (0, 100)
        o = nt.nodes.new('ShaderNodeOutputMaterial'); o.location = (300, 100)
        nt.links.new(ti.outputs['Color'], a)
        nt.links.new(vc.outputs['Color'], b)
        nt.links.new(res, bs.inputs['Base Color'])
        nt.links.new(bs.outputs['BSDF'], o.inputs['Surface'])
        met, rough, spec = CLASS_PARAMS[d['cls']]
        bs.inputs['Metallic'].default_value = met
        bs.inputs['Roughness'].default_value = rough
        bs.inputs['Specular IOR Level'].default_value = spec
        m['style_class'] = d['cls']
        out[name] = m
    return out
