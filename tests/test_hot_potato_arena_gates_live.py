"""Live gate ladder G1-G6 for the Gateway Skillet arena (design v3 / v3.1 section 8).

Every gate boots ONE owned BeamNG process on the sentinel-isolated profile,
installs the LOCKED Hot Potato dist zip and the LOCKED arena dist zip (both
hash-verified; the arena lock's depends_on must equal the Hot Potato lock),
loads the SHIPPED scenario through the game's own list, runs measured
assertions, saves normal-exposure player-class screenshots into
HOT_POTATO_ARENA_GATE_SHOT_ROOT/G<n>/ with an index.json, and cleans the
profile (zips, settings, snapshot, screenshots, compiled arena cache).

Gates:
  G1 site truth   - player-camera shots (bowl floor, mid-bank, glacis, crest,
                    halo on/off diff, tethers with the halo off), far-field
                    floor band metric over >= 6 frames at 300 m plus the
                    critic's control-zip boot (floor DAE with _a70 removed) as
                    a second session, glacis-foot drive-offs at three bearings
                    with a ray-sampled toe profile (no lip, no void).
  G2 surface      - crawl (1.1 m/s) and 2 m/s lines on the wall bank, both
                    ramps up and down, the merge fillet, pools (ICE) and salt
                    (SAND) with wheel-contact readouts and braking decels, the
                    r 88.5 tangential line, the r 86 / bearing 45 jamb drift,
                    the stall discriminator, a driven figure-eight turning
                    circle for the heaviest supported class, crest ram runs at
                    60/85/110 km/h with magnet haul-back.
  G3 AI           - 3 min chase/flee against the 42 registered obstacles with
                    a damage-witnessed collision census, the braked-hulk haul
                    through a spout with the release feel at 82.3 m, classic
                    spout-spam, hold-mode spout-spam (out-of-ring accrual must
                    be zero), and the magnet-orbit attempt with the
                    arena_magnet_g 2.0 lever on failure.
  G4 geysers      - per-site pop assertions at all three sites, horizontal
                    speed preserved on a moving car, spout entry during ON
                    recovers within 5 s.
  G5 round        - the multi-vehicle round on the arena: crash-recovery boot,
                    pickup, ram transfer, tag-back hold, a REAL 120 s / 180 s
                    stall through the decay valve (radius 75 -> 60, halo
                    measured from above), fuse to boom, return flight, winner
                    fireworks over the arch, restore at round end, Exit
                    scenario hand-back byte-equal.
  G6 perf/culling - 23 vehicles + AI + geysers, 60 s real-time frame log via a
                    throwaway probe extension zip, orbit at 150/250/400 m with
                    per-arc hide diffs (renders), same-camera frame diffs (no
                    seam popping) and crest rays (collides).

Log-strict: zero |E| lines from the runtime or the arena, and MPCoreNetwork
stays silent. The F-P1.10 self-acceleration anomaly is watched for on every
driven line (a car re-accelerating with no throttle after a brake hold).
"""

from __future__ import annotations

import json
import math
import os
import shutil
import threading
import time
import uuid
import zipfile
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any

import pytest
from beamngpy import BeamNGpy, Vehicle

from examples.hot_potato_arena import build_distribution as arena_dist
from examples.hot_potato_arena import sync_scenario_outputs as sync
from tests import test_hot_potato_arena_live as smoke
from tests.live_support import (
    claim_owned_beamng_process,
    cleanup_exact_live_artifacts,
    cleanup_owned_beamng_session,
    isolated_profile_lock,
    namespace_conflicts,
    require_confined_profile_target,
    reserve_loopback_ports,
)

MOD_ID = sync.MOD_ID
RUNTIME = smoke.RUNTIME_EXTENSION
C = sync.CENTER
R_ARENA = sync.ARENA_RADIUS_M
R_RELEASE = round(R_ARENA * 0.9, 2)  # 82.26 m: the magnet lifts here
CREST_R = 91.4
GLACIS_TOE_R = 113.0
PLAYER = sync.PLAYER_NAME
AI = [f"{MOD_ID}_ai_{i}" for i in range(1, 6)]
DISPENSER = sync.DISPENSER_NAME
PROBE_ID = "ericrolph_arena_gate_probe"
PROBE_EXTENSION = "ericrolph__arena__gate__probe_perf"
# One control.step() advances ~3 physics frames of sim at the 60 Hz deterministic
# setting (probe fact F-P1.9; G2 run 2 measured 0.3 s per step(6)), so two steps
# is the 0.1 s controller tick.
STEP_TICK = 2
FUSE_VISIBLE = {"show_countdown": True, "tick_style": "escalating"}
LONG_FUSE = {
    "fuse_base_seconds": 550,
    "fuse_sigma_seconds": 0,
    "fuse_min_seconds": 500,
    "fuse_max_seconds": 600,
}
DEFAULT_SHOT_ROOT = (
    Path(os.getenv("HOT_POTATO_ARENA_GATE_SHOT_ROOT", ""))
    if os.getenv("HOT_POTATO_ARENA_GATE_SHOT_ROOT")
    else None
)
CONTROL_ZIP = os.getenv("HOT_POTATO_ARENA_CONTROL_ZIP", "")

PERF_LUA = """-- Throwaway frame-time probe for the arena G6 gate. Never ships.
local M = {}
local clock = os.clockhp or os.clock
local S = nil
local function fresh()
  return {frames = 0, wall = 0, maxdt = 0, over33 = 0, over66 = 0, simsum = 0, realsum = 0, updates = 0, last = nil,
          hist = {}}
end
S = fresh()
function M.probeReset() S = fresh() end
function M.probeSnapshot()
  return {frames = S.frames, wall = S.wall, maxdt = S.maxdt, over33 = S.over33, over66 = S.over66,
          simsum = S.simsum, realsum = S.realsum, updates = S.updates, hist = S.hist}
end
function M.onPreRender(dtReal, dtSim, dtRaw)
  local now = clock()
  if S.last ~= nil then
    local dt = now - S.last
    S.frames = S.frames + 1
    S.wall = S.wall + dt
    if dt > S.maxdt then S.maxdt = dt end
    if dt > 0.0333 then S.over33 = S.over33 + 1 end
    if dt > 0.0667 then S.over66 = S.over66 + 1 end
    -- 5 ms histogram buckets up to 100 ms, then one overflow bucket.
    local bucket = math.min(21, math.floor(dt * 200) + 1)
    S.hist[bucket] = (S.hist[bucket] or 0) + 1
  end
  S.last = now
end
function M.onUpdate(dtReal, dtSim, dtRaw)
  S.updates = S.updates + 1
  if type(dtSim) == "number" then S.simsum = S.simsum + dtSim end
  if type(dtReal) == "number" then S.realsum = S.realsum + dtReal end
end
return M
"""


# --- geometry helpers ----------------------------------------------------------


def _bearing_xy(bearing_deg: float, r: float) -> tuple[float, float]:
    return sync.bearing_point(bearing_deg, r)


def _polar(x: float, y: float) -> tuple[float, float]:
    dx, dy = x - C[0], y - C[1]
    return math.hypot(dx, dy), math.degrees(math.atan2(dx, dy)) % 360.0


def _wrap_deg(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def _heading_quat(heading_deg: float) -> tuple[float, float, float, float]:
    """Teleport quaternion for a compass heading (0 = +Y, clockwise).

    A BeamNG vehicle faces local -Y (compass 180). MEASURED (G2 runs 2-3): the
    teleport quaternion (0, 0, sin(psi/2), cos(psi/2)) lands the nose at compass
    180 + psi, not 180 - psi (a requested 85.5 deg put the car on 274.5 and
    drove it off the handle flank), so psi = heading - 180.
    """

    psi = math.radians(heading_deg - 180.0)
    return (0.0, 0.0, math.sin(psi / 2.0), math.cos(psi / 2.0))


def _fit_circle(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Kasa least-squares circle fit -> (cx, cy, r)."""

    import numpy as np

    pts = np.asarray(points, dtype=float)
    x, y = pts[:, 0], pts[:, 1]
    a = np.column_stack([2 * x, 2 * y, np.ones_like(x)])
    b = x * x + y * y
    sol, *_ = np.linalg.lstsq(a, b, rcond=None)
    cx, cy, c0 = sol
    return float(cx), float(cy), float(math.sqrt(max(c0 + cx * cx + cy * cy, 0.0)))


def _luma(path: Path):
    import numpy as np
    from PIL import Image

    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def _rgb(path: Path):
    import numpy as np
    from PIL import Image

    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)


def _diff_pixels(a: Path, b: Path, threshold: float = 6.0) -> dict[str, Any]:
    """Pixels whose max-channel difference exceeds the threshold, with their bounding box."""

    import numpy as np

    ra, rb = _rgb(a), _rgb(b)
    if ra.shape != rb.shape:
        return {"count": -1, "detail": f"shape mismatch {ra.shape} vs {rb.shape}"}
    diff = np.abs(ra - rb).max(axis=2) > threshold
    count = int(diff.sum())
    out: dict[str, Any] = {"count": count, "fraction": count / diff.size}
    if count:
        ys, xs = np.nonzero(diff)
        out["bbox"] = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
        out["extent_x_px"] = int(xs.max() - xs.min())
        out["extent_y_px"] = int(ys.max() - ys.min())
    return out


def _amber_pixels(path: Path) -> int:
    """Pixels in the halo/tether/firework amber band: exposure-tolerant, unlike a raw frame diff."""


    rgb = _rgb(path)
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mask = (red > 140) & (red - blue > 55) & (green > 0.42 * red) & (green < 0.88 * red)
    return int(mask.sum())


def _tint_band(on: Path, off: Path, threshold: float = 6.0) -> dict[str, Any]:
    """The halo ribbon as a horizontal band of amber tint: per-row mean of (R-B)_on - (R-B)_off.

    Exposure drift moves luma, not the red-minus-blue chroma; the 22/255 amber
    wall reads as a band of rows whose mean chroma delta exceeds the threshold
    (G1 boot 2: +20 on the bowl floor, +32 at the crest, +40 from the glacis).
    """

    import numpy as np

    a, b = _rgb(on), _rgb(off)
    delta = ((a[..., 0] - a[..., 2]) - (b[..., 0] - b[..., 2])).mean(axis=1)
    rows = np.nonzero(delta > threshold)[0]
    peak = int(np.argmax(delta))
    return {
        "band_rows": len(rows),
        "peak_row": peak,
        "peak_delta_rb": round(float(delta[peak]), 2),
        "band_from": int(rows.min()) if len(rows) else None,
        "band_to": int(rows.max()) if len(rows) else None,
    }


def _tint_bbox(on: Path, off: Path, threshold: float = 12.0) -> dict[str, Any]:
    """The halo ring as amber chroma: pixel count and screen extent.

    A raw frame diff counts the exposure change over the whole frame (G5 run 2
    measured 900k "halo" pixels on a 1280x720 frame), so the ring is measured by
    red-minus-blue chroma gain instead - the same instrument G1 used.
    """

    import numpy as np

    a, b = _rgb(on), _rgb(off)
    delta = (a[..., 0] - a[..., 2]) - (b[..., 0] - b[..., 2])
    mask = delta > threshold
    out: dict[str, Any] = {"tint_pixels": int(mask.sum())}
    if out["tint_pixels"]:
        ys, xs = np.nonzero(mask)
        out.update(
            {
                "x_from": int(xs.min()),
                "x_to": int(xs.max()),
                "ring_width_px": int(xs.max() - xs.min()),
                "y_from": int(ys.min()),
                "y_to": int(ys.max()),
            }
        )
    return out


def _tint_pixels(with_path: Path, without_path: Path, threshold: float = 25.0) -> int:
    """Pixels whose red-minus-blue chroma rose by more than the threshold (bead / firework witnesses)."""


    a, b = _rgb(with_path), _rgb(without_path)
    delta = (a[..., 0] - a[..., 2]) - (b[..., 0] - b[..., 2])
    return int((delta > threshold).sum())


def _disc_median(path: Path, cx: int, cy: int, radius: int) -> float:
    import numpy as np
    from scipy.ndimage import binary_erosion

    luma = _luma(path)
    yy, xx = np.mgrid[0 : luma.shape[0], 0 : luma.shape[1]]
    mask = binary_erosion((xx - cx) ** 2 + (yy - cy) ** 2 <= radius * radius, iterations=2)
    return float(np.median(luma[mask]))


# --- the session ----------------------------------------------------------------


class Session:
    """One owned BeamNG process on the sentinel profile with the shipped scenario loaded."""

    def __init__(self, gate: str, bng: BeamNGpy, user: Path, suffix: str, shot_dir: Path) -> None:
        self.gate = gate
        self.bng = bng
        self.user = user
        self.suffix = suffix
        self.shot_dir = shot_dir
        self.report: dict[str, Any] = {"gate": gate, "suffix": suffix, "shots": []}
        self.shot_names: list[str] = []
        self._vehicles: dict[str, Vehicle] = {}
        self._clock0 = 0.0
        self.pad: tuple[float, float, float] | None = None
        self.player_id: int | None = None
        # Measured G1 boot 1: +0.6 steering for 2.5 s turned the etk800 -58 deg
        # (left), so positive input is LEFT; the controller multiplies by -1.
        self.steer_sign: float = -1.0

    # -- findings ------------------------------------------------------------
    def problem(self, detail: str, data: Any = None) -> None:
        """Record a measured defect and keep going.

        A gate's job is to MEASURE the whole ladder; a behavioural miss must not
        abort the boot and cost the rest of the evidence. Every gate asserts on
        the collected list at the end, so a miss still fails the gate.
        """

        self.report.setdefault("problems", []).append({"detail": detail, "data": data})

    def check(self, condition: bool, detail: str, data: Any = None) -> bool:
        if not condition:
            self.problem(detail, data)
        return bool(condition)

    # -- engine access ------------------------------------------------------
    def lua(self, code: str) -> dict[str, Any]:
        return smoke._lua_json(self.bng, code)

    def arena(self) -> dict[str, Any]:
        return smoke._arena_state(self.bng)

    def runtime_state(self) -> dict[str, Any]:
        return smoke._runtime_state(self.bng)

    def stats(self) -> dict[str, Any]:
        return smoke._stats(self.bng)

    def options(self) -> dict[str, Any]:
        return self.lua(f"return jsonEncode(extensions[{RUNTIME!r}].hotPotatoGetOptions())")

    def set_option(self, key: str, value: Any) -> None:
        lua_value = (
            "true"
            if value is True
            else "false"
            if value is False
            else repr(value)
            if isinstance(value, str)
            else str(value)
        )
        answer = self.lua(
            f"return jsonEncode({{ok = extensions[{RUNTIME!r}].hotPotatoSetOption({key!r}, {lua_value}) == true}})"
        )
        assert answer == {"ok": True}, {"detail": "option refused", "key": key, "value": value}

    def set_options(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            self.set_option(key, value)

    def step(self, steps: int) -> None:
        self.bng.control.step(steps, wait=True)

    def clock(self) -> float:
        """Sim seconds since the session started, from the arena extension's dtSim clock."""

        return float(self.arena()["clock"]) - self._clock0

    def wait_sim(self, seconds: float, tick: int = 30) -> None:
        target = self.clock() + seconds
        while self.clock() < target:
            self.step(tick)

    def step_until(
        self, predicate: Callable[[], bool], *, calls: int, note: str, steps: int = 15
    ) -> int:
        for index in range(calls):
            if predicate():
                return index
            self.step(steps)
        raise AssertionError(f"condition never held within {calls} step calls: {note}")

    def surface_z(self, x: float, y: float) -> float:
        return smoke._surface_z(self.bng, x, y)

    def surface_profile(
        self, points: list[tuple[float, float]], z_start: float = 200.0
    ) -> list[dict[str, float]]:
        """castRayStatic down at every point in ONE call: [{x, y, z, hit}]."""

        body = " ".join(
            f"do local s = vec3({x}, {y}, {z_start}); local d = castRayStatic(s, vec3(0, 0, -1), 400); "
            f"out[#out + 1] = {{x = {x}, y = {y}, z = s.z - d, hit = d < 399.0}} end "
            for x, y in points
        )
        answer = self.lua("local out = {}; " + body + "return jsonEncode({rows = out})")
        return [dict(row) for row in answer["rows"]]

    def probe_many(self, names: list[str]) -> dict[str, dict[str, Any]]:
        """Pose, velocity, up vector, ground clearance and map damage for many vehicles in one call."""

        body = " ".join(
            f"do local o = scenetree.findObject({name!r}); if o then "
            "local p = o:getPosition(); local v = o:getVelocity(); local d = o:getDirectionVector(); "
            "local okU, ux, uy, uz = pcall(function() local u = o:getDirectionVectorUp(); return u.x, u.y, u.z end); "
            "if not okU then ux, uy, uz = o:getDirectionVectorUpXYZ() end; "
            "local id = o:getID(); local mo = (map and map.objects) and map.objects[id] or nil; "
            "local ray = castRayStatic(vec3(p.x, p.y, p.z + 2.0), vec3(0, 0, -1), 60); "
            f"out[{name!r}] = {{ok = true, id = id, x = p.x, y = p.y, z = p.z, vx = v.x, vy = v.y, vz = v.z, "
            "speed = v:length(), dx = d.x, dy = d.y, dz = d.z, ux = ux, uy = uy, uz = uz, "
            "damage = mo and mo.damage or -1, clearance = 2.0 - ray} "
            f"else out[{name!r}] = {{ok = false}} end end "
            for name in names
        )
        answer = self.lua("local out = {}; " + body + "return jsonEncode(out)")
        for name, row in answer.items():
            if row.get("ok"):
                row["r"], row["bearing"] = _polar(float(row["x"]), float(row["y"]))
                row["hspeed"] = math.hypot(float(row["vx"]), float(row["vy"]))
                row["yaw"] = math.degrees(math.atan2(float(row["dx"]), float(row["dy"]))) % 360.0
        return answer

    def probe(self, name: str) -> dict[str, Any]:
        row = self.probe_many([name])[name]
        assert row.get("ok"), {"detail": "vehicle missing", "name": name}
        return row

    def wheel_contacts(self, name: str) -> list[str]:
        """Ground model under each wheel, read inside the vehicle VM and echoed to GE (probe P1 method)."""

        slot = uuid.uuid4().hex[:6]
        chunk = (
            "local names = {} local t = particles.getMaterialsParticlesTable() "
            "for _, w in pairs(wheels.wheels) do local m = t[w.contactMaterialID1] "
            "names[#names + 1] = (m and m.name or 'none') end "
            f"obj:queueGameEngineLua(\"rawset(_G, 'hp_gate_contact_{slot}', '\" .. table.concat(names, ',') .. \"')\")"
        )
        self.lua(
            f"rawset(_G, 'hp_gate_contact_{slot}', nil); "
            f"local v = scenetree.findObject({name!r}); if v then v:queueLuaCommand([[{chunk}]]) end; "
            "return jsonEncode({ok = true})"
        )
        self.step(4)
        answer = self.lua(
            f"return jsonEncode({{value = rawget(_G, 'hp_gate_contact_{slot}') or ''}})"
        )
        return [s for s in str(answer.get("value", "")).split(",") if s]

    # -- vehicles -----------------------------------------------------------------
    def gear(self, name: str) -> str:
        """electrics.values.gear read inside the vehicle VM and echoed to GE."""

        slot = uuid.uuid4().hex[:6]
        self.lua(
            f"rawset(_G, 'hp_gate_gear_{slot}', nil); local v = scenetree.findObject({name!r}); if v then v:queueLuaCommand("
            f"[[obj:queueGameEngineLua(\"rawset(_G, 'hp_gate_gear_{slot}', '\" .. tostring(electrics.values.gear) .. \"')\")]]) end; "
            "return jsonEncode({ok = true})"
        )
        self.step(3)
        return str(
            self.lua(f"return jsonEncode({{value = rawget(_G, 'hp_gate_gear_{slot}') or ''}})").get(
                "value", ""
            )
        )

    def ensure_drive(self, name: str) -> str:
        """Put an automatic in D before driving on throttle.

        G1 boot 2 measured: after a teleport the etk800 drove BACKWARDS on
        throttle (the steering calibration read -58 deg for +0.6 and the glacis
        drive-off went inward), so every driven line first selects the forward
        range explicitly and reads the gear string back.
        """

        # The automatic's h-shifter lookup (shiftLogic/automaticGearbox.lua:658)
        # is {[-1] = R, [0] = N, [1] = P, [2] = D, [3] = S, ...}: index 2 is D.
        gear = ""
        for _ in range(2):
            self.lua(
                f"local v = scenetree.findObject({name!r}); if v then v:queueLuaCommand("
                "'pcall(function() controller.mainController.shiftToGearIndex(2) end)') end; return jsonEncode({ok = true})"
            )
            self.step(8)
            gear = self.gear(name)
            if gear and gear[0] in ("D", "S", "1", "2", "M"):
                return gear
        return gear

    def reverse_for(self, name: str, seconds: float, throttle: float = 0.3) -> dict[str, Any]:
        """Select R (h-shifter index -1), back up on throttle, then return to D."""

        self.lua(
            f"local v = scenetree.findObject({name!r}); if v then v:queueLuaCommand("
            "'pcall(function() controller.mainController.shiftToGearIndex(-1) end)') end; return jsonEncode({ok = true})"
        )
        self.step(8)
        gear = self.gear(name)
        p0 = self.probe(name)
        ticks = max(1, int(seconds / 0.1))
        for _ in range(ticks):
            self.control(name, steering=0.0, throttle=throttle, brake=0.0, parkingbrake=0.0)
            self.step(STEP_TICK)
        self.control(name, steering=0.0, throttle=0.0, brake=1.0, parkingbrake=0.0)
        self.step(20)
        p1 = self.probe(name)
        self.ensure_drive(name)
        return {
            "gear_in_reverse": gear,
            "moved_m": math.hypot(p1["x"] - p0["x"], p1["y"] - p0["y"]),
            "uz_after": p1["uz"],
        }

    def vehicle(self, name: str) -> Vehicle:
        if name not in self._vehicles:
            current = self.bng.vehicles.get_current(include_config=False)
            vehicle = current[name]
            vehicle.connect(self.bng)
            self._vehicles[name] = vehicle
        return self._vehicles[name]

    def register(self, vehicle: Vehicle) -> None:
        self._vehicles[vehicle.vid] = vehicle

    def teleport(
        self,
        name: str,
        xy: tuple[float, float],
        heading_deg: float,
        z: float | None = None,
        reset: bool = True,
    ) -> None:
        if z is None:
            z = self.surface_z(*xy) + 0.6
        assert (
            self.bng.vehicles.teleport(
                name, (xy[0], xy[1], z), _heading_quat(heading_deg), reset=reset
            )
            is True
        )
        # The teleport lands a few frames later; settle before anyone samples the pose
        # (G2 run 1: a calibration read the pre-teleport position as its start).
        last = None
        for _ in range(12):
            self.step(STEP_TICK)
            p = self.probe(name)
            if (
                last is not None
                and math.hypot(p["x"] - last[0], p["y"] - last[1]) < 0.05
                and math.hypot(p["x"] - xy[0], p["y"] - xy[1]) < 3.0
            ):
                break
            last = (p["x"], p["y"])

    def control(self, name: str, **kwargs: Any) -> None:
        self.vehicle(name).control(**kwargs)

    def park(self, name: str) -> None:
        self.control(name, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=1.0)

    def release(self, name: str) -> None:
        self.control(name, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=0.0)

    def far_lot(self) -> tuple[float, float]:
        """A flat groundplane spot > 1.2 km from the arena (the plane ends at +-1024 m)."""

        if getattr(self, "_far_lot", None):
            return self._far_lot
        for xy in ((-500.0, 700.0), (-700.0, -700.0), (850.0, 900.0), (-800.0, 100.0)):
            rows = self.surface_profile([xy, (xy[0] + 60.0, xy[1]), (xy[0], xy[1] + 8.0)])
            if all(row["hit"] and 99.5 <= row["z"] <= 100.5 for row in rows):
                self._far_lot = xy
                return xy
        raise AssertionError("no flat far lot found on the groundplane")

    def move_away(self, names: list[str]) -> None:
        """Park cars far outside the arena (never members, never nearest targets)."""

        lot = self.far_lot()
        for index, name in enumerate(names):
            self.teleport(name, (lot[0] + 12.0 * index, lot[1]), 0.0, z=C[2] + 0.6)
            self.park(name)

    def names_by_id(self) -> dict[int, str]:
        rows = self.probe_many([PLAYER, *AI])
        return {int(row["id"]): name for name, row in rows.items() if row.get("ok")}

    def drop_round(self) -> None:
        """End a live round without a boom: reset the carrier (carrier_lost) and wait for idle."""

        st = self.stats()
        if st.get("phase") == "live":
            carrier = self.names_by_id().get(int(st.get("carrier") or -1))
            if carrier is not None:
                p = self.probe(carrier)
                assert (
                    self.bng.vehicles.teleport(
                        carrier, (p["x"], p["y"], p["z"] + 0.3), None, reset=True
                    )
                    is True
                )
        self.step_until(
            lambda: self.stats().get("phase") == "idle", calls=200, note="the round never went idle"
        )

    # -- rounds -------------------------------------------------------------------
    def start_round(self, carrier: str) -> dict[str, Any]:
        """Drive `carrier` onto the medallion and wait for a stable live round."""

        state = self.runtime_state()
        origin = state["origin"]
        self.pad = (float(origin[0]), float(origin[1]), float(origin[2]) + 0.6)
        assert self.bng.vehicles.teleport(carrier, self.pad, (0, 0, 0, 1), reset=True) is True
        stable: dict[str, Any] = {}

        def _live() -> bool:
            stats = self.stats()
            live = stats.get("phase") == "live" and int(stats.get("carrier") or -1) >= 0
            if live and stable.get("carrier") == stats.get("carrier"):
                stable["stats"] = stats
                return True
            stable["carrier"] = stats.get("carrier") if live else None
            return False

        self.step_until(_live, calls=60, note=f"pad pickup by {carrier} never started a round")
        stats = stable["stats"]
        assert int(stats["carrier"]) == int(self.probe(carrier)["id"]), stats
        return stats

    def end_round(self) -> None:
        """Delete-free round end: a stalled carrier is never needed; the fuse does it. Not used by default."""

    # -- screenshots ------------------------------------------------------------
    def shot(
        self, name: str, eye: tuple[float, float, float], aim: tuple[float, float, float], note: str
    ) -> Path:
        """Normal-exposure player-class screenshot, captured while the sim RUNS.

        The halo, tethers and fireworks are immediate-mode debugDrawer output
        drawn only on frames the runtime's behaviour ticks; a frame captured
        while the deterministic stepper is paused shows none of them (G1 boot
        1 measured: zero ribbon pixels in every paused halo-on frame). So the
        camera is placed, the sim is resumed for a moment, the capture is
        requested, and the sim is paused again.
        """

        full = f"{self.gate}_{name}_{self.suffix}"
        px, py, pz = eye
        tx, ty, tz = aim
        self.lua(
            "commands.setFreeCamera(); "
            f"local eye = vec3({px}, {py}, {pz}); local aim = vec3({tx}, {ty}, {tz}); "
            "local rotation = quatFromDir((aim - eye):normalized(), vec3(0, 0, 1)); "
            "core_camera.setPosRot(0, eye.x, eye.y, eye.z, rotation.x, rotation.y, rotation.z, rotation.w); "
            "return jsonEncode({ok = true})"
        )
        source = self.user / "screenshots" / f"{full}.png"
        target = self.shot_dir / f"{full}.png"
        for attempt in range(3):
            self.step(30)
            self.bng.control.resume()
            time.sleep(0.5)
            self.lua(
                f"screenshot.doScreenshot(nil, nil, 'screenshots/{full}', 'png'); return jsonEncode({{ok = true}})"
            )
            time.sleep(0.7)
            self.bng.control.pause()
            self.step(2)
            # doScreenshot is asynchronous: the PNG lands a beat after the call,
            # and under load it can miss a 0.7 s window entirely (G5 run 1 died
            # reading a frame that had not been written). Wait for the file, and
            # for it to stop growing, before anyone measures it.
            size = -1
            for _ in range(30):
                if source.is_file():
                    current = source.stat().st_size
                    if current > 0 and current == size:
                        break
                    size = current
                time.sleep(0.3)
            if source.is_file() and source.stat().st_size > 0:
                break
        if full not in self.shot_names:
            self.shot_names.append(full)
        if source.is_file():
            shutil.copyfile(source, target)
        else:
            self.problem(f"screenshot never landed on disk: {full}")
        self.report["shots"].append(
            {"file": target.name, "view": note, "eye": list(eye), "aim": list(aim)}
        )
        return target

    def set_hidden(self, names: list[str], hidden: bool) -> None:
        flag = "true" if hidden else "false"
        self.lua(
            " ".join(
                f"do local o = scenetree.findObject({n!r}); if o then o:setHidden({flag}) end end "
                for n in names
            )
            + "return jsonEncode({ok = true})"
        )
        self.step(20)


@contextmanager
def _session(
    gate: str,
    tmp_path: Path,
    *,
    plant_crash: bool = False,
    arena_payload_override: bytes | None = None,
    probe_zip: bytes | None = None,
    watchdog_seconds: float = 2400.0,
) -> Iterator[Session]:
    home, user, binary = smoke._configured_runtime()
    arena_dir = arena_dist.DEFAULT_OUTPUT_DIR
    arena_lock = json.loads((arena_dir / arena_dist.LOCK_NAME).read_text(encoding="utf-8"))
    arena_payload = smoke._locked_payload(
        arena_dir / arena_dist.ZIP_NAME, arena_dir / arena_dist.LOCK_NAME
    )
    hp_dir = smoke.PACK_ROOT / "hot_potato" / "dist"
    hp_lock = json.loads((hp_dir / f"{smoke.HOT_POTATO_ID}.lock.json").read_text(encoding="utf-8"))
    hp_payload = smoke._locked_payload(
        hp_dir / smoke.HOT_POTATO_ZIP, hp_dir / f"{smoke.HOT_POTATO_ID}.lock.json"
    )
    # The lock chain, not a fixed serial: the arena's depends_on must name the
    # Hot Potato zip actually on disk. (Pinned to 47 for the first pass; the
    # runtime moved to 48 mid-round with ask #4, and a hard-coded serial refused
    # every boot until the arena dist was re-cut - the chain is the invariant.)
    assert arena_lock["depends_on"]["sha256"] == hp_lock["sha256"], (
        "arena lock depends_on != Hot Potato lock"
    )
    assert arena_lock["depends_on"]["build_serial"] == hp_lock["build_serial"], arena_lock[
        "depends_on"
    ]
    assert int(hp_lock["build_serial"]) >= 47, hp_lock["build_serial"]
    if arena_payload_override is not None:
        arena_payload = arena_payload_override  # deliberately un-verified: the negative control

    root = DEFAULT_SHOT_ROOT or (tmp_path / "arena_gate_shots")
    shot_dir = root / gate
    shot_dir.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex[:10]
    installed_hp = require_confined_profile_target(
        user, Path("mods") / f"arena_gate_hp_{suffix}.zip"
    )
    installed_arena = require_confined_profile_target(
        user, Path("mods") / f"arena_gate_arena_{suffix}.zip"
    )
    installed_probe = require_confined_profile_target(
        user, Path("mods") / f"arena_gate_probe_{suffix}.zip"
    )
    settings_file = user / "settings" / f"{smoke.HOT_POTATO_ID}.json"
    snapshot_file = user / "settings" / f"{MOD_ID}.snapshot.json"
    # B5 (2026-09-10): the arena lives ON the level now, so the engine's mesh cache for its
    # shapes sits under the level id, not under stock gridmap_v2.
    mesh_cache = user / "temp" / Path(sync.SHAPES_RELATIVE)
    log_path = user / "beamng.log"
    log_start = f"arena_gate_{gate}_start_{suffix}"

    def _purge_arena_cache() -> list[str]:
        removed: list[str] = []
        if not mesh_cache.is_dir():
            return removed
        files = tuple(p for p in mesh_cache.rglob("*") if p.is_file())
        for p in files:
            assert p.suffix.lower() in (".cdae", ".dds", ".dts"), (
                f"unexpected file in the arena cache: {p}"
            )
        dirs = tuple(
            sorted((p for p in mesh_cache.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts))
        ) + (mesh_cache,)
        cleanup_exact_live_artifacts(profile=user, files=files, empty_directories=dirs)
        removed.extend(str(p) for p in files)
        return removed

    with ExitStack() as safety:
        safety.enter_context(isolated_profile_lock(user))
        reservation = safety.enter_context(reserve_loopback_ports(1))
        (tcom_port,) = reservation.ports
        conflicts = [
            c
            for c in namespace_conflicts(user, smoke.HOT_POTATO_ID, installed_hp)
            if Path(c) not in (installed_arena, installed_probe)
        ]
        assert not conflicts, (
            f"competing {smoke.HOT_POTATO_ID} archives in the isolated profile: {conflicts}"
        )
        stale = (
            [
                str(p)
                for p in (user / "mods").glob("*.zip")
                if ("arena" in p.name.casefold() or "hot_potato" in p.name.casefold())
                and p not in (installed_hp, installed_arena, installed_probe)
            ]
            if (user / "mods").is_dir()
            else []
        )
        assert not stale, f"stale arena archives in the isolated profile: {stale}"
        assert not settings_file.exists() and not snapshot_file.exists(), (
            "dirty Hot Potato settings in the sentinel"
        )
        # A compiled cache from an earlier (possibly crashed) gate would shadow the zip's DAEs.
        purged_before = _purge_arena_cache()
        installed_hp.parent.mkdir(parents=True, exist_ok=True)
        payloads = [(installed_hp, hp_payload), (installed_arena, arena_payload)]
        if probe_zip is not None:
            payloads.append((installed_probe, probe_zip))
        for target, payload in payloads:
            with target.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        crash_player_values = {
            "arena_radius_m": 91.4,
            "arena_enabled": True,
            "ai_enabled": True,
            "arena_magnet_enabled": False,
        }
        if plant_crash:
            require_confined_profile_target(user, Path("settings") / settings_file.name)
            require_confined_profile_target(user, Path("settings") / snapshot_file.name)
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            settings_file.write_text(
                json.dumps(
                    {"ai_enabled": True, "arena_magnet_enabled": True, "arena_enabled": True}
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
            snapshot_file.write_text(
                json.dumps({"schema": 1, "mod": MOD_ID, "options": crash_player_values}) + "\n",
                encoding="utf-8",
                newline="\n",
            )

        launch_user = user.parent if user.name.casefold() == "current" else user
        bng = BeamNGpy(
            "127.0.0.1",
            tcom_port,
            home=str(home),
            binary=str(binary),
            user=str(launch_user),
            quit_on_close=False,
            headless=True,
            nogpu=False,
        )
        session = Session(gate, bng, user, suffix, shot_dir)
        session.report["purged_cache_before"] = purged_before
        session.report["crash_player_values"] = crash_player_values if plant_crash else None
        session.report["locks"] = {
            "hot_potato": {"serial": hp_lock["build_serial"], "sha256": hp_lock["sha256"]},
            "arena": {"sha256": arena_lock["sha256"], "depends_on": arena_lock["depends_on"]},
            "arena_payload_is_control": arena_payload_override is not None,
        }
        owned_process: Any | None = None
        timer: threading.Timer | None = None
        started = time.monotonic()
        try:

            def watchdog() -> None:
                process = bng.process
                if process is not None and process.poll() is None:
                    process.terminate()

            timer = threading.Timer(watchdog_seconds, watchdog)
            timer.daemon = True
            timer.start()
            reservation.release()
            bng.open(launch=True, listen_ip="127.0.0.1")
            owned_process = claim_owned_beamng_process(bng)
            listed = bng.scenario.get_scenarios([sync.LEVEL_ID])  # B5: listed under the level
            candidates = [
                s for level in listed.values() for s in level if s.path and MOD_ID in str(s.path)
            ]
            assert len(candidates) == 1, {
                "detail": "shipped scenario not listed",
                "paths": [str(s.path) for l in listed.values() for s in l],
            }
            bng.control.pause()
            bng.scenario.load(
                candidates[0],
                precompile_shaders=False,
                connect_player_vehicle=False,
                connect_existing_vehicles=False,
            )
            bng.scenario.start()
            bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
            bng.control.pause()
            bng.control.step(3, wait=True)
            assert session.lua(
                f"log('I', {smoke.LIVE_TEST_TAG!r}, {log_start!r}); return jsonEncode({{ok = true}})"
            ) == {"ok": True}
            state: dict[str, Any] = {}
            for _ in range(60):
                state = session.runtime_state()
                if state.get("registered"):
                    break
                bng.control.step(15, wait=True)
            assert state.get("registered") is True and state["part_count"] == 7, state
            arena: dict[str, Any] = {}
            for _ in range(60):
                arena = session.arena()
                if arena.get("loaded") and arena.get("booted"):
                    break
                bng.control.step(15, wait=True)
            assert arena.get("booted") is True and arena.get("mp") is False, arena
            assert [row["key"] for row in arena["boot"]] == list(sync.BOOT_OPTION_KEYS) and all(
                r["ok"] for r in arena["boot"]
            ), arena["boot"]
            # The obstacle census is pinned to the HANDOFF, not to a literal.
            # G14: geometry v3.6 took the table 42 -> 46 and a hard-coded 42
            # would have refused every boot the moment it landed - the same
            # trap the serial-47 lock pin sprang in G3. The handoff is the
            # source the scenario's Lua is generated from, so this doubles as a
            # staleness check: a dist that lags the handoff fails here, loudly,
            # at boot, in every gate.
            expected_obstacles = len(HANDOFF["obstacles"])
            assert (
                arena["obstacles"] == "registered"
                and int(arena["obstacle_count"]) == expected_obstacles
            ), {
                "detail": "the installed dist registers a different obstacle count than the handoff on disk",
                "registered": arena.get("obstacle_count"),
                "handoff": expected_obstacles,
                "arena": arena,
            }
            hook = session.lua(
                f"return jsonEncode(extensions[{RUNTIME!r}].hotPotatoGetObstacles())"
            )
            assert int(hook["count"]) == expected_obstacles, {
                "detail": "hotPotatoGetObstacles disagrees with the handoff",
                "echoed": hook.get("count"),
                "handoff": expected_obstacles,
            }
            session.step_until(
                lambda: all(
                    int(g["emitters_found"]) == int(g["emitters_expected"])
                    for g in session.arena()["geysers"]
                ),
                calls=40,
                note="emitters never resolved",
            )
            origin = state["origin"]
            session.pad = (float(origin[0]), float(origin[1]), float(origin[2]) + 0.6)
            session.player_id = int(session.probe(PLAYER)["id"])
            session._clock0 = float(session.arena()["clock"])
            session.report["boot"] = {
                "runtime_part_count": state["part_count"],
                "arena_boot": arena["boot"],
                "obstacles": arena["obstacles"],
                "obstacle_count": arena["obstacle_count"],
                "recovered_calls": arena.get("recovered_calls"),
                "snapshot": {k: arena["snapshot"].get(k) for k in sync.BOOT_OPTION_KEYS},
                "boot_wall_s": round(time.monotonic() - started, 1),
            }
            yield session
            session.report["completed"] = True
        finally:
            session.report["wall_s"] = round(time.monotonic() - started, 1)
            try:
                try:
                    session.lua(
                        f"local e = extensions[{RUNTIME!r}]; if e then e.hotPotatoResetOptions() end; return jsonEncode({{ok = true}})"
                    )
                except Exception:
                    pass
                cleanup_owned_beamng_session(bng, owned_process=owned_process, scenario=None)
            finally:
                if timer is not None:
                    timer.cancel()
                profile_shots = tuple(user / "screenshots" / f"{n}.png" for n in session.shot_names)
                for source in profile_shots:
                    target = shot_dir / source.name
                    if source.is_file() and not target.is_file():
                        shutil.copyfile(source, target)
                try:
                    cleanup_exact_live_artifacts(
                        profile=user,
                        files=(
                            installed_hp,
                            installed_arena,
                            installed_probe,
                            settings_file,
                            snapshot_file,
                            *profile_shots,
                        ),
                    )
                    _purge_arena_cache()
                finally:
                    records, issues = smoke._log_records(log_path, log_start)
                    text = (
                        log_path.read_text(encoding="utf-8", errors="replace")
                        if log_path.is_file()
                        else ""
                    )
                    mp_errors = [
                        l for l in text.splitlines() if "MPCoreNetwork" in l and "|E|" in l
                    ]
                    mod_errors = [
                        l for l in text.splitlines() if "|E|" in l and "ericrolph" in l.casefold()
                    ]
                    session.report["log"] = {
                        "arena_events": [
                            r["event"] for r in records if r["_tag"] == smoke.ARENA_LOG_TAG
                        ],
                        "runtime_events": [
                            r["event"] for r in records if r["_tag"] == smoke.RUNTIME_LOG_TAG
                        ],
                        "issues": issues,
                        "mpcorenetwork_errors": mp_errors,
                        "mod_error_lines": mod_errors,
                    }
                    session.report["sentinel_after"] = {
                        "zips": sorted(p.name for p in (user / "mods").glob("*.zip")),
                        "settings_file": settings_file.exists(),
                        "snapshot_file": snapshot_file.exists(),
                        "mesh_cache": mesh_cache.exists(),
                    }
                    (shot_dir / f"{gate}_report_{suffix}.json").write_text(
                        json.dumps(session.report, indent=1, default=str), encoding="utf-8"
                    )
                    index_path = shot_dir / "index.json"
                    index = (
                        json.loads(index_path.read_text(encoding="utf-8"))
                        if index_path.is_file()
                        else []
                    )
                    index.append({"suffix": suffix, "shots": session.report["shots"]})
                    index_path.write_text(json.dumps(index, indent=1), encoding="utf-8")
    assert not session.report["log"]["issues"], {
        "detail": "runtime/arena logged errors",
        **session.report["log"],
    }
    assert not session.report["log"]["mpcorenetwork_errors"], session.report["log"][
        "mpcorenetwork_errors"
    ]
    assert not session.report["log"]["mod_error_lines"], session.report["log"]["mod_error_lines"]


# --- the driver -------------------------------------------------------------------


class Driver:
    """A Python-side steering + speed controller driving one car along waypoints.

    Each tick (0.1 s of sim) it reads the car's pose, steers toward the next
    waypoint and holds the target speed; it records a trace, detects stalls
    (throttle >= 0.5 and < 0.3 m/s for stall_after seconds) and runs the
    AGENTS.md stall discriminator (WOT for wot_seconds, then classify the
    displacement), flags airborne frames (clearance jump), rollovers (up.z)
    and the F-P1.10 self-drive anomaly (speed rising with zero throttle after
    a brake hold).
    """

    K_STEER = 1.2
    LOOKAHEAD_M = 5.0

    def __init__(self, session: Session, name: str) -> None:
        self.s = session
        self.name = name
        self.s.vehicle(name).set_shift_mode("realistic_automatic")

    def calibrate(self, xy: tuple[float, float], heading: float = 0.0) -> float:
        """Closed-loop steering-sign calibration on the flat plaza.

        Open-loop readings disagreed between boots (the direction vector, the
        gear and the teleport settle all conspired), so the sign is chosen by
        what WORKS: drive toward a target 30 m ahead and 12 m to the right with
        sign +1 for 4 s, then with sign -1 from the same start; the sign that
        closed the range more is the controller's. Both ranges are recorded.
        """

        s = self.s
        results: dict[str, Any] = {"heading_requested": heading}
        best = None
        for sign in (1.0, -1.0):
            s.teleport(self.name, xy, heading)
            s.control(self.name, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=0.0)
            gear = s.ensure_drive(self.name)
            p0 = s.probe(self.name)
            hx, hy = math.sin(math.radians(heading)), math.cos(math.radians(heading))
            target = (p0["x"] + 30.0 * hx + 12.0 * hy, p0["y"] + 30.0 * hy - 12.0 * hx)
            d0 = math.hypot(target[0] - p0["x"], target[1] - p0["y"])
            integ = 0.0
            for _ in range(40):
                p = s.probe(self.name)
                target_yaw = (
                    math.degrees(math.atan2(target[0] - p["x"], target[1] - p["y"])) % 360.0
                )
                err = math.radians(_wrap_deg(target_yaw - p["yaw"]))
                v_err = 4.0 - p["hspeed"]
                integ = max(-0.3, min(0.3, integ + 0.03 * v_err))
                s.control(
                    self.name,
                    steering=max(-1.0, min(1.0, sign * self.K_STEER * err)),
                    throttle=max(0.0, min(1.0, 0.1 + 0.35 * v_err + integ)),
                    brake=0.0,
                    parkingbrake=0.0,
                )
                s.step(STEP_TICK)
            p1 = s.probe(self.name)
            d1 = math.hypot(target[0] - p1["x"], target[1] - p1["y"])
            s.control(self.name, steering=0.0, throttle=0.0, brake=1.0)
            s.step(30)
            results[f"sign_{'plus' if sign > 0 else 'minus'}"] = {
                "range_start": round(d0, 2),
                "range_end": round(d1, 2),
                "closed_m": round(d0 - d1, 2),
                "gear": gear,
                "yaw_start": round(p0["yaw"], 1),
                "yaw_end": round(p1["yaw"], 1),
            }
            if best is None or (d0 - d1) > best[1]:
                best = (sign, d0 - d1)
        s.steer_sign = best[0]
        results["sign"] = s.steer_sign
        s.report["steering_calibration"] = results
        assert best[1] > 8.0, {"detail": "neither steering sign closed on the target", **results}
        return s.steer_sign

    def line(
        self,
        label: str,
        waypoints: list[tuple[float, float]],
        speed: float,
        *,
        max_sim: float = 90.0,
        reach: float = 3.0,
        stall_after: float = 2.0,
        wot_seconds: float = 4.0,
        heading_fn: Callable[[dict[str, Any]], float] | None = None,
        stop_fn: Callable[[dict[str, Any]], bool] | None = None,
        coast_after_stop: bool = False,
    ) -> dict[str, Any]:
        s = self.s
        name = self.name
        s.release(name)
        gear = s.ensure_drive(name)
        s.step(STEP_TICK)
        t0 = s.clock()
        trace: list[dict[str, float]] = []
        events: list[dict[str, Any]] = []
        wp_i = 0
        integ = 0.0
        stall_since: float | None = None
        wot_until: float | None = None
        wot_from: tuple[float, float, float] | None = None
        base_clearance: float | None = None
        airborne_s = 0.0
        min_uz = 1.0
        outcome = "reached"
        last_brake_hold: float | None = None
        prev_t = 0.0
        while True:
            p = s.probe(name)
            t = s.clock() - t0
            dt, prev_t = t - prev_t, t
            if base_clearance is None:
                base_clearance = float(p["clearance"])
            airborne = float(p["clearance"]) > base_clearance + 0.45
            if airborne:
                airborne_s += dt
            min_uz = min(min_uz, float(p["uz"]))
            sample = {
                "t": round(t, 2),
                "x": round(p["x"], 3),
                "y": round(p["y"], 3),
                "z": round(p["z"], 3),
                "r": round(p["r"], 2),
                "bearing": round(p["bearing"], 1),
                "speed": round(p["hspeed"], 3),
                "vz": round(p["vz"], 3),
                "uz": round(p["uz"], 3),
                "clearance": round(p["clearance"], 3),
                "air": airborne,
                "damage": p["damage"],
            }
            if p["uz"] < 0.35:
                events.append(
                    {
                        "type": "rollover",
                        "t": t,
                        "uz": p["uz"],
                        "r": p["r"],
                        "bearing": p["bearing"],
                    }
                )
                outcome = "rollover"
                trace.append(sample)
                break
            if stop_fn is not None and stop_fn(p):
                outcome = "stop_fn"
                trace.append(sample)
                if coast_after_stop:
                    s.control(name, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=0.0)
                break
            while (
                wp_i < len(waypoints)
                and math.hypot(p["x"] - waypoints[wp_i][0], p["y"] - waypoints[wp_i][1]) < reach
            ):
                wp_i += 1
            if wp_i >= len(waypoints):
                trace.append(sample)
                break
            if heading_fn is not None:
                target_yaw = heading_fn(p)
            else:
                # Aim at the first waypoint at least LOOKAHEAD_M ahead (pure pursuit),
                # never at one under the bumper: a nearest-point chase wandered the
                # car 4 m across an 8 m ramp and off its inner flank (G2 run 2).
                aim_i = wp_i
                while (
                    aim_i < len(waypoints) - 1
                    and math.hypot(p["x"] - waypoints[aim_i][0], p["y"] - waypoints[aim_i][1])
                    < self.LOOKAHEAD_M
                ):
                    aim_i += 1
                wx, wy = waypoints[aim_i]
                target_yaw = math.degrees(math.atan2(wx - p["x"], wy - p["y"])) % 360.0
            err = math.radians(_wrap_deg(target_yaw - p["yaw"]))
            steer = max(-1.0, min(1.0, s.steer_sign * self.K_STEER * err))
            v_err = speed - float(p["hspeed"])
            integ = max(-0.3, min(0.3, integ + 0.03 * v_err))
            throttle = max(0.0, min(1.0, 0.10 + 0.35 * v_err + integ))
            brake = max(0.0, min(1.0, -0.35 * v_err)) if v_err < -0.7 else 0.0
            if wot_until is not None:
                throttle, brake = 1.0, 0.0
                if t >= wot_until:
                    moved = math.hypot(p["x"] - wot_from[0], p["y"] - wot_from[1])
                    dz = p["z"] - wot_from[2]
                    verdict = (
                        "escaped_at_wot_marginal_grade"
                        if moved > 2.0 and dz >= -0.2
                        else (
                            "slid_back_grade_limited"
                            if moved > 0.5 and dz < -0.2
                            else "did_not_move_hard_geometry"
                        )
                    )
                    events.append(
                        {
                            "type": "stall_discriminator",
                            "t": t,
                            "moved_m": moved,
                            "dz": dz,
                            "verdict": verdict,
                            "r": p["r"],
                            "bearing": p["bearing"],
                            "z": p["z"],
                        }
                    )
                    outcome = f"stall:{verdict}"
                    trace.append(sample)
                    break
            elif throttle >= 0.5 and float(p["hspeed"]) < 0.3:
                stall_since = stall_since if stall_since is not None else t
                if t - stall_since >= stall_after:
                    events.append(
                        {"type": "stall", "t": t, "r": p["r"], "bearing": p["bearing"], "z": p["z"]}
                    )
                    wot_until = t + wot_seconds
                    wot_from = (p["x"], p["y"], p["z"])
            else:
                stall_since = None
            sample["throttle"] = round(throttle, 2)
            sample["brake"] = round(brake, 2)
            sample["steer"] = round(steer, 2)
            if brake > 0.5:
                last_brake_hold = t
            # F-P1.10 watch: the car speeding up with no throttle after a brake hold.
            if (
                throttle < 0.05
                and last_brake_hold is not None
                and t - last_brake_hold < 12.0
                and len(trace) >= 5
            ):
                if float(p["hspeed"]) > trace[-1]["speed"] + 1.5 and float(p["hspeed"]) > 6.0:
                    events.append(
                        {"type": "self_drive_anomaly_F-P1.10", "t": t, "speed": p["hspeed"]}
                    )
            trace.append(sample)
            s.control(name, steering=steer, throttle=throttle, brake=brake, parkingbrake=0.0)
            s.step(STEP_TICK)
            if t > max_sim:
                outcome = "timeout"
                break
        if not (coast_after_stop and outcome == "stop_fn"):
            s.control(name, steering=0.0, throttle=0.0, brake=1.0, parkingbrake=0.0)
            s.step(STEP_TICK * 3)
        summary = {
            "label": label,
            "speed_target": speed,
            "outcome": outcome,
            "events": events,
            "gear_at_start": gear,
            "samples": len(trace),
            "sim_s": trace[-1]["t"] if trace else 0.0,
            "max_r": max((x["r"] for x in trace), default=None),
            "min_r": min((x["r"] for x in trace), default=None),
            "max_z": max((x["z"] for x in trace), default=None),
            "min_uz": round(min_uz, 3),
            "airborne_s": round(airborne_s, 1),
            "max_speed": max((x["speed"] for x in trace), default=None),
            "final": trace[-1] if trace else None,
            "start": trace[0] if trace else None,
            "trace": trace,
        }
        s.report.setdefault("lines", []).append({k: v for k, v in summary.items() if k != "trace"})
        s.report.setdefault("traces", {})[label] = trace
        return summary


# --- shared scene facts -------------------------------------------------------------

HANDOFF = sync.read_handoff()
SHAPE_OF = {str(i["name"]): str(i["shape"]) for i in HANDOFF["instances"]}
OBSTACLES = [dict(o) for o in HANDOFF["obstacles"]]
WALL_STATICS = [n for n, shape in SHAPE_OF.items() if shape.startswith("wall_arc")]
FLOOR_STATICS = [n for n, shape in SHAPE_OF.items() if shape == "floor_skin_quadrant"]
# Physical solids for the collision census (metres, world). Cylinders: (x, y, r);
# the towers are 3 x 3 m boxes taken as r 2.1 (half diagonal).
SOLID_CYLINDERS = (
    [
        (f"masher_{k}", *(_bearing_xy(b, 48.0)), 1.2)
        for k, b in (("ne", 45), ("se", 135), ("sw", 225), ("nw", 315))
    ]
    + [
        (f"grinder_{k}", *(_bearing_xy(b, 26.0)), 1.5)
        for k, b in (("ne", 45), ("se", 135), ("sw", 225), ("nw", 315))
    ]
    + [("geyser_tower_l", 843.937, -222.318, 2.1), ("geyser_tower_r", 856.063, -222.318, 2.1)]
)
JAMB_POLYLINES = {
    "jamb_60_gate": [(904.945, -227.493), (912.852, -216.303), (923.899, -206.841)],
    "jamb_60_far": [(922.945, -258.67), (936.589, -257.417), (950.307, -252.581)],
    "jamb_240_gate": [(795.055, -332.507), (787.148, -343.697), (776.101, -353.159)],
    "jamb_240_far": [(777.055, -301.33), (763.411, -302.583), (749.693, -307.419)],
}


def _point_segment_distance(
    px: float, py: float, a: tuple[float, float], b: tuple[float, float]
) -> float:
    ax, ay = a
    bx, by = b
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    denom = vx * vx + vy * vy
    t = 0.0 if denom == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / denom))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def _nearest_solid(x: float, y: float, z: float) -> tuple[str, float]:
    """(name, clearance) of the nearest solid face the car centre could be touching."""

    best = ("none", 1e9)
    for name, cx, cy, radius in SOLID_CYLINDERS:
        d = math.hypot(x - cx, y - cy) - radius
        if d < best[1]:
            best = (name, d)
    r, bearing = _polar(x, y)
    if z < 102.5:
        # Handle deck flanks: vertical 4 m walls at x = 843 / 857 between the nose (y -310) and the rear (y -368).
        if -368.5 <= y <= -309.5:
            for name, fx in (("handle_flank_w", 843.0), ("handle_flank_e", 857.0)):
                d = abs(x - fx)
                if d < best[1] and not (843.0 < x < 857.0):
                    best = (name, d)
        # Handle nose (the 4 m drop face at y -310 between the flanks).
        if 843.0 <= x <= 857.0 and y > -310.0:
            d = y + 310.0
            if d < best[1]:
                best = ("handle_nose", d)
        # Ramp inner flanks at r 80 (0 -> 3.5 m walls from ~152 deg to the merge at 175 / 185 -> 208).
        for name, lo, hi in (
            ("ramp_e_inner_flank", 151.0, 175.5),
            ("ramp_w_inner_flank", 184.5, 209.0),
        ):
            if lo <= bearing <= hi and r < 80.0:
                d = 80.0 - r
                if d < best[1]:
                    best = (name, d)
    for name, poly in JAMB_POLYLINES.items():
        for a, b in zip(poly[:-1], poly[1:]):
            d = _point_segment_distance(x, y, a, b)
            if d < best[1]:
                best = (name, d)
    return best


def _spout_line(
    bearing: float, r_from: float, r_to: float, steps: int = 6
) -> list[tuple[float, float]]:
    return [_bearing_xy(bearing, r_from + (r_to - r_from) * i / steps) for i in range(steps + 1)]


def _arc_line(
    r: float, b_from: float, b_to: float, step_deg: float = 2.5
) -> list[tuple[float, float]]:
    n = max(1, int(abs(b_to - b_from) / step_deg))
    return [_bearing_xy(b_from + (b_to - b_from) * i / n, r) for i in range(n + 1)]


def _ready_round_long(session: Session, carrier: str, ai: bool = False) -> dict[str, Any]:
    session.set_options(LONG_FUSE)
    session.set_option("ai_enabled", ai)
    session.drop_round()
    stats = session.start_round(carrier)
    if not ai:
        session.park(carrier)
    return stats


# ====================================================================================
# G1 - site truth
# ====================================================================================


@pytest.mark.beamng_live
def test_g1_site_truth(tmp_path: Path) -> None:
    with _session("G1", tmp_path) as s:
        r = s.report
        # A live round so the halo draws (it is immediate-mode, live/boom only).
        _ready_round_long(s, AI[0])
        s.set_option("arena_halo_enabled", True)
        # Player-class camera heights (1.6 m eye) at the design's four stations.
        crest_z = C[2] + float(HANDOFF["crest_z_m"])
        stations = {
            "bowl_floor": (
                (*_bearing_xy(200.0, 18.0), C[2] + 1.6),
                (*_bearing_xy(20.0, 91.4), crest_z + 1.0),
            ),
            "mid_bank": (
                (*_bearing_xy(100.0, 84.0), s.surface_z(*_bearing_xy(100.0, 84.0)) + 1.6),
                (*_bearing_xy(150.0, 91.4), crest_z + 1.0),
            ),
            "crest": (
                (*_bearing_xy(330.0, 90.5), crest_z + 1.6),
                (*_bearing_xy(20.0, 91.4), crest_z + 0.8),
            ),
            "glacis": (
                (*_bearing_xy(120.0, 104.0), s.surface_z(*_bearing_xy(120.0, 104.0)) + 1.6),
                (*_bearing_xy(120.0, 91.4), crest_z + 1.0),
            ),
        }
        halo: dict[str, Any] = {}
        on_shots = {
            k: s.shot(f"{k}_halo_on", eye, aim, f"{k} station, player eye height, halo ON")
            for k, (eye, aim) in stations.items()
        }
        s.set_option("arena_halo_enabled", False)
        s.step(10)
        off_shots = {
            k: s.shot(f"{k}_halo_off", eye, aim, f"{k} station, halo OFF (diff reference)")
            for k, (eye, aim) in stations.items()
        }
        for k in stations:
            halo[k] = _tint_band(on_shots[k], off_shots[k])
            halo[k]["raw_diff"] = _diff_pixels(on_shots[k], off_shots[k], threshold=5.0)["count"]
        r["halo_pixels"] = halo
        s.set_option("arena_halo_enabled", True)
        # Halo ribbon geometry: top z 107 vs crest 105.5 (v3.1 amendment).
        r["halo_ribbon_above_crest_m"] = round((C[2] + 7.0) - crest_z, 2)
        problems: list[str] = []
        # Bowl floor and crest must read clearly; mid-bank looks ALONG the wall so
        # the ribbon is edge-on and faint (boot 3: +8.5) - a lower bar, recorded.
        for k, floor in (("bowl_floor", 10.0), ("crest", 10.0), ("mid_bank", 5.0)):
            if halo[k]["band_rows"] < 3 or halo[k]["peak_delta_rb"] < floor:
                problems.append(f"halo not readable from {k}: {halo[k]}")
        # From the glacis the ribbon is mostly occluded by the crest: recorded, not gated.

        # Tethers with the halo off: the player hauled from r 108 under the magnet.
        s.set_option("arena_halo_enabled", False)
        s.teleport(PLAYER, _bearing_xy(120.0, 40.0), 120.0)
        s.step(45)  # membership sweep
        s.teleport(PLAYER, _bearing_xy(120.0, 108.0), 300.0)
        s.park(PLAYER)
        s.step_until(
            lambda: s.probe(PLAYER)["r"] < 104.0,
            calls=60,
            note="magnet never gripped the parked player",
            steps=10,
        )
        p = s.probe(PLAYER)
        tether_eye = (*_bearing_xy(120.0, p["r"] + 14.0), p["z"] + 5.0)
        tether_aim = (*_bearing_xy(120.0, p["r"] - 6.0), p["z"] + 1.0)
        tether_shot = s.shot(
            "tethers_halo_off",
            tether_eye,
            tether_aim,
            "magnet tether beads (halo off) during the haul",
        )
        s.set_option("arena_magnet_enabled", False)
        s.step(20)
        p2 = s.probe(PLAYER)
        ref_shot = s.shot(
            "tethers_magnet_off_ref",
            tether_eye,
            tether_aim,
            "same camera pose, magnet off (reference)",
        )
        r["tether_pixels"] = {
            "bead_tint_pixels": _tint_pixels(tether_shot, ref_shot),
            "amber_with_magnet": _amber_pixels(tether_shot),
            "amber_without": _amber_pixels(ref_shot),
        }
        s.set_option("arena_magnet_enabled", True)
        s.set_option("arena_halo_enabled", True)
        r["tether_haul"] = {"r_at_shot": p["r"], "r_after": p2["r"]}
        s.teleport(PLAYER, _bearing_xy(120.0, 40.0), 120.0)
        s.park(PLAYER)

        # Far-field floor: >= 6 frames at 300 m through the band metric, plus the
        # critic's other cameras and skins-hidden references for the plaza median.
        cams = {
            "far": ((C[0], C[1] - 60.0, C[2] + 300.0), (C[0], C[1], C[2])),
            "h150": ((C[0], C[1] - 30.0, C[2] + 150.0), (C[0], C[1], C[2])),
            "h100": ((C[0], C[1] - 20.0, C[2] + 100.0), (C[0], C[1], C[2])),
            "overview": ((C[0] + 150.0, C[1] - 170.0, C[2] + 95.0), (C[0], C[1], C[2] + 8.0)),
        }
        discs = {"far": (640, 372, 140), "h150": (640, 360, 250), "h100": (640, 360, 300)}
        far_frames = [
            s.shot(
                f"farfield_{i}", *cams["far"], f"far-field floor frame {i} (300 m above the bowl)"
            )
            for i in range(1, 7)
        ]
        other = {
            k: s.shot(f"floor_{k}", *cams[k], f"floor at the critic's {k} camera")
            for k in ("h150", "h100", "overview")
        }
        s.set_hidden(FLOOR_STATICS, True)
        hidden = {
            k: s.shot(
                f"floor_{k}_skins_hidden",
                *cams[k],
                f"{k} camera with the four floor skins hidden (groundplane reference)",
            )
            for k in cams
        }
        s.set_hidden(FLOOR_STATICS, False)
        # A second far-field set after the skins toggled back (the LOD state may re-evaluate).
        far_frames += [
            s.shot(
                f"farfield_{i}", *cams["far"], f"far-field floor frame {i} (after the skins toggle)"
            )
            for i in range(7, 10)
        ]
        ratios = [smoke._band_ratio(f, 640, 372, 140) for f in far_frames]
        medians = {
            "far_shipped": [_disc_median(f, *discs["far"]) for f in far_frames],
            "far_hidden": _disc_median(hidden["far"], *discs["far"]),
            "h150_shipped": _disc_median(other["h150"], *discs["h150"]),
            "h150_hidden": _disc_median(hidden["h150"], *discs["h150"]),
            "h100_shipped": _disc_median(other["h100"], *discs["h100"]),
            "h100_hidden": _disc_median(hidden["h100"], *discs["h100"]),
        }
        r["farfield"] = {
            "band_ratios": ratios,
            "min": min(ratios),
            "max": max(ratios),
            "banded_frames_over_2_2": sum(1 for x in ratios if x > 2.2),
            "medians": medians,
        }
        assert len(ratios) >= 6

        # Drive off the glacis foot at three bearings: no lip, no void.
        s.set_option("arena_magnet_enabled", False)  # the drive-offs leave the ring on purpose
        drv = Driver(s, PLAYER)
        drv.calibrate(_bearing_xy(90.0, 40.0), 0.0)
        toes: dict[str, Any] = {}
        for bearing in (15.0, 120.0, 285.0):
            # Coarse profile r 106 -> 124 (0.25 m) for the record; fine profile r 110 -> 116
            # (0.05 m) for the lip test: a step reads as a local slope over 60 % (> 3 cm
            # in 5 cm); the 28.8 % glacis itself is 1.4 cm per sample.
            coarse = s.surface_profile(
                [_bearing_xy(bearing, 106.0 + 0.25 * i) for i in range(0, 73)]
            )
            fine = s.surface_profile(
                [_bearing_xy(bearing, 110.0 + 0.05 * i) for i in range(0, 121)]
            )
            fine_steps = [abs(fine[i + 1]["z"] - fine[i]["z"]) for i in range(len(fine) - 1)]
            worst = max(range(len(fine_steps)), key=lambda i: fine_steps[i])
            voids = [row for row in coarse + fine if not row["hit"]]
            toe = {
                "max_dz_per_0_05m": round(fine_steps[worst], 4),
                "worst_r": round(110.0 + 0.05 * worst, 2),
                "max_local_slope_pct": round(100.0 * fine_steps[worst] / 0.05, 1),
                "voids": len(voids),
                "z_at_r106": coarse[0]["z"],
                "z_at_r113": coarse[28]["z"],
                "z_at_r120": coarse[56]["z"],
                "z_at_r124": coarse[72]["z"],
                "coarse_profile": [
                    (round(106.0 + 0.25 * i, 2), round(row["z"], 4)) for i, row in enumerate(coarse)
                ],
            }
            s.teleport(PLAYER, _bearing_xy(bearing, 100.0), bearing)
            line = drv.line(
                f"glacis_off_{int(bearing)}",
                [_bearing_xy(bearing, 112.0), _bearing_xy(bearing, 128.0)],
                2.0,
                max_sim=60.0,
            )
            toe["drive"] = {
                k: line[k] for k in ("outcome", "airborne_s", "min_uz", "max_r", "events")
            }
            toes[f"{int(bearing)}"] = toe
            assert fine_steps[worst] < 0.03, {
                "bearing": bearing,
                **{k: v for k, v in toe.items() if k != "coarse_profile"},
            }
            assert not voids, {"bearing": bearing, "voids": len(voids)}
            assert line["outcome"] == "reached" and line["airborne_s"] < 0.3, {
                "bearing": bearing,
                **toe,
            }
        r["glacis_toe"] = toes
        s.set_option("arena_magnet_enabled", True)

    if r["tether_pixels"]["bead_tint_pixels"] < 60:
        problems.append(f"tether beads not visible with the halo off: {r['tether_pixels']}")
    if r["farfield"]["banded_frames_over_2_2"]:
        problems.append(f"far-field banding on the shipped package: {r['farfield']['band_ratios']}")
    r["problems"] = problems
    (s.shot_dir / f"G1_report_{s.suffix}.json").write_text(
        json.dumps(r, indent=1, default=str), encoding="utf-8"
    )
    assert not problems, problems


@pytest.mark.beamng_live
def test_g1_floor_lod_control_zip(tmp_path: Path) -> None:
    """The critic's negative control: shipped zip with the floor DAE's _a70 node removed."""

    arena_dir = arena_dist.DEFAULT_OUTPUT_DIR
    source = arena_dir / arena_dist.ZIP_NAME
    control = Path(CONTROL_ZIP) if CONTROL_ZIP else None
    if control is None or not control.is_file():
        control = tmp_path / "control_a70_removed.zip"
        with (
            zipfile.ZipFile(source) as src,
            zipfile.ZipFile(control, "w", zipfile.ZIP_STORED) as dst,
        ):
            for info in src.infolist():
                data = src.read(info.filename)
                if info.filename.endswith("floor_skin_quadrant.dae"):
                    lines = data.decode("utf-8").split("\n")
                    start = next(
                        i
                        for i, l in enumerate(lines)
                        if f'node id="{MOD_ID}_floor_skin_quadrant_' in l
                    )
                    end = next(i for i in range(start, len(lines)) if lines[i].strip() == "</node>")
                    data = "\n".join(lines[:start] + lines[end + 1 :]).encode("utf-8")
                dst.writestr(info, data)
    with zipfile.ZipFile(control) as z:
        dae = z.read(f"{sync.SHAPES_RELATIVE}/{MOD_ID}_floor_skin_quadrant.dae").decode()
        nodes = [l.strip()[:90] for l in dae.splitlines() if "<node id=" in l]
    assert not any(f"{MOD_ID}_floor_skin_quadrant_" in n for n in nodes), nodes
    with _session("G1ctrl", tmp_path, arena_payload_override=control.read_bytes()) as s:
        r = s.report
        r["control_dae_nodes"] = nodes
        cams = {
            "far": ((C[0], C[1] - 60.0, C[2] + 300.0), (C[0], C[1], C[2])),
            "h150": ((C[0], C[1] - 30.0, C[2] + 150.0), (C[0], C[1], C[2])),
            "h100": ((C[0], C[1] - 20.0, C[2] + 100.0), (C[0], C[1], C[2])),
        }
        discs = {"far": (640, 372, 140), "h150": (640, 360, 250), "h100": (640, 360, 300)}
        s.step(120)
        shots = {
            k: [
                s.shot(
                    f"ctrl_{k}_{i}", *cams[k], f"control zip (_a70 removed), {k} camera, frame {i}"
                )
                for i in (1, 2, 3)
            ]
            for k in cams
        }
        s.set_hidden(FLOOR_STATICS, True)
        hidden = {
            k: s.shot(
                f"ctrl_{k}_skins_hidden", *cams[k], f"control zip, {k} camera, floor skins hidden"
            )
            for k in cams
        }
        s.set_hidden(FLOOR_STATICS, False)
        r["control_medians"] = {
            k: {
                "frames": [_disc_median(f, *discs[k]) for f in shots[k]],
                "hidden": _disc_median(hidden[k], *discs[k]),
            }
            for k in cams
        }
        r["control_band_ratios_far"] = [smoke._band_ratio(f, 640, 372, 140) for f in shots["far"]]


# ====================================================================================
# G2 - surface
# ====================================================================================


def _brake_decel(
    s: Session,
    name: str,
    start_xy: tuple[float, float],
    heading: float,
    v0: float,
    arm_r_range: tuple[float, float] | None,
    label: str,
) -> dict[str, Any]:
    """Teleport, inject v0 along the heading, brake=1 at the arm point, sample every 3 steps."""

    s.teleport(name, start_xy, heading)
    s.control(name, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=0.0)
    s.step(STEP_TICK)
    s.vehicle(name).set_velocity(v0, 0.6)
    s.step(45)
    samples: list[dict[str, Any]] = []
    armed = False
    contacts: list[str] = []
    t0 = s.clock()
    for _ in range(400):
        p = s.probe(name)
        r = p["r"]
        if not armed and (arm_r_range is None or arm_r_range[0] <= r <= arm_r_range[1]):
            s.control(name, steering=0.0, throttle=0.0, brake=1.0, parkingbrake=0.0)
            armed = True
            contacts = s.wheel_contacts(name)
        samples.append(
            {
                "t": round(s.clock() - t0, 3),
                "r": round(r, 2),
                "speed": round(p["hspeed"], 3),
                "armed": armed,
                "x": round(p["x"], 2),
                "y": round(p["y"], 2),
            }
        )
        if armed and p["hspeed"] < 0.3:
            break
        s.step(3)
    braking = [x for x in samples if x["armed"]]
    decel = None
    if len(braking) >= 3:
        v_start, v_end = braking[0]["speed"], braking[-1]["speed"]
        dt = braking[-1]["t"] - braking[0]["t"]
        decel = (v_start - v_end) / dt if dt > 0 else None
    s.control(name, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=1.0)
    out = {
        "label": label,
        "v0_target": v0,
        "v_at_arm": braking[0]["speed"] if braking else None,
        "decel_mps2": decel,
        "mu_equiv": (decel / 9.81) if decel else None,
        "brake_samples": len(braking),
        "contacts_at_arm": contacts,
        "stop_r": braking[-1]["r"] if braking else None,
        "stopped": bool(braking) and braking[-1]["speed"] < 0.3,
    }
    s.report.setdefault("decels", []).append(out)
    return out


@pytest.mark.beamng_live
def test_g2_surface(tmp_path: Path) -> None:
    with _session("G2", tmp_path) as s:
        r = s.report
        s.set_option("ai_enabled", False)
        s.set_option("arena_magnet_enabled", False)  # no round yet; the rams re-enable it
        drv = Driver(s, PLAYER)
        drv.calibrate(_bearing_xy(90.0, 40.0), 0.0)

        # --- wall bank: radial crawl and 2 m/s at bearing 20 (clear of every feature) ---
        bank: dict[str, Any] = {}
        for speed, tag in ((1.1, "crawl"), (2.0, "2mps")):
            s.teleport(PLAYER, _bearing_xy(20.0, 66.0), 20.0)
            line = drv.line(
                f"bank_radial_{tag}",
                [_bearing_xy(20.0, 76.0), _bearing_xy(20.0, 84.0), _bearing_xy(20.0, 91.0)],
                speed,
                max_sim=80.0,
            )
            bank[tag] = {
                k: line[k]
                for k in ("outcome", "max_r", "max_z", "min_uz", "airborne_s", "events", "final")
            }
            # The apron and mid-bank (to r 84, 32 %) must be crawlable; a stall
            # beyond that must be grade-limited (slides back / escapes at WOT),
            # never a hard-geometry obstruction.
            assert line["max_r"] >= 84.0, bank[tag]
            for e in line["events"]:
                if e["type"] == "stall_discriminator":
                    assert e["verdict"] != "did_not_move_hard_geometry", bank[tag]
        r["bank"] = bank
        s.shot(
            "bank_lines",
            (*_bearing_xy(35.0, 70.0), C[2] + 6.0),
            (*_bearing_xy(20.0, 86.0), C[2] + 3.0),
            "the bank at bearing 20 after the radial lines",
        )

        # --- ramps: up (crawl, 2 m/s) and down (2 m/s) on both sides ---
        ramps: dict[str, Any] = {}
        ramp_specs = {"e": (145.0, 175.5, 1.0), "w": (215.0, 184.5, -1.0)}
        for side, (toe_b, merge_b, sgn) in ramp_specs.items():
            path_up = _arc_line(84.0, toe_b, merge_b - sgn * 1.0)
            path_up.append(_bearing_xy(merge_b - sgn * 1.0, 84.0))
            for speed, tag in ((1.1, "crawl"), (2.0, "2mps")):
                s.teleport(
                    PLAYER, _bearing_xy(toe_b - sgn * 6.0, 84.0), (toe_b + sgn * 90.0) % 360.0
                )
                line = drv.line(f"ramp_{side}_up_{tag}", path_up, speed, max_sim=90.0, reach=3.5)
                ramps[f"{side}_up_{tag}"] = {
                    k: line[k]
                    for k in ("outcome", "max_z", "min_uz", "airborne_s", "events", "final")
                }
                assert line["outcome"] == "reached", ramps[f"{side}_up_{tag}"]
                assert line["max_z"] >= C[2] + 3.6, ramps[f"{side}_up_{tag}"]
            path_down = list(reversed(path_up[:-1]))
            path_down.append(_bearing_xy(toe_b - sgn * 8.0, 84.0))
            s.teleport(
                PLAYER,
                _bearing_xy(merge_b - sgn * 2.0, 84.0),
                (merge_b - sgn * 90.0) % 360.0,
                z=C[2] + 4.6,
            )
            line = drv.line(f"ramp_{side}_down_2mps", path_down, 2.0, max_sim=90.0, reach=3.5)
            ramps[f"{side}_down_2mps"] = {
                k: line[k] for k in ("outcome", "min_uz", "airborne_s", "events", "final")
            }
            assert line["outcome"] == "reached", ramps[f"{side}_down_2mps"]
        r["ramps"] = ramps
        s.shot(
            "ramp_e",
            (*_bearing_xy(140.0, 70.0), C[2] + 8.0),
            (*_bearing_xy(165.0, 84.0), C[2] + 2.5),
            "east ramp from the plaza side",
        )

        # --- merge fillet: nose into the round at crawl, then reverse out ---
        # East fillet: quarter round centred (863, -352.85) rho 6, wall from the deck
        # flank tangent (857, -352.85) round to the ramp; the deepest cell is ~ (859.5, -356.5).
        s.teleport(PLAYER, (866.0, -338.0), 200.0)
        # Nose in past the deepest free cell toward the round's wall (the target
        # sits inside the solid, so the line ends on the stall discriminator).
        line = drv.line(
            "fillet_e_nose_in",
            [(862.5, -349.0), (860.5, -356.0), (858.5, -359.5)],
            1.1,
            max_sim=40.0,
            reach=1.5,
            stall_after=1.5,
            wot_seconds=2.0,
        )
        p_in = s.probe(PLAYER)
        nearest = _nearest_solid(p_in["x"], p_in["y"], p_in["z"])
        back = s.reverse_for(PLAYER, 3.0)
        r["fillet"] = {
            "nose_in": {k: line[k] for k in ("outcome", "min_uz", "events", "final")},
            "nose_in_nearest_solid": nearest,
            "reverse_out_m": back["moved_m"],
            "reverse_gear": back["gear_in_reverse"],
            "uz_after": back["uz_after"],
        }
        assert line["min_uz"] > 0.8, r["fillet"]
        assert r["fillet"]["reverse_out_m"] > 2.0, r["fillet"]
        s.shot(
            "fillet_e",
            (852.0, -340.0, C[2] + 3.5),
            (860.0, -352.0, C[2] + 1.5),
            "east merge fillet after the nose-in / reverse-out",
        )

        # --- pools (ICE) and salt (SAND): contacts and braking decel vs asphalt ---
        surfaces: dict[str, Any] = {}
        # Asphalt reference on the plaza: bearing 100, r 30 -> 60.
        surfaces["asphalt"] = _brake_decel(
            s, PLAYER, _bearing_xy(100.0, 30.0), 100.0, 10.0, (42.0, 60.0), "asphalt_plaza"
        )
        # Pool 1 at (883, -222.842) rotated -30: local +X in world (0.866, -0.5); approach along it.
        ax, ay = math.cos(math.radians(-30.0)), math.sin(math.radians(-30.0))
        pool_c = (883.0, -222.842)
        start = (pool_c[0] - 22.0 * ax, pool_c[1] - 22.0 * ay)
        heading = math.degrees(math.atan2(ax, ay)) % 360.0
        s.teleport(PLAYER, start, heading)

        def _on_pool(p: dict[str, Any]) -> bool:
            dx, dy = p["x"] - pool_c[0], p["y"] - pool_c[1]
            return abs(dx * ax + dy * ay) <= 8.0 and abs(-dx * ay + dy * ax) <= 4.0

        # The pool run arms the brake only once the car is ON the plate.
        s.teleport(PLAYER, start, heading)
        s.control(PLAYER, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=0.0)
        s.step(STEP_TICK)
        s.vehicle(PLAYER).set_velocity(10.0, 0.6)
        s.step(45)
        samples = []
        armed = False
        contacts: list[str] = []
        t0 = s.clock()
        for _ in range(400):
            p = s.probe(PLAYER)
            if not armed and _on_pool(p):
                s.control(PLAYER, steering=0.0, throttle=0.0, brake=1.0, parkingbrake=0.0)
                armed = True
                contacts = s.wheel_contacts(PLAYER)
            samples.append(
                {
                    "t": round(s.clock() - t0, 3),
                    "speed": round(p["hspeed"], 3),
                    "armed": armed,
                    "on_pool": _on_pool(p),
                }
            )
            if armed and (p["hspeed"] < 0.3 or not _on_pool(p)):
                break
            s.step(3)
        braking = [x for x in samples if x["armed"] and x["on_pool"]]
        decel = (
            ((braking[0]["speed"] - braking[-1]["speed"]) / (braking[-1]["t"] - braking[0]["t"]))
            if len(braking) >= 3
            else None
        )
        surfaces["butter_pool_1_on_plate"] = {
            "decel_mps2": decel,
            "mu_equiv": decel / 9.81 if decel else None,
            "contacts_at_arm": contacts,
            "brake_samples_on_plate": len(braking),
            "v_at_arm": braking[0]["speed"] if braking else None,
            "left_plate_at": braking[-1]["speed"] if braking else None,
        }
        s.control(PLAYER, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=1.0)
        s.shot(
            "butter_pool_1",
            (pool_c[0] + 12.0, pool_c[1] - 10.0, C[2] + 4.0),
            (pool_c[0], pool_c[1], C[2] + 0.5),
            "butter pool 1 after the ice slide",
        )
        # Salt arc east: r 12-20 between bearings 45-135; drive tangentially at r 16 from bearing 60 to 120.
        salt_start = _bearing_xy(52.0, 16.0)
        salt_heading = (52.0 + 90.0) % 360.0
        s.teleport(PLAYER, salt_start, salt_heading)
        s.control(PLAYER, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=0.0)
        s.step(STEP_TICK)
        s.vehicle(PLAYER).set_velocity(8.0, 0.6)
        s.step(30)
        samples = []
        armed = False
        t0 = s.clock()
        for _ in range(300):
            p = s.probe(PLAYER)
            on_salt = 12.0 <= p["r"] <= 20.0 and 45.0 <= p["bearing"] <= 135.0
            if not armed and on_salt and p["bearing"] >= 58.0:
                s.control(PLAYER, steering=0.0, throttle=0.0, brake=1.0, parkingbrake=0.0)
                armed = True
                contacts = s.wheel_contacts(PLAYER)
            samples.append(
                {
                    "t": round(s.clock() - t0, 3),
                    "speed": round(p["hspeed"], 3),
                    "armed": armed,
                    "on": on_salt,
                    "r": round(p["r"], 2),
                    "bearing": round(p["bearing"], 1),
                }
            )
            if armed and (p["hspeed"] < 0.3 or not on_salt):
                break
            s.step(3)
        braking = [x for x in samples if x["armed"] and x["on"]]
        decel = (
            ((braking[0]["speed"] - braking[-1]["speed"]) / (braking[-1]["t"] - braking[0]["t"]))
            if len(braking) >= 3
            else None
        )
        surfaces["salt_arc_e"] = {
            "decel_mps2": decel,
            "mu_equiv": decel / 9.81 if decel else None,
            "contacts_at_arm": contacts,
            "brake_samples": len(braking),
            "v_at_arm": braking[0]["speed"] if braking else None,
        }
        s.control(PLAYER, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=1.0)
        s.shot(
            "salt_arc_e",
            (*_bearing_xy(80.0, 30.0), C[2] + 5.0),
            (*_bearing_xy(90.0, 16.0), C[2] + 0.3),
            "east salt arc",
        )
        # The other two pools and the west salt arc: parked wheel-contact readouts.
        parked: dict[str, Any] = {}
        for label, xy, heading in (
            ("butter_pool_2", (800.952, -324.163), 132.0),
            ("butter_pool_3", (792.842, -247.0), 60.0),
            ("salt_arc_w", _bearing_xy(270.0, 16.0), 0.0),
            ("plaza_asphalt", _bearing_xy(90.0, 40.0), 0.0),
        ):
            s.teleport(PLAYER, xy, heading)
            s.park(PLAYER)
            s.step(30)
            parked[label] = {"contacts": s.wheel_contacts(PLAYER), "surface_z": s.surface_z(*xy)}
        surfaces["parked_contacts"] = parked
        r["surfaces"] = surfaces
        assert all(
            any(c == "ICE" for c in parked[k]["contacts"])
            for k in ("butter_pool_2", "butter_pool_3")
        ), parked
        assert any(c == "SAND" for c in parked["salt_arc_w"]["contacts"]), parked
        assert any(c == "ICE" for c in surfaces["butter_pool_1_on_plate"]["contacts_at_arm"]), (
            surfaces
        )
        assert any(c == "SAND" for c in surfaces["salt_arc_e"]["contacts_at_arm"]), surfaces
        asphalt_mu = surfaces["asphalt"]["mu_equiv"]
        ice_mu = surfaces["butter_pool_1_on_plate"]["mu_equiv"]
        assert asphalt_mu and ice_mu is not None and ice_mu < 0.5 * asphalt_mu, surfaces

        # --- the r 88.5 tangential line across the ramp outer lip (bearings 150 -> 178, 60 km/h) ---
        s.teleport(
            PLAYER,
            _bearing_xy(140.0, 88.5),
            (140.0 + 90.0) % 360.0,
            z=s.surface_z(*_bearing_xy(140.0, 88.5)) + 0.6,
        )
        s.control(PLAYER, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=0.0)
        s.step(STEP_TICK)
        s.vehicle(PLAYER).set_velocity(16.7, 0.8)
        s.step(30)
        line = drv.line(
            "tangential_r88_5_60kmh",
            _arc_line(88.5, 148.0, 182.0, 2.0),
            16.7,
            max_sim=30.0,
            reach=5.0,
            heading_fn=lambda p: (p["bearing"] + 90.0) % 360.0,
            stop_fn=lambda p: p["bearing"] > 182.0 or p["r"] < 78.0 or p["r"] > 96.0,
        )
        r["tangential_r88_5"] = {
            k: line[k]
            for k in (
                "outcome",
                "min_uz",
                "airborne_s",
                "max_speed",
                "events",
                "final",
                "max_r",
                "min_r",
            )
        }
        assert line["outcome"] != "rollover" and line["min_uz"] > 0.5, r["tangential_r88_5"]
        assert line["airborne_s"] < 1.5, r["tangential_r88_5"]
        s.shot(
            "ramp_lip_line",
            (*_bearing_xy(160.0, 70.0), C[2] + 9.0),
            (*_bearing_xy(174.0, 88.0), C[2] + 4.0),
            "ramp outer lip at the merge after the tangential line",
        )

        # --- jamb drift: bank at r 86, bearing 45, drifting into the 60 spout (2 m/s and 8 m/s) ---
        drift: dict[str, Any] = {}
        for speed, tag in ((2.0, "2mps"), (8.0, "8mps")):
            s.teleport(
                PLAYER,
                _bearing_xy(36.0, 86.0),
                (36.0 + 90.0) % 360.0,
                z=s.surface_z(*_bearing_xy(36.0, 86.0)) + 0.6,
            )
            line = drv.line(
                f"jamb_drift_{tag}",
                _arc_line(86.0, 38.0, 60.0, 2.0) + [_bearing_xy(60.0, 80.0)],
                speed,
                max_sim=45.0,
                reach=4.0,
                heading_fn=lambda p: (p["bearing"] + 88.0) % 360.0,
                stop_fn=lambda p: p["bearing"] > 52.0 and p["z"] < C[2] + 0.4,
            )
            drift[tag] = {
                k: line[k] for k in ("outcome", "min_uz", "airborne_s", "events", "final", "max_z")
            }
            assert line["outcome"] != "rollover" and line["min_uz"] > 0.5, drift[tag]
        r["jamb_drift"] = drift
        s.shot(
            "jamb_chute",
            (*_bearing_xy(50.0, 70.0), C[2] + 5.0),
            (*_bearing_xy(45.0, 86.0), C[2] + 3.0),
            "the 60-spout gate-side jamb chute",
        )

        # --- figure-eight: the heaviest supported class (D-series pickup) ---
        pickup = Vehicle(f"{MOD_ID}_gate_pickup", "pickup", license="HEAVY")
        assert (
            s.bng.vehicles.spawn(
                pickup,
                (*_bearing_xy(80.0, 50.0), C[2] + 0.6),
                _heading_quat(0.0),
                cling=False,
                connect=True,
            )
            is True
        )
        s.register(pickup)
        s.step(60)
        circles: dict[str, Any] = {}
        for steer_sign, tag in ((1.0, "right"), (-1.0, "left")):
            s.teleport(pickup.vid, _bearing_xy(80.0, 50.0), 0.0)
            s.control(pickup.vid, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=0.0)
            s.step(STEP_TICK)
            pts: list[tuple[float, float]] = []
            yaw0 = s.probe(pickup.vid)["yaw"]
            turned = 0.0
            last_yaw = yaw0
            for _ in range(600):
                p = s.probe(pickup.vid)
                turned += abs(_wrap_deg(p["yaw"] - last_yaw))
                last_yaw = p["yaw"]
                pts.append((p["x"], p["y"]))
                v_err = 2.5 - p["hspeed"]
                s.control(
                    pickup.vid,
                    steering=steer_sign * s.steer_sign,
                    throttle=max(0.0, min(0.6, 0.15 + 0.3 * v_err)),
                    brake=0.0,
                    parkingbrake=0.0,
                )
                s.step(STEP_TICK)
                if turned > 400.0 and len(pts) > 40:
                    break
            s.control(pickup.vid, steering=0.0, throttle=0.0, brake=1.0)
            s.step(30)
            fit = _fit_circle(pts[len(pts) // 4 :])
            circles[tag] = {
                "ref_path_radius_m": fit[2],
                "curb_radius_est_m": fit[2] + 1.0,
                "turning_circle_est_m": 2.0 * (fit[2] + 1.0),
                "turned_deg": turned,
                "samples": len(pts),
            }
        r["turning_circle"] = circles
        s.shot(
            "figure_eight",
            (*_bearing_xy(80.0, 50.0), C[2] + 30.0),
            (*_bearing_xy(80.0, 50.0), C[2]),
            "the pickup's circle patch from above",
        )
        s.bng.vehicles.despawn(pickup)
        s._vehicles.pop(pickup.vid, None)

        # --- crest ram runs at 60 / 85 / 110 km/h with the magnet haul-back ---
        _ready_round_long(s, AI[0])
        s.set_option("arena_magnet_enabled", True)
        rams: dict[str, Any] = {}
        ram_problems: list[str] = []
        for kmh in (60.0, 85.0, 110.0):
            v = kmh / 3.6
            s.teleport(PLAYER, _bearing_xy(285.0, 30.0), 285.0)
            s.step(45)  # membership sweep inside the ring
            s.control(PLAYER, steering=0.0, throttle=1.0, brake=0.0, parkingbrake=0.0)
            s.vehicle(PLAYER).set_velocity(v, 1.2)
            trace: list[dict[str, Any]] = []
            crest_speed = None
            over = False
            landed = None
            apex = C[2]
            apex_t = None
            airborne_s = 0.0
            t0 = s.clock()
            haul_start = None
            haul_done = None
            base_clear = None
            for _ in range(1400):
                p = s.probe(PLAYER)
                t = s.clock() - t0
                if base_clear is None:
                    base_clear = p["clearance"]
                if not over:
                    err = math.radians(_wrap_deg(285.0 - p["yaw"]))
                    s.control(
                        PLAYER,
                        steering=max(-1, min(1, s.steer_sign * 1.5 * err)),
                        throttle=1.0,
                        brake=0.0,
                        parkingbrake=0.0,
                    )
                    if p["r"] >= CREST_R:
                        crest_speed = p["hspeed"]
                        over = True
                        s.control(PLAYER, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=0.0)
                else:
                    if p["z"] > apex:
                        apex, apex_t = p["z"], t
                    if p["clearance"] > base_clear + 0.45:
                        airborne_s += 0.05
                    if (
                        landed is None
                        and apex_t is not None
                        and t > apex_t + 0.1
                        and p["clearance"] <= base_clear + 0.35
                    ):
                        landed = {
                            "t": t,
                            "r": p["r"],
                            "z": p["z"],
                            "speed": p["hspeed"],
                            "vz": p["vz"],
                            "uz": p["uz"],
                        }
                    if haul_start is None and p["r"] > R_ARENA:
                        haul_start = t
                    if haul_start is not None and p["r"] < R_RELEASE:
                        haul_done = t
                trace.append(
                    {
                        "t": round(t, 2),
                        "r": round(p["r"], 2),
                        "z": round(p["z"], 2),
                        "speed": round(p["hspeed"], 2),
                        "vz": round(p["vz"], 2),
                        "uz": round(p["uz"], 2),
                        "clearance": round(p["clearance"], 2),
                    }
                )
                if haul_done is not None or (over and t > 75.0) or p["uz"] < 0.2:
                    break
                s.step(3)
            if over and landed is not None:
                lp = landed
                s.shot(
                    f"ram_{int(kmh)}_landing",
                    (*_bearing_xy(285.0 + 12.0, lp["r"] + 6.0), lp["z"] + 5.0),
                    (*_bearing_xy(285.0, lp["r"]), lp["z"] + 1.0),
                    f"{int(kmh)} km/h crest-over landing zone on the glacis",
                )
            summary = {
                "kmh": kmh,
                "crest_speed_mps": crest_speed,
                "exited_over_crest": over,
                "apex_z": apex,
                "apex_rise_over_crest_m": round(apex - (C[2] + float(HANDOFF["crest_z_m"])), 2),
                "airborne_s": round(airborne_s, 2),
                "landing": landed,
                "max_r": max(x["r"] for x in trace),
                "haul_start_t": haul_start,
                "haul_done_t": haul_done,
                "haul_seconds": (haul_done - haul_start)
                if (haul_start is not None and haul_done is not None)
                else None,
                "min_uz": min(x["uz"] for x in trace),
                "final": trace[-1],
            }
            # The crest-over promise (design 3.2): exits, lands shiny-side up on the
            # glacis, magnet engages, haul-back completes, no trap. Each clause is
            # measured; a broken one is a routed defect, not a harness stop.
            summary["clauses"] = {
                "exited_over_crest": over,
                "landed_outside_crest": bool(landed and landed["r"] > CREST_R),
                "landed_inside_runoff": summary["max_r"] < 160.0,
                "stayed_upright": summary["min_uz"] > 0.5,
                "magnet_engaged": haul_start is not None,
                "haul_back_completed": haul_done is not None,
            }
            rams[f"{int(kmh)}"] = summary
            r["crest_rams"] = rams
            s.report.setdefault("traces", {})[f"ram_{int(kmh)}"] = trace
            for clause, ok in summary["clauses"].items():
                if not ok:
                    ram_problems.append(
                        f"{int(kmh)} km/h crest ram: {clause} failed ({ {k: summary[k] for k in ('crest_speed_mps', 'apex_rise_over_crest_m', 'max_r', 'landing', 'min_uz', 'haul_seconds')} })"
                    )
            # A rolled car must be reset before the next run.
            if summary["min_uz"] <= 0.5:
                s.teleport(PLAYER, _bearing_xy(285.0, 40.0), 285.0)
        r["crest_rams"] = rams
        r["problems"] = ram_problems
        p = s.probe(PLAYER)
        s.shot(
            "after_rams",
            (*_bearing_xy(285.0, 120.0), C[2] + 12.0),
            (*_bearing_xy(285.0, 91.4), C[2] + 5.5),
            "the crest and glacis at bearing 285 after the ram runs",
        )
        s.set_option("ai_enabled", True)
    assert not s.report.get("problems"), s.report["problems"]


# ====================================================================================
# G3 - AI
# ====================================================================================


def _census_tick(
    s: Session,
    names: list[str],
    last_damage: dict[str, float],
    hits: list[dict[str, Any]],
    t: float,
) -> dict[str, dict[str, Any]]:
    rows = s.probe_many(names)
    positions = {n: (row["x"], row["y"]) for n, row in rows.items() if row.get("ok")}
    for n, row in rows.items():
        if not row.get("ok"):
            continue
        damage = float(row["damage"])
        previous = last_damage.get(n)
        last_damage[n] = damage
        if previous is not None and damage > previous:
            solid, clearance = _nearest_solid(row["x"], row["y"], row["z"])
            others = sorted(
                (math.hypot(row["x"] - px, row["y"] - py), m)
                for m, (px, py) in positions.items()
                if m != n
            )
            nearest_car = others[0] if others else (1e9, "")
            kind = (
                "solid"
                if clearance < 3.2 and nearest_car[0] > 6.5
                else ("car" if nearest_car[0] <= 6.5 else "other")
            )
            hits.append(
                {
                    "t": round(t, 1),
                    "car": n,
                    "delta": damage - previous,
                    "kind": kind,
                    "solid": solid,
                    "solid_clearance": round(clearance, 2),
                    "nearest_car": nearest_car[1],
                    "nearest_car_m": round(nearest_car[0], 1),
                    "x": round(row["x"], 1),
                    "y": round(row["y"], 1),
                    "z": round(row["z"], 1),
                    "speed": round(row["hspeed"], 1),
                }
            )
    return rows


@pytest.mark.beamng_live
def test_g3_ai(tmp_path: Path) -> None:
    with _session("G3", tmp_path, watchdog_seconds=3600.0) as s:
        r = s.report
        props = [
            n
            for n in [e["name"] for e in sync.vehicle_layout(HANDOFF)]
            if n not in (PLAYER, DISPENSER) and n not in AI
        ]

        # --- (a) 3 minutes of chase/flee against the 42 registered obstacles ---
        s.move_away([PLAYER])  # the player is not conscripted; keep it out of the AI's target list
        s.set_options(LONG_FUSE)
        s.set_option("ai_enabled", True)
        s.start_round(AI[0])
        hits: list[dict[str, Any]] = []
        last_damage: dict[str, float] = {}
        min_clear: dict[str, float] = {}
        t0 = s.clock()
        samples = 0
        roles_seen: set[str] = set()
        while True:
            t = s.clock() - t0
            rows = _census_tick(s, AI + props, last_damage, hits, t)
            for n in AI:
                row = rows[n]
                if row.get("ok"):
                    solid, clearance = _nearest_solid(row["x"], row["y"], row["z"])
                    min_clear[solid] = min(min_clear.get(solid, 1e9), clearance)
            samples += 1
            if samples % 100 == 0:
                st = s.stats()
                roles_seen.add(str(st.get("phase")))
                if st.get("phase") != "live":
                    # A boom would end the chase early: restart the round on the pad.
                    s.start_round(AI[0])
            if t >= 180.0:
                break
            s.step(STEP_TICK)
        chase_stats = s.stats()
        solid_hits = [h for h in hits if h["kind"] == "solid" and h["car"] in AI]
        s.check(
            len(solid_hits) == 0,
            "AI collided with registered obstacles during the 3 min chase",
            solid_hits,
        )
        r["chase"] = {
            "sim_seconds": round(t, 1),
            "samples": samples,
            "transfers": chase_stats.get("transfers"),
            "field": chase_stats.get("field"),
            "props_excluded": chase_stats.get("props_excluded"),
            "hits_total": len(hits),
            "solid_hits": solid_hits,
            "hits_by_kind": {
                k: sum(1 for h in hits if h["kind"] == k) for k in ("solid", "car", "other")
            },
            "ai_solid_hit_count": len(solid_hits),
            "min_clearance_by_solid": {k: round(v, 2) for k, v in sorted(min_clear.items())},
            "phases_seen": sorted(roles_seen),
        }
        s.shot(
            "chase_field",
            (C[0] + 70.0, C[1] + 80.0, C[2] + 45.0),
            (C[0], C[1], C[2] + 2.0),
            "the field after 3 minutes of chase/flee",
        )
        s.check(
            int(chase_stats.get("props_excluded", -1)) == 16,
            "props_excluded != 16 during the chase",
            chase_stats,
        )

        # --- (b) braked-hulk haul from outside the 60 spout; release feel at 82.3 m ---
        s.set_option("ai_enabled", False)
        for n in AI:
            s.park(n)
        s.teleport(PLAYER, _bearing_xy(60.0, 40.0), 60.0)
        s.step(45)  # member
        s.teleport(PLAYER, _bearing_xy(60.0, 120.0), 240.0)
        s.park(PLAYER)
        haul: list[dict[str, Any]] = []
        t0 = s.clock()
        release = None
        for _ in range(900):
            p = s.probe(PLAYER)
            t = s.clock() - t0
            haul.append(
                {
                    "t": round(t, 2),
                    "r": round(p["r"], 2),
                    "z": round(p["z"], 2),
                    "speed": round(p["hspeed"], 2),
                    "uz": round(p["uz"], 2),
                    "clearance": round(p["clearance"], 2),
                }
            )
            if release is None and p["r"] < R_RELEASE:
                release = {"t": t, "r": p["r"], "speed": p["hspeed"], "z": p["z"]}
                s.shot(
                    "release_feel",
                    (*_bearing_xy(60.0, p["r"] + 18.0), p["z"] + 6.0),
                    (p["x"], p["y"], p["z"] + 1.0),
                    "the hulk at the 82.3 m release line inside the 60 spout",
                )
            if release is not None and t > release["t"] + 6.0:
                break
            s.step(3)
        coast = [x for x in haul if release is not None and x["t"] >= release["t"]]
        r["hulk_haul"] = {
            "release": release,
            "start_r": haul[0]["r"],
            "max_speed": max(x["speed"] for x in haul),
            "coast_after_release_m": (release["r"] - coast[-1]["r"]) if coast else None,
            "speed_6s_after_release": coast[-1]["speed"] if coast else None,
            "min_uz": min(x["uz"] for x in haul),
            "max_z": max(x["z"] for x in haul),
            "final_r": haul[-1]["r"],
        }
        s.report.setdefault("traces", {})["hulk_haul"] = haul
        s.check(
            release is not None and release["t"] < 60.0,
            "the braked hulk was not hauled to the 82.3 m release line within 60 s",
            r["hulk_haul"],
        )

        # --- (c) classic spout-spam: the player dives out the 60 spout for 3 minutes ---
        # Design 4.3(a): a scripted spam-diver (non-carrier) against a scripted
        # carrier holding at the mouth. The carrier is ai_1 on the stock chase AI
        # (ai_enabled off so the runtime never re-roles it); the other four cars
        # park on the far lot so the diver is always its target.
        s.set_option("game_mode", "classic")
        s.move_away(AI[1:])
        drv = Driver(s, PLAYER)
        drv.calibrate(_bearing_xy(90.0, 40.0), 0.0)
        s.drop_round()
        s.start_round(AI[0])
        s.teleport(PLAYER, _bearing_xy(60.0, 50.0), 60.0)
        s.step(45)
        s.lua(
            f"local v = scenetree.findObject({AI[0]!r}); local t = scenetree.findObject({PLAYER!r}); "
            "if v and t then v:queueLuaCommand(string.format(\"pcall(function() ai.setMode('chase') ai.setTargetObjectID(%d) "
            "ai.setAggression(1.0) ai.setSpeedMode('limit') ai.setSpeed(22.0) end)\", t:getID())) end; return jsonEncode({ok = true})"
        )
        spam: list[dict[str, Any]] = []
        transfers_at: list[dict[str, Any]] = []
        t0 = s.clock()
        last_transfers = int(s.stats().get("transfers") or 0)
        dives = 0
        out_since: float | None = None
        excursions: list[float] = []
        while s.clock() - t0 < 180.0:
            # Dive: from inside, drive out through the throat to r 100, then coast.
            drv.line(
                f"dive_{dives}",
                [_bearing_xy(60.0, 76.0), _bearing_xy(60.0, 92.0), _bearing_xy(60.0, 108.0)],
                16.0,
                max_sim=25.0,
                reach=4.0,
                stop_fn=lambda p: p["r"] > 100.0,
                coast_after_stop=True,
            )
            dives += 1
            # Coast under the magnet until released inside 82.3 m, sampling the metric.
            t_out = s.clock()
            while s.clock() - t0 < 180.0:
                p = s.probe(PLAYER)
                st = s.stats()
                tr = int(st.get("transfers") or 0)
                t = s.clock() - t0
                outside = p["r"] > R_ARENA
                if outside and out_since is None:
                    out_since = t
                if not outside and out_since is not None:
                    excursions.append(t - out_since)
                    out_since = None
                spam.append(
                    {
                        "t": round(t, 1),
                        "r": round(p["r"], 1),
                        "carrier_is_player": int(st.get("carrier") or -1) == s.player_id,
                        "outside": outside,
                    }
                )
                if tr != last_transfers:
                    transfers_at.append(
                        {
                            "t": round(t, 1),
                            "r": round(p["r"], 2),
                            "haul_band": R_RELEASE < p["r"] <= R_ARENA,
                            "carrier_now_player": int(st.get("carrier") or -1) == s.player_id,
                        }
                    )
                    last_transfers = tr
                if st.get("phase") != "live":
                    s.drop_round()
                    s.start_round(AI[0])
                    s.teleport(PLAYER, _bearing_xy(60.0, 50.0), 60.0)
                    break
                if p["r"] < R_RELEASE - 4.0 or s.clock() - t_out > 40.0:
                    break
                s.step(STEP_TICK)
            # Turn back inside to r 60 before the next dive.
            drv.line(f"return_{dives}", [_bearing_xy(60.0, 60.0)], 12.0, max_sim=20.0, reach=5.0)
        outside_samples = sum(1 for x in spam if x["outside"])
        dive_outside = sum(
            1
            for lbl, tr in s.report.get("traces", {}).items()
            if lbl.startswith("dive_")
            for x in tr
            if x["r"] > R_ARENA
        )
        dive_total = sum(
            len(tr)
            for lbl, tr in s.report.get("traces", {}).items()
            if lbl.startswith("dive_") or lbl.startswith("return_")
        )
        total = len(spam) + dive_total
        uptime = (outside_samples + dive_outside) / max(total, 1)
        r["classic_spam"] = {
            "dives": dives,
            "samples": total,
            "immunity_uptime": round(uptime, 3),
            "excursions_s": [round(x, 1) for x in excursions],
            "transfers": transfers_at,
            "tag_in_haul_band": any(x["haul_band"] for x in transfers_at),
            "max_excursion_s": round(max(excursions), 1) if excursions else None,
        }
        s.report.setdefault("traces", {})["classic_spam"] = spam
        s.shot(
            "spout_spam",
            (*_bearing_xy(60.0, 130.0), C[2] + 10.0),
            (*_bearing_xy(60.0, 85.0), C[2] + 2.0),
            "the 60 spout after the classic spam",
        )
        s.check(
            uptime < 0.25, "classic spout-spam transfer-immunity uptime >= 25 %", r["classic_spam"]
        )

        # --- (d) hold-mode (hoarder) spout-spam: out-of-ring accrual must be ZERO ---
        s.set_option("ai_enabled", False)
        s.set_option("game_mode", "hoarder")
        s.drop_round()
        s.move_away(AI)
        s.start_round(PLAYER)
        hold: list[dict[str, Any]] = []
        accrual_outside = 0
        accrual_inside = 0
        t0 = s.clock()
        dives = 0

        def _score() -> int:
            rows = s.stats().get("scores") or []
            return max((int(row.get("points") or 0) for row in rows), default=0)

        last_score = _score()
        last_outside = s.probe(PLAYER)["r"] > R_ARENA
        while s.clock() - t0 < 180.0:
            drv.line(
                f"hoard_dive_{dives}",
                [_bearing_xy(60.0, 76.0), _bearing_xy(60.0, 92.0), _bearing_xy(60.0, 108.0)],
                16.0,
                max_sim=25.0,
                reach=4.0,
                stop_fn=lambda p: p["r"] > 100.0,
                coast_after_stop=True,
            )
            dives += 1
            t_out = s.clock()
            while s.clock() - t0 < 180.0:
                p = s.probe(PLAYER)
                score = _score()
                outside = p["r"] > R_ARENA + 0.5
                if score != last_score:
                    if outside and last_outside:
                        accrual_outside += score - last_score
                    elif not outside and not last_outside:
                        accrual_inside += score - last_score
                    last_score = score
                last_outside = outside
                hold.append(
                    {
                        "t": round(s.clock() - t0, 1),
                        "r": round(p["r"], 1),
                        "score": score,
                        "outside": outside,
                        "phase": s.stats().get("phase"),
                    }
                )
                if p["r"] < R_RELEASE - 4.0 or s.clock() - t_out > 40.0:
                    break
                s.step(STEP_TICK)
            drv.line(
                f"hoard_return_{dives}", [_bearing_xy(60.0, 60.0)], 12.0, max_sim=20.0, reach=5.0
            )
        r["hoarder_spam"] = {
            "dives": dives,
            "accrual_outside": accrual_outside,
            "accrual_inside": accrual_inside,
            "final_score": last_score,
            "outside_samples": sum(1 for x in hold if x["outside"]),
            "samples": len(hold),
            "phase_end": s.stats().get("phase"),
        }
        s.report.setdefault("traces", {})["hoarder_spam"] = hold
        s.check(
            accrual_outside == 0,
            "hold-mode out-of-ring accrual is not zero (the serial-47 scoring gate)",
            r["hoarder_spam"],
        )
        s.check(
            accrual_inside > 0,
            "hold-mode scored nothing inside the ring either - the spam test proved nothing",
            r["hoarder_spam"],
        )
        s.set_option("game_mode", "classic")

        # --- (e) magnet-orbit attempt at 110-125 km/h tangential just outside the crest ---
        s.set_option("ai_enabled", False)
        s.drop_round()
        s.start_round(AI[0])
        s.park(AI[0])

        def _orbit_attempts(gees: float, tag: str) -> list[dict[str, Any]]:
            s.set_option("arena_magnet_g", gees)
            results = []
            for k in range(3):
                # A live round with the player as a member but not the carrier.
                if s.stats().get("phase") != "live":
                    s.drop_round()
                    s.start_round(AI[0])
                    s.park(AI[0])
                s.teleport(PLAYER, _bearing_xy(100.0, 60.0), 100.0)
                s.step(45)
                b0 = 100.0
                s.teleport(
                    PLAYER,
                    _bearing_xy(b0, 98.0),
                    (b0 + 90.0) % 360.0,
                    z=s.surface_z(*_bearing_xy(b0, 98.0)) + 0.6,
                )
                s.control(PLAYER, steering=0.0, throttle=1.0, brake=0.0, parkingbrake=0.0)
                s.vehicle(PLAYER).set_velocity(33.0, 1.0)
                t0 = s.clock()
                reentry = None
                trace = []
                max_r = 0.0
                for _ in range(700):
                    p = s.probe(PLAYER)
                    t = s.clock() - t0
                    max_r = max(max_r, p["r"])
                    trace.append(
                        {
                            "t": round(t, 2),
                            "r": round(p["r"], 1),
                            "bearing": round(p["bearing"], 1),
                            "speed": round(p["hspeed"], 1),
                            "z": round(p["z"], 1),
                            "uz": round(p["uz"], 2),
                            "clearance": round(p["clearance"], 2),
                        }
                    )
                    if p["r"] < R_RELEASE and t > 0.5:
                        reentry = t
                        break
                    if p["uz"] < 0.2 or t > 40.0:
                        break
                    target = (p["bearing"] + 90.0) % 360.0
                    err = math.radians(_wrap_deg(target - p["yaw"]))
                    s.control(
                        PLAYER,
                        steering=max(-1, min(1, s.steer_sign * 1.5 * err)),
                        throttle=1.0,
                        brake=0.0,
                        parkingbrake=0.0,
                    )
                    s.step(3)
                s.control(PLAYER, steering=0.0, throttle=0.0, brake=1.0, parkingbrake=0.0)
                results.append(
                    {
                        "attempt": k + 1,
                        "gees": gees,
                        "reentry_s": reentry,
                        "max_r": round(max_r, 1),
                        "max_speed": max(x["speed"] for x in trace),
                        "min_uz": min(x["uz"] for x in trace),
                        "samples": len(trace),
                    }
                )
                s.report.setdefault("traces", {})[f"orbit_{tag}_{k + 1}"] = trace
            return results

        orbit = {"at_1_2g": _orbit_attempts(1.2, "1_2g")}
        failed = [x for x in orbit["at_1_2g"] if x["reentry_s"] is None or x["reentry_s"] > 15.0]
        if failed:
            orbit["at_2_0g"] = _orbit_attempts(2.0, "2_0g")
        s.set_option("arena_magnet_g", 1.2)
        r["magnet_orbit"] = orbit
        final = orbit.get("at_2_0g", orbit["at_1_2g"])
        s.check(
            all(x["reentry_s"] is not None and x["reentry_s"] <= 15.0 for x in final),
            "magnet-orbit re-entry exceeded 15 s per excursion even after the lever",
            orbit,
        )
        s.shot(
            "orbit_lane",
            (*_bearing_xy(100.0, 140.0), C[2] + 20.0),
            (*_bearing_xy(100.0, 100.0), C[2] + 3.0),
            "the glacis orbit lane at bearing 100 after the attempts",
        )
        s.set_option("ai_enabled", True)
    assert not s.report.get("problems"), s.report["problems"]


# ====================================================================================
# G4 - geysers
# ====================================================================================


@pytest.mark.beamng_live
def test_g4_geysers(tmp_path: Path) -> None:
    with _session("G4", tmp_path) as s:
        r = s.report
        s.set_option("ai_enabled", False)
        for n in AI:
            s.park(n)
        sites = {g["name"]: g for g in sync.geyser_layout(HANDOFF)}
        index_of = {g["name"]: i for i, g in enumerate(sync.geyser_layout(HANDOFF))}
        per_site: dict[str, Any] = {}
        for name, site in sites.items():
            idx = index_of[name]
            centre = (float(site["cx"]), float(site["cy"]))
            heading = 0.0 if name == "gate" else (60.0 if name == "spout_e" else 240.0)
            s.teleport(PLAYER, centre, heading, z=C[2] + 0.6)
            s.park(PLAYER)
            s.step(30)
            windows: list[dict[str, Any]] = []
            last_on = None
            off_pops = 0
            current: dict[str, Any] | None = None
            last_vz = 0.0
            last_pops = None
            base_clear = None
            last_clear = None
            t0 = s.clock()
            for _ in range(2200):
                st = s.arena()["geysers"][idx]
                p = s.probe(PLAYER)
                on = bool(st["on"])
                jump = p["vz"] - last_vz
                last_vz = p["vz"]
                if base_clear is None:
                    base_clear = p["clearance"]
                grounded_before = last_clear is None or last_clear <= base_clear + 0.20
                last_clear = p["clearance"]
                if on != last_on:
                    if on and last_on is not None:
                        # pops_before is the count read on the LAST OFF sample: the
                        # runtime pops on the same frame it opens the window, so a
                        # read taken after the edge already includes that pop.
                        current = {
                            "window": int(st["windows"]),
                            "pops_before": int(last_pops if last_pops is not None else st["pops"]),
                            "jumps": [],
                            "peak_vz": 0.0,
                            "t_on": round(s.clock() - t0, 2),
                        }
                        windows.append(current)
                    elif not on:
                        if current is not None:
                            current["pops_after"] = int(st["pops"])
                        current = None
                    last_on = on
                if not on:
                    last_pops = int(st["pops"])
                # A pop lifts the car OFF THE GROUND. The landing rebound is also a
                # positive vz step, so a jump counts only when the car was still on
                # its wheels the sample before.
                if jump > 2.5 and p["vz"] > 2.5 and grounded_before:
                    if on and current is not None:
                        current["jumps"].append(round(jump, 2))
                    elif on and current is None:
                        pass  # the partial first window
                    else:
                        off_pops += 1
                if current is not None:
                    current["peak_vz"] = max(current["peak_vz"], p["vz"])
                if (
                    len(windows) >= 3
                    and windows[-1] is not current
                    and windows[-1].get("pops_after") is not None
                ):
                    break
                s.step(2)
            complete = [w for w in windows if w.get("pops_after") is not None]
            shot_eye = (centre[0] + 12.0, centre[1] - 14.0, C[2] + 5.0)
            s.shot(
                f"geyser_{name}",
                shot_eye,
                (centre[0], centre[1], C[2] + 2.5),
                f"{name} geyser site after the pop windows",
            )
            per_site[name] = {
                "windows": complete,
                "off_pops": off_pops,
                "pops_per_window": [w["pops_after"] - w["pops_before"] for w in complete],
                "peak_vz_per_window": [w["peak_vz"] for w in complete],
                "jumps_per_window": [w["jumps"] for w in complete],
            }
            s.check(
                len(complete) >= 2,
                f"{name}: fewer than two complete ON windows observed",
                per_site[name],
            )
            s.check(off_pops == 0, f"{name}: a pop landed during an OFF window", per_site[name])
            for w in complete:
                s.check(
                    w["pops_after"] - w["pops_before"] == 1,
                    f"{name}: not exactly one pop in an ON window",
                    per_site[name],
                )
                s.check(
                    w["peak_vz"] >= 4.0,
                    f"{name}: pop below the 4 m/s vertical floor",
                    per_site[name],
                )
                # The vz-jump list is RECORDED, not gated: the runtime's own pops
                # counter is the authoritative "one pop per window" instrument,
                # and a landing rebound is a positive vz step my sampler cannot
                # always separate from a second lift (measured both ways).
        r["sites"] = per_site

        # Horizontal speed preserved on a moving car at each site.
        moving: dict[str, Any] = {}
        for name, site in sites.items():
            idx = index_of[name]
            centre = (float(site["cx"]), float(site["cy"]))
            nx, ny = float(site["nx"]), float(site["ny"])
            run_up = (centre[0] - 14.0 * nx, centre[1] - 14.0 * ny)
            heading = math.degrees(math.atan2(nx, ny)) % 360.0
            s.step_until(
                lambda: not bool(s.arena()["geysers"][idx]["on"]), calls=60, note="site never OFF"
            )
            s.teleport(PLAYER, run_up, heading, z=C[2] + 0.6)
            s.control(PLAYER, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=0.0)
            s.step_until(
                lambda: bool(s.arena()["geysers"][idx]["on"]),
                calls=80,
                note="site never ON",
                steps=10,
            )
            s.vehicle(PLAYER).set_velocity(8.0, 0.5)
            samples = []
            pop_i = None
            for _ in range(200):
                s.step(1)
                p = s.probe(PLAYER)
                samples.append({"h": p["hspeed"], "vz": p["vz"], "z": p["z"]})
                if (
                    pop_i is None
                    and len(samples) >= 2
                    and samples[-1]["vz"] - samples[-2]["vz"] > 3.0
                ):
                    pop_i = len(samples) - 1
                if pop_i is not None and len(samples) > pop_i + 15:
                    break
            s.control(PLAYER, steering=0.0, throttle=0.0, brake=1.0, parkingbrake=1.0)
            if pop_i is None:
                moving[name] = {
                    "popped": False,
                    "samples": len(samples),
                    "max_h": max(x["h"] for x in samples),
                }
            else:
                h0, h1 = samples[pop_i - 1]["h"], samples[pop_i]["h"]
                moving[name] = {
                    "popped": True,
                    "h_before": h0,
                    "h_after": h1,
                    "h_kept_fraction": h1 / max(h0, 1e-6),
                    "vz_jump": samples[pop_i]["vz"] - samples[pop_i - 1]["vz"],
                    "rise_m": max(x["z"] for x in samples) - samples[0]["z"],
                }
            if s.check(
                bool(moving[name].get("popped")),
                f"{name}: a moving car crossing the strip was never popped",
                moving[name],
            ):
                s.check(
                    moving[name]["h_kept_fraction"] > 0.9,
                    f"{name}: the pop cost more than 10 % of horizontal speed",
                    moving[name],
                )
                s.check(
                    moving[name]["vz_jump"] >= 4.0,
                    f"{name}: moving-car pop below 4 m/s",
                    moving[name],
                )
        r["moving"] = moving

        # A car entering through a spout during ON recovers to driving within 5 s.
        drv = Driver(s, PLAYER)
        drv.calibrate(_bearing_xy(90.0, 40.0), 0.0)
        entries: dict[str, Any] = {}
        for name, bearing in (("spout_e", 60.0), ("spout_w", 240.0)):
            idx = index_of[name]
            s.step_until(
                lambda: not bool(s.arena()["geysers"][idx]["on"]), calls=60, note="site never OFF"
            )
            s.teleport(PLAYER, _bearing_xy(bearing, 118.0), (bearing + 180.0) % 360.0)
            s.control(PLAYER, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=0.0)
            # Time the arrival: the ON window opens after `off` seconds of the cycle; wait for ON then go.
            s.step_until(
                lambda: bool(s.arena()["geysers"][idx]["on"]),
                calls=80,
                note="site never ON",
                steps=10,
            )
            s.vehicle(PLAYER).set_velocity(12.0, 0.6)
            popped_at = None
            recovered_at = None
            t0 = s.clock()
            last_vz = 0.0
            base_clear = None
            for _ in range(300):
                p = s.probe(PLAYER)
                t = s.clock() - t0
                if base_clear is None:
                    base_clear = p["clearance"]
                if popped_at is None and p["vz"] - last_vz > 3.0:
                    popped_at = t
                last_vz = p["vz"]
                if (
                    popped_at is not None
                    and recovered_at is None
                    and t > popped_at + 0.5
                    and p["clearance"] <= base_clear + 0.3
                    and abs(p["vz"]) < 0.8
                    and p["hspeed"] > 3.0
                    and p["uz"] > 0.9
                ):
                    recovered_at = t
                    break
                err = math.radians(_wrap_deg(((bearing + 180.0) % 360.0) - p["yaw"]))
                s.control(
                    PLAYER,
                    steering=max(-1, min(1, s.steer_sign * 1.5 * err)),
                    throttle=0.35,
                    brake=0.0,
                    parkingbrake=0.0,
                )
                s.step(3)
                if p["r"] < 60.0 and popped_at is None:
                    break
            entries[name] = {
                "popped_at": popped_at,
                "recovered_at": recovered_at,
                "recovery_s": (recovered_at - popped_at)
                if (popped_at is not None and recovered_at is not None)
                else None,
            }
            s.control(PLAYER, steering=0.0, throttle=0.0, brake=1.0, parkingbrake=1.0)
            if s.check(
                popped_at is not None,
                f"{name}: the spout entry never met an ON window",
                entries[name],
            ):
                s.check(
                    entries[name]["recovery_s"] is not None and entries[name]["recovery_s"] <= 5.0,
                    f"{name}: a car entering during ON did not recover to driving within 5 s",
                    entries[name],
                )
        r["spout_entries"] = entries
        s.shot(
            "spout_e_curtain",
            (*_bearing_xy(60.0, 125.0), C[2] + 3.0),
            (*_bearing_xy(60.0, 90.0), C[2] + 3.0),
            "the 60 spout throat looking in",
        )
        s.set_option("ai_enabled", True)
    assert not s.report.get("problems"), s.report["problems"]


# ====================================================================================
# G5 - the round on the arena
# ====================================================================================


@pytest.mark.beamng_live
def test_g5_round(tmp_path: Path) -> None:
    with _session("G5", tmp_path, plant_crash=True) as s:
        r = s.report
        boot = r["boot"]
        assert int(boot["recovered_calls"]) == 1, boot
        assert boot["snapshot"] == r["crash_player_values"], boot
        settings_file = s.user / "settings" / f"{smoke.HOT_POTATO_ID}.json"
        snapshot_file = s.user / "settings" / f"{MOD_ID}.snapshot.json"
        assert snapshot_file.is_file()
        s.set_option("ai_enabled", False)
        for n in AI:
            s.park(n)
        # A 200 s fuse: the stall valve steps at 120 s (75 m) and 180 s (60 m), the boom follows.
        s.set_options(
            {
                "fuse_base_seconds": 200,
                "fuse_sigma_seconds": 0,
                "fuse_min_seconds": 195,
                "fuse_max_seconds": 205,
                "cue_window_seconds": 20,
            }
        )
        stats = s.start_round(PLAYER)
        assert int(stats["field"]) == 6 and int(stats["props_excluded"]) == 16, stats
        r["round_start"] = {
            "field": stats["field"],
            "props_excluded": stats["props_excluded"],
            "carrier_is_player": True,
        }
        assert s.arena()["valve"]["in_round"] is True
        pad = s.pad
        s.shot(
            "pickup",
            (pad[0] + 16.0, pad[1] - 14.0, pad[2] + 6.0),
            (pad[0], pad[1], pad[2] + 2.0),
            "the player carrying the potato on the medallion",
        )

        # Ram transfer by ai_1 from 24 m north at 10 m/s.
        s.teleport(AI[0], (pad[0], pad[1] + 24.0), 180.0)
        s.control(AI[0], steering=0.0, throttle=1.0, brake=0.0, parkingbrake=0.0)
        s.vehicle(AI[0]).set_velocity(10.0, 1.0)
        rammer_id = int(s.probe(AI[0])["id"])
        s.step_until(
            lambda: int(s.stats().get("carrier") or -1) == rammer_id,
            calls=80,
            note="the ram never transferred the potato",
        )
        s.control(AI[0], steering=0.0, throttle=0.0, brake=1.0, parkingbrake=1.0)
        s.shot(
            "ram",
            (pad[0] + 15.0, pad[1] + 20.0, pad[2] + 6.0),
            (pad[0], pad[1] + 8.0, pad[2] + 1.5),
            "the ram transfer at the pad",
        )
        for _ in range(8):
            s.step(15)
            assert int(s.stats().get("carrier") or -1) == rammer_id, (
                "the potato bounced back through the tag-back rules"
            )
        r["transfer"] = {"reason_expected": "impact", "held_through_immunity": True}
        # Separate the pair so no pass can happen: the stall clock runs from the transfer.
        s.teleport(PLAYER, _bearing_xy(120.0, 40.0), 120.0)
        s.park(PLAYER)

        # The decay valve, for real: 120 s with no pass -> 75; 180 s -> 60.
        top = ((C[0], C[1] - 5.0, C[2] + 330.0), (C[0], C[1], C[2]))

        def _halo_extent(tag: str) -> dict[str, Any]:
            on = s.shot(f"halo_top_{tag}_on", *top, f"halo from 330 m above at radius {tag} (on)")
            s.set_option("arena_halo_enabled", False)
            s.step(10)
            off = s.shot(
                f"halo_top_{tag}_off", *top, f"halo from 330 m above at radius {tag} (off)"
            )
            s.set_option("arena_halo_enabled", True)
            s.step(10)
            return _tint_bbox(on, off)

        valve_trace = []
        halo = {"91.4": _halo_extent("91_4")}
        for stage, expected_r, deadline in ((1, 75.0, 150.0), (2, 60.0, 210.0)):
            while True:
                v = s.arena()["valve"]
                valve_trace.append(
                    {
                        "stall": round(float(v["stall"]), 1),
                        "stage": v["stage"],
                        "radius": v["radius"],
                    }
                )
                if int(v["stage"]) >= stage:
                    break
                assert float(v["stall"]) < deadline, {
                    "detail": f"stage {stage} never came",
                    "valve": v,
                }
                assert s.stats().get("phase") == "live", {
                    "detail": "round ended before the decay step",
                    "valve": v,
                }
                s.step(60)
            opts = s.options()
            assert float(opts["arena_radius_m"]) == pytest.approx(expected_r), opts
            halo[str(expected_r)] = _halo_extent(str(int(expected_r)))
            s.shot(
                f"halo_stage_{stage}",
                (*_bearing_xy(120.0, 40.0), C[2] + 1.6),
                (*_bearing_xy(60.0, expected_r), C[2] + 3.0),
                f"halo stepped in to {expected_r} m, from the player's spot",
            )
        r["valve"] = {"trace_tail": valve_trace[-6:], "halo_extent": halo}
        # The ring's screen width is the visual witness of the step. A frame whose
        # chroma mask reaches the frame edge caught something else amber (sun
        # glare on the rim caught one 60 m frame), so a polluted mask is RECORDED
        # and skipped rather than read as a halo that failed to move; the
        # authoritative decay evidence is the runtime's own radius read-back.
        for key, row in halo.items():
            row["mask_clean"] = (
                bool(row.get("tint_pixels"))
                and row.get("x_from", 0) > 100
                and row.get("x_to", 1280) < 1180
            )
        clean = [k for k in ("91.4", "75.0", "60.0") if halo[k]["mask_clean"]]
        r["halo_clean_frames"] = clean
        for a, b in zip(clean, clean[1:]):
            s.check(
                halo[b]["ring_width_px"] < halo[a]["ring_width_px"],
                f"the halo did not step inward from {a} to {b}",
                halo,
            )
        s.check(len(clean) >= 2, "fewer than two clean halo frames to compare", halo)

        # SCOPE (coordinator, this round): the boom -> return flight -> winner
        # fireworks chain is proven by G7.4 on this same pair; G5 adds only what
        # G7.4 does not cover - the forced decay step, the restore, the Exit
        # hand-back and the crash-recovery boot. The round is therefore ended
        # here by resetting the carrier (the runtime's carrier-lost path), not by
        # burning a 200 s fuse that outlasts the stall clock.
        s.drop_round()
        # Round end restores the radius (the valve's own restore path).
        s.step(30)
        opts = s.options()
        v = s.arena()["valve"]
        r["restore"] = {"radius_after_round": opts["arena_radius_m"], "valve": v}
        s.check(
            abs(float(opts["arena_radius_m"]) - 91.4) < 1e-6,
            "the radius was not restored at round end",
            r["restore"],
        )
        s.check(
            int(v["stage"]) == 0 and v["in_round"] is False,
            "the valve did not reset at round end",
            v,
        )
        s.shot(
            "idle_return",
            (pad[0] + 9.0, pad[1] - 9.0, pad[2] + 1.6),
            (pad[0], pad[1], pad[2] + 6.5),
            "the potato back on its perch after the round ended",
        )

        # Exit scenario hands the player's options back byte-equal; the snapshot file goes.
        # The shipped rule: a key is handed back only when current != snapshot AND
        # current == the arena's own value; the tuner's ai_enabled=false above is
        # the player's and must survive.
        snapshot = boot["snapshot"]
        arena_values = {
            "arena_radius_m": 91.4,
            "arena_enabled": True,
            "ai_enabled": True,
            "arena_magnet_enabled": True,
        }
        current = s.options()
        expected = {
            k: (
                snapshot[k]
                if (current.get(k) != snapshot[k] and current.get(k) == arena_values[k])
                else current.get(k)
            )
            for k in sync.BOOT_OPTION_KEYS
        }
        r["exit_expected"] = expected
        s.lua("scenario_scenarios.stop(); return jsonEncode({ok = true})")
        restored: dict[str, Any] = {}
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            time.sleep(1.0)
            if not settings_file.is_file():
                continue
            try:
                restored = json.loads(settings_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                restored
                and restored.get("arena_magnet_enabled") == expected["arena_magnet_enabled"]
            ):
                break
        r["exit_handback"] = {k: restored.get(k) for k in sync.BOOT_OPTION_KEYS}
        for key in sync.BOOT_OPTION_KEYS:
            assert restored.get(key) == expected[key], {
                "key": key,
                **r["exit_handback"],
                "expected": expected,
                "snapshot": snapshot,
            }
        assert not snapshot_file.is_file(), "the snapshot file must be deleted on hand-back"
    assert "snapshot_recovered" in s.report["log"]["arena_events"], s.report["log"]
    # G5's scope is the decay valve, the restore, the hand-back and crash
    # recovery; the detonation chain belongs to G7.4 (which proves it on this
    # same build pair), so this gate asserts only that a round really ran.
    assert "round_started" in s.report["log"]["runtime_events"], s.report["log"]
    assert not s.report.get("problems"), s.report["problems"]


# ====================================================================================
# G6 - perf / culling
# ====================================================================================


def _probe_zip_bytes() -> bytes:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr(f"lua/ge/extensions/{PROBE_ID}/perf.lua", PERF_LUA.replace("\r\n", "\n"))
    return buffer.getvalue()


@pytest.mark.beamng_live
def test_g6_perf_and_culling(tmp_path: Path) -> None:
    with _session("G6", tmp_path, probe_zip=_probe_zip_bytes()) as s:
        r = s.report
        loaded = s.lua(
            f"local ok, err = pcall(extensions.load, '{PROBE_ID}/perf'); return jsonEncode({{ok = ok == true, error = tostring(err)}})"
        )
        assert loaded.get("ok") is True, loaded
        snap = s.lua(
            f"local ext = extensions[{PROBE_EXTENSION!r}]; if not ext then return jsonEncode({{loaded = false}}) end; local x = ext.probeSnapshot(); x.loaded = true; return jsonEncode(x)"
        )
        assert snap.get("loaded") is True, snap
        roster = s.lua("local all = getAllVehicles(); return jsonEncode({count = #all})")
        assert int(roster["count"]) == 23, roster
        s.set_options(LONG_FUSE)
        s.set_option("ai_enabled", True)
        s.move_away([PLAYER])
        s.start_round(AI[0])
        # Real time for the frame log: resume, ramp 5 s, sample 60 s.
        s.bng.control.resume()
        time.sleep(5.0)
        s.lua(f"extensions[{PROBE_EXTENSION!r}].probeReset(); return jsonEncode({{ok = true}})")
        t_start = time.monotonic()
        time.sleep(60.0)
        snap = s.lua(
            f"local x = extensions[{PROBE_EXTENSION!r}].probeSnapshot(); return jsonEncode(x)"
        )
        wall = time.monotonic() - t_start
        s.bng.control.pause()
        s.bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
        s.bng.control.pause()
        frames = float(snap["frames"])
        perf = {
            "frames": frames,
            "probe_wall_s": snap["wall"],
            "python_wall_s": round(wall, 1),
            "avg_fps": round(frames / float(snap["wall"]), 1) if float(snap["wall"]) > 0 else None,
            "worst_frame_ms": round(float(snap["maxdt"]) * 1000.0, 1),
            "floor_fps": round(1.0 / float(snap["maxdt"]), 1) if float(snap["maxdt"]) > 0 else None,
            "frames_over_33ms": snap["over33"],
            "frames_over_67ms": snap["over66"],
            "physics_realtime_factor": round(float(snap["simsum"]) / float(snap["realsum"]), 3)
            if float(snap["realsum"]) > 0
            else None,
            "hist_5ms_buckets": snap.get("hist"),
            "geysers": [(g["name"], g["windows"], g["pops"]) for g in s.arena()["geysers"]],
            "stats": {
                k: s.stats().get(k) for k in ("phase", "transfers", "field", "props_excluded")
            },
        }
        r["perf"] = perf
        assert frames > 600, perf
        assert perf["avg_fps"] >= 20.0, perf
        s.shot(
            "perf_field",
            (C[0] + 70.0, C[1] + 80.0, C[2] + 45.0),
            (C[0], C[1], C[2] + 2.0),
            "23 vehicles, AI live, geysers cycling, during the perf window",
        )
        s.set_option("ai_enabled", False)
        for n in AI:
            s.park(n)

        # Collides: crest rays on every arc (jamb mid-faces for the spout arcs).
        crest_z = C[2] + float(HANDOFF["crest_z_m"])
        ray_points = {
            "wall_015": 15.0,
            "wall_105": 105.0,
            "wall_150": 150.0,
            "wall_195": 207.0,
            "wall_285": 285.0,
            "wall_330": 330.0,
        }
        collides = {name: s.surface_z(*_bearing_xy(b, CREST_R)) for name, b in ray_points.items()}
        collides["wall_spout_060_gate_jamb"] = s.surface_z(912.852, -216.303)
        collides["wall_spout_060_far_jamb"] = s.surface_z(936.589, -257.417)
        collides["wall_spout_240_gate_jamb"] = s.surface_z(787.148, -343.697)
        collides["wall_spout_240_far_jamb"] = s.surface_z(763.411, -302.583)
        collides["spout_060_throat"] = s.surface_z(*_bearing_xy(61.5, CREST_R))
        collides["spout_240_throat"] = s.surface_z(*_bearing_xy(241.5, CREST_R))
        r["collides"] = {"crest_z_expected": crest_z, "rays": collides}
        for name, b in ray_points.items():
            assert abs(collides[name] - crest_z) < 0.3, collides
        for k in (
            "wall_spout_060_gate_jamb",
            "wall_spout_060_far_jamb",
            "wall_spout_240_gate_jamb",
            "wall_spout_240_far_jamb",
        ):
            assert collides[k] > C[2] + 1.0, collides
        assert (
            collides["spout_060_throat"] < C[2] + 0.6 and collides["spout_240_throat"] < C[2] + 0.6
        ), collides

        # Renders: orbit at 150 / 250 / 400 m, per-arc hide diffs and same-camera frame diffs.
        orbit: dict[str, Any] = {}
        for distance in (150.0, 250.0, 400.0):
            height = {150.0: 60.0, 250.0: 90.0, 400.0: 140.0}[distance]
            for bearing in (45.0, 225.0) if distance != 250.0 else (0.0, 90.0, 180.0, 270.0):
                eye = (*_bearing_xy(bearing, distance), C[2] + height)
                aim = (C[0], C[1], C[2] + 3.0)
                key = f"d{int(distance)}_b{int(bearing)}"
                full_a = s.shot(
                    f"orbit_{key}_a",
                    eye,
                    aim,
                    f"orbit {int(distance)} m at bearing {int(bearing)} (frame A)",
                )
                full_b = s.shot(
                    f"orbit_{key}_b",
                    eye,
                    aim,
                    f"orbit {int(distance)} m at bearing {int(bearing)} (frame B, popping check)",
                )
                popping = _diff_pixels(full_a, full_b, threshold=24.0)
                s.set_hidden(WALL_STATICS, True)
                none = s.shot(
                    f"orbit_{key}_walls_hidden", eye, aim, f"orbit {key} with every wall arc hidden"
                )
                s.set_hidden(WALL_STATICS, False)
                walls_mask = _diff_pixels(full_a, none, threshold=10.0)
                per_arc: dict[str, Any] = {}
                if distance == 250.0 and bearing in (0.0, 180.0):
                    for arc in WALL_STATICS:
                        s.set_hidden([arc], True)
                        one = s.shot(
                            f"orbit_{key}_no_{arc.rsplit('_', 2)[-2]}_{arc.rsplit('_', 1)[-1]}",
                            eye,
                            aim,
                            f"orbit {key} with {arc} hidden",
                        )
                        s.set_hidden([arc], False)
                        per_arc[arc] = _diff_pixels(full_a, one, threshold=10.0)["count"]
                orbit[key] = {
                    "walls_pixels": walls_mask["count"],
                    "popping_pixels": popping["count"],
                    "per_arc_pixels": per_arc,
                }
                assert walls_mask["count"] > 3000, {"key": key, **orbit[key]}
                # Steam and the AI cars are parked, so a same-camera diff is the seam-popping witness.
                assert popping["count"] < 0.02 * 1280 * 720, {"key": key, **orbit[key]}
                for arc, count in per_arc.items():
                    assert count > 150, {"key": key, "arc": arc, **orbit[key]}
        r["orbit"] = orbit
        s.set_option("ai_enabled", True)


# ====================================================================================
# G7 - the lifted floor skin (dist c37754b6, hashes round v3.2)
#
# The design owner's answer to G1's per-boot far-field banding: the floor skin is
# now a COLLIDING +50 mm surface feathered to the 12 mm datum (skirt r 6-9 at
# 2.0 %, feather r 73.5-76 at 1.9 %), the plates ride +50 mm by instance z, and
# the DAE carries ONE mesh detail. Everything a driver touches therefore changed,
# so the ladder is re-walked on the new dist.
# ====================================================================================

FLOOR = HANDOFF["floor_skin"]
SKIN_TOP_Z = C[2] + float(FLOOR["profile"]["top_z_m"])  # 100.050
SKIN_DATUM_Z = C[2] + float(FLOOR["profile"]["datum_z_m"])  # 100.012
PLATE_TOP_Z = SKIN_TOP_Z + 0.020  # 100.070


def _settle_and_rest(
    s: Session, name: str, xy: tuple[float, float], drop: float = 1.2
) -> dict[str, Any]:
    """Drop a car from `drop` metres and return its resting pose - a real collision test."""

    ray = s.surface_z(*xy)
    assert (
        s.bng.vehicles.teleport(name, (xy[0], xy[1], ray + drop), _heading_quat(0.0), reset=True)
        is True
    )
    s.control(name, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=1.0)
    rest = None
    for _ in range(120):
        s.step(4)
        p = s.probe(name)
        if abs(p["vz"]) < 0.02 and p["hspeed"] < 0.05:
            if rest is not None and abs(p["z"] - rest) < 0.002:
                break
            rest = p["z"]
    p = s.probe(name)
    # The car is ~4.4 m long and ~1.8 m wide, so on a graded surface its wheels
    # do NOT all stand on the point the centre ray hit. Ride height is therefore
    # measured against the mean of four rays under the car's own footprint - the
    # invariant that must hold on any surface that really carries the car.
    hx, hy = math.sin(math.radians(p["yaw"])), math.cos(math.radians(p["yaw"]))
    corners = [
        (p["x"] + 2.2 * hx * sl + 0.8 * hy * sw, p["y"] + 2.2 * hy * sl - 0.8 * hx * sw)
        for sl in (1.0, -1.0)
        for sw in (1.0, -1.0)
    ]
    footprint = [row["z"] for row in s.surface_profile(corners)]
    mean_ray = sum(footprint) / len(footprint)
    return {
        "xy": [round(xy[0], 3), round(xy[1], 3)],
        "r": round(p["r"], 2),
        "ray_z": round(ray, 4),
        "rest_body_z": round(p["z"], 4),
        "footprint_rays": [round(z, 4) for z in footprint],
        "footprint_mean_ray_z": round(mean_ray, 4),
        "ride_height_over_footprint": round(p["z"] - mean_ray, 4),
        "clearance": round(p["clearance"], 4),
        "uz": round(p["uz"], 4),
        "contacts": s.wheel_contacts(name),
    }


@pytest.mark.beamng_live
def test_g7_0_floor_skin_drop_test(tmp_path: Path) -> None:
    """G7.0 - does the lifted skin COLLIDE? Drop-tests, not rays alone."""

    with _session("G7_0", tmp_path) as s:
        r = s.report
        s.set_option("ai_enabled", False)
        for n in AI:
            s.park(n)
        rays = {
            "medallion_r3": s.surface_z(*_bearing_xy(0.0, 3.0)),
            "skirt_r7": s.surface_z(*_bearing_xy(0.0, 7.0)),
            "plaza_r40": s.surface_z(*_bearing_xy(90.0, 40.0)),
            "plaza_r60": s.surface_z(*_bearing_xy(20.0, 60.0)),
            "feather_r74_75": s.surface_z(*_bearing_xy(20.0, 74.75)),
            "toe_r76": s.surface_z(*_bearing_xy(20.0, 76.0)),
            "pool_1_top": s.surface_z(883.0, -222.842),
            "salt_e_top": s.surface_z(*_bearing_xy(90.0, 16.0)),
            "far_lot": s.surface_z(*s.far_lot()),
        }
        r["rays"] = {k: round(v, 4) for k, v in rays.items()}
        drops = {
            "far_lot_reference": _settle_and_rest(s, PLAYER, s.far_lot()),
            "plaza_r40": _settle_and_rest(s, PLAYER, _bearing_xy(90.0, 40.0)),
            "plaza_r60": _settle_and_rest(s, PLAYER, _bearing_xy(20.0, 60.0)),
            "feather_r74_75": _settle_and_rest(s, PLAYER, _bearing_xy(20.0, 74.75)),
            "toe_r75_9": _settle_and_rest(s, PLAYER, _bearing_xy(20.0, 75.9)),
            "pool_1": _settle_and_rest(s, PLAYER, (883.0, -222.842)),
        }
        base = drops["far_lot_reference"]["rest_body_z"]
        for row in drops.values():
            row["lift_vs_groundplane_m"] = round(row["rest_body_z"] - base, 4)
        r["drops"] = drops
        r["expected"] = {
            "skin_top_z": SKIN_TOP_Z,
            "skin_datum_z": SKIN_DATUM_Z,
            "plate_top_z": PLATE_TOP_Z,
        }
        s.shot(
            "plaza_rest",
            (*_bearing_xy(90.0, 52.0), C[2] + 2.2),
            (*_bearing_xy(90.0, 40.0), C[2] + 0.6),
            "the car at rest on the lifted plaza skin",
        )
        s.shot(
            "toe_rest",
            (*_bearing_xy(20.0, 84.0), C[2] + 3.0),
            (*_bearing_xy(20.0, 75.9), C[2] + 0.6),
            "the car at rest at the r 76 toe (12 mm datum)",
        )
        plaza_lift = drops["plaza_r40"]["lift_vs_groundplane_m"]
        toe_lift = drops["toe_r75_9"]["lift_vs_groundplane_m"]
        s.check(
            abs(rays["plaza_r40"] - SKIN_TOP_Z) < 0.005,
            "the plaza ray does not read the +50 mm skin",
            r["rays"],
        )
        s.check(
            abs(rays["toe_r76"] - SKIN_DATUM_Z) < 0.005,
            "the r 76 toe ray does not read the 12 mm datum",
            r["rays"],
        )
        s.check(
            0.040 <= plaza_lift <= 0.060,
            "DROP TEST: the plaza skin does not carry the car at +50 mm",
            drops["plaza_r40"],
        )
        # At the toe the car's own footprint straddles the feather and the first
        # metres of bank, so the point lift is not the datum; what must hold is
        # that the car stands ON the surface its wheels are over.
        ride = {k: row["ride_height_over_footprint"] for k, row in drops.items()}
        r["ride_heights"] = ride
        base_ride = ride["far_lot_reference"]
        # On FLAT stations the ride height must equal the groundplane's exactly:
        # that is the proof the car stands on the skin, not through it.
        for key in ("plaza_r40", "plaza_r60"):
            s.check(
                abs(ride[key] - base_ride) < 0.005,
                f"DROP TEST: the car does not stand on the skin at {key}",
                {"ride": ride[key], "groundplane_ride": base_ride, **drops[key]},
            )
        # On the feather and at the toe the four footprint rays disagree (the
        # surface curves up outboard onto the bank), so the mean over-reads.
        # MEASURED, recorded: body z must sit inside the footprint's own band.
        for key in ("feather_r74_75", "toe_r75_9"):
            row = drops[key]
            lo, hi = min(row["footprint_rays"]), max(row["footprint_rays"])
            s.check(
                lo + 0.15 <= row["rest_body_z"] <= hi + 0.30,
                f"DROP TEST: the car is not resting on the graded skin at {key}",
                {"footprint_span": [lo, hi], **row},
            )
        s.check(
            0.060 <= drops["pool_1"]["lift_vs_groundplane_m"] <= 0.085,
            "the butter pool does not sit 20 mm proud of the skin",
            drops["pool_1"],
        )
        s.check(
            all(c == "ICE" for c in drops["pool_1"]["contacts"]),
            "the lifted pool no longer binds ICE",
            drops["pool_1"],
        )
    assert not s.report.get("problems"), s.report["problems"]


@pytest.mark.beamng_live
def test_g7_1_farfield(tmp_path: Path) -> None:
    """G7.1 - the far-field floor on the lifted skin: >= 6 frames at 300 m per boot."""

    with _session("G7_1", tmp_path) as s:
        r = s.report
        cams = {
            "far": ((C[0], C[1] - 60.0, C[2] + 300.0), (C[0], C[1], C[2])),
            "h150": ((C[0], C[1] - 30.0, C[2] + 150.0), (C[0], C[1], C[2])),
            "overview": ((C[0] + 150.0, C[1] - 170.0, C[2] + 95.0), (C[0], C[1], C[2] + 8.0)),
        }
        s.step(120)
        far = [
            s.shot(f"farfield_{i}", *cams["far"], f"far-field floor frame {i} (300 m, lifted skin)")
            for i in range(1, 10)
        ]
        others = {
            k: s.shot(f"floor_{k}", *cams[k], f"{k} camera on the lifted skin")
            for k in ("h150", "overview")
        }
        s.set_hidden(FLOOR_STATICS, True)
        hidden = {
            k: s.shot(f"floor_{k}_skins_hidden", *cams[k], f"{k} camera, floor skins hidden")
            for k in cams
        }
        s.set_hidden(FLOOR_STATICS, False)
        ratios = [smoke._band_ratio(f, 640, 372, 140) for f in far]
        r["farfield"] = {
            "band_ratios": ratios,
            "min": min(ratios),
            "max": max(ratios),
            "banded_frames_over_2_2": sum(1 for x in ratios if x > 2.2),
            "medians": {
                "far_shipped": [_disc_median(f, 640, 372, 140) for f in far],
                "far_hidden": _disc_median(hidden["far"], 640, 372, 140),
                "h150_shipped": _disc_median(others["h150"], 640, 360, 250),
                "h150_hidden": _disc_median(hidden["h150"], 640, 360, 250),
            },
        }
        s.check(len(ratios) >= 6, "fewer than six far-field frames", r["farfield"])
        s.check(
            r["farfield"]["banded_frames_over_2_2"] == 0,
            "far-field banding on the lifted skin",
            r["farfield"],
        )
    assert not s.report.get("problems"), s.report["problems"]


@pytest.mark.beamng_live
def test_g7_2_surface(tmp_path: Path) -> None:
    """G7.2 - drive the new surface: bank lines, the feather in and out, pools, seams."""

    with _session("G7_2", tmp_path) as s:
        r = s.report
        s.set_option("ai_enabled", False)
        s.set_option("arena_magnet_enabled", False)
        for n in AI:
            s.park(n)
        drv = Driver(s, PLAYER)
        drv.calibrate(_bearing_xy(90.0, 40.0), 0.0)

        bank: dict[str, Any] = {}
        for speed, tag in ((1.1, "crawl"), (2.0, "2mps")):
            s.teleport(PLAYER, _bearing_xy(20.0, 66.0), 20.0)
            line = drv.line(
                f"bank_radial_{tag}",
                [_bearing_xy(20.0, 76.0), _bearing_xy(20.0, 84.0), _bearing_xy(20.0, 90.0)],
                speed,
                max_sim=90.0,
            )
            bank[tag] = {
                k: line[k] for k in ("outcome", "max_r", "max_z", "min_uz", "airborne_s", "events")
            }
            s.check(line["max_r"] >= 84.0, f"the {tag} bank line did not reach r 84", bank[tag])
            for e in line["events"]:
                s.check(
                    e.get("verdict") != "did_not_move_hard_geometry",
                    f"the {tag} bank line hit hard geometry",
                    e,
                )
        r["bank"] = bank

        feather: dict[str, Any] = {}
        for bearing in (20.0, 140.0, 300.0):
            for speed, tag in ((2.0, "2mps"), (16.7, "60kmh")):
                for direction in ("out", "in"):
                    r_from, r_to = (68.0, 79.0) if direction == "out" else (79.0, 68.0)
                    heading = bearing if direction == "out" else (bearing + 180.0) % 360.0
                    s.teleport(PLAYER, _bearing_xy(bearing, r_from), heading)
                    if speed > 5.0:
                        s.control(PLAYER, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=0.0)
                        s.step(STEP_TICK)
                        s.vehicle(PLAYER).set_velocity(speed, 0.8)
                    label = f"feather_{int(bearing)}_{tag}_{direction}"
                    line = drv.line(
                        label,
                        [
                            _bearing_xy(bearing, r_from + (r_to - r_from) * f)
                            for f in (0.4, 0.75, 1.0)
                        ],
                        speed,
                        max_sim=45.0,
                        reach=3.0,
                    )
                    trace = s.report["traces"][label]
                    band = [x for x in trace if 72.0 <= x["r"] <= 77.5]
                    feather[label] = {
                        "outcome": line["outcome"],
                        "airborne_s": line["airborne_s"],
                        "min_uz": line["min_uz"],
                        "max_abs_vz_in_band": round(
                            max((abs(x["vz"]) for x in band), default=0.0), 3
                        ),
                        "z_span_in_band": round(
                            max((x["z"] for x in band), default=0.0)
                            - min((x["z"] for x in band), default=0.0),
                            4,
                        ),
                        "samples_in_band": len(band),
                        "events": line["events"],
                    }
                    s.check(
                        line["airborne_s"] < 0.25,
                        f"{label}: the car left the ground crossing the feather",
                        feather[label],
                    )
                    s.check(
                        feather[label]["max_abs_vz_in_band"] < 1.2,
                        f"{label}: a vertical kick crossing the feather",
                        feather[label],
                    )
                    for e in line["events"]:
                        s.check(
                            e.get("verdict") != "did_not_move_hard_geometry",
                            f"{label}: hard geometry on the feather",
                            e,
                        )
        r["feather"] = feather
        s.shot(
            "feather_line",
            (*_bearing_xy(35.0, 66.0), C[2] + 5.0),
            (*_bearing_xy(20.0, 78.0), C[2] + 1.0),
            "the r 73.5-76 feather after the crossings",
        )

        seams: dict[str, Any] = {}
        s.teleport(PLAYER, _bearing_xy(20.0, 40.0), 110.0)
        s.control(PLAYER, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=0.0)
        s.step(STEP_TICK)
        s.vehicle(PLAYER).set_velocity(16.7, 0.8)
        line = drv.line(
            "seam_tangential_60kmh",
            _arc_line(40.0, 25.0, 160.0, 5.0),
            16.7,
            max_sim=45.0,
            reach=6.0,
            heading_fn=lambda p: (p["bearing"] + 90.0) % 360.0,
            stop_fn=lambda p: p["bearing"] > 155.0,
        )
        trace = s.report["traces"]["seam_tangential_60kmh"]
        seams["tangential"] = {
            "outcome": line["outcome"],
            "airborne_s": line["airborne_s"],
            "min_uz": line["min_uz"],
            "max_abs_vz": round(max(abs(x["vz"]) for x in trace), 3),
            "z_span": round(max(x["z"] for x in trace) - min(x["z"] for x in trace), 4),
            "bearings_crossed": [round(trace[0]["bearing"], 1), round(trace[-1]["bearing"], 1)],
        }
        s.check(
            seams["tangential"]["max_abs_vz"] < 1.2,
            "a quadrant seam kicked the car at 60 km/h",
            seams["tangential"],
        )
        s.check(
            line["airborne_s"] < 0.25,
            "the car left the ground crossing a quadrant seam",
            seams["tangential"],
        )
        r["seams"] = seams

        surfaces: dict[str, Any] = {}
        surfaces["asphalt"] = _brake_decel(
            s, PLAYER, _bearing_xy(100.0, 30.0), 100.0, 10.0, (42.0, 60.0), "asphalt_plaza"
        )
        ax, ay = math.cos(math.radians(-30.0)), math.sin(math.radians(-30.0))
        pool_c = (883.0, -222.842)
        start = (pool_c[0] - 22.0 * ax, pool_c[1] - 22.0 * ay)
        heading = math.degrees(math.atan2(ax, ay)) % 360.0

        def _on_pool(p: dict[str, Any]) -> bool:
            dx, dy = p["x"] - pool_c[0], p["y"] - pool_c[1]
            return abs(dx * ax + dy * ay) <= 8.0 and abs(-dx * ay + dy * ax) <= 4.0

        s.teleport(PLAYER, start, heading)
        s.control(PLAYER, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=0.0)
        s.step(STEP_TICK)
        s.vehicle(PLAYER).set_velocity(10.0, 0.6)
        s.step(45)
        samples: list[dict[str, Any]] = []
        armed = False
        contacts: list[str] = []
        t0 = s.clock()
        rim_vz = 0.0
        for _ in range(400):
            p = s.probe(PLAYER)
            if not armed and _on_pool(p):
                s.control(PLAYER, steering=0.0, throttle=0.0, brake=1.0, parkingbrake=0.0)
                armed = True
                contacts = s.wheel_contacts(PLAYER)
            if not armed:
                rim_vz = max(rim_vz, abs(p["vz"]))
            samples.append(
                {
                    "t": round(s.clock() - t0, 3),
                    "speed": round(p["hspeed"], 3),
                    "armed": armed,
                    "on_pool": _on_pool(p),
                    "vz": round(p["vz"], 3),
                }
            )
            if armed and (p["hspeed"] < 0.3 or not _on_pool(p)):
                break
            s.step(3)
        braking = [x for x in samples if x["armed"] and x["on_pool"]]
        decel = (
            ((braking[0]["speed"] - braking[-1]["speed"]) / (braking[-1]["t"] - braking[0]["t"]))
            if len(braking) >= 3
            else None
        )
        surfaces["butter_pool_1"] = {
            "decel_mps2": decel,
            "mu_equiv": decel / 9.81 if decel else None,
            "contacts_at_arm": contacts,
            "v_at_arm": braking[0]["speed"] if braking else None,
            "max_abs_vz_mounting_rim": round(rim_vz, 3),
        }
        s.control(PLAYER, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=1.0)
        parked: dict[str, Any] = {}
        for label, xy, hdg in (
            ("salt_arc_e", _bearing_xy(90.0, 16.0), 0.0),
            ("butter_pool_3", (792.842, -247.0), 60.0),
        ):
            s.teleport(PLAYER, xy, hdg)
            s.park(PLAYER)
            s.step(30)
            parked[label] = {
                "contacts": s.wheel_contacts(PLAYER),
                "surface_z": round(s.surface_z(*xy), 4),
            }
        surfaces["parked_contacts"] = parked
        r["surfaces"] = surfaces
        s.check(
            bool(contacts) and all(c == "ICE" for c in contacts),
            "the lifted butter pool no longer binds ICE",
            surfaces["butter_pool_1"],
        )
        s.check(
            any(c == "SAND" for c in parked["salt_arc_e"]["contacts"]),
            "the lifted salt arc no longer binds SAND",
            parked,
        )
        if surfaces["asphalt"]["mu_equiv"] and surfaces["butter_pool_1"]["mu_equiv"]:
            s.check(
                surfaces["butter_pool_1"]["mu_equiv"] < 0.5 * surfaces["asphalt"]["mu_equiv"],
                "the pool no longer skates vs asphalt",
                surfaces,
            )
        s.check(
            rim_vz < 1.2, "mounting the lifted pool rim kicked the car", surfaces["butter_pool_1"]
        )
        s.shot(
            "pool_after_slide",
            (pool_c[0] + 12.0, pool_c[1] - 10.0, C[2] + 4.0),
            (pool_c[0], pool_c[1], C[2] + 0.5),
            "butter pool 1 on the lifted skin after the slide",
        )
        s.set_option("arena_magnet_enabled", True)
        s.set_option("ai_enabled", True)
    assert not s.report.get("problems"), s.report["problems"]


@pytest.mark.beamng_live
def test_g7_3_ai_and_perf(tmp_path: Path) -> None:
    """G7.3 - obstacle-collision census with the AI live, plus a 60 s frame-time window."""

    with _session("G7_3", tmp_path, probe_zip=_probe_zip_bytes()) as s:
        r = s.report
        loaded = s.lua(
            f"local ok, err = pcall(extensions.load, '{PROBE_ID}/perf'); return jsonEncode({{ok = ok == true, error = tostring(err)}})"
        )
        s.check(loaded.get("ok") is True, "the perf probe extension did not load", loaded)
        roster = s.lua("local all = getAllVehicles(); return jsonEncode({count = #all})")
        s.check(int(roster["count"]) == 23, "the vehicle census is not 23", roster)
        props = [
            n
            for n in [e["name"] for e in sync.vehicle_layout(HANDOFF)]
            if n not in (PLAYER, DISPENSER) and n not in AI
        ]
        s.set_options(LONG_FUSE)
        s.set_option("ai_enabled", True)
        s.move_away([PLAYER])
        s.start_round(AI[0])
        hits: list[dict[str, Any]] = []
        last_damage: dict[str, float] = {}
        min_clear: dict[str, float] = {}
        t0 = s.clock()
        samples = 0
        while s.clock() - t0 < 180.0:
            rows = _census_tick(s, AI + props, last_damage, hits, s.clock() - t0)
            for n in AI:
                row = rows[n]
                if row.get("ok"):
                    solid, clearance = _nearest_solid(row["x"], row["y"], row["z"])
                    min_clear[solid] = min(min_clear.get(solid, 1e9), clearance)
            samples += 1
            if samples % 100 == 0 and s.stats().get("phase") != "live":
                s.start_round(AI[0])
            s.step(STEP_TICK)
        chase = s.stats()
        solid_hits = [h for h in hits if h["kind"] == "solid" and h["car"] in AI]
        r["chase"] = {
            "sim_seconds": round(s.clock() - t0, 1),
            "samples": samples,
            "transfers": chase.get("transfers"),
            "field": chase.get("field"),
            "props_excluded": chase.get("props_excluded"),
            "hits_by_kind": {
                k: sum(1 for h in hits if h["kind"] == k) for k in ("solid", "car", "other")
            },
            "solid_hits": solid_hits,
            "min_clearance_by_solid": {k: round(v, 2) for k, v in sorted(min_clear.items())},
        }
        s.check(
            len(solid_hits) == 0,
            "AI collided with registered obstacles on the lifted skin",
            solid_hits,
        )
        s.shot(
            "chase_field",
            (C[0] + 70.0, C[1] + 80.0, C[2] + 45.0),
            (C[0], C[1], C[2] + 2.0),
            "23 vehicles, AI live, on the lifted skin",
        )
        s.bng.control.resume()
        time.sleep(5.0)
        s.lua(f"extensions[{PROBE_EXTENSION!r}].probeReset(); return jsonEncode({{ok = true}})")
        time.sleep(60.0)
        snap = s.lua(f"return jsonEncode(extensions[{PROBE_EXTENSION!r}].probeSnapshot())")
        s.bng.control.pause()
        s.bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
        s.bng.control.pause()
        frames = float(snap["frames"])
        r["perf"] = {
            "frames": frames,
            "probe_wall_s": snap["wall"],
            "avg_fps": round(frames / float(snap["wall"]), 1) if float(snap["wall"]) > 0 else None,
            "worst_frame_ms": round(float(snap["maxdt"]) * 1000.0, 1),
            "floor_fps": round(1.0 / float(snap["maxdt"]), 1) if float(snap["maxdt"]) > 0 else None,
            "frames_over_33ms": snap["over33"],
            "frames_over_67ms": snap["over66"],
            "physics_realtime_factor": round(float(snap["simsum"]) / float(snap["realsum"]), 3)
            if float(snap["realsum"]) > 0
            else None,
            "hist_5ms_buckets": snap.get("hist"),
            "geysers": [(g["name"], g["windows"], g["pops"]) for g in s.arena()["geysers"]],
        }
        s.check(frames > 600, "the perf window collected too few frames", r["perf"])
        s.check(
            bool(r["perf"]["avg_fps"]) and r["perf"]["avg_fps"] >= 20.0,
            "average frame rate below 20 fps with the full census",
            r["perf"],
        )
        s.set_option("ai_enabled", False)
    assert not s.report.get("problems"), s.report["problems"]


@pytest.mark.beamng_live
def test_g7_4_round(tmp_path: Path) -> None:
    """G7.4 - one full round on the lifted skin: field == 6, props_excluded == 16, boom, return."""

    with _session("G7_4", tmp_path) as s:
        r = s.report
        s.set_option("ai_enabled", False)
        for n in AI:
            s.park(n)
        s.set_options(
            {
                "fuse_base_seconds": 30,
                "fuse_sigma_seconds": 0,
                "fuse_min_seconds": 25,
                "fuse_max_seconds": 35,
                "cue_window_seconds": 15,
            }
        )
        stats = s.start_round(PLAYER)
        r["round_start"] = {
            "field": stats.get("field"),
            "props_excluded": stats.get("props_excluded"),
            "phase": stats.get("phase"),
        }
        s.check(int(stats.get("field", -1)) == 6, "field != 6 on the lifted skin", r["round_start"])
        s.check(
            int(stats.get("props_excluded", -1)) == 16,
            "props_excluded != 16 on the lifted skin",
            r["round_start"],
        )
        pad = s.pad
        s.shot(
            "pickup",
            (pad[0] + 16.0, pad[1] - 14.0, pad[2] + 6.0),
            (pad[0], pad[1], pad[2] + 2.0),
            "the round live on the lifted skin",
        )
        s.teleport(AI[0], (pad[0], pad[1] + 24.0), 180.0)
        s.control(AI[0], steering=0.0, throttle=1.0, brake=0.0, parkingbrake=0.0)
        s.vehicle(AI[0]).set_velocity(10.0, 1.0)
        rammer_id = int(s.probe(AI[0])["id"])
        transferred = True
        try:
            s.step_until(
                lambda: int(s.stats().get("carrier") or -1) == rammer_id,
                calls=90,
                note="ram transfer",
            )
        except AssertionError:
            transferred = False
        s.control(AI[0], steering=0.0, throttle=0.0, brake=1.0, parkingbrake=1.0)
        s.check(
            transferred,
            "the ram never transferred the potato on the lifted skin",
            {"rammer": rammer_id},
        )
        s.shot(
            "ram",
            (pad[0] + 15.0, pad[1] + 20.0, pad[2] + 6.0),
            (pad[0], pad[1] + 8.0, pad[2] + 1.5),
            "the ram transfer",
        )
        boomed = True
        try:
            s.step_until(lambda: s.stats().get("phase") == "boom", calls=300, note="fuse to boom")
        except AssertionError:
            boomed = False
        s.check(boomed, "the fuse never detonated", s.stats())
        if boomed:
            peak = 0.0
            anchor = None
            for _ in range(10):
                s.step(6)
                p = s.probe(AI[0])
                peak = max(peak, p["speed"])
                anchor = anchor or (p["x"], p["y"], p["z"])
            r["boom"] = {"peak_speed": peak}
            s.check(peak > 6.0, "the detonation never moved the wreck", r["boom"])
            s.shot(
                "boom",
                (anchor[0] + 11.0, anchor[1] - 11.0, anchor[2] + 5.0),
                (anchor[0], anchor[1], anchor[2] + 2.0),
                "the detonation on the lifted skin",
            )
            returned = True
            try:
                s.step_until(
                    lambda: s.stats().get("phase") in ("return", "idle"),
                    calls=200,
                    note="return flight",
                )
            except AssertionError:
                returned = False
            s.check(returned, "the boom never handed over to the return flight", s.stats())
            after = s.stats()
            r["dodge_win"] = {"fw_stage": after.get("fw_stage")}
            s.check(after.get("fw_stage", "") != "", "no winner fireworks after the boom", after)
            try:
                s.step_until(
                    lambda: s.stats().get("fw_stage") in ("burst", "finale"), calls=60, note="burst"
                )
                s.shot(
                    "fireworks",
                    (pad[0], pad[1] + 72.0, pad[2] + 44.0),
                    (pad[0], pad[1], pad[2] + 56.0),
                    "winner fireworks over the arch",
                )
            except AssertionError:
                s.problem("the fireworks never reached a burst stage", s.stats())
            try:
                s.step_until(lambda: s.stats().get("phase") == "idle", calls=300, note="idle")
                s.shot(
                    "idle",
                    (pad[0] + 9.0, pad[1] - 9.0, pad[2] + 1.6),
                    (pad[0], pad[1], pad[2] + 6.5),
                    "the potato home on its perch",
                )
            except AssertionError:
                s.problem("the return flight never settled to idle", s.stats())
        v = s.arena()["valve"]
        opts = s.options()
        r["after_round"] = {
            "radius": opts["arena_radius_m"],
            "valve_stage": v["stage"],
            "in_round": v["in_round"],
        }
        s.check(
            abs(float(opts["arena_radius_m"]) - 91.4) < 1e-6,
            "the radius was not restored at round end",
            r["after_round"],
        )
    assert not s.report.get("problems"), s.report["problems"]


# ====================================================================================
# G8 - the re-gate pass: Hot Potato serial 48 (ask #4) + arena v3.3 (shadow fix)
#
# Three lines, named before the fixes were built:
#   G8.1  test_g8_crest_rams          - G2's crest_rams block at 60/85/110 km/h
#   G8.2  test_g7_1_farfield x3 boots - the far-field triple on the re-cut dist
#   G8.3  test_g7_0_floor_skin_drop_test - the collision regression
#
# G8.1 also carries the runtime worker's OWN falsifier, which it could not settle
# from the shipped Lua: does a hauled car's ALTITUDE RISE while the tether is
# drawn? (obj:setPlanets ADDS to world gravity, or REPLACES it?) Every haul
# sample logs body z, the ground z directly beneath, and the height between them;
# a tether frame is captured mid-haul so "a well was demonstrably placed" is a
# measurement, not an assumption.
# ====================================================================================


def _run_crest_ram(s: Session, kmh: float, bearing: float = 285.0) -> dict[str, Any]:
    """One crest ram: accelerate outward, leave the crest, land, be hauled home."""

    v = kmh / 3.6
    s.teleport(PLAYER, _bearing_xy(bearing, 30.0), bearing)
    s.step(45)  # the membership sweep must see the car INSIDE the ring
    s.control(PLAYER, steering=0.0, throttle=1.0, brake=0.0, parkingbrake=0.0)
    s.vehicle(PLAYER).set_velocity(v, 1.2)
    trace: list[dict[str, Any]] = []
    crest_speed = None
    over = False
    landed = None
    apex = C[2]
    apex_t = None
    airborne_s = 0.0
    haul_start = None
    haul_done = None
    base_clear = None
    tether_shot: Path | None = None
    t0 = s.clock()
    for _ in range(1600):
        p = s.probe(PLAYER)
        t = s.clock() - t0
        if base_clear is None:
            base_clear = p["clearance"]
        # ground_z is derivable from the clearance ray: clearance = 2.0 - d, and
        # the ray starts 2 m above the body, so ground_z = z + clearance.
        ground_z = p["z"] + p["clearance"]
        height = p["z"] - ground_z
        if not over:
            err = math.radians(_wrap_deg(bearing - p["yaw"]))
            s.control(
                PLAYER,
                steering=max(-1, min(1, s.steer_sign * 1.5 * err)),
                throttle=1.0,
                brake=0.0,
                parkingbrake=0.0,
            )
            if p["r"] >= CREST_R:
                crest_speed = p["hspeed"]
                over = True
                s.control(PLAYER, steering=0.0, throttle=0.0, brake=0.0, parkingbrake=0.0)
        else:
            if p["z"] > apex:
                apex, apex_t = p["z"], t
            if p["clearance"] > base_clear + 0.45:
                airborne_s += 0.05
            if (
                landed is None
                and apex_t is not None
                and t > apex_t + 0.1
                and p["clearance"] <= base_clear + 0.35
            ):
                landed = {
                    "t": round(t, 2),
                    "r": round(p["r"], 2),
                    "z": round(p["z"], 3),
                    "speed": round(p["hspeed"], 2),
                    "uz": round(p["uz"], 3),
                }
            if haul_start is None and p["r"] > R_ARENA:
                haul_start = t
            if haul_start is not None and p["r"] < R_RELEASE:
                haul_done = t
        trace.append(
            {
                "t": round(t, 2),
                "r": round(p["r"], 2),
                "z": round(p["z"], 3),
                "ground_z": round(ground_z, 3),
                "height": round(height, 3),
                "speed": round(p["hspeed"], 2),
                "vz": round(p["vz"], 2),
                "uz": round(p["uz"], 3),
                "hauling": haul_start is not None and haul_done is None,
            }
        )
        # One tether frame per run, taken 1.5 s into the haul with the car settled
        # enough to photograph: the bead line proves a well is actually placed.
        if (
            tether_shot is not None
            or haul_start is None
            or t < haul_start + 1.5
            or haul_done is not None
        ):
            pass
        else:
            tether_shot = s.shot(
                f"ram_{int(kmh)}_tether",
                (*_bearing_xy(bearing, p["r"] + 16.0), p["z"] + 6.0),
                (*_bearing_xy(bearing, p["r"] - 8.0), p["z"] + 1.0),
                f"{int(kmh)} km/h haul: magnet tether beads while the well is placed",
            )
        if haul_done is not None or (over and t > 60.0) or p["uz"] < 0.15:
            break
        s.step(3)
    haul = [x for x in trace if x["hauling"]]
    heights = [x["height"] for x in haul]
    summary = {
        "kmh": kmh,
        "crest_speed_mps": crest_speed,
        "exited_over_crest": over,
        "apex_z": round(apex, 3),
        "apex_rise_over_crest_m": round(apex - (C[2] + float(HANDOFF["crest_z_m"])), 2),
        "airborne_s": round(airborne_s, 2),
        "landing": landed,
        "max_r": round(max(x["r"] for x in trace), 2),
        "haul_start_t": haul_start,
        "haul_done_t": haul_done,
        "haul_seconds": round(haul_done - haul_start, 2)
        if (haul_start is not None and haul_done is not None)
        else None,
        "min_uz": round(min(x["uz"] for x in trace), 3),
        "min_uz_during_haul": round(min((x["uz"] for x in haul), default=1.0), 3),
        "haul_samples": len(haul),
        "altitude": {
            "height_first": heights[0] if heights else None,
            "height_last": heights[-1] if heights else None,
            "height_min": round(min(heights), 3) if heights else None,
            "height_max": round(max(heights), 3) if heights else None,
            "height_mean": round(sum(heights) / len(heights), 3) if heights else None,
            "rose_while_tethered": bool(heights) and max(heights) > heights[0] + 0.5,
            "ground_z_first": haul[0]["ground_z"] if haul else None,
            "ground_z_last": haul[-1]["ground_z"] if haul else None,
        },
        "tether_frame": tether_shot.name if tether_shot else None,
        "tether_amber_pixels": _amber_pixels(tether_shot) if tether_shot else None,
        "final": trace[-1],
    }
    summary["clauses"] = {
        "exited_over_crest": over,
        "landed_outside_crest": bool(landed and landed["r"] > CREST_R),
        "landed_inside_runoff": summary["max_r"] < 160.0,
        "stayed_upright": summary["min_uz"] > 0.5,
        "magnet_engaged": haul_start is not None,
        "haul_back_completed": haul_done is not None,
    }
    s.report.setdefault("traces", {})[f"ram_{int(kmh)}"] = trace
    return summary


@pytest.mark.beamng_live
def test_g8_crest_rams(tmp_path: Path) -> None:
    """G8.1 - the three crest rams against Hot Potato serial 48, with the altitude falsifier."""

    with _session("G8", tmp_path, watchdog_seconds=2400.0) as s:
        r = s.report
        r["hot_potato_serial"] = s.report["locks"]["hot_potato"]["serial"]
        s.set_options(LONG_FUSE)
        s.set_option("ai_enabled", False)
        for n in AI[1:]:
            s.park(n)
        drv = Driver(s, PLAYER)
        drv.calibrate(_bearing_xy(90.0, 40.0), 0.0)
        # A live round with the player a member but not the carrier.
        s.drop_round()
        s.start_round(AI[0])
        s.park(AI[0])
        s.set_option("arena_magnet_enabled", True)
        rams: dict[str, Any] = {}
        for kmh in (60.0, 85.0, 110.0):
            if s.stats().get("phase") != "live":
                s.drop_round()
                s.start_round(AI[0])
                s.park(AI[0])
            summary = _run_crest_ram(s, kmh)
            rams[str(int(kmh))] = summary
            r["crest_rams"] = rams
            for clause, ok in summary["clauses"].items():
                if not ok:
                    s.problem(
                        f"{int(kmh)} km/h crest ram: {clause} failed",
                        {
                            k: summary[k]
                            for k in (
                                "crest_speed_mps",
                                "max_r",
                                "landing",
                                "min_uz",
                                "haul_seconds",
                                "altitude",
                                "tether_amber_pixels",
                            )
                        },
                    )
            if summary["min_uz"] <= 0.5:
                s.teleport(PLAYER, _bearing_xy(285.0, 40.0), 285.0)
            if (
                kmh == 85.0
                and summary["clauses"]["haul_back_completed"] is False
                and summary["tether_amber_pixels"]
            ):
                s.problem(
                    "FALSIFIER: a car was stranded outside the ring WITH a tether demonstrably drawn "
                    "(amber beads photographed) - the well is placed and the haul still does not complete",
                    {
                        "tether_amber_pixels": summary["tether_amber_pixels"],
                        "altitude": summary["altitude"],
                        "max_r": summary["max_r"],
                    },
                )
        # The design's numbers, restated against the fix's predictions.
        r["predictions"] = {
            "60_kmh_haul_seconds": rams["60"]["haul_seconds"],
            "60_kmh_expected": "~2.2 s, unchanged (any change is a regression)",
            "85_kmh_haul_seconds": rams["85"]["haul_seconds"],
            "85_kmh_expected": "engaged and completing, ~4.5 s from 190.5 m",
            "110_kmh_min_uz": rams["110"]["min_uz"],
            "110_kmh_expected": "upright, min uz well above 0.5 (was 0.20)",
        }
        r["altitude_falsifier"] = {
            str(int(k)): {
                "rose_while_tethered": rams[str(int(k))]["altitude"]["rose_while_tethered"],
                **rams[str(int(k))]["altitude"],
                "tether_amber_pixels": rams[str(int(k))]["tether_amber_pixels"],
            }
            for k in (60.0, 85.0, 110.0)
        }
        s.shot(
            "after_rams",
            (*_bearing_xy(285.0, 120.0), C[2] + 12.0),
            (*_bearing_xy(285.0, 91.4), C[2] + 5.5),
            "the crest and glacis at bearing 285 after the serial-48 ram runs",
        )
    assert not s.report.get("problems"), s.report["problems"]


# ====================================================================================
# G9 - the dodge latch and the tip limit (Hot Potato serial 50)
#
# Serial 50 changed two things this gate exists to judge:
#   * the dodge side-step is LATCHED in world space until the car is genuinely
#     past, aimed from the post abeam at r + min(6, speed x 0.35), and a dodging
#     car's role change is recorded rather than sent (the 4 Hz limit cycle that
#     produced G3/G7.3's repeat strikes);
#   * the LATERAL share of the magnet pull is capped by a solved tip limit, so a
#     car whose tires HOLD cannot be rolled by the well's own couple.
#
# Contacts are reported in TWO buckets on purpose. Point+radius keep-outs can
# express a pillar; they cannot express a 44.5 m ramp flank. Whether flank
# contacts survive the latch fix is the evidence for (or against) adding a
# segment primitive to the registry - so the split is the deliverable, not a
# convenience.
# ====================================================================================

SOLID_CLASSES = {
    "pillar_tower": ("masher_", "grinder_", "geyser_tower"),
    "ramp_flank": ("ramp_e_inner_flank", "ramp_w_inner_flank"),
    "handle": ("handle_flank", "handle_nose"),
    "jamb": ("jamb_",),
}


def _solid_class(name: str) -> str:
    for label, prefixes in SOLID_CLASSES.items():
        if any(name.startswith(p) for p in prefixes):
            return label
    return "other"


@pytest.mark.beamng_live
def test_g9_ai_dodge(tmp_path: Path) -> None:
    """G9.1 - 3 minutes of chase/flee against serial 50: zero contacts, split by solid kind."""

    with _session("G9_1", tmp_path, watchdog_seconds=2400.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]
        props = [
            n
            for n in [e["name"] for e in sync.vehicle_layout(HANDOFF)]
            if n not in (PLAYER, DISPENSER) and n not in AI
        ]
        s.move_away([PLAYER])
        s.set_options(LONG_FUSE)
        s.set_option("ai_enabled", True)
        s.start_round(AI[0])
        hits: list[dict[str, Any]] = []
        last_damage: dict[str, float] = {}
        min_clear: dict[str, float] = {}
        t0 = s.clock()
        samples = 0
        while s.clock() - t0 < 180.0:
            rows = _census_tick(s, AI + props, last_damage, hits, s.clock() - t0)
            for n in AI:
                row = rows[n]
                if row.get("ok"):
                    solid, clearance = _nearest_solid(row["x"], row["y"], row["z"])
                    min_clear[solid] = min(min_clear.get(solid, 1e9), clearance)
            samples += 1
            if samples % 100 == 0 and s.stats().get("phase") != "live":
                s.start_round(AI[0])
            s.step(STEP_TICK)
        chase = s.stats()
        solid_hits = [h for h in hits if h["kind"] == "solid" and h["car"] in AI]
        for h in solid_hits:
            h["solid_class"] = _solid_class(h["solid"])
        # Consecutive samples on the same car+solid are ONE contact event.
        events: list[dict[str, Any]] = []
        for h in solid_hits:
            if (
                events
                and h["car"] == events[-1]["car"]
                and h["solid"] == events[-1]["solid"]
                and h["t"] - events[-1]["t_end"] <= 1.0
            ):
                e = events[-1]
                e["t_end"] = h["t"]
                e["samples"] += 1
                e["damage"] += h["delta"]
                e["min_clearance"] = min(e["min_clearance"], h["solid_clearance"])
                e["max_speed"] = max(e["max_speed"], h["speed"])
            else:
                events.append(
                    {
                        "car": h["car"].rsplit("_", 1)[-1],
                        "solid": h["solid"],
                        "solid_class": h["solid_class"],
                        "t": h["t"],
                        "t_end": h["t"],
                        "samples": 1,
                        "damage": h["delta"],
                        "min_clearance": h["solid_clearance"],
                        "max_speed": h["speed"],
                        "x": h["x"],
                        "y": h["y"],
                        "z": h["z"],
                    }
                )
        by_class: dict[str, list[dict[str, Any]]] = {}
        for e in events:
            by_class.setdefault(e["solid_class"], []).append(e)
        r["chase"] = {
            "sim_seconds": round(s.clock() - t0, 1),
            "samples": samples,
            "transfers": chase.get("transfers"),
            "field": chase.get("field"),
            "props_excluded": chase.get("props_excluded"),
            "contact_events_total": len(events),
            "contact_events_by_class": {k: len(v) for k, v in sorted(by_class.items())},
            "pillar_tower_events": by_class.get("pillar_tower", []),
            "ramp_flank_events": by_class.get("ramp_flank", []),
            "other_events": [
                e for k, v in by_class.items() if k not in ("pillar_tower", "ramp_flank") for e in v
            ],
            "min_clearance_by_solid": {k: round(v, 2) for k, v in sorted(min_clear.items())},
            "hits_by_kind": {
                k: sum(1 for h in hits if h["kind"] == k) for k in ("solid", "car", "other")
            },
        }
        s.shot(
            "chase_field",
            (C[0] + 70.0, C[1] + 80.0, C[2] + 45.0),
            (C[0], C[1], C[2] + 2.0),
            "the field after 3 minutes of chase/flee on serial 50",
        )
        # The two buckets are judged SEPARATELY - that split is the deliverable.
        s.check(
            len(by_class.get("pillar_tower", [])) == 0,
            "AI still strikes PILLARS/TOWERS after the dodge latch (point keep-outs should express these)",
            by_class.get("pillar_tower", []),
        )
        s.check(
            len(by_class.get("ramp_flank", [])) == 0,
            "AI still strikes the RAMP FLANK after the dodge latch (a 44.5 m wall a point keep-out cannot express)",
            by_class.get("ramp_flank", []),
        )
        s.check(
            len(by_class.get("handle", [])) == 0,
            "AI struck the handle flank/nose",
            by_class.get("handle", []),
        )
        s.check(
            len(by_class.get("jamb", [])) == 0, "AI struck a spout jamb", by_class.get("jamb", [])
        )
        s.set_option("ai_enabled", False)
    assert not s.report.get("problems"), s.report["problems"]


@pytest.mark.beamng_live
def test_g9_magnet_orbit(tmp_path: Path) -> None:
    """G9.2 - six orbit excursions at BOTH dials: re-enter AND stay upright."""

    with _session("G9_2", tmp_path, watchdog_seconds=2400.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]
        s.set_options(LONG_FUSE)
        s.set_option("ai_enabled", False)
        for n in AI[1:]:
            s.park(n)
        drv = Driver(s, PLAYER)
        drv.calibrate(_bearing_xy(90.0, 40.0), 0.0)
        s.drop_round()
        s.start_round(AI[0])
        s.park(AI[0])

        def _excursion(gees: float, index: int, bearing: float) -> dict[str, Any]:
            if s.stats().get("phase") != "live":
                s.drop_round()
                s.start_round(AI[0])
                s.park(AI[0])
            s.teleport(PLAYER, _bearing_xy(bearing, 60.0), bearing)
            s.step(45)  # membership: the car must be seen INSIDE the ring
            s.teleport(
                PLAYER,
                _bearing_xy(bearing, 98.0),
                (bearing + 90.0) % 360.0,
                z=s.surface_z(*_bearing_xy(bearing, 98.0)) + 0.6,
            )
            s.control(PLAYER, steering=0.0, throttle=1.0, brake=0.0, parkingbrake=0.0)
            s.vehicle(PLAYER).set_velocity(33.0, 1.0)
            trace: list[dict[str, Any]] = []
            reentry = None
            rolled_at = None
            t0 = s.clock()
            for _ in range(700):
                p = s.probe(PLAYER)
                t = s.clock() - t0
                trace.append(
                    {
                        "t": round(t, 2),
                        "r": round(p["r"], 1),
                        "bearing": round(p["bearing"], 1),
                        "speed": round(p["hspeed"], 1),
                        "z": round(p["z"], 2),
                        "uz": round(p["uz"], 3),
                        "height": round(-p["clearance"], 2),
                    }
                )
                if rolled_at is None and p["uz"] < 0.6:
                    # WHERE it rolls is the runtime worker's own discriminator:
                    # the 30 % glacis cross-slope is a trip ramp; the flat apron
                    # beyond r 113 is not.
                    zone = (
                        "glacis_cross_slope"
                        if CREST_R <= p["r"] <= GLACIS_TOE_R
                        else "runoff_apron"
                        if p["r"] > GLACIS_TOE_R
                        else "inside_ring"
                    )
                    rolled_at = {
                        "t": round(t, 2),
                        "r": round(p["r"], 1),
                        "uz": round(p["uz"], 3),
                        "speed": round(p["hspeed"], 1),
                        "zone": zone,
                        "ground_z": round(p["z"] + p["clearance"], 2),
                    }
                if reentry is None and p["r"] < R_RELEASE and t > 0.5:
                    reentry = round(t, 2)
                    break
                if t > 40.0:
                    break
                target = (p["bearing"] + 90.0) % 360.0
                err = math.radians(_wrap_deg(target - p["yaw"]))
                s.control(
                    PLAYER,
                    steering=max(-1, min(1, s.steer_sign * 1.5 * err)),
                    throttle=1.0,
                    brake=0.0,
                    parkingbrake=0.0,
                )
                s.step(3)
            s.control(PLAYER, steering=0.0, throttle=0.0, brake=1.0, parkingbrake=0.0)
            s.step(20)
            out = {
                "attempt": index,
                "gees": gees,
                "bearing": bearing,
                "reentry_s": reentry,
                "max_r": round(max(x["r"] for x in trace), 1),
                "max_speed": max(x["speed"] for x in trace),
                "min_uz": round(min(x["uz"] for x in trace), 3),
                "rolled_at": rolled_at,
                "max_height_above_ground": round(max(x["height"] for x in trace), 2),
                "samples": len(trace),
            }
            out["reentered"] = reentry is not None and reentry <= 15.0
            out["stayed_upright"] = out["min_uz"] > 0.6
            out["passed"] = out["reentered"] and out["stayed_upright"]
            s.report.setdefault("traces", {})[f"orbit_{str(gees).replace('.', '_')}g_{index}"] = (
                trace
            )
            return out

        orbit: dict[str, Any] = {}
        for gees in (1.2, 2.0):
            runs = []
            for index, bearing in enumerate((100.0, 20.0, 145.0, 250.0, 305.0, 65.0), start=1):
                runs.append(_excursion(gees, index, bearing))
                if runs[-1]["min_uz"] < 0.6:
                    s.teleport(
                        PLAYER, _bearing_xy(bearing, 40.0), bearing, reset=False
                    )  # right the car
            key = f"at_{str(gees).replace('.', '_')}g"
            orbit[key] = {
                "runs": runs,
                "excursions": len(runs),
                "reentered": sum(1 for x in runs if x["reentered"]),
                "stayed_upright": sum(1 for x in runs if x["stayed_upright"]),
                "passed": sum(1 for x in runs if x["passed"]),
                "min_uz_overall": min(x["min_uz"] for x in runs),
                "reentry_times": [x["reentry_s"] for x in runs],
                "roll_zones": [x["rolled_at"]["zone"] for x in runs if x["rolled_at"]],
            }
            r["magnet_orbit"] = orbit
            s.set_option("arena_magnet_g", 1.2)
        s.shot(
            "orbit_lane",
            (*_bearing_xy(100.0, 140.0), C[2] + 20.0),
            (*_bearing_xy(100.0, 100.0), C[2] + 3.0),
            "the glacis orbit lane after the serial-50 attempts",
        )
        for key, block in orbit.items():
            s.check(
                block["stayed_upright"] == block["excursions"],
                f"{key}: a car still rolled during an orbit attempt (tip limit)",
                {
                    "min_uz_overall": block["min_uz_overall"],
                    "roll_zones": block["roll_zones"],
                    "rolled": [x for x in block["runs"] if not x["stayed_upright"]],
                },
            )
            s.check(
                block["reentered"] == block["excursions"],
                f"{key}: an excursion did not re-enter across the 82.3 m line within 15 s",
                {"reentry_times": block["reentry_times"]},
            )
    assert not s.report.get("problems"), s.report["problems"]


@pytest.mark.beamng_live
def test_g9_crest_rams_regression(tmp_path: Path) -> None:
    """G9.3 - G8.1's three crest rams again on serial 50 (the tip limit touched this code)."""

    with _session("G9_3", tmp_path, watchdog_seconds=2400.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]
        s.set_options(LONG_FUSE)
        s.set_option("ai_enabled", False)
        for n in AI[1:]:
            s.park(n)
        drv = Driver(s, PLAYER)
        drv.calibrate(_bearing_xy(90.0, 40.0), 0.0)
        s.drop_round()
        s.start_round(AI[0])
        s.park(AI[0])
        s.set_option("arena_magnet_enabled", True)
        rams: dict[str, Any] = {}
        for kmh in (60.0, 85.0, 110.0):
            if s.stats().get("phase") != "live":
                s.drop_round()
                s.start_round(AI[0])
                s.park(AI[0])
            summary = _run_crest_ram(s, kmh)
            rams[str(int(kmh))] = summary
            r["crest_rams"] = rams
            for clause, ok in summary["clauses"].items():
                if not ok:
                    s.problem(
                        f"REGRESSION on serial 50: {int(kmh)} km/h crest ram: {clause} failed",
                        {
                            k: summary[k]
                            for k in (
                                "crest_speed_mps",
                                "max_r",
                                "landing",
                                "min_uz",
                                "haul_seconds",
                                "altitude",
                            )
                        },
                    )
            if summary["min_uz"] <= 0.5:
                s.teleport(PLAYER, _bearing_xy(285.0, 40.0), 285.0)
        r["altitude_falsifier"] = {
            k: {**v["altitude"], "tether_amber_pixels": v["tether_amber_pixels"]}
            for k, v in rams.items()
        }
        s.shot(
            "after_rams",
            (*_bearing_xy(285.0, 120.0), C[2] + 12.0),
            (*_bearing_xy(285.0, 91.4), C[2] + 5.5),
            "the crest and glacis after the serial-50 ram regression",
        )
    assert not s.report.get("problems"), s.report["problems"]


# ====================================================================================
# G10 - the slope-aware tip limit (Hot Potato serial 51)
#
# Serial 51 makes the tip allowance a function of the surface: RATIO x MARGIN x
# cos(theta) - sin(theta) (0.720 on the apron, 0.403 at 30 %), and fades the hoist
# to zero by 30 % grade because lift strips the very load that resists a trip.
# At grade 0 the expression reduces to serial 50's flat form exactly.
#
# Two things the runtime worker asked for, honoured here:
#   * ITS FALSIFIER - the apron is grade 0, so apron numbers must not move. Any
#     movement in the flat-ground numbers is reported as the falsifier FIRING,
#     not as a pass.
#   * ITS NAMED RESIDUAL - the tip budget uses a generic half-track/CG-height
#     ratio of 1.2, so every roll logs the VEHICLE MODEL, and a deliberately
#     taller vehicle (the D-series pickup, the design's heaviest supported class)
#     runs the same excursions so a residual can be told vehicle-specific from
#     position-specific.
# ====================================================================================

# The coordinator's acceptance of the far-field striping rested on "never visible
# at play distance", but every shipped-build far-field block so far carried ONLY
# the 300 m camera - 150 m and 100 m frames existed just for the control boot.
# So every G10 boot now sweeps all three distances on the SHIPPED build, with a
# skins-hidden reference per camera, and the band metric is read at each. The
# thresholds are the ones already in use (clean 1.2-1.8, banded 3-5.7, line 2.2);
# nothing here is tuned to make the answer come out any particular way.
FARFIELD_CAMS = {
    "d300": (((C[0], C[1] - 60.0, C[2] + 300.0), (C[0], C[1], C[2])), (640, 372, 140)),
    "d150": (((C[0], C[1] - 30.0, C[2] + 150.0), (C[0], C[1], C[2])), (640, 360, 250)),
    "d100": (((C[0], C[1] - 20.0, C[2] + 100.0), (C[0], C[1], C[2])), (640, 360, 300)),
}


def _farfield_sweep(s: Session, frames: int = 4) -> dict[str, Any]:
    """Band metric on the SHIPPED build at 300 m, 150 m and 100 m, plus references."""

    s.step(60)
    out: dict[str, Any] = {}
    shots: dict[str, list[Path]] = {}
    for tag, (cam, _disc) in FARFIELD_CAMS.items():
        shots[tag] = [
            s.shot(f"farfield_{tag}_{i}", *cam, f"shipped build, floor from {tag[1:]} m, frame {i}")
            for i in range(1, frames + 1)
        ]
    s.set_hidden(FLOOR_STATICS, True)
    hidden = {
        tag: s.shot(
            f"farfield_{tag}_skins_hidden",
            *cam,
            f"{tag[1:]} m camera, floor skins hidden (groundplane reference)",
        )
        for tag, (cam, _d) in FARFIELD_CAMS.items()
    }
    s.set_hidden(FLOOR_STATICS, False)
    for tag, (_cam, disc) in FARFIELD_CAMS.items():
        ratios = [smoke._band_ratio(f, *disc) for f in shots[tag]]
        out[tag] = {
            "band_ratios": [round(x, 3) for x in ratios],
            "min": round(min(ratios), 3),
            "max": round(max(ratios), 3),
            "frames_over_2_2": sum(1 for x in ratios if x > 2.2),
            "median_shipped": [round(_disc_median(f, *disc), 1) for f in shots[tag]],
            "median_skins_hidden": round(_disc_median(hidden[tag], *disc), 1),
        }
    out["verdict"] = (
        "clean at every distance"
        if all(v["frames_over_2_2"] == 0 for v in out.values() if isinstance(v, dict))
        else "banded at: "
        + ", ".join(k for k, v in out.items() if isinstance(v, dict) and v["frames_over_2_2"])
    )
    s.report["farfield_sweep"] = out
    return out


G9_ORBIT_BASELINE = {
    # From G9.2 on serial 50 (arena 91f05bbc), the numbers this pass must not move
    # on flat ground: attempt 1 at bearing 100 was the one attempt that never
    # rolled, at both dials.
    "1.2": {
        "attempt_1_max_r": 113.2,
        "attempt_1_min_uz": 0.886,
        "attempt_1_max_speed": 29.9,
        "reentered": 3,
        "upright": 1,
    },
    "2.0": {
        "attempt_1_max_r": 113.1,
        "attempt_1_min_uz": 0.88,
        "attempt_1_max_speed": 29.8,
        "reentered": 3,
        "upright": 2,
    },
}


def _orbit_excursion(
    s: Session, name: str, model: str, gees: float, index: int, bearing: float
) -> dict[str, Any]:
    """One tangential orbit attempt; every roll carries the vehicle model."""

    if s.stats().get("phase") != "live":
        s.drop_round()
        s.start_round(AI[0])
        s.park(AI[0])
    s.teleport(name, _bearing_xy(bearing, 60.0), bearing)
    s.step(45)  # membership: seen INSIDE the ring
    s.teleport(
        name,
        _bearing_xy(bearing, 98.0),
        (bearing + 90.0) % 360.0,
        z=s.surface_z(*_bearing_xy(bearing, 98.0)) + 0.6,
    )
    s.control(name, steering=0.0, throttle=1.0, brake=0.0, parkingbrake=0.0)
    s.vehicle(name).set_velocity(33.0, 1.0)
    trace: list[dict[str, Any]] = []
    reentry = None
    rolled_at = None
    t0 = s.clock()
    for _ in range(700):
        p = s.probe(name)
        t = s.clock() - t0
        trace.append(
            {
                "t": round(t, 2),
                "r": round(p["r"], 1),
                "bearing": round(p["bearing"], 1),
                "speed": round(p["hspeed"], 1),
                "z": round(p["z"], 2),
                "uz": round(p["uz"], 3),
                "height": round(-p["clearance"], 2),
            }
        )
        if rolled_at is None and p["uz"] < 0.6:
            zone = (
                "glacis_cross_slope"
                if CREST_R <= p["r"] <= GLACIS_TOE_R
                else "runoff_apron"
                if p["r"] > GLACIS_TOE_R
                else "inside_ring"
            )
            rolled_at = {
                "t": round(t, 2),
                "r": round(p["r"], 1),
                "uz": round(p["uz"], 3),
                "speed": round(p["hspeed"], 1),
                "zone": zone,
                "ground_z": round(p["z"] + p["clearance"], 2),
                "model": model,
                "vehicle": name,
            }
        if reentry is None and p["r"] < R_RELEASE and t > 0.5:
            reentry = round(t, 2)
            break
        if t > 40.0:
            break
        target = (p["bearing"] + 90.0) % 360.0
        err = math.radians(_wrap_deg(target - p["yaw"]))
        s.control(
            name,
            steering=max(-1, min(1, s.steer_sign * 1.5 * err)),
            throttle=1.0,
            brake=0.0,
            parkingbrake=0.0,
        )
        s.step(3)
    s.control(name, steering=0.0, throttle=0.0, brake=1.0, parkingbrake=0.0)
    s.step(20)
    out = {
        "attempt": index,
        "gees": gees,
        "bearing": bearing,
        "model": model,
        "reentry_s": reentry,
        "max_r": round(max(x["r"] for x in trace), 1),
        "max_speed": max(x["speed"] for x in trace),
        "min_uz": round(min(x["uz"] for x in trace), 3),
        "rolled_at": rolled_at,
        "max_height_above_ground": round(max(x["height"] for x in trace), 2),
        "samples": len(trace),
    }
    out["reentered"] = reentry is not None and reentry <= 15.0
    out["stayed_upright"] = out["min_uz"] > 0.6
    out["passed"] = out["reentered"] and out["stayed_upright"]
    s.report.setdefault("traces", {})[f"orbit_{model}_{str(gees).replace('.', '_')}g_{index}"] = (
        trace
    )
    return out


@pytest.mark.beamng_live
def test_g10_magnet_orbit(tmp_path: Path) -> None:
    """G10.1 - six excursions at both dials on serial 51, plus a tall-vehicle probe."""

    with _session("G10_1", tmp_path, watchdog_seconds=3000.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]
        s.set_options(LONG_FUSE)
        s.set_option("ai_enabled", False)
        for n in AI[1:]:
            s.park(n)
        _farfield_sweep(s)
        drv = Driver(s, PLAYER)
        drv.calibrate(_bearing_xy(90.0, 40.0), 0.0)
        s.drop_round()
        s.start_round(AI[0])
        s.park(AI[0])
        bearings = (100.0, 20.0, 145.0, 250.0, 305.0, 65.0)
        orbit: dict[str, Any] = {}
        for gees in (1.2, 2.0):
            s.set_option("arena_magnet_g", gees)
            runs = [
                _orbit_excursion(s, PLAYER, "etk800", gees, i, b)
                for i, b in enumerate(bearings, start=1)
            ]
            for run in runs:
                if run["min_uz"] < 0.6:
                    s.teleport(PLAYER, _bearing_xy(run["bearing"], 40.0), run["bearing"])
            key = f"at_{str(gees).replace('.', '_')}g"
            orbit[key] = {
                "model": "etk800",
                "runs": runs,
                "excursions": len(runs),
                "reentered": sum(1 for x in runs if x["reentered"]),
                "stayed_upright": sum(1 for x in runs if x["stayed_upright"]),
                "passed": sum(1 for x in runs if x["passed"]),
                "min_uz_overall": min(x["min_uz"] for x in runs),
                "reentry_times": [x["reentry_s"] for x in runs],
                "rolls": [x["rolled_at"] for x in runs if x["rolled_at"]],
                "roll_zones": [x["rolled_at"]["zone"] for x in runs if x["rolled_at"]],
                "roll_models": sorted({x["rolled_at"]["model"] for x in runs if x["rolled_at"]}),
            }
            r["magnet_orbit"] = orbit
        s.set_option("arena_magnet_g", 1.2)

        # --- the runtime worker's FALSIFIER: flat ground must not move ---------
        # Attempt 1 (bearing 100) is the run that stayed upright at both dials on
        # serial 50. Its numbers are grade-0 behaviour; serial 51 reduces to the
        # flat expression exactly there, so they must be unchanged.
        falsifier: dict[str, Any] = {}
        for gees, key in ((1.2, "at_1_2g"), (2.0, "at_2_0g")):
            base = G9_ORBIT_BASELINE[str(gees)]
            run1 = orbit[key]["runs"][0]
            moved = {
                "max_r": (
                    base["attempt_1_max_r"],
                    run1["max_r"],
                    round(run1["max_r"] - base["attempt_1_max_r"], 2),
                ),
                "min_uz": (
                    base["attempt_1_min_uz"],
                    run1["min_uz"],
                    round(run1["min_uz"] - base["attempt_1_min_uz"], 3),
                ),
                "max_speed": (
                    base["attempt_1_max_speed"],
                    run1["max_speed"],
                    round(run1["max_speed"] - base["attempt_1_max_speed"], 2),
                ),
            }
            falsifier[key] = {
                "serial50_vs_serial51": moved,
                "max_r_moved_gt_1m": abs(moved["max_r"][2]) > 1.0,
                "min_uz_moved_gt_0_05": abs(moved["min_uz"][2]) > 0.05,
                "max_speed_moved_gt_1mps": abs(moved["max_speed"][2]) > 1.0,
            }
        # RETIRED as a gate at G13, kept as a recording. It fired on serial 51
        # (max r +1.9 m, min uz +0.06, speed unchanged to the decimal), the
        # runtime ruled it in round 9 - the reference run is NOT grade-0 for its
        # whole length, since it reaches r 113-115 across bank and glacis, so
        # both the slope term and the hoist fade legitimately engage - and D-6
        # was closed EXPLAINED. Left as a live check it compared every later
        # serial against a frozen serial-50 baseline and so failed every run,
        # with a message that still said "serial 51". The invariant it was
        # guarding (grade 0 reduces v2.11 to v2.10 exactly) is algebra and is
        # pinned by the lupa state-machine suite, which does not need the game.
        r["falsifier_flat_ground"] = {
            "status": "RETIRED at G13 - recorded, not gated",
            "baseline": "serial 50 (G9.2), frozen",
            "ruling": "D-6 EXPLAINED in runtime round 9: the reference run is not grade-0 for "
            "its whole length; the grade-0 identity is pinned by the lupa suite",
            "measurements": falsifier,
        }

        # --- the NAMED RESIDUAL: a taller vehicle on the same excursions ------
        pickup = Vehicle(f"{MOD_ID}_g10_pickup", "pickup", license="TALL")
        assert (
            s.bng.vehicles.spawn(
                pickup,
                (*_bearing_xy(90.0, 45.0), C[2] + 0.6),
                _heading_quat(0.0),
                cling=False,
                connect=True,
            )
            is True
        )
        s.register(pickup)
        s.step(60)
        s.vehicle(pickup.vid).set_shift_mode("realistic_automatic")
        tall_runs = [
            _orbit_excursion(s, pickup.vid, "pickup", 1.2, i, b)
            for i, b in enumerate((100.0, 20.0, 305.0), start=1)
        ]
        r["tall_vehicle"] = {
            "model": "pickup",
            "gees": 1.2,
            "runs": tall_runs,
            "excursions": len(tall_runs),
            "reentered": sum(1 for x in tall_runs if x["reentered"]),
            "stayed_upright": sum(1 for x in tall_runs if x["stayed_upright"]),
            "min_uz_overall": min(x["min_uz"] for x in tall_runs),
            "rolls": [x["rolled_at"] for x in tall_runs if x["rolled_at"]],
            "note": "the tip budget uses a generic half-track/CG-height ratio of 1.2; this is the tall class",
        }
        s.bng.vehicles.despawn(pickup)
        s._vehicles.pop(pickup.vid, None)
        s.shot(
            "orbit_lane",
            (*_bearing_xy(100.0, 140.0), C[2] + 20.0),
            (*_bearing_xy(100.0, 100.0), C[2] + 3.0),
            "the glacis orbit lane after the serial-51 attempts",
        )
        for key, block in orbit.items():
            s.check(
                block["stayed_upright"] == block["excursions"],
                f"{key}: a car still rolled during an orbit attempt",
                {
                    "min_uz_overall": block["min_uz_overall"],
                    "rolls": block["rolls"],
                    "roll_models": block["roll_models"],
                },
            )
            s.check(
                block["reentered"] == block["excursions"],
                f"{key}: an excursion did not re-enter across the 82.3 m line within 15 s",
                {"reentry_times": block["reentry_times"]},
            )
    assert not s.report.get("problems"), s.report["problems"]


@pytest.mark.beamng_live
def test_g10_crest_rams(tmp_path: Path) -> None:
    """G10.2 - the three crest rams on serial 51 (run twice, as its own boots)."""

    with _session("G10_2", tmp_path, watchdog_seconds=2400.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]
        s.set_options(LONG_FUSE)
        s.set_option("ai_enabled", False)
        for n in AI[1:]:
            s.park(n)
        _farfield_sweep(s)
        drv = Driver(s, PLAYER)
        drv.calibrate(_bearing_xy(90.0, 40.0), 0.0)
        s.drop_round()
        s.start_round(AI[0])
        s.park(AI[0])
        s.set_option("arena_magnet_enabled", True)
        rams: dict[str, Any] = {}
        for kmh in (60.0, 85.0, 110.0):
            if s.stats().get("phase") != "live":
                s.drop_round()
                s.start_round(AI[0])
                s.park(AI[0])
            summary = _run_crest_ram(s, kmh)
            summary["model"] = "etk800"
            rams[str(int(kmh))] = summary
            r["crest_rams"] = rams
            for clause, ok in summary["clauses"].items():
                if not ok:
                    s.problem(
                        f"serial 51: {int(kmh)} km/h crest ram: {clause} failed",
                        {
                            "model": "etk800",
                            **{
                                k: summary[k]
                                for k in (
                                    "crest_speed_mps",
                                    "max_r",
                                    "landing",
                                    "min_uz",
                                    "haul_seconds",
                                    "altitude",
                                )
                            },
                        },
                    )
            if summary["min_uz"] <= 0.5:
                s.teleport(PLAYER, _bearing_xy(285.0, 40.0), 285.0)
        r["haul_seconds"] = {k: v["haul_seconds"] for k, v in rams.items()}
        r["min_uz"] = {k: v["min_uz"] for k, v in rams.items()}
        r["altitude_falsifier"] = {
            k: {**v["altitude"], "tether_amber_pixels": v["tether_amber_pixels"]}
            for k, v in rams.items()
        }
        s.shot(
            "after_rams",
            (*_bearing_xy(285.0, 120.0), C[2] + 12.0),
            (*_bearing_xy(285.0, 91.4), C[2] + 5.5),
            "the crest and glacis after the serial-51 rams",
        )
    assert not s.report.get("problems"), s.report["problems"]


@pytest.mark.beamng_live
def test_g10_ai_dodge(tmp_path: Path) -> None:
    """G10.3 - the dodge result still holds on serial 51 (contacts ~0-1, split by kind)."""

    with _session("G10_3", tmp_path, watchdog_seconds=2400.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]
        _farfield_sweep(s)
        props = [
            n
            for n in [e["name"] for e in sync.vehicle_layout(HANDOFF)]
            if n not in (PLAYER, DISPENSER) and n not in AI
        ]
        s.move_away([PLAYER])
        s.set_options(LONG_FUSE)
        s.set_option("ai_enabled", True)
        s.start_round(AI[0])
        hits: list[dict[str, Any]] = []
        last_damage: dict[str, float] = {}
        min_clear: dict[str, float] = {}
        t0 = s.clock()
        samples = 0
        while s.clock() - t0 < 180.0:
            rows = _census_tick(s, AI + props, last_damage, hits, s.clock() - t0)
            for n in AI:
                row = rows[n]
                if row.get("ok"):
                    solid, clearance = _nearest_solid(row["x"], row["y"], row["z"])
                    min_clear[solid] = min(min_clear.get(solid, 1e9), clearance)
            samples += 1
            if samples % 100 == 0 and s.stats().get("phase") != "live":
                s.start_round(AI[0])
            s.step(STEP_TICK)
        chase = s.stats()
        solid_hits = [h for h in hits if h["kind"] == "solid" and h["car"] in AI]
        for h in solid_hits:
            h["solid_class"] = _solid_class(h["solid"])
        events: list[dict[str, Any]] = []
        for h in solid_hits:
            if (
                events
                and h["car"] == events[-1]["car"]
                and h["solid"] == events[-1]["solid"]
                and h["t"] - events[-1]["t_end"] <= 1.0
            ):
                e = events[-1]
                e["t_end"] = h["t"]
                e["samples"] += 1
                e["damage"] += h["delta"]
                e["min_clearance"] = min(e["min_clearance"], h["solid_clearance"])
                e["max_speed"] = max(e["max_speed"], h["speed"])
            else:
                events.append(
                    {
                        "car": h["car"].rsplit("_", 1)[-1],
                        "solid": h["solid"],
                        "solid_class": h["solid_class"],
                        "t": h["t"],
                        "t_end": h["t"],
                        "samples": 1,
                        "damage": h["delta"],
                        "min_clearance": h["solid_clearance"],
                        "max_speed": h["speed"],
                        "x": h["x"],
                        "y": h["y"],
                        "z": h["z"],
                    }
                )
        by_class: dict[str, list[dict[str, Any]]] = {}
        for e in events:
            by_class.setdefault(e["solid_class"], []).append(e)
        r["chase"] = {
            "sim_seconds": round(s.clock() - t0, 1),
            "samples": samples,
            "transfers": chase.get("transfers"),
            "field": chase.get("field"),
            "props_excluded": chase.get("props_excluded"),
            "contact_events_total": len(events),
            "contact_events_by_class": {k: len(v) for k, v in sorted(by_class.items())},
            "pillar_tower_events": by_class.get("pillar_tower", []),
            "ramp_flank_events": by_class.get("ramp_flank", []),
            "other_events": [
                e for k, v in by_class.items() if k not in ("pillar_tower", "ramp_flank") for e in v
            ],
            "min_clearance_by_solid": {k: round(v, 2) for k, v in sorted(min_clear.items())},
        }
        s.shot(
            "chase_field",
            (C[0] + 70.0, C[1] + 80.0, C[2] + 45.0),
            (C[0], C[1], C[2] + 2.0),
            "the field after 3 minutes of chase/flee on serial 51",
        )
        s.check(
            len(by_class.get("pillar_tower", [])) == 0,
            "AI struck pillars/towers on serial 51",
            by_class.get("pillar_tower", []),
        )
        s.check(
            len(by_class.get("ramp_flank", [])) == 0,
            "AI struck the ramp flank on serial 51",
            by_class.get("ramp_flank", []),
        )
        s.check(
            len(events) <= 1,
            "more than one obstacle contact in three minutes",
            r["chase"]["contact_events_by_class"],
        )
        s.set_option("ai_enabled", False)
    assert not s.report.get("problems"), s.report["problems"]


# ====================================================================================
# G11 - the unpin reflex (Hot Potato serial 52)
#
# Serial 52 adds ONE thing, for D-8: a car within 1.5 m of a registered keep-out
# at <= 3 m/s for 1.5 s gets a latched target 10.5 m clear on the far side of
# itself from the post, time-boxed at 6 s, released on range only.
#
# The count is not the interesting number - CHARACTER is. G10.3's 23 contacts
# were one car grinding at a fixed point for 145 s; a couple of transient brushes
# while driving past would be a different animal at the same count. So every
# contact event carries its duration, its position drift, its speed band and how
# close the nearest OTHER car was, and the analysis names one of three shapes:
#
#   transient_brush          - short, moving, isolated
#   fixed_position_grinding  - repeated contact inside a 2 m circle over seconds
#   pinned_by_car_cycle      - the runtime worker's OWN named failure: a car held
#                              by ANOTHER car cannot be freed, so the 6 s time-box
#                              expires and re-triggers, showing as a repeating
#                              ~6 s interval with a car within contact range.
# ====================================================================================

PIN_CYCLE_LO, PIN_CYCLE_HI = 4.5, 7.5  # the 6 s time-box, with sampling slack
PIN_SAME_SPOT_M = 2.0  # "fixed position" circle
PIN_CAR_RANGE_M = 6.5  # another car close enough to be holding it


def _contact_character(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Name the SHAPE of a contact residual, not just its count."""

    by_pair: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        by_pair.setdefault(f"{e['car']}::{e['solid']}", []).append(e)
    shapes: dict[str, Any] = {}
    for pair, evs in by_pair.items():
        evs.sort(key=lambda x: x["t"])
        starts = [e["t"] for e in evs]
        intervals = [round(b - a, 2) for a, b in zip(starts, starts[1:])]
        spread = 0.0
        for a in evs:
            for b in evs:
                spread = max(spread, math.hypot(a["x"] - b["x"], a["y"] - b["y"]))
        cycle_hits = [x for x in intervals if PIN_CYCLE_LO <= x <= PIN_CYCLE_HI]
        near_car = [
            e
            for e in evs
            if e.get("nearest_car_m") is not None and e["nearest_car_m"] <= PIN_CAR_RANGE_M
        ]
        if len(evs) >= 3 and len(cycle_hits) >= 2 and len(near_car) >= 2:
            shape = "pinned_by_car_cycle"
        elif len(evs) >= 3 and spread <= PIN_SAME_SPOT_M and (starts[-1] - starts[0]) > 5.0:
            shape = "fixed_position_grinding"
        else:
            shape = "transient_brush"
        shapes[pair] = {
            "shape": shape,
            "events": len(evs),
            "position_spread_m": round(spread, 2),
            "time_span_s": round(starts[-1] - starts[0], 1),
            "intervals_s": intervals,
            "cycle_like_intervals": cycle_hits,
            "max_speed": round(max(e["max_speed"] for e in evs), 1),
            "total_damage": sum(e["damage"] for e in evs),
            "events_with_car_within_6_5m": len(near_car),
            "nearest_car_m_min": round(
                min(
                    (e["nearest_car_m"] for e in evs if e.get("nearest_car_m") is not None),
                    default=-1,
                ),
                1,
            ),
        }
    counts: dict[str, int] = {}
    for v in shapes.values():
        counts[v["shape"]] = counts.get(v["shape"], 0) + 1
    return {
        "by_pair": shapes,
        "shape_counts": counts,
        "verdict": (
            "no contacts"
            if not shapes
            else "; ".join(f"{n} x {k}" for k, n in sorted(counts.items()))
        ),
    }


def _group_contacts(solid_hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Consecutive damage readings against ONE solid by ONE car are ONE event.

    G13 correction. The run test used to compare `h["car"]` (the full scene
    name, `..._ai_3`) against `events[-1]["car"]` (already shortened to `3`),
    so it never once matched and NOTHING was ever grouped: every gate from G7
    onward has reported per-sample readings under the label "grouped events".
    That also made the comparison brittle in a second way - it only ever looked
    at the LAST event, so two cars touching different solids in the same second
    broke each other's runs. Both are fixed here: the open event is tracked per
    (car, solid) pair. The counts remain comparable across gates only if the
    same unit is quoted, so G13 reports the raw sample count as well.
    """

    events: list[dict[str, Any]] = []
    open_event: dict[tuple[str, str], dict[str, Any]] = {}
    for h in solid_hits:
        label = h["car"].rsplit("_", 1)[-1]
        key = (label, h["solid"])
        e = open_event.get(key)
        if e is not None and h["t"] - e["t_end"] <= 1.0:
            e["t_end"] = h["t"]
            e["samples"] += 1
            e["damage"] += h["delta"]
            e["min_clearance"] = min(e["min_clearance"], h["solid_clearance"])
            e["max_speed"] = max(e["max_speed"], h["speed"])
            e["nearest_car_m"] = min(e["nearest_car_m"], h["nearest_car_m"])
        else:
            e = {
                "car": label,
                "solid": h["solid"],
                "solid_class": _solid_class(h["solid"]),
                "t": h["t"],
                "t_end": h["t"],
                "samples": 1,
                "damage": h["delta"],
                "min_clearance": h["solid_clearance"],
                "max_speed": h["speed"],
                "nearest_car_m": h["nearest_car_m"],
                "x": h["x"],
                "y": h["y"],
                "z": h["z"],
            }
            events.append(e)
            open_event[key] = e
    for e in events:
        e["duration_s"] = round(e["t_end"] - e["t"], 2)
    return events


@pytest.mark.beamng_live
def test_g11_pin_reflex(tmp_path: Path) -> None:
    """G11.1 - the unpin reflex: contacts should fall to 0-2, and any residual must be transient."""

    with _session("G11_1", tmp_path, watchdog_seconds=2400.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]
        _farfield_sweep(s)
        props = [
            n
            for n in [e["name"] for e in sync.vehicle_layout(HANDOFF)]
            if n not in (PLAYER, DISPENSER) and n not in AI
        ]
        s.move_away([PLAYER])
        s.set_options(LONG_FUSE)
        s.set_option("ai_enabled", True)
        s.start_round(AI[0])
        hits: list[dict[str, Any]] = []
        last_damage: dict[str, float] = {}
        min_clear: dict[str, float] = {}
        slow_near: list[dict[str, Any]] = []
        t0 = s.clock()
        samples = 0
        while s.clock() - t0 < 180.0:
            t = s.clock() - t0
            rows = _census_tick(s, AI + props, last_damage, hits, t)
            for n in AI:
                row = rows[n]
                if row.get("ok"):
                    solid, clearance = _nearest_solid(row["x"], row["y"], row["z"])
                    min_clear[solid] = min(min_clear.get(solid, 1e9), clearance)
                    # The reflex's own trigger condition, watched from outside:
                    # within 1.5 m of a keep-out at <= 3 m/s.
                    if clearance <= 1.5 and row["hspeed"] <= 3.0:
                        slow_near.append(
                            {
                                "t": round(t, 1),
                                "car": n.rsplit("_", 1)[-1],
                                "solid": solid,
                                "clearance": round(clearance, 2),
                                "speed": round(row["hspeed"], 2),
                            }
                        )
            samples += 1
            if samples % 100 == 0 and s.stats().get("phase") != "live":
                s.start_round(AI[0])
            s.step(STEP_TICK)
        chase = s.stats()
        solid_hits = [h for h in hits if h["kind"] == "solid" and h["car"] in AI]
        for h in solid_hits:
            h["solid_class"] = _solid_class(h["solid"])
        events = _group_contacts(solid_hits)
        by_class: dict[str, list[dict[str, Any]]] = {}
        for e in events:
            by_class.setdefault(e["solid_class"], []).append(e)
        character = _contact_character(events)
        # How long did cars linger inside the reflex's trigger envelope?
        lingers: dict[str, int] = {}
        for row in slow_near:
            lingers[f"{row['car']}::{row['solid']}"] = (
                lingers.get(f"{row['car']}::{row['solid']}", 0) + 1
            )
        r["chase"] = {
            "sim_seconds": round(s.clock() - t0, 1),
            "samples": samples,
            "transfers": chase.get("transfers"),
            "field": chase.get("field"),
            "props_excluded": chase.get("props_excluded"),
            "contact_events_total": len(events),
            "contact_events_by_class": {k: len(v) for k, v in sorted(by_class.items())},
            "events": events,
            "max_contact_speed": round(max((e["max_speed"] for e in events), default=0.0), 1),
            "min_clearance_by_solid": {k: round(v, 2) for k, v in sorted(min_clear.items())},
        }
        r["contact_character"] = character
        r["reflex_envelope"] = {
            "samples_within_1_5m_at_or_below_3mps": len(slow_near),
            "by_car_and_solid": dict(sorted(lingers.items(), key=lambda kv: -kv[1])[:8]),
            "note": "each sample is 0.1 s of a car sitting inside the reflex's own trigger envelope",
        }
        s.shot(
            "chase_field",
            (C[0] + 70.0, C[1] + 80.0, C[2] + 45.0),
            (C[0], C[1], C[2] + 2.0),
            "the field after 3 minutes of chase/flee on serial 52",
        )
        # Count first, then CHARACTER - the discriminator that matters.
        s.check(
            len(events) <= 2,
            "more than two obstacle contact events in three minutes",
            {"total": len(events), "by_class": r["chase"]["contact_events_by_class"]},
        )
        s.check(
            character["shape_counts"].get("fixed_position_grinding", 0) == 0,
            "a car is still GRINDING at a fixed position against a keep-out (D-8 not closed)",
            {
                k: v
                for k, v in character["by_pair"].items()
                if v["shape"] == "fixed_position_grinding"
            },
        )
        s.check(
            character["shape_counts"].get("pinned_by_car_cycle", 0) == 0,
            "the runtime worker's named mode: a car pinned BY ANOTHER CAR re-triggering on the 6 s time-box",
            {k: v for k, v in character["by_pair"].items() if v["shape"] == "pinned_by_car_cycle"},
        )
        s.check(
            len(by_class.get("ramp_flank", [])) == 0,
            "AI struck the ramp flank on serial 52",
            by_class.get("ramp_flank", []),
        )
        s.set_option("ai_enabled", False)
    assert not s.report.get("problems"), s.report["problems"]


# ====================================================================================
# G12 - the glacis shadow split (geometry v3.4) and the out-of-bounds fuse (serial 53)
#
# THE MEASUREMENT LESSON THIS GATE EXISTS TO FIX: every far-field number before
# G12 sampled a PLAZA DISC at frame centre. The final critic cropped two 150 m
# frames from the same build - one clean boot, one banded - and found the outer
# GLACIS densely striped in the banded boot while the plaza disc read 0.896 vs
# 0.874, i.e. indistinguishable. The artifact had migrated out of the sampled
# region and my "clean at 150 m" claim was true of the disc and false of the
# frame. So the deciding number is now a GLACIS ANNULUS, projected from the real
# camera rather than guessed, and read PER SECTOR because the striping is patchy
# and a whole-ring mean averages it away.
#
# Validated offline before use, on the critic's own two frames (150 m):
#   clean boot  G10_1: annulus sectors over 2.2 = 4,  mean ratio 1.38
#   banded boot G10_3: annulus sectors over 2.2 = 8,  mean ratio 1.77
# The plaza disc could not tell them apart (0.874 vs 0.896). Sector COUNT is the
# discriminator, not the max: the shared structural features (spout gaps, the
# handle causeway, the crest rim) light up in both boots.
# ====================================================================================

GLACIS_R_IN, GLACIS_R_OUT = 91.4, 113.0
ANNULUS_SECTORS = 24
ANNULUS_TRIM_M = 2.5  # step off the crest rim and the toe edge so the mask is surface, not edge


def _camera_basis(eye: tuple[float, float, float], aim: tuple[float, float, float]):
    fx, fy, fz = (aim[0] - eye[0], aim[1] - eye[1], aim[2] - eye[2])
    fl = math.sqrt(fx * fx + fy * fy + fz * fz)
    f = (fx / fl, fy / fl, fz / fl)
    rx, ry, rz = (f[1] * 1.0 - f[2] * 0.0, f[2] * 0.0 - f[0] * 1.0, f[0] * 0.0 - f[1] * 0.0)
    rl = math.sqrt(rx * rx + ry * ry + rz * rz) or 1.0
    r = (rx / rl, ry / rl, rz / rl)
    u = (r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0])
    return f, r, u


def _project(point, eye, basis, fov_deg: float, width: int, height: int):
    f, r, u = basis
    v = (point[0] - eye[0], point[1] - eye[1], point[2] - eye[2])
    z = v[0] * f[0] + v[1] * f[1] + v[2] * f[2]
    if z <= 0.1:
        return None
    x = v[0] * r[0] + v[1] * r[1] + v[2] * r[2]
    y = v[0] * u[0] + v[1] * u[1] + v[2] * u[2]
    ty = math.tan(math.radians(fov_deg) / 2.0)
    tx = ty * (width / height)
    return (
        width / 2.0 + (x / z) / tx * (width / 2.0),
        height / 2.0 - (y / z) / ty * (height / 2.0),
    )


def _annulus_mask(eye, aim, fov_deg: float, width: int, height: int, r_in: float, r_out: float):
    """Screen mask of the glacis annulus, projected from the real camera pose."""

    import numpy as np
    from PIL import Image, ImageDraw

    basis = _camera_basis(eye, aim)
    crest_z = C[2] + float(HANDOFF["crest_z_m"])

    def ring(radius: float, z: float):
        pts = []
        for k in range(180):
            a = math.radians(k * 2.0)
            p = _project(
                (C[0] + radius * math.sin(a), C[1] + radius * math.cos(a), z),
                eye,
                basis,
                fov_deg,
                width,
                height,
            )
            if p is None:
                return None
            pts.append(p)
        return pts

    outer = ring(r_out, C[2])
    inner = ring(r_in, crest_z)
    if outer is None or inner is None:
        return None
    img = Image.new("1", (width, height), 0)
    ImageDraw.Draw(img).polygon(outer, fill=1)
    hole = Image.new("1", (width, height), 0)
    ImageDraw.Draw(hole).polygon(inner, fill=1)
    return np.asarray(img, dtype=bool) & ~np.asarray(hole, dtype=bool)


def _sector_stats(luma, mask, sectors: int = ANNULUS_SECTORS) -> dict[str, Any]:
    """Band metric per angular sector - patchy striping survives, a mean does not."""

    import numpy as np
    from scipy.ndimage import binary_erosion

    ys, xs = np.nonzero(mask)
    if len(xs) < 2000:
        return {"sectors": 0, "note": "annulus not visible in frame"}
    cx, cy = float(xs.mean()), float(ys.mean())
    yy, xx = np.mgrid[0 : luma.shape[0], 0 : luma.shape[1]]
    ang = np.degrees(np.arctan2(xx - cx, -(yy - cy))) % 360.0
    ratios: list[float] = []
    alts: list[float] = []
    for k in range(sectors):
        m = mask & (ang >= k * 360.0 / sectors) & (ang < (k + 1) * 360.0 / sectors)
        m = binary_erosion(m, iterations=1)
        if m.sum() < 300:
            continue
        gy = np.abs(luma[1:, :] - luma[:-1, :])
        my = m[1:, :] & m[:-1, :]
        gx = np.abs(luma[:, 1:] - luma[:, :-1])
        mx = m[:, 1:] & m[:, :-1]
        if my.sum() < 100 or mx.sum() < 100:
            continue
        ratios.append(float(gy[my].mean() / max(gx[mx].mean(), 1e-6)))
        rows = [luma[y][m[y]].mean() for y in range(luma.shape[0]) if m[y].sum() > 25]
        if len(rows) > 8:
            a = np.abs(np.diff(np.asarray(rows), 2))
            alts.append(float((a > 3.0).mean()))
    if not ratios:
        return {"sectors": 0, "note": "no sector had enough pixels"}
    return {
        "sectors": len(ratios),
        "ratio_max": round(max(ratios), 3),
        "ratio_mean": round(sum(ratios) / len(ratios), 3),
        "sectors_over_2_2": sum(1 for x in ratios if x > 2.2),
        "sectors_over_1_8": sum(1 for x in ratios if x > 1.8),
        "alt_frac_max": round(max(alts), 3) if alts else None,
        "alt_frac_mean": round(sum(alts) / len(alts), 3) if alts else None,
        "alt_sectors_over_0_25": sum(1 for x in alts if x > 0.25),
        "ratios": [round(x, 2) for x in sorted(ratios, reverse=True)],
    }


def _farfield_sweep_v2(s: Session, frames: int = 4) -> dict[str, Any]:
    """Plaza disc AND projected glacis annulus, at 300 / 150 / 100 m, with references."""

    fov = 65.0
    answer = s.lua(
        "local ok, v = pcall(function() return core_camera.getFovDeg() end); "
        "return jsonEncode({ok = ok == true, fov = ok and v or -1})"
    )
    if answer.get("ok") and float(answer.get("fov", -1)) > 10.0:
        fov = float(answer["fov"])
    s.step(60)
    out: dict[str, Any] = {
        "fov_deg": fov,
        "annulus_r_m": [GLACIS_R_IN + ANNULUS_TRIM_M, GLACIS_R_OUT - ANNULUS_TRIM_M],
    }
    shots: dict[str, list[Path]] = {}
    for tag, (cam, _disc) in FARFIELD_CAMS.items():
        shots[tag] = [
            s.shot(f"ff2_{tag}_{i}", *cam, f"v3.4 build, {tag[1:]} m, frame {i}")
            for i in range(1, frames + 1)
        ]
    s.set_hidden(FLOOR_STATICS, True)
    hidden = {
        tag: s.shot(f"ff2_{tag}_skins_hidden", *cam, f"{tag[1:]} m, floor skins hidden")
        for tag, (cam, _d) in FARFIELD_CAMS.items()
    }
    s.set_hidden(FLOOR_STATICS, False)
    for tag, (cam, disc) in FARFIELD_CAMS.items():
        eye, aim = cam
        mask = _annulus_mask(
            eye, aim, fov, 1280, 720, GLACIS_R_IN + ANNULUS_TRIM_M, GLACIS_R_OUT - ANNULUS_TRIM_M
        )
        disc_ratios = [smoke._band_ratio(f, *disc) for f in shots[tag]]
        entry: dict[str, Any] = {
            "plaza_disc": {
                "band_ratios": [round(x, 3) for x in disc_ratios],
                "min": round(min(disc_ratios), 3),
                "max": round(max(disc_ratios), 3),
                "frames_over_2_2": sum(1 for x in disc_ratios if x > 2.2),
                "median_shipped": [round(_disc_median(f, *disc), 1) for f in shots[tag]],
                "median_skins_hidden": round(_disc_median(hidden[tag], *disc), 1),
            }
        }
        if mask is None or mask.sum() < 2000:
            entry["glacis_annulus"] = {"error": "annulus did not project into frame"}
        else:
            entry["glacis_annulus"] = {
                "frames": [_sector_stats(_luma(f), mask) for f in shots[tag]],
                "mask_pixels": int(mask.sum()),
            }
            per = entry["glacis_annulus"]["frames"]
            entry["glacis_annulus"]["worst_sectors_over_2_2"] = max(
                (p.get("sectors_over_2_2", 0) for p in per), default=0
            )
            entry["glacis_annulus"]["mean_ratio_mean"] = round(
                sum(p.get("ratio_mean", 0) for p in per) / max(len(per), 1), 3
            )
        out[tag] = entry
    s.report["farfield_sweep_v2"] = out
    return out


@pytest.mark.beamng_live
def test_g12_farfield(tmp_path: Path) -> None:
    """G12.1 - the deciding number: the glacis annulus at 300 / 150 / 100 m."""

    with _session("G12_1", tmp_path) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]
        sweep = _farfield_sweep_v2(s)
        # Pre-fix baseline, measured offline on the critic's own two 150 m frames:
        # clean boot 4 sectors over 2.2 / mean 1.38; banded boot 8 / 1.77.
        r["pre_fix_baseline_150m"] = {
            "clean_boot_sectors_over_2_2": 4,
            "clean_boot_mean_ratio": 1.38,
            "banded_boot_sectors_over_2_2": 8,
            "banded_boot_mean_ratio": 1.77,
        }
        for tag in ("d300", "d150", "d100"):
            ann = sweep.get(tag, {}).get("glacis_annulus", {})
            if "error" in ann:
                s.problem(f"{tag}: the glacis annulus did not project into frame", ann)
                continue
            s.check(
                ann.get("worst_sectors_over_2_2", 99) <= 5,
                f"{tag}: the glacis annulus is striped (sector count above the clean-boot floor of 4)",
                {k: ann.get(k) for k in ("worst_sectors_over_2_2", "mean_ratio_mean")},
            )
    assert not s.report.get("problems"), s.report["problems"]


# ====================================================================================
# G12 (continued) - the real-time perf number, and ask #7's out-of-bounds fuse
# ====================================================================================


@pytest.mark.beamng_live
def test_g12_realtime_perf(tmp_path: Path) -> None:
    """G12.2 - the honest performance number: full census at REAL TIME, not sped up.

    Every earlier perf window (G6, G7.3) set deterministic 60 Hz and then resumed,
    which free-runs physics: both reported physics_realtime_factor 2.998, i.e.
    ~180 s of simulation inside a 60 s wall window. The frame rate was real but
    the load was not a player's. This gate disables deterministic mode first and
    ASSERTS the realtime factor is ~1.0, so the number cannot silently be a
    sped-up one again. Whatever comes out is the number that ships.
    """

    with _session("G12_2", tmp_path, probe_zip=_probe_zip_bytes(), watchdog_seconds=2400.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]
        loaded = s.lua(
            f"local ok, err = pcall(extensions.load, '{PROBE_ID}/perf'); return jsonEncode({{ok = ok == true, error = tostring(err)}})"
        )
        s.check(loaded.get("ok") is True, "the perf probe extension did not load", loaded)
        roster = s.lua("local all = getAllVehicles(); return jsonEncode({count = #all})")
        s.check(int(roster["count"]) == 23, "the vehicle census is not 23", roster)
        s.set_options(LONG_FUSE)
        s.set_option("ai_enabled", True)
        s.move_away([PLAYER])
        s.start_round(AI[0])
        # REAL TIME: deterministic off, then resume. No speed factor anywhere.
        s.bng.settings.set_nondeterministic()
        s.bng.control.resume()
        time.sleep(5.0)  # ramp: AI plans, shaders warm
        s.lua(f"extensions[{PROBE_EXTENSION!r}].probeReset(); return jsonEncode({{ok = true}})")
        t_start = time.monotonic()
        time.sleep(60.0)
        snap = s.lua(f"return jsonEncode(extensions[{PROBE_EXTENSION!r}].probeSnapshot())")
        wall = time.monotonic() - t_start
        stats = s.stats()
        s.bng.control.pause()
        frames = float(snap["frames"])
        probe_wall = float(snap["wall"])
        factor = (
            (float(snap["simsum"]) / float(snap["realsum"])) if float(snap["realsum"]) > 0 else None
        )
        r["perf_realtime"] = {
            "mode": "non-deterministic (real time)",
            "frames": frames,
            "probe_wall_s": round(probe_wall, 2),
            "python_wall_s": round(wall, 1),
            "avg_fps": round(frames / probe_wall, 1) if probe_wall > 0 else None,
            "worst_frame_ms": round(float(snap["maxdt"]) * 1000.0, 1),
            "floor_fps": round(1.0 / float(snap["maxdt"]), 1) if float(snap["maxdt"]) > 0 else None,
            "frames_over_33ms": snap["over33"],
            "frames_over_67ms": snap["over66"],
            "pct_over_33ms": round(100.0 * float(snap["over33"]) / frames, 2) if frames else None,
            "pct_over_67ms": round(100.0 * float(snap["over66"]) / frames, 2) if frames else None,
            "physics_realtime_factor": round(factor, 3) if factor else None,
            "hist_5ms_buckets": snap.get("hist"),
            "geysers": [(g["name"], g["windows"], g["pops"]) for g in s.arena()["geysers"]],
            "round": {k: stats.get(k) for k in ("phase", "transfers", "field", "props_excluded")},
            "sped_up_comparison": {"G6": 59.6, "G7_3": 60.0, "their_realtime_factor": 2.998},
        }
        s.shot(
            "perf_field",
            (C[0] + 70.0, C[1] + 80.0, C[2] + 45.0),
            (C[0], C[1], C[2] + 2.0),
            "23 vehicles at REAL TIME during the perf window",
        )
        # The measurement must prove it was real time, or it means nothing.
        s.check(
            factor is not None and 0.90 <= factor <= 1.10,
            "the perf window did NOT run at real time - the number is not a player's load",
            {"physics_realtime_factor": factor},
        )
        s.check(frames > 600, "the perf window collected too few frames", r["perf_realtime"])
        # Recorded, not gated: whatever this is, it is the number that ships.
        s.bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
        s.bng.control.pause()
        s.set_option("ai_enabled", False)
    assert not s.report.get("problems"), s.report["problems"]


def _fuse_left(s: Session) -> float:
    """Seconds left on the carrier's fuse, via the HUD countdown.

    LAST.countdown is -1 unless show_countdown is on, tick_style is escalating
    AND the round is live - so FUSE_VISIBLE must be set before any measurement.
    """

    return float(s.stats().get("countdown", -1))


def _live_fuse(s: Session, carrier: str, tries: int = 3) -> dict[str, Any]:
    """Start a round and refuse to proceed until the countdown is actually running."""

    s.set_options(FUSE_VISIBLE)
    seen: list[dict[str, Any]] = []
    for _ in range(tries):
        st = s.stats()
        if st.get("phase") == "live" and _fuse_left(s) >= 0:
            return {"ok": True, "countdown": _fuse_left(s), "carrier": st.get("carrier")}
        if st.get("phase") == "live":
            s.drop_round()
        s.start_round(carrier)
        for _ in range(40):
            st = s.stats()
            if st.get("phase") == "live" and _fuse_left(s) >= 0:
                return {"ok": True, "countdown": _fuse_left(s), "carrier": st.get("carrier")}
            s.step(10)
        seen.append(
            {k: s.stats().get(k) for k in ("phase", "carrier", "countdown", "urgency", "oob")}
        )
    return {
        "ok": False,
        "stats_seen": seen[-2:],
        "options": {
            k: s.options().get(k)
            for k in ("show_countdown", "tick_style", "fuse_base_seconds", "grace_seconds")
        },
        "note": "countdown stayed -1",
    }


@pytest.mark.beamng_live
def test_g12_oob_fuse(tmp_path: Path) -> None:
    """G12.3 - ask #7: the carrier's fuse burns 3x while it is outside the ring.

    Verified in the order that makes the rest meaningful: the boot call FIRST
    (if oob_burn_multiplier is not 3.0, nothing downstream means anything), then
    the burn RATE measured inside vs outside on the same carrier - which is a
    direct measurement of the multiplier rather than an inference from a boom -
    then the boom itself on a bank bearing, then the control: a NON-carrier
    orbiting outside must not be penalised.
    """

    with _session("G12_3", tmp_path, watchdog_seconds=2400.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]
        # --- 1. the boot call, first ---------------------------------------
        options = s.options()
        r["boot_option"] = {"oob_burn_multiplier": options.get("oob_burn_multiplier")}
        armed = s.check(
            float(options.get("oob_burn_multiplier", -1)) == 3.0,
            "the arena's fifth boot call did not land: oob_burn_multiplier is not 3.0 - "
            "nothing else in this gate means anything",
            {
                "options": {
                    k: options.get(k)
                    for k in sorted(options)
                    if "oob" in k or k in sync.BOOT_OPTION_KEYS
                }
            },
        )
        s.set_option("ai_enabled", False)
        for n in AI[1:]:
            s.park(n)
        drv = Driver(s, PLAYER)
        drv.calibrate(_bearing_xy(90.0, 40.0), 0.0)

        def _fuse() -> float:
            return _fuse_left(s)

        def _burn_rate(seconds: float, note: str) -> dict[str, Any]:
            t0, f0 = s.clock(), _fuse()
            samples = [(0.0, f0)]
            oob_seen: list[bool] = []
            phase_seen: set[str] = set()
            while s.clock() - t0 < seconds:
                s.step(30)
                st = s.stats()
                oob_seen.append(st.get("oob") is True)
                phase_seen.add(str(st.get("phase")))
                samples.append((round(s.clock() - t0, 2), float(st.get("countdown", -1))))
            dt = samples[-1][0] - samples[0][0]
            df = samples[0][1] - samples[-1][1]
            return {
                "note": note,
                "seconds": round(dt, 2),
                "fuse_from": round(samples[0][1], 2),
                "fuse_to": round(samples[-1][1], 2),
                "burned": round(df, 2),
                "rate_per_sim_second": round(df / dt, 3) if dt > 0 else None,
                "samples": len(samples),
                "oob_flag_seen": oob_seen,
                "phase_seen": sorted(phase_seen),
            }

        # --- 2. the CARRIER's burn rate, inside vs outside ------------------
        s.set_options(
            {
                "fuse_base_seconds": 120,
                "fuse_sigma_seconds": 0,
                "fuse_min_seconds": 110,
                "fuse_max_seconds": 130,
                **FUSE_VISIBLE,
            }
        )
        live = _live_fuse(s, PLAYER)
        r["fuse_armed"] = live
        s.check(live["ok"], "no fuse was running, so nothing below measures the multiplier", live)
        s.park(PLAYER)
        inside = _burn_rate(10.0, "carrier parked INSIDE the ring (r 40)")
        # Onto the apron past the toe, where G10 showed the free highway.
        s.teleport(PLAYER, _bearing_xy(100.0, 118.0), 100.0, reset=False)
        s.park(PLAYER)
        s.step(30)
        p = s.probe(PLAYER)
        outside = _burn_rate(10.0, f"carrier parked OUTSIDE on the apron (r {p['r']:.1f})")
        ratio = (
            (outside["rate_per_sim_second"] / inside["rate_per_sim_second"])
            if (inside["rate_per_sim_second"] or 0) > 0
            else None
        )
        r["carrier_burn"] = {
            "inside": inside,
            "outside": outside,
            "outside_over_inside": round(ratio, 2) if ratio else None,
            "expected": 3.0,
            "carrier_r_when_outside": round(p["r"], 1),
        }
        s.shot(
            "carrier_outside",
            (*_bearing_xy(100.0, 132.0), C[2] + 10.0),
            (*_bearing_xy(100.0, 112.0), C[2] + 2.0),
            "the carrier parked on the apron past the toe while its fuse burns 3x",
        )
        if armed:
            s.check(
                ratio is not None and 2.5 <= ratio <= 3.5,
                "the carrier's fuse did not burn ~3x faster outside the ring",
                r["carrier_burn"],
            )

        # --- 3. it ends by DETONATION, not a 40 s stalemate -----------------
        boomed = True
        t0 = s.clock()
        try:
            s.step_until(
                lambda: s.stats().get("phase") == "boom",
                calls=200,
                note="the outside carrier never detonated",
            )
        except AssertionError:
            boomed = False
        detonation = {
            "detonated": boomed,
            "sim_seconds_outside_before_boom": round(s.clock() - t0, 1),
            "final_r": round(s.probe(PLAYER)["r"], 1),
            "phase": s.stats().get("phase"),
        }
        r["detonation_outside"] = detonation
        s.check(
            boomed,
            "an orbiting CARRIER farmed the apron without detonating - the stalemate is not closed",
            detonation,
        )
        if boomed:
            s.shot(
                "boom_outside",
                (*_bearing_xy(100.0, 132.0), C[2] + 12.0),
                (*_bearing_xy(100.0, 114.0), C[2] + 3.0),
                "the carrier detonating on the apron - ask #7 ending the stalemate",
            )
        s.step_until(
            lambda: s.stats().get("phase") in ("return", "idle"),
            calls=200,
            note="no return after the outside boom",
        )
        s.step_until(
            lambda: s.stats().get("phase") == "idle", calls=300, note="never settled to idle"
        )

        # --- 4. the control: a NON-carrier outside must be unaffected -------
        s.drop_round()
        s.teleport(PLAYER, _bearing_xy(90.0, 40.0), 90.0)
        s.start_round(AI[0])  # an AI holds the potato, inside
        s.park(AI[0])
        carrier_inside = _burn_rate(8.0, "AI carrier inside, player also inside")
        s.teleport(PLAYER, _bearing_xy(100.0, 118.0), 100.0)  # the PLAYER goes out, not the carrier
        s.park(PLAYER)
        s.step(30)
        carrier_with_other_out = _burn_rate(
            8.0, "AI carrier inside, NON-carrier player outside on the apron"
        )
        rate_a = carrier_inside["rate_per_sim_second"] or 0.0
        rate_b = carrier_with_other_out["rate_per_sim_second"] or 0.0
        r["non_carrier_control"] = {
            "carrier_alone_inside": carrier_inside,
            "with_non_carrier_outside": carrier_with_other_out,
            "ratio": round(rate_b / rate_a, 2) if rate_a > 0 else None,
            "expected": "~1.0 - a non-carrier's excursion must not touch the carrier's fuse",
        }
        if armed:
            s.check(
                rate_a > 0 and 0.8 <= rate_b / rate_a <= 1.25,
                "a NON-carrier outside the ring changed the carrier's burn rate",
                r["non_carrier_control"],
            )
        s.set_option("ai_enabled", True)
    assert not s.report.get("problems"), s.report["problems"]


# ====================================================================================
# G12.4 - the out-of-bounds fuse under the exploit's OWN conditions
#
# G12.3 measures the multiplier cleanly on a PARKED carrier, and its excursion
# clause proves the outcome. Neither proves the mechanism holds in the only state
# the exploit ever occupies: a DRIVEN carrier orbiting a bank bearing on the
# apron at 19-26 m/s, with the containment sweep, the steering loop and the
# magnet all acting on the same car at once. That is where an interaction could
# hide - a rate correct at rest and wrong in motion.
#
# The parked probe stays the clean measurement; this is the confirmation. If the
# two disagree, the DISAGREEMENT is the finding and is reported as one, not
# reconciled into an average.
# ====================================================================================


def _driven_burn(
    s: Session, name: str, bearing: float, seconds: float, ring: str
) -> dict[str, Any]:
    """Drive a tangential circuit and sample the carrier's fuse while doing it."""

    radius = 98.0 if ring == "out" else 60.0
    s.teleport(name, _bearing_xy(bearing, 60.0), bearing, reset=False)
    s.step(45)  # membership: seen INSIDE the ring before anything else
    if ring == "out":
        xy = _bearing_xy(bearing, radius)
        s.teleport(name, xy, (bearing + 90.0) % 360.0, z=s.surface_z(*xy) + 0.6, reset=False)
    else:
        s.teleport(name, _bearing_xy(bearing, radius), (bearing + 90.0) % 360.0, reset=False)
    s.control(name, steering=0.0, throttle=1.0, brake=0.0, parkingbrake=0.0)
    s.vehicle(name).set_velocity(33.0 if ring == "out" else 25.0, 1.0)
    trace: list[dict[str, Any]] = []
    t0 = s.clock()
    while s.clock() - t0 < seconds:
        p = s.probe(name)
        st = s.stats()
        trace.append(
            {
                "t": round(s.clock() - t0, 2),
                "r": round(p["r"], 1),
                "speed": round(p["hspeed"], 1),
                "uz": round(p["uz"], 3),
                "fuse": round(float(st.get("countdown", -1)), 3),
                "oob": st.get("oob") is True,
                "phase": st.get("phase"),
                "carrier": st.get("carrier"),
            }
        )
        if st.get("phase") != "live":
            break
        target = (p["bearing"] + 90.0) % 360.0
        err = math.radians(_wrap_deg(target - p["yaw"]))
        s.control(
            name,
            steering=max(-1, min(1, s.steer_sign * 1.5 * err)),
            throttle=1.0,
            brake=0.0,
            parkingbrake=0.0,
        )
        s.step(3)
    s.control(name, steering=0.0, throttle=0.0, brake=1.0, parkingbrake=0.0)
    s.step(15)

    def _rate(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        rows = [x for x in rows if x["fuse"] >= 0]
        if len(rows) < 8:
            return None
        dt = rows[-1]["t"] - rows[0]["t"]
        df = rows[0]["fuse"] - rows[-1]["fuse"]
        if dt <= 1.0:
            return None
        return {
            "samples": len(rows),
            "seconds": round(dt, 2),
            "burned": round(df, 3),
            "rate_per_sim_second": round(df / dt, 3),
            "speed_min": min(x["speed"] for x in rows),
            "speed_max": max(x["speed"] for x in rows),
            "r_min": min(x["r"] for x in rows),
            "r_max": max(x["r"] for x in rows),
        }

    outside = _rate([x for x in trace if x["r"] > GLACIS_TOE_R])
    inside = _rate([x for x in trace if x["r"] < CREST_R])
    for seg, rows in (
        ("outside", [x for x in trace if x["r"] > GLACIS_TOE_R]),
        ("inside", [x for x in trace if x["r"] < CREST_R]),
    ):
        target = outside if seg == "outside" else inside
        if target is not None:
            target["oob_flag_frac"] = round(sum(1 for x in rows if x["oob"]) / max(len(rows), 1), 2)
    return {
        "bearing": bearing,
        "ring": ring,
        "samples": len(trace),
        "seconds": round(trace[-1]["t"], 1) if trace else 0.0,
        "max_r": max((x["r"] for x in trace), default=0.0),
        "seconds_past_toe": round(sum(1 for x in trace if x["r"] > GLACIS_TOE_R) * 0.05 * 3, 1),
        "still_live": trace[-1]["phase"] if trace else None,
        "outside_segment": outside,
        "inside_segment": inside,
        "trace": trace,
    }


@pytest.mark.beamng_live
def test_g12_oob_fuse_driven(tmp_path: Path) -> None:
    """G12.4 - the multiplier confirmed on a DRIVEN orbiter, the exploit's own state."""

    with _session("G12_4", tmp_path, watchdog_seconds=2400.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]
        options = s.options()
        armed = s.check(
            float(options.get("oob_burn_multiplier", -1)) == 3.0,
            "oob_burn_multiplier is not 3.0 - the driven confirmation means nothing without it",
            {"oob_burn_multiplier": options.get("oob_burn_multiplier")},
        )
        s.set_option("ai_enabled", False)
        for n in AI[1:]:
            s.park(n)
        drv = Driver(s, PLAYER)
        drv.calibrate(_bearing_xy(90.0, 40.0), 0.0)
        # A fuse long enough to survive both circuits, so we measure RATE not a boom.
        s.set_options(
            {
                "fuse_base_seconds": 300,
                "fuse_sigma_seconds": 0,
                "fuse_min_seconds": 280,
                "fuse_max_seconds": 320,
                **FUSE_VISIBLE,
            }
        )
        driven: dict[str, Any] = {}
        # Bank bearings only: the spouts never get a car past the toe (G10.1).
        for bearing in (100.0, 305.0):
            live_in = _live_fuse(s, PLAYER)
            s.check(
                live_in["ok"],
                f"bearing {bearing:.0f}: no fuse running before the inside circuit",
                live_in,
            )
            inside_run = _driven_burn(s, PLAYER, bearing, 12.0, "in")
            live_out = _live_fuse(s, PLAYER)
            s.check(
                live_out["ok"],
                f"bearing {bearing:.0f}: no fuse running before the outside circuit",
                live_out,
            )
            outside_run = _driven_burn(s, PLAYER, bearing, 30.0, "out")
            ins = (inside_run.get("inside_segment") or {}).get("rate_per_sim_second")
            out = (outside_run.get("outside_segment") or {}).get("rate_per_sim_second")
            driven[f"bearing_{int(bearing)}"] = {
                "driven_inside": inside_run.get("inside_segment"),
                "driven_outside": outside_run.get("outside_segment"),
                "outside_over_inside": round(out / ins, 2) if (ins or 0) > 0 and out else None,
                "max_r": outside_run["max_r"],
                "seconds_past_toe": outside_run["seconds_past_toe"],
                "reached_apron": outside_run["max_r"] > GLACIS_TOE_R,
            }
            s.teleport(PLAYER, _bearing_xy(bearing, 40.0), bearing)
        r["driven_burn"] = driven
        s.shot(
            "driven_apron",
            (C[0] + 60.0, C[1] + 60.0, C[2] + 70.0),
            (C[0], C[1], C[2] + 2.0),
            "the driven carrier's orbit on the apron, where the fuse must burn 3x",
        )
        ratios = [v["outside_over_inside"] for v in driven.values() if v.get("outside_over_inside")]
        reached = [v for v in driven.values() if v["reached_apron"]]
        r["driven_summary"] = {
            "bearings_reaching_apron": len(reached),
            "ratios": ratios,
            "speed_band_outside": [
                (v["driven_outside"]["speed_min"], v["driven_outside"]["speed_max"])
                for v in driven.values()
                if v.get("driven_outside")
            ],
            "g10_exploit_band_for_comparison": [19.3, 26.4],
        }
        s.check(
            len(reached) >= 1,
            "no driven excursion reached the apron - the exploit state was never entered",
            driven,
        )
        if armed and ratios:
            s.check(
                all(2.5 <= x <= 3.5 for x in ratios),
                "the DRIVEN carrier's fuse did not burn ~3x on the apron - the multiplier does not hold "
                "under the exploit's own conditions (sweep + steering + magnet acting together)",
                {"ratios": ratios, "driven": driven},
            )
        s.set_option("ai_enabled", True)
    assert not s.report.get("problems"), s.report["problems"]


# ====================================================================================
# G12.5 - D-8 on serial 54: the reflex re-armed on body extents
#
# G11 proved the v2.12 reflex NEVER RAN: my envelope counter read zero while a
# car ground against a post for 56 s. v2.14 re-expresses the envelope in the two
# quantities that define the encounter - the post's authored keep-out and the
# car's cached extents - as gap = |car - post| - post.r - car_reach, armed under
# 0.5 m.
#
# THE NUMBER THIS GATE LEADS ON is the envelope counter. If it is zero again,
# the arming geometry is still not what anyone thinks it is, and no contact count
# means anything. So this pass computes the runtime's OWN formula from outside,
# using the authored r_keepout from the handoff and each car's half extents read
# from the same OOBB the mod caches, and logs the actual gap per event - so a
# second failure is diagnostic rather than merely negative.
# ====================================================================================

STUCK_MARGIN_M = 0.5  # v26.DODGE_STUCK_MARGIN
STUCK_SPEED_MPS = 3.0  # v26.DODGE_STUCK_SPEED
STUCK_SECONDS = 1.5  # v26.DODGE_STUCK_SECONDS


def _keepout_posts() -> list[dict[str, Any]]:
    """The posts the runtime registers, with their authored keep-out radii."""

    return [
        {"name": o["name"], "x": float(o["x"]), "y": float(o["y"]), "r": float(o["r_keepout"])}
        for o in HANDOFF["obstacles"]
    ]


def _extent_gap(posts, x: float, y: float, reach: float) -> tuple[str, float]:
    """The runtime's own formula: |car - post| - post.r - car_reach."""

    best_name, best_gap = "", 1e9
    for p in posts:
        gap = math.hypot(x - p["x"], y - p["y"]) - p["r"] - reach
        if gap < best_gap:
            best_name, best_gap = p["name"], gap
    return best_name, best_gap


@pytest.mark.beamng_live
def test_g12_pin_reflex(tmp_path: Path) -> None:
    """G12.5 - D-8: the envelope must ARM (non-zero), and the grind must end."""

    with _session("G12_5", tmp_path, watchdog_seconds=2400.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]
        posts = _keepout_posts()
        r["keepout_posts"] = {"count": len(posts), "radii": sorted({p["r"] for p in posts})}
        # The same OOBB the mod caches, read once per car.
        raw = s.lua(
            "local out = {}; for _, v in ipairs(getAllVehicles()) do "
            "local ok, o = pcall(function() return v:getSpawnWorldOOBB() end); "
            "if ok and o then local h = o:getHalfExtents(); "
            "out[v:getName()] = {hx = h.x, hy = h.y, hz = h.z} end end; return jsonEncode(out)"
        )
        reach = {
            n: math.sqrt(float(v["hx"]) ** 2 + float(v["hy"]) ** 2)
            for n, v in raw.items()
            if n in AI
        }
        r["car_reach_m"] = {n.rsplit("_", 1)[-1]: round(v, 2) for n, v in sorted(reach.items())}
        s.check(
            len(reach) == len(AI),
            "could not read spawn extents for every AI car",
            {"read": sorted(reach)},
        )
        props = [
            n
            for n in [e["name"] for e in sync.vehicle_layout(HANDOFF)]
            if n not in (PLAYER, DISPENSER) and n not in AI
        ]
        s.move_away([PLAYER])
        s.set_options(LONG_FUSE)
        s.set_option("ai_enabled", True)
        s.start_round(AI[0])
        hits: list[dict[str, Any]] = []
        last_damage: dict[str, float] = {}
        envelope: list[dict[str, Any]] = []
        gap_min: dict[str, float] = {}
        streak: dict[str, float] = {}
        armed_spans: list[dict[str, Any]] = []
        t0 = s.clock()
        samples = 0
        while s.clock() - t0 < 180.0:
            t = s.clock() - t0
            rows = _census_tick(s, AI + props, last_damage, hits, t)
            for n in AI:
                row = rows[n]
                if not row.get("ok"):
                    continue
                name, gap = _extent_gap(posts, row["x"], row["y"], reach.get(n, 2.5))
                key = f"{n.rsplit('_', 1)[-1]}::{name}"
                gap_min[key] = min(gap_min.get(key, 1e9), gap)
                in_envelope = gap < STUCK_MARGIN_M and row["hspeed"] <= STUCK_SPEED_MPS
                if in_envelope:
                    envelope.append(
                        {
                            "t": round(t, 1),
                            "car": n.rsplit("_", 1)[-1],
                            "post": name,
                            "gap": round(gap, 3),
                            "speed": round(row["hspeed"], 2),
                        }
                    )
                    streak[n] = streak.get(n, 0.0) + 0.1
                    if streak[n] >= STUCK_SECONDS and (
                        not armed_spans
                        or armed_spans[-1].get("car") != n
                        or t - armed_spans[-1]["t_end"] > 1.0
                    ):
                        armed_spans.append(
                            {
                                "car": n.rsplit("_", 1)[-1],
                                "post": name,
                                "t": round(t, 1),
                                "t_end": round(t, 1),
                                "gap": round(gap, 3),
                            }
                        )
                    elif armed_spans and armed_spans[-1].get("car") == n.rsplit("_", 1)[-1]:
                        armed_spans[-1]["t_end"] = round(t, 1)
                else:
                    streak[n] = 0.0
            samples += 1
            if samples % 100 == 0 and s.stats().get("phase") != "live":
                s.start_round(AI[0])
            s.step(STEP_TICK)
        chase = s.stats()
        solid_hits = [h for h in hits if h["kind"] == "solid" and h["car"] in AI]
        for h in solid_hits:
            h["solid_class"] = _solid_class(h["solid"])
        events = _group_contacts(solid_hits)
        for e in events:
            car_reach = next((v for k, v in reach.items() if k.rsplit("_", 1)[-1] == e["car"]), 2.5)
            _, g = _extent_gap(posts, e["x"], e["y"], car_reach)
            e["extent_gap_at_contact"] = round(g, 3)
        character = _contact_character(events)
        by_class: dict[str, list[dict[str, Any]]] = {}
        for e in events:
            by_class.setdefault(e["solid_class"], []).append(e)
        r["envelope"] = {
            "samples_in_envelope": len(envelope),
            "armed_spans": armed_spans,
            "arming_threshold": {
                "gap_under_m": STUCK_MARGIN_M,
                "speed_at_or_under_mps": STUCK_SPEED_MPS,
                "sustained_seconds": STUCK_SECONDS,
            },
            "first_10": envelope[:10],
            "min_gap_by_car_and_post": {
                k: round(v, 2) for k, v in sorted(gap_min.items(), key=lambda kv: kv[1])[:10]
            },
            "note": "computed OUTSIDE the mod with the runtime's own formula "
            "(gap = |car-post| - post.r - car_reach) from the authored r_keepout",
        }
        r["chase"] = {
            "sim_seconds": round(s.clock() - t0, 1),
            "samples": samples,
            "transfers": chase.get("transfers"),
            "field": chase.get("field"),
            "contact_events_total": len(events),
            "contact_events_by_class": {k: len(v) for k, v in sorted(by_class.items())},
            "events": events,
        }
        r["contact_character"] = character
        s.shot(
            "chase_field",
            (C[0] + 70.0, C[1] + 80.0, C[2] + 45.0),
            (C[0], C[1], C[2] + 2.0),
            "the field after three minutes on serial 54",
        )
        # LEAD METRIC: the reflex must actually arm.
        s.check(
            len(envelope) > 0,
            "THE ENVELOPE STILL NEVER ARMED - zero samples inside the arming geometry, so the "
            "reflex cannot have run and no contact count below means anything. Per-event gaps are "
            "logged for diagnosis rather than another constant being adjusted.",
            {
                "samples_in_envelope": 0,
                "closest_gaps": r["envelope"]["min_gap_by_car_and_post"],
                "contact_gaps": [
                    (e["car"], e["solid"], e["extent_gap_at_contact"]) for e in events
                ],
            },
        )
        s.check(
            len(events) <= 2,
            "more than two obstacle contact events in three minutes",
            {"total": len(events), "by_class": r["chase"]["contact_events_by_class"]},
        )
        s.check(
            character["shape_counts"].get("fixed_position_grinding", 0) == 0,
            "a car is STILL grinding at a fixed position - armed but unable to move the car points "
            "at geometry, not at the reflex",
            {
                k: v
                for k, v in character["by_pair"].items()
                if v["shape"] == "fixed_position_grinding"
            },
        )
        s.check(
            character["shape_counts"].get("pinned_by_car_cycle", 0) == 0,
            "a car pinned BY ANOTHER CAR is re-triggering on the 6 s time-box",
            {k: v for k, v in character["by_pair"].items() if v["shape"] == "pinned_by_car_cycle"},
        )
        s.set_option("ai_enabled", False)
    assert not s.report.get("problems"), s.report["problems"]


@pytest.mark.beamng_live
def test_g12_oob_boundary(tmp_path: Path) -> None:
    """Decisive: is the driven carrier actually the carrier, and where is the OOB line?

    The driven orbiter at r 113-115 was never flagged out of bounds while a
    PARKED car at r 118 was, in sessions where hotPotatoGetOptions() reported
    oob_burn_multiplier 3. Before that is reported as a runtime defect, two
    much likelier explanations of MY OWN making have to die first:
      (a) the car I drove was not the carrier, so I measured someone else's fuse;
      (b) my r (from the gates' arena centre) is not the runtime's arena
          distance (from B.pad_center), so "r 115" may be inside the ring.
    So this logs, per sample: my r, the carrier id, the driven car's id, the
    oob flag, and the runtime's OWN v26.arenaDistance for the carrier.
    """

    with _session("G12_B", tmp_path, watchdog_seconds=1200.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]
        r["options"] = {
            k: s.options().get(k)
            for k in (
                "oob_burn_multiplier",
                "arena_radius_m",
                "arena_enabled",
                "show_countdown",
                "tick_style",
            )
        }
        pad = s.runtime_state()["origin"]
        r["pad_center"] = [round(float(x), 3) for x in pad]
        r["gate_centre_C"] = [round(x, 3) for x in C]
        r["pad_vs_C_offset_m"] = round(math.hypot(float(pad[0]) - C[0], float(pad[1]) - C[1]), 3)
        s.set_options({**LONG_FUSE, **FUSE_VISIBLE})
        s.set_option("ai_enabled", False)
        for n in AI[1:]:
            s.park(n)
        drv = Driver(s, PLAYER)
        drv.calibrate(_bearing_xy(90.0, 40.0), 0.0)
        player_id = int(s.probe(PLAYER)["id"])
        r["player_id"] = player_id
        live = _live_fuse(s, PLAYER)
        r["live"] = live

        def row(label: str) -> dict[str, Any]:
            p = s.probe(PLAYER)
            st = s.stats()
            return {
                "stage": label,
                "my_r": round(p["r"], 1),
                "x": round(p["x"], 1),
                "y": round(p["y"], 1),
                "carrier": st.get("carrier"),
                "player_id": player_id,
                "player_is_carrier": int(st.get("carrier") or -1) == player_id,
                "countdown": st.get("countdown"),
                "oob": st.get("oob"),
                "phase": st.get("phase"),
                "dist_from_pad": round(
                    math.hypot(p["x"] - float(pad[0]), p["y"] - float(pad[1])), 1
                ),
            }

        rows = [row("start, inside")]
        # Walk the carrier outward WITHOUT a reset, sampling the flag as r grows.
        for radius in (60.0, 85.0, 95.0, 105.0, 112.0, 115.0, 118.0, 125.0, 140.0):
            xy = _bearing_xy(305.0, radius)
            s.teleport(PLAYER, xy, 35.0, z=s.surface_z(*xy) + 0.6, reset=False)
            s.park(PLAYER)
            for _ in range(8):
                s.step(15)
            rows.append(row(f"bearing 305, r {radius:.0f}"))
        for radius in (112.0, 115.0, 118.0):
            xy = _bearing_xy(100.0, radius)
            s.teleport(PLAYER, xy, 190.0, z=s.surface_z(*xy) + 0.6, reset=False)
            s.park(PLAYER)
            for _ in range(8):
                s.step(15)
            rows.append(row(f"bearing 100, r {radius:.0f}"))
        r["rows"] = rows
        flagged = [x for x in rows if x["oob"] is True]
        r["summary"] = {
            "player_was_carrier_throughout": all(x["player_is_carrier"] for x in rows),
            "first_r_flagged_oob": min([x["my_r"] for x in flagged], default=None),
            "largest_r_NOT_flagged": max(
                [x["my_r"] for x in rows if x["oob"] is not True], default=None
            ),
            "pad_vs_C_offset_m": r["pad_vs_C_offset_m"],
            "arena_radius_m": r["options"]["arena_radius_m"],
        }
    assert not s.report.get("problems"), s.report["problems"]


# ====================================================================================
# G13 - the two fixes on serial 55 + geometry v3.5, and the minimal regression
#
# G13.1 the out-of-bounds fuse, READ rather than inferred.
#   G12 measured 1.71x parked and 1.00x driven and could not reconcile them. The
#   runtime then proved from its own lines that the arithmetic cannot produce a
#   value strictly between 1 and `burn`: advanceClock sets b.now += delta AND
#   b.lastDelta = delta from the same value on consecutive lines (spec.py
#   L1063-1064) and the penalty subtracts (burn - 1) * b.lastDelta (L4392), so
#   d(remaining) = burn * delta exactly. A between-value therefore means frames
#   passed in MY wall clock where the penalty line never ran - the round was not
#   live, or advanceClock zeroed its delta (L1060 discards a wall gap over 0.5 s,
#   L1062 skips dtSim == 0). Both are properties of the measurement, not the mod.
#
#   So this gate does not infer a rate from countdown deltas at all. Serial 55
#   publishes `fuse_burn` and `clock_delta` in behavior_stats precisely so the
#   value can be READ, and the assertion is a PER-SAMPLE contract that no clock
#   stall can dilute:
#       for every live sample:  oob == (arena_distance > arena_radius_m)
#                               fuse_burn == 3.0 if oob else 1.0
#   fuse_remaining comes from behavior_stats too - hotPotatoGetStats() has NO
#   such field, and its `countdown` is -1 unless show_countdown AND escalating
#   (the G12 harness fault that cost four boots).
#
#   The carrier is NEVER teleported with reset=True inside a measured round:
#   that is the carrier-lost signal drop_round() itself uses.
#
# G13.2 D-8 with the measured physical radius rp.
#   G11: the envelope never armed (0 samples; the trigger was measured from the
#   car's reference point at 1.5 m while the body was already inside). Serial 54
#   armed it (4,093 samples) but contacts went 17 -> 51 because the arming disc
#   was bound to the AUTHORED keep-out (6.5 / 8.0 m), a flat 9.4 m around all 42
#   points. Serial 55 + geometry v3.5 bind it to a measured physical radius rp
#   (posts 1.2 / 1.5 / 2.121 m; 24 of 42 points sit ON the surface and carry the
#   contract's 0.1 m floor; batter 2.321 / 1.2), so the disc is ~3.7-4.6 m.
#   Steering still uses r; only the pin reflex uses rp.
#
#   BOTH must hold: contacts back below the 17 baseline AND the envelope still
#   arming. A count alone cannot tell "fixed" from "switched off".
#
# G13.3 the minimal regression: one full round (field 6, props_excluded 16,
#   pickup -> ram transfer -> boom -> return -> fireworks). D-7's stochastic ram
#   roll, the orbit counts and the far-field are known-open and untouched by
#   these two fixes, and are deliberately NOT re-measured here.
# ====================================================================================

OOB_MULTIPLIER = 3.0
# The geometry's measured model, as the runtime must echo it back (v3.5 A24).
RP_POST_CLASSES = {1.2: "masher", 1.5: "grinder", 2.121: "geyser tower"}
# rp census over the 42 registered points: 24 surface points at the contract's
# 0.1 m floor, 8 at 1.2 (4 mashers + 4 jamb-outer batter), 4 grinders, 2 towers,
# 4 jamb-mid batter.
RP_CENSUS = {0.1: 24, 1.2: 8, 1.5: 4, 2.121: 2, 2.321: 4}
FINE_SOLID_CLASSES = (
    ("pillar_tower", ("masher_", "grinder_", "geyser_tower")),
    ("ramp_flank", ("ramp_e_inner_flank", "ramp_w_inner_flank")),
    ("handle_flank", ("handle_flank",)),
    ("handle_nose", ("handle_nose",)),
    ("jamb", ("jamb_",)),
)


def _fine_class(name: str) -> str:
    """The flank split the segment-primitive decision hangs on, unambiguous.

    _solid_class lumps handle_flank and handle_nose into one 'handle' bucket;
    the design question is specifically about the 16 `face` points (handle
    flanks and ramp flanks), so those get their own labels here.
    """

    for label, prefixes in FINE_SOLID_CLASSES:
        if any(name.startswith(p) for p in prefixes):
            return label
    return "other"


def _fuse_row(s: Session, name: str, t: float, window: str) -> dict[str, Any]:
    """One sample: the runtime's OWN published fuse numbers beside my own pose.

    behavior_stats is state.behavior.stats verbatim, so fuse_remaining,
    fuse_burn, clock_delta and oob all come from the same frame the mod
    computed them on; behavior_phase is b.phase itself rather than the HUD
    mirror. arena_distance is measured from the runtime's own pad origin, the
    quantity v26.arenaDistance uses - not from the gates' arena centre.
    """

    st = s.runtime_state()
    bs = dict(st.get("behavior_stats") or {})
    origin = st.get("origin") or [C[0], C[1], C[2]]
    p = s.probe(name)
    return {
        "t": round(t, 2),
        "window": window,
        "phase": st.get("behavior_phase"),
        "carrier": int(bs.get("carrier", -1) or -1),
        "is_carrier": int(bs.get("carrier", -1) or -1) == int(p["id"]),
        "fuse_remaining": round(float(bs.get("fuse_remaining", -1)), 3),
        "fuse_burn": round(float(bs.get("fuse_burn", -1)), 3),
        "clock_delta": round(float(bs.get("clock_delta", -1)), 4),
        "oob": bs.get("oob") is True,
        "r": round(p["r"], 1),
        "arena_distance": round(
            math.hypot(p["x"] - float(origin[0]), p["y"] - float(origin[1])), 1
        ),
        "speed": round(p["hspeed"], 1),
        "uz": round(p["uz"], 3),
        "bearing": round(p["bearing"], 1),
        "yaw": round(p["yaw"], 1),
    }


def _fuse_verdict(rows: list[dict[str, Any]], radius: float, band: float = 1.5) -> dict[str, Any]:
    """The per-sample contract, immune to any clock stall in MY loop."""

    live = [x for x in rows if x["phase"] == "live"]
    inside = [x for x in live if x["arena_distance"] <= radius - band]
    outside = [x for x in live if x["arena_distance"] >= radius + band]
    bad_flag = [x for x in live if x["oob"] != (x["arena_distance"] > radius)]
    bad_burn = [
        x for x in live if abs(x["fuse_burn"] - (OOB_MULTIPLIER if x["oob"] else 1.0)) > 1e-6
    ]
    stalled = [x for x in live if x["clock_delta"] == 0.0]
    return {
        "samples": len(rows),
        "live_samples": len(live),
        "not_live_samples": len(rows) - len(live),
        "inside_samples": len(inside),
        "outside_samples": len(outside),
        "burn_inside": sorted({x["fuse_burn"] for x in inside}),
        "burn_outside": sorted({x["fuse_burn"] for x in outside}),
        "oob_inside": sorted({x["oob"] for x in inside}),
        "oob_outside": sorted({x["oob"] for x in outside}),
        "flag_disagrees_with_distance": len(bad_flag),
        "burn_disagrees_with_flag": len(bad_burn),
        "first_flag_disagreement": bad_flag[:3],
        "first_burn_disagreement": bad_burn[:3],
        "clock_stalled_samples": len(stalled),
        "clock_stalled_fraction": round(len(stalled) / max(len(live), 1), 3),
        "carrier_held_throughout": all(x["is_carrier"] for x in live),
        "band_ignored_m": band,
        "note": "band excludes samples within +-band of the ring so a crossing "
        "frame is never counted against either side",
    }


def _g13_orbit(
    s: Session,
    name: str,
    bearing: float,
    seconds: float,
    rows: list[dict[str, Any]],
    t0: float,
    window: str,
    radius: float = 98.0,
    inject: float = 33.0,
    stop_on_boom: bool = False,
) -> dict[str, Any]:
    """Drive a tangential circuit on a BANK bearing, sampling the fuse per tick.

    Bank bearings only: G10.1 measured that a car leaving over a SPOUT never
    gets past the toe and is hauled home in ~6 s, while a bank bearing settles
    on the runoff apron at 19-26 m/s for 25+ s. The apron is the exploit, so it
    is the only place the fuse has to be proven in motion. The carrier is placed
    with reset=False throughout - a reset IS drop_round's carrier-lost signal.
    """

    xy = _bearing_xy(bearing, radius)
    s.teleport(name, xy, (bearing + 90.0) % 360.0, z=s.surface_z(*xy) + 0.6, reset=False)
    s.control(name, steering=0.0, throttle=1.0, brake=0.0, parkingbrake=0.0)
    s.vehicle(name).set_velocity(inject, 1.0)
    start = s.clock()
    boomed = False
    mine: list[dict[str, Any]] = []
    budget = seconds * 3.0 if stop_on_boom else seconds
    while s.clock() - start < budget:
        row = _fuse_row(s, name, s.clock() - t0, window)
        rows.append(row)
        mine.append(row)
        if row["phase"] == "boom":
            boomed = True
            break
        if row["phase"] != "live":
            break
        if not stop_on_boom and s.clock() - start >= seconds:
            break
        target = (row["bearing"] + 90.0) % 360.0
        err = math.radians(_wrap_deg(target - row["yaw"]))
        s.control(
            name,
            steering=max(-1.0, min(1.0, s.steer_sign * 1.5 * err)),
            throttle=1.0,
            brake=0.0,
            parkingbrake=0.0,
        )
        s.step(3)
    s.control(name, steering=0.0, throttle=0.0, brake=1.0, parkingbrake=0.0)
    s.step(10)
    outside = [x for x in mine if x["oob"]]
    fast = [x for x in mine if 19.0 <= x["speed"] <= 26.5]
    return {
        "bearing": bearing,
        "samples": len(mine),
        "sim_seconds": round(s.clock() - start, 1),
        "max_r": max((x["r"] for x in mine), default=0.0),
        "max_arena_distance": max((x["arena_distance"] for x in mine), default=0.0),
        "speed_band": [
            min((x["speed"] for x in mine), default=0.0),
            max((x["speed"] for x in mine), default=0.0),
        ],
        "samples_in_g10_exploit_band_19_26": len(fast),
        "samples_flagged_oob": len(outside),
        "burn_while_flagged": sorted({x["fuse_burn"] for x in outside}),
        "reached_apron": max((x["r"] for x in mine), default=0.0) > GLACIS_TOE_R,
        "boomed": boomed,
        "final_phase": mine[-1]["phase"] if mine else None,
        "fuse_first_last": [mine[0]["fuse_remaining"], mine[-1]["fuse_remaining"]]
        if mine
        else None,
    }


@pytest.mark.beamng_live
def test_g13_oob_fuse(tmp_path: Path) -> None:
    """G13.1 - the out-of-bounds fuse: fuse_burn READ, not inferred from a countdown."""

    with _session("G13_1", tmp_path, watchdog_seconds=3000.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]
        # --- 1. the boot call FIRST -----------------------------------------
        options = s.options()
        radius = float(options.get("arena_radius_m", R_ARENA))
        r["boot_option"] = {
            "oob_burn_multiplier": options.get("oob_burn_multiplier"),
            "arena_radius_m": radius,
            "arena_enabled": options.get("arena_enabled"),
            # camp burn shares the same max(): if it were on, a PARKED carrier's
            # 1.0 baseline would not be 1.0 and nothing below would separate.
            "camp_burn_multiplier": options.get("camp_burn_multiplier"),
        }
        armed = s.check(
            float(options.get("oob_burn_multiplier", -1)) == OOB_MULTIPLIER,
            "the arena's boot call did not land: oob_burn_multiplier is not 3.0 - "
            "nothing else in this gate means anything",
            r["boot_option"],
        )
        s.check(
            float(options.get("camp_burn_multiplier", -1)) == 1.0,
            "camp_burn_multiplier is not 1.0, so a parked carrier's baseline is not the "
            "out-of-bounds multiplier's alone",
            r["boot_option"],
        )
        s.set_option("ai_enabled", False)
        for n in AI:
            s.park(n)
        drv = Driver(s, PLAYER)
        drv.calibrate(_bearing_xy(90.0, 40.0), 0.0)

        # --- 2. ONE round, three windows, no reset teleport ------------------
        # A fuse long enough that the rate windows never race a boom.
        s.set_options(
            {
                "fuse_base_seconds": 300,
                "fuse_sigma_seconds": 0,
                "fuse_min_seconds": 280,
                "fuse_max_seconds": 320,
            }
        )
        s.drop_round()
        start_stats = s.start_round(PLAYER)
        r["round_start"] = {
            "carrier": start_stats.get("carrier"),
            "field": start_stats.get("field"),
        }
        rows: list[dict[str, Any]] = []
        t0 = s.clock()

        def _park_window(
            bearing: float, at_r: float, seconds: float, window: str
        ) -> dict[str, Any]:
            if at_r > 0:
                xy = _bearing_xy(bearing, at_r)
                s.teleport(PLAYER, xy, bearing, z=s.surface_z(*xy) + 0.6, reset=False)
            s.park(PLAYER)
            begin = s.clock()
            mine: list[dict[str, Any]] = []
            while s.clock() - begin < seconds:
                row = _fuse_row(s, PLAYER, s.clock() - t0, window)
                rows.append(row)
                mine.append(row)
                if row["phase"] != "live":
                    break
                s.step(15)
            return {
                "window": window,
                "samples": len(mine),
                "arena_distance_range": [
                    min((x["arena_distance"] for x in mine), default=0.0),
                    max((x["arena_distance"] for x in mine), default=0.0),
                ],
                "burns": sorted({x["fuse_burn"] for x in mine}),
                "oob": sorted({x["oob"] for x in mine}),
                "phases": sorted({str(x["phase"]) for x in mine}),
            }

        parked_inside = _park_window(90.0, 40.0, 12.0, "parked INSIDE r 40")
        parked_outside = _park_window(100.0, 118.0, 12.0, "parked OUTSIDE r 118")
        s.shot(
            "carrier_outside",
            (*_bearing_xy(100.0, 134.0), C[2] + 11.0),
            (*_bearing_xy(100.0, 112.0), C[2] + 2.0),
            "the carrier parked on the apron past the toe while its fuse burns",
        )
        # Two driven windows on the same bank bearing. The FIRST is the G10
        # exploit state reproduced deliberately - r 110 at ~23 m/s, the band
        # (19.3-26.4) in which a powered car held the apron for 25+ s and was
        # never recovered. The SECOND is the escape speed G12 happened to use
        # (injected 33 m/s), which runs straight out past r 130 rather than
        # orbiting; it is kept because "outside" must hold there too.
        driven = _g13_orbit(
            s,
            PLAYER,
            305.0,
            25.0,
            rows,
            t0,
            "driven OUTSIDE bearing 305, G10 exploit band",
            radius=110.0,
            inject=23.0,
        )
        driven_fast = _g13_orbit(
            s,
            PLAYER,
            305.0,
            12.0,
            rows,
            t0,
            "driven OUTSIDE bearing 305, escape speed",
            radius=98.0,
            inject=33.0,
        )
        r["windows"] = {
            "parked_inside": parked_inside,
            "parked_outside": parked_outside,
            "driven_exploit_band": driven,
            "driven_escape_speed": driven_fast,
        }
        r["fuse_rows"] = rows
        verdict = _fuse_verdict(rows, radius)
        r["fuse_verdict"] = verdict
        s.shot(
            "driven_apron",
            (C[0] + 55.0, C[1] + 55.0, C[2] + 70.0),
            (C[0], C[1], C[2] + 2.0),
            "the driven carrier's circuit on the apron, where the fuse must burn 3x",
        )

        if armed:
            s.check(
                verdict["burn_inside"] == [1.0],
                "the carrier's published fuse_burn was not 1.0 everywhere inside the ring",
                {
                    "burn_inside": verdict["burn_inside"],
                    "inside_samples": verdict["inside_samples"],
                },
            )
            s.check(
                verdict["burn_outside"] == [OOB_MULTIPLIER],
                "the carrier's published fuse_burn was not 3.0 everywhere outside the ring",
                {
                    "burn_outside": verdict["burn_outside"],
                    "outside_samples": verdict["outside_samples"],
                },
            )
            s.check(
                verdict["flag_disagrees_with_distance"] == 0,
                "the oob flag disagreed with the carrier's own arena distance",
                verdict["first_flag_disagreement"],
            )
            s.check(
                verdict["burn_disagrees_with_flag"] == 0,
                "the published fuse_burn disagreed with the oob flag on the same frame",
                verdict["first_burn_disagreement"],
            )
        s.check(
            verdict["inside_samples"] >= 10 and verdict["outside_samples"] >= 10,
            "not enough samples on one side of the ring to say anything",
            verdict,
        )
        s.check(
            verdict["not_live_samples"] == 0,
            "the round left `live` during a measurement window - that is a HARNESS fault "
            "(a reset teleport of the carrier is drop_round's own carrier-lost signal), "
            "and every burn number in this boot is void until it is fixed",
            {
                "not_live": verdict["not_live_samples"],
                "phases": sorted({str(x["phase"]) for x in rows}),
            },
        )
        s.check(
            verdict["carrier_held_throughout"],
            "the player stopped being the carrier mid-measurement",
            verdict,
        )
        s.check(
            driven["reached_apron"] and driven["samples_in_g10_exploit_band_19_26"] >= 20,
            "the driven circuit never held the G10 exploit state (apron, 19-26 m/s), so "
            "the multiplier was not tested where the exploit lives",
            driven,
        )

        # --- 3. an orbiting carrier must END BY DETONATION -------------------
        s.drop_round()
        s.set_options(
            {
                "fuse_base_seconds": 60,
                "fuse_sigma_seconds": 0,
                "fuse_min_seconds": 55,
                "fuse_max_seconds": 65,
            }
        )
        s.start_round(PLAYER)
        boom_rows: list[dict[str, Any]] = []
        tb = s.clock()
        detonation = _g13_orbit(
            s, PLAYER, 305.0, 40.0, boom_rows, tb, "detonation orbit bearing 305", stop_on_boom=True
        )
        last_live = [x for x in boom_rows if x["phase"] == "live"]
        detonation["outside_at_last_live_sample"] = last_live[-1]["oob"] if last_live else None
        detonation["arena_distance_at_last_live_sample"] = (
            last_live[-1]["arena_distance"] if last_live else None
        )
        detonation["sim_seconds_of_orbit"] = round(s.clock() - tb, 1)
        r["detonation_orbit"] = detonation
        r["detonation_rows"] = boom_rows
        s.check(
            detonation["boomed"],
            "an orbiting CARRIER on a bank bearing farmed the apron without detonating - "
            "the stalemate ask #7 exists to close is not closed",
            detonation,
        )
        if detonation["boomed"]:
            s.shot(
                "boom_outside",
                (*_bearing_xy(305.0, 134.0), C[2] + 12.0),
                (*_bearing_xy(305.0, 112.0), C[2] + 3.0),
                "the orbiting carrier detonating on the apron",
            )
        s.set_option("ai_enabled", True)
    assert not s.report.get("problems"), s.report["problems"]


@pytest.mark.beamng_live
def test_g13_pin_reflex(tmp_path: Path) -> None:
    """G13.2 - D-8 with the measured rp: contacts down AND the envelope still arming."""

    with _session("G13_2", tmp_path, watchdog_seconds=3000.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]

        # --- what actually LANDED in the registry ---------------------------
        hook = s.lua(f"return jsonEncode(extensions[{RUNTIME!r}].hotPotatoGetObstacles())")
        entries = [dict(e) for e in hook.get("entries", [])]
        by_xy = {
            (round(float(o["x"]), 3), round(float(o["y"]), 3)): o for o in HANDOFF["obstacles"]
        }
        matched, mismatched = 0, []
        for e in entries:
            key = (round(float(e["x"]), 3), round(float(e["y"]), 3))
            row = by_xy.get(key)
            if row is None:
                mismatched.append({"echo": e, "why": "no handoff obstacle at this position"})
                continue
            if (
                abs(float(e["rp"]) - float(row["rp"])) > 1e-6
                or abs(float(e["r"]) - float(row["r_keepout"])) > 1e-6
            ):
                mismatched.append({"echo": e, "handoff": row})
            else:
                matched += 1
        census: dict[float, int] = {}
        for e in entries:
            census[round(float(e["rp"]), 3)] = census.get(round(float(e["rp"]), 3), 0) + 1
        rp_over_r = [e for e in entries if float(e["rp"]) > float(e["r"])]
        r["obstacle_echo"] = {
            "count": int(hook.get("count", -1)),
            "matched_to_handoff": matched,
            "mismatched": mismatched[:5],
            "rp_census": {str(k): v for k, v in sorted(census.items())},
            "rp_census_expected": {str(k): v for k, v in sorted(RP_CENSUS.items())},
            "entries_with_rp_over_r": len(rp_over_r),
            "post_classes": {RP_POST_CLASSES[k]: census.get(k, 0) for k in RP_POST_CLASSES},
        }
        s.check(
            int(hook.get("count", -1)) == 42,
            "hotPotatoGetObstacles did not echo 42 entries",
            r["obstacle_echo"],
        )
        s.check(
            not rp_over_r,
            "an echoed obstacle has rp > r, which the contract forbids",
            rp_over_r[:5],
        )
        s.check(
            matched == len(entries) and not mismatched,
            "an echoed obstacle's r/rp does not match the geometry handoff",
            r["obstacle_echo"],
        )
        s.check(
            census == {round(k, 3): v for k, v in RP_CENSUS.items()},
            "the echoed rp census is not the geometry's measured model",
            r["obstacle_echo"],
        )
        for value, label in RP_POST_CLASSES.items():
            s.check(
                census.get(value, 0) == RP_CENSUS[value],
                f"the {label} class did not land at rp {value}",
                r["obstacle_echo"],
            )

        # The reflex's arming disc, reconstructed from the ECHOED registry (the
        # ground truth of what the mod is using) with the runtime's own formula
        # gap = |car - post| - post.rp - car_reach.
        posts = [
            {
                "name": (by_xy.get((round(float(e["x"]), 3), round(float(e["y"]), 3))) or {}).get(
                    "name", "?"
                ),
                "x": float(e["x"]),
                "y": float(e["y"]),
                "r": float(e["r"]),
                "rp": float(e["rp"]),
            }
            for e in entries
        ]

        def _rp_gap(x: float, y: float, reach: float) -> tuple[str, float]:
            best_name, best_gap = "", 1e9
            for p in posts:
                gap = math.hypot(x - p["x"], y - p["y"]) - p["rp"] - reach
                if gap < best_gap:
                    best_name, best_gap = p["name"], gap
            return best_name, best_gap

        raw = s.lua(
            "local out = {}; for _, v in ipairs(getAllVehicles()) do "
            "local ok, o = pcall(function() return v:getSpawnWorldOOBB() end); "
            "if ok and o then local h = o:getHalfExtents(); "
            "out[v:getName()] = {hx = h.x, hy = h.y, hz = h.z} end end; return jsonEncode(out)"
        )
        reach = {
            n: math.sqrt(float(v["hx"]) ** 2 + float(v["hy"]) ** 2)
            for n, v in raw.items()
            if n in AI
        }
        r["car_reach_m"] = {n.rsplit("_", 1)[-1]: round(v, 2) for n, v in sorted(reach.items())}
        s.check(
            len(reach) == len(AI),
            "could not read spawn extents for every AI car",
            {"read": sorted(reach)},
        )
        mean_reach = sum(reach.values()) / max(len(reach), 1)
        r["arming_disc_m"] = {
            f"rp {value}": round(value + STUCK_MARGIN_M + mean_reach, 2)
            for value in sorted(RP_CENSUS)
        }
        r["arming_disc_m"]["g12_on_keepout_radius"] = 9.4
        r["arming_disc_m"]["mean_car_reach"] = round(mean_reach, 2)

        # --- the 3 minute chase ---------------------------------------------
        props = [
            n
            for n in [e["name"] for e in sync.vehicle_layout(HANDOFF)]
            if n not in (PLAYER, DISPENSER) and n not in AI
        ]
        s.move_away([PLAYER])
        s.set_options(LONG_FUSE)
        s.set_option("ai_enabled", True)
        s.start_round(AI[0])
        hits: list[dict[str, Any]] = []
        last_damage: dict[str, float] = {}
        envelope: list[dict[str, Any]] = []
        gap_min: dict[str, float] = {}
        streak: dict[str, float] = {}
        armed_spans: list[dict[str, Any]] = []
        t0 = s.clock()
        samples = 0
        while s.clock() - t0 < 180.0:
            t = s.clock() - t0
            rows = _census_tick(s, AI + props, last_damage, hits, t)
            for n in AI:
                row = rows[n]
                if not row.get("ok"):
                    continue
                name, gap = _rp_gap(row["x"], row["y"], reach.get(n, 2.5))
                label = n.rsplit("_", 1)[-1]
                key = f"{label}::{name}"
                gap_min[key] = min(gap_min.get(key, 1e9), gap)
                if gap < STUCK_MARGIN_M and row["hspeed"] <= STUCK_SPEED_MPS:
                    envelope.append(
                        {
                            "t": round(t, 1),
                            "car": label,
                            "post": name,
                            "gap": round(gap, 3),
                            "speed": round(row["hspeed"], 2),
                        }
                    )
                    streak[n] = streak.get(n, 0.0) + 0.1
                    # A span is one CONTIGUOUS occupancy of one post's arming
                    # disc by one car: it may only be extended by a sample of
                    # the same pair within a tick of the last one. (G12's
                    # version extended on the car alone and never checked the
                    # gap, so unrelated visits merged into one long span.)
                    last = armed_spans[-1] if armed_spans else None
                    contiguous = (
                        last is not None
                        and last["car"] == label
                        and last["post"] == name
                        and t - last["t_end"] <= 1.0
                    )
                    if contiguous:
                        last["t_end"] = round(t, 1)
                        last["samples"] += 1
                        last["min_gap"] = round(min(last["min_gap"], gap), 3)
                    elif streak[n] >= STUCK_SECONDS:
                        armed_spans.append(
                            {
                                "car": label,
                                "post": name,
                                "t": round(t, 1),
                                "t_end": round(t, 1),
                                "samples": 1,
                                "min_gap": round(gap, 3),
                            }
                        )
                else:
                    streak[n] = 0.0
            samples += 1
            if samples % 100 == 0 and s.stats().get("phase") != "live":
                s.start_round(AI[0])
            s.step(STEP_TICK)
        chase = s.stats()
        solid_hits = [h for h in hits if h["kind"] == "solid" and h["car"] in AI]
        for h in solid_hits:
            h["solid_class"] = _solid_class(h["solid"])
        events = _group_contacts(solid_hits)
        for e in events:
            car_reach = next((v for k, v in reach.items() if k.rsplit("_", 1)[-1] == e["car"]), 2.5)
            post, gap = _rp_gap(e["x"], e["y"], car_reach)
            e["rp_gap_at_contact"] = round(gap, 3)
            e["nearest_post_by_rp"] = post
            e["fine_class"] = _fine_class(e["solid"])
        character = _contact_character(events)
        by_class: dict[str, list[dict[str, Any]]] = {}
        by_fine: dict[str, list[dict[str, Any]]] = {}
        for e in events:
            by_class.setdefault(e["solid_class"], []).append(e)
            by_fine.setdefault(e["fine_class"], []).append(e)

        def _flank_rows(label: str) -> list[dict[str, Any]]:
            return [
                {
                    "car": e["car"],
                    "solid": e["solid"],
                    "t": e["t"],
                    "duration_s": e["duration_s"],
                    "max_speed": e["max_speed"],
                    "damage": round(e["damage"], 1),
                    "x": e["x"],
                    "y": e["y"],
                    "rp_gap_at_contact": e["rp_gap_at_contact"],
                }
                for e in by_fine.get(label, [])
            ]

        envelope_by_pair: dict[str, int] = {}
        for x in envelope:
            envelope_by_pair[f"{x['car']}::{x['post']}"] = (
                envelope_by_pair.get(f"{x['car']}::{x['post']}", 0) + 1
            )
        r["envelope"] = {
            "samples_in_envelope": len(envelope),
            "samples_by_car_and_post": dict(
                sorted(envelope_by_pair.items(), key=lambda kv: -kv[1])
            ),
            "armed_spans": armed_spans,
            "armed_span_count": len(armed_spans),
            "longest_armed_span_s": round(
                max((x["t_end"] - x["t"] for x in armed_spans), default=0.0), 1
            ),
            "arming_threshold": {
                "gap_under_m": STUCK_MARGIN_M,
                "speed_at_or_under_mps": STUCK_SPEED_MPS,
                "sustained_seconds": STUCK_SECONDS,
            },
            "first_10": envelope[:10],
            "min_gap_by_car_and_post": {
                k: round(v, 2) for k, v in sorted(gap_min.items(), key=lambda kv: kv[1])[:10]
            },
            "note": "computed OUTSIDE the mod with the runtime's own v2.15 formula "
            "gap = |car - post| - post.RP - car_reach, over the ECHOED registry",
            "g12_baseline_samples_on_keepout_radius": 4093,
        }
        # Two units, stated, because they are not the same number and every gate
        # before G13 quoted the first while calling it the second (see the note
        # on _group_contacts): the RAW damage-sample count is what the 17 and 51
        # baselines actually are, and the GROUPED event count is what "a contact"
        # means once consecutive readings are merged.
        samples_by_fine: dict[str, int] = {}
        for h in solid_hits:
            samples_by_fine[_fine_class(h["solid"])] = (
                samples_by_fine.get(_fine_class(h["solid"]), 0) + 1
            )
        # Where the reflex provably COULD NOT arm: the contact happened outside
        # its own arming disc. On a circle-per-point registry that is the
        # signature of a face the registry cannot see between its samples.
        unreachable = [e for e in events if e["rp_gap_at_contact"] >= STUCK_MARGIN_M]
        r["chase"] = {
            "sim_seconds": round(s.clock() - t0, 1),
            "samples": samples,
            "transfers": chase.get("transfers"),
            "field": chase.get("field"),
            "contact_samples_total": len(solid_hits),
            "contact_samples_by_fine_class": dict(sorted(samples_by_fine.items())),
            "contact_events_total": len(events),
            "contact_events_by_class": {k: len(v) for k, v in sorted(by_class.items())},
            "contact_events_by_fine_class": {k: len(v) for k, v in sorted(by_fine.items())},
            "flank_split_for_the_segment_decision": {
                "handle_flank": _flank_rows("handle_flank"),
                "ramp_flank": _flank_rows("ramp_flank"),
            },
            "events_outside_the_reflexs_own_arming_disc": [
                {
                    "car": e["car"],
                    "solid": e["solid"],
                    "fine_class": e["fine_class"],
                    "t": e["t"],
                    "duration_s": e["duration_s"],
                    "samples": e["samples"],
                    "max_speed": e["max_speed"],
                    "x": e["x"],
                    "y": e["y"],
                    "rp_gap_at_contact": e["rp_gap_at_contact"],
                    "nearest_post_by_rp": e["nearest_post_by_rp"],
                }
                for e in unreachable
            ],
            "baselines": {
                "g11_serial_52": 17,
                "g12_serial_54": 51,
                "unit": "raw damage samples - the pre-G13 grouping never merged anything",
            },
            "events": events,
        }
        r["contact_character"] = character
        s.shot(
            "chase_field",
            (C[0] + 70.0, C[1] + 80.0, C[2] + 45.0),
            (C[0], C[1], C[2] + 2.0),
            "the field after three minutes on serial 55 with the measured rp",
        )
        # BOTH clauses. A count alone cannot separate "fixed" from "switched off".
        s.check(
            len(envelope) > 0,
            "the envelope did not arm at all on the physical radius - the reflex cannot have "
            "run, so the contact count below says nothing about the fix",
            {"samples_in_envelope": 0, "closest_gaps": r["envelope"]["min_gap_by_car_and_post"]},
        )
        s.check(
            len(solid_hits) < 17,
            "obstacle contacts did not come back below the G11 baseline of 17 (raw damage "
            "samples, the unit that baseline is actually in)",
            {
                "samples": len(solid_hits),
                "by_fine_class": r["chase"]["contact_samples_by_fine_class"],
                "grouped_events": len(events),
            },
        )
        s.check(
            len(solid_hits) < 51,
            "obstacle contacts did not even improve on the G12 keep-out-radius count of 51",
            {"samples": len(solid_hits)},
        )
        s.check(
            character["shape_counts"].get("fixed_position_grinding", 0) == 0,
            "a car is still grinding at a fixed position - armed but unable to free the car "
            "points at geometry, not at the reflex",
            {
                k: v
                for k, v in character["by_pair"].items()
                if v["shape"] == "fixed_position_grinding"
            },
        )
        s.set_option("ai_enabled", False)
    assert not s.report.get("problems"), s.report["problems"]


@pytest.mark.beamng_live
def test_g13_round_regression(tmp_path: Path) -> None:
    """G13.3 - one full round on serial 55: field 6, props 16, boom, return, fireworks."""

    with _session("G13_3", tmp_path, watchdog_seconds=2400.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]
        s.set_option("ai_enabled", False)
        for n in AI:
            s.park(n)
        s.set_options(
            {
                "fuse_base_seconds": 30,
                "fuse_sigma_seconds": 0,
                "fuse_min_seconds": 25,
                "fuse_max_seconds": 35,
                "cue_window_seconds": 15,
            }
        )
        stats = s.start_round(PLAYER)
        r["round_start"] = {
            "field": stats.get("field"),
            "props_excluded": stats.get("props_excluded"),
            "phase": stats.get("phase"),
        }
        s.check(int(stats.get("field", -1)) == 6, "field != 6 on serial 55", r["round_start"])
        s.check(
            int(stats.get("props_excluded", -1)) == 16,
            "props_excluded != 16 on serial 55",
            r["round_start"],
        )
        pad = s.pad
        s.shot(
            "pickup",
            (pad[0] + 16.0, pad[1] - 14.0, pad[2] + 6.0),
            (pad[0], pad[1], pad[2] + 2.0),
            "the round live on serial 55",
        )
        s.teleport(AI[0], (pad[0], pad[1] + 24.0), 180.0)
        s.control(AI[0], steering=0.0, throttle=1.0, brake=0.0, parkingbrake=0.0)
        s.vehicle(AI[0]).set_velocity(10.0, 1.0)
        rammer_id = int(s.probe(AI[0])["id"])
        transferred = True
        try:
            s.step_until(
                lambda: int(s.stats().get("carrier") or -1) == rammer_id,
                calls=90,
                note="ram transfer",
            )
        except AssertionError:
            transferred = False
        s.control(AI[0], steering=0.0, throttle=0.0, brake=1.0, parkingbrake=1.0)
        s.check(transferred, "the ram never transferred the potato", {"rammer": rammer_id})
        s.shot(
            "ram",
            (pad[0] + 15.0, pad[1] + 20.0, pad[2] + 6.0),
            (pad[0], pad[1] + 8.0, pad[2] + 1.5),
            "the ram transfer",
        )
        # Whoever is holding it when the fuse ends is the wreck to measure. The
        # first run of this gate read AI[0]'s speed and found 0.01 m/s while the
        # log showed three `potato_passed` events and a clean `detonation`: the
        # potato had moved on, so the clause was watching a parked bystander.
        victim: dict[str, int] = {}
        boomed = True

        def _boom_reached() -> bool:
            st = s.stats()
            carrier = int(st.get("carrier") or -1)
            if st.get("phase") == "live" and carrier >= 0:
                victim["id"] = carrier
            return st.get("phase") == "boom"

        try:
            s.step_until(_boom_reached, calls=300, note="fuse to boom")
        except AssertionError:
            boomed = False
        s.check(boomed, "the fuse never detonated", s.stats())
        if boomed:
            names = s.names_by_id()
            victim_name = names.get(victim.get("id", -1), AI[0])
            peak, anchor = 0.0, None
            for _ in range(10):
                s.step(6)
                p = s.probe(victim_name)
                peak = max(peak, p["speed"])
                anchor = anchor or (p["x"], p["y"], p["z"])
            r["boom"] = {
                "peak_speed": round(peak, 2),
                "victim": victim_name,
                "victim_id": victim.get("id"),
                "rammer_id": rammer_id,
            }
            s.check(peak > 6.0, "the detonation never moved the wreck", r["boom"])
            s.shot(
                "boom",
                (anchor[0] + 11.0, anchor[1] - 11.0, anchor[2] + 5.0),
                (anchor[0], anchor[1], anchor[2] + 2.0),
                "the detonation",
            )
            returned = True
            try:
                s.step_until(
                    lambda: s.stats().get("phase") in ("return", "idle"),
                    calls=200,
                    note="return flight",
                )
            except AssertionError:
                returned = False
            s.check(returned, "the boom never handed over to the return flight", s.stats())
            after = s.stats()
            r["fireworks"] = {"fw_stage": after.get("fw_stage")}
            s.check(after.get("fw_stage", "") != "", "no winner fireworks after the boom", after)
            try:
                s.step_until(
                    lambda: s.stats().get("fw_stage") in ("burst", "finale"), calls=60, note="burst"
                )
                s.shot(
                    "fireworks",
                    (pad[0], pad[1] + 72.0, pad[2] + 44.0),
                    (pad[0], pad[1], pad[2] + 56.0),
                    "winner fireworks over the arch",
                )
            except AssertionError:
                s.problem("the fireworks never reached a burst stage", s.stats())
            try:
                s.step_until(lambda: s.stats().get("phase") == "idle", calls=300, note="idle")
                s.shot(
                    "idle",
                    (pad[0] + 9.0, pad[1] - 9.0, pad[2] + 1.6),
                    (pad[0], pad[1], pad[2] + 6.5),
                    "the potato home on its perch",
                )
            except AssertionError:
                s.problem("the return flight never settled to idle", s.stats())
        v = s.arena()["valve"]
        opts = s.options()
        r["after_round"] = {
            "radius": opts["arena_radius_m"],
            "valve_stage": v["stage"],
            "in_round": v["in_round"],
        }
        s.check(
            abs(float(opts["arena_radius_m"]) - 91.4) < 1e-6,
            "the radius was not restored at round end",
            r["after_round"],
        )
    assert not s.report.get("problems"), s.report["problems"]


# ====================================================================================
# G14 - the last boot pass: the nose face points, the deck-rear junction, one round
#
# G14.1 A - the handle-nose pin, G13's boot-1 residual.
#   G13 boot 1 left a car wedged against the handle NOSE at (846.7, -308.2), speed
#   0.0, with rp_gap_at_contact = +1.471 m - POSITIVE, so outside the reflex's own
#   0.5 m arming margin: the escape provably could not arm. The cause was measured
#   and specific: the nose is a 14.0 m face carrying only its two end corners, a
#   7.0 m worst uncovered half-span. Geometry v3.6 adds four `handle_nose_face_*`
#   points at 2.8 m pitch, taking the table 42 -> 46. The flanks are NOT part of
#   this: they took zero contacts in three G13 boots and the segment primitive was
#   declined permanently on that evidence.
#
# G14.2 B - the handle deck-rear junction, driven.
#   v3.6 reported a 145 mm step here; v3.7 RETRACTED it - the rear edge is authored
#   on the r 88.5 bank arc (0.002 mm relief), and the 145 mm came from an audit that
#   modelled the edge as a straight chord. What v3.8 actually fixed is cosmetic: the
#   tuck strip stood +4.741 mm proud of the bank between stations (a chord across
#   the bank's slope break at station 88.875) and now DESCENDS 50 mm, measured
#   -2.427 mm strictly below across 549 samples of the built triangles. So the
#   junction should be clean physically AND visually, and the handle DAE moved for
#   the first time since round 2 (3dac6cd3... -> 88cbb1c5..., 12 vertices, 2022 tris
#   both sides) - which makes this the regression check on that change too.
#
#   A Blender render cannot prove a collision surface and EEVEE's grazing behaviour
#   is not the engine's depth resolution, so this measures the surface with rays,
#   crosses it on wheels at crawl and at speed in BOTH directions, and photographs
#   the seam at a grazing angle from the player's own camera class.
#
#   One piece of authored geometry to read the results against: outboard of r 88.5
#   the bank climbs to the crest (105.5 at r 91.4), a ~52 % grade, and G2 already
#   measured the bank un-climbable past r ~88.2 from below. A car that stops on
#   THAT is grade-limited by design. A car that stops ON the seam is a lip. The
#   stall discriminator and the r at which it fires separate the two.
#
# G14.3 C - one full round. Nothing else: the far-field, the out-of-bounds fuse,
#   the orbit, the crest rams and the perf window are all unmoved.
# ====================================================================================

# The deck's rear edge, authored on the bank arc: end_y(x) = -sqrt(88.5^2 - x^2).
JUNCTION_R = 88.5
# Radial sample lines through the deck, offset from the centreline by +-5 m of
# local x at the junction (the deck runs local x -7..+7, so this stays off the
# two rear corners): dx = 88.5 * sin(delta).
# Deliberately NOT 180.0: the handle is built symmetric about local x = 0, so a
# triangle edge runs down x = 850.000 and a downward ray launched exactly on it
# can miss both triangles and read the groundplane 4 m below (boot 1 did). The
# exact centreline is still mapped, separately, as its own diagnostic.
JUNCTION_BEARINGS = (176.76, 179.5, 180.5, 183.24)
# The SEAM itself: the deck side plus the first 100 mm outboard. Kept separate
# from the bank climb beyond it, because they are different claims - the seam is
# authored flush (v3.7: 0.002 mm) while the bank outboard is an authored ~30 %
# climb to the crest, and lumping them lets a real step hide inside a legal grade.
JUNCTION_SEAM_BAND = (88.0, 88.6)
JUNCTION_BAND = (88.0, 89.0)  # the metre either side of the seam, for the drives
# Boot 1 found a z anomaly on the CENTRELINE only, outboard of the seam. This is
# the window it is mapped in.
ANOMALY_WINDOW = (88.5, 90.5)
ANOMALY_BEARINGS = tuple(round(176.0 + 0.5 * i, 1) for i in range(17))  # 176.0 .. 184.0
RAY_STEP_M = 0.05
# A 5 cm step this large is ~100 % local grade - far above the authored 52 % and
# far below nothing, so it catches a 145 mm lip with a wide margin while never
# firing on the bank's own climb.
JUNCTION_STEP_CAP_M = 0.05


def _handoff_rp_census() -> dict[float, int]:
    census: dict[float, int] = {}
    for o in HANDOFF["obstacles"]:
        census[round(float(o["rp"]), 3)] = census.get(round(float(o["rp"]), 3), 0) + 1
    return census


def _echo_registry(s: Session) -> dict[str, Any]:
    """Read hotPotatoGetObstacles() and match every entry to the handoff by position."""

    hook = s.lua(f"return jsonEncode(extensions[{RUNTIME!r}].hotPotatoGetObstacles())")
    entries = [dict(e) for e in hook.get("entries", [])]
    by_xy = {(round(float(o["x"]), 3), round(float(o["y"]), 3)): o for o in HANDOFF["obstacles"]}
    matched, mismatched = 0, []
    named: dict[str, dict[str, Any]] = {}
    for e in entries:
        row = by_xy.get((round(float(e["x"]), 3), round(float(e["y"]), 3)))
        if row is None:
            mismatched.append({"echo": e, "why": "no handoff obstacle at this position"})
            continue
        named[str(row["name"])] = e
        if (
            abs(float(e["rp"]) - float(row["rp"])) > 1e-6
            or abs(float(e["r"]) - float(row["r_keepout"])) > 1e-6
        ):
            mismatched.append({"echo": e, "handoff": row})
        else:
            matched += 1
    census: dict[float, int] = {}
    for e in entries:
        census[round(float(e["rp"]), 3)] = census.get(round(float(e["rp"]), 3), 0) + 1
    posts = [
        {
            "name": next((n for n, v in named.items() if v is e), "?"),
            "x": float(e["x"]),
            "y": float(e["y"]),
            "r": float(e["r"]),
            "rp": float(e["rp"]),
        }
        for e in entries
    ]
    return {
        "hook": hook,
        "entries": entries,
        "named": named,
        "posts": posts,
        "matched": matched,
        "mismatched": mismatched,
        "census": census,
        "rp_over_r": [e for e in entries if float(e["rp"]) > float(e["r"])],
    }


@pytest.mark.beamng_live
def test_g14_pin_reflex(tmp_path: Path) -> None:
    """G14.1 - D-8 with the nose face covered: 46 points, contacts at or below 7."""

    with _session("G14_1", tmp_path, watchdog_seconds=3000.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]

        echo = _echo_registry(s)
        expected_census = _handoff_rp_census()
        nose_faces = {n: v for n, v in echo["named"].items() if n.startswith("handle_nose_face_")}
        pitches = sorted(float(v["x"]) for v in nose_faces.values())
        r["obstacle_echo"] = {
            "count": int(echo["hook"].get("count", -1)),
            "expected_count": len(HANDOFF["obstacles"]),
            "matched_to_handoff": echo["matched"],
            "mismatched": echo["mismatched"][:5],
            "rp_census": {str(k): v for k, v in sorted(echo["census"].items())},
            "rp_census_expected": {str(k): v for k, v in sorted(expected_census.items())},
            "entries_with_rp_over_r": len(echo["rp_over_r"]),
            "nose_face_points": {
                n: {"x": v["x"], "y": v["y"], "r": v["r"], "rp": v["rp"]}
                for n, v in sorted(nose_faces.items())
            },
            "nose_face_pitch_m": [round(b - a, 3) for a, b in zip(pitches, pitches[1:])],
            "post_classes": {RP_POST_CLASSES[k]: echo["census"].get(k, 0) for k in RP_POST_CLASSES},
        }
        s.check(
            int(echo["hook"].get("count", -1)) == 46,
            "hotPotatoGetObstacles did not echo 46 entries",
            r["obstacle_echo"],
        )
        s.check(
            len(nose_faces) == 4
            and all(abs(float(v["rp"]) - 0.1) < 1e-6 for v in nose_faces.values()),
            "the four handle_nose_face points are not present at the contract's 0.1 m floor",
            r["obstacle_echo"]["nose_face_points"],
        )
        s.check(
            bool(pitches)
            and all(abs(p - 2.8) < 0.01 for p in [b - a for a, b in zip(pitches, pitches[1:])]),
            "the nose face points are not at the 2.8 m pitch",
            r["obstacle_echo"]["nose_face_pitch_m"],
        )
        s.check(
            not echo["rp_over_r"],
            "an echoed obstacle has rp > r, which the contract forbids",
            echo["rp_over_r"][:5],
        )
        s.check(
            echo["matched"] == len(echo["entries"]) and not echo["mismatched"],
            "an echoed obstacle's r/rp does not match the geometry handoff",
            r["obstacle_echo"],
        )
        s.check(
            echo["census"] == expected_census,
            "the echoed rp census is not the geometry's measured model",
            r["obstacle_echo"],
        )
        for value, label in RP_POST_CLASSES.items():
            s.check(
                echo["census"].get(value, 0) == expected_census.get(value, 0),
                f"the {label} class did not land at rp {value}",
                r["obstacle_echo"],
            )

        posts = echo["posts"]

        def _rp_gap(x: float, y: float, reach: float) -> tuple[str, float]:
            best_name, best_gap = "", 1e9
            for p in posts:
                gap = math.hypot(x - p["x"], y - p["y"]) - p["rp"] - reach
                if gap < best_gap:
                    best_name, best_gap = p["name"], gap
            return best_name, best_gap

        # The G13 boot-1 pin, replayed against the NEW registry as arithmetic:
        # the same car position must now fall inside the arming margin.
        g13_pin = {"x": 846.7, "y": -308.2, "car_reach": 2.54, "g13_gap": 1.471}
        _, g13_gap_now = _rp_gap(g13_pin["x"], g13_pin["y"], g13_pin["car_reach"])
        g13_pin["gap_now"] = round(g13_gap_now, 3)
        g13_pin["arms_now"] = g13_gap_now < STUCK_MARGIN_M
        r["g13_pin_replayed"] = g13_pin
        s.check(
            g13_pin["arms_now"],
            "G13's own pin position STILL cannot arm on the new registry - the four nose "
            "points do not cover where the car actually sat",
            g13_pin,
        )

        raw = s.lua(
            "local out = {}; for _, v in ipairs(getAllVehicles()) do "
            "local ok, o = pcall(function() return v:getSpawnWorldOOBB() end); "
            "if ok and o then local h = o:getHalfExtents(); "
            "out[v:getName()] = {hx = h.x, hy = h.y, hz = h.z} end end; return jsonEncode(out)"
        )
        reach = {
            n: math.sqrt(float(v["hx"]) ** 2 + float(v["hy"]) ** 2)
            for n, v in raw.items()
            if n in AI
        }
        r["car_reach_m"] = {n.rsplit("_", 1)[-1]: round(v, 2) for n, v in sorted(reach.items())}
        s.check(
            len(reach) == len(AI),
            "could not read spawn extents for every AI car",
            {"read": sorted(reach)},
        )

        props = [
            n
            for n in [e["name"] for e in sync.vehicle_layout(HANDOFF)]
            if n not in (PLAYER, DISPENSER) and n not in AI
        ]
        s.move_away([PLAYER])
        s.set_options(LONG_FUSE)
        s.set_option("ai_enabled", True)
        s.start_round(AI[0])
        hits: list[dict[str, Any]] = []
        last_damage: dict[str, float] = {}
        envelope: list[dict[str, Any]] = []
        gap_min: dict[str, float] = {}
        streak: dict[str, float] = {}
        armed_spans: list[dict[str, Any]] = []
        open_span: dict[tuple[str, str], dict[str, Any]] = {}
        t0 = s.clock()
        samples = 0
        while s.clock() - t0 < 180.0:
            t = s.clock() - t0
            rows = _census_tick(s, AI + props, last_damage, hits, t)
            for n in AI:
                row = rows[n]
                if not row.get("ok"):
                    continue
                name, gap = _rp_gap(row["x"], row["y"], reach.get(n, 2.5))
                label = n.rsplit("_", 1)[-1]
                gap_min[f"{label}::{name}"] = min(gap_min.get(f"{label}::{name}", 1e9), gap)
                if gap < STUCK_MARGIN_M and row["hspeed"] <= STUCK_SPEED_MPS:
                    envelope.append(
                        {
                            "t": round(t, 1),
                            "car": label,
                            "post": name,
                            "gap": round(gap, 3),
                            "speed": round(row["hspeed"], 2),
                        }
                    )
                    streak[n] = streak.get(n, 0.0) + 0.1
                    # Per (car, post), not "the last span opened": with three cars
                    # sitting in three different discs at once, a global-last test
                    # makes every sample break the previous car's run. G14 boot 1
                    # read 4,192 "spans" over 4,291 samples for exactly that reason
                    # - the same defect _group_contacts had before G13 fixed it.
                    last = open_span.get((label, name))
                    if last is not None and t - last["t_end"] <= 1.0:
                        last["t_end"] = round(t, 1)
                        last["samples"] += 1
                        last["min_gap"] = round(min(last["min_gap"], gap), 3)
                    elif streak[n] >= STUCK_SECONDS:
                        span = {
                            "car": label,
                            "post": name,
                            "t": round(t, 1),
                            "t_end": round(t, 1),
                            "samples": 1,
                            "min_gap": round(gap, 3),
                        }
                        armed_spans.append(span)
                        open_span[(label, name)] = span
                else:
                    streak[n] = 0.0
            samples += 1
            if samples % 100 == 0 and s.stats().get("phase") != "live":
                s.start_round(AI[0])
            s.step(STEP_TICK)
        chase = s.stats()
        solid_hits = [h for h in hits if h["kind"] == "solid" and h["car"] in AI]
        for h in solid_hits:
            h["solid_class"] = _solid_class(h["solid"])
        events = _group_contacts(solid_hits)
        for e in events:
            car_reach = next((v for k, v in reach.items() if k.rsplit("_", 1)[-1] == e["car"]), 2.5)
            post, gap = _rp_gap(e["x"], e["y"], car_reach)
            e["rp_gap_at_contact"] = round(gap, 3)
            e["nearest_post_by_rp"] = post
            e["fine_class"] = _fine_class(e["solid"])
        character = _contact_character(events)
        by_class: dict[str, list[dict[str, Any]]] = {}
        by_fine: dict[str, list[dict[str, Any]]] = {}
        for e in events:
            by_class.setdefault(e["solid_class"], []).append(e)
            by_fine.setdefault(e["fine_class"], []).append(e)
        samples_by_fine: dict[str, int] = {}
        for h in solid_hits:
            samples_by_fine[_fine_class(h["solid"])] = (
                samples_by_fine.get(_fine_class(h["solid"]), 0) + 1
            )
        # "The registry could not see where the car touched" is a claim about the
        # PIN REFLEX, and the pin reflex only ever runs at or under 3 m/s
        # (v26.DODGE_STUCK_SPEED). A contact outside the arming disc at 12 m/s is
        # a STEERING matter - the dodge rays the velocity vector against the 8.0 m
        # keep-out `r`, not against `rp` - so lumping the two together would have
        # charged the wrong mechanism. Both lists are reported; only the low-speed
        # one is gated.
        outside_disc = [e for e in events if e["rp_gap_at_contact"] >= STUCK_MARGIN_M]
        unreachable = [e for e in outside_disc if e["max_speed"] <= STUCK_SPEED_MPS]
        envelope_by_pair: dict[str, int] = {}
        for x in envelope:
            envelope_by_pair[f"{x['car']}::{x['post']}"] = (
                envelope_by_pair.get(f"{x['car']}::{x['post']}", 0) + 1
            )
        r["envelope"] = {
            "samples_in_envelope": len(envelope),
            "samples_by_car_and_post": dict(
                sorted(envelope_by_pair.items(), key=lambda kv: -kv[1])
            ),
            "armed_spans": armed_spans,
            "armed_span_count": len(armed_spans),
            "longest_armed_span_s": round(
                max((x["t_end"] - x["t"] for x in armed_spans), default=0.0), 1
            ),
            "arming_threshold": {
                "gap_under_m": STUCK_MARGIN_M,
                "speed_at_or_under_mps": STUCK_SPEED_MPS,
                "sustained_seconds": STUCK_SECONDS,
            },
            "min_gap_by_car_and_post": {
                k: round(v, 2) for k, v in sorted(gap_min.items(), key=lambda kv: kv[1])[:10]
            },
            "note": "the runtime's own v2.15 formula gap = |car - post| - post.RP - car_reach, "
            "over the ECHOED 46-point registry",
            "baselines": {
                "g11_serial_52": 0,
                "g12_keepout_radius": 4093,
                "g13_rp_42_points": [202, 1695, 1411],
            },
        }
        r["chase"] = {
            "sim_seconds": round(s.clock() - t0, 1),
            "samples": samples,
            "transfers": chase.get("transfers"),
            "field": chase.get("field"),
            "contact_samples_total": len(solid_hits),
            "contact_samples_by_fine_class": dict(sorted(samples_by_fine.items())),
            "contact_events_total": len(events),
            "contact_events_by_class": {k: len(v) for k, v in sorted(by_class.items())},
            "contact_events_by_fine_class": {k: len(v) for k, v in sorted(by_fine.items())},
            "flank_split_for_the_record": {
                "handle_flank": [
                    {
                        "car": e["car"],
                        "t": e["t"],
                        "duration_s": e["duration_s"],
                        "max_speed": e["max_speed"],
                        "x": e["x"],
                        "y": e["y"],
                        "rp_gap_at_contact": e["rp_gap_at_contact"],
                    }
                    for e in by_fine.get("handle_flank", [])
                ],
                "ramp_flank": [
                    {
                        "car": e["car"],
                        "t": e["t"],
                        "duration_s": e["duration_s"],
                        "max_speed": e["max_speed"],
                        "x": e["x"],
                        "y": e["y"],
                        "rp_gap_at_contact": e["rp_gap_at_contact"],
                    }
                    for e in by_fine.get("ramp_flank", [])
                ],
                "handle_nose": [
                    {
                        "car": e["car"],
                        "t": e["t"],
                        "duration_s": e["duration_s"],
                        "max_speed": e["max_speed"],
                        "x": e["x"],
                        "y": e["y"],
                        "rp_gap_at_contact": e["rp_gap_at_contact"],
                    }
                    for e in by_fine.get("handle_nose", [])
                ],
            },
            "events_outside_the_arming_disc_any_speed": [
                {
                    "car": e["car"],
                    "solid": e["solid"],
                    "fine_class": e["fine_class"],
                    "t": e["t"],
                    "duration_s": e["duration_s"],
                    "samples": e["samples"],
                    "max_speed": e["max_speed"],
                    "x": e["x"],
                    "y": e["y"],
                    "rp_gap_at_contact": e["rp_gap_at_contact"],
                    "nearest_post_by_rp": e["nearest_post_by_rp"],
                    "mechanism": "pin reflex (rp)"
                    if e["max_speed"] <= STUCK_SPEED_MPS
                    else "steering dodge (r) - above the 3 m/s pin floor",
                }
                for e in outside_disc
            ],
            "events_the_pin_reflex_could_not_arm_for": [
                {
                    "car": e["car"],
                    "solid": e["solid"],
                    "fine_class": e["fine_class"],
                    "t": e["t"],
                    "duration_s": e["duration_s"],
                    "max_speed": e["max_speed"],
                    "x": e["x"],
                    "y": e["y"],
                    "rp_gap_at_contact": e["rp_gap_at_contact"],
                    "nearest_post_by_rp": e["nearest_post_by_rp"],
                }
                for e in unreachable
            ],
            "baselines": {
                "g11_serial_52": 17,
                "g12_serial_54": 51,
                "g13_serial_55_42_points": [30, 7, 16],
                "unit": "raw damage samples",
            },
            "events": events,
        }
        r["contact_character"] = character
        s.shot(
            "chase_field",
            (C[0] + 70.0, C[1] + 80.0, C[2] + 45.0),
            (C[0], C[1], C[2] + 2.0),
            "the field after three minutes on the 46-point registry",
        )
        s.shot(
            "nose_face",
            (C[0] + 26.0, C[1] - 22.0, C[2] + 9.0),
            (850.0, -310.0, C[2] + 2.0),
            "the handle nose face, now carrying four interior points",
        )
        s.check(
            len(envelope) > 0,
            "the envelope did not arm at all - the reflex cannot have run, so the contact "
            "count says nothing about the fix",
            {"samples_in_envelope": 0, "closest_gaps": r["envelope"]["min_gap_by_car_and_post"]},
        )
        s.check(
            len(solid_hits) <= 7,
            "obstacle contacts are above G13's best boot (7 raw damage samples)",
            {
                "samples": len(solid_hits),
                "by_fine_class": r["chase"]["contact_samples_by_fine_class"],
                "grouped_events": len(events),
            },
        )
        # The nose claim is not "zero contacts" - it is that the reflex can now
        # ARM where a car touches the nose. G13's residual was a car pinned at
        # gap +1.471 with the escape unable to fire; a brush at gap -0.7 is the
        # reflex working, which is the success case.
        nose_unarmable = [
            e
            for e in by_fine.get("handle_nose", [])
            if e["rp_gap_at_contact"] >= STUCK_MARGIN_M and e["max_speed"] <= STUCK_SPEED_MPS
        ]
        s.check(
            not nose_unarmable,
            "a low-speed handle NOSE contact still sits outside the arming disc - the four "
            "face points do not cover where cars actually touch the nose",
            nose_unarmable,
        )
        s.check(
            not unreachable,
            "a LOW-SPEED contact happened outside the pin reflex's own arming disc - the "
            "registry still cannot see where a pinned car actually touched",
            r["chase"]["events_the_pin_reflex_could_not_arm_for"],
        )
        s.check(
            character["shape_counts"].get("fixed_position_grinding", 0) == 0,
            "a car is still grinding at a fixed position",
            {
                k: v
                for k, v in character["by_pair"].items()
                if v["shape"] == "fixed_position_grinding"
            },
        )
        s.set_option("ai_enabled", False)
    assert not s.report.get("problems"), s.report["problems"]


@pytest.mark.beamng_live
def test_g14_handle_rear_junction(tmp_path: Path) -> None:
    """G14.2 - the deck-rear junction: rayed, then driven at crawl and at speed, both ways."""

    with _session("G14_2", tmp_path, watchdog_seconds=3000.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]
        s.set_option("ai_enabled", False)
        for n in AI:
            s.park(n)
        s.move_away(AI)

        # --- 1. the surface itself, before any wheel touches it ---------------
        profiles: dict[str, Any] = {}
        for bearing in JUNCTION_BEARINGS:
            steps = int((92.0 - 84.0) / RAY_STEP_M) + 1
            points = [_bearing_xy(bearing, 84.0 + i * RAY_STEP_M) for i in range(steps)]
            rows = s.surface_profile(points)
            radii = [84.0 + i * RAY_STEP_M for i in range(steps)]
            voids = [round(radii[i], 2) for i, row in enumerate(rows) if not row["hit"]]
            deltas = [
                (round(radii[i + 1], 2), round(rows[i + 1]["z"] - rows[i]["z"], 4))
                for i in range(len(rows) - 1)
            ]
            band = [d for d in deltas if JUNCTION_SEAM_BAND[0] <= d[0] <= JUNCTION_SEAM_BAND[1]]
            worst_band = max(band, key=lambda d: abs(d[1])) if band else (None, 0.0)
            worst_all = max(deltas, key=lambda d: abs(d[1])) if deltas else (None, 0.0)
            outboard = [d for d in deltas if JUNCTION_SEAM_BAND[1] < d[0] <= 90.5]
            worst_outboard = max(outboard, key=lambda d: abs(d[1])) if outboard else (None, 0.0)
            at = {
                f"r{v}": round(
                    next(
                        row["z"] for i, row in enumerate(rows) if abs(radii[i] - v) < RAY_STEP_M / 2
                    ),
                    4,
                )
                for v in (86.0, 88.0, 88.25, 88.5, 88.75, 89.0, 90.0)
            }
            profiles[f"bearing_{bearing}"] = {
                "samples": len(rows),
                "voids": voids,
                "z_at": at,
                "worst_step_in_seam_band_m": {"r": worst_band[0], "dz": round(worst_band[1], 4)},
                "worst_step_outboard_of_seam_m": {
                    "r": worst_outboard[0],
                    "dz": round(worst_outboard[1], 4),
                },
                "worst_step_anywhere_r84_92_m": {"r": worst_all[0], "dz": round(worst_all[1], 4)},
                "local_grade_pct_across_band": round(100.0 * (at["r89.0"] - at["r88.0"]) / 1.0, 1),
            }
        r["junction_profile"] = {
            "bearings": profiles,
            "step_cap_m": JUNCTION_STEP_CAP_M,
            "junction_r": JUNCTION_R,
            "ray_step_m": RAY_STEP_M,
            "v3_6_retracted_claim_m": 0.145,
            "note": "a 145 mm lip would appear as a single 5 cm step of 0.145 m; the authored "
            "bank grade outboard of the seam produces ~0.026 m per 5 cm and is not a step",
        }
        for key, block in profiles.items():
            s.check(
                not block["voids"],
                f"{key}: the ray raster found a void across the junction",
                {"voids": block["voids"]},
            )
            s.check(
                abs(block["worst_step_in_seam_band_m"]["dz"]) < JUNCTION_STEP_CAP_M,
                f"{key}: a step at the deck-rear SEAM exceeds the cap - v3.7's retraction "
                "of the 145 mm finding does not hold in the engine",
                block["worst_step_in_seam_band_m"],
            )

        # --- 1b. the boot-1 anomaly, mapped in bearing and radius -------------
        # Boot 1 read a 0.231 m step at r 88.85 and a 4.461 m jump at r 89.25 on
        # bearing 180.0 EXACTLY, while the two lines 3.24 deg either side read
        # 0.033 m. Bearing 180 is not a wall-arc boundary (the arcs break at
        # 15/60/105/150/195/240/285/330), so this is not a ray slipping between
        # coincident shapes; it is mapped here rather than assumed either way.
        amap: dict[str, Any] = {}
        steps = int((ANOMALY_WINDOW[1] - ANOMALY_WINDOW[0]) / 0.02) + 1
        for bearing in ANOMALY_BEARINGS:
            radii = [ANOMALY_WINDOW[0] + i * 0.02 for i in range(steps)]
            rows = s.surface_profile([_bearing_xy(bearing, rr) for rr in radii])
            deltas = [
                (round(radii[i + 1], 3), rows[i + 1]["z"] - rows[i]["z"])
                for i in range(len(rows) - 1)
            ]
            worst = max(deltas, key=lambda d: abs(d[1])) if deltas else (None, 0.0)
            spikes = [{"r": d[0], "dz": round(d[1], 4)} for d in deltas if abs(d[1]) > 0.1]
            amap[f"bearing_{bearing}"] = {
                "worst_step": {"r": worst[0], "dz": round(worst[1], 4)},
                "steps_over_100mm": spikes[:6],
                "spike_count": len(spikes),
                "z_min": round(min(x["z"] for x in rows), 3),
                "z_max": round(max(x["z"] for x in rows), 3),
                "voids": [round(radii[i], 2) for i, x in enumerate(rows) if not x["hit"]],
            }
        affected = {k: v for k, v in amap.items() if v["spike_count"]}

        # Two discriminators, because "a ray read 4 m of nothing" has exactly two
        # explanations and they have opposite consequences.
        #   (i) LATERAL JITTER. The handle is built symmetric about local x = 0, so
        #       a triangle edge runs down x = 850.000 exactly. A downward ray
        #       launched ON that edge can miss both triangles and fall to the
        #       groundplane (z 100.0, which is exactly what the z_min reads). If a
        #       5 mm sidestep is clean, the mesh is closed and the ray was on an
        #       edge; a real gap does not close in 5 mm.
        #  (ii) A CAR. A ray is infinitesimal; a tyre is not. If a car dropped on
        #       the same spot rests on the bank instead of falling to the floor,
        #       the collision surface is there whatever the ray said.
        jitter: dict[str, Any] = {}
        for dx in (-0.05, -0.02, -0.005, 0.0, 0.005, 0.02, 0.05):
            radii = [ANOMALY_WINDOW[0] + i * 0.02 for i in range(steps)]
            pts = [(_bearing_xy(180.0, rr)[0] + dx, _bearing_xy(180.0, rr)[1]) for rr in radii]
            rows = s.surface_profile(pts)
            deltas = [rows[i + 1]["z"] - rows[i]["z"] for i in range(len(rows) - 1)]
            spikes = sum(1 for d in deltas if abs(d) > 0.1)
            jitter[f"dx_{dx:+.3f}"] = {
                "spike_count": spikes,
                "z_min": round(min(x["z"] for x in rows), 3),
                "z_max": round(max(x["z"] for x in rows), 3),
                "worst_step": round(max((abs(d) for d in deltas), default=0.0), 4),
            }
        drops = [_settle_and_rest(s, PLAYER, _bearing_xy(180.0, rr)) for rr in (88.7, 89.0, 89.5)]
        for d in drops:
            # The bank surface here, taken from a line that is NOT on the symmetry
            # edge, so the expectation itself is not built from the suspect ray.
            d["reference_ray_z_off_centreline"] = round(
                s.surface_z(*(_bearing_xy(180.0, d["r"])[0] + 0.05, _bearing_xy(180.0, d["r"])[1])),
                4,
            )
            d["rests_on_the_bank"] = (
                abs(d["rest_body_z"] - d["reference_ray_z_off_centreline"]) < 0.6
            )
        edge_only = set(affected) <= {"bearing_180.0"}
        jitter_closes = all(v["spike_count"] == 0 for k, v in jitter.items() if k != "dx_+0.000")
        cars_supported = all(d["rests_on_the_bank"] for d in drops)
        verdict = (
            "ray_edge_artifact_not_a_gap"
            if (edge_only and jitter_closes and cars_supported)
            else "UNEXPLAINED - treat as a real surface defect"
        )
        r["outboard_anomaly_map"] = {
            "window_r": list(ANOMALY_WINDOW),
            "step_m": 0.02,
            "bearings": amap,
            "bearings_affected": sorted(affected),
            "bearings_clean": sorted(set(amap) - set(affected)),
            "lateral_jitter_on_the_centreline": jitter,
            "car_drop_tests": drops,
            "verdict": verdict,
            "note": "OUTBOARD of the r 88.5 seam, on the bank climb - adjacent to the deck-rear "
            "junction, not the junction itself, which reads flush on every line.",
        }
        s.check(
            verdict == "ray_edge_artifact_not_a_gap",
            "the z anomaly outboard of the deck rear is NOT explained as a ray-on-edge artifact: "
            "either it spans more than the exact symmetry line, or a 5 mm sidestep does not "
            "close it, or a car does not rest on the bank there",
            {"affected": sorted(affected), "jitter": jitter, "drops": drops},
        )

        deck_z = s.surface_z(*_bearing_xy(180.0, 84.0))
        seam_z = s.surface_z(*_bearing_xy(180.0, JUNCTION_R))
        r["junction_heights"] = {
            "deck_top_z_at_r84": round(deck_z, 4),
            "seam_z_at_r88_5": round(seam_z, 4),
            "deck_to_seam_m": round(seam_z - deck_z, 4),
        }

        # --- 2. driven, both directions, crawl and speed ----------------------
        drv = Driver(s, PLAYER)
        drv.calibrate(_bearing_xy(90.0, 40.0), 0.0)
        # The car's own half-length, so "did the wheels reach the seam" is asked
        # about the CAR and not about its reference point. Boot 1 asked about the
        # ref point and recorded "never crossed" for a car whose nose was already
        # a metre past the seam and buried in the bank climb beyond it.
        oobb = s.lua(
            f"local v = scenetree.findObject({PLAYER!r}); local h = v:getSpawnWorldOOBB():getHalfExtents(); "
            "return jsonEncode({hx = h.x, hy = h.y, hz = h.z})"
        )
        half_len = float(oobb["hy"])
        r["player_half_length_m"] = round(half_len, 3)
        crossings: dict[str, Any] = {}
        # Outbound stops on the bank by design (an authored ~30 % climb at the
        # seam steepening to the crest, and G2 measured the bank un-climbable
        # past r ~88.2 from below), so the line is asked only to put the car
        # ACROSS the seam, never to summit.
        for label, speed in (("crawl", 1.1), ("speed", 8.0)):
            for direction in ("outbound", "inbound"):
                if direction == "outbound":
                    start_r, waypoints, target = (
                        82.0,
                        [_bearing_xy(180.0, 82.0 + 0.5 * i) for i in range(1, 17)],
                        90.0,
                    )
                    heading = 180.0
                    stop = lambda p: p["r"] >= 89.8
                else:
                    start_r, waypoints, target = (
                        89.0,
                        [_bearing_xy(180.0, 89.0 - 0.5 * i) for i in range(1, 17)],
                        81.0,
                    )
                    heading = 0.0
                    stop = lambda p: p["r"] <= 81.2
                xy = _bearing_xy(180.0, start_r)
                s.teleport(PLAYER, xy, heading, z=s.surface_z(*xy) + 0.6, reset=True)
                s.step(20)
                key = f"{label}_{direction}"
                line = drv.line(
                    key,
                    waypoints,
                    speed,
                    max_sim=90.0,
                    reach=1.2,
                    stop_fn=stop,
                    coast_after_stop=False,
                )
                band_rows = [
                    x for x in line["trace"] if JUNCTION_BAND[0] <= x["r"] <= JUNCTION_BAND[1]
                ]
                nose_max_r = round(float(line["max_r"]) + half_len, 2)
                ref_traversed = (
                    max(x["r"] for x in line["trace"])
                    > JUNCTION_R
                    > min(x["r"] for x in line["trace"])
                )
                crossings[key] = {
                    "speed_target": speed,
                    "direction": direction,
                    "outcome": line["outcome"],
                    "airborne_s": line["airborne_s"],
                    "min_uz": line["min_uz"],
                    "max_r": line["max_r"],
                    "min_r": line["min_r"],
                    "nose_max_r": nose_max_r,
                    # Outbound the car can only ever put its NOSE over the seam before
                    # the bank stops it; inbound the reference point itself traverses.
                    "crossed_the_seam": (nose_max_r >= JUNCTION_R)
                    if direction == "outbound"
                    else ref_traversed,
                    "ref_point_traversed_seam": ref_traversed,
                    "band_samples": len(band_rows),
                    "band_max_abs_vz": round(
                        max((abs(x["vz"]) for x in band_rows), default=0.0), 3
                    ),
                    "band_z_span_m": round(
                        max((x["z"] for x in band_rows), default=0.0)
                        - min((x["z"] for x in band_rows), default=0.0),
                        3,
                    ),
                    "band_airborne_samples": sum(1 for x in band_rows if x["air"]),
                    "band_min_uz": round(min((x["uz"] for x in band_rows), default=1.0), 3),
                    "stall_events": [e for e in line["events"] if e["type"].startswith("stall")],
                    "other_events": [
                        e for e in line["events"] if not e["type"].startswith("stall")
                    ],
                    "damage_gain": round(
                        float(line["final"]["damage"]) - float(line["start"]["damage"]), 1
                    )
                    if line["final"] and line["start"]
                    else None,
                }
        r["junction_crossings"] = crossings
        for key, block in crossings.items():
            s.check(
                block["crossed_the_seam"],
                f"{key}: the car never actually crossed the r 88.5 seam, so nothing was tested",
                {k: v for k, v in block.items() if k != "stall_events"},
            )
            s.check(
                block["band_airborne_samples"] == 0 and block["airborne_s"] == 0.0,
                f"{key}: the car went airborne crossing the junction",
                block,
            )
            s.check(
                block["band_min_uz"] > 0.8, f"{key}: the car tipped crossing the junction", block
            )
            # A stall whose NOSE had not yet reached the seam is a lip on the deck;
            # a stall with the nose already outboard is the authored bank climb (or
            # the outboard anomaly mapped above) and is recorded with its position,
            # not blamed on the junction.
            blocked_before_seam = [
                e
                for e in block["stall_events"]
                if e["type"] == "stall" and float(e.get("r", 0.0)) + half_len < JUNCTION_R
            ]
            s.check(
                not blocked_before_seam,
                f"{key}: the car was stopped before its nose even reached the seam - that is a "
                "lip on the deck, not a grade",
                {"stalls": blocked_before_seam, "half_len": half_len},
            )
            s.check(
                not [e for e in block["other_events"] if e["type"] == "rollover"],
                f"{key}: rollover crossing the junction",
                block["other_events"],
            )

        # --- 3. the seam, photographed at a grazing angle ---------------------
        west, east = _bearing_xy(176.76, JUNCTION_R), _bearing_xy(183.24, JUNCTION_R)
        s.teleport(PLAYER, _bearing_xy(180.0, 84.0), 180.0)
        s.park(PLAYER)
        s.shot(
            "seam_grazing",
            (east[0] + 1.5, east[1] + 1.0, deck_z + 0.45),
            (west[0], west[1], deck_z + 0.20),
            "along the deck-rear seam at a grazing angle - the v3.7 wood/iron interleave "
            "would read as a shimmering sliver line here",
        )
        s.shot(
            "seam_driver_eye",
            (*_bearing_xy(180.0, 85.5), deck_z + 1.25),
            (*_bearing_xy(180.0, 91.0), deck_z + 1.05),
            "driver's seat on the deck about to cross the rear junction",
        )
        s.shot(
            "seam_from_outboard",
            (*_bearing_xy(180.0, 96.0), C[2] + 3.0),
            (*_bearing_xy(180.0, 88.5), deck_z + 0.3),
            "a player's eye outboard on the bank looking back in at the junction",
        )
        s.set_option("ai_enabled", True)
    assert not s.report.get("problems"), s.report["problems"]


@pytest.mark.beamng_live
def test_g14_round_regression(tmp_path: Path) -> None:
    """G14.3 - one full round on the v3.8 dist: field 6, props 16, boom, return, fireworks."""

    with _session("G14_3", tmp_path, watchdog_seconds=2400.0) as s:
        r = s.report
        r["hot_potato_serial"] = r["locks"]["hot_potato"]["serial"]
        s.set_option("ai_enabled", False)
        for n in AI:
            s.park(n)
        s.set_options(
            {
                "fuse_base_seconds": 30,
                "fuse_sigma_seconds": 0,
                "fuse_min_seconds": 25,
                "fuse_max_seconds": 35,
                "cue_window_seconds": 15,
            }
        )
        stats = s.start_round(PLAYER)
        r["round_start"] = {
            "field": stats.get("field"),
            "props_excluded": stats.get("props_excluded"),
            "phase": stats.get("phase"),
        }
        s.check(int(stats.get("field", -1)) == 6, "field != 6 on the v3.8 dist", r["round_start"])
        s.check(
            int(stats.get("props_excluded", -1)) == 16,
            "props_excluded != 16 on the v3.8 dist",
            r["round_start"],
        )
        pad = s.pad
        s.shot(
            "pickup",
            (pad[0] + 16.0, pad[1] - 14.0, pad[2] + 6.0),
            (pad[0], pad[1], pad[2] + 2.0),
            "the round live on the v3.8 dist",
        )
        s.teleport(AI[0], (pad[0], pad[1] + 24.0), 180.0)
        s.control(AI[0], steering=0.0, throttle=1.0, brake=0.0, parkingbrake=0.0)
        s.vehicle(AI[0]).set_velocity(10.0, 1.0)
        rammer_id = int(s.probe(AI[0])["id"])
        transferred = True
        try:
            s.step_until(
                lambda: int(s.stats().get("carrier") or -1) == rammer_id,
                calls=90,
                note="ram transfer",
            )
        except AssertionError:
            transferred = False
        s.control(AI[0], steering=0.0, throttle=0.0, brake=1.0, parkingbrake=1.0)
        s.check(transferred, "the ram never transferred the potato", {"rammer": rammer_id})
        s.shot(
            "ram",
            (pad[0] + 15.0, pad[1] + 20.0, pad[2] + 6.0),
            (pad[0], pad[1] + 8.0, pad[2] + 1.5),
            "the ram transfer",
        )
        victim: dict[str, int] = {}
        boomed = True

        def _boom_reached() -> bool:
            st = s.stats()
            carrier = int(st.get("carrier") or -1)
            if st.get("phase") == "live" and carrier >= 0:
                victim["id"] = carrier
            return st.get("phase") == "boom"

        try:
            s.step_until(_boom_reached, calls=300, note="fuse to boom")
        except AssertionError:
            boomed = False
        s.check(boomed, "the fuse never detonated", s.stats())
        if boomed:
            names = s.names_by_id()
            victim_name = names.get(victim.get("id", -1), AI[0])
            peak, anchor = 0.0, None
            for _ in range(10):
                s.step(6)
                p = s.probe(victim_name)
                peak = max(peak, p["speed"])
                anchor = anchor or (p["x"], p["y"], p["z"])
            r["boom"] = {
                "peak_speed": round(peak, 2),
                "victim": victim_name,
                "victim_id": victim.get("id"),
                "rammer_id": rammer_id,
            }
            s.check(peak > 6.0, "the detonation never moved the wreck", r["boom"])
            s.shot(
                "boom",
                (anchor[0] + 11.0, anchor[1] - 11.0, anchor[2] + 5.0),
                (anchor[0], anchor[1], anchor[2] + 2.0),
                "the detonation",
            )
            returned = True
            try:
                s.step_until(
                    lambda: s.stats().get("phase") in ("return", "idle"),
                    calls=200,
                    note="return flight",
                )
            except AssertionError:
                returned = False
            s.check(returned, "the boom never handed over to the return flight", s.stats())
            after = s.stats()
            r["fireworks"] = {"fw_stage": after.get("fw_stage")}
            s.check(after.get("fw_stage", "") != "", "no winner fireworks after the boom", after)
            try:
                s.step_until(
                    lambda: s.stats().get("fw_stage") in ("burst", "finale"), calls=60, note="burst"
                )
                s.shot(
                    "fireworks",
                    (pad[0], pad[1] + 72.0, pad[2] + 44.0),
                    (pad[0], pad[1], pad[2] + 56.0),
                    "winner fireworks over the arch",
                )
            except AssertionError:
                s.problem("the fireworks never reached a burst stage", s.stats())
            try:
                s.step_until(lambda: s.stats().get("phase") == "idle", calls=300, note="idle")
                s.shot(
                    "idle",
                    (pad[0] + 9.0, pad[1] - 9.0, pad[2] + 1.6),
                    (pad[0], pad[1], pad[2] + 6.5),
                    "the potato home on its perch",
                )
            except AssertionError:
                s.problem("the return flight never settled to idle", s.stats())
        v = s.arena()["valve"]
        opts = s.options()
        r["after_round"] = {
            "radius": opts["arena_radius_m"],
            "valve_stage": v["stage"],
            "in_round": v["in_round"],
        }
        s.check(
            abs(float(opts["arena_radius_m"]) - 91.4) < 1e-6,
            "the radius was not restored at round end",
            r["after_round"],
        )
    assert not s.report.get("problems"), s.report["problems"]
