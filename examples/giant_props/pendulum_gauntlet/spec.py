"""Wrecking Ball Pendulum Gauntlet — authored constants for Blender + runtime.

A 40 m elevated bridge of squishy inflated mats with entry/exit ramps, and
four steel gantries overhead, each hanging a genuinely physics-driven
wrecking ball: heavy free-node octahedron clusters on cable chains,
authored displaced +/-40 degrees so gravity swings them across the lane
from the moment the prop spawns. The car has to time the gaps while the
wobbly inflatable deck bounces underneath.

Everything is ONE connected cage: fixed trusses and gantries, free sprung
deck/bumper nodes, and free cable/ball nodes. The wrecking balls collide
with real vehicles through their own collision triangles; resetting the
prop re-cocks the pendulums to full amplitude.
"""

MOD_ID = "ericrolph_pendulum_gauntlet"
DISPLAY_NAME = "Wrecking Ball Pendulum Gauntlet"
VALUE_DOLLARS = 45000
ZIP_BASENAME = "pendulum_gauntlet_ericrolph.zip"

# Authored frame: right-handed, meters, Z-up, +Y drive direction.
DECK_TOP_Z = 3.0
DECK_HALF_WIDTH = 1.8
BUMPER_X = 2.2
BUMPER_Z = 3.55
SUBFRAME_Z = 2.2
# 2 m stations: with 4 m bays and 60 kN/m supports a car landing on the deck
# sank through to the subframe (proven live 2026-07-22, same failure mode as
# the bouncy castle's original coarse floor).
STATION_YS = [-20.0 + 2.0 * i for i in range(21)]
RAMP_GROUND_Y = 28.0
GANTRY_YS = [-15.0, -5.0, 5.0, 15.0]
GANTRY_POST_X = 4.0
GANTRY_TOP_Z = 10.5
ANCHOR_Z = 10.4
CABLE_LENGTH = 6.4
BALL_RADIUS = 1.1
SWING_ANGLES_DEG = [40.0, -40.0, 40.0, -40.0]

PALETTE = {
    f"{MOD_ID}_mat_red": {
        "texture": {"family": "pvc_weave", "params": {"base": [0.82, 0.18, 0.14]}},
        "color": [0.82, 0.18, 0.14, 1.0],
        "metallic": 0.0,
        "roughness": 0.45,
    },
    f"{MOD_ID}_mat_blue": {
        "texture": {"family": "pvc_weave", "params": {"base": [0.16, 0.36, 0.75]}},
        "color": [0.16, 0.36, 0.75, 1.0],
        "metallic": 0.0,
        "roughness": 0.45,
    },
    f"{MOD_ID}_bumper_yellow": {
        "texture": {"family": "pvc_weave", "params": {"base": [0.9, 0.72, 0.1], "seams": False}},
        "color": [0.95, 0.78, 0.12, 1.0],
        "metallic": 0.0,
        "roughness": 0.45,
    },
    f"{MOD_ID}_steel": {
        "texture": {"family": "steel_worn"},
        "color": [0.5, 0.53, 0.57, 1.0],
        "metallic": 0.85,
        "roughness": 0.35,
    },
    f"{MOD_ID}_hazard": {
        "texture": {"family": "hazard_chevron"},
        "color": [0.9, 0.55, 0.08, 1.0],
        "metallic": 0.1,
        "roughness": 0.5,
    },
    f"{MOD_ID}_ball_dark": {
        "texture": {"family": "forged_ball"},
        "color": [0.16, 0.16, 0.18, 1.0],
        "metallic": 0.7,
        "roughness": 0.4,
    },
    f"{MOD_ID}_ramp_asphalt": {
        "texture": {"family": "asphalt"},
        "color": [0.16, 0.16, 0.17, 1.0],
        "metallic": 0.0,
        "roughness": 0.9,
    },
}

TRIGGERS = {
    "bridge_zone": {
        "mode": "Overlaps",
        "center": [0.0, 0.0, DECK_TOP_Z + 2.2],
        "dimensions": [7.0, 44.0, 5.0],
    },
    "gate_south": {
        "mode": "Overlaps",
        "center": [0.0, -22.5, DECK_TOP_Z + 1.6],
        "dimensions": [5.4, 4.0, 3.6],
    },
    "gate_north": {
        "mode": "Overlaps",
        "center": [0.0, 22.5, DECK_TOP_Z + 1.6],
        "dimensions": [5.4, 4.0, 3.6],
    },
}

EFFECTS = {}

BEHAVIOR = {
    "camera_distance": 44.0,
    "run_timeout_seconds": 90.0,
    # Auto re-cock: swings decay over minutes; when the balls have nearly
    # settled and nobody is on or near the bridge, reset the prop so the
    # gauntlet is never found dead (player report 2026-07-23).
    "recock_amplitude_m": 1.2,
    "recock_window_seconds": 8.0,
}

