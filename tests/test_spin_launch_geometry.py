"""Static geometry gates for the Spin Launch Kinetic Accelerator.

The pack gates prove the evidence chain and the lupa gate proves the state
machine against stubs, which have no geometry at all. Neither can answer the
question this machine actually turns on: the launch tube PIVOTS around the
chamber rim across an eight-rung elevation ladder, and nothing has ever
exercised the low half of that ladder in geometry. Every render, the selector
thumbnail, the headless default and the live default sit at 50 degrees. That
is exactly how the warning beacon came to sit inside the launch bore at 34,
39 and 45 degrees and stay invisible.

So: sweep the bore over the whole ladder and check what is standing in it.
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
from xml.etree import ElementTree

import pytest

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
MOD_KEY = "spin_launch"
MOD_ID = "ericrolph_spin_launch"
# The tube's own two parts: the barrel and the muzzle hatch bolted to its lip
# are supposed to be inside the tube envelope, and nothing else is.
TUBE_OWN_PARTS = frozenset({"tube", "muzzle"})


def load_spec():
    spec_path = PACK_ROOT / MOD_KEY / "spec.py"
    loader = importlib.util.spec_from_file_location("spin_launch_geometry_spec", spec_path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


def load_handoff() -> dict:
    path = PACK_ROOT / MOD_KEY / "authoring" / f"{MOD_ID}.handoff.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _bore_frame(spec, point, tilt_deg: float) -> tuple[float, float]:
    """Return (station down the bore, perpendicular distance from its axis).

    Both the handoff's ``source_world_position`` and its ``pivot_world`` are in
    the AUTHORED frame, which is the frame ``spec.tube_origin`` /
    ``spec.tube_axis`` are written in. The jbeam ``position`` is NOT - it has
    x and y negated into BeamNG vehicle space - and using it here silently
    mirrors the whole machine about the launch plane.
    """

    origin = spec.tube_origin(tilt_deg)
    axis = spec.tube_axis(tilt_deg)
    delta = [point[index] - origin[index] for index in range(3)]
    station = sum(delta[index] * axis[index] for index in range(3))
    perpendicular = [delta[index] - station * axis[index] for index in range(3)]
    return station, math.sqrt(sum(value * value for value in perpendicular))


def test_launch_corridor_is_clear_across_the_whole_elevation_ladder() -> None:
    """Nothing may stand inside the bore the machine promises the payload.

    TUBE_BORE_R is not an arbitrary threshold - it is the machine's own
    statement of how much clear tube the payload gets. If a fixed collision
    node or another part's pivot is inside it, one of the two is a lie.

    Two confirmed breaches at the moment, both at ends of the ladder that no
    render, thumbnail or gate has ever visited:

      tilt 34: part beacon, station 15.87 m, clearance 0.115 m
      tilt 39: part beacon, station 17.20 m, clearance 1.329 m
      tilt 72: node bore_1_00_1, station 9.55 m, clearance 2.068 m

    The beacon cannot be fixed by sliding it along the crown: the bore axis
    sweeps the whole x = 0 crown across the ladder, and every y from -8 to +10
    at that height comes within 0.64 m of it. Off the launch plane is the only
    clear ground - at |x| = OUTER_HALF_X the worst-case clearance is 5.401 m.

    bore_1_00_1 is the mid-span cage ring node on the slot's upper lip at
    theta 134.0, and the required window edge is derivable rather than
    guessable: a cylinder of radius rho about a line tangent to the payload
    circle cuts the cage circle wherever
    cos(theta - theta_release) lies between (PAYLOAD_R -/+ rho) / CAGE_BORE_R,
    so the arc the cage must not occupy is
    theta_release - [acos((PAYLOAD_R - rho)/CAGE_BORE_R),
                     acos((PAYLOAD_R + rho)/CAGE_BORE_R)].
    Over the ladder that unions to (74.997, 137.044) for the clear bore and
    (71.117, 145.580) for the barrel's outer rib. The cage window is
    (70.0, 134.0): correct at the bottom, 11.58 degrees short at the top.
    """

    spec = load_spec()
    handoff = load_handoff()
    obstacles: list[tuple[str, tuple[float, float, float]]] = [
        (f"part:{part['name']}", tuple(part["pivot_world"]))
        for part in handoff["parts"]
        if part["name"] not in TUBE_OWN_PARTS
    ]
    obstacles += [
        (f"node:{node['id']}", tuple(node["source_world_position"]))
        for node in handoff["nodes"]
        if node["collision"]
    ]
    assert len(obstacles) > 400, "the obstacle set collapsed; the gate proves nothing"

    tightest: dict[str, dict] = {}
    breaches: list[dict] = []
    for tilt_deg in spec.TILT_STEPS_DEG:
        closest = (float("inf"), "", 0.0)
        for name, point in obstacles:
            station, radius = _bore_frame(spec, point, tilt_deg)
            if not spec.TUBE_S0 <= station <= spec.TUBE_S1:
                continue
            if radius < closest[0]:
                closest = (radius, name, station)
            if radius < spec.TUBE_BORE_R:
                breaches.append({
                    "tilt_deg": tilt_deg,
                    "obstacle": name,
                    "station_m": round(station, 3),
                    "clearance_m": round(radius, 3),
                    "clear_bore_r": spec.TUBE_BORE_R,
                })
        tightest[f"{tilt_deg:g}"] = {
            "clearance_m": round(closest[0], 3),
            "obstacle": closest[1],
            "station_m": round(closest[2], 3),
        }
    print(json.dumps({"tightest_per_tilt": tightest}, sort_keys=True))
    assert not breaches, breaches


def test_no_other_part_pivot_rides_inside_the_barrel() -> None:
    """Softer envelope, different claim: the tube's STEEL, not its clear bore.

    A fixture 3.2 m off the axis clears the payload and still has the barrel
    drawn straight through it. Only the barrel's own two parts belong inside
    TUBE_RIB_R; anything else there is geometry passing through geometry, and
    it is a render defect a player sees from the pad.

    Currently red at tilt 45: part beacon, station 18.63 m, clearance 3.207 m -
    outside the 2.55 m bore but inside the 3.25 m wall. This is the third rung
    of the same beacon defect and the reason the fix is a placement change, not
    a clipped ladder.

    Necessary, not sufficient: the sonic-baffle case is slung to one side of
    the barrel (radial 4.55, half-depth 1.30, lateral +/-1.55) so the assembly
    is not axisymmetric, and a per-vertex envelope measured off the shipped
    tube.dae reaches 6.94 m in places. A cylinder cannot express that without
    swallowing legitimate lid-plate nodes at |x| = HALF_X, so this checks the
    barrel proper and leaves the outboard lobe to the eye.
    """

    spec = load_spec()
    handoff = load_handoff()
    intrusions = []
    for part in handoff["parts"]:
        if part["name"] in TUBE_OWN_PARTS:
            continue
        for tilt_deg in spec.TILT_STEPS_DEG:
            station, radius = _bore_frame(spec, tuple(part["pivot_world"]), tilt_deg)
            if spec.TUBE_S0 <= station <= spec.TUBE_S1 and radius < spec.TUBE_RIB_R:
                intrusions.append({
                    "tilt_deg": tilt_deg,
                    "part": part["name"],
                    "station_m": round(station, 3),
                    "clearance_m": round(radius, 3),
                    "barrel_r": spec.TUBE_RIB_R,
                })
    assert not intrusions, intrusions


def test_no_render_only_scale_prop_reaches_a_shipped_artefact() -> None:
    """THE THUMBNAIL BORROWS A CAR AND MUST GIVE IT BACK.

    ``create_spin_launch.add_thumbnail_scale_car`` imports cannon_car_wash's
    mini_car.dae, scaled x22, purely so the selector tile has something
    human-sized in it - the reviewer's blocking note was that nothing in the
    thumbnail says the machine throws CARS. It is imported AFTER every export
    and deleted after the render, and the generator asserts the scene is
    restored; both of those are inside one process and neither is visible
    from here.

    This is the outside check, and it is worth having because the failure is
    catastrophic and silent: a Mini welded into the visual DAE would ship in
    the flexbody, in the 28 MB zip, in the release lock and in the handoff
    hashes, and every other gate in the pack would go green on it, because
    they all compare the artefacts to each other rather than to intent.
    """

    import zipfile

    root = PACK_ROOT / MOD_KEY
    needles = ("mini_car", "minicar", "thumb_scale_car", "cannon_car_wash")
    offenders = []
    for path in sorted((root / "mod").rglob("*")):
        if not path.is_file():
            continue
        blob = path.read_bytes()
        for needle in needles:
            if needle.encode() in blob:
                offenders.append(f"{path.name}: {needle}")
    handoff = (root / "authoring" / f"{MOD_ID}.handoff.json").read_text(
        encoding="utf-8")
    for needle in needles:
        if needle in handoff:
            offenders.append(f"handoff: {needle}")
    distribution = next((root / "dist").glob("*.zip"), None)
    if distribution is not None:
        with zipfile.ZipFile(distribution) as archive:
            for member in archive.namelist():
                for needle in needles:
                    if needle in member:
                        offenders.append(f"zip member: {member}")
    assert not offenders, offenders


def _body_mesh_points(spec):
    """The SHIPPED body mesh in the authored frame (mesh x and y negated)."""

    path = (PACK_ROOT / MOD_KEY / "mod" / "vehicles" / spec.MOD_ID
            / f"{spec.MOD_ID}.dae")
    points = []
    for element in ElementTree.parse(path).iter():
        if element.tag.split("}")[-1] != "float_array":
            continue
        if not (element.get("id") or "").endswith("positions-array"):
            continue
        values = [float(token) for token in element.text.split()]
        points.extend(
            (-x, -y, z) for x, y, z
            in zip(values[0::3], values[1::3], values[2::3], strict=True))
    assert points, f"no vertex positions in {path.name}"
    return points


def _shipped_materials(spec):
    path = (PACK_ROOT / MOD_KEY / "mod" / "vehicles" / spec.MOD_ID
            / "main.materials.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _luma(rgb):
    """Rec.709 luma of a linear-ish base colour. Only used for ratios."""

    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def test_all_eight_bar_windows_read_at_rest() -> None:
    """THE POWER AND ELEVATION ROWS HAD NO SCALE ON THEM.

    Rendered before this round: four lit blocks, then bare dark panel for
    positions 5 to 8. No socket, no window, no outline - so a player could
    not tell the scale was eight wide, could not tell they were at 4 of 8,
    could not tell there was headroom, and the printed "182" over position 8
    sat above nothing at all. The mechanism is in poseMachine: an unlit
    segment is translated bar_hidden_dy = 0.16 m back through an opaque
    console body, so it simply is not there. A bar_socket surround existed at
    (0.13, 0.135, 0.145) against a panel_dark plate at (0.07, 0.06, 0.06) -
    six hundredths of albedo on a matte plate, which is nothing - and it was
    a SOLID BOX, so it had no window in it either.

    Measured on the shipped mesh: all sixteen positions must present the same
    face, and that face has to be a window - an outer bezel outline with a
    clear opening inside it - not a slab.
    """

    spec = load_spec()
    points = _body_mesh_points(spec)
    front = spec.CONSOLE_FACE_Y
    signatures = {}
    for gauge in ("pwr", "tilt"):
        row_z = spec.BAR_SEG_Z[gauge]
        for index, x in enumerate(spec.BAR_SEG_X, start=1):
            local = [point for point in points
                     if abs(point[0] - x) <= 0.085
                     and abs(point[2] - row_z) <= 0.070
                     and abs(point[1] - front) <= 0.06]
            assert local, f"{gauge}{index} has no console geometry at all"
            signatures[(gauge, index)] = frozenset(
                (round(point[0] - x, 4), round(point[1] - front, 4),
                 round(point[2] - row_z, 4)) for point in local)

    # EVERY position identical: a row where positions 5-8 are cheaper than
    # 1-4 is a row whose top half does not exist.
    for gauge in ("pwr", "tilt"):
        first = signatures[(gauge, 1)]
        for index in range(2, 9):
            assert signatures[(gauge, index)] == first, (gauge, index)

    # ...and the face is a WINDOW. The frontmost plane has to carry an outer
    # rectangle and an inner one; a solid box would carry only the outer.
    face = min(dy for _dx, dy, _dz in signatures[("pwr", 1)])
    rim = {(dx, dz) for dx, dy, dz in signatures[("pwr", 1)]
           if abs(dy - face) < 1e-9}
    outer = {(abs(dx), abs(dz)) for dx, dz in rim}
    assert len(outer) >= 2, sorted(rim)
    widest = max(outer)
    opening = min(corner for corner in outer if corner != widest)
    assert opening[0] < widest[0] and opening[1] < widest[1], (opening, widest)
    # The opening is the bit a player sees INTO: it has to be most of the
    # window, or the bezel is a picture frame with nothing in it.
    assert (opening[0] * opening[1]) / (widest[0] * widest[1]) > 0.55, (
        opening, widest)

    # ...and what sits in the opening has to be distinguishable from the
    # plate around it, which is the half the old bar_socket failed.
    materials = _shipped_materials(spec)
    lens = materials[f"{spec.MOD_ID}_bar_lens_off"]["Stages"][0]["baseColorFactor"]
    # panel_dark is textured, so its shipped factor is a tint; the palette
    # colour it tints is what the eye sees.
    plate = spec.PALETTE[f"{spec.MOD_ID}_panel_dark"]["color"][:3]
    lit = spec.PALETTE[f"{spec.MOD_ID}_bar_lit"]["color"][:3]
    # AN AMBER LENS ON A NEUTRAL PLATE SEPARATES BY HUE FIRST, and luma is
    # the wrong instrument for it - green carries 72 percent of the Rec.709
    # weighting and an amber body has almost none, so this lens reads 1.76x
    # the plate on luma and 3.14x in red. Assert the channel the contrast is
    # actually in, and assert the hue difference itself.
    assert lens[0] / plate[0] >= 2.5, (
        f"the unlit lens is {lens[0] / plate[0]:.2f}x the plate in red: it"
        " reads as panel")
    assert lens[0] / max(lens[1], 1e-6) >= 2.0, "the lens is not amber"
    assert plate[0] / max(plate[1], 1e-6) < 1.5, "the plate is not neutral"
    assert _luma(lens[:3]) > _luma(plate)
    # ...and it is still darker than the lit block, or lit and unlit look the
    # same and the row reads 8/8 at rest.
    assert _luma(lens[:3]) < 0.7 * _luma(lit)


# The pack's px-per-PLATE-METRE law, restated here rather than imported so a
# generator that changed it has to change this too. 538.9 px/m is the
# measured state a player described as "blurry all of a sudden"
# (gforce_centrifuge, 2026-08-10); 819.2 px/m is what spin_launch's own
# console plate was raised to in response.
LETTERED_PX_PER_M_MIN = 538.9

# name -> (physical width m, physical height m)
LETTERED_SURFACES = {
    "panel_legend": (2.50, 1.86),
    "dial_vel": (0.92, 0.92),
    "dial_vac": (0.92, 0.92),
    "binnacle_plate": (2.30, 0.22),
    "sign_panel": (10.0, 1.0472),
}

# DECLARED EXEMPTIONS, with their measured value and the reason. An exemption
# is a debt, not a dispensation: the test asserts the measured figure still
# matches, so the moment somebody fixes it this gate says the entry is stale.
LETTERED_EXEMPTIONS = {
    # 1024 square over a 10.00 m board. Not fixed this round - see the
    # sign_panel entry in spec.py for why a square-only texture family makes
    # `size` the wrong lever.
    "sign_panel": 102.4,
    # 1024 square over a 2.30 x 0.22 m engraved nameplate. Under the line
    # ACROSS and enormously over it DOWN (4654.5 px/m), which for a
    # two-word nameplate is the axis that carries the cap height: 1024 px
    # across about twenty characters is 51 px per character. Declared rather
    # than raised because doubling the map would spend 4x the memory on the
    # axis that is already 8.6x the line.
    "binnacle_plate": 445.2,
}


def test_every_lettered_surface_is_resolved_or_declared() -> None:
    """THE PX-PER-METRE RULE, APPLIED TO THE WIDEST LETTERED SURFACE.

    spec.py writes the law out at panel_legend - "a legend map's real
    resolution is px per PLATE METRE, not px" - and it was never applied to
    the marquee, which is the physically widest lettered surface on the
    machine: a 1024 square map across a 10.00 m board is 102.4 px/m, against
    819.2 for the console plate two metres from the same eye and 1113 for the
    dials. Nothing measured it, so nobody noticed.

    It is NOT fixed in this round and the reasoning is on the sign_panel
    entry in spec.py: texture_kit's marquee family is square-only, so `size`
    is the only lever and a 9.55:1 board throws away 90 percent of every
    texel it buys - clearing this line would need size 8192, about 90 MB
    cooked, for one sign. The right fix is a non-square marquee map, which is
    a texture_kit change. So it is DECLARED here instead of forgotten, and
    the declaration carries the measurement so it cannot go stale quietly.
    """

    spec = load_spec()
    assert 2.0 * spec.SIGN_HALF_X == pytest.approx(
        LETTERED_SURFACES["sign_panel"][0], abs=1e-6)
    assert 2.0 * spec.SIGN_HALF_Z == pytest.approx(
        LETTERED_SURFACES["sign_panel"][1], abs=1e-4)

    for name, (width, height) in LETTERED_SURFACES.items():
        entry = spec.PALETTE[f"{spec.MOD_ID}_{name}"]
        size = entry["texture"]["size"]
        across = size / width
        down = size / height
        if name in LETTERED_EXEMPTIONS:
            assert across == pytest.approx(LETTERED_EXEMPTIONS[name], abs=0.05), (
                f"{name} is now {across:.1f} px/m across, not the "
                f"{LETTERED_EXEMPTIONS[name]} px/m this exemption was written "
                "for - if it clears the line, delete the exemption")
            assert across < LETTERED_PX_PER_M_MIN, (
                f"{name} clears the line now; delete its exemption")
            continue
        assert across >= LETTERED_PX_PER_M_MIN, (
            f"{name} is {across:.1f} px/m across, under {LETTERED_PX_PER_M_MIN}")
        assert down >= LETTERED_PX_PER_M_MIN, (
            f"{name} is {down:.1f} px/m down, under {LETTERED_PX_PER_M_MIN}")


def test_the_marquee_does_not_flood_its_own_lettering() -> None:
    """THE ONLY LETTERED SURFACE ON THIS MACHINE WHOSE TYPE COULD NOT BE READ.

    Measured on the board's pixels: ink 177 against board 222, a 45-level
    delta, about 1.5:1. The console legend in the same pipeline measures 149
    levels, about 5:1. panel_legend carries no emissive; sign_panel carried
    620 nits, and that was the whole difference - a uniform emission lifts
    the ink and the board by the same amount, so it destroys contrast and
    cannot add any.

    The rung comes from the pack's own photometric ledger
    (pachinko_tower/spec.py:3615-3617): DAY_BAND (1500, 15000) is what reads
    as EMITTING in daylight and NIGHT_BAND (60, 400) is what reads as lit
    after dark. 620 sat in neither, which is the worst place for a backlit
    diffuser whose lettering is a silhouette. It belongs in the night band.

    The source texture was never the problem and this asserts that too, so a
    future flattening of the print cannot hide behind the emissive fix.
    """

    spec = load_spec()
    entry = spec.PALETTE[f"{spec.MOD_ID}_sign_panel"]
    nits = entry["stage"]["emissiveIntensityNits"]
    # The ledger's bands, restated with their citation.
    night_band = (60.0, 400.0)
    day_band_floor = 1500.0
    assert night_band[0] <= nits <= night_band[1], (
        f"sign_panel is {nits} nits: a backlit marquee belongs in the night"
        f" band {night_band}, not between the bands")
    assert nits < day_band_floor
    # The emissive itself has to stay declared, or prop_builder drops the
    # generated glow map and the panel has no night behaviour at all.
    assert len(entry["emissive"]) == 3
    materials = _shipped_materials(spec)
    stage = materials[f"{spec.MOD_ID}_sign_panel"]["Stages"][0]
    assert stage["emissiveIntensityNits"] == nits
    assert "emissiveMap" in stage, "the glow map was dropped"

    # ...and the print itself still has contrast to be flooded. Measured on
    # the shipped source: two-valued, ink 0.0929 against board 0.9482.
    numpy = pytest.importorskip("numpy")
    image = pytest.importorskip("PIL.Image")
    path = (PACK_ROOT / MOD_KEY / "textures"
            / f"{spec.MOD_ID}_sign_panel.color.png")
    with image.open(path) as handle:
        pixels = numpy.asarray(handle.convert("RGB"), dtype=numpy.float64) / 255.0
    luma = (0.2126 * pixels[..., 0] + 0.7152 * pixels[..., 1]
            + 0.0722 * pixels[..., 2])
    ink = float(numpy.mean(luma[luma <= numpy.percentile(luma, 10)]))
    board = float(numpy.mean(luma[luma >= numpy.percentile(luma, 40)]))
    assert board / ink >= 6.0, (
        f"the marquee source is only {board / ink:.1f}:1; the print itself"
        " has gone flat and no emissive setting will rescue it")


def _console_face_points(spec):
    """Console-face vertices of the SHIPPED body mesh, in the authored frame.

    The vehicle's own mesh is authored in the MESH frame - the authored frame
    with x and y negated - so the conversion is one sign change per axis.
    """

    path = (PACK_ROOT / MOD_KEY / "mod" / "vehicles" / spec.MOD_ID
            / f"{spec.MOD_ID}.dae")
    points = []
    for element in ElementTree.parse(path).iter():
        if element.tag.split("}")[-1] != "float_array":
            continue
        if not (element.get("id") or "").endswith("positions-array"):
            continue
        values = [float(token) for token in element.text.split()]
        for x, y, z in zip(values[0::3], values[1::3], values[2::3], strict=True):
            if (abs(-x - spec.CONSOLE_X) <= 2.0
                    and abs(-y - spec.CONSOLE_FACE_Y) <= 0.20):
                points.append((-x, -y, z))
    assert points, f"no console geometry in {path.name}"
    return points


def test_the_nameplate_band_is_clear_of_both_dial_silhouettes() -> None:
    """THE INSTRUMENTS MUST NOT STAND ON THE WORDS.

    The round that fixed the doubled bezel made the dial can carry the
    bezel's radius, which grew each instrument's visible disc from GAUGE_R
    (0.46) to GAUGE_BEZEL_R (0.515) without anything in the build being able
    to notice - the dial centre, the case half-height and the nameplate row
    were three unrelated literals in two files. The result shipped as
    "EXIT <>LOCITY" and "CHAMBER <>ESSURE": the cans hung 125 mm down over a
    220 mm engraved band and took the middle out of both words.

    MEASURED ON THE SHIPPED CONSOLE, because the arithmetic version of this
    could not fail. `gap >= BINNACLE_GAP` was a verbatim copy of the
    import-time assert at spec.py:1101-1102 (GAUGE_VEL_PIVOT[2] and
    GAUGE_VAC_PIVOT[2] are both GAUGE_Z, which is what that assert uses), so
    spec.py would raise on `load_spec()` and pytest would report a COLLECTION
    ERROR for the whole module. This line could never be the thing that went
    red - it could only ever agree with something that had already stopped
    the run.

    The mesh, on the other hand, does not know what spec.py intended. Directly
    under each dial centre the lowest console-face geometry is the bottom of
    the bezel can, and the highest thing below THAT is the nameplate's top
    edge. Measured 2026-08-25: bezel bottom 8.3400 m, plate top 8.3150 m,
    gap 0.0250 m - exactly BINNACLE_GAP, i.e. the console ships with no
    margin at all and any drift shows here immediately.

    The remaining assertions are read off the PIVOTS and the PLATE RECTANGLE
    rather than off the stack constants that place them, so they stay an
    independent check on the thing spec.BINNACLE_STACK asserts about itself.
    Both dials, because the two pivots are written separately and only one of
    them has to drift.
    """

    spec = load_spec()
    plate_top = spec.BINNACLE_PLATE_Z + spec.BINNACLE_PLATE_H * 0.5
    plate_bottom = spec.BINNACLE_PLATE_Z - spec.BINNACLE_PLATE_H * 0.5
    plate_x = (spec.CONSOLE_X - spec.BINNACLE_PLATE_W * 0.5,
               spec.CONSOLE_X + spec.BINNACLE_PLATE_W * 0.5)
    console = _console_face_points(spec)
    for tag, pivot in (("vel", spec.GAUGE_VEL_PIVOT),
                       ("vac", spec.GAUGE_VAC_PIVOT)):
        # The words sit at u = 0.25 and 0.75 of the plate, i.e. directly
        # under the dial centres - that is the design, so an x-only clearance
        # can never be the answer and the whole guard is the z gap.
        assert plate_x[0] <= pivot[0] <= plate_x[1], (tag, pivot)

        # A 50 mm column straight down the dial's own centre line. The
        # nameplate has no vertices there, so the lowest thing in it IS the
        # bezel can's underside.
        column = [point for point in console
                  if abs(point[0] - pivot[0]) <= 0.05
                  and spec.BINNACLE_BOTTOM_Z - 0.05 <= point[2] <= pivot[2]]
        assert column, f"the {tag} dial is not on the shipped console at all"
        bezel_bottom = min(point[2] for point in column)
        assert bezel_bottom == pytest.approx(
            pivot[2] - spec.GAUGE_BEZEL_R, abs=2e-3), (tag, bezel_bottom)

        # ...and the highest console geometry BELOW it, across the whole
        # plate, is the nameplate's top edge.
        below = [point[2] for point in console
                 if plate_x[0] - 1e-4 <= point[0] <= plate_x[1] + 1e-4
                 and point[2] < bezel_bottom - 1e-6]
        assert below, "nothing under the dials on the shipped console"
        measured_plate_top = max(below)
        gap = bezel_bottom - measured_plate_top
        assert gap >= spec.BINNACLE_GAP - 1e-9, {
            "detail": f"the {tag} dial hangs over the nameplate",
            "dial_bottom": round(bezel_bottom, 4),
            "plate_top": round(measured_plate_top, 4),
            "gap": round(gap, 4),
            "required": spec.BINNACLE_GAP,
        }
        # ...and the thing it measured really is the plate, not some
        # unrelated moulding that happened to be the nearest surface.
        assert measured_plate_top == pytest.approx(plate_top, abs=2e-3), (
            tag, measured_plate_top, plate_top)
    # ...and the band has to stay ON the case, or the fix is a plate hanging
    # in mid air under the binnacle.
    assert plate_bottom >= spec.BINNACLE_BOTTOM_Z - 1e-9, (
        plate_bottom, spec.BINNACLE_BOTTOM_Z)
    assert plate_top <= spec.BINNACLE_TOP_Z, (plate_top, spec.BINNACLE_TOP_Z)
    # The dials have to stay on it too - the cheap way to satisfy the gap is
    # to push them through the roof the status tower stands on.
    for pivot in (spec.GAUGE_VEL_PIVOT, spec.GAUGE_VAC_PIVOT):
        assert pivot[2] + spec.GAUGE_BEZEL_R <= spec.BINNACLE_TOP_Z - 0.04, (
            "the dial reaches the status tower's base flange", pivot)


def test_the_observation_ring_is_a_window_and_not_a_lamp() -> None:
    """THE PACK'S BEST VISUAL IDEA, READ OFF THE SHIPPED MATERIAL.

    A 5.2 m glazed annulus centred on the payload circle is the reason to
    stand next to this machine, and it read as a flat milky panel for three
    review rounds. Three causes, and this gate holds all three shut:

    1. NO OPACITY. prop_builder declared `translucent` and left the alpha in
       `baseColorFactor[3]`, which the v1.5 PBR material does not read - so
       the pane was FULLY OPAQUE in game. Proven live on this mod's own dial:
       adding `opacityFactor` and nothing else turned a blank disc into a
       legible instrument.
    2. SELF-LUMINOUS. Emission is unaffected by opacity, so 170 nits of
       [0.40, 0.72, 0.90] was a fixed glow laid over whatever the pane
       transmitted. A window is not a lamp.
    3. ITS OWN ALBEDO. [0.52, 0.70, 0.78] is a pale sky-blue BODY colour; at
       26 percent it measured luminance 174.1 against a 189.7 sky, i.e. the
       same tone as the lid plates it is set into. The pack's two glasses
       that work are both dark (cannon_car_wash selector_glass
       [0.03, 0.32, 0.48], gforce_centrifuge spandrel_glass
       [0.028, 0.034, 0.04]).

    Measured on the -X lid face over the pane's own pixels, isolated by an ID
    pass: 174.1 / std 12.46 / p5-p95 43.3 shipped, against 145.0 / 19.36 /
    68.7 on the built artefact - 55 percent more through-pane spread, and
    44.7 counts under the sky instead of 15.6.
    """

    materials = json.loads(
        (PACK_ROOT / MOD_KEY / "mod" / "vehicles" / MOD_ID
         / "main.materials.json").read_text(encoding="utf-8"))
    glass = materials[f"{MOD_ID}_obs_glass"]
    stage = glass["Stages"][0]
    assert glass.get("translucent") is True, glass
    assert stage.get("opacityFactor") == 0.26, stage
    assert stage["baseColorFactor"][3] == 1.0, stage
    # A pane that lays a solid shadow shadows the very interior it exists to
    # show, and it is a 5.2 m annulus over the payload circle.
    assert glass.get("castShadows") is False, glass
    for key in ("emissiveFactor", "emissive", "emissiveIntensityNits"):
        assert key not in stage, (key, stage)
    # DARKER THAN WHAT IT IS SET INTO, which is the milkiness test that a
    # per-channel literal would not survive a retint of the machine.
    pane = sum(stage["baseColorFactor"][:3])
    plate = sum(materials[f"{MOD_ID}_lid_plate"]["Stages"][0]["baseColorFactor"][:3])
    assert pane < plate * 0.5, {
        "detail": "the observation ring is as bright as the lid it is set into",
        "pane": stage["baseColorFactor"][:3], "lid_plate_sum": round(plate, 4)}
