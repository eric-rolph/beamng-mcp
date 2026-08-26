"""The pachinko_tower photometric fixture schedule and show clock.

A SEPARATE FILE ON PURPOSE. `tests/test_giant_props_pack.py` is edited by
several sessions at once and this round's delta has to stay legible against
that churn; a new module can be reviewed, re-run and reverted on its own.

Everything asserted here is either (a) a conversion that must trace to the
measured calibration law, (b) a band that must trace to a measured rung, or
(c) a structural invariant that a future edit could silently break. Nothing
here re-measures the engine - the measurements live in AGENTS.md and in the
round-9 probe artefacts, and these tests only stop the code drifting away
from them.
"""

from __future__ import annotations

import importlib.util
import json
import math
import zipfile
from pathlib import Path

import pytest

PACK = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
MOD = PACK / "pachinko_tower"


@pytest.fixture(scope="module")
def spec():
    loader = importlib.util.spec_from_file_location("pachinko_spec_photometry", MOD / "spec.py")
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# THE CONVERSION BOUNDARY
# ---------------------------------------------------------------------------


def test_calibration_law_constants(spec):
    """5000 cd == brightness 1.0, measured over 3269 of 3269 shipped paired
    instances with zero exceptions (AGENTS.md). A PointLight's intensity is
    LUMENS, so its divisor carries the 4*pi."""
    assert spec.CANDELA_PER_BRIGHTNESS == 5000.0
    assert spec.LUMENS_PER_BRIGHTNESS == pytest.approx(4.0 * math.pi * 5000.0)


def test_spot_conversion_matches_the_owners_targets(spec):
    """The commission's directional figures, converted, must land in range.

    These are the two numbers a reader is most likely to want to check by
    hand: 8500 / 5000 = 1.70 and 1200 / 5000 = 0.24.
    """
    assert spec.spot_brightness(8500.0) == 1.70
    assert spec.spot_brightness(1200.0) == 0.24
    assert spec.FIXTURE_CLASSES["centre_strobe"]["brightness"] == 1.70
    assert spec.FIXTURE_CLASSES["peg_spot"]["brightness"] == 0.24


def test_point_conversion_round_trips_its_own_anchor(spec):
    """FILL_SCALE is anchored on the marquee flood's PHOTOGRAPHED brightness of
    1.15, so converting the scaled 650 lm target back must return ~1.15.

    If this ever fails, the anchor and the scale have been edited apart and the
    schedule's one empirical number no longer means what its comment says.
    """
    fill_lm = spec.FIXTURE_CLASSES["marquee"]["fill_lumens"]
    assert spec.point_brightness(fill_lm) == pytest.approx(1.15, abs=0.002)


def test_the_k_squared_law_is_not_silently_applied(spec):
    """PROP_SCALE is published, but k^2 is deliberately NOT used for the fill.

    The schedule says so in terms; this pins it, because "someone tidied the
    comment and applied the obvious formula" is exactly how an unmeasured
    number gets into a ledger.
    """
    assert spec.PROP_SCALE == pytest.approx(48.85, abs=0.01)
    k_squared_lm = 650.0 * spec.PROP_SCALE**2
    assert spec.FIXTURE_CLASSES["marquee"]["fill_lumens"] < k_squared_lm / 10.0
    assert spec.point_brightness(k_squared_lm) > 6.0  # would exceed the clamp


# ---------------------------------------------------------------------------
# THE MEASURED BANDS
# ---------------------------------------------------------------------------


def test_every_scheduled_night_value_is_inside_the_measured_band(spec):
    """Usable night band ~60-400 nit, saturation somewhere in the open interval
    (400, 550] and NOTHING inside that interval measured. The schedule caps at
    the 320-nit rung so the show never lives on the edge of it."""
    for name, entry in spec.FIXTURE_CLASSES.items():
        if "night_nits" not in entry:
            continue
        assert spec.NIGHT_BAND[0] <= entry["night_nits"] <= spec.NIGHT_PEAK_NITS, name
    assert spec.NIGHT_PEAK_NITS == 320.0
    assert spec.NIGHT_PEAK_NITS < 400.0


def test_day_and_night_bands_do_not_overlap(spec):
    """The constraint that forces a runtime schedule to exist at all. If these
    ever overlapped, a static nits value would be sufficient and the whole
    Lua-driven design would be unnecessary complexity."""
    assert spec.NIGHT_BAND[1] < spec.DAY_BAND[0]


