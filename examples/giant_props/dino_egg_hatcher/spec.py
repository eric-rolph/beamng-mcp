"""Dino Egg Hatcher — authored constants for Blender + runtime.

A giant speckled egg in a straw nest with a cracked-open doorway. Drive
inside and the shell shards start to rattle (anticipation). After a few
wobbling seconds the egg HATCHES: seventeen curved shell fragments burst
outward in ballistic arcs, dust erupts, and the car launches skyward like
a newborn dino. The shards cartoon-rewind back together to re-arm.

2026-07-23 player round 5: nearly the ENTIRE egg now fragments. Only a low
cracked-open cup (jagged rim ~2.3 m, with the doorway notch) stays static
and collidable; everything above it — a band of six wall pieces, the ring,
and the crown caps — is kinematic shards, so the hatch strips the egg down
to its cup like a real cracked egg.
"""

import math

MOD_ID = "ericrolph_dino_egg_hatcher"
DISPLAY_NAME = "Dino Egg Hatcher"
VALUE_DOLLARS = 26000
ZIP_BASENAME = "dino_egg_hatcher_ericrolph.zip"

# Authored frame: right-handed, meters, Z-up, +Y drive direction; the crack
# doorway faces -Y.
EGG_CENTER_Z = 3.6
EGG_RADIUS = 3.1
EGG_SCALE_Z = 1.32
SHELL_RING_RADIUS = 2.95
# The static remainder is just a cracked cup: collision ring tops out at
# the jagged rim. Everything above CUP_RIM_Z flies on hatch.
CUP_RIM_Z = 2.3
SHELL_Z_LEVELS = (0.4, CUP_RIM_Z)
DOOR_ANGLE_DEG = 270.0  # -Y
SHARD_RING_RADIUS = 1.9
SHARD_RING_Z = 5.5
# Ten curved shell fragments cut from a real dome shell (2026-07-23 player
# feedback: the old chunky boxes were "too blocky" — these are genuine
# sphere-shell pieces split by irregular wedges, so the burst reads as a
# cracked eggshell). Ring wedges: (start_deg, end_deg); caps split the
# crown above z_split.
SHARD_RING_WEDGES = [
    (0.0, 52.0),
    (52.0, 118.0),
    (118.0, 165.0),
    (165.0, 228.0),
    (228.0, 275.0),
    (275.0, 322.0),
    (322.0, 360.0),
]
SHARD_CAP_WEDGES = [(15.0, 130.0), (130.0, 250.0), (250.0, 375.0)]
SHARD_CAP_Z = 6.35
# Mid-wall band (CUP_RIM_Z..5.0): seven more pieces, seams staggered off
# the ring wedges so the cracks brick-lace instead of lining up. The three
# wedges spanning the doorway get the door arch subtracted so the entrance
# stays open at rest.
SHARD_BAND_WEDGES = [
    (20.0, 80.0),
    (80.0, 140.0),
    (140.0, 200.0),
    (200.0, 250.0),
    (250.0, 290.0),
    (290.0, 340.0),
    (340.0, 380.0),
]
SHARD_BAND_DOOR = {3, 4, 5}  # 0-based indices of wedges crossing the -Y arch

