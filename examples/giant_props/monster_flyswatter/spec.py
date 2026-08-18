"""Monster Flyswatter — authored constants shared by Blender and the runtime.

A giant flyswatter on a low hinge beside a painted swat lane. Driving into
the lane wakes it: the raised swatter trembles (anticipation), slams down
across the lane, holds, then rises slowly to re-arm. Any vehicle inside the
kill zone at slam time is swatted across the map like a bug. The head
deliberately does not cover the outer lane edge — hug it to survive.
"""

MOD_ID = "ericrolph_monster_flyswatter"
DISPLAY_NAME = "Monster Flyswatter"
VALUE_DOLLARS = 18000
ZIP_BASENAME = "monster_flyswatter_ericrolph.zip"

# Authored frame: right-handed, meters, Z-up, +Y drive direction.
LANE_HALF_X = 3.2
LANE_HALF_Y = 10.0
# Nearly flush with the terrain (was 0.12, which read as a floating slab).
LANE_TOP_Z = 0.03
PEDESTAL_MIN = (4.8, -1.7, 0.0)
PEDESTAL_MAX = (8.2, 1.7, 1.5)
PIVOT = (6.5, 0.0, 1.4)
ARM_LENGTH = 7.2
HEAD_CENTER_OFFSET = -7.2  # along -X from the pivot at slam pose
HEAD_WIDTH = 6.4  # X extent of the head at slam
HEAD_LENGTH = 6.2  # Y extent
REST_ANGLE_DEG = 72.0
SLAM_ANGLE_DEG = -6.0