def test_the_brightest_surface_sits_exactly_on_the_rung(spec):
    """NIGHT_RATIO is held exact rather than rounded, because rounding it to
    four places put the brightest surface at 319.9 instead of 320.0."""
    assert spec.FIXTURE_CLASSES["playfield_edge"]["night_nits"] == spec.NIGHT_PEAK_NITS


# ---------------------------------------------------------------------------
# STRUCTURE
# ---------------------------------------------------------------------------


def test_fixture_classes_cover_the_commission(spec):
    """The owner's six classes, plus the two this review added.

    THIS TEST WAS RED ON ARRIVAL. Round 2 added `letter_flood` and never
    updated the set, so the photometry module shipped with a failing test and
    four review rounds ran without noticing - which is its own comment on how
    much of the certification was reading claims rather than running them.
    Round 3 adds `letter_plate`. Both are listed explicitly rather than
    loosening the assert to a subset, because the point of the test is that
    nobody adds a fixture class without saying so here.
    """
    assert set(spec.FIXTURE_CLASSES) == {
        "marquee",
        "playfield_edge",
        "centre_strobe",
        "peg_spot",
        "bezel",
        "gasket",
        "letter_flood",
        "letter_plate",
    }
    for entry in spec.FIXTURE_CLASSES.values():
        assert entry["si"], "every class states its SI target in words"
        assert entry["kelvin"] >= 2700


def test_spot_fixtures_are_derived_and_out_of_the_fall_volume(spec):
    """Three strobes + one spotlight per peg row, and not one of them inside a
    volume a car can occupy - the same law the twelve PointLights obey."""
    # Three strobes, one per peg row, and the eight letter floods round 2 hung
    # off the shaft flank. Also stale on arrival - see the note above.
    assert len(spec.SPOT_SPECS) == 3 + spec.PEG_ROWS + 8
    assert len({e["slot"] for e in spec.SPOT_SPECS}) == len(spec.SPOT_SPECS)
    for entry in spec.SPOT_SPECS:
        # THE LAW, not the old proxy. `y <= LAMP_TUBE_Y` only holds while every
        # fixture is on the board's front elevation; the eight letter floods are
        # on the shaft's outboard FLANK where y is irrelevant. spec.py restated
        # this correctly in round 2 and this test kept the proxy - a third
        # stale-on-arrival assertion in this module.
        assert entry["pos"][1] <= spec.LAMP_TUBE_Y + 1e-9 or entry["pos"][0] >= spec.CAR_REACH_X, (
            entry["slot"]
        )
    # Every peg spot's z is derived from the row it lights, never retyped.
    rows = [e for e in spec.SPOT_SPECS if "row" in e]
    assert len(rows) == spec.PEG_ROWS
    for entry in rows:
        assert entry["rowz"] == pytest.approx(spec.PEG_ROW_Z[entry["row"]], abs=1e-4)


def test_emissive_slots_do_not_collide_with_the_pointlight_namespace(spec):
    """`lamp_*` belongs to the twelve PointLights and the file asserts on their
    count. A driven SURFACE and the LAMP in front of it are different fixtures.
    """
    light_slots = {e["slot"] for e in spec.LIGHT_SPECS}
    emissive_slots = {e["slot"] for e in spec.EMISSIVE_SPECS}
    assert not (light_slots & emissive_slots)
    assert not any(s.startswith("lamp_") for s in emissive_slots)


def test_every_emissive_spec_names_a_real_palette_material(spec):
    for entry in spec.EMISSIVE_SPECS:
        assert entry["material"] in spec.PALETTE, entry["slot"]
        assert entry["cls"] in spec.FIXTURE_CLASSES


def test_the_write_budget_is_set_by_the_measured_cost(spec):
    """postApply() measured at 1.5-4.0 ms. Two per frame is 3-8 ms worst case.
    Anything much above this and the show costs frames; this pins the intent so
    a future 'let's just drive them all' edit fails loudly."""
    assert spec.EMISSIVE_WRITE_BUDGET <= 3
    assert spec.EMISSIVE_QUANT_STEPS >= 8


# ---------------------------------------------------------------------------
# THE PALETTE, AND THE ONE RULE THAT KILLS EMISSION DEAD
# ---------------------------------------------------------------------------


