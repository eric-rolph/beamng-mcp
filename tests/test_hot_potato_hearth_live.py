"""Live gates for B2's hearth, on the sentinel profile only.

Three legs, each its own boot, each installing ONE of the cuts
``scratchpad/level_round/b2/recut/{main,control,hearthoff}`` through
``HOT_POTATO_LEVEL_DIST_DIR``:

* ``test_hearth_live`` (leg ``main``) -- the scene and datablock census, the ray
  gates, the four judged frames, the ember census with its ``setActive(false)``
  control, the night-light window, the audio source state, the E-line audit, and
  the 60 s frame-time window at the 23-vehicle census by day and by night.
* ``test_hearth_material_control`` (leg ``control``) -- the SAME frames with
  ``vertColor`` and ``emissive`` removed.  The soot ratio and the crust's luma and
  red excess are only meaningful against this leg; nothing is subtracted inside a
  capped frame.
* ``test_hearth_off_control`` (leg ``hearthoff``) -- the SAME 60 s windows with the
  hearth's three groups and 619 decal rows removed.  The hearth's frame-time cost is
  (main - hearthoff), measured, not estimated.

The boot fixture, the Session class, the shot recipe and the profile purges are
B1's (``test_hot_potato_level_scaffold_live``), imported read-only.  Everything is
confined to the sentinel by ``isolated_profile_lock`` and
``require_confined_profile_target`` there.
"""

from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any

import pytest

from examples.hot_potato_arena.level import hearth_spec as hs
from tests import test_hot_potato_level_scaffold_live as scaffold

pytestmark = pytest.mark.beamng_live

C = hs.C
LEVEL_ID = hs.LEVEL_ID
PERF_PATH = "ericrolph__hot__potato__b2/perf"
#: ``extensions.load`` maps a SINGLE underscore to a path separator and a DOUBLE
#: one to a literal underscore, and the module key is the load path with "/"
#: replaced by "_" -- the arena G6/G12.2 probe's own proven pair.
PERF_EXTENSION = "ericrolph__hot__potato__b2_perf"
RAY_START_Z = 400.0
RAY_LENGTH = 500.0
#: 23 vehicles is the arena's census (DESIGN.md G12); the level round spawns them on
#: the ash bed because the scenario itself does not move levels until B5.
CENSUS_VEHICLES = 23
CENSUS_MODEL = "etk800"
PERF_WINDOW_S = 60.0

#: The B0 r3 ember detector, verbatim: additive embers render with B ~= 0 while the
#: PointLight-lit ground is warm brown (B 24-41), so the blue ceiling is what tells
#: a particle from a lit surface.
EMBER_R_MIN = 120
EMBER_RB_MIN = 40
EMBER_B_MAX = 8
#: The upper third of the 1920 x 1080 S4 frame: above the ash bed, so a pixel
#: that passes the detector there is a particle, not the crust it rose from.
EMBER_SKY_BOX = (0, 0, 1920, 360)


def _leg() -> str:
    return (os.getenv("HOT_POTATO_HEARTH_LEG") or "main").strip()


def _perf_enabled() -> bool:
    """Frame-time windows only run when the operator asserts an idle box (r2)."""

    return (os.getenv("HOT_POTATO_HEARTH_PERF") or "").strip() == "1"


def _require_leg(name: str) -> None:
    if _leg() != name:
        pytest.skip(f"HOT_POTATO_HEARTH_LEG={_leg()!r}; this gate is the {name!r} leg")


def stream_refusals(report: dict[str, Any]) -> dict[str, Any]:
    """Attribute every ``skipping stream-in`` line, or refuse to pass.

    Critic r2, C2-5: three of B2's own re-cooked 2048 rock maps produced
    ``dds mip chain (12) does not match texture (11) ... skipping stream-in`` in the
    CERTIFIED control boot, the collector that exists to read exactly this had them in
    ``log.texture_stream_warnings``, and NOTHING asserted on the field -- so the report
    walked past it while D1's whole thesis was "all six now cook at 2048".

    **What r3 measured, and it is not the cook.**  Every one of B2's 24 shipped rock
    PNGs is exactly 2048 x 2048, and the message's own numbers say the DDS chain is
    correct (12 = a full 2048 chain); it is the TEXTURE OBJECT that has 11.  The
    controlled experiment is in this round's boots: moving ``_r.data`` and ``_ao.data``
    to 1024 (``hearth_textures.DATA_MAP_DIVISOR``) removed exactly those two warnings
    from the next control boot and left the 2048 ``_nm.normal`` one standing.  So the
    rule the engine is applying is "a chain longer than the texture object's is
    refused", and the object's length is set by the profile's streaming budget --
    ``settings.json GraphicTextureQuality`` is **Normal** on the sentinel.

    The gate therefore ATTRIBUTES rather than ignores.  A refusal on a map this
    round ships larger than 1024 is expected under a reduced streaming budget and is
    recorded with its shipped dimensions; anything else -- a refusal on a map that is
    1024 or smaller, a line naming a texture nobody can find, or ANY refusal at all
    once the profile is set to High -- fails.  That is the assert that was missing,
    and it is the one that would have caught r2.
    """

    import re
    import struct

    log = report.get("log")
    if log is None or "texture_stream_warnings" not in log:
        raise AssertionError("the boot produced no log summary, so the gate cannot read it")
    quality = _profile_texture_quality()
    shapes = hs.EXAMPLE_ROOT / "mod" / "levels" / hs.LEVEL_ID / hs.SHAPE_DIR
    sizes: dict[str, int] = {}
    for path in shapes.glob("*.png"):
        head = path.read_bytes()[16:24]
        sizes[path.name.upper().replace(".PNG", ".DDS")] = struct.unpack(">II", head)[0]
    attributed, unattributed = [], []
    for line in log["texture_stream_warnings"]:
        match = re.search(r"([A-Z0-9_.]+[.]DDS)", line)
        name = match.group(1) if match else ""
        px = sizes.get(name)
        row = {"texture": name, "shipped_px": px, "line": line.strip()[-160:]}
        if px is not None and px > 1024 and quality != "High":
            attributed.append(row)
        else:
            unattributed.append(row)
    result = {
        "GraphicTextureQuality": quality,
        "attributed_to_streaming_budget": attributed,
        "unattributed": unattributed,
        "shipped_px_of_refused": sorted({r["shipped_px"] for r in attributed if r["shipped_px"]}),
    }
    assert not unattributed, result
    if quality == "High":
        assert not attributed, result
    return result


def _profile_texture_quality() -> str:
    import json as _json

    user = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    if not user:
        return "unknown"
    path = Path(user) / "settings" / "settings.json"
    if not path.is_file():
        return "unknown"
    return str(_json.loads(path.read_text(encoding="utf-8")).get("GraphicTextureQuality", "?"))


#: ``queue_lua_command`` carries the whole snippet as one string, and
#: ``surface_profile`` writes about 200 characters per point, so a 300-point sweep
#: would be a 60 kB command.  Every sweep below goes through this chunker.
RAY_CHUNK = 50


