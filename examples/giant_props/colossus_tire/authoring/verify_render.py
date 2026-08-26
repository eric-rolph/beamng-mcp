"""Multi-view verification render for COLOSSUS 10350/80R457.

Rebuilds the generator's scene and renders a fixed set of cameras into
``authoring/verify/``. These are the images design rounds are judged from,
so the camera list is authored and stable: same frames every run, so two
rounds can actually be compared.

    & $blender454 --factory-startup --background \
        --python examples/giant_props/colossus_tire/authoring/verify_render.py

Add ``-- --only <name>`` to render one view while iterating.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
EXAMPLE_ROOT = SCRIPT_PATH.parents[1]
PACK_ROOT = EXAMPLE_ROOT.parent
sys.path.insert(0, str(PACK_ROOT))
sys.path.insert(0, str(EXAMPLE_ROOT))
sys.path.insert(0, str(EXAMPLE_ROOT / "blender"))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import spec  # noqa: E402
import create_colossus_tire as gen  # noqa: E402
from proplib import blender_kit as bk  # noqa: E402

OUT = EXAMPLE_ROOT / "authoring" / "verify"

# (name, camera, look_at, lens, resolution)
_BAND_ANGLE = math.radians(68.9)          # up and to the left of the axle
_BAND_STANDOFF = (9.0, 1.5, 1.0)          # camera offset from the target


def _band_target(name: str) -> tuple[float, float, float]:
    radius = next(r for entry, r, _h in spec.BAND_STACK if entry == name)
    return (
        2.0,
        radius * math.sin(_BAND_ANGLE),
        spec.OUTER_RADIUS - radius * math.cos(_BAND_ANGLE),
    )


def _band_camera(name: str) -> tuple[float, float, float]:
    target = _band_target(name)
    return tuple(target[i] + _BAND_STANDOFF[i] for i in range(3))


# THE FEATURE CAMERAS HAVE TO LOOK AT THEIR FEATURES. Round 4 found the
# "buttress" frame aimed at radius 9.363, |x| 2.4 - which is 2.7 m INSIDE the
# sidewall at the size-code band - while the wrap lives at radius 11.61-13.51,
# |x| 4.61-5.29, and "shoulder" aimed at radius 10.935 against a shoulder at
# 13.23-13.31. Both features had shipped defects for three rounds and no image
# in authoring/verify/ contained either of them. A named view now derives its
# look-at from the thing it is named for, and a gate checks the arithmetic.
FEATURES = {
    # name: (radius, axial, viewing angle round the tire, standoff)
    "shoulder": (
        spec.OUTER_RADIUS - spec.SECTION_HEIGHT * (1.0 - spec.SHL_FRACTION),
        spec.TREAD_HALF + 0.45,
        math.radians(115.0),
        7.0,
    ),
    "buttress": (
        0.5 * (spec.PROTECTOR_RADII[0] + spec.PROTECTOR_RADII[-1]),
        spec.SECTION_HALF - 0.30,
        math.radians(100.0),
        8.5,
    ),
    "bead": (
        spec.BEAD_RADIUS + 0.35,
        spec.SECTION_HALF * 0.86,
        math.radians(140.0),
        6.0,
    ),
}


def _feature_target(name: str) -> tuple[float, float, float]:
    radius, axial, angle, _standoff = FEATURES[name]
    return (
        axial,
        radius * math.sin(angle),
        spec.OUTER_RADIUS - radius * math.cos(angle),
    )


def _feature_camera(name: str) -> tuple[float, float, float]:
    radius, axial, angle, standoff = FEATURES[name]
    # Outboard and out along the radius, a little further round the clock, so
    # the feature is seen across its own curvature rather than end-on.
    swing = angle + math.radians(-12.0)
    reach = radius + standoff
    return (
        axial + standoff * 0.85,
        reach * math.sin(swing),
        spec.OUTER_RADIUS - reach * math.cos(swing),
    )


VIEWS = (
    ("hero", (40.0, -46.0, 20.0), (0.0, 0.0, 13.0), 42.0, (1000, 620)),
    ("profile", (2.0, -62.0, 14.0), (0.0, 0.0, 14.0), 55.0, (1000, 620)),
    ("face", (34.0, 0.0, 14.0), (0.0, 0.0, 14.0), 46.0, (1000, 1000)),
    ("tread_close", (1.2, -13.0, 25.6), (0.0, -2.0, 25.0), 70.0, (1000, 700)),
    ("shoulder", _feature_camera("shoulder"), _feature_target("shoulder"), 52.0, (1000, 700)),
    ("buttress", _feature_camera("buttress"), _feature_target("buttress"), 52.0, (1000, 700)),
    ("bead", _feature_camera("bead"), _feature_target("bead"), 50.0, (1000, 700)),
    ("sidewall_type", _band_camera("SIZE_CODE"), _band_target("SIZE_CODE"), 55.0, (1000, 700)),
    ("sidewall_print", _band_camera("PRINT_BAND"), _band_target("PRINT_BAND"), 55.0, (1000, 700)),
    ("chocks", (11.0, 13.5, 4.2), (0.0, 6.0, 1.0), 42.0, (1000, 700)),
    ("contact", (9.0, -11.0, 2.4), (0.0, -2.0, 0.7), 40.0, (1000, 620)),
    ("scale", (26.0, -52.0, 3.2), (2.0, -4.0, 8.0), 50.0, (1000, 620)),
    ("underside", (16.0, -20.0, 1.0), (1.0, 0.0, 1.4), 40.0, (1000, 620)),
    # THE DRIVER'S FRAME. Round 4's worst pixel defect lived on the liner and
    # round 5 found the surface shipping visually unreviewed: no exterior
    # view can see the one surface the hamster mode is driven on. Lit by the
    # render-only cabin lamp; in game this space is honestly dark until a car
    # brings headlights.
    ("cavity", (0.0, -5.0, 2.4), (0.0, 9.0, 5.2), 30.0, (1000, 700)),
    # Straight at a climb face: the hazard stripes and the side-plate band.
    # The old stripe decals were invisible from EVERY authored angle, which
    # is how sixteen inward-wound triangles survived four review rounds.
    ("chock_face", (5.9, -8.2, 3.4), (2.7, -2.9, 0.3), 42.0, (1000, 700)),
)


def scene() -> None:
    bk.reset_scene()
    materials = bk.materials_from_palette(
        spec, EXAMPLE_ROOT / "textures", preview_emission=True
    )
    # Every builder main() calls, in the same order. A frame that is missing
    # a builder is a frame that cannot review it, and the lane chevrons went a
    # whole round unreviewed because this list had drifted from main()'s - and
    # then the small-print ring went a whole round the same way, judged in
    # renders it was never in. tests/test_colossus_tire_geometry.py now
    # compares the two lists, because a comment saying "keep these in sync"
    # has now failed twice.
    gen.build_carcass(materials)
    gen.build_tread(materials)
    gen.build_print_band(materials)
    gen.build_lettering(materials)
    gen.build_chocks(materials)

    # BACKFACE CULLING ON, everywhere. BeamNG culls flexbody backfaces; EEVEE
    # does not unless told to, and that difference is exactly why round 1's
    # renders looked correct while every carcass surface was wound inside out.
    # A verification render that is more forgiving than the engine is not a
    # verification render.
    for material in bpy.data.materials:
        material.use_backface_culling = True

    ground = bpy.data.meshes.new("ground")
    ground.from_pydata(
        [(-90, -90, 0), (90, -90, 0), (90, 90, 0), (-90, 90, 0)], [], [(0, 1, 2, 3)]
    )
    ground.update()
    obj = bpy.data.objects.new("ground", ground)
    bpy.context.scene.collection.objects.link(obj)
    material = bk.material("verify_ground", (0.30, 0.29, 0.27, 1.0), roughness=0.95)
    obj.data.materials.append(material)


def light() -> None:
    world = bpy.data.worlds.new("verify_world")
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs[0].default_value = (0.42, 0.52, 0.66, 1.0)
        background.inputs[1].default_value = 1.0
    bpy.context.scene.world = world

    key = bpy.data.lights.new("key", "SUN")
    key.energy = 3.1
    key.angle = math.radians(1.2)
    key_obj = bpy.data.objects.new("key", key)
    bpy.context.scene.collection.objects.link(key_obj)
    key_obj.rotation_euler = Vector((-0.55, 0.30, -1.0)).to_track_quat("-Z", "Y").to_euler()

    # A work lamp inside the carcass. The cavity of a 28 m tire is genuinely
    # dark and an honest render of it is a black rectangle, which cannot be
    # reviewed. Render-only.
    lamp = bpy.data.lights.new("cabin_lamp", "AREA")
    lamp.energy = 45.0
    lamp.size = 6.0
    lamp_obj = bpy.data.objects.new("cabin_lamp", lamp)
    bpy.context.scene.collection.objects.link(lamp_obj)
    lamp_obj.location = (0.0, 0.0, 6.5)
    lamp_obj.rotation_euler = (math.pi, 0.0, 0.0)

    fill = bpy.data.lights.new("fill", "SUN")
    fill.energy = 1.1
    fill_obj = bpy.data.objects.new("fill", fill)
    bpy.context.scene.collection.objects.link(fill_obj)
    fill_obj.rotation_euler = Vector((0.8, -0.6, -0.7)).to_track_quat("-Z", "Y").to_euler()


def render(name, location, look_at, lens, resolution) -> None:
    scene_data = bpy.context.scene
    camera_data = bpy.data.cameras.new(f"cam_{name}")
    camera_data.lens = lens
    camera = bpy.data.objects.new(f"cam_{name}", camera_data)
    scene_data.collection.objects.link(camera)
    camera.location = location
    direction = Vector(look_at) - Vector(location)
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene_data.camera = camera
    scene_data.render.engine = "BLENDER_EEVEE_NEXT"
    scene_data.render.resolution_x, scene_data.render.resolution_y = resolution
    scene_data.render.image_settings.file_format = "JPEG"
    scene_data.render.image_settings.quality = 90
    # STANDARD, not Filmic. These frames exist to judge MATERIAL VALUES, and
    # a filmic curve lifts shadows hard: carbon-black rubber at its real
    # ~0.043 linear albedo renders as mid-grey concrete under Filmic and as
    # black under Standard, which is what it is. Judging albedo through a
    # look transform is how a texture ends up 12x too dark and nobody notices.
    scene_data.view_settings.view_transform = "Standard"
    OUT.mkdir(parents=True, exist_ok=True)
    scene_data.render.filepath = str(OUT / f"{name}.jpg")
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(camera, do_unlink=True)
    bpy.data.cameras.remove(camera_data)


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    scene()
    light()
    for view in VIEWS:
        if only and view[0] != only:
            continue
        render(*view)
        print(f"rendered {view[0]}")


if __name__ == "__main__":
    main()