def test_no_palette_entry_has_a_four_component_emissive(spec):
    """THREE components emit; FOUR are inert and nothing rescues four - not
    `emissive: true`, not `emissiveIntensityNits`, not a value above 1.0.
    Measured at midnight on a real renderer; 486 of 486 shipped BeamNG
    emissiveFactor arrays are 3-component."""
    for name, entry in spec.PALETTE.items():
        factor = entry.get("emissive")
        if isinstance(factor, (list, tuple)):
            assert len(factor) == 3, f"{name} has {len(factor)} components"


def test_emissive_palette_entries_carry_a_day_target(spec):
    lit = {n for n, e in spec.PALETTE.items() if isinstance(e.get("emissive"), (list, tuple))}
    assert len(lit) >= 16
    for name in lit:
        stage = spec.PALETTE[name].get("stage") or {}
        assert "emissiveIntensityNits" in stage, name
        # The authored value is the DAY target and must be inside the day band.
        assert spec.DAY_BAND[0] * 0.7 <= stage["emissiveIntensityNits"] <= spec.DAY_BAND[1]


# ---------------------------------------------------------------------------
# THE GENERATED RUNTIME
# ---------------------------------------------------------------------------


def test_runtime_lua_carries_the_show_and_the_mandatory_flush(spec):
    lua = spec.LUA_BEHAVIOR
    assert "local Show =" in lua
    assert "Show.update(state, dtSim, dtReal)" in lua
    assert "behavior.update = function(state, dtSim, dtReal)" in lua
    # THE KEYSTONE CONDITION. setField alone leaves the pixel untouched;
    # postApply() is what reaches the renderer. Measured 2026-08-15.
    assert 'm:setField("emissiveIntensityNits", 0,' in lua
    assert "m:postApply()" in lua


def test_the_show_clock_has_exactly_one_accumulator(spec):
    """Drift-free BY CONSTRUCTION: one sum, everything else derived. If a
    second `+ dt` appears against the show clock, the argument is gone."""
    lua = spec.LUA_BEHAVIOR
    assert lua.count("Show.clock = Show.clock +") == 1
    assert "math.floor(Show.clock / SHOW_TICK)" in lua
    # and the beat index must be DERIVED, never counted
    assert "Show.beat = Show.beat +" not in lua


def test_every_photometric_number_in_the_runtime_arrived_by_splice(spec):
    """A derived quantity that gets retyped is the defect class this project's
    own ledger names as its leading one."""
    lua = spec.LUA_BEHAVIOR
    for slot in ("strobe_0", "strobe_1", "strobe_2"):
        assert f'slot = "{slot}"' in lua
    assert lua.count('slot = "pegspot_') == spec.PEG_ROWS
    assert lua.count('mat = "') == len(spec.EMISSIVE_SPECS)
    assert f"local EMISSIVE_WRITE_BUDGET = {spec.EMISSIVE_WRITE_BUDGET}" in lua
    assert f"local EMISSIVE_NIGHT_PEAK = {spec.NIGHT_PEAK_NITS}" in lua


# ---------------------------------------------------------------------------
# THE SHIPPED ARTEFACT
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def shipped_materials():
    zip_path = MOD / "dist" / "pachinko_tower_ericrolph.zip"
    if not zip_path.is_file():
        pytest.skip("no dist zip built")
    with zipfile.ZipFile(zip_path) as archive:
        return json.loads(archive.read("vehicles/ericrolph_pachinko_tower/main.materials.json"))


def test_shipped_emissive_materials_are_three_component(shipped_materials):
    lit = 0
    for name, definition in shipped_materials.items():
        for stage in definition.get("Stages", []):
            factor = stage.get("emissiveFactor")
            if isinstance(factor, list):
                lit += 1
                assert len(factor) == 3, f"{name}: {len(factor)} components"
                assert "emissiveIntensityNits" in stage, name
    assert lit >= 16, f"only {lit} emissive stages shipped"


def test_the_glow_maps_actually_ship(shipped_materials):
    """The cookable-suffix law: a glow map must be `<base>_glow.color.png` or
    the cooker skips it SILENTLY and the material samples nothing."""
    maps = [
        stage["emissiveMap"]
        for definition in shipped_materials.values()
        for stage in definition.get("Stages", [])
        if stage.get("emissiveMap")
    ]
    assert len(maps) >= 14
    for path in maps:
        assert path.endswith("_glow.color.png"), path
        assert ".emissive." not in path


