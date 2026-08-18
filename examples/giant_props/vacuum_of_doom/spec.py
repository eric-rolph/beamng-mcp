"""The Vacuum Cleaner of Doom — authored constants for Blender + runtime.

An oversized shop vac. Entering the approach lane wakes it: the turbine cap
spools up with a dust cloud at the nozzle (anticipation), then an invisible
force field drags cars toward the mouth. Vehicles that reach the mouth get
SLURPed, digested for a beat, then spat out of the angled exhaust stack on
the far side with a steam blast.

The pull is a per-frame acceleration toward the nozzle applied by the GE
runtime, capped by a position-delta speed estimate so nothing integrates to
silly velocities.
"""

MOD_ID = "ericrolph_vacuum_of_doom"
DISPLAY_NAME = "The Vacuum Cleaner of Doom"
VALUE_DOLLARS = 28000
ZIP_BASENAME = "vacuum_of_doom_ericrolph.zip"

# Authored frame: right-handed, meters, Z-up, +Y drive direction. The car
# approaches from -Y; the canister sits behind the nozzle on +Y.
DRUM_CENTER_Y = 6.0
DRUM_RADIUS = 3.2
NOZZLE_POINT = (0.0, -3.5, 1.1)
EXHAUST_EXIT = (0.0, 11.0, 5.1)
EXHAUST_DIR = (0.0, 0.906, 0.423)  # 25 degrees above horizontal, +Y
TELEPORT_POINT = (0.0, 12.2, 5.8)

PALETTE = {
    f"{MOD_ID}_vac_orange": {
        "texture": {"family": "plastic_ribs", "params": {"base": [0.9, 0.44, 0.1], "ribs": 6.0}},
        "color": [0.92, 0.45, 0.08, 1.0],
        "metallic": 0.1,
        "roughness": 0.35,
    },
    f"{MOD_ID}_charcoal": {
        "texture": {
            "family": "painted_metal",
            "params": {"base": [0.14, 0.14, 0.16], "rough": 0.5},
        },
        "color": [0.13, 0.13, 0.15, 1.0],
        "metallic": 0.2,
        "roughness": 0.55,
    },
    f"{MOD_ID}_hose_gray": {
        "texture": {
            "family": "plastic_ribs",
            "params": {"base": [0.42, 0.44, 0.47], "ribs": 10.0, "rough": 0.5},
        },
        "color": [0.42, 0.44, 0.47, 1.0],
        "metallic": 0.05,
        "roughness": 0.6,
    },
    f"{MOD_ID}_steel": {
        "texture": {"family": "steel_worn"},
        "color": [0.6, 0.62, 0.65, 1.0],
        "metallic": 0.85,
        "roughness": 0.3,
    },
    f"{MOD_ID}_cream": {
        "texture": {"family": "painted_metal", "params": {"base": [0.92, 0.88, 0.78]}},
        "color": [0.92, 0.88, 0.78, 1.0],
        "metallic": 0.0,
        "roughness": 0.55,
    },
}

TRIGGERS = {
    "pull_zone": {
        "mode": "Overlaps",
        "center": [0.0, -14.0, 2.2],
        "dimensions": [10.0, 21.0, 4.4],
    },
    "gulp_zone": {
        # Overlaps, not Contains: a vehicle arrives at the bell throat at
        # speed and may crumple against the back wall, inflating its OOBB
        # beyond any full-containment box. This is a capture zone, not a
        # launcher — the eject impulse fires only after the subject is
        # teleported to the exhaust, far from anything else. Deep-throat box
        # so only properly swallowed vehicles overlap it.
        "mode": "Overlaps",
        "center": [0.0, -3.3, 1.2],
        "dimensions": [4.6, 1.6, 2.8],
    },
}

EFFECTS = {
    "nozzle_dust": {
        "emitter": "BNGP_2",
        "position": [0.0, -4.6, 1.0],
        "direction": [0.0, -0.7, 0.7],
    },
    "exhaust_steam": {
        "emitter": "BNGP_34",
        "position": list(EXHAUST_EXIT),
        "direction": list(EXHAUST_DIR),
    },
}

BEHAVIOR = {
    "camera_distance": 36.0,
    "spool_seconds": 1.2,
    "winddown_seconds": 1.5,
    "digest_seconds": 0.8,
    "pull_accel_start": 4.0,
    "pull_accel_full": 12.0,
    "pull_ramp_seconds": 3.0,
    # Capped so vehicles arrive at the bell throat without demolishing
    # themselves against its back wall.
    "max_pull_speed": 14.0,
    "eject_speed_mps": 45.0,
    "flap_open_seconds": 0.9,
    "nozzle_point": list(NOZZLE_POINT),
    "teleport_point": list(TELEPORT_POINT),
    "exhaust_dir": list(EXHAUST_DIR),
    "cap_idle_spin": 0.0,
    "cap_spool_spin": 4.0,
    "cap_full_spin": 18.0,
}

