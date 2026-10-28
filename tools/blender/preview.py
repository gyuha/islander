"""Render a 512x512 QA preview of a glb. Run:
blender -b --factory-startup -P tools/blender/preview.py -- <input.glb> <output.png> [front]

Default view is a 3/4 camera; the optional "front" view looks straight at -Y
(Godot +Z, the front of the character). Imports the glb into an empty scene, adds a sun and a soft world light, and
renders from a 3/4 camera framing the bounding box with Eevee.
"""

import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(argv) not in (2, 3) or (len(argv) == 3 and argv[2] != "front"):
        raise SystemExit("usage: preview.py -- <input.glb> <output.png> [front]")
    return Path(argv[0]).resolve(), Path(argv[1]).resolve(), len(argv) == 3


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def world_bounds(objects):
    points = []
    for obj in objects:
        if obj.type == "MESH":
            points.extend(obj.matrix_world @ v.co for v in obj.data.vertices)
    lo = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    hi = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return lo, hi


def eevee_engine_name():
    items = bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items.keys()
    for name in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        if name in items:
            return name
    raise SystemExit(f"no Eevee engine found in {items}")


def main():
    glb_path, png_path, front = parse_args()
    clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(glb_path))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    lo, hi = world_bounds(meshes)
    center = (lo + hi) / 2
    radius = (hi - lo).length / 2

    scene = bpy.context.scene
    scene.render.engine = eevee_engine_name()
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"

    world = bpy.data.worlds.new("PreviewWorld")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.55, 0.78, 0.80, 1.0)
    bg.inputs["Strength"].default_value = 0.9
    scene.world = world

    sun_data = bpy.data.lights.new("PreviewSun", type="SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("PreviewSun", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(50), 0, math.radians(-30))

    # Camera in 3/4 view: front of the model is Blender -Y (Godot +Z).
    direction = Vector((0.0, -1.0, 0.08) if front else (0.75, -0.75, 0.55)).normalized()
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.lens_unit = "FOV"
    cam_data.angle = math.radians(30)
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    scene.collection.objects.link(cam)
    distance = radius / math.tan(cam_data.angle / 2) * 1.15
    cam.location = center + direction * distance
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam

    png_path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(png_path)
    bpy.ops.render.render(write_still=True)
    print(f"PREVIEW_WRITTEN {png_path}")


if __name__ == "__main__":
    main()