# ---------------------------------------------------------------------------
# LEGIBILITY. THE METRIC THAT WAS MISSING.
#
# Five rounds of photometry correlated COMMANDED FLOOD BRIGHTNESS against MEAN
# PLATE LUMINANCE and passed every time, at r = +0.77 to +0.94. The same
# frames, scored for letter contrast, correlate at r = -0.78 to -0.95. The
# metric was ANTI-CORRELATED WITH THE GOAL, so it could not fail: mean plate
# luminance is precisely the quantity that rises as the glyph is erased.
#
# THE LAW, and it is general to every lit sign in this pack: CORRELATION ON
# MEAN LUMINANCE IS NEVER THE ACCEPTANCE TEST FOR A SIGN. A sign is accepted on
# whether it can be READ, and reading needs contrast between two things, which
# is a two-sample statistic. These tests are the offline half - they score the
# authored artwork before a single frame is rendered - and the capture harness
# carries the in-frame half.
# ---------------------------------------------------------------------------


def _luminance(rgb) -> float:
    return float(0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2])


def _plate_glow(spec, material: str):
    """Regenerate a plate's GLOW map and split it into glyph and field.

    The glow map is what the surface emits at night, so it - not the albedo -
    is the thing legibility after dark is a property of. The glyph mask is
    recovered from the COLOUR map, which the family composes as
    ``bg*(1-mask) + fg*mask``: projecting a texel onto the fg-bg axis inverts
    that exactly, with no second render and no assumption about the font.
    """

    import importlib.util

    import numpy as np

    loader = importlib.util.spec_from_file_location(
        "proplib_texture_kit_legibility", PACK / "proplib" / "texture_kit.py"
    )
    kit = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(kit)

    entry = spec.PALETTE[material]["texture"]
    params = dict(entry["params"])
    size = entry.get("size", 512)
    color, _height, _rough, _alpha, emissive = kit.marquee(size, np.random.default_rng(0), **params)

    fg = np.asarray(params["fg"], dtype=float)
    bg = np.asarray(params.get("bg", (0.93, 0.94, 0.95)), dtype=float)
    axis = fg - bg
    mask = ((color - bg) @ axis) / float(axis @ axis)

    lum = 0.2126 * emissive[..., 0] + 0.7152 * emissive[..., 1] + 0.0722 * emissive[..., 2]
    # Hard cores only. The anti-aliased rim is genuinely intermediate and
    # averaging it into either sample would flatter the contrast figure.
    return lum[mask > 0.9], lum[mask < 0.1]


def test_every_letter_plate_is_reverse_printed(spec):
    """THE ROUND-3 BLOCKER, as a gate.

    A plate that is both self-luminous and floodlit must be reverse-printed:
    the GLYPH is the bright half and the FIELD is the half with headroom. On
    white-field art the field emits ~0.93 of full scale, has nothing left to
    give, and every candela the chase adds goes into closing the gap to the
    glyph until Michelson contrast inside the plate reaches 0.000.

    This test fails on the artwork that shipped through five review rounds.
    """

    import numpy as np

    for k in range(8):
        material = f"{spec.MOD_ID}_sign_letter_{k}"
        ink, field = _plate_glow(spec, material)
        assert ink.size and field.size, material
        ink_lum, field_lum = float(np.mean(ink)), float(np.mean(field))
        assert ink_lum > field_lum, (
            f"{material} is NOT reverse-printed: glyph {ink_lum:.3f} is darker "
            f"than field {field_lum:.3f}. On a lit plate that is the erasure "
            f"failure - the field has no headroom and the flood closes the gap."
        )
        # HEADROOM, stated as a number. The field must sit low enough that a
        # flood can raise the plate without the field clipping first.
        assert field_lum <= 0.35, (
            f"{material}'s field emits {field_lum:.3f} of full scale before any "
            f"flood; it will clip and the glyph will be erased into it"
        )
        michelson = (ink_lum - field_lum) / (ink_lum + field_lum)
        assert michelson >= 0.5, (
            f"{material} Michelson contrast {michelson:.3f} is under the 0.5 "
            f"gate; the letter will not survive a flood"
        )


