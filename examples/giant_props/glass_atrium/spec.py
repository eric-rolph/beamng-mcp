"""The Glass Atrium — authored constants for Blender + runtime.

A ten-storey steel-framed atrium tower whose floors are breakable glass
panes. Drive onto the freight-lift pad and the tower hoists you to the
open skylight, then lets go: the car smashes down through floor after
floor, every pane shattering and falling away as a real jbeam sheet, with
the steel frame arresting a slice of the fall speed at each level (the
"progressive speed brake") until the car flops onto the crash cushion at
the bottom and drives out the archway.

Anticipation beat: the lift countdown ("3... 2... 1...") while the whole
glass stack you are about to fall through glitters below you.

Physics: each floor is a 4x4 grid of free glass nodes skinned to its own
flexbody mesh (falling sheets), hung from fixed frame anchors by breakable
support beams sharing one breakGroup per floor; the pane's collision
triangles carry the same breakGroup so the surface vanishes the instant
its hangers snap. Break strength climbs floor by floor toward the ground,
and the runtime adds an upward velocity brake on every shatter so the
descent stays survivable for a normal car.
"""

MOD_ID = "ericrolph_glass_atrium"
DISPLAY_NAME = "The Glass Atrium"
VALUE_DOLLARS = 68000
ZIP_BASENAME = "glass_atrium_ericrolph.zip"

# Authored frame: right-handed, meters, Z-up, +Y drive direction. The
# tower is centred on the origin; the lift pad and exit archway face -Y.
GLASS_HALF = 6.0  # panes span x,y in [-6, 6]
FRAME_HALF = 6.9  # anchor ring / wall line
FLOOR_COUNT = 10
FLOOR_Z0 = 6.0  # lowest glass floor
FLOOR_DZ = 3.2  # storey height
RIM_Z = FLOOR_Z0 + FLOOR_DZ * FLOOR_COUNT + 1.0  # open skylight rim (39.0)
PANE_NODES = 4  # 4x4 free nodes per floor
CUSHION_TOP_Z = 1.05  # landing cushion deck
DOOR_HALF_WIDTH = 2.6  # exit archway on the -Y wall; also the ring bay width
DOOR_TOP_Z = 5.8  # visual arch top, just under the first ring at z=6.0
LIFT_PAD_Y = -13.5
DROP_Z = RIM_Z + 2.5

# Brittle hanger ladder: the skylight floor pops at a touch, the lobby
# floor needs a real impact. index 1 = TOP floor in player messaging.
# Live tuning (2026-07-23): with brake-capped (~10 m/s) arrivals the
# break/hold cliff for a 1.35 t ETK800 sits between 94 kN (floor 9 of the
# 30+8k ladder — broke) and 102 kN (its floor 10 — held, drop timed out).
# Keep every storey safely below it: top 28 kN, +6.5 kN per storey, lobby
# floor 86.5 kN.
GLASS_BREAK_TOP_N = 28000.0
GLASS_BREAK_STEP_N = 6500.0

