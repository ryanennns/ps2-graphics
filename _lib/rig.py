"""Standard preview rig (style.md section 7), identical for every asset:
soft low-energy sun along the shared SUN, flat pale-blue sky, 32 mm lens, 900x600,
4 cardinal eye-level shots at 45% of asset height from max(18 m, 1.25 x bbox diagonal),
one 3/4 aerial, plus a steep top shot for assets over 35 m tall.

The rig lives in its own collection, which is not part of the asset. Calling setup() again replaces it.
"""
import math, os
import bpy
from mathutils import Vector

from .shading import SUN, SUN_ELEV

RIG_COLL = "_PreviewRig (not part of asset)"
STANDARD = ("Cam_S", "Cam_N", "Cam_E", "Cam_W", "Cam_Aerial34")


def _remove_rig():
    c = bpy.data.collections.get(RIG_COLL)
    if c:
        for o in list(c.objects):
            data = o.data
            bpy.data.objects.remove(o)
            if data is not None and data.users == 0:
                (bpy.data.cameras if isinstance(data, bpy.types.Camera) else bpy.data.lights).remove(data)
        bpy.data.collections.remove(c)


def add_cam(C, name, loc, target, lens=32):
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    cam.clip_end = 500
    o = bpy.data.objects.new(name, cam)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    C.objects.link(o)
    return o


def asset_bounds(asset_root):
    mn = Vector((1e9,) * 3); mx = Vector((-1e9,) * 3)
    for o in asset_root.all_objects:
        if o.type != 'MESH':
            continue
        for v in o.data.vertices:
            w = o.matrix_world @ v.co
            for i in range(3):
                mn[i] = min(mn[i], w[i]); mx[i] = max(mx[i], w[i])
    return mn, mx


def viewport_defaults():
    """Material Preview using the scene sun/sky, so opening the .blend matches the previews."""
    for scr in bpy.data.screens:
        for area in scr.areas:
            if area.type == 'VIEW_3D':
                sp = area.spaces.active
                sp.shading.type = 'MATERIAL'
                sp.shading.use_scene_lights = True
                sp.shading.use_scene_world = True
                sp.clip_end = 1000
                sp.overlay.show_floor = False
                sp.overlay.show_extras = False


def setup(asset_root, extra_cams=(), default_cam=None):
    """asset_root: the asset's top collection. extra_cams: (name, loc, target, lens) review shots.
    Returns the camera names, standard ones first."""
    _remove_rig()
    sc = bpy.context.scene
    C = bpy.data.collections.new(RIG_COLL)
    sc.collection.children.link(C)

    sun = bpy.data.lights.new("PreviewSun", 'SUN')
    sun.energy = 2.2
    sun.angle = math.radians(25)
    so = bpy.data.objects.new("PreviewSun", sun)
    d = Vector((SUN.x * math.cos(SUN_ELEV), SUN.y * math.cos(SUN_ELEV), math.sin(SUN_ELEV)))
    so.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    C.objects.link(so)

    w = bpy.data.worlds.get("PaleSky") or bpy.data.worlds.new("PaleSky")
    w.use_nodes = True
    bg = w.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (0.50, 0.61, 0.76, 1)
    bg.inputs['Strength'].default_value = 0.9
    sc.world = w
    sc.render.engine = 'BLENDER_EEVEE'
    sc.render.resolution_x, sc.render.resolution_y = 900, 600
    sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = 'Standard'

    mn, mx = asset_bounds(asset_root)
    ctr = (mn + mx) / 2
    diag = (mx - mn).length
    dist = max(18, 1.25 * diag)
    height = mx.z - max(mn.z, 0)
    eye = 0.45 * height
    names = []
    for name, dv in (("Cam_S", (0, -1)), ("Cam_N", (0, 1)), ("Cam_E", (1, 0)), ("Cam_W", (-1, 0))):
        add_cam(C, name, (ctr.x + dv[0] * dist, ctr.y + dv[1] * dist, eye), (ctr.x, ctr.y, eye))
        names.append(name)
    add_cam(C, "Cam_Aerial34", (ctr.x - dist * 0.6, ctr.y - dist * 0.6, dist * 0.55), (ctr.x, ctr.y, 0))
    names.append("Cam_Aerial34")
    if height > 35:
        add_cam(C, "Cam_Top", (ctr.x - dist * 0.2, ctr.y - dist * 0.2, dist * 1.1), (ctr.x, ctr.y, 0))
        names.append("Cam_Top")
    for name, loc, target, lens in extra_cams:
        add_cam(C, name, loc, target, lens)
        names.append(name)
    sc.camera = bpy.data.objects[default_cam or "Cam_Aerial34"]
    viewport_defaults()
    print(f"RIG dist {dist:.1f} eye {eye:.2f} diag {diag:.1f} cams {len(names)}")
    return names


def render(names, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    sc = bpy.context.scene
    keep = sc.camera
    for name in names:
        sc.camera = bpy.data.objects[name]
        sc.render.filepath = os.path.join(out_dir, name + ".png")
        bpy.ops.render.render(write_still=True)
        print("RENDERED", name)
    sc.camera = keep
