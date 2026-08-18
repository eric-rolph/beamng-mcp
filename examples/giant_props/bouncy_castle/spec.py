"""Bouncy Castle Landing Zone — authored constants for Blender + runtime.

A massive inflatable castle with a genuinely soft, springy floor and pillow
walls: the floor is a lattice of free nodes on low-damping springs over a
fixed base frame, so cars boing around inside instead of crashing. Three
walls are soft bumpers; the south side is open with an entry ramp. Corner
towers and battlements are fixed dressing.

Softness numbers (per node): the floor sits on ~42 kN/m springs with a
damping ratio around 0.12 of critical, so most of the impact energy comes
back. The walls are softer still.
"""

MOD_ID = "ericrolph_bouncy_castle"
DISPLAY_NAME = "Bouncy Castle Landing Zone"
VALUE_DOLLARS = 32000
ZIP_BASENAME = "bouncy_castle_ericrolph.zip"

# Authored frame: right-handed, meters, Z-up, +Y drive direction.
HALF = 10.0  # inner floor half-extent
FLOOR_Z = 0.8
WALL_TOP_Z = 3.4
FRAME_X = 11.0  # fixed outer frame line
GATE_HALF = 3.0  # south entry opening half-width
RAMP_GROUND_Y = -14.6
# 9x9 floor nodes (2.5 m cells): the original 6x6/42 kN/m floor let a car
# dropped from 8 m punch straight through to the terrain (proven live
# 2026-07-22). Finer cells + stiffer springs stop the punch-through while
# the ~0.16 damping ratio keeps the bounce.
GRID = 8  # floor cells per side

PALETTE = {
    f"{MOD_ID}_vinyl_blue": {
        "texture": {"family": "pvc_weave", "params": {"base": [0.16, 0.36, 0.78], "quilt": True}},
        "color": [0.16, 0.36, 0.78, 1.0],
        "metallic": 0.0,
        "roughness": 0.42,
    },
    f"{MOD_ID}_vinyl_red": {
        "texture": {"family": "pvc_weave", "params": {"base": [0.8, 0.15, 0.12]}},
        "color": [0.82, 0.16, 0.12, 1.0],
        "metallic": 0.0,
        "roughness": 0.42,
    },
    f"{MOD_ID}_vinyl_yellow": {
        "texture": {"family": "pvc_weave", "params": {"base": [0.9, 0.72, 0.1]}},
        "color": [0.95, 0.78, 0.12, 1.0],
        "metallic": 0.0,
        "roughness": 0.42,
    },
    f"{MOD_ID}_vinyl_cream": {
        "texture": {"family": "pvc_weave", "params": {"base": [0.9, 0.87, 0.78], "seams": False}},
        "color": [0.93, 0.9, 0.8, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
    f"{MOD_ID}_flag_green": {
        "color": [0.15, 0.65, 0.3, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
        "double_sided": True,
    },
}

TRIGGERS = {
    "bounce_zone": {
        "mode": "Overlaps",
        "center": [0.0, 0.0, FLOOR_Z + 2.2],
        "dimensions": [2 * HALF, 2 * HALF, 4.4],
    },
}

EFFECTS = {}

BEHAVIOR = {
    "camera_distance": 40.0,
    "greeting_cooldown": 6.0,
    # Gimmick-Pad-style super-jumps (player request 2026-07-23): every car
    # inside gets a scheduled scripted bounce with random power and delay.
    "jump_height_min_m": 1.0,
    # 8 (was 20): full-power jumps drifted cars clean over the 3.4 m
    # walls (player report 2026-07-23).
    "jump_height_max_m": 8.0,
    "jump_delay_min_s": 1.0,
    "jump_delay_max_s": 5.0,
    "jump_lateral_mps": 1.2,
}

LUA_BEHAVIOR = r"""
behavior.init = function(state)
  state.behavior.lastGreeting = -math.huge
  state.behavior.clock = 0
  state.behavior.jumpers = {}
  state.behavior.stats = {jumps = 0}
end

behavior.reset = function(state)
  behavior.init(state)
end

local function scheduleJump(state, vehicleId)
  state.behavior.jumpers[vehicleId] = {
    timer = B.jump_delay_min_s
      + math.random() * (B.jump_delay_max_s - B.jump_delay_min_s),
  }
end

behavior.onEnter = function(state, zone, vehicle)
  if zone ~= "bounce_zone" then return end
  local id = vehicle:getId()
  if not state.behavior.jumpers[id] then
    scheduleJump(state, id)
  end
  local clock = state.behavior.clock or 0
  if clock - (state.behavior.lastGreeting or -math.huge) < B.greeting_cooldown then
    return
  end
  state.behavior.lastGreeting = clock
  showMessage("Boing! Welcome to the bouncy castle!", 2.2)
  emitEvent(state, "I", "bouncer_entered", {subject_id = vehicle:getId()})
end

behavior.onExit = function(state, zone, vehicleId)
  if zone == "bounce_zone" then
    state.behavior.jumpers[vehicleId] = nil
  end
end

behavior.onSubjectGone = function(state, vehicleId, reason)
  state.behavior.jumpers[vehicleId] = nil
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  b.clock = (b.clock or 0) + dtSim
  for vehicleId, jumper in pairs(b.jumpers) do
    jumper.timer = jumper.timer - dtSim
    if jumper.timer <= 0 then
      local vehicle = exactVehicle(vehicleId)
      if vehicle then
        local height = B.jump_height_min_m
          + math.random() * (B.jump_height_max_m - B.jump_height_min_m)
        local speed = math.sqrt(2 * 9.81 * height)
        local up = toWorldDir(state, vec3(0, 0, 1))
        -- Drift aims INWARD (toward the castle centre) plus a small random
        -- component, so super-jumps self-contain instead of ejecting cars
        -- over the walls.
        local centre = toWorldPoint(state, vec3(0, 0, 0))
        local offset = vehicle:getPosition() - centre
        offset.z = 0
        local lateral = vec3(0, 0, 0)
        if offset:length() > 2.0 then
          local inward = vec3(-offset.x, -offset.y, 0)
          inward:normalize()
          lateral = inward * (B.jump_lateral_mps * 0.8)
        end
        lateral = lateral
          + toWorldDir(state, vec3(1, 0, 0))
          * ((math.random() * 2 - 1) * B.jump_lateral_mps * 0.4)
          + toWorldDir(state, vec3(0, 1, 0))
          * ((math.random() * 2 - 1) * B.jump_lateral_mps * 0.4)
        -- Add on top of existing motion so mid-bounce momentum carries.
        addSubjectVelocity(state, vehicle, up * speed + lateral)
        b.stats.jumps = (b.stats.jumps or 0) + 1
        showMessage(string.format("BOING! +%d m", math.floor(height + 0.5)), 1.4)
        emitEvent(state, "I", "castle_super_jump", {
          subject_id = vehicleId,
          height_m = height,
        })
      end
      scheduleJump(state, vehicleId)
    end
  end
end
"""