PALETTE = {
    f"{MOD_ID}_glass_pane": {
        "color": [0.62, 0.78, 0.85, 0.32],
        "metallic": 0.0,
        "roughness": 0.08,
        "double_sided": True,
    },
    f"{MOD_ID}_glass_wall": {
        "color": [0.55, 0.72, 0.82, 0.22],
        "metallic": 0.0,
        "roughness": 0.06,
        "double_sided": True,
    },
    f"{MOD_ID}_steel_frame": {
        "texture": {"family": "steel_worn"},
        "color": [0.5, 0.53, 0.57, 1.0],
        "metallic": 0.85,
        "roughness": 0.35,
    },
    f"{MOD_ID}_girder_red": {
        "texture": {
            "family": "painted_metal",
            "params": {"base": [0.72, 0.16, 0.12], "rough": 0.38},
        },
        "color": [0.72, 0.16, 0.12, 1.0],
        "metallic": 0.1,
        "roughness": 0.38,
    },
    f"{MOD_ID}_cushion_blue": {
        "texture": {"family": "pvc_weave", "params": {"base": [0.16, 0.32, 0.62], "quilt": True}},
        "color": [0.16, 0.32, 0.62, 1.0],
        "metallic": 0.0,
        "roughness": 0.55,
    },
    f"{MOD_ID}_lift_hazard": {
        "texture": {"family": "hazard_chevron"},
        "color": [0.95, 0.75, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
    f"{MOD_ID}_asphalt": {
        "texture": {"family": "asphalt"},
        "color": [0.16, 0.16, 0.17, 1.0],
        "metallic": 0.0,
        "roughness": 0.9,
    },
    f"{MOD_ID}_trim_white": {
        "color": [0.9, 0.9, 0.88, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
}

TRIGGERS = {
    # Drive onto the freight lift: any overlap starts the countdown.
    "lift_pad": {
        "mode": "Overlaps",
        "center": [0.0, LIFT_PAD_Y, 1.8],
        "dimensions": [5.4, 5.4, 3.6],
    },
    # The full drop shaft, skylight to lobby.
    "shaft": {
        "mode": "Overlaps",
        "center": [0.0, 0.0, RIM_Z / 2 + 1.0],
        "dimensions": [13.4, 13.4, RIM_Z + 4.0],
    },
    # Lobby level: settled cars here count as a completed drop.
    "landing": {
        "mode": "Overlaps",
        "center": [0.0, 0.0, CUSHION_TOP_Z + 1.6],
        "dimensions": [12.6, 12.6, 3.2],
    },
}

EFFECTS = {
    "landing_dust": {
        "emitter": "BNGP_2",
        "position": [0.0, 0.0, CUSHION_TOP_Z + 0.3],
        "direction": [0.0, 0.0, 1.0],
    },
}

BEHAVIOR = {
    "camera_distance": 48.0,
    "lift_countdown_s": 3.0,
    "drop_point": [0.0, 0.0, DROP_Z],
    "drop_release_mps": 2.0,
    # Progressive speed brake: every shatter clamps the fall speed back to
    # this cap (a pure fraction converges to ~12 m/s and never slows —
    # adversarial-review finding 2026-07-23). The final arrest re-clamps
    # near the lobby keyed on the CAR, immune to sentinel latency.
    "brake_cap_mps": 6.5,
    "final_arrest_height_m": 3.0,
    "shatter_drop_m": 1.2,
    "landing_z": CUSHION_TOP_Z,
    "settle_speed_mps": 2.5,
    "drop_timeout_s": 30.0,
    # A car that stalls on unbroken glass mid-shaft has no way out and
    # would block the zone-gated reset forever: the timeout hands it back.
    "lift_return_point": [0.0, LIFT_PAD_Y, 0.8],
    "reset_delay_s": 6.0,
    # "floors" is injected by the generator: [{cid, index, z}, ...] with
    # index 1 = the skylight floor players hit first.
}

LUA_BEHAVIOR = r"""
behavior.init = function(state)
  local b = state.behavior
  b.phase = "idle"
  b.elapsed = 0
  b.countdown = 0
  b.countSpoken = nil
  b.subjectId = nil
  b.dropTimer = 0
  b.resetTimer = 0
  b.arrested = false
  b.shattered = {}
  b.stats = b.stats or {floors_broken = 0, drops_completed = 0, glass_down = 0}
  b.stats.glass_down = 0
end

behavior.reset = function(state)
  local keepStats = state.behavior.stats
  behavior.init(state)
  state.behavior.stats = keepStats
  state.behavior.stats.glass_down = 0
  setEffectActive(state, "landing_dust", false)
end

behavior.onEnter = function(state, zone, vehicle)
  local b = state.behavior
  if zone == "lift_pad" and b.phase == "idle" then
    b.phase = "arming"
    b.elapsed = 0
    b.countdown = B.lift_countdown_s
    b.countSpoken = nil
    b.subjectId = vehicle:getId()
    showMessage("Freight lift engaged. Going UP.", 1.6)
    emitEvent(state, "I", "atrium_lift_engaged", {subject_id = vehicle:getId()})
  elseif zone == "lift_pad" and b.phase ~= "idle" then
    showMessage("Glaziers still sweeping - hold on.", 1.4)
  end
end

local function checkFloors(state)
  local b = state.behavior
  -- Phase-gated: latching outside a drop re-marks still-fallen sheets in
  -- the requestReset window and would leave stale flags that disable every
  -- brake on the next run (adversarial-review finding 2026-07-23).
  if b.phase ~= "dropping" and b.phase ~= "settled" then return end
  local prop = exactVehicle(state.propId)
  if not prop then return end
  for _, floor in ipairs(B.floors or {}) do
    if not b.shattered[floor.index] then
      local okNode, offset = pcall(function()
        return prop:getNodePosition(floor.cid)
      end)
      if okNode and offset and offset.z < floor.z - B.shatter_drop_m then
        b.shattered[floor.index] = true
        b.stats.floors_broken = b.stats.floors_broken + 1
        b.stats.glass_down = b.stats.glass_down + 1
        emitEvent(state, "I", "atrium_floor_shattered", {floor = floor.index})
        if b.phase == "dropping" and b.subjectId then
          local vehicle = exactVehicle(b.subjectId)
          if vehicle then
            local velocity = vehicle:getVelocity()
            local fall = -velocity.z
            -- Clamp, don't scale: a fixed fraction has a ~12 m/s fixed
            -- point and never actually slows the descent.
            if fall > B.brake_cap_mps then
              addSubjectVelocity(state, vehicle, vec3(0, 0, fall - B.brake_cap_mps))
            end
            local mph = math.floor(velocity:length() * 2.237 + 0.5)
            showMessage(("FLOOR %d SHATTERED - %d mph"):format(floor.index, mph), 1.1)
          end
        end
      end
    end
  end
end

local function abortDrop(state, reason)
  local b = state.behavior
  emitEvent(state, "I", "atrium_drop_aborted", {reason = reason})
  b.phase = "settled"
  b.resetTimer = 0
  b.subjectId = nil
end

behavior.onSubjectGone = function(state, vehicleId, reason)
  local b = state.behavior
  if vehicleId ~= b.subjectId then return end
  -- Our own drop-release teleport fires a subject_reset one frame after
  -- atrium_drop_started (live run 1, 2026-07-23): ignore resets in the
  -- opening second of a drop. A real mid-fall player recovery later still
  -- aborts, and the zone-membership touchdown gate keeps an early
  -- recovery from scoring: the car respawns outside shaft/landing, so the
  -- drop can only end via the timeout abort.
  if b.phase == "dropping" and reason == "subject_reset" and b.dropTimer < 1.0 then
    return
  end
  if b.phase == "arming" or b.phase == "dropping" then
    abortDrop(state, reason or "subject_gone")
  end
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  b.elapsed = b.elapsed + dtSim
  checkFloors(state)
  if b.phase == "idle" then
    -- A car already waiting on the pad (its enter event was consumed
    -- during settle/reset) still deserves a ride.
    local queued = firstOccupant(state, "lift_pad")
    if queued then
      behavior.onEnter(state, "lift_pad", queued)
    end
  elseif b.phase == "arming" then
    local subject = b.subjectId and zoneOccupants(state, "lift_pad")[b.subjectId]
    if not subject then
      b.phase = "idle"
      b.subjectId = nil
      showMessage("The lift wants a passenger.", 1.4)
      return
    end
    b.countdown = b.countdown - dtSim
    local whole = math.max(0, math.ceil(b.countdown))
    if whole ~= b.countSpoken and whole > 0 then
      b.countSpoken = whole
      showMessage(("Dropping in %d..."):format(whole), 0.9)
    end
    if b.countdown <= 0 then
      local vehicle = exactVehicle(b.subjectId)
      if not vehicle then
        b.phase = "idle"
        b.subjectId = nil
        return
      end
      local rotation = quat(vehicle:getRotation())
      if teleportSubject(state, vehicle, toWorldPoint(state, B.drop_point), rotation) then
        launchSubject(state, vehicle, vec3(0, 0, -B.drop_release_mps))
        b.phase = "dropping"
        b.dropTimer = 0
        b.arrested = false
        showMessage("ENJOY THE VIEW. ALL TEN OF THEM.", 2.0)
        emitEvent(state, "I", "atrium_drop_started", {subject_id = b.subjectId})
      else
        b.phase = "idle"
        b.subjectId = nil
      end
    end
  elseif b.phase == "dropping" then
    b.dropTimer = b.dropTimer + dtSim
    local vehicle = b.subjectId and exactVehicle(b.subjectId)
    if not vehicle then
      abortDrop(state, "subject_vanished")
      return
    end
    local velocity = vehicle:getVelocity()
    local position = vehicle:getPosition()
    local origin = state.origin or position
    local height = position.z - origin.z
    -- Final arrest keyed on the CAR, not a sentinel: floor 10's sheet may
    -- not register its 1.2 m drop before the car reaches the cushion.
    local fall = -velocity.z
    if not b.arrested and height < B.landing_z + B.final_arrest_height_m
        and fall > B.brake_cap_mps then
      b.arrested = true
      addSubjectVelocity(state, vehicle, vec3(0, 0, fall - B.brake_cap_mps))
    end
    local speed = velocity:length()
    local inZones = zoneOccupants(state, "landing")[b.subjectId]
      or zoneOccupants(state, "shaft")[b.subjectId]
    if height < B.landing_z + 2.2 and speed < B.settle_speed_mps and inZones then
      b.phase = "settled"
      b.resetTimer = 0
      b.stats.drops_completed = b.stats.drops_completed + 1
      setEffectActive(state, "landing_dust", true)
      showMessage(
        ("TOUCHDOWN. %d floors shattered."):format(b.stats.glass_down), 2.4)
      emitEvent(state, "I", "atrium_drop_completed", {
        subject_id = b.subjectId,
        floors_shattered = b.stats.glass_down,
      })
    elseif b.dropTimer > B.drop_timeout_s then
      -- Stalled on unbroken glass mid-shaft: there is no drivable way out
      -- of the tower above the lobby, so hand the car back to the pad
      -- (leaving it would gate the reset forever).
      if zoneOccupants(state, "shaft")[b.subjectId] then
        showMessage("STUCK ON THE GLASS. The lift takes you back.", 2.2)
        teleportSubject(
          state, vehicle, toWorldPoint(state, B.lift_return_point),
          quat(vehicle:getRotation()))
        launchSubject(state, vehicle, vec3(0, 0, 0))
      end
      abortDrop(state, "drop_timeout")
    end
  elseif b.phase == "settled" then
    b.resetTimer = b.resetTimer + dtSim
    if b.resetTimer > 2.0 then
      setEffectActive(state, "landing_dust", false)
    end
    -- The lift pad deliberately does NOT gate the reset: it sits on the
    -- natural drive-out path and a car queueing there would soft-lock the
    -- glass forever (adversarial-review finding 2026-07-23).
    if b.resetTimer >= B.reset_delay_s
        and zoneCount(state, "landing") == 0
        and zoneCount(state, "shaft") == 0 then
      local prop = exactVehicle(state.propId)
      if prop then
        prop:requestReset(RESET_PHYSICS)
        showMessage("Glaziers dispatched. Atrium restored.", 1.8)
        emitEvent(state, "I", "atrium_restored", {})
        -- Stay in "resetting" until the confirmed reset callback clears
        -- b.shattered — clearing at queue time lets checkFloors re-latch
        -- the still-fallen sheets and kill the next run's brakes.
        b.phase = "resetting"
        b.resetTimer = 0
        b.subjectId = nil
      else
        b.phase = "idle"
        b.subjectId = nil
      end
    end
  elseif b.phase == "resetting" then
    b.resetTimer = b.resetTimer + dtSim
    if b.resetTimer > 5.0 then
      -- Reset callback never arrived; recover rather than wedge.
      behavior.reset(state)
    end
  end
end
"""