def _profile(session: scaffold.Session, points: list[tuple[float, float]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for start in range(0, len(points), RAY_CHUNK):
        rows.extend(session.surface_profile(points[start : start + RAY_CHUNK]))
    return rows


def _load_level(session: scaffold.Session) -> dict[str, Any]:
    """Load the level in freeroam the way B1's own gate does, and settle it.

    ``scaffold._boot`` only opens the process; the level load is the test's job.  The
    generated scenario carries NO level id in its name so the duplicate-prefab E line
    the scenario system logs can only be BeamNGpy's own (B1's D-7 note).
    """

    from beamngpy import Scenario, Vehicle

    from examples.hot_potato_arena.level import level_writer as writer

    bng = session.bng
    levels = bng.scenario.get_levels()
    assert LEVEL_ID in levels, sorted(levels)
    scenario = Scenario(LEVEL_ID, "b2_bngpy_probe")
    player = Vehicle("b2_player", model=CENSUS_MODEL, licence="B2")
    spawn = writer.spawn_position()
    scenario.add_vehicle(player, pos=(spawn[0], spawn[1], spawn[2]), rot_quat=(0, 0, 0, 1))
    started = time.monotonic()
    bng.control.pause()
    scenario.make(bng)
    session.scenario = scenario
    session.scenario_dir = None
    bng.scenario.load(scenario, precompile_shaders=False)
    bng.scenario.start()
    bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
    bng.control.pause()
    session.register(player)
    session.step(8)
    session.marker(session.log_marker)
    return {
        "level_load_s": round(time.monotonic() - started, 1),
        "level_listing": {
            "name": levels[LEVEL_ID].name,
            "path": levels[LEVEL_ID].path,
            "size": list(levels[LEVEL_ID].size),
        },
        "player": "b2_player",
    }


# --- readings ------------------------------------------------------------------------
def _scene_census(session: scaffold.Session) -> dict[str, Any]:
    """Every hearth object read back from the scene tree, by name."""

    names = [
        *(r["name"] for r in hs.stone_records()),
        *(r["name"] for r in hs.crust_records()),
        *(r["name"] for r in hs.emitter_records()),
        *(r["name"] for r in hs.light_records()),
        *(r["name"] for r in hs.audio_records()),
    ]
    rows: dict[str, Any] = {}
    for start in range(0, len(names), 40):
        chunk = names[start : start + 40]
        body = " ".join(
            f"do local o = scenetree.findObject({name!r}); if o then local p = o:getPosition(); "
            f"out[{name!r}] = {{ok = true, cls = o:getClassName(), x = p.x, y = p.y, z = p.z, "
            "enabled = o:getField('isEnabled', 0), night = o:getField('nightLight', 0), "
            "active = o:getField('active', 0), track = o:getField('track', 0), "
            "emitter = o:getField('emitter', 0), db = o:getField('dataBlock', 0), "
            "ct = o:getField('collisionType', 0), amb = o:getField('soundAmbience', 0), "
            "ref = o:getField('referenceDistance', 0), maxd = o:getField('maxDistance', 0)} "
            f"else out[{name!r}] = {{ok = false}} end end "
            for name in chunk
        )
        rows.update(session.lua("local out = {}; " + body + "return jsonEncode(out)"))
    return rows


def _datablock_census(session: scaffold.Session) -> dict[str, Any]:
    wanted = [
        *(n for d in hs.particle_datablock_files().values() for n in d),
        *hs.sfx_datablock_file()[1],
        *hs.decal_datablock_file()[1],
        # the controls: these three must STAY missing (B0's law)
        "EmberEmitter",
        "EmberNode",
        "EmberParticle",
        # the stock sets the fire / smoke / steam nodes name
        "BNGP_Fire_Huge",
        "BNGP_6",
        "BNGP_24",
        "lightExampleEmitterNodeData1",
        "amb_windtrees_01",
        "amb_birds_01",
    ]
    body = " ".join(
        f"do local o = scenetree.findObject({name!r}); "
        f"out[{name!r}] = o and o:getClassName() or false end "
        for name in wanted
    )
    counts = (
        "local function n(c) local g = scenetree.findClassObjects(c); "
        "return g and #g or -1 end; "
        "local cls = {ParticleData = n('ParticleData'), "
        "ParticleEmitterData = n('ParticleEmitterData'), "
        "ParticleEmitterNodeData = n('ParticleEmitterNodeData'), "
        "SFXProfile = n('SFXProfile'), DecalData = n('DecalData'), "
        "PointLight = n('PointLight'), SpotLight = n('SpotLight'), "
        "SFXEmitter = n('SFXEmitter'), SFXSpace = n('SFXSpace'), "
        "ParticleEmitterNode = n('ParticleEmitterNode'), TSStatic = n('TSStatic')}; "
    )
    return session.lua(
        "local out = {}; " + counts + body + "return jsonEncode({found = out, class_counts = cls})"
    )


def _lane_widths_by_ray(session: scaffold.Session) -> dict[str, Any]:
    """Sweep each lane's chord at r 202 with down-rays and find the clear span.

    The stones are the only solids on this line, so a ray that lands on the terrain
    (z ~ 100) is clear and one that lands on a stone is blocked.  The clear span
    about the lane axis is the width a car meets.
    """

    out: dict[str, Any] = {}
    for lane in (60.0, 150.0, 240.0, 330.0):
        theta = math.radians(lane)
        ax, ay = math.sin(theta), math.cos(theta)
        px, py = -ay, ax  # the across-lane unit
        ox, oy = hs.bearing_point(lane, 202.0)
        offsets = [round(v * 0.5, 2) for v in range(-160, 161)]
        points = [(ox + px * d, oy + py * d) for d in offsets]
        rows = _profile(session, points)
        blocked = [abs(d) for d, row in zip(offsets, rows, strict=True) if row["ray_z"] > 101.0]
        half = min(blocked) if blocked else 80.0
        out[f"lane_{int(lane)}"] = {
            "clear_half_width_m": round(half, 2),
            "clear_width_m": round(half * 2.0, 2),
            "samples": len(points),
            "blocked_samples": len(blocked),
        }
    out["min_width_m"] = round(
        min(v["clear_width_m"] for v in out.values() if isinstance(v, dict)), 2
    )
    return out


def _stone_face_radii_by_ray(session: scaffold.Session) -> dict[str, Any]:
    """March inward along each stone's bearing until a ray stops hitting it."""

    rows = []
    for stone in hs.stones():
        _, bearing = hs.polar(float(stone["x"]), float(stone["y"]))
        radii = [round(195.0 + 0.25 * i, 2) for i in range(0, 141)]
        points = [hs.bearing_point(bearing, r) for r in radii]
        profile = _profile(session, points)
        hit = [r for r, row in zip(radii, profile, strict=True) if row["ray_z"] > 101.0]
        rows.append(
            {
                "name": stone["name"],
                "bearing": round(bearing, 3),
                "first_hit_r": min(hit) if hit else None,
                "design_inner_face_r": float(stone["r_inner"]),
                "hits": len(hit),
            }
        )
    measured = [r["first_hit_r"] for r in rows if r["first_hit_r"] is not None]
    return {
        "rows": rows,
        "stones_seen": len(measured),
        "min_first_hit_r": min(measured) if measured else None,
    }


def _object_clearance_by_ray(session: scaffold.Session) -> dict[str, Any]:
    """z - terrain z for every emitter, light and audio object, measured live."""

    rows = []
    entries = (
        [("emitter", r["name"], r["position"]) for r in hs.emitter_records()]
        + [("light", r["name"], r["position"]) for r in hs.light_records()]
        + [("audio", r["name"], r["position"]) for r in hs.audio_records()]
    )
    points = [(float(p[0]), float(p[1])) for _, _, p in entries]
    profile = _profile(session, points)
    for (kind, name, position), row in zip(entries, profile, strict=True):
        rows.append(
            {
                "kind": kind,
                "name": name,
                "z": round(float(position[2]), 3),
                "ray_z": round(float(row["ray_z"]), 3),
                "delta": round(float(position[2]) - float(row["ray_z"]), 3),
            }
        )
    return {"rows": rows, "min_delta": round(min(r["delta"] for r in rows), 3), "count": len(rows)}


def _box_stats(path: Path, box: tuple[int, int, int, int]) -> dict[str, float]:
    """Mean luma and red excess in one pixel box (B0's A9 instrument, verbatim)."""

    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        data = np.asarray(image.convert("RGB")).astype(np.float32)
    x0, y0, x1, y1 = box
    patch = data[y0:y1, x0:x1]
    luma = patch[:, :, 0] * 0.299 + patch[:, :, 1] * 0.587 + patch[:, :, 2] * 0.114
    red_excess = patch[:, :, 0] - (patch[:, :, 1] + patch[:, :, 2]) / 2.0
    return {
        "box": list(box),
        "luma_mean": round(float(luma.mean()), 3),
        "luma_p90": round(float(np.percentile(luma, 90)), 3),
        "red_excess_mean": round(float(red_excess.mean()), 3),
        "red_excess_p90": round(float(np.percentile(red_excess, 90)), 3),
        "rgb_mean": [round(float(patch[:, :, i].mean()), 2) for i in range(3)],
    }


def _ember_census(path: Path, box: tuple[int, int, int, int] | None = None) -> dict[str, Any]:
    """B0 r3's detector: R >= 120 & R-B >= 40 & B <= 8, pixels and 8-connected blobs."""

    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        data = np.asarray(image.convert("RGB")).astype(np.int32)
    if box:
        x0, y0, x1, y1 = box
        data = data[y0:y1, x0:x1]
    red, blue = data[:, :, 0], data[:, :, 2]
    mask = (red >= EMBER_R_MIN) & ((red - blue) >= EMBER_RB_MIN) & (blue <= EMBER_B_MAX)
    pixels = int(mask.sum())
    # 8-connected blob count, iterative flood fill
    seen = np.zeros_like(mask, dtype=bool)
    blobs = 0
    ys, xs = np.nonzero(mask)
    height, width = mask.shape
    for sy, sx in zip(ys.tolist(), xs.tolist(), strict=True):
        if seen[sy, sx]:
            continue
        blobs += 1
        stack = [(sy, sx)]
        seen[sy, sx] = True
        while stack:
            cy, cx = stack.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
    return {
        "detector": f"R>={EMBER_R_MIN} & R-B>={EMBER_RB_MIN} & B<={EMBER_B_MAX}",
        "pixels": pixels,
        "blobs": blobs,
        "frame_px": [int(mask.shape[1]), int(mask.shape[0])],
        "box": list(box) if box else None,
    }


def _prepare_camera(session: scaffold.Session) -> dict[str, Any]:
    """Make the free camera, THEN set the FOV, THEN read it back.

    B0's law is "commands.setFreeCamera() FIRST, then core_camera.setFOV(nil, 60)".
    Issuing both in ONE Lua chunk is not first-then: boot 2 logged
    ``Unrecognized parameter camId`` once per frame, which is exactly what the engine
    says when setFOV runs before a free camera exists -- i.e. every frame would have
    been at the 65 deg default while the report claimed 60.  This splits the call and
    records ``getFovDeg`` beside every frame, so the number is not a claim.
    """

    session.lua("commands.setFreeCamera(); return jsonEncode({ok = true})")
    session.step(4)
    answer = session.lua(
        f"core_camera.setFOV(nil, {scaffold.CAMERA_FOV_DEG}); "
        "local fov = nil; pcall(function() fov = core_camera.getFovDeg() end); "
        "local cam = nil; pcall(function() cam = core_camera.getActiveCamName() end); "
        "return jsonEncode({fov = fov, cam = cam})"
    )
    session.step(2)
    return answer


def _fov_now(session: scaffold.Session) -> Any:
    answer = session.lua(
        "local fov = nil; pcall(function() fov = core_camera.getFovDeg() end); "
        "return jsonEncode({fov = fov})"
    )
    return answer.get("fov")


def _ember_difference(active: Path, inactive: Path, box: tuple[int, int, int, int] | None):
    """The ember signal = detector(active) AND NOT detector(inactive), same camera.

    On THIS map the B0 r3 detector alone cannot separate a spark from the crust: the
    crust is emissive at factor (1.0, 0.36, 0.08), so its own pixels pass
    ``B <= 8`` too (boot 2 read 308,030 px active vs 308,503 inactive -- the detector
    was measuring the bed, not the particles).  The control is therefore the SAME
    camera with every emitter ``setActive(false)``, and the reading is the
    difference mask.
    """

    import numpy as np
    from PIL import Image

    def mask_of(path: Path):
        with Image.open(path) as image:
            data = np.asarray(image.convert("RGB")).astype(np.int32)
        if box:
            x0, y0, x1, y1 = box
            data = data[y0:y1, x0:x1]
        red, blue = data[:, :, 0], data[:, :, 2]
        return (red >= EMBER_R_MIN) & ((red - blue) >= EMBER_RB_MIN) & (blue <= EMBER_B_MAX)

    def luma_of(path: Path) -> float:
        with Image.open(path) as image:
            data = np.asarray(image.convert("RGB")).astype(np.float32)
        return float((data[:, :, 0] * 0.299 + data[:, :, 1] * 0.587 + data[:, :, 2] * 0.114).mean())

    on = mask_of(active)
    off = mask_of(inactive)
    gained = on & ~off
    lost = off & ~on
    # The pair's validity check, published with the reading: two frames of the same
    # camera one toggle apart differ by ~0 in whole-frame mean luma.  A pair taken
    # across camera moves does not -- r2's first S2 pair drifted 30.2.
    drift = round(luma_of(active) - luma_of(inactive), 4)
    return {
        "detector": f"R>={EMBER_R_MIN} & R-B>={EMBER_RB_MIN} & B<={EMBER_B_MAX}",
        "box": list(box) if box else None,
        "active_px": int(on.sum()),
        "inactive_px": int(off.sum()),
        "gained_px": int(gained.sum()),
        "lost_px": int(lost.sum()),
        "gained_blobs": _blobs(gained),
        "net_px": int(on.sum()) - int(off.sum()),
        "exposure_drift_luma": drift,
        "pair_is_single_variable": abs(drift) < 1.0,
        "active_frame": active.name,
        "inactive_frame": inactive.name,
        "control": "the same camera and clock with every emitter setActive(false)",
    }


def _particle_shape(active: Path, inactive: Path, tag: str) -> dict[str, Any]:
    """What the particles LOOK like, from the same pair: how many, how big, what shape.

    The B0 detector counts the emissive BED (:func:`_ember_difference` says so); this
    reads the pair as luminance and keeps the two statistics that would have caught r1's
    defect from the numbers alone -- **bounding-box aspect** and **bounding-box fill**.
    A round soft sprite fills about half its box; r1's rendered sparks had a median fill
    of 0.875 and a median aspect of 1.00, which is a filled square, and the glow sprite
    was a 972 px rectangle at fill 0.98.  Counting was never the problem in r1; nobody
    asked the count what shape it was.

    The pair is normalised by the per-channel MEDIAN before differencing, so whatever
    eye adaptation is left between the two frames cancels instead of drowning a 5 px
    spark.  The un-normalised drift is published beside it.
    """

    import numpy as np
    from PIL import Image

    def rgb(path: Path):
        with Image.open(path) as image:
            return np.asarray(image.convert("RGB")).astype(np.float32)

    a, b = rgb(active), rgb(inactive)
    gains = []
    for channel in range(3):
        left = float(np.median(a[:, :, channel]))
        right = float(np.median(b[:, :, channel]))
        gains.append(left / right if right > 1e-3 else 1.0)
    b = np.clip(b * np.array(gains, np.float32), 0.0, 255.0)
    brighter = (a.sum(axis=2) - b.sum(axis=2)) > 30.0
    mask = brighter & (np.abs(a - b).sum(axis=2) > 30.0)
    rows = _blob_rows(mask, minimum=3)
    biggest = sorted(rows, key=lambda r: -r["px"])[:5]
    return {
        "tag": tag,
        "active_frame": active.name,
        "inactive_frame": inactive.name,
        "rule": "median-normalised: sum|dRGB| > 30 and brighter with the emitters ON",
        "median_gain_rgb": [round(g, 5) for g in gains],
        "brighter_px": int(mask.sum()),
        "darker_px": int(((b.sum(axis=2) - a.sum(axis=2)) > 30.0).sum()),
        "blobs": len(rows),
        "median_aspect": round(float(np.median([r["aspect"] for r in rows])), 4) if rows else None,
        "median_fill": round(float(np.median([r["fill"] for r in rows])), 4) if rows else None,
        "largest_blobs": biggest,
        "largest_px": biggest[0]["px"] if biggest else 0,
    }


def _settled_shot(
    session: scaffold.Session,
    name: str,
    eye: tuple[float, float, float],
    aim: tuple[float, float, float],
    note: str,
) -> Path:
    """One DISCARDED frame at this camera, then the frame that is kept.

    Measured in this round: the engine's eye adaptation is still converging when a
    shot is taken immediately after a camera move, so the first frame at a rig is not
    at the same exposure as the second.  Across an emitters-on/off pair that showed up
    as a 16.1 luma shift over the WHOLE S2 frame -- 2 million "brighter" pixels, one
    blob covering 1920x1080, and no particle in it.  Every judged frame is taken from
    the settled state so main and control frames are comparable and a pair is a pair.
    """

    session.shot(f"{name}_warmup", eye, aim, "discarded: eye-adaptation warm-up")
    return session.shot(name, eye, aim, note)


def _blob_rows(mask, minimum: int = 3) -> list[dict[str, Any]]:
    """8-connected components with bounding box, aspect (short/long) and fill."""

    import numpy as np

    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    out: list[dict[str, Any]] = []
    ys, xs = np.nonzero(mask)
    for sy, sx in zip(ys.tolist(), xs.tolist(), strict=True):
        if seen[sy, sx]:
            continue
        stack = [(sy, sx)]
        seen[sy, sx] = True
        points: list[tuple[int, int]] = []
        while stack:
            cy, cx = stack.pop()
            points.append((cy, cx))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        if len(points) < minimum:
            continue
        array = np.array(points)
        box_h = int(array[:, 0].max() - array[:, 0].min()) + 1
        box_w = int(array[:, 1].max() - array[:, 1].min()) + 1
        out.append(
            {
                "px": len(points),
                "cx": round(float(array[:, 1].mean()), 1),
                "cy": round(float(array[:, 0].mean()), 1),
                "w": box_w,
                "h": box_h,
                "aspect": round(float(min(box_w, box_h) / max(box_w, box_h)), 4),
                "fill": round(float(len(points) / (box_w * box_h)), 4),
            }
        )
    return out


def _blobs(mask) -> int:
    import numpy as np

    seen = np.zeros_like(mask, dtype=bool)
    count = 0
    ys, xs = np.nonzero(mask)
    height, width = mask.shape
    for sy, sx in zip(ys.tolist(), xs.tolist(), strict=True):
        if seen[sy, sx]:
            continue
        count += 1
        stack = [(sy, sx)]
        seen[sy, sx] = True
        while stack:
            cy, cx = stack.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
    return count


def _frame_luma(path: Path) -> dict[str, float]:
    """Whole-frame mean luma: the honest witness that a night frame IS night."""

    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        data = np.asarray(image.convert("RGB")).astype(np.float32)
    luma = data[:, :, 0] * 0.299 + data[:, :, 1] * 0.587 + data[:, :, 2] * 0.114
    return {
        "mean": round(float(luma.mean()), 3),
        "p90": round(float(np.percentile(luma, 90)), 3),
        "max": round(float(luma.max()), 1),
    }


def _set_clock(session: scaffold.Session, clock: float) -> dict[str, Any]:
    session.lua(
        f"core_environment.setTimeOfDay({{time = {clock}}}); return jsonEncode({{ok = true}})"
    )
    session.step(60)
    answer = session.lua(
        "local tod = scenetree.findObject('tod'); local sky = scenetree.findObject('sunsky'); "
        "local env = nil; pcall(function() env = core_environment.getTimeOfDay() end); "
        "local ls = nil; pcall(function() ls = core_environment.getLightState() end); "
        "return jsonEncode({time = tod and tod:getField('time', 0), "
        "azimuth = sky and sky:getField('azimuth', 0), "
        "elevation = sky and sky:getField('elevation', 0), env = env, light_state = ls})"
    )
    session.step(15)
    return answer


def _night_light_state(session: scaffold.Session) -> dict[str, Any]:
    names = [r["name"] for r in hs.light_records()]
    out: dict[str, Any] = {"enabled": 0, "disabled": 0, "missing": 0, "per_light": {}}
    for start in range(0, len(names), 40):
        chunk = names[start : start + 40]
        body = " ".join(
            f"do local o = scenetree.findObject({name!r}); "
            f"out[{name!r}] = o and o:getField('isEnabled', 0) or 'missing' end "
            for name in chunk
        )
        answer = session.lua("local out = {}; " + body + "return jsonEncode(out)")
        out["per_light"].update(answer)
    for value in out["per_light"].values():
        if value == "missing":
            out["missing"] += 1
        elif str(value) in {"1", "true"}:
            out["enabled"] += 1
        else:
            out["disabled"] += 1
    # B0 law: getField(name, 0) returns "" for a DYNAMIC field; getDynamicFields() lists
    # them.  Boot 2 read "" for both window keys and would have reported them missing.
    out["window"] = session.lua(
        "local li = scenetree.findObject('theLevelInfo'); local dyn = nil; "
        "pcall(function() dyn = li:getDynamicFields() end); "
        "local function d(k) if type(dyn) == 'table' then return dyn[k] end end; "
        "return jsonEncode({found = li ~= nil, dynamic = dyn, "
        "start = d('nightLightsNightStart'), stop = d('nightLightsNightEnd')})"
    )
    return out


def _audio_sources(session: scaffold.Session) -> dict[str, Any]:
    return session.lua(
        "local act = nil; pcall(function() act = Engine.Audio.getActiveSources() end); "
        "local out = {}; local total = 0; "
        "for _, s in ipairs(act or {}) do total = total + 1; if s.cls == 'SFXSound' then "
        "out[#out + 1] = {name = s.name, dist = s.dist, playing = s.playing, loop = s.loop, "
        "vol = s.vol, att = s.att, is3d = s.is3d} end end; "
        "return jsonEncode({sources = out, total = total, sfxsound = #out})"
    )


def _set_emitters_active(session: scaffold.Session, active: bool) -> dict[str, Any]:
    names = [r["name"] for r in hs.emitter_records()]
    body = " ".join(
        f"do local o = scenetree.findObject({name!r}); if o then "
        f"o:setField('active', 0, {str(active).lower()!r}); n = n + 1 end end "
        for name in names
    )
    answer = session.lua("local n = 0; " + body + "return jsonEncode({set = n})")
    session.step(60)
    return answer


def _load_perf(session: scaffold.Session) -> dict[str, Any]:
    answer = session.lua(
        f"local ok, err = pcall(extensions.load, {PERF_PATH!r}); "
        f"local m = extensions[{PERF_EXTENSION!r}]; "
        "return jsonEncode({ok = ok == true, has_module = m ~= nil, error = tostring(err)})"
    )
    if answer.get("has_module") is not True:
        session.problem(
            "the B2 perf instrument did not load; no frame-time number is possible", answer
        )
    return answer


def _perf_window(session: scaffold.Session, label: str, seconds: float) -> dict[str, Any]:
    """A REAL-TIME frame-time window: deterministic off, resumed, factor asserted.

    Every reading carries its physics real-time factor beside it, because a window
    run with physics free-running is not a player's load (arena G12.2's own lesson:
    two earlier windows reported factor 2.998).
    """

    session.bng.settings.set_nondeterministic()
    session.bng.control.resume()
    time.sleep(5.0)
    session.lua(f"extensions[{PERF_EXTENSION!r}].probeReset(); return jsonEncode({{ok = true}})")
    started = time.monotonic()
    time.sleep(seconds)
    snap = session.lua(f"return jsonEncode(extensions[{PERF_EXTENSION!r}].probeSnapshot())")
    wall = time.monotonic() - started
    session.bng.control.pause()
    session.bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
    frames = float(snap["frames"])
    probe_wall = float(snap["wall"]) or 1e-9
    realsum = float(snap["realsum"])
    factor = (float(snap["simsum"]) / realsum) if realsum > 0 else None
    return {
        "label": label,
        "mode": "non-deterministic (real time)",
        "frames": frames,
        "probe_wall_s": round(probe_wall, 2),
        "python_wall_s": round(wall, 1),
        "avg_fps": round(frames / probe_wall, 2) if frames else None,
        "mean_frame_ms": round(1000.0 * probe_wall / frames, 2) if frames else None,
        "worst_frame_ms": round(float(snap["maxdt"]) * 1000.0, 1),
        "frames_over_33ms": snap["over33"],
        "frames_over_67ms": snap["over66"],
        "pct_over_33ms": round(100.0 * float(snap["over33"]) / frames, 3) if frames else None,
        "physics_realtime_factor": round(factor, 3) if factor else None,
        "hist_5ms_buckets": snap.get("hist"),
    }


def _spawn_census(session: scaffold.Session) -> dict[str, Any]:
    """Put ``CENSUS_VEHICLES`` cars on the ash bed, the arena's census by count."""

    from beamngpy import Vehicle

    spawned = []
    for index in range(CENSUS_VEHICLES - 1):
        bearing = index * 360.0 / (CENSUS_VEHICLES - 1)
        x, y = hs.bearing_point(bearing, 140.0)
        name = f"b2_census_{index:02d}"
        vehicle = Vehicle(name, model=CENSUS_MODEL, license="B2")
        ok = session.bng.vehicles.spawn(
            vehicle,
            (x, y, C[2] + 0.6),
            scaffold._heading_quat((bearing + 90.0) % 360.0),
            cling=True,
            connect=False,
        )
        if ok is not True:
            session.problem(f"census vehicle {name} did not spawn")
            break
        session.register(vehicle)
        spawned.append(name)
        session.step(6)
    roster = session.lua("local all = getAllVehicles(); return jsonEncode({count = #all})")
    return {"spawned": spawned, "roster": roster, "model": CENSUS_MODEL}


def _log_audit(session: scaffold.Session) -> None:
    """Nothing to do here; ``_boot``'s teardown records the log split into the report."""


def _harvest_engine_bakes(session: scaffold.Session) -> dict[str, Any]:
    """Copy the ``.cdae`` and imposter atlases out of ``temp/`` BEFORE the purge.

    r1 generated all nineteen of them and deleted them unread with the rest of the
    profile footprint.  Two consequences the critic named: QB-8 ("every DAE ships its
    sibling ``.cdae``"), a ``stock`` item design section 13 says this level MEETS, read
    ``cdae_cov 0.125`` on B2's own cut; and the ``BB::DIM=128 / EQUATOR_STEPS=32 /
    INCLUDE_POLES=0`` recipe the report claimed was authored but never confirmed on
    B2's shapes -- the atlas that would have proved it was thrown away.  B1's backdrop
    gate already harvests its one ``.cdae`` this way; this is the same move on seven.

    The atlases are read with B3's own ``forest_build.imposter_reading`` so the number
    is comparable with the forest's, and each row carries its source DAE's sha256 so a
    later shape change makes the bake visibly stale (B3's law: an atlas can bake BLANK
    and staleness is invisible to a close-range gate).
    """

    import hashlib

    from examples.hot_potato_arena.level import forest_build as fb

    cooked = session.user / "temp" / "levels" / LEVEL_ID / hs.SHAPE_DIR
    destination = session.shot_dir.parent / "harvest"
    source_hash: dict[str, str] = {}
    shapes = hs.AUTHORING / f"{LEVEL_ID}_hearth_shapes.json"
    if shapes.is_file():
        import json

        manifest = json.loads(shapes.read_text(encoding="utf-8"))
        rows = list(manifest["stones"].values()) + (
            [manifest["crust"]] if manifest.get("crust") else []
        )
        source_hash = {Path(str(r["relative"])).name: str(r["sha256"]) for r in rows}
    files: list[dict[str, Any]] = []
    if cooked.is_dir():
        for path in sorted(cooked.iterdir()):
            if not path.is_file():
                continue
            name = path.name
            if not (name.endswith(".cdae") or ".imposter" in name):
                continue
            payload = path.read_bytes()
            destination.mkdir(parents=True, exist_ok=True)
            (destination / name).write_bytes(payload)
            dae = name.split(".dae.")[0] + ".dae" if ".dae." in name else None
            if dae is None:
                dae = name.removesuffix(".cdae") + ".dae"
            row: dict[str, Any] = {
                "name": name,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "source_dae": dae,
                "source_sha256": source_hash.get(dae),
                "saved_to": str(destination / name),
            }
            if name.endswith(".imposter.dds") or name.endswith(".imposter_normals.dds"):
                try:
                    row["atlas"] = fb.imposter_reading(payload)
                except Exception as error:  # recorded, never fatal
                    row["atlas_error"] = repr(error)
            files.append(row)
    return {
        "cooked_dir": str(cooked),
        "exists": cooked.is_dir(),
        "destination": str(destination),
        "cdae": sum(1 for r in files if r["name"].endswith(".cdae")),
        "imposters": sum(1 for r in files if ".imposter" in r["name"]),
        "files": files,
    }


# --- the legs ------------------------------------------------------------------------
def test_hearth_live(tmp_path: Path) -> None:
    """Leg ``main``: the hearth as it ships, judged and measured."""

    _require_leg("main")
    with scaffold._boot("b2main", tmp_path, watchdog_seconds=3000.0) as session:
        report = session.report
        report["load"] = _load_level(session)
        session.marker("B2 hearth gates begin")
        report["leg"] = "main"
        report["scene"] = _scene_census(session)
        report["datablocks"] = _datablock_census(session)
        report["lanes_by_ray"] = _lane_widths_by_ray(session)
        report["stone_faces_by_ray"] = _stone_face_radii_by_ray(session)
        report["object_clearance"] = _object_clearance_by_ray(session)
        report["r11_readback"] = _r11_readback(session)
        report["audio"] = _audio_sources(session)

        # --- the night window, measured against the two windows it could be -----
        # The engine's default window is 0.25-0.75 and this record's SOLAR window is
        # 0.3493-0.6896; the level authors 0.29-0.79 as LevelInfo dynamic strings.
        # 0.20 is outside all three, 0.30 discriminates the solar window, and 0.26
        # (default ON / authored OFF) and 0.77 (default OFF / authored ON) are the two
        # clocks that discriminate the authored window from the default.
        report["night_window"] = {}
        for clock in (0.20, 0.26, 0.77):
            report["night_window"][f"clock_{clock:.2f}"] = {
                "clock": _set_clock(session, clock),
                "lights": _night_light_state(session),
            }
        report["clock_020"] = report["night_window"]["clock_0.20"]["clock"]
        report["night_lights_at_020"] = report["night_window"]["clock_0.20"]["lights"]

        # --- day, clock 0.30 ---------------------------------------------------
        report["clock_030"] = _set_clock(session, 0.30)
        report["night_lights_at_030"] = _night_light_state(session)
        report["camera_030"] = _prepare_camera(session)
        for name, eye, aim, note in _day_shots():
            _settled_shot(session, name, eye, aim, note)
        report["fov_after_day_shots"] = _fov_now(session)
        # r2: the DAY A/B nobody had.  r1 blamed six white pills on lens flares and the
        # critic blamed them on the glow sprites and on track_lantern_2; both were
        # guesses from a projection near a blob.  One toggle settles it -- a blob that
        # is gone with every emitter inactive is a particle, one that stays is a light.
        #
        # **The pair is shot back to back AT ONE CAMERA.**  r2's first attempt shot the
        # two OFF frames after the whole day list, so four camera moves sat between
        # each pair's halves -- and the engine's eye adaptation had not finished
        # converging, which shifted the ENTIRE S2 frame by 30.2 luma (2,039,573 px
        # "brighter", one blob covering all 1920x1080).  A difference of two frames at
        # different exposures is not an A/B; `exposure_drift_luma` is published beside
        # every reading so the next reader can see it is ~0 and not take it on trust.
        report["day_particle_ab"] = {}
        report["day_particle_shape"] = {}
        report["emitters_off_day"] = {}
        for tag, rig in (("S4", _S4), ("S2", _S2)):
            _set_emitters_active(session, True)
            # A DISCARDED warm-up frame at this camera first.  Adjacency alone was not
            # enough: the engine's eye adaptation is still converging after a camera
            # move, so the pair's FIRST half is measurably darker/brighter than its
            # second (16.1 luma on S2, 8.4 on S4, 2.5 at night in the previous run).
            # One throwaway frame at the rig lands both halves in the converged state.
            for pass_index in range(2):
                # TWO warm-ups: one was enough for S4 (drift 8.4 -> -0.20) and not for
                # S2 (16.1 -> 9.7), because S2 follows a dark frame and the adaptation
                # ramp is longer the bigger the jump.
                session.shot(
                    f"{tag}_day_ab_warmup_{pass_index}",
                    *rig[:2],
                    "discarded: eye-adaptation warm-up",
                )
            on = session.shot(
                f"{tag}_day_emitters_on", *rig[:2], f"{tag} at 0.30, emitters ON (the A/B half)"
            )
            report["emitters_off_day"][tag] = _set_emitters_active(session, False)
            off = session.shot(
                f"{tag}_day_emitters_off",
                *rig[:2],
                f"{tag} at 0.30 with every emitter setActive(false), same camera, next frame",
            )
            report["day_particle_ab"][tag] = _ember_difference(on, off, None)
            report["day_particle_shape"][tag] = _particle_shape(on, off, f"{tag} day 0.30")
        _set_emitters_active(session, True)
        report["crust_reading_030"] = _crust_reading(session, "030")
        report["soot_reading_030"] = _soot_reading(session, "030")
        report["frame_luma_030"] = {
            name: _frame_luma(_shot_path(session, name)) for name, *_ in _day_shots()
        }

        # --- night, clock 0.50 -------------------------------------------------
        report["clock_050"] = _set_clock(session, 0.50)
        report["night_lights_at_050"] = _night_light_state(session)
        report["camera_050"] = _prepare_camera(session)
        for name, eye, aim, note in _night_shots():
            _settled_shot(session, name, eye, aim, note)
        _settled_shot(
            session, "crust_instrument_night", _CRUST_EYE, _CRUST_AIM, "the crust rig at 0.50"
        )
        report["crust_reading_050"] = _crust_reading(session, "050")
        for pass_index in range(2):
            session.shot(
                f"S4_night_ab_warmup_{pass_index}",
                *_S4[:2],
                "discarded: eye-adaptation warm-up",
            )
        s4_night = session.shot(
            "S4_ember_night", *_S4[:2], "S4's eye at clock 0.50: the ember census frame"
        )
        report["emitters_off"] = _set_emitters_active(session, False)
        off = session.shot(
            "S4_ember_night_inactive", *_S4[:2], "the same eye with every emitter setActive(false)"
        )
        report["ember_census"] = {
            "whole_frame": _ember_difference(s4_night, off, None),
            "sky_box": _ember_difference(s4_night, off, EMBER_SKY_BOX),
            "raw_active": _ember_census(s4_night),
            "raw_inactive": _ember_census(off),
            "shape": _particle_shape(s4_night, off, "night 0.50"),
        }
        report["frame_luma_050"] = {
            name: _frame_luma(_shot_path(session, name)) for name, *_ in _night_shots()
        }
        report["frame_luma_050"]["S4_ember_night"] = _frame_luma(s4_night)
        report["frame_luma_050"]["S4_ember_night_inactive"] = _frame_luma(off)
        report["fov_after_night_shots"] = _fov_now(session)
        _set_emitters_active(session, True)

        report["engine_bake_harvest"] = _harvest_engine_bakes(session)

        # --- the frame-time windows, OPT-IN (r2) -------------------------------
        # A recorded law of this round: a frame-time leg measured while another agent
        # is building or booting on the same machine is not a measurement.  r1 ran two
        # legs against a foreign BeamNG process and had to throw both away (the night
        # CONTROL came out worse than the treatment).  The window now only runs when
        # the operator asserts the box is idle, so a boot taken for FRAMES cannot
        # quietly produce a frame-time number nobody can trust.
        if _perf_enabled():
            report["perf_extension"] = _load_perf(session)
            report["census"] = _spawn_census(session)
            report["perf_night"] = _perf_window(session, "hearth on, clock 0.50", PERF_WINDOW_S)
            report["clock_030_again"] = _set_clock(session, 0.30)
            report["perf_day"] = _perf_window(session, "hearth on, clock 0.30", PERF_WINDOW_S)
        else:
            report["perf_skipped"] = {
                "why": "HOT_POTATO_HEARTH_PERF is not 1: the box was not asserted idle",
                "how_to_run": (
                    "with nothing else building or booting: "
                    "$env:HOT_POTATO_HEARTH_PERF='1'; b2/run_live_b2.ps1 main, then hearthoff"
                ),
            }
        session.marker("B2 hearth gates end")

    problems = session.report.get("problems") or []
    assert not problems, problems
    stream_refusals(session.report)  # asserts; b2/assemble_evidence.py publishes it


def test_hearth_material_control(tmp_path: Path) -> None:
    """Leg ``control``: the same frames with ``vertColor`` and ``emissive`` removed."""

    _require_leg("control")
    with scaffold._boot("b2control", tmp_path, watchdog_seconds=2000.0) as session:
        report = session.report
        report["load"] = _load_level(session)
        session.marker("B2 hearth material control begins")
        report["leg"] = "control"
        report["clock_030"] = _set_clock(session, 0.30)
        report["camera_030"] = _prepare_camera(session)
        for name, eye, aim, note in _day_shots():
            _settled_shot(session, name, eye, aim, note)
        report["crust_reading_030"] = _crust_reading(session, "030")
        report["soot_reading_030"] = _soot_reading(session, "030")
        report["frame_luma_030"] = {
            name: _frame_luma(_shot_path(session, name)) for name, *_ in _day_shots()
        }
        report["fov_after_day_shots"] = _fov_now(session)
        report["clock_050"] = _set_clock(session, 0.50)
        report["camera_050"] = _prepare_camera(session)
        for name, eye, aim, note in _night_shots():
            _settled_shot(session, name, eye, aim, note)
        _settled_shot(
            session, "crust_instrument_night", _CRUST_EYE, _CRUST_AIM, "the crust rig at 0.50"
        )
        report["crust_reading_050"] = _crust_reading(session, "050")
        report["frame_luma_050"] = {
            name: _frame_luma(_shot_path(session, name)) for name, *_ in _night_shots()
        }
        # the same harvest, so the .cdae the release ships is proven to reproduce
        # byte-for-byte on a second boot of the same shapes rather than once
        report["engine_bake_harvest"] = _harvest_engine_bakes(session)
        session.marker("B2 hearth material control ends")
    problems = session.report.get("problems") or []
    assert not problems, problems
    stream_refusals(session.report)  # asserts; b2/assemble_evidence.py publishes it


def test_hearth_off_control(tmp_path: Path) -> None:
    """Leg ``hearthoff``: the same 60 s windows with the whole hearth removed."""

    _require_leg("hearthoff")
    with scaffold._boot("b2hearthoff", tmp_path, watchdog_seconds=2400.0) as session:
        report = session.report
        report["load"] = _load_level(session)
        session.marker("B2 hearth-off control begins")
        report["leg"] = "hearthoff"
        report["scene"] = _scene_census(session)
        report["perf_extension"] = _load_perf(session)
        report["census"] = _spawn_census(session)
        report["clock_050"] = _set_clock(session, 0.50)
        report["perf_night"] = _perf_window(session, "hearth off, clock 0.50", PERF_WINDOW_S)
        report["clock_030"] = _set_clock(session, 0.30)
        report["perf_day"] = _perf_window(session, "hearth off, clock 0.30", PERF_WINDOW_S)
        session.marker("B2 hearth-off control ends")
    problems = session.report.get("problems") or []
    assert not problems, problems


# --- the camera set ------------------------------------------------------------------
def _camera(name: str) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    for camera in hs.layout()["cameras"]:
        if camera["name"].startswith(name):
            return tuple(camera["position"]), tuple(camera["look_at"])
    raise KeyError(name)


_S2 = (*_camera("S2"), "S2: the skillet bedded in coals from the trail at m 14")
_S4 = (*_camera("S4"), "S4: the driver's eye on the ash band, crust at 2-10 m")
_S5 = (*_camera("S5"), "S5: the lantern at clock 0.50")
_S6 = (*_camera("S6"), "S6: the handle at clock 0.50, both north fires through the N gaps")

#: A dedicated instrument frame: 25 m over the ring at bearing 0, tipped down so the
#: crust (r 176-199) and the bare hearth slab past r 202 are in the SAME frame, at the
#: same exposure -- B0's A9 rig, on the shipped surface.
_CRUST_EYE = (*hs.bearing_point(0.0, 176.0), C[2] + 22.0)
_CRUST_AIM = (*hs.bearing_point(0.0, 205.0), C[2] + 0.2)
#: r2: the OUTWARD rig above puts the crust and the bare ground beyond the ring in one
#: frame, but the design's own S4 rule compares the crust with the **hearth slab**
#: (r <= 175), which is behind that camera.  This second rig looks INWARD down the
#: 60 deg lane -- a gap between clusters, so no stone stands in the line -- and holds
#: crust (176-199) and slab (113-175) in the same pixels, same sun, same exposure.
_CRUST_IN_EYE = (*hs.bearing_point(60.0, 232.0), C[2] + 22.0)
_CRUST_IN_AIM = (*hs.bearing_point(60.0, 150.0), C[2] + 0.2)
#: r2 (critic r1 "Missing"): design section 8's S4 rule ends "Pass: no texel pixelation
#: at 2 m", and it is written about the EMBER PLATES ("ember plates 2-10 m") -- so the
#: 2 m frame is of the crust.  The critic also asked for a close frame of a STONE,
#: because the worst texel density is a stone's; that is the second rig, at 5 m off the
#: bounding cylinder (2 m puts the near plane inside the mesh -- measured, boot r2a).
#: ``hearth_stone_21`` is the ``namaqualand_boulder_04`` instance whose outward face the
#: 0.30 sun (az 294) actually lights.
_TEXEL_STONE = "hearth_stone_21"
_TEXEL_STAND_OFF_M = 5.0
_CRUST_2M_EYE = (*hs.bearing_point(30.0, 184.0), C[2] + 2.0)
_CRUST_2M_AIM = (*hs.bearing_point(30.0, 190.0), C[2] + 0.2)
#: A stone at 60 m, framed head-on so its foot band and its upper band are both in
#: frame: the soot instrument.
_SOOT_STONE = "hearth_stone_02"


def _stone_row(name: str) -> dict[str, Any]:
    for stone in hs.stones():
        if stone["name"] == name:
            return stone
    raise KeyError(name)


def _soot_eye() -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    stone = _stone_row(_SOOT_STONE)
    r, bearing = hs.polar(float(stone["x"]), float(stone["y"]))
    eye = (*hs.bearing_point(bearing, r - 70.0), C[2] + 12.0)
    aim = (float(stone["x"]), float(stone["y"]), float(stone["z"]) + 12.0)
    return eye, aim


def _texel_eye() -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """``_TEXEL_STAND_OFF_M`` off ``_TEXEL_STONE``'s bounding cylinder, looking at it."""

    stone = _stone_row(_TEXEL_STONE)
    radius, bearing = hs.polar(float(stone["x"]), float(stone["y"]))
    stand_off = float(stone["diam"]) / 2.0 + _TEXEL_STAND_OFF_M
    eye = (*hs.bearing_point(bearing, radius + stand_off), float(stone["z"]) + 4.0)
    aim = (float(stone["x"]), float(stone["y"]), float(stone["z"]) + 4.0)
    return eye, aim


def _day_shots() -> list[tuple[str, tuple, tuple, str]]:
    eye, aim = _soot_eye()
    texel_eye, texel_aim = _texel_eye()
    return [
        ("S2_trailhead_to_pan", _S2[0], _S2[1], _S2[2]),
        ("S4_driver_ash_band", _S4[0], _S4[1], _S4[2]),
        ("crust_instrument", _CRUST_EYE, _CRUST_AIM, "crust r 176-199 and bare ground past 202"),
        (
            "crust_slab_instrument",
            _CRUST_IN_EYE,
            _CRUST_IN_AIM,
            "inward down the 60 deg lane: crust r 176-199 AND the hearth slab r 113-175",
        ),
        ("soot_instrument", eye, aim, f"{_SOOT_STONE} head-on at 70 m: the soot bands"),
        (
            "crust_2m_instrument",
            _CRUST_2M_EYE,
            _CRUST_2M_AIM,
            "the ember plates at 2 m: design section 8's 'no texel pixelation at 2 m'",
        ),
        (
            "stone_5m_instrument",
            texel_eye,
            texel_aim,
            f"{_TEXEL_STONE} at 5 m: the round's worst texel density, close",
        ),
    ]


def _night_shots() -> list[tuple[str, tuple, tuple, str]]:
    return [
        ("S5_lantern_night", _S5[0], _S5[1], _S5[2]),
        ("S6_handle_night", _S6[0], _S6[1], _S6[2]),
    ]


def _shot_path(session: scaffold.Session, name: str) -> Path:
    return session.shot_dir / f"level_{session.boot}_{name}_{session.suffix}.png"


def _class_stats(path: Path, masks: dict[str, Any], bearing: Any, step: int) -> dict[str, Any]:
    """Mean luma / red excess per PROJECTED ground class, plus per-bearing sector means.

    The sector table is what makes the ratio shadow-honest without knowing where the
    sun is: a stone's shadow lands at one bearing and darkens BOTH classes there, so
    the median of the per-sector ratios is not the mean of two differently-shadowed
    regions.  (r1 compared one box against another box and the second box was on a
    rock; see ``hs.ground_classification``.)
    """

    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        data = np.asarray(image.convert("RGB")).astype(np.float32)[::step, ::step]
    luma = data[:, :, 0] * 0.299 + data[:, :, 1] * 0.587 + data[:, :, 2] * 0.114
    red_excess = data[:, :, 0] - (data[:, :, 1] + data[:, :, 2]) / 2.0
    # rays that never meet the ground carry NaN; they are outside every mask anyway
    sector = np.floor(np.nan_to_num(bearing, nan=-1.0) / 2.0).astype(np.int32)
    out: dict[str, Any] = {}
    per_sector: dict[str, dict[int, dict[str, float]]] = {}
    for name, mask in masks.items():
        if not mask.any():
            out[name] = {"px": 0}
            continue
        out[name] = {
            "px": int(mask.sum()),
            "luma_mean": round(float(luma[mask].mean()), 3),
            "red_excess_mean": round(float(red_excess[mask].mean()), 3),
            "rgb_mean": [round(float(data[:, :, i][mask].mean()), 2) for i in range(3)],
        }
        rows: dict[int, dict[str, float]] = {}
        for value in np.unique(sector[mask]).tolist():
            cell = mask & (sector == value)
            if int(cell.sum()) < 200:
                continue
            rows[int(value)] = {
                "px": int(cell.sum()),
                "luma": float(luma[cell].mean()),
                "red_excess": float(red_excess[cell].mean()),
            }
        per_sector[name] = rows
    out["_per_sector"] = per_sector
    return out


def _sector_ratio(per_sector: dict[str, Any], a: str, b: str, field: str) -> dict[str, Any]:
    import numpy as np

    left, right = per_sector.get(a, {}), per_sector.get(b, {})
    shared = sorted(set(left) & set(right))
    values = [left[s][field] / right[s][field] for s in shared if abs(right[s][field]) > 1e-6]
    if not values:
        return {"sectors": 0, "median": None}
    return {
        "sectors": len(values),
        "median": round(float(np.median(values)), 4),
        "p10": round(float(np.percentile(values, 10)), 4),
        "p90": round(float(np.percentile(values, 90)), 4),
    }


def _crust_reading(session: scaffold.Session, tag: str) -> dict[str, Any]:
    """The crust against real ground, in one frame, by PROJECTION -- not by pixel box.

    r1 used two fixed boxes and the critic drew them on the frame: the "slab control"
    box lay almost entirely on ``hearth_stone_02``, so the headline 1.158x / 3.068x was
    crust-vs-ROCK.  This is the fix, and it is the same fix the soot gate needed: every
    pixel's ray is intersected with the ground plane, its radius from the hearth centre
    says which band it is in, and any ray that meets a stone's cylinder first is thrown
    away.  Two rigs are read -- the outward one (crust vs the bare ground past the ring)
    and the inward one (crust vs the design's own **hearth slab**, r 113-175).
    """

    step = 2
    rigs = {
        "outward": {
            "frame": "crust_instrument_night" if tag == "050" else "crust_instrument",
            "eye": _CRUST_EYE,
            "aim": _CRUST_AIM,
            "bands": {"crust": (176.0, 199.0), "ground_beyond": (203.0, 245.0)},
            "control": "ground_beyond",
        },
    }
    if tag == "030":
        rigs["inward"] = {
            "frame": "crust_slab_instrument",
            "eye": _CRUST_IN_EYE,
            "aim": _CRUST_IN_AIM,
            "bands": {"crust": (176.0, 199.0), "hearth_slab": (113.0, 175.0)},
            "control": "hearth_slab",
        }
    out: dict[str, Any] = {
        "clock_tag": tag,
        "method": "per-pixel ground classification by projection (hs.ground_classification)",
        "b0_reference": {"luma_ratio": [1.12, 1.20], "red_excess_ratio": [2.9, 3.1]},
        "design_rule": "section 8 S4: the crust's red excess >= 2.5x the slab's",
    }
    for rig, spec in rigs.items():
        path = _shot_path(session, str(spec["frame"]))
        if not path.is_file():
            session.problem(f"the {rig} crust instrument frame is missing for {tag}")
            out[rig] = {"missing": True}
            continue
        geometry = hs.ground_classification(
            spec["eye"], spec["aim"], spec["bands"], z_plane=C[2], step=step
        )
        stats = _class_stats(path, geometry["masks"], geometry["bearing"], step)
        control = str(spec["control"])
        per_sector = stats.pop("_per_sector")
        crust, base = stats.get("crust", {}), stats.get(control, {})
        out[rig] = {
            "frame": path.name,
            "bands": geometry["bands"],
            "counts": geometry["counts"],
            "blocked_by_a_stone_px": geometry["blocked_by_a_stone_px"],
            "classes": stats,
            "control": control,
            "luma_ratio": round(crust["luma_mean"] / base["luma_mean"], 4)
            if base.get("luma_mean")
            else None,
            "red_excess_ratio": round(crust["red_excess_mean"] / base["red_excess_mean"], 4)
            if base.get("red_excess_mean")
            else None,
            "luma_ratio_by_sector": _sector_ratio(per_sector, "crust", control, "luma"),
            "red_excess_ratio_by_sector": _sector_ratio(per_sector, "crust", control, "red_excess"),
        }
    return out


#: World-height bands on the soot stone: the critic's own two, kept so r1, the critic's
#: reading and r2 are the same measurement.  ``SOOT_RADIUS_FRACTION`` keeps the mask
#: inside the rock's silhouette (0.55 reached past its shoulder into the sky).
SOOT_BANDS = {"foot": (100.5, 103.5), "upper": (116.0, 122.0)}
SOOT_RADIUS_FRACTION = 0.45


def _soot_reading(session: scaffold.Session, tag: str) -> dict[str, Any]:
    """The stone's foot band vs its upper band -- by PROJECTION, not by pixel box.

    r1's boxes sat partly on the ash below the stone, which is why two runs of
    identical content disagreed (0.705 and 1.009).  Here every pixel's ray is
    intersected with the stone's own core cylinder and binned by the WORLD z of the
    hit, so the two bands are the two heights the bake grades between and nothing
    else.  A ratio below 1 is consistent with the bake; only the ``control`` leg (the
    same frame with ``vertColor`` removed) turns it into a measurement, and the number
    that survives a difference in exposure between two boots is the DOUBLE ratio
    (foot main/control over upper main/control), computed offline in ``b2/r2/soot_ab2.py``.
    """

    path = _shot_path(session, "soot_instrument")
    if not path.is_file():
        session.problem(f"the soot instrument frame is missing for {tag}")
        return {"missing": True}
    eye, aim = _soot_eye()
    geometry = hs.stone_band_classification(
        eye, aim, _SOOT_STONE, SOOT_BANDS, radius_fraction=SOOT_RADIUS_FRACTION, step=2
    )
    import numpy as np

    stats = _class_stats(path, geometry["masks"], np.zeros_like(geometry["world_z"]), 2)
    stats.pop("_per_sector", None)
    foot, upper = stats.get("foot", {}), stats.get("upper", {})
    return {
        "frame": path.name,
        "clock_tag": tag,
        "stone": _SOOT_STONE,
        "asset": geometry["asset"],
        "method": "hs.stone_band_classification (projected world-z bands on the stone)",
        "bands_world_z": geometry["bands_world_z"],
        "counts": geometry["counts"],
        "on_stone_px": geometry["on_stone_px"],
        "bands": stats,
        "foot_over_upper_luma": round(foot["luma_mean"] / upper["luma_mean"], 4)
        if upper.get("luma_mean")
        else None,
        "bake": {
            "floor": hs.SOOT_FLOOR,
            "top_m": hs.SOOT_TOP_M,
            "in_the_dae": "srgb-pre-compensated BYTE_COLOR: the DAE carries the floor itself",
        },
    }


def _r11_readback(session: scaffold.Session) -> dict[str, Any]:
    """R11: the four fires and the S6 camera within 1.0 m of ``layout.json``.

    The design's own margins are 0.64 deg / 0.55 deg = 3.6 m / 3.0 m across the line
    of sight, so a 3 m placement error hides a fire; this reads the placed objects
    back before the S6 frame is judged.
    """

    rows = []
    for fire in hs.layout()["fires"]:
        node = hs.object_name(f"{fire['name']}_fire")
        answer = session.lua(
            f"local o = scenetree.findObject({node!r}); if not o then "
            "return jsonEncode({ok = false}) end; local p = o:getPosition(); "
            "return jsonEncode({ok = true, x = p.x, y = p.y, z = p.z})"
        )
        if answer.get("ok"):
            error = math.hypot(
                float(answer["x"]) - float(fire["x"]), float(answer["y"]) - float(fire["y"])
            )
        else:
            error = None
        rows.append(
            {
                "fire": fire["name"],
                "node": node,
                "read": answer,
                "xy_error_m": round(error, 4) if error is not None else None,
            }
        )
    camera = next(c for c in hs.layout()["cameras"] if c["name"].startswith("S6"))
    return {
        "fires": rows,
        # NOT ``r["xy_error_m"] or 99.0``: a perfect 0.0 m is falsy and the first cut of
        # this line reported 99.0 m for four fires that had read back exactly.
        "max_fire_xy_error_m": max(
            (99.0 if r["xy_error_m"] is None else r["xy_error_m"]) for r in rows
        ),
        "s6_camera_authored": camera["position"],
        "s6_camera_used": list(_S6[0]),
        "s6_camera_error_m": round(math.dist(camera["position"], list(_S6[0])), 4),
    }
