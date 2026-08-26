"""The pressure envelope has to be closed everywhere it is not a door.

The chamber's openings are made by OMITTING angular spans of the revolved
shell and bore, never by boolean difference - cut_openings' bevel-after-
boolean tombstone in blender_kit forbids the alternative. That idiom is
right, and it has one failure mode: an omission removes the FULL profile
width over the FULL arc, while whatever plugs it is a different shape.
Nothing in the build complains. The DAE exports, the cage bakes, the mod
ships, and the player parks in the airlock looking at open sky through the
wall of a vacuum chamber.

Measured on the first cut (2026-08-24): the airlock omission was one
authored arc, (207.0, 233.981), applied to both the bore (r = 20.4) and the
shell (r = 21.6). The tunnel that plugs it is a box, |x| <= 3.4 capped at
z = 8.4. That left 5.964 deg of bore and 3.923 deg of shell standing above
the soffit with nothing over them, ran the shell 4.173 deg past the floor to
z = 2.029, and left a 0.80 m strip open on each flank of each surface -
11.97 m^2 of bore and 11.39 m^2 of shell. The generator's comment claimed
the tunnel "runs a little past the tunnel proper so the omitted shell arc
never shows an open edge". True, and useless: the overrun is in Y, and the
arc escapes the rectangle in X and Z.

Separately, SLOT_DEG was cut out of the BORE liner as well as the shell -
22.79 m of arc by 8.40 m, 191 m^2 of the one surface the payload looks at
for the whole ride, with nothing at bore radius behind it.

So this file is arithmetic, not promises: every omitted arc is sampled and
every sample has to land inside the thing that plugs it, and the generator
is read to confirm it still asks for the arcs the arithmetic covers.
"""

from __future__ import annotations

import ast
import importlib.util
import itertools
import math
from pathlib import Path
from xml.etree import ElementTree

import pytest

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
MOD_KEY = "spin_launch"
GENERATOR = PACK_ROOT / MOD_KEY / "blender" / "create_spin_launch.py"


