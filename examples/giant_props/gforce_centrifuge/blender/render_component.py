"""Component render harness for worker/critic loops.

Usage (each worker runs this after editing its module):

    & 'C:/Users/ericr/Applications/Blender/4.5.4/blender.exe' \
        --factory-startup --background \
        --python examples/giant_props/gforce_centrifuge/blender/render_component.py \
        -- <component_name>

Imports ``components/<component_name>.py``, calls its ``build(materials)``
(which must return a list of Blender objects), then renders three PNG views
to ``blender/component_renders/<component_name>_{front,three_quarter,top}.png``.
Deterministic: fixed camera, sun, and film settings.
"""

from __future__ import annotations

import importlib
import math
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
BLENDER_ROOT = SCRIPT_PATH.parent
EXAMPLE_ROOT = BLENDER_ROOT.parent
PACK_ROOT = EXAMPLE_ROOT.parent
sys.path.insert(0, str(PACK_ROOT))
sys.path.insert(0, str(EXAMPLE_ROOT))
sys.path.insert(0, str(BLENDER_ROOT))

import bpy  # noqa: E402

import spec  # noqa: E402
from proplib import blender_kit as bk  # noqa: E402

component_name = sys.argv[sys.argv.index("--") + 1]
module = importlib.import_module(f"components.{component_name}")

bk.reset_scene()
materials = bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")
objects = module.build(materials)
if not objects:
    raise SystemExit("component build() returned no objects")

# Fit the camera to the component bounds.
xs, ys, zs = [], [], []
for obj in objects:
    for corner in obj.bound_box:
        world = obj.matrix_world @ __import__("mathutils").Vector(corner)
        xs.append(world.x)
        ys.append(world.y)
        zs.append(world.z)
cx, cy, cz = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2
extent = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1.0)

sun_data = bpy.data.lights.new("sun", "SUN")
sun_data.energy = 3.2
sun = bpy.data.objects.new("sun", sun_data)
bpy.context.scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(50), 0.0, math.radians(35))
fill_data = bpy.data.lights.new("fill", "SUN")
fill_data.energy = 0.9
fill = bpy.data.objects.new("fill", fill_data)
bpy.context.scene.collection.objects.link(fill)
fill.rotation_euler = (math.radians(60), 0.0, math.radians(-120))
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.7, 0.78, 0.86, 1.0)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.7
bpy.context.scene.world = world

camera_data = bpy.data.cameras.new("cam")
camera = bpy.data.objects.new("cam", camera_data)
bpy.context.scene.collection.objects.link(camera)
bpy.context.scene.camera = camera
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.resolution_x = 1100
scene.render.resolution_y = 700
scene.render.filepath = ""

out_dir = BLENDER_ROOT / "component_renders"
out_dir.mkdir(exist_ok=True)

VIEWS = {
    "front": (0.0, -2.1, 0.5),
    "three_quarter": (1.5, -1.5, 0.85),
    "top": (0.35, -0.35, 2.4),
}
for view_name, (ux, uy, uz) in VIEWS.items():
    distance = extent * 1.15
    camera.location = (cx + ux * distance, cy + uy * distance, cz + uz * distance)
    direction = __import__("mathutils").Vector((cx, cy, cz)) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(out_dir / f"{component_name}_{view_name}.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", scene.render.filepath)
print("COMPONENT RENDER DONE", component_name, "objects:", len(objects))