LUA_BEHAVIOR = r"""
local OPPOSITE = {gate_south = "gate_north", gate_north = "gate_south"}

-- Each rigid pendulum part follows its physics ball: read the ball centre
-- node's live position and swing the part about the anchor to match. The
-- flexbody deliberately carries no cable/ball geometry (skinning smeared it
-- into morphing blades).
local function posePendulums(state)
  local prop = exactVehicle(state.propId)
  if not prop or not state.origin then return end
  local propPosition = prop:getPosition()
  local ex = toWorldDir(state, vec3(1, 0, 0))
  for index, pendulum in ipairs(B.pendulums or {}) do
    local cid = resolveNodeCid(state, pendulum.node)
    local okNode, offset = pcall(function()
      return cid and prop:getNodePosition(cid) or nil
    end)
    if okNode and offset then
      local ballWorld = propPosition + offset
      local anchorWorld = toWorldPoint(state, pendulum.anchor)
      local delta = ballWorld - anchorWorld
      local dx = delta:dot(ex)
      local dz = delta.z
      if math.abs(dx) > 0.001 or math.abs(dz) > 0.001 then
        local phi = math.atan2(-dx, -dz)
        setPartPose(
          state,
          "pendulum_" .. (index - 1),
          nil,
          axisAngle(vec3(0, 1, 0), phi)
        )
      end
    end
  end
end

behavior.init = function(state)
  state.behavior.clock = 0
  state.behavior.runs = {}
  posePendulums(state)
end

behavior.reset = function(state)
  behavior.init(state)
  showMessage("Pendulums re-cocked. DODGE!", 2.0)
end

behavior.onEnter = function(state, zone, vehicle)
  if zone == "bridge_zone" then return end
  local b = state.behavior
  local id = vehicle:getId()
  local run = b.runs[id]
  if run and OPPOSITE[run.from] == zone
    and (b.clock - run.at) <= B.run_timeout_seconds then
    b.runs[id] = nil
    showMessage("GAUNTLET CLEARED! Nice dodging.", 2.4)
    emitEvent(state, "I", "gauntlet_cleared", {
      subject_id = id,
      seconds = b.clock - run.at,
    })
    return
  end
  b.runs[id] = {from = zone, at = b.clock}
  showMessage("DODGE THE WRECKING BALLS!", 2.2)
  emitEvent(state, "I", "gauntlet_entered", {subject_id = id, gate = zone})
end

behavior.onSubjectGone = function(state, vehicleId, reason)
  state.behavior.runs[vehicleId] = nil
end

local function occupied(state)
  return zoneCount(state, "bridge_zone") > 0
    or zoneCount(state, "gate_south") > 0
    or zoneCount(state, "gate_north") > 0
end

local function updateRecock(state, dtSim)
  local b = state.behavior
  local prop = exactVehicle(state.propId)
  local first = B.pendulums and B.pendulums[1]
  if not prop or not first then return end
  -- Warned re-cock in progress: count it down and fire regardless of
  -- occupancy. The authored ball poses are outboard of the deck (x +/-4.1,
  -- z ~5.5), so a reset cannot teleport a ball into a car on the bridge —
  -- and players parked mid-bridge were finding the gauntlet permanently
  -- dead under the old nobody-around gate (report 2026-07-23).
  if b.recockCountdown then
    b.recockCountdown = b.recockCountdown - dtSim
    if b.recockCountdown <= 0 then
      b.recockCountdown = nil
      local okReset = pcall(function() prop:requestReset(RESET_PHYSICS) end)
      if okReset then
        emitEvent(state, "I", "pendulums_recocked", {})
      end
    end
    return
  end
  local firstCid = resolveNodeCid(state, first.node)
  local okNode, offset = pcall(function()
    return firstCid and prop:getNodePosition(firstCid) or nil
  end)
  if not okNode or not offset then return end
  local ex = toWorldDir(state, vec3(1, 0, 0))
  local swing = math.abs(offset:dot(ex))
  b.windowMax = math.max(b.windowMax or 0, swing)
  b.windowElapsed = (b.windowElapsed or 0) + dtSim
  if b.windowElapsed < B.recock_window_seconds then return end
  local settled = b.windowMax < B.recock_amplitude_m
  b.windowMax = 0
  b.windowElapsed = 0
  if settled then
    if occupied(state) then
      showMessage("Re-cocking the wrecking balls in 3...", 2.6)
      b.recockCountdown = 3.0
    else
      b.recockCountdown = 0.01
    end
  end
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  b.clock = b.clock + dtSim
  for id, run in pairs(b.runs) do
    if (b.clock - run.at) > B.run_timeout_seconds then
      b.runs[id] = nil
    end
  end
  posePendulums(state)
  updateRecock(state, dtSim)
end
"""