LUA_BEHAVIOR = r"""
behavior.init = function(state)
  state.behavior.phase = "idle"
  state.behavior.elapsed = 0
  state.behavior.activeTime = 0
  state.behavior.capAngle = 0
  state.behavior.capSpeed = 0
  state.behavior.tracked = {}
  state.behavior.digest = nil
  state.behavior.flapTimer = nil
  state.behavior.swallowed = 0
end

behavior.reset = function(state)
  behavior.init(state)
  setEffectActive(state, "nozzle_dust", false)
  setEffectActive(state, "exhaust_steam", false)
  setPartPose(state, "exhaust_flap", nil, quat(0, 0, 0, 1))
end

behavior.onEnter = function(state, zone, vehicle)
  local b = state.behavior
  if zone == "pull_zone" then
    if b.phase == "idle" or b.phase == "winddown" then
      b.phase = "spool"
      b.elapsed = 0
      b.activeTime = 0
      setEffectActive(state, "nozzle_dust", true)
      showMessage("The vacuum awakens...", 1.8)
      emitEvent(state, "I", "vacuum_spooling", {subject_id = vehicle:getId()})
    end
  elseif zone == "gulp_zone" then
    if not b.digest and (b.phase == "active" or b.phase == "spool") then
      b.digest = {subjectId = vehicle:getId(), elapsed = 0}
      showMessage("SLURP!", 1.4)
      emitEvent(state, "I", "vacuum_gulp", {subject_id = vehicle:getId()})
    end
  end
end

behavior.onExit = function(state, zone, vehicleId)
  if zone == "pull_zone" then
    state.behavior.tracked[vehicleId] = nil
  end
end

behavior.onSubjectGone = function(state, vehicleId, reason)
  state.behavior.tracked[vehicleId] = nil
  if state.behavior.digest and state.behavior.digest.subjectId == vehicleId then
    state.behavior.digest = nil
  end
end

local function pullOccupants(state, dtSim)
  local b = state.behavior
  local nozzle = toWorldPoint(state, B.nozzle_point)
  local ramp = math.min(1, b.activeTime / B.pull_ramp_seconds)
  local accel = B.pull_accel_start + (B.pull_accel_full - B.pull_accel_start) * ramp
  for vehicleId in pairs(zoneOccupants(state, "pull_zone")) do
    if not (b.digest and b.digest.subjectId == vehicleId) then
      local vehicle = exactVehicle(vehicleId)
      if vehicle then
        local position = vehicle:getPosition()
        local track = b.tracked[vehicleId]
        local speedTowards = 0
        if track and dtSim > 0 then
          local moved = (position - track.position) * (1 / dtSim)
          local towards = nozzle - position
          if towards:length() > 0.01 then
            towards:normalize()
            speedTowards = moved:dot(towards)
          end
        end
        b.tracked[vehicleId] = {position = vec3(position.x, position.y, position.z)}
        local towards = nozzle - position
        if towards:length() > 0.5 and speedTowards < B.max_pull_speed then
          towards:normalize()
          addSubjectVelocity(state, vehicle, towards * (accel * dtSim))
        end
      end
    end
  end
end

local function finishDigest(state)
  local b = state.behavior
  local digest = b.digest
  b.digest = nil
  if not digest then return end
  local vehicle = exactVehicle(digest.subjectId)
  if not vehicle then return end
  local target = toWorldPoint(state, B.teleport_point)
  local rotation = quat(vehicle:getRotation())
  if not teleportSubject(state, vehicle, target, rotation) then return end
  local direction = toWorldDir(state, B.exhaust_dir)
  launchSubject(state, vehicle, direction * B.eject_speed_mps)
  showMessage("PTOOEY!", 1.6)
  b.swallowed = b.swallowed + 1
  emitEvent(state, "I", "vacuum_eject", {
    subject_id = digest.subjectId,
    swallowed_total = b.swallowed,
  })
  setEffectActive(state, "exhaust_steam", true)
  b.flapTimer = 0
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  b.elapsed = b.elapsed + dtSim

  if b.phase == "spool" then
    b.capSpeed = B.cap_spool_spin
    if b.elapsed >= B.spool_seconds then
      b.phase = "active"
      b.elapsed = 0
      showMessage("MAXIMUM SUCTION", 1.6)
      emitEvent(state, "I", "vacuum_active", {})
    end
  elseif b.phase == "active" then
    b.activeTime = b.activeTime + dtSim
    local ramp = math.min(1, b.activeTime / B.pull_ramp_seconds)
    b.capSpeed = B.cap_spool_spin + (B.cap_full_spin - B.cap_spool_spin) * ramp
    pullOccupants(state, dtSim)
    if zoneCount(state, "pull_zone") == 0 and not b.digest then
      b.phase = "winddown"
      b.elapsed = 0
      setEffectActive(state, "nozzle_dust", false)
    end
  elseif b.phase == "winddown" then
    b.capSpeed = math.max(0, b.capSpeed - dtSim * 12)
    if b.elapsed >= B.winddown_seconds then
      b.phase = "idle"
      b.elapsed = 0
      b.capSpeed = B.cap_idle_spin
      b.activeTime = 0
      b.tracked = {}
    end
  else
    b.capSpeed = B.cap_idle_spin
  end

  if b.digest then
    b.digest.elapsed = b.digest.elapsed + dtSim
    if b.digest.elapsed >= B.digest_seconds then
      finishDigest(state)
      -- Another patient customer may already be pressed against the mouth.
      if b.phase == "active" then
        local nextVehicle = firstOccupant(state, "gulp_zone")
        if nextVehicle then
          b.digest = {subjectId = nextVehicle:getId(), elapsed = 0}
          showMessage("SLURP!", 1.4)
        end
      end
    end
  end

  if b.flapTimer then
    b.flapTimer = b.flapTimer + dtSim
    local t = b.flapTimer / B.flap_open_seconds
    local angle
    if t < 0.25 then
      angle = math.rad(-70) * (t / 0.25)
    elseif t < 1 then
      angle = math.rad(-70) * (1 - (t - 0.25) / 0.75)
    else
      angle = 0
      b.flapTimer = nil
      setEffectActive(state, "exhaust_steam", false)
    end
    setPartPose(state, "exhaust_flap", nil, axisAngle(vec3(1, 0, 0), angle))
  end

  b.capAngle = b.capAngle + b.capSpeed * dtSim
  setPartPose(state, "turbine_cap", nil, axisAngle(vec3(0, 0, 1), b.capAngle))
end
"""
