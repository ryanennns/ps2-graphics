"""Open an asset for viewing, with the 3D view split into one panel per camera, in Material Preview.

    Blender path/to/model.blend --python _lib/view.py -- Cam_Store Cam_Interior

With no camera names, it shows the scene camera only.
"""
import sys
import bpy

CAMS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def setup():
    win = bpy.context.window_manager.windows[0]
    scr = win.screen
    views = [a for a in scr.areas if a.type == 'VIEW_3D']
    if not views:
        return 0.5
    cams = [c for c in CAMS if c in bpy.data.objects] or [bpy.context.scene.camera.name]
    for _ in range(len(cams) - 1):
        area = max((a for a in scr.areas if a.type == 'VIEW_3D'), key=lambda a: a.width)
        with bpy.context.temp_override(window=win, screen=scr, area=area):
            bpy.ops.screen.area_split(direction='VERTICAL', factor=0.5)
    views = sorted((a for a in scr.areas if a.type == 'VIEW_3D'), key=lambda a: a.x)
    for a, cam in zip(views, cams):
        sp = a.spaces.active
        sp.shading.type = 'MATERIAL'
        sp.shading.use_scene_lights = True
        sp.shading.use_scene_world = True
        sp.overlay.show_extras = False
        sp.overlay.show_floor = False
        sp.use_local_camera = True
        sp.camera = bpy.data.objects[cam]
        sp.region_3d.view_perspective = 'CAMERA'
        region = [r for r in a.regions if r.type == 'WINDOW'][0]
        with bpy.context.temp_override(window=win, screen=scr, area=a, region=region):
            bpy.ops.view3d.view_center_camera()
    return None


bpy.app.timers.register(setup, first_interval=1.0)