PALETTE = {
    f"{MOD_ID}_plastic_red": {
        "texture": {
            "family": "painted_metal",
            "params": {"base": [0.83, 0.12, 0.1], "rough": 0.38, "peel": 0.8},
        },
        "color": [0.83, 0.12, 0.1, 1.0],
        "metallic": 0.05,
        "roughness": 0.35,
    },
    f"{MOD_ID}_mesh_green": {
        "texture": {"family": "mesh_weave", "params": {"base": [0.2, 0.62, 0.28]}},
        "color": [0.2, 0.62, 0.28, 1.0],
        "metallic": 0.0,
        "roughness": 0.55,
        "double_sided": True,
    },
    f"{MOD_ID}_steel": {
        "texture": {"family": "steel_worn"},
        "color": [0.55, 0.57, 0.6, 1.0],
        "metallic": 0.85,
        "roughness": 0.35,
    },
    f"{MOD_ID}_asphalt": {
        "texture": {"family": "asphalt"},
        "color": [0.15, 0.15, 0.16, 1.0],
        "metallic": 0.0,
        "roughness": 0.9,
    },
    f"{MOD_ID}_paint_white": {
        "color": [0.88, 0.88, 0.86, 1.0],
        "metallic": 0.0,
        "roughness": 0.6,
    },
    f"{MOD_ID}_hazard_yellow": {
        "texture": {"family": "hazard_chevron"},
        "color": [0.95, 0.75, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
}

TRIGGERS = {
    "lane_zone": {
        "mode": "Overlaps",
        "center": [0.0, -7.0, 1.8],
        "dimensions": [2 * LANE_HALF_X, 5.0, 3.6],
    },
    "kill_zone": {
        "mode": "Overlaps",
        "center": [-0.7, 0.0, 1.7],
        "dimensions": [HEAD_WIDTH, HEAD_LENGTH, 3.2],
    },
}

EFFECTS = {
    "slam_dust": {
        "emitter": "BNGP_2",
        "position": [-0.7, 0.0, 0.6],
        "direction": [0.0, 0.0, 1.0],
    },
}

BEHAVIOR = {
    "camera_distance": 34.0,
    "rest_angle_deg": REST_ANGLE_DEG,
    "slam_angle_deg": SLAM_ANGLE_DEG,
    "tremble_seconds": 0.5,
    "slam_seconds": 0.22,
    "hold_seconds": 0.8,
    "rise_seconds": 2.2,
    "cooldown_seconds": 1.0,
    "swat_window_seconds": 0.3,
    "swat_speed_mps": 40.0,
    "swat_dir_x": -0.86,
    "swat_dir_lateral": 0.25,
    "swat_dir_up": 0.45,
}

LUA_BEHAVIOR = r"""
local function armPose(state, angleRad)
  -- Y-axis hinges compose mirrored through the 180-degree model rotation
  -- (X-axis hinges verified upright on the seesaw; the swatter arm rendered
  -- buried at +72 in play-testing 2026-07-23), so negate here and keep the
  -- authored angle constants semantically "positive = raised".
  setPartPose(state, "swatter_arm", nil, axisAngle(vec3(0, 1, 0), -angleRad))
end

behavior.init = function(state)
  state.behavior.phase = "idle"
  state.behavior.elapsed = 0
  state.behavior.clock = 0
  state.behavior.swatted = {}
  armPose(state, math.rad(B.rest_angle_deg))
end

behavior.reset = function(state)
  behavior.init(state)
  setEffectActive(state, "slam_dust", false)
end

behavior.onEnter = function(state, zone, vehicle)
  if zone == "lane_zone" and state.behavior.phase == "idle" then
    state.behavior.phase = "tremble"
    state.behavior.elapsed = 0
    state.behavior.swatted = {}
    showMessage("bzzzz...", 1.0)
    emitEvent(state, "I", "swatter_armed", {subject_id = vehicle:getId()})
  end
end

behavior.onExit = function(state, zone, vehicleId)
  if zone == "kill_zone"
    and not state.behavior.swatted[vehicleId]
    and (state.behavior.phase == "hold" or state.behavior.phase == "rise") then
    showMessage("Near miss!", 1.4)
    emitEvent(state, "I", "near_miss", {subject_id = vehicleId})
  end
end

local function swatOccupants(state)
  local headCenter = toWorldPoint(state, vec3(-0.7, 0.0, 1.0))
  local lateralAxis = toWorldDir(state, vec3(0, 1, 0))
  for vehicleId in pairs(zoneOccupants(state, "kill_zone")) do
    if not state.behavior.swatted[vehicleId] then
      local vehicle = exactVehicle(vehicleId)
      if vehicle then
        local offset = vehicle:getPosition() - headCenter
        local lateral = offset:dot(lateralAxis) >= 0 and 1 or -1
        local direction = toWorldDir(state, vec3(
          B.swat_dir_x, lateral * B.swat_dir_lateral, B.swat_dir_up))
        if launchSubject(state, vehicle, direction * B.swat_speed_mps) then
          state.behavior.swatted[vehicleId] = true
          showMessage("SWAT!", 1.5)
          emitEvent(state, "I", "subject_swatted", {subject_id = vehicleId})
        end
      end
    end
  end
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  b.clock = b.clock + dtSim
  b.elapsed = b.elapsed + dtSim
  local rest = math.rad(B.rest_angle_deg)
  local slam = math.rad(B.slam_angle_deg)
  if b.phase == "idle" then
    armPose(state, rest)
  elseif b.phase == "tremble" then
    armPose(state, rest + math.sin(b.clock * 45) * 0.035)
    if b.elapsed >= B.tremble_seconds then
      b.phase = "slam"
      b.elapsed = 0
      emitEvent(state, "I", "swatter_slam", {})
    end
  elseif b.phase == "slam" then
    local t = math.min(1, b.elapsed / B.slam_seconds)
    armPose(state, rest + (slam - rest) * t * t)
    if t >= 1 then
      b.phase = "hold"
      b.elapsed = 0
      setEffectActive(state, "slam_dust", true)
      swatOccupants(state)
    end
  elseif b.phase == "hold" then
    armPose(state, slam)
    if b.elapsed <= B.swat_window_seconds then
      swatOccupants(state)
    end
    if b.elapsed >= B.hold_seconds then
      b.phase = "rise"
      b.elapsed = 0
      setEffectActive(state, "slam_dust", false)
    end
  elseif b.phase == "rise" then
    local t = math.min(1, b.elapsed / B.rise_seconds)
    local smooth = t * t * (3 - 2 * t)
    armPose(state, slam + (rest - slam) * smooth)
    if t >= 1 then
      b.phase = "cooldown"
      b.elapsed = 0
    end
  elseif b.phase == "cooldown" then
    armPose(state, rest)
    if b.elapsed >= B.cooldown_seconds then
      b.phase = "idle"
      b.elapsed = 0
      b.swatted = {}
      -- A vehicle camping under the swatter gets swatted again.
      if zoneCount(state, "kill_zone") > 0 or zoneCount(state, "lane_zone") > 0 then
        b.phase = "tremble"
        showMessage("bzzzz...", 1.0)
      end
    end
  end
end
"""