def _load_spec():
    path = PACK_ROOT / MOD_KEY / "spec.py"
    loader = importlib.util.spec_from_file_location("spin_launch_envelope_spec", path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


spec = _load_spec()


def yz(theta_deg: float, radius: float) -> tuple[float, float]:
    """Authored (y, z) of a point on the chamber circle."""

    theta = math.radians(theta_deg)
    return radius * math.cos(theta), spec.HUB_Z + radius * math.sin(theta)


def samples(arc, count: int = 1440):
    start, end = arc
    return [start + (end - start) * i / count for i in range(count + 1)]


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(GENERATOR.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} has gone from {GENERATOR.name}")


def _arcs_excluding_calls(func: ast.FunctionDef) -> set[tuple[str, ...]]:
    found = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "arcs_excluding":
            found.add(tuple(a.attr for a in node.args if isinstance(a, ast.Attribute)))
    return found


def _calls(func: ast.FunctionDef) -> set[str]:
    return {getattr(n.func, "id", None) for n in ast.walk(func) if isinstance(n, ast.Call)}


# --- the airlock omission -------------------------------------------------
# The two surfaces are parametrized by NAME and resolved at call time, not by
# reading spec at import time. TUNNEL_BORE_DEG and TUNNEL_SHELL_DEG do not
# exist until the two-arc fix lands, and an AttributeError raised at module
# scope is a COLLECTION error - pytest treats one of those as fatal for the
# whole session, so this file would take the entire static suite down with it
# and hide the very reds it was written to show. Resolved inside the test the
# same missing name is one red test that names it: a finding, not an outage.
# The assertions are untouched.
TUNNEL_SURFACES = [
    pytest.param("TUNNEL_BORE_DEG", "CHAMBER_R", id="bore"),
    pytest.param("TUNNEL_SHELL_DEG", "SHELL_R", id="shell"),
]


@pytest.mark.parametrize("arc_name, radius_name", TUNNEL_SURFACES)
def test_the_omitted_arc_ends_exactly_on_the_tunnel_s_clear_rectangle(arc_name, radius_name):
    """Not "about the right place" - ON it, to floating-point.

    An arc that stops a degree short of the soffit is 1.8 m of open wall at
    this radius, and an arc that runs a degree past the floor is the sill
    tombstone on TUNNEL_FLOOR_DEG. Both edges are solved, so both are exact.
    """

    arc = getattr(spec, arc_name)
    radius = getattr(spec, radius_name)
    assert yz(arc[0], radius)[1] == pytest.approx(spec.TUNNEL_TOP_Z, abs=1e-9)
    assert yz(arc[1], radius)[1] == pytest.approx(spec.DECK_Z, abs=1e-9)


def test_the_sill_angles_land_on_the_chords_the_tunnel_was_cut_to():
    """The bore and shell sills are the same chord TUNNEL_Y_IN/OUT solve.

    If these ever disagree, the liner's cut edge, the tunnel floor's leading
    edge and the deck's leading edge have stopped meeting on one line.
    """

    assert yz(spec.TUNNEL_BORE_DEG[1], spec.CHAMBER_R)[0] == pytest.approx(
        spec.TUNNEL_Y_IN, abs=1e-9
    )
    assert yz(spec.TUNNEL_SHELL_DEG[1], spec.SHELL_R)[0] == pytest.approx(
        spec.TUNNEL_Y_OUT, abs=1e-9
    )


@pytest.mark.parametrize("arc_name, radius_name", TUNNEL_SURFACES)
def test_no_omitted_point_lies_outside_the_thing_that_plugs_it(arc_name, radius_name):
    """The whole defect in one assertion.

    The plug is a box. Every point of the hole has to be inside it - in Z
    (soffit and floor), and in Y (the wall/soffit overrun). X is not
    checkable here because the box is NARROWER than the hole by construction;
    that is what the spandrels are for, and it has its own test below.
    """

    arc = getattr(spec, arc_name)
    radius = getattr(spec, radius_name)
    for theta in samples(arc):
        y, z = yz(theta, radius)
        assert spec.DECK_Z - 1e-9 <= z <= spec.TUNNEL_TOP_Z + 1e-9, theta
        assert spec.TUNNEL_Y_FAR - 1e-9 <= y <= spec.TUNNEL_Y_NEAR + 1e-9, theta


def test_the_floor_slab_reaches_both_sills():
    """The floor stops at TUNNEL_Y_IN, so both sills must be at or beyond it."""

    for arc, radius in (
        (spec.TUNNEL_BORE_DEG, spec.CHAMBER_R),
        (spec.TUNNEL_SHELL_DEG, spec.SHELL_R),
    ):
        y = yz(arc[1], radius)[0]
        assert spec.TUNNEL_Y_FAR <= y <= spec.TUNNEL_Y_IN + 1e-9, (arc, y)


def test_the_plug_is_narrower_than_the_hole_so_the_spandrels_are_mandatory():
    """0.80 m per flank, per surface. 11.97 m^2 + 11.39 m^2 if they go away."""

    assert spec.TUNNEL_HALF_X < spec.HALF_X
    assert "build_tunnel_spandrels" in _calls(_function("build_chamber"))


def test_the_shell_and_the_bore_omit_their_own_arcs_and_the_liner_keeps_the_slot():
    """Three regressions in one parse.

    - one shared arc for two radii (the crown and toe holes),
    - the slot cut out of the bore liner (191 m^2),
    - and any future re-merge of the two.
    """

    assert _arcs_excluding_calls(_function("build_chamber")) == {
        ("SLOT_DEG", "TUNNEL_SHELL_DEG"),
        ("TUNNEL_BORE_DEG",),
    }


# --- the launch slot ------------------------------------------------------
def _shell_mesh_points():
    """The SHIPPED body mesh, converted to the authored frame.

    The vehicle's own mesh is authored in the MESH frame - the authored frame
    with x and y negated, which is the same flip PROP_REF_OFFSET carries - so
    the conversion is one sign change per axis. Cross-checked on the ramp
    foot: authored RAMP_Y0 = -76.0 appears here at y = +76.0.
    """

    path = PACK_ROOT / MOD_KEY / "mod" / "vehicles" / spec.MOD_ID / f"{spec.MOD_ID}.dae"
    points = []
    for element in ElementTree.parse(path).iter():
        if element.tag.split("}")[-1] != "float_array":
            continue
        if not (element.get("id") or "").endswith("positions-array"):
            continue
        values = [float(token) for token in element.text.split()]
        points.extend(
            (-x, -y, z) for x, y, z in zip(values[0::3], values[1::3], values[2::3], strict=True)
        )
    assert points, f"no vertex positions in {path.name}"
    return points


def _polar(point):
    """(chamber radius, theta in degrees) of an authored-frame point."""

    return (
        math.hypot(point[1], point[2] - spec.HUB_Z),
        math.degrees(math.atan2(point[2] - spec.HUB_Z, point[1])) % 360.0,
    )


def test_the_shingle_leaves_span_the_whole_omitted_arc():
    """THE LEAVES, MEASURED OFF THE MESH THAT SHIPS.

    What this test used to do could not fail. Every line of it reduced to
    ``lap > 0``: ``start - span*lap <= start`` and ``end + span*lap >= end``
    are true for any positive span and lap, and so is
    ``covered[i+1][0] < covered[i][1]``, which expands to
    ``start + span*(i+1-lap) < start + span*(i+1+lap)``. It restated the
    algebra in spec.py's own comment back at spec.py and never once looked at
    a leaf.

    So this reads the 30 leaves out of the shipped body mesh instead. Each
    one sits at its own radius (SLOT_LEAF_R0 + SLOT_LEAF_STEP*i), which is
    what makes them separable, and the vertices at that radius inside a
    window around the opening give the leaf's true angular span. Measured
    2026-08-25: all 30 present, every span within 0.002 deg of the rule, the
    union running 62.636 to 144.404 against a SLOT_DEG of 63.568 to 143.472,
    and 1.8644 deg of lap between neighbours.
    """

    start, end = spec.SLOT_DEG
    span = (end - start) / spec.SLOT_LEAVES
    lap = spec.SLOT_LEAF_OVERLAP
    points = _shell_mesh_points()
    # A window one leaf-span wide either side of the opening. Wide enough to
    # hold every leaf including its lap, narrow enough to exclude the shell
    # furniture that happens to share a leaf's radius elsewhere on the ring.
    window = [
        point
        for point in points
        if abs(point[0]) <= spec.SLOT_LEAF_HALF_X + 1e-3
        and start - span <= _polar(point)[1] <= end + span
        and spec.SLOT_LEAF_R0 - 1e-3 <= _polar(point)[0] <= spec.SLOT_LEAF_R_MAX + 1e-3
    ]
    assert window, "no leaf geometry at all in the shipped mesh"

    measured = []
    for index in range(spec.SLOT_LEAVES):
        radius = spec.SLOT_LEAF_R0 + spec.SLOT_LEAF_STEP * index
        # Three tenths of a step: the leaves are 12 mm apart radially, so this
        # separates leaf i from leaf i+1 without catching a neighbour's edge
        # bevel, which half a step does.
        leaf = [
            point for point in window if abs(_polar(point)[0] - radius) <= 0.3 * spec.SLOT_LEAF_STEP
        ]
        assert leaf, f"leaf {index} is missing from the shipped mesh at r={radius:.3f}"
        angles = [_polar(point)[1] for point in leaf]
        measured.append((min(angles), max(angles)))
        expected = (start + span * (index - lap), start + span * (index + 1.0 + lap))
        assert measured[-1][0] == pytest.approx(expected[0], abs=0.002), index
        assert measured[-1][1] == pytest.approx(expected[1], abs=0.002), index

    # The union has to be a SUPERSET of the hole, and the leaves have to lap
    # rather than merely abut - a butt joint is a gap the first time anything
    # in this chain rounds.
    assert min(edge[0] for edge in measured) <= start
    assert max(edge[1] for edge in measured) >= end
    for previous, following in itertools.pairwise(measured):
        overlap = previous[1] - following[0]
        assert overlap > 0.0, (previous, following)
        assert overlap == pytest.approx(2.0 * span * lap, abs=0.004), overlap


def test_the_shingle_leaves_span_the_whole_profile_width():
    """A leaf narrower than the shell is a slot you can see into edge-on.

    ``SLOT_LEAF_HALF_X >= OUTER_HALF_X`` could not fail: spec.py:323 DEFINES
    SLOT_LEAF_HALF_X as ``OUTER_HALF_X + 0.10``. Both half-widths are
    measured off the shipped mesh here instead - the shell's in three clean
    sectors well away from the slot and the airlock, the leaves' inside the
    opening. Measured 2026-08-25: shell 5.4000 m in all three sectors, leaves
    5.5000 m.
    """

    points = _shell_mesh_points()
    start, end = spec.SLOT_DEG
    shell_widths = []
    for sector in ((10.0, 45.0), (150.0, 195.0), (300.0, 340.0)):
        band = [
            point
            for point in points
            if abs(_polar(point)[0] - spec.SHELL_R) <= 0.01
            and sector[0] <= _polar(point)[1] <= sector[1]
        ]
        assert band, sector
        shell_widths.append(max(abs(point[0]) for point in band))
    # The profile is a revolve, so the three sectors must agree.
    assert max(shell_widths) - min(shell_widths) < 1e-6, shell_widths

    leaves = [
        point
        for point in points
        if start <= _polar(point)[1] <= end
        and spec.SLOT_LEAF_R0 - 1e-3 <= _polar(point)[0] <= spec.SLOT_LEAF_R_MAX + 1e-3
    ]
    assert leaves, "no leaf geometry inside the opening"
    assert max(abs(point[0]) for point in leaves) >= max(shell_widths) - 1e-9, (
        "the shingles are narrower than the shell they close"
    )


def test_the_leaf_stack_is_closed_on_both_flanks():
    """The stack stands up to 0.448 m proud of plates that stop at SHELL_R.

    Without cheeks that is a 0.448 m by 24.38 m annulus open on each side,
    21.84 m^2, running the whole 64 degrees.
    """

    source = ast.dump(_function("build_slot"))
    assert "slot_cheek_" in source


def test_the_tube_pierce_stays_inside_the_slot_at_every_tilt():
    """The slot has to be long enough for the collar at both extremes."""

    for tilt in spec.TILT_STEPS_DEG:
        pierce = spec.release_theta_deg(tilt) - spec.TANGENT_OFFSET_OUT_DEG
        assert spec.SLOT_DEG[0] < pierce < spec.SLOT_DEG[1], (tilt, pierce)
