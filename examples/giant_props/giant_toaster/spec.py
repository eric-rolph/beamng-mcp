"""The Giant Toaster — authored constants shared by Blender and the runtime.

Redesigned 2026-07-23 after play-testing: the old drive-on slab read as a
BBQ grill. This is now a real upright two-slice toaster (Sunbeam T-20
proportions): a tall rounded chrome body on a bakelite plinth, a long
trestle ramp climbing to the crown, and two DEEP slots the car drops into —
sitting down inside like bread, with heating-element strips glowing orange
on the slot walls. The lever rides down the side track while it ticks, then
POP: the slot plate flings the car out over the rim. The browning dial on
the east face of the base is a drive-by bump zone cycling launch power 1..6.
"""

MOD_ID = "ericrolph_giant_toaster"
DISPLAY_NAME = "The Giant Toaster"
VALUE_DOLLARS = 25000
ZIP_BASENAME = "giant_toaster_ericrolph.zip"

# Authored frame: right-handed, meters, Z-up, +Y drive direction. The ramp
# ascends from -Y to a landing, then the car drops into a slot.
BODY_HALF_X = 3.25
BODY_HALF_Y = 5.25
BODY_TOP_Z = 5.0
BASE_TOP_Z = 0.7
SLOT_CENTER_X = 1.55
SLOT_HALF_WIDTH = 1.45  # inner walls at |x| 0.1, outer walls at |x| 3.0
# 4.35 (was 4.15): the 0.85 m drop over a 1.35 m lip beached low cars
# at the slot entry (player screenshot 2026-07-23). 0.65 deep with a
# 14-degree lip keeps the bread-in-slot look and drives smoothly.
SLOT_FLOOR_Z = 4.35
SLOT_Y_MIN = -5.25  # open through the south face; entry lip ramps down inside
SLOT_Y_MAX = 3.6
LANDING_Y_MIN = -9.0  # deeper shelf: room to align before dropping in
RAMP_GROUND_Y = -25.5

DIAL_CENTER = (3.32, -3.0, 1.9)
DIAL_RADIUS = 0.95
LEVER_PIVOT = (3.3, -3.2, 4.5)
PLATE_TOP_Z = SLOT_FLOOR_Z