def test_the_letter_plates_wear_the_marquee_dress(spec):
    """One ink, one field, across every reverse-printed family on the machine.

    Named constants rather than repeated literals, so a future edit cannot
    drift one family back onto a white ground on its own.
    """

    assert spec.LETTER_INK == [0.97, 0.93, 0.80]
    assert spec.LETTER_FIELD == [0.55, 0.06, 0.09]
    title = spec.PALETTE[f"{spec.MOD_ID}_sign_title"]["texture"]["params"]
    assert title["fg"] == spec.LETTER_INK
    assert title["bg"] == spec.LETTER_FIELD
    for k in range(8):
        params = spec.PALETTE[f"{spec.MOD_ID}_sign_letter_{k}"]["texture"]["params"]
        assert params["fg"] is spec.LETTER_INK
        assert params["bg"] is spec.LETTER_FIELD
        assert params["text"] == "PACHINKO"[k]


def test_the_letter_plates_have_their_own_fixture_class(spec):
    """They are the only lit surface that is also floodlit, so they carry a
    lower nominal. Sharing `marquee` double-counted the light."""

    assert spec.FIXTURE_CLASSES["letter_plate"]["day_nits"] == 1200.0
    assert (
        spec.FIXTURE_CLASSES["letter_plate"]["night_nits"]
        < spec.FIXTURE_CLASSES["marquee"]["night_nits"]
    )
    letters = [e for e in spec.EMISSIVE_SPECS if e["slot"].startswith("sign_letter_")]
    assert len(letters) == 8
    assert all(e["cls"] == "letter_plate" for e in letters)


# ---------------------------------------------------------------------------
# THE MOVING SUN
# ---------------------------------------------------------------------------


def test_the_write_demand_model_names_its_two_sources(spec):
    """Round 2's model contained only the breathe, so "no mode saturates" was a
    claim about a world with a frozen time of day - which is the only world any
    capture had been taken in."""

    breathe = spec.emissive_write_demand()
    assert max(breathe.values()) <= spec.EMISSIVE_WRITE_CAP * 0.5
    # Exactly proportional to 1 / day_length, which is what makes the inverse
    # solvable in closed form.
    assert spec.emissive_tod_demand(600.0) == pytest.approx(
        spec.emissive_tod_demand(1200.0) * 2.0, rel=1e-6
    )
    assert spec.emissive_tod_demand(spec.EMISSIVE_TOD_MIN_DAY_SECONDS) == pytest.approx(
        spec.EMISSIVE_WRITE_CAP * 0.5, rel=1e-3
    )


def test_the_quantiser_bands_against_the_regime_not_the_instant(spec):
    """The fix for the dawn/dusk saturation path. If the Lua ever goes back to
    banding against the live blended nominal, every surface writes every frame
    that the sun moves."""

    lua = spec.LUA_BEHAVIOR
    assert "Emissive.nominal[spec.slot] =\n      (blend < 0.5) and spec.night or spec.day" in lua
    assert "Emissive.nominal[spec.slot] = nominal" not in lua


def test_the_runtime_band_models_the_clamp_and_the_quantiser(spec):
    """It claimed to report "the nits actually WRITTEN" and reported the
    unclamped, unquantised target. The proof it is fixed is that it now
    reproduces the MEASURED midnight marquee value exactly."""

    band = spec.emissive_runtime_band(True)
    assert band["marquee"]["attract"][0] == pytest.approx(123.5, abs=0.05)
    for cls_name, modes in band.items():
        assert set(modes) == set(spec.SHOW_MODES), cls_name
        for mode, (lo, hi) in modes.items():
            assert lo >= spec.EMISSIVE_NIGHT_FLOOR, (cls_name, mode)
            assert hi <= spec.NIGHT_PEAK_NITS, (cls_name, mode)


def test_the_spot_table_is_counted_structurally(spec):
    """The old assert counted a substring over the whole runtime with slack, and
    the hand-written Lua contributed two hits of its own."""

    lua = spec.LUA_BEHAVIOR
    table = lua[lua.index("local SPOT_SPECS = {") :]
    table = table[: table.index("\n}")]
    n = len(spec.SPOT_SPECS)
    for key in ("row = ", "letter = ", "rowz = ", "chase = "):
        assert table.count(key) == n, key
    for k in range(8):
        assert table.count(f"letter = {k},") == 1
