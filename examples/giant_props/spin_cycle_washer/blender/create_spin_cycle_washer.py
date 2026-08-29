"""Deterministic Blender generator for the Washing Machine Spin Cycle.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/spin_cycle_washer/blender/create_spin_cycle_washer.py
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

import spec  # noqa: E402
from proplib import blender_kit as bk  # noqa: E402

MOD_ID = spec.MOD_ID
MOD_ROOT = EXAMPLE_ROOT / "mod"
VEHICLE_DIR = MOD_ROOT / "vehicles" / MOD_ID
AUTHORING_ROOT = EXAMPLE_ROOT / "authoring"

H = spec.BODY_HALF
TOP = spec.BODY_TOP
AXIS_Z = spec.DRUM_AXIS_Z
DRUM_R = spec.DRUM_RADIUS
Y0 = spec.DRUM_Y_MIN
Y1 = spec.DRUM_Y_MAX


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


def _face_uv(obj, width: float, height: float) -> None:
    """Re-unwrap the -Y (front) face into an authored 0..1 frame.

    bk.add_box UVs are metric; legend/label textures author the plate face
    as u across, v UP from the plate bottom (the centrifuge console-legend
    idiom, round 15). Mesh vertices are LOCAL, centered on the object
    origin (add_box never applies location), so the frame is the plate's
    own half-extents — world x0/z0 here shifted the map into a tiled wrap
    (duplicate dial labels, first verify render 2026-08-13)."""

    mesh = obj.data
    uv = mesh.uv_layers.active
    if uv is None:
        uv = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        if poly.normal.y < -0.5:
            for li in poly.loop_indices:
                vx, _vy, vz = mesh.vertices[mesh.loops[li].vertex_index].co
                uv.data[li].uv = (
                    (vx + width / 2.0) / width,
                    (vz + height / 2.0) / height,
                )


def _face_uv_rear(obj, width: float, height: float) -> None:
    """+Y (rear) face variant of _face_uv: u runs along -X so the print
    reads correctly for a viewer standing BEHIND the machine (rear
    stickers, 2026-08-13). Same LOCAL half-extent frame."""

    mesh = obj.data
    uv = mesh.uv_layers.active
    if uv is None:
        uv = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        if poly.normal.y > 0.5:
            for li in poly.loop_indices:
                vx, _vy, vz = mesh.vertices[mesh.loops[li].vertex_index].co
                uv.data[li].uv = (
                    (width / 2.0 - vx) / width,
                    (vz + height / 2.0) / height,
                )


HEAVY_FONT = r"C:\Windows\Fonts\ariblk.ttf"
_FONT_CACHE: dict = {}


def _text_font(path: str):
    import bpy

    if path not in _FONT_CACHE:
        _FONT_CACHE[path] = bpy.data.fonts.load(path)
    return _FONT_CACHE[path]


def add_text_solid(name, text, cap_height, depth, value, location, rotation,
                   *, max_width=None, font_path=HEAVY_FONT):
    """Extruded glyph solid, centred on its bbox, posed via object transform
    (the catapult/centrifuge marquee recipe: FONT curve -> mesh, object
    matrix carries the pose, export bakes matrix_world)."""

    import bpy

    curve = bpy.data.curves.new(f"{name}_curve", type="FONT")
    curve.body = text
    curve.font = _text_font(font_path)
    curve.size = 1.0
    curve.extrude = depth / 2.0
    obj = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.view_layer.objects.active
    mesh = obj.data
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    scale = cap_height / (max(ys) - min(ys))
    if max_width is not None and (max(xs) - min(xs)) * scale > max_width:
        scale = max_width / (max(xs) - min(xs))
    x_mid = 0.5 * (max(xs) + min(xs))
    y_mid = 0.5 * (max(ys) + min(ys))
    for v in mesh.vertices:
        v.co.x = (v.co.x - x_mid) * scale
        v.co.y = (v.co.y - y_mid) * scale
    mesh.update()
    obj.name = name
    mesh.name = f"{name}_mesh"
    obj.location = location
    obj.rotation_euler = rotation
    bk.assign_material(obj, value)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(38.0))
    except Exception:
        bpy.ops.object.shade_flat()
    obj.select_set(False)
    return obj


def build_visual(materials) -> list:
    import bpy

    white = materials[f"{MOD_ID}_enamel_white"]
    gray = materials[f"{MOD_ID}_enamel_gray"]
    dial_blue = materials[f"{MOD_ID}_dial_blue"]
    asphalt = materials[f"{MOD_ID}_ramp_asphalt"]
    steel = materials[f"{MOD_ID}_drum_steel"]

    objects = []
    # Enamel body with the drum cavity bored out of the front face.
    body = bk.add_box(
        f"{MOD_ID}_body",
        (0.0, 0.0, TOP / 2),
        (2 * H, 2 * H, TOP),
        white,
        bevel=0.4,
        metric_uv=(2.6, 2.6),
    )
    cavity = bk.add_cylinder(
        f"{MOD_ID}_cavity_cutter",
        (0.0, (Y0 - 1.2 + Y1) / 2, AXIS_Z),
        DRUM_R + 0.15,
        (Y1 - (Y0 - 1.2)),
        None,
        vertices=64,
        axis="Y",
    )
    # Apply the body's 0.4 edge bevel IN ORDER before boring the cavity.
    # Left pending, the exporter re-bevelled the boolean's OUTPUT: the bore
    # rim chamfered below the machine's own floor, collided with the
    # bottom-edge bevel and shipped 0.083380 m^2 of same-winding double
    # cover on the front panel (proplib KNOWN BUG; measurements in
    # apply_pending_bevels' docstring). The mouth is now the cutter's true
    # r 4.35 with a sharp rim; porthole_trim (inner edge r 4.28) covers it.
    bk.apply_pending_bevels(body)
    bpy.ops.object.select_all(action="DESELECT")
    bk.cut_openings(body, [cavity])
    objects.append(body)
    gasket = materials[f"{MOD_ID}_gasket_rubber"]
    console = materials[f"{MOD_ID}_console_graphite"]
    lamp = materials[f"{MOD_ID}_drum_lamp"]

    # Double porthole trim: painted outer ring + brushed inner ring + rubber
    # door gasket just inside the mouth. ENTRANCE REWORK (2026-08-13,
    # player screenshot: "the metal is occluding the ramp"): every one of
    # these rings used to run FULL circle, so their bottom arcs crossed
    # the drive path right at the threshold (tube tops up to z 0.97
    # against a z 0.65 sill). Each ring is now boolean-cut below z 0.55
    # and the open ends bury into a flat steel threshold sill, making the
    # mouth a drivable D-shaped hatch.
    chrome = materials[f"{MOD_ID}_chrome_trim"]
    ring_specs = (
        ("porthole_trim", (0.0, -H - 0.05, AXIS_Z), DRUM_R + 0.42, 0.34,
         gray, 12),
        ("porthole_inner", (0.0, -H + 0.18, AXIS_Z), DRUM_R + 0.05, 0.2,
         chrome, 10),
        # Folded rubber bellows: two light-gray convolutions just inside
        # the mouth (research: the visible gasket is one of the strongest
        # "real washer" cues; a single near-black torus read as a tire).
        ("door_gasket", (0.0, -H + 0.5, AXIS_Z), DRUM_R - 0.15, 0.28,
         gasket, 10),
        ("door_gasket_inner", (0.0, -H + 0.85, AXIS_Z), DRUM_R - 0.35,
         0.22, gasket, 10),
    )
    for ring_name, ring_center, ring_r, ring_tube, ring_mat, minor in ring_specs:
        # major 28 -> 96 (2026-08-13, player: "way too few triangles...
        # too faceted"): on a 4+ m ring every chord was ~1 m long and the
        # silhouette read as a polygon. 96 puts chords under 30 cm.
        ring = bk.add_torus(
            f"{MOD_ID}_{ring_name}",
            ring_center,
            ring_r,
            ring_tube,
            ring_mat,
            rotation=(math.pi / 2, 0.0, 0.0),
            major_segments=96,
            minor_segments=max(minor, 14),
        )
        throat_cutter = bk.add_box(
            f"{MOD_ID}_{ring_name}_throat_cut",
            (0.0, ring_center[1], 0.55 - 1.5),
            (12.0, 3.0, 3.0),
            None,
        )
        bk.cut_openings(ring, [throat_cutter])
        objects.append(ring)
    # Flat threshold sill: a brushed-steel apron whose top is FLUSH with
    # the ramp line at the fascia (z 0.65), swallowing the cut ring ends.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_threshold_sill",
            (0.0, -H + 0.05, 0.44),
            (5.6, 1.9, 0.42),
            chrome,
            bevel=0.03,
        )
    )
    # Drum lamp: warm emissive strip at the top of the mouth so the interior
    # reads as a lit drum, not a black void.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_drum_lamp_strip",
            (0.0, -H + 0.9, AXIS_Z + DRUM_R - 0.55),
            (1.8, 0.5, 0.35),
            lamp,
            bevel=0.06,
        )
    )
    # Front fascia seams: sheet-metal part lines down each front corner
    # plus the kick-plate seam (real fronts are separate pressings).
    # ENTRANCE REWORK (2026-08-13): the kick seam and kick plate used to
    # run the FULL body width, straight across the porthole mouth - the
    # "metal occluding the ramp" in the player screenshot. Both are now
    # split into left/right segments that stop clear of the trim ring.
    for seam_name, (cx, cz, dx, dz) in {
        "seam_l": (-H + 0.5, TOP / 2, 0.08, TOP - 1.8),
        "seam_r": (H - 0.5, TOP / 2, 0.08, TOP - 1.8),
        "seam_kick_l": (-5.15, 1.32, 2.3, 0.08),
        "seam_kick_r": (5.15, 1.32, 2.3, 0.08),
    }.items():
        objects.append(
            bk.add_box(
                f"{MOD_ID}_{seam_name}",
                (cx, -H - 0.02, cz),
                (dx, 0.05, dz),
                gray,
                bevel=0.0,
            )
        )
    for kick_tag, kick_x in (("l", -4.95), ("r", 4.95)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_kick_plate_{kick_tag}",
                (kick_x, -H - 0.06, 0.6),
                (2.3, 0.14, 1.1),
                console,
                bevel=0.04,
            )
        )
    # Pump-filter access hatch in the kick plate (right corner) — a small
    # round service door, strong realism cue.
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_filter_hatch",
            (4.5, -H - 0.12, 0.6),
            0.5,
            0.1,
            gray,
            vertices=18,
            axis="Y",
        )
    )

    # ---- Control strip: full-width graphite band across the top of the
    # fascia (top ~17% of body height, per front-loader research), with
    # detergent drawer / program dial / touch pads / LCD laid out left to
    # right. Legend skins carry authored 0..1 face UVs; label positions in
    # the textures are computed in spec.py from the same layout constants.
    strip_z = spec.STRIP_Z0 + spec.STRIP_H / 2.0
    objects.append(
        bk.add_box(
            f"{MOD_ID}_control_strip",
            (0.0, -H - 0.12, strip_z),
            (2 * H, 0.3, spec.STRIP_H),
            console,
            bevel=0.06,
            metric_uv=(2.2, 2.2),
        )
    )
    # Detergent drawer, viewer's left: proud face with a chrome pull bar.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_drawer",
            (-4.55, -H - 0.05, 11.85),
            (3.2, 0.56, 1.5),
            gray,
            bevel=0.08,
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_drawer_pull",
            (-4.55, -H - 0.36, 11.25),
            (2.6, 0.12, 0.18),
            chrome,
            bevel=0.04,
        )
    )
    # Program dial: chrome ring + graphite cap + white pointer at 12
    # o'clock, over a printed legend plate with the ten cycle names.
    dial_plate = bk.add_box(
        f"{MOD_ID}_dial_plate",
        (spec.DIAL_X, -H - 0.29, strip_z),
        (spec.DIAL_PLATE_W, 0.02, spec.STRIP_H),
        materials[f"{MOD_ID}_dial_legend"],
        bevel=0.0,
    )
    _face_uv(dial_plate, spec.DIAL_PLATE_W, spec.STRIP_H)
    objects.append(dial_plate)
    # Program knob, realism pass (2026-08-13): chrome skirt at the panel,
    # dark soft-touch grip barrel with GEOMETRIC knurling (16 radial ribs
    # - texture stripes cannot wrap a cylinder the right way), brushed
    # top cap, recessed white pointer line. Visible cylinders get 24-32
    # segments (silhouette law).
    # The knob itself (grip + knurls + cap + pointer) lives in
    # build_parts["dial"] 2026-08-13 (player: "make the dial functional"):
    # it is a posable part the GE behavior rotates to the selected program
    # detent. The wide chrome SKIRT that used to sit behind it was deleted
    # the same day (player: "remove the circle metal backing") - it read as
    # a dinner plate bolted to the fascia and buried the legend ring. All
    # that stays behind is a slim graphite shaft bridging the standoff gap,
    # so the knob reads as mounted rather than floating.
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_dial_shaft",
            (spec.DIAL_X, -H - 0.35, strip_z),
            0.16,
            0.24,
            console,
            vertices=20,
            axis="Y",
        )
    )
    # Touch controls legend + pads.
    controls_plate = bk.add_box(
        f"{MOD_ID}_controls_plate",
        (spec.CONTROLS_X0 + spec.CONTROLS_W / 2.0, -H - 0.286, strip_z),
        (spec.CONTROLS_W, 0.02, spec.STRIP_H),
        materials[f"{MOD_ID}_controls_legend"],
        bevel=0.0,
    )
    _face_uv(controls_plate, spec.CONTROLS_W, spec.STRIP_H)
    objects.append(controls_plate)
    # POWER button deleted 2026-08-13 (player: "we don't need a power
    # button") - the ringed blue START moved into its slot via START_X.
    # REALISM PASS same day: each option button is a recessed graphite
    # bezel frame + a heavily-rounded satin-stainless cap sitting proud,
    # instead of a bare white box.
    button_satin = materials[f"{MOD_ID}_button_satin"]
    for index, bx in enumerate(spec.BUTTON_XS):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_button_frame_{index}",
                (bx, -H - 0.29, 11.85),
                (0.66, 0.08, 0.65),
                console,
                bevel=0.02,
            )
        )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_button_{index}",
                (bx, -H - 0.35, 11.85),
                (0.52, 0.14, 0.51),
                button_satin,
                bevel=0.1,
            )
        )
    # START: chrome base collar + glossy blue DOMED cap (squashed sphere)
    # inside the chrome halo ring.
    start_glass = materials[f"{MOD_ID}_start_glass"]
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_start_base",
            (spec.START_X, -H - 0.31, 11.85),
            0.3,
            0.1,
            chrome,
            vertices=24,
            axis="Y",
        )
    )
    objects.append(
        bk.add_sphere(
            f"{MOD_ID}_start_button",
            (spec.START_X, -H - 0.36, 11.85),
            0.27,
            start_glass,
            segments=24,
            rings=12,
            scale=(1.0, 0.55, 1.0),
        )
    )
    objects.append(
        bk.add_torus(
            f"{MOD_ID}_start_ring",
            (spec.START_X, -H - 0.38, 11.85),
            0.37,
            0.06,
            chrome,
            rotation=(math.pi / 2, 0.0, 0.0),
            major_segments=24,
            minor_segments=10,
        )
    )
    # Ice-blue segment display: time remaining + spin + temperature.
    display_plate = bk.add_box(
        f"{MOD_ID}_display",
        (5.325, -H - 0.33, 11.9),
        (1.55, 0.08, 0.95),
        materials[f"{MOD_ID}_display_lcd"],
        bevel=0.0,
    )
    _face_uv(display_plate, 1.55, 0.95)
    objects.append(display_plate)

    # Brand LOGO between the control strip and the door top (2026-08-13,
    # player: "make this look like a logo and center it"): extruded chrome
    # wordmark + blue underline swoosh, centred on the door axis - no
    # more printed white plate.
    # Graphite letters, not chrome: chrome-on-white-enamel vanished in the
    # first verify render; dark metal reads at any light angle.
    objects.append(
        add_text_solid(
            f"{MOD_ID}_logo_wordmark",
            "MAXSPIN",
            0.52,
            0.1,
            console,
            (0.0, -H - 0.1, 10.22),
            (math.pi / 2.0, 0.0, 0.0),
            max_width=4.4,
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_logo_underline",
            (0.15, -H - 0.08, 9.82),
            (3.1, 0.06, 0.09),
            dial_blue,
            bevel=0.03,
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_logo_dot",
            (-1.85, -H - 0.08, 9.82),
            0.07,
            0.06,
            dial_blue,
            vertices=12,
            axis="Y",
        )
    )
    # (Energy sticker moved to the REAR panel 2026-08-13 - US EnergyGuide
    # style, see the rear service wall below.)

    # Worktop slab with a rear upstand trim (replaces the old floating
    # angled console; controls now live on the fascia band).
    objects.append(
        bk.add_box(
            f"{MOD_ID}_worktop",
            (0.0, -0.05, TOP + 0.275),
            (2 * H + 0.3, 2 * H + 0.2, 0.55),
            white,
            bevel=0.1,
            metric_uv=(2.6, 2.6),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_worktop_upstand",
            (0.0, H - 0.12, TOP + 0.7),
            (2 * H + 0.3, 0.45, 0.55),
            gray,
            bevel=0.08,
        )
    )
    # Stamped stiffening ribs on both side panels. 2026-08-13 player pass
    # ("the reinforcement sides should be curved into the sides of the wall
    # instead of being simply slabs that are squared off on all sides"):
    # these were applied boxes standing 8 cm proud with hard ends. A real
    # side panel rib is a SWAGE pressed out of the sheet - a smooth dome
    # that rises from the panel and dies away at both ends. Modelled as a
    # long squashed sphere buried in the panel so only the crown shows.
    for side in (-1.0, 1.0):
        for rib_index, rib_z in enumerate((3.2, 5.2, 7.2)):
            swage = bk.add_sphere(
                f"{MOD_ID}_side_rib_{'l' if side < 0 else 'r'}{rib_index}",
                # Centre sits INSIDE the panel: half-extent 0.19 against a
                # 0.12 burial leaves ~0.07 m of crown proud.
                (side * (H - 0.12), 0.0, rib_z),
                1.0,
                white,
                segments=32,
                rings=18,
                scale=(0.19, (2 * H - 2.6) / 2.0, 0.26),
            )
            objects.append(swage)
    # ---- Rear service wall (2026-08-13 realism pass, player: "the vents
    # and hose hookups need to look far more realistic"). Vocabulary from
    # real front-loader backs: a pressed rear tub cover with bearing boss
    # and transit bolts, framed louver vent banks with angled slats, a
    # recessed twin inlet-valve box with brass 3/4" GHT fittings (red/blue
    # collars), a corrugated drain hose looped over its clip, a power cord
    # on a wrap bracket, the rating plate, and the EnergyGuide sticker.
    brass = materials[f"{MOD_ID}_brass_fitting"]
    hose = materials[f"{MOD_ID}_hose_rubber"]
    cord = materials[f"{MOD_ID}_cord_black"]
    mark_hot = materials[f"{MOD_ID}_mark_hot"]
    mark_cold = materials[f"{MOD_ID}_mark_cold"]
    # Pressed rear tub cover over the drum axis: the big circular pressing
    # every real machine has, with a stamped stiffening ring and a centre
    # bearing boss.
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_tub_cover",
            (0.0, H + 0.02, AXIS_Z),
            3.6,
            0.14,
            gray,
            vertices=28,
            axis="Y",
        )
    )
    objects.append(
        bk.add_torus(
            f"{MOD_ID}_tub_cover_ring",
            (0.0, H + 0.1, AXIS_Z),
            2.6,
            0.07,
            gray,
            rotation=(math.pi / 2, 0.0, 0.0),
            major_segments=28,
            minor_segments=8,
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_bearing_boss",
            (0.0, H + 0.12, AXIS_Z),
            0.55,
            0.22,
            gray,
            vertices=16,
            axis="Y",
        )
    )
    # Transit bolts on the cover flange: hex head over a rubber washer,
    # the shipping-restraint pattern.
    for bolt_index in range(4):
        bolt_angle = math.radians(45.0 + bolt_index * 90.0)
        bolt_x = math.cos(bolt_angle) * 2.95
        bolt_z = AXIS_Z + math.sin(bolt_angle) * 2.95
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_transit_washer_{bolt_index}",
                (bolt_x, H + 0.1, bolt_z),
                0.3,
                0.06,
                gasket,
                vertices=12,
                axis="Y",
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_transit_bolt_{bolt_index}",
                (bolt_x, H + 0.17, bolt_z),
                0.2,
                0.14,
                gray,
                vertices=6,
                axis="Y",
            )
        )
    # Framed louver banks: a recessed graphite frame with angled slats
    # (stamped-vent look) instead of floating slot bars.
    for side in (-1.0, 1.0):
        side_tag = "l" if side < 0 else "r"
        objects.append(
            bk.add_box(
                f"{MOD_ID}_vent_frame_{side_tag}",
                (side * 2.15, H + 0.01, 11.55),
                (2.4, 0.06, 1.7),
                console,
                bevel=0.02,
            )
        )
        for louver_index in range(5):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_louver_{side_tag}{louver_index}",
                    (side * 2.15, H + 0.07, 10.95 + louver_index * 0.31),
                    (2.1, 0.05, 0.16),
                    gray,
                    bevel=0.0,
                    rotation=(math.radians(38.0), 0.0, 0.0),
                )
            )
    # Recessed inlet-valve box: dark backing panel, two brass valves with
    # hex flats, threaded tips and hot/cold collar rings.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_inlet_box",
            (4.6, H + 0.03, 12.15),
            (2.3, 0.1, 1.3),
            console,
            bevel=0.02,
        )
    )
    for valve_x, mark, valve_tag in ((4.05, mark_hot, "hot"),
                                     (5.15, mark_cold, "cold")):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_inlet_body_{valve_tag}",
                (valve_x, H + 0.28, 12.15),
                0.17,
                0.5,
                brass,
                vertices=12,
                axis="Y",
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_inlet_hex_{valve_tag}",
                (valve_x, H + 0.16, 12.15),
                0.23,
                0.16,
                brass,
                vertices=6,
                axis="Y",
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_inlet_thread_{valve_tag}",
                (valve_x, H + 0.56, 12.15),
                0.125,
                0.18,
                brass,
                vertices=12,
                axis="Y",
            )
        )
        objects.append(
            bk.add_torus(
                f"{MOD_ID}_inlet_collar_{valve_tag}",
                (valve_x, H + 0.4, 12.15),
                0.19,
                0.045,
                mark,
                rotation=(math.pi / 2, 0.0, 0.0),
                major_segments=16,
                minor_segments=8,
            )
        )
    # Corrugated drain hose: gray elbow at the pump, a ribbed vertical run
    # up the left edge, a loop over the white clip bar, and the open end
    # hanging back down.
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_drain_elbow",
            (-4.5, H + 0.22, 1.15),
            0.26,
            0.4,
            gray,
            vertices=12,
            axis="Y",
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_drain_hose_run",
            (-4.5, H + 0.3, 6.25),
            0.2,
            9.7,
            hose,
            vertices=12,
        )
    )
    for rib_index in range(13):
        objects.append(
            bk.add_torus(
                f"{MOD_ID}_drain_rib_{rib_index}",
                (-4.5, H + 0.3, 1.75 + rib_index * 0.72),
                0.2,
                0.055,
                hose,
                major_segments=12,
                minor_segments=6,
            )
        )
    objects.append(
        bk.add_torus(
            f"{MOD_ID}_drain_loop",
            (-4.15, H + 0.3, 11.35),
            0.55,
            0.2,
            hose,
            rotation=(math.pi / 2, 0.0, 0.0),
            major_segments=20,
            minor_segments=10,
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_drain_tail",
            (-3.6, H + 0.3, 10.85),
            0.2,
            1.0,
            hose,
            vertices=12,
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_drain_clip",
            (-4.15, H + 0.18, 11.95),
            (1.4, 0.16, 0.25),
            white,
            bevel=0.03,
        )
    )
    # Power cord (2026-08-13 coherence pass, player screenshot with the
    # floating drop/tail circled): every segment now shares the same
    # y-plane (H+0.34) and each joint overlaps the next piece, so the run
    # reads boss -> drop -> coil -> tail -> plug as ONE cable. The plug is
    # a proper North American NEMA 5-15: black molded body, two flat brass
    # blades and the round ground pin, hanging prongs-down.
    brass = materials[f"{MOD_ID}_brass_fitting"]
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_cord_boss",
            (5.9, H + 0.2, 12.3),
            0.16,
            0.4,
            cord,
            vertices=16,
            axis="Y",
        )
    )
    # Vertical drop: top buried in the boss, bottom tip inside the outer
    # coil's top tube.
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_cord_drop",
            (5.9, H + 0.34, 10.68),
            0.065,
            3.15,
            cord,
            vertices=10,
        )
    )
    for horn_index, horn_z in enumerate((9.05, 8.15)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_cord_horn_{horn_index}",
                (5.9, H + 0.2, horn_z),
                (0.8, 0.3, 0.16),
                gray,
                bevel=0.04,
            )
        )
    for coil_index, coil_r in enumerate((0.55, 0.44, 0.33)):
        objects.append(
            bk.add_torus(
                f"{MOD_ID}_cord_coil_{coil_index}",
                (5.9, H + 0.34, 8.6),
                coil_r,
                0.065,
                cord,
                rotation=(math.pi / 2, 0.0, 0.0),
                major_segments=28,
                minor_segments=8,
            )
        )
    # Tail: leaves the outer coil's bottom tangent and slants down-left
    # into the plug (cylinder authored along Z, tilted 45 degrees about Y:
    # ends land at (5.92, 8.08) on the coil and (5.32, 7.48) in the plug).
    tail = bk.add_cylinder(
        f"{MOD_ID}_cord_tail",
        (5.62, H + 0.34, 7.78),
        0.065,
        0.85,
        cord,
        vertices=10,
    )
    tail.rotation_euler = (0.0, math.radians(45.0), 0.0)
    objects.append(tail)
    # Molded strain-relief taper bridging tail and plug body.
    objects.append(
        bk.add_cone(
            f"{MOD_ID}_plug_relief",
            (5.36, H + 0.34, 7.52),
            0.1,
            0.065,
            0.24,
            cord,
            rotation=(0.0, math.radians(45.0), 0.0),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_cord_plug",
            (5.3, H + 0.34, 7.26),
            (0.3, 0.26, 0.42),
            cord,
            bevel=0.06,
        )
    )
    # NEMA 5-15 face, prongs down: two parallel flat blades plus the
    # round ground pin offset toward the machine.
    for blade_index, blade_x in enumerate((5.3 - 0.08, 5.3 + 0.08)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_plug_blade_{blade_index}",
                (blade_x, H + 0.3, 6.98),
                (0.035, 0.09, 0.2),
                brass,
                bevel=0.0,
            )
        )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_plug_ground_pin",
            (5.3, H + 0.44, 6.99),
            0.035,
            0.18,
            brass,
            vertices=12,
        )
    )
    # Rating plate (electrical spec) and the US EnergyGuide sticker, both
    # facing the rear viewer.
    serial = bk.add_box(
        f"{MOD_ID}_serial_plate",
        (5.2, H + 0.02, 2.3),
        (0.9, 0.04, 0.6),
        materials[f"{MOD_ID}_serial_plate"],
        bevel=0.0,
    )
    _face_uv_rear(serial, 0.9, 0.6)
    objects.append(serial)
    energy = bk.add_box(
        f"{MOD_ID}_energy_sticker",
        (-3.55, H + 0.02, 8.3),
        (1.55, 0.04, 2.1),
        materials[f"{MOD_ID}_energy_label"],
        bevel=0.0,
    )
    _face_uv_rear(energy, 1.55, 2.1)
    objects.append(energy)
    # Black threaded leveling feet with hex locknuts.
    foot_rubber = materials[f"{MOD_ID}_foot_rubber"]
    for index, (fx, fy) in enumerate(
        (
            (-H + 0.8, -H + 0.8),
            (H - 0.8, -H + 0.8),
            (-H + 0.8, H - 0.8),
            (H - 0.8, H - 0.8),
        )
    ):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_foot_{index}",
                (fx, fy, 0.1),
                0.45,
                0.2,
                foot_rubber,
                vertices=14,
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_foot_nut_{index}",
                (fx, fy, 0.26),
                0.58,
                0.16,
                gray,
                vertices=6,
            )
        )
    # Drum back plate with a pressed hub + spokes for depth (static; the
    # spinning liner is a part), in brighter stainless.
    bright = materials[f"{MOD_ID}_drum_bright"]
    # Back plate front face sits 10 cm proud of the cavity's boolean back
    # wall (both were at exactly y=4.0 — coplanar faces z-fought as radial
    # shimmer streaks, reported live 2026-08-13). Spokes ride another 6 cm
    # in front of the plate, hub in front of the spokes.
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_drum_back",
            (0.0, Y1 + 0.05, AXIS_Z),
            DRUM_R - 0.05,
            0.3,
            bright,
            vertices=24,
            axis="Y",
            # No metric_uv: the cylinder UV scaler is circumference-based,
            # which smears the CAP's perforation holes into hairline
            # stripes (verify render 2026-08-13); the default planar cap
            # projection keeps a clean dot grid.
        )
    )
    # Spider = solid brushed stainless, NOT the perforated drum skin: on
    # plain box UVs the hole grid smeared into dark slashes along every
    # arm (2026-08-13, exposed once the back plate's holes were sharpened).
    spider = materials[f"{MOD_ID}_drum_spider"]
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_drum_hub",
            (0.0, Y1 - 0.18, AXIS_Z),
            0.9,
            0.35,
            spider,
            vertices=48,
            axis="Y",
        )
    )
    for spoke in range(3):
        spoke_angle = spoke * math.pi / 3
        objects.append(
            bk.add_box(
                f"{MOD_ID}_drum_spoke_{spoke}",
                (0.0, Y1 - 0.17, AXIS_Z),
                (0.6, 0.18, 2 * DRUM_R - 1.2),
                spider,
                bevel=0.05,
                rotation=(0.0, spoke_angle, 0.0),
                metric_uv=(1.2, 1.2),
            )
        )
    # Entry ramp up to the drum sill.
    sill_z = AXIS_Z - DRUM_R + 0.25
    run = -H - spec.RAMP_GROUND_Y
    ramp_len = math.hypot(run, sill_z)
    angle = math.atan2(sill_z, run)
    normal = (0.0, -math.sin(angle), math.cos(angle))
    mid_y = (spec.RAMP_GROUND_Y + -H) / 2
    objects.append(
        bk.add_box(
            f"{MOD_ID}_ramp",
            (0.0, mid_y - normal[1] * 0.11, sill_z / 2 - normal[2] * 0.11),
            (4.4, ramp_len, 0.22),
            asphalt,
            bevel=0.0,
            rotation=(angle, 0.0, 0.0),
            metric_uv=(2.5, 2.5),
        )
    )
    return objects


_WATER_HALF_W = 4.05


def _water_top_z(x: float, y: float) -> float:
    """Height of the wash-water surface at (x, y), authored frame.

    Standing waves plus a meniscus lip that climbs at the +-X edges. The
    foam sheet reuses this so suds ride the swell instead of knifing
    through it (they intersected as white "ice floes" in the first verify
    render of the 2026-08-13 slosh pass).
    """

    edge = abs(x) / _WATER_HALF_W
    lip = 0.24 * edge ** 7
    wave = (
        0.055 * math.sin(x * 2.6 + y * 1.3)
        + 0.045 * math.sin(y * 2.1 - x * 1.1)
        + 0.03 * math.sin(x * 4.7 + y * 3.9)
    ) * (1.0 - edge ** 4)
    return spec.WATER_PIVOT[2] + lip + wave


def _add_foam_sheet(name, value):
    """Suds sheet that follows the water surface 6 cm above it."""

    import bpy
    import bmesh

    half_w = _WATER_HALF_W - 0.35
    fy0, fy1 = Y0 + 0.45, Y1 - 0.45
    nx, ny = 20, 12
    bm = bmesh.new()
    grid = {}
    for iy in range(ny + 1):
        y = fy0 + (fy1 - fy0) * iy / ny
        for ix in range(nx + 1):
            x = -half_w + 2.0 * half_w * ix / nx
            grid[(ix, iy)] = bm.verts.new((x, y, _water_top_z(x, y) + 0.06))
    for iy in range(ny):
        for ix in range(nx):
            bm.faces.new((
                grid[(ix, iy)], grid[(ix + 1, iy)],
                grid[(ix + 1, iy + 1)], grid[(ix, iy + 1)],
            ))
    # Planar UVs so the suds opacity mask (which is what breaks the sheet
    # into floating rafts) actually samples. Tiled coarser than the water
    # so the clumps read as bigger than the ripples.
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        for loop in face.loops:
            loop[uv_layer].uv = (loop.vert.co.x / 3.4, loop.vert.co.y / 3.4)
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bk.assign_material(obj, value)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(60.0))
    except Exception:
        bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj


def _add_water_body(name, value):
    """Sculpted wash-water mesh (2026-08-13 slosh pass).

    Authored with its rippled TOP at the part pivot plane (z 0.4) so the
    runtime's downward z-scale still works. The top grid carries standing
    waves plus a meniscus lip that rises ~0.24 m at the +-X edges (the lip
    sits ABOVE the pivot, so in game it climbs the drum wall above the
    waterline). Below the rim, ring loops taper inward with depth so the
    squashed body reads as water conforming to a round drum.
    """
    import bpy
    import bmesh

    half_w = _WATER_HALF_W
    wy0, wy1 = Y0 + 0.25, Y1 - 0.25
    y_mid = (wy0 + wy1) / 2.0
    top_z = spec.WATER_PIVOT[2]
    depth = spec.WATER_SLAB_HEIGHT
    nx, ny = 24, 14

    bm = bmesh.new()
    grid = {}
    for iy in range(ny + 1):
        y = wy0 + (wy1 - wy0) * iy / ny
        for ix in range(nx + 1):
            x = -half_w + 2.0 * half_w * ix / nx
            grid[(ix, iy)] = bm.verts.new((x, y, _water_top_z(x, y)))
    for iy in range(ny):
        for ix in range(nx):
            bm.faces.new((
                grid[(ix, iy)], grid[(ix + 1, iy)],
                grid[(ix + 1, iy + 1)], grid[(ix, iy + 1)],
            ))

    # Ordered boundary loop of the top grid (counter-clockwise).
    boundary = []
    for ix in range(nx + 1):
        boundary.append(grid[(ix, 0)])
    for iy in range(1, ny + 1):
        boundary.append(grid[(nx, iy)])
    for ix in range(nx - 1, -1, -1):
        boundary.append(grid[(ix, ny)])
    for iy in range(ny - 1, 0, -1):
        boundary.append(grid[(0, iy)])

    # Depth rings: shrink toward the bottom (round-drum taper).
    rows = [boundary]
    for frac, width_keep, length_keep in (
        (0.10, 0.97, 0.99),
        (0.30, 0.86, 0.95),
        (0.60, 0.66, 0.88),
        (1.00, 0.42, 0.78),
    ):
        ring = []
        for vert in boundary:
            x, y, _ = vert.co
            ring.append(bm.verts.new((
                x * width_keep,
                y_mid + (y - y_mid) * length_keep,
                top_z - depth * frac,
            )))
        rows.append(ring)
    count = len(boundary)
    for upper, lower in zip(rows, rows[1:]):
        for k in range(count):
            nk = (k + 1) % count
            bm.faces.new((upper[k], upper[nk], lower[nk], lower[k]))
    bm.faces.new(tuple(reversed(rows[-1])))

    # Top-down planar UVs so the scrolling ripple maps stream across the
    # surface. 2.6 m -> 1.7 m per tile (2026-08-13): the ripple field is
    # fine wind chop calibrated against the game's ripple_nm, and at 2.6 m
    # the chop was too large to read as water on an 8 m pool.
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        for loop in face.loops:
            loop[uv_layer].uv = (loop.vert.co.x / 1.7, loop.vert.co.y / 1.7)

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bk.assign_material(obj, value)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(60.0))
    except Exception:
        bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj


def build_parts(materials) -> dict[str, dict[str, object]]:
    import bpy

    gray = materials[f"{MOD_ID}_enamel_gray"]
    steel = materials[f"{MOD_ID}_drum_steel"]
    glass = materials[f"{MOD_ID}_glass_blue"]

    parts: dict[str, dict[str, object]] = {}
    # Full-length ribbed drum liner, spinning about Y. The visible surface
    # sits 5 cm inside the collision ring so cars read as resting ON it
    # (the original three floating hoops + paddles sweeping through the car
    # were the "strange internals" reported in play-testing).
    drum_center = (0.0, (Y0 + Y1) / 2, AXIS_Z)
    # Open tube: a capped cylinder's front disc face blocked the porthole
    # view from outside (backface culling hid it from inside, so the drum
    # looked fine from within — reported live 2026-08-13).
    liner_objects = [
        bk.add_cylinder(
            f"{MOD_ID}_liner_shell",
            drum_center,
            DRUM_R - 0.05,
            Y1 - Y0 - 0.5,
            steel,
            vertices=80,
            axis="Y",
            metric_uv=(1.9, 1.9),
            open_ended=True,
        )
    ]
    # Three lifter paddles at 120 degrees (real front loaders have 3, not
    # 8 ribs). 2026-08-13 player pass ("curved into the sides of the wall
    # instead of simply slabs squared off on all sides"): each lifter is
    # now a long squashed-sphere blister half-buried in the liner, so the
    # crest is a smooth dome and both ends sweep down into the drum wall
    # like a moulded plastic lifter. Local X = radial (0.5), Z =
    # tangential (0.85), Y = along the drum. Kept shallow (~0.35 m proud
    # on a 4.2 m drum); the collision cage stays the smooth 12-gon.
    paddle = materials[f"{MOD_ID}_paddle_plastic"]
    for index in range(3):
        angle = math.radians(90.0 + index * 120.0)
        blister_r = DRUM_R + 0.13  # centre buried past the liner surface
        blister = bk.add_sphere(
            f"{MOD_ID}_paddle_{index}",
            (
                math.cos(angle) * blister_r,
                (Y0 + Y1) / 2,
                AXIS_Z + math.sin(angle) * blister_r,
            ),
            1.0,
            paddle,
            segments=32,
            rings=16,
            scale=(0.5, (Y1 - Y0 - 1.8) / 2.0, 0.85),
        )
        blister.rotation_euler = (0.0, -angle, 0.0)
        liner_objects.append(blister)
    parts["drum_liner"] = {"objects": liner_objects, "pivot": drum_center}

    # Program knob as a posable part (2026-08-13, player: "make the dial
    # functional so it can turn"): grip barrel, geometric knurling, satin
    # cap and pointer, pivoting about the knob's own Y axis so the GE
    # behavior can twist it to the selected program detent.
    strip_z = spec.STRIP_Z0 + spec.STRIP_H / 2.0
    knob_shell = materials[f"{MOD_ID}_knob_shell"]
    white = materials[f"{MOD_ID}_enamel_white"]
    # STANDOFF (2026-08-13, player: "off set the dial from the face a
    # little bit"): the whole knob moved 0.12 m further out, leaving a
    # ~10 cm gap between the legend plate face (-H-0.30) and the grip's
    # back face so the knob floats proud of the fascia instead of sitting
    # flat on it.
    dial_objects = [
        bk.add_cylinder(
            f"{MOD_ID}_dial_grip",
            (spec.DIAL_X, -H - 0.68, strip_z),
            0.62,
            0.55,
            knob_shell,
            vertices=32,
            axis="Y",
        )
    ]
    for rib_index in range(16):
        rib_angle = rib_index * math.pi / 8.0
        dial_objects.append(
            bk.add_box(
                f"{MOD_ID}_dial_knurl_{rib_index}",
                (
                    spec.DIAL_X + math.cos(rib_angle) * 0.63,
                    -H - 0.68,
                    strip_z + math.sin(rib_angle) * 0.63,
                ),
                (0.055, 0.48, 0.13),
                knob_shell,
                bevel=0.015,
                rotation=(0.0, -rib_angle, 0.0),
            )
        )
    dial_objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_dial_cap",
            (spec.DIAL_X, -H - 0.98, strip_z),
            0.52,
            0.1,
            materials[f"{MOD_ID}_button_satin"],
            vertices=32,
            axis="Y",
        )
    )
    dial_objects.append(
        bk.add_box(
            f"{MOD_ID}_dial_pointer",
            (spec.DIAL_X, -H - 1.02, strip_z + 0.3),
            (0.07, 0.06, 0.32),
            white,
            bevel=0.0,
        )
    )
    parts["dial"] = {
        "objects": dial_objects,
        "pivot": (spec.DIAL_X, -H - 0.72, strip_z),
    }

    # Wash water: translucent body whose TOP surface sits at the part
    # pivot, so the runtime rides the pivot on the waterline and z-scales
    # the body downward to fill. Foam floats just above it.
    # 2026-08-13 SLOSH PASS (player: "looks like a wobbling flat rectangle
    # ...should be curved into the sides of the wall"): the old flat box is
    # now a sculpted bmesh — a rippled top surface with a meniscus lip that
    # climbs above the waterline at the drum walls, and sides that taper
    # inward toward the bottom so the squashed silhouette reads as liquid
    # sitting in a round drum, not a crate of blue glass.
    water = materials[f"{MOD_ID}_wash_water"]
    foam = materials[f"{MOD_ID}_suds_foam"]
    water_slab = _add_water_body(f"{MOD_ID}_water_body", water)
    parts["water_body"] = {"objects": [water_slab], "pivot": spec.WATER_PIVOT}
    del water_slab
    # Foam is a THIN flush sheet, not a slab: the old 16 cm beveled block
    # rode proud of the waterline and its white sides read as a container
    # rim around the water (player screenshot 2026-08-13). It now poses
    # half-sunk (poseWater z +0.02), so only the foam TOP breaks the
    # surface.
    foam_slab = _add_foam_sheet(f"{MOD_ID}_suds_foam", foam)
    parts["suds_foam"] = {"objects": [foam_slab], "pivot": spec.WATER_PIVOT}

    # Porthole door: chrome trim ring + blue-tinted convex glass, hinged
    # on the +X side, with visible hinge arms and a recessed grip pocket
    # at the opposite rim (research: chrome ring + integrated grip is the
    # premium front-loader look; protruding bar handles are dated).
    chrome = materials[f"{MOD_ID}_chrome_trim"]
    dark = materials[f"{MOD_ID}_foot_rubber"]
    # Door ring/glass resolution raised 28/24 -> 96/48 (same faceting
    # complaint as the porthole rings - these are the largest circles on
    # the machine).
    door_ring = bk.add_torus(
        f"{MOD_ID}_door_ring",
        (0.0, -H - 0.55, AXIS_Z),
        DRUM_R - 0.35,
        0.5,
        chrome,
        rotation=(math.pi / 2, 0.0, 0.0),
        major_segments=96,
        minor_segments=16,
    )
    door_glass = bk.add_sphere(
        f"{MOD_ID}_door_glass",
        (0.0, -H - 0.75, AXIS_Z),
        DRUM_R - 0.7,
        glass,
        segments=48,
        rings=24,
        scale=(1.0, 0.45, 1.0),
    )
    door_hinge = bk.add_cylinder(
        f"{MOD_ID}_door_hinge",
        (spec.DOOR_PIVOT[0], spec.DOOR_PIVOT[1], AXIS_Z),
        0.2,
        2.2,
        gray,
        vertices=12,
    )
    door_objects = [door_ring, door_glass, door_hinge]
    for arm_index, arm_z in enumerate((AXIS_Z - 1.35, AXIS_Z + 1.35)):
        door_objects.append(
            bk.add_box(
                f"{MOD_ID}_hinge_arm_{arm_index}",
                (3.55, -H - 0.15, arm_z),
                (1.1, 0.5, 0.4),
                gray,
                bevel=0.05,
            )
        )
    door_objects.append(
        bk.add_box(
            f"{MOD_ID}_door_grip",
            (-(DRUM_R - 0.25), -H - 0.65, AXIS_Z),
            (0.6, 0.5, 1.3),
            dark,
            bevel=0.08,
        )
    )
    parts["door"] = {
        "objects": door_objects,
        "pivot": spec.DOOR_PIVOT,
    }
    del bpy
    return parts


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    body = cage.add_box_lattice(
        "body",
        (-H, -H, 0.0),
        (H, H, TOP),
        subdivisions=(2, 2, 2),
        fixed=True,
        collision=False,
        collision_faces=("top", "north", "east", "west"),
    )
    # Front (south) face: collide only the upper band, leaving the porthole
    # region open.
    for ix in range(2):
        quad = [
            body[(ix, 0, 1)],
            body[(ix + 1, 0, 1)],
            body[(ix + 1, 0, 2)],
            body[(ix, 0, 2)],
        ]
        for node in quad:
            cage.nodes[cage.node_index[node]]["collision"] = True
        cage.add_quad(quad, ground_model="metal")

    # Drum interior: 12 columns x 3 rings wound inward, plus a back-wall fan.
    rings = (Y0, (Y0 + Y1) / 2, Y1)
    columns: dict[tuple[int, int], str] = {}
    count = 12
    for index in range(count):
        angle = math.radians(index * 30.0)
        for ring_index, y in enumerate(rings):
            columns[(index, ring_index)] = cage.add_node(
                f"drum_{index:02d}_{ring_index}",
                (
                    math.cos(angle) * DRUM_R,
                    y,
                    AXIS_Z + math.sin(angle) * DRUM_R,
                ),
                fixed=True,
                collision=True,
                weight=140.0,
            )
    back_center = cage.add_node(
        "drum_back_center", (0.0, Y1, AXIS_Z), fixed=True, collision=True, weight=140.0
    )
    for index in range(count):
        next_index = (index + 1) % count
        for ring_index in range(len(rings)):
            cage.add_beam(columns[(index, ring_index)], columns[(next_index, ring_index)])
            if ring_index > 0:
                cage.add_beam(columns[(index, ring_index - 1)], columns[(index, ring_index)])
        for ring_index in range(len(rings) - 1):
            cage.add_quad(
                [
                    columns[(index, ring_index)],
                    columns[(next_index, ring_index)],
                    columns[(next_index, ring_index + 1)],
                    columns[(index, ring_index + 1)],
                ],
                ground_model="metal",
            )
        cage.add_triangle(
            columns[(index, len(rings) - 1)],
            columns[(next_index, len(rings) - 1)],
            back_center,
            ground_model="metal",
        )
        cage.add_beam(columns[(index, len(rings) - 1)], back_center)
    # Stitch the drum to the body lattice.
    for index in (0, 3, 6, 9):
        cage.add_beam(columns[(index, 0)], body[(1, 0, 1)])
        cage.add_beam(columns[(index, 2)], body[(1, 2, 1)])

    # Entry ramp to the drum sill.
    sill_z = AXIS_Z - DRUM_R + 0.25
    ramp_l = cage.add_node(
        "ramp_ground_l", (-2.2, spec.RAMP_GROUND_Y, 0.0), fixed=True, collision=True
    )
    ramp_r = cage.add_node(
        "ramp_ground_r", (2.2, spec.RAMP_GROUND_Y, 0.0), fixed=True, collision=True
    )
    sill_l = cage.add_node("sill_l", (-2.2, -H, sill_z), fixed=True, collision=True)
    sill_r = cage.add_node("sill_r", (2.2, -H, sill_z), fixed=True, collision=True)
    cage.add_beam(ramp_l, ramp_r)
    cage.add_beam(sill_l, sill_r)
    cage.add_beam(ramp_l, sill_l)
    cage.add_beam(ramp_r, sill_r)
    cage.add_beam(sill_l, body[(0, 0, 0)])
    cage.add_beam(sill_r, body[(2, 0, 0)])
    cage.add_beam(sill_l, columns[(7, 0)])
    cage.add_beam(sill_r, columns[(11, 0)])
    cage.add_quad([ramp_l, ramp_r, sill_r, sill_l], ground_model="asphalt")
    # Bridge from the sill to the drum bottom (column 9 is at 270 degrees).
    # Only the sill span: the 8->9 drum panel is already emitted by the drum
    # interior loop, and re-adding it duplicated the exact triangles
    # (contact-force doubling, 2026-08-09 twin audit).
    cage.add_quad(
        [sill_l, sill_r, columns[(9, 0)], columns[(8, 0)]],
        ground_model="metal",
    )

    # Interactive fascia buttons (centrifuge round-15 recipe): anchors
    # 9 cm proud of the caps so the trigger boxes float in free air in
    # front of the fascia, plus a per-button orthonormal frame pair.
    panel_anchor_nodes: list[str] = []
    for button in spec.PANEL_BUTTONS:
        px, py, pz = button["position"]
        anchor = cage.add_node(
            f"panelbtn_{button['id']}",
            (px, py - 0.09, pz),
            fixed=True,
            collision=False,
            weight=20.0,
        )
        panel_anchor_nodes.append(anchor)
        for tag, off in (("fx", (0.4, 0.0, 0.0)), ("fy", (0.0, 0.0, 0.4))):
            frame_id = cage.add_node(
                f"panel{tag}_{button['id']}",
                (px + off[0], py - 0.09 + off[1], pz + off[2]),
                fixed=True,
                collision=False,
                weight=20.0,
            )
            cage.add_beam(frame_id, body[(1, 0, 2)])
    frame_x_node = cage.add_node(
        "panel_frame_x", spec.PANEL_FRAME_X, fixed=True, collision=False,
        weight=20.0,
    )
    frame_y_node = cage.add_node(
        "panel_frame_y", spec.PANEL_FRAME_Y, fixed=True, collision=False,
        weight=20.0,
    )
    for identifier in [*panel_anchor_nodes, frame_x_node, frame_y_node]:
        cage.add_beam(identifier, body[(1, 0, 2)])

    cage.set_refnodes_existing(
        ref=body[(1, 1, 0)],
        back=body[(1, 0, 0)],
        left=body[(0, 1, 0)],
        up=body[(1, 1, 1)],
    )
    cage.set_spawn_envelope(
        [
            body[(0, 0, 0)],
            body[(2, 0, 0)],
            body[(0, 2, 0)],
            body[(2, 2, 0)],
            body[(0, 0, 2)],
            body[(2, 0, 2)],
            body[(0, 2, 2)],
            body[(2, 2, 2)],
        ]
    )
    cage.auto_base_nodes()
    return cage


def main() -> None:
    bk.reset_scene()
    materials = build_materials()
    visual_objects = build_visual(materials)
    part_builds = build_parts(materials)

    parts = []
    for name, build in sorted(part_builds.items()):
        dae_path = VEHICLE_DIR / f"{MOD_ID}_{name}.dae"
        info = bk.export_part_shape(MOD_ID, name, dae_path, build["objects"], build["pivot"])
        info["path"] = f"vehicles/{MOD_ID}/{MOD_ID}_{name}.dae"
        parts.append(info)

    visual = bk.export_flexbody_visual(
        MOD_ID,
        VEHICLE_DIR / f"{MOD_ID}.dae",
        visual_objects,
        f"{MOD_ID}_visual",
    )

    cage = build_cage()
    behavior = dict(spec.BEHAVIOR)
    bk.write_handoff(
        AUTHORING_ROOT / f"{MOD_ID}.handoff.json",
        mod_id=MOD_ID,
        display_name=spec.DISPLAY_NAME,
        cage=cage,
        visual=visual,
        visual_dae_relative=f"vehicles/{MOD_ID}/{MOD_ID}.dae",
        visual_mesh_name=f"{MOD_ID}_visual",
        parts=parts,
        palette=spec.PALETTE,
        panel={
            "frame_x_node": f"{MOD_ID}_panel_frame_x",
            "frame_y_node": f"{MOD_ID}_panel_frame_y",
            "buttons": [
                {
                    "id": button["id"],
                    "title": button["title"],
                    "node": f"{MOD_ID}_panelbtn_{button['id']}",
                    "frame_x_node": f"{MOD_ID}_panelfx_{button['id']}",
                    "frame_y_node": f"{MOD_ID}_panelfy_{button['id']}",
                    "size": button.get("size", 0.7),
                }
                for button in spec.PANEL_BUTTONS
            ],
        },
        behavior={
            "tunables": behavior,
            "triggers": spec.TRIGGERS,
            "effects": spec.EFFECTS,
            "camera_distance": behavior.get("camera_distance", 30.0),
        },
    )
    bk.render_thumbnail(
        AUTHORING_ROOT / f"{MOD_ID}_thumbnail.jpg",
        camera_location=(20.0, -26.0, 12.0),
        look_at=(0.0, 0.0, 6.0),
    )
    print(f"SPIN_CYCLE_WASHER generator complete: {len(parts)} parts")


if __name__ == "__main__":
    main()