PALETTE = {
    f"{MOD_ID}_chrome": {
        "texture": {"family": "scribed_chrome"},
        "color": [0.84, 0.86, 0.9, 1.0],
        "metallic": 0.95,
        "roughness": 0.16,
    },
    f"{MOD_ID}_chrome_dark": {
        "texture": {
            "family": "brushed_metal",
            "params": {"base": [0.34, 0.36, 0.4], "rough": 0.35},
        },
        "color": [0.32, 0.34, 0.38, 1.0],
        "metallic": 0.85,
        "roughness": 0.35,
    },
    f"{MOD_ID}_slot_dark": {
        "color": [0.09, 0.08, 0.08, 1.0],
        "metallic": 0.3,
        "roughness": 0.6,
    },
    f"{MOD_ID}_element_glow": {
        "color": [0.55, 0.12, 0.04, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
        # THREE components, not four (2026-08-15, round 18). This was
        # [1.0, 0.42, 0.1, 1.0], and a four-element emissiveFactor renders
        # completely inert - the nichrome elements have never once glowed.
        # Measured on a calibration strip; see AGENTS.md "Round-16/17: the
        # photometric ledger" and prop_builder.check_emissive_factor.
        "emissive": [1.0, 0.42, 0.1],
        # 800 nit. The elements sit down inside a shaded slot, so the daylight
        # bar is the one that matters and 800 is the measured "unmistakable"
        # rung (+44.5 sRGB over an unlit control at noon). Clipping at night
        # is the right failure for red-hot metal - an incandescent element
        # viewed in the dark IS saturated - and the factor keeps it orange
        # while it does, since the factor still tints once nits is driving.
        "stage": {"emissiveIntensityNits": 800},
    },
    f"{MOD_ID}_bakelite": {
        "texture": {"family": "bakelite"},
        "color": [0.06, 0.06, 0.07, 1.0],
        "metallic": 0.0,
        "roughness": 0.55,
    },
    f"{MOD_ID}_dial_cream": {
        "texture": {
            "family": "painted_metal",
            "params": {"base": [0.93, 0.89, 0.78], "rough": 0.4},
        },
        "color": [0.93, 0.89, 0.78, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
    f"{MOD_ID}_pointer_red": {
        "color": [0.85, 0.12, 0.05, 1.0],
        "metallic": 0.0,
        "roughness": 0.4,
    },
    f"{MOD_ID}_plate_steel": {
        "texture": {
            "family": "brushed_metal",
            "params": {"base": [0.62, 0.64, 0.68], "rough": 0.3},
        },
        "color": [0.62, 0.64, 0.68, 1.0],
        "metallic": 0.9,
        "roughness": 0.3,
    },
    f"{MOD_ID}_ramp_steel": {
        "texture": {"family": "steel_worn"},
        "color": [0.42, 0.44, 0.48, 1.0],
        "metallic": 0.8,
        "roughness": 0.45,
    },
    f"{MOD_ID}_hazard": {
        "texture": {"family": "hazard_chevron"},
        "color": [0.9, 0.7, 0.1, 1.0],
        "metallic": 0.1,
        "roughness": 0.5,
    },
}

TRIGGERS = {
    # Deep slots: bottoms reach ~0.55 m below the slot floor for OOBB-settle
    # jitter; tops clear the rim so a contained car launches cleanly.
    "slot_l": {
        "mode": "Contains",
        "center": [-SLOT_CENTER_X, -0.8, SLOT_FLOOR_Z + 1.5],
        "dimensions": [3.0, 9.2, 4.2],
    },
    "slot_r": {
        "mode": "Contains",
        "center": [SLOT_CENTER_X, -0.8, SLOT_FLOOR_Z + 1.5],
        "dimensions": [3.0, 9.2, 4.2],
    },
    "dial_zone": {
        "mode": "Overlaps",
        "center": [5.2, -3.0, 1.6],
        "dimensions": [3.4, 3.4, 3.2],
    },
}

EFFECTS = {
    "pop_steam_l": {
        "emitter": "BNGP_34",
        "position": [-SLOT_CENTER_X, -0.4, BODY_TOP_Z + 0.3],
        "direction": [0.0, 0.0, 1.0],
    },
    "pop_steam_r": {
        "emitter": "BNGP_34",
        "position": [SLOT_CENTER_X, -0.4, BODY_TOP_Z + 0.3],
        "direction": [0.0, 0.0, 1.0],
    },
}

BEHAVIOR = {
    "camera_distance": 40.0,
    "tick_duration": 2.8,
    "plate_dip": 0.1,
    "plate_rise": 1.6,
    "plate_return_seconds": 1.2,
    "cooldown_seconds": 2.0,
    "lever_drop": 1.9,
    "lever_drop_seconds": 0.5,
    "forward_kick_mps": 3.0,
    "dial_bump_cooldown": 0.9,
    "launch_speeds_mps": [12.0, 17.0, 23.0, 30.0, 38.0, 48.0],
    "dial_angles_deg": [-75.0, -45.0, -15.0, 15.0, 45.0, 75.0],
}

LUA_BEHAVIOR = r"""
local SLOT_PLATES = {slot_l = "plate_l", slot_r = "plate_r"}

local function slotState(state, zone)
  local slots = state.behavior.slots
  if not slots then
    slots = {}
    state.behavior.slots = slots
  end
  local slot = slots[zone]
  if not slot then
    slot = {phase = "idle", elapsed = 0, lastCount = nil}
    slots[zone] = slot
  end
  return slot
end

local function anySlotTicking(state)
  for _, slot in pairs(state.behavior.slots or {}) do
    if slot.phase == "ticking" then return true end
  end
  return false
end

local function applyDialPose(state)
  local level = state.behavior.level or 3
  local angle = math.rad(B.dial_angles_deg[level] or 0)
  if anySlotTicking(state) then
    angle = angle + math.sin((state.behavior.clock or 0) * 30) * 0.05
  end
  -- The dial faces +X; the pointer swings about the X axis (X-axis hinge
  -- signs verified upright on the seesaw).
  setPartPose(state, "dial_pointer", nil, axisAngle(vec3(1, 0, 0), angle))
end

behavior.init = function(state)
  state.behavior.level = 3
  state.behavior.dialCooldown = 0
  state.behavior.clock = 0
  state.behavior.slots = {}
  state.behavior.stats = {pops = 0}
  applyDialPose(state)
end

behavior.reset = function(state)
  state.behavior.slots = {}
  setPartPose(state, "plate_l", vec3(0, 0, 0), quat(0, 0, 0, 1))
  setPartPose(state, "plate_r", vec3(0, 0, 0), quat(0, 0, 0, 1))
  setPartPose(state, "lever_knob", vec3(0, 0, 0), quat(0, 0, 0, 1))
  setEffectActive(state, "pop_steam_l", false)
  setEffectActive(state, "pop_steam_r", false)
  applyDialPose(state)
end

behavior.onEnter = function(state, zone, vehicle)
  if zone == "dial_zone" then
    if (state.behavior.dialCooldown or 0) > 0 then return end
    state.behavior.dialCooldown = B.dial_bump_cooldown
    state.behavior.level = (state.behavior.level % #B.launch_speeds_mps) + 1
    showMessage(
      string.format("Browning dial: level %d of %d", state.behavior.level,
        #B.launch_speeds_mps),
      2.0
    )
    emitEvent(state, "I", "dial_level_changed", {level = state.behavior.level})
    applyDialPose(state)
    return
  end
  if not SLOT_PLATES[zone] then return end
  local slot = slotState(state, zone)
  if slot.phase ~= "idle" then return end
  slot.phase = "ticking"
  slot.elapsed = 0
  slot.lastCount = nil
  showMessage(
    string.format("Bread detected. Toasting at level %d...", state.behavior.level),
    2.0
  )
  emitEvent(state, "I", "toasting_started", {
    zone = zone,
    subject_id = vehicle:getId(),
    level = state.behavior.level,
  })
end

behavior.onExit = function(state, zone, vehicleId)
  if not SLOT_PLATES[zone] then return end
  local slot = slotState(state, zone)
  if slot.phase == "ticking" and zoneCount(state, zone) == 0 then
    slot.phase = "idle"
    slot.elapsed = 0
    showMessage("The toast escaped!", 1.6)
    emitEvent(state, "I", "toasting_aborted", {zone = zone, subject_id = vehicleId})
  end
end

behavior.onSubjectGone = function(state, vehicleId, reason)
  for zone in pairs(SLOT_PLATES) do
    local slot = slotState(state, zone)
    if slot.phase == "ticking" and zoneCount(state, zone) == 0 then
      slot.phase = "idle"
      slot.elapsed = 0
    end
  end
end

local function updateSlot(state, zone, plateName, dtSim)
  local slot = slotState(state, zone)
  local steamName = zone == "slot_l" and "pop_steam_l" or "pop_steam_r"
  if slot.phase == "ticking" then
    slot.elapsed = slot.elapsed + dtSim
    local remaining = B.tick_duration - slot.elapsed
    local count = math.max(0, math.ceil(remaining))
    if count ~= slot.lastCount and count > 0 then
      slot.lastCount = count
      showMessage(string.format("tick... %d", count), 0.9)
    end
    local dip = -B.plate_dip * math.min(1, slot.elapsed / 0.35)
    setPartPose(state, plateName, vec3(0, 0, dip), nil)
    if slot.elapsed >= B.tick_duration then
      local vehicle = firstOccupant(state, zone)
      if not vehicle then
        slot.phase = "idle"
        slot.elapsed = 0
        return
      end
      local up = toWorldDir(state, vec3(0, 0, 1))
      local forward = toWorldDir(state, vec3(0, 1, 0))
      local speed = B.launch_speeds_mps[state.behavior.level or 3]
        or B.launch_speeds_mps[3]
      local velocity = up * speed + forward * B.forward_kick_mps
      showMessage("POP!", 1.5)
      if launchSubject(state, vehicle, velocity) then
        state.behavior.stats.pops = (state.behavior.stats.pops or 0) + 1
        emitEvent(state, "I", "toast_popped", {
          zone = zone,
          subject_id = vehicle:getId(),
          level = state.behavior.level,
          speed_mps = speed,
        })
        setEffectActive(state, steamName, true)
        slot.phase = "popped"
        slot.elapsed = 0
      else
        slot.phase = "idle"
        slot.elapsed = 0
      end
    end
  elseif slot.phase == "popped" then
    slot.elapsed = slot.elapsed + dtSim
    local rise
    if slot.elapsed < 0.1 then
      rise = B.plate_rise * (slot.elapsed / 0.1)
    else
      local settle = math.min(1, (slot.elapsed - 0.1) / B.plate_return_seconds)
      rise = B.plate_rise * (1 - settle)
      if slot.elapsed > 0.6 then setEffectActive(state, steamName, false) end
    end
    setPartPose(state, plateName, vec3(0, 0, rise), nil)
    if slot.elapsed >= 0.1 + B.plate_return_seconds + B.cooldown_seconds then
      slot.phase = "idle"
      slot.elapsed = 0
      setPartPose(state, plateName, vec3(0, 0, 0), nil)
    end
  end
end

behavior.update = function(state, dtSim)
  state.behavior.clock = (state.behavior.clock or 0) + dtSim
  if (state.behavior.dialCooldown or 0) > 0 then
    state.behavior.dialCooldown = state.behavior.dialCooldown - dtSim
  end
  for zone, plateName in pairs(SLOT_PLATES) do
    updateSlot(state, zone, plateName, dtSim)
  end
  local target = 0
  for _, slot in pairs(state.behavior.slots or {}) do
    if slot.phase == "ticking" then
      local drop = -B.lever_drop
        * math.min(1, slot.elapsed / B.lever_drop_seconds)
      if drop < target then target = drop end
    end
  end
  local pose = state.partPoses.lever_knob
  local current = pose and pose.offset.z or 0
  local step = (target - current) * math.min(1, dtSim * 10)
  setPartPose(state, "lever_knob", vec3(0, 0, current + step), nil)
  if anySlotTicking(state) then applyDialPose(state) end
end
"""