PALETTE = {
    f"{MOD_ID}_eggshell": {
        "texture": {"family": "eggshell"},
        "color": [0.93, 0.9, 0.8, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
        "double_sided": True,
    },
    f"{MOD_ID}_crack_white": {
        "color": [0.98, 0.97, 0.93, 1.0],
        "metallic": 0.0,
        "roughness": 0.4,
    },
    f"{MOD_ID}_spot_green": {
        "color": [0.25, 0.55, 0.25, 1.0],
        "metallic": 0.0,
        "roughness": 0.55,
    },
    f"{MOD_ID}_spot_teal": {
        "color": [0.15, 0.5, 0.5, 1.0],
        "metallic": 0.0,
        "roughness": 0.55,
    },
    f"{MOD_ID}_nest_straw": {
        "texture": {"family": "straw"},
        "color": [0.78, 0.62, 0.22, 1.0],
        "metallic": 0.0,
        "roughness": 0.75,
    },
    f"{MOD_ID}_nest_dark": {
        "texture": {"family": "straw", "params": {"base": [0.5, 0.37, 0.14]}},
        "color": [0.45, 0.33, 0.12, 1.0],
        "metallic": 0.0,
        "roughness": 0.85,
    },
}

TRIGGERS = {
    "egg_zone": {
        "mode": "Contains",
        # Bottom sits 0.4 m below the nest floor plate (top at z 0.4):
        # settling vehicle OOBBs dip below the surface, and without the
        # allowance Contains flaps enter/exit (proven live 2026-07-22).
        "center": [0.0, 0.3, 2.0],
        "dimensions": [5.0, 5.4, 4.0],
    },
    "nest_zone": {
        "mode": "Overlaps",
        "center": [0.0, -5.0, 1.6],
        "dimensions": [9.0, 9.0, 3.2],
    },
}

EFFECTS = {
    "hatch_dust_top": {
        "emitter": "BNGP_2",
        "position": [0.0, 0.0, 5.4],
        "direction": [0.0, 0.0, 1.0],
    },
    "hatch_dust_l": {
        "emitter": "BNGP_2",
        "position": [-2.4, 0.0, 3.2],
        "direction": [-0.8, 0.0, 0.6],
    },
    "hatch_dust_r": {
        "emitter": "BNGP_2",
        "position": [2.4, 0.0, 3.2],
        "direction": [0.8, 0.0, 0.6],
    },
}

BEHAVIOR = {
    "camera_distance": 30.0,
    "wobble_seconds": 2.5,
    "fly_seconds": 1.1,
    "sink_seconds": 1.4,
    "open_seconds": 9.0,
    "reassemble_seconds": 1.2,
    "launch_up_mps": 30.0,
    "launch_forward_mps": 6.0,
    "shard_fly_distance": 8.0,
    "shard_rise": 4.5,
    "shard_dirs": [
        [
            round(math.cos(math.radians((a + b) / 2)), 6),
            round(math.sin(math.radians((a + b) / 2)), 6),
        ]
        for a, b in SHARD_RING_WEDGES
    ]
    + [
        [
            round(0.55 * math.cos(math.radians((a + b) / 2)), 6),
            round(0.55 * math.sin(math.radians((a + b) / 2)), 6),
        ]
        for a, b in SHARD_CAP_WEDGES
    ]  # the top caps drift off at a lazy angle
    + [
        [
            round(0.9 * math.cos(math.radians((a + b) / 2)), 6),
            round(0.9 * math.sin(math.radians((a + b) / 2)), 6),
        ]
        for a, b in SHARD_BAND_WEDGES
    ],  # wall band pieces kick outward a touch flatter
    "shard_names": [
        f"shard_{index + 1}"
        for index in range(len(SHARD_RING_WEDGES) + len(SHARD_CAP_WEDGES) + len(SHARD_BAND_WEDGES))
    ],
}

LUA_BEHAVIOR = r"""
local SHARD_NAMES = B.shard_names

local function shardsAtRest(state)
  for _, name in ipairs(SHARD_NAMES) do
    setPartPose(state, name, vec3(0, 0, 0), quat(0, 0, 0, 1))
  end
end

local function dustActive(state, active)
  setEffectActive(state, "hatch_dust_top", active)
  setEffectActive(state, "hatch_dust_l", active)
  setEffectActive(state, "hatch_dust_r", active)
end

behavior.init = function(state)
  state.behavior.phase = "idle"
  state.behavior.elapsed = 0
  state.behavior.clock = 0
  shardsAtRest(state)
end

behavior.reset = function(state)
  behavior.init(state)
  dustActive(state, false)
end

behavior.onEnter = function(state, zone, vehicle)
  local b = state.behavior
  if zone == "nest_zone" and b.phase == "idle" then
    showMessage("Something is sleeping in there... drive in through the crack!", 2.6)
  elseif zone == "egg_zone" and b.phase == "idle" then
    b.phase = "wobble"
    b.elapsed = 0
    dustActive(state, true)
    showMessage("The egg is wobbling...", 2.0)
    emitEvent(state, "I", "egg_wobbling", {subject_id = vehicle:getId()})
  end
end

behavior.onExit = function(state, zone, vehicleId)
  local b = state.behavior
  if zone == "egg_zone" and b.phase == "wobble"
    and zoneCount(state, "egg_zone") == 0 then
    b.phase = "idle"
    b.elapsed = 0
    dustActive(state, false)
    shardsAtRest(state)
    showMessage("The egg went back to sleep.", 1.8)
    emitEvent(state, "I", "egg_wobble_aborted", {subject_id = vehicleId})
  end
end

behavior.onSubjectGone = function(state, vehicleId, reason)
  local b = state.behavior
  if b.phase == "wobble" and zoneCount(state, "egg_zone") == 0 then
    b.phase = "idle"
    b.elapsed = 0
    dustActive(state, false)
    shardsAtRest(state)
  end
end

local function poseShardsFlight(state, progress, sinking)
  for index, name in ipairs(SHARD_NAMES) do
    local dir = B.shard_dirs[index]
    local dist = B.shard_fly_distance * (1 - (1 - progress) * (1 - progress))
    local rise = B.shard_rise * progress - 6.5 * progress * progress
    if sinking then rise = rise - sinking * 4.0 end
    local tumbleAxis = vec3(-dir[2], dir[1], 0.15)
    setPartPose(
      state,
      name,
      vec3(dir[1] * dist, dir[2] * dist, rise),
      axisAngle(tumbleAxis, progress * (2.5 + index * 0.6) + (sinking or 0) * 1.5)
    )
  end
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  b.clock = b.clock + dtSim
  b.elapsed = b.elapsed + dtSim
  if b.phase == "wobble" then
    for index, name in ipairs(SHARD_NAMES) do
      local dir = B.shard_dirs[index]
      local rattle = math.sin(b.clock * 24 + index * 1.7) * 0.05
      local hop = math.abs(math.sin(b.clock * 17 + index)) * 0.07
      setPartPose(
        state,
        name,
        vec3(dir[1] * rattle, dir[2] * rattle, hop),
        axisAngle(vec3(-dir[2], dir[1], 0), rattle * 0.8)
      )
    end
    if b.elapsed >= B.wobble_seconds then
      local vehicle = firstOccupant(state, "egg_zone")
      if not vehicle then
        b.phase = "idle"
        b.elapsed = 0
        dustActive(state, false)
        shardsAtRest(state)
        return
      end
      local up = toWorldDir(state, vec3(0, 0, 1))
      local forward = toWorldDir(state, vec3(0, 1, 0))
      local velocity = up * B.launch_up_mps + forward * B.launch_forward_mps
      showMessage("RAWR! IT HATCHED!", 2.0)
      if launchSubject(state, vehicle, velocity) then
        emitEvent(state, "I", "egg_hatched", {subject_id = vehicle:getId()})
        b.phase = "fly"
        b.elapsed = 0
      else
        b.phase = "idle"
        b.elapsed = 0
        dustActive(state, false)
        shardsAtRest(state)
      end
    end
  elseif b.phase == "fly" then
    local t = math.min(1, b.elapsed / B.fly_seconds)
    poseShardsFlight(state, t, nil)
    if t >= 1 then
      b.phase = "sink"
      b.elapsed = 0
      dustActive(state, false)
    end
  elseif b.phase == "sink" then
    local t = math.min(1, b.elapsed / B.sink_seconds)
    poseShardsFlight(state, 1, t)
    if t >= 1 then
      b.phase = "open"
      b.elapsed = 0
    end
  elseif b.phase == "open" then
    if b.elapsed >= B.open_seconds then
      b.phase = "reassemble"
      b.elapsed = 0
      showMessage("The egg is reassembling...", 2.0)
    end
  elseif b.phase == "reassemble" then
    local t = math.min(1, b.elapsed / B.reassemble_seconds)
    local back = 1 - t
    poseShardsFlight(state, back, (1 - t) * 0.6)
    if t >= 1 then
      shardsAtRest(state)
      b.phase = "idle"
      b.elapsed = 0
      emitEvent(state, "I", "egg_rearmed", {})
    end
  end
end
"""
