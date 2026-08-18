"""Hot Potato — authored constants shared by Blender and the runtime.

A drive-through gate with a scorched russet potato hanging under its header.
Drive fully through the arch and the potato follows YOU: it hovers over your
roof, hisses, and counts down. Touch another car and it jumps to them, with a
short immunity window on the car that just passed it so it cannot ping-pong
bumper to bumper. When the fuse runs out, whoever is holding it gets shelled,
pressed and set alight. Keep going until one car is left intact.

Architecture notes that are easy to get wrong (see hot_potato/DESIGN.md for
the full audit of why):

- There is NO vehicle-vehicle collision hook on the GE side - zero
  occurrences in BeamNG 0.39's shipped Lua - so the transfer is a positional
  sweep over ``getAllVehicles()``, not an event. Trigger boxes could not do
  this job anyway: they are anchored to the prop and cannot follow a carrier.
- The fuse runs on ``Engine.Platform.getSystemTimeMS()``. ``dtSim`` inside a
  prop's ``behavior.update`` is NOT wall seconds (measured ~3x fast), and a
  countdown the player watches has to agree with their own clock.
- Detonation is a ladder, because the framework's GE-side velocity helpers
  are ``applyClusterVelocityScaleAdd`` - a uniform add over the whole node
  cluster that by construction cannot strain a single beam. Real damage
  comes from the vehicle side: breakgroups + tyres, then a per-node
  ``applyForceVector`` press, then the launch, then fire.
"""

MOD_ID = "ericrolph_hot_potato"
DISPLAY_NAME = "Hot Potato"
VALUE_DOLLARS = 12000
ZIP_BASENAME = "hot_potato_ericrolph.zip"

# Authored frame: right-handed, meters, Z-up, +Y drive direction.
APRON_HALF_X = 5.6
APRON_HALF_Y = 7.0
# Nearly flush with the terrain: the flyswatter's 0.12 m slab read as a
# floating plate, and anything a car drives over is capped at ~0.02 m of
# relief by the drivable-surface law.
APRON_TOP_Z = 0.04

POST_X = 4.2  # post centres; the drive-through gap is 2*(POST_X - POST_HALF)
POST_HALF = 0.5
POST_TOP_Z = 5.4

HEADER_HALF_X = 4.7
HEADER_HALF_Y = 0.6
HEADER_Z0 = 5.4
HEADER_Z1 = 6.2

# The potato's idle home: dead centre under the header, high enough that even
# the stock city bus (2.994 m) passes under it untouched.
POTATO_HOME = (0.0, 0.0, 4.15)
POTATO_SEMI_X = 0.95  # long axis across the gate
POTATO_SEMI_Y = 0.60
POTATO_SEMI_Z = 0.58

SIGN_HALF_X = 4.7
SIGN_HALF_Z = 0.49  # 9.4 x 0.98 m board = 9.59:1, matching marquee's aspect
SIGN_MID_Z = 5.8

PALETTE = {
    # The hero material. 2048 because this is the one surface a player will
    # put the camera against, and its structure (net cells ~4% of the tile)
    # is authored at true tuber proportions rather than true millimetres:
    # a giant potato has to read as a potato photographed close, not as
    # sandpaper.
    f"{MOD_ID}_potato": {
        "texture": {
            "family": "potato_skin",
            "size": 2048,
            "normal_strength": 3.6,
            # net_scale 3.4 lands the net cells near 8 cm on a ~2 m tuber -
            # the same cell-to-tuber proportion a real russet has. At 1.0 the
            # cells were ~28 cm and the skin read as marble veining.
            "params": {
                "eyes": 19,
                "net": 1.0,
                "net_scale": 3.4,
                "soil_amount": 0.5,
                "scuff": 0.5,
            },
        },
        "color": [0.60, 0.44, 0.28, 1.0],
        "metallic": 0.0,
        "roughness": 0.88,
    },
    f"{MOD_ID}_steel": {
        "texture": {"family": "steel_worn"},
        "color": [0.55, 0.57, 0.6, 1.0],
        "metallic": 0.85,
        "roughness": 0.38,
    },
    f"{MOD_ID}_paint_red": {
        "texture": {
            "family": "painted_metal",
            "params": {"base": [0.72, 0.14, 0.11], "rough": 0.42, "peel": 0.9},
        },
        "color": [0.72, 0.14, 0.11, 1.0],
        "metallic": 0.05,
        "roughness": 0.4,
    },
    f"{MOD_ID}_hazard": {
        "texture": {"family": "hazard_chevron", "size": 512},
        "color": [0.95, 0.75, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
    f"{MOD_ID}_concrete": {
        "texture": {"family": "concrete", "size": 1024},
        "color": [0.55, 0.54, 0.52, 1.0],
        "metallic": 0.0,
        "roughness": 0.88,
    },
    f"{MOD_ID}_sign": {
        "texture": {"family": "marquee", "params": {"text": "HOT POTATO"}},
        "color": [0.93, 0.94, 0.95, 1.0],
        "metallic": 0.0,
        "roughness": 0.34,
    },
}

TRIGGERS = {
    # Contains + bounding box: the launcher pattern. A round only starts when
    # a whole vehicle is inside the arch, which is also what makes "drive
    # through to pick it up" read as deliberate rather than incidental.
    "start_gate": {
        "mode": "Contains",
        "center": [0.0, 0.0, 2.4],
        "dimensions": [7.0, 6.0, 4.6],
    },
}

EFFECTS = {
    # All three are re-posed by the behaviour every frame; their authored
    # positions are only where they sit before the first round.
    "fuse": {
        "emitter": "BNGP_waterfallsteam",
        "position": [0.0, 0.0, 4.9],
        "direction": [0.0, 0.0, 1.0],
    },
    "blast": {
        "emitter": "BNGP_Fire_Huge",
        "position": [0.0, 0.0, 4.15],
        "direction": [0.0, 0.0, 1.0],
    },
    "cheer": {
        "emitter": "BNGP_confetti",
        "position": [0.0, 0.0, 6.3],
        "direction": [0.0, 0.0, 1.0],
    },
}

BEHAVIOR = {
    "camera_distance": 30.0,
    # --- the potato ------------------------------------------------------
    "potato_home": list(POTATO_HOME),
    "hover_clearance": 1.30,
    "spin_rate": 1.15,
    "bob_amplitude": 0.16,
    "bob_rate": 2.3,
    # --- fuse ------------------------------------------------------------
    "fuse_min_seconds": 24.0,
    "fuse_max_seconds": 38.0,
    "fuse_reset_on_pass": True,
    "warn_seconds": 10.0,
    # --- transfer --------------------------------------------------------
    # Touch mode measures each car's own spawn OOBB; radius mode uses one
    # constant for everybody. Touch is the fair default.
    "use_touch_mode": True,
    "touch_margin": 0.9,
    "transfer_radius": 6.0,
    "cooldown_seconds": 2.0,
    "join_immunity_seconds": 2.0,
    "min_players": 1,
    # --- detonation ------------------------------------------------------
    "detonate_break": True,
    "detonate_crush": True,
    "detonate_fire": True,
    "detonate_launch_mps": 16.0,
    # A physically meaningful number instead of a magic newton figure: the
    # vehicle-side command solves F = m*dv/physicsDt per node, so this IS
    # the downward velocity step the roof nodes take in one physics step
    # while the sills take none. That differential is the deformation.
    "crush_dv_mps": 7.5,
    "crush_min_z": 0.55,
    "crush_inward": 0.45,
    "fire_seconds": 6.0,
    "round_idle_seconds": 4.0,
    # --- carrier beacon --------------------------------------------------
    # Real light objects. This used to say "vehicle-material emissive is
    # inert in this pipeline (dead black across builds 63-69), so a glowing
    # marker can only be lights" - RETIRED 2026-08-15 (round 17): the black
    # materials had a FOUR-element `emissiveFactor`; three elements emit.
    # Lights are still right here, because a marker has to be seen from
    # across the arena and emissive ILLUMINATES NOTHING - it only self-glows.
    # Rate 3.0, not 9: at 9 the centrifuge's bar strobed 8.6 flashes/s
    # against a 60 Hz frame.
    "beacon_rate": 3.0,
    "beacon_height": 1.15,
    "beacon_brightness": 2.4,
    "beacon_radius": 7.5,
    "beacon_ray_range": 22.0,
    # --- safety ----------------------------------------------------------
    # Phys-explosion watchdog: a vehicle whose spawn OOBB half-extent
    # balloons past this has had a node explode. Stop feeding a solver that
    # is already losing it.
    "safety_enabled": True,
    "safety_extent_max": 24.0,
}

# Tunables the framework itself consumes; they never appear as `B.x` in the
# behaviour source.
FRAMEWORK_TUNABLES = frozenset({"camera_distance"})

LUA_BEHAVIOR = r"""
-- ==========================================================================
-- Hot Potato
--
-- One carrier at a time. The potato is a non-colliding TSStatic posed onto
-- the carrier's roof every frame; the carrier wears a rotating amber beacon
-- so everyone can see who is holding it. Transfer is a positional sweep,
-- never a trigger box, because a trigger box cannot follow a moving car.
-- ==========================================================================

local REQUIRED = {
  "potato_home", "hover_clearance", "spin_rate", "bob_amplitude", "bob_rate",
  "fuse_min_seconds", "fuse_max_seconds", "fuse_reset_on_pass", "warn_seconds",
  "use_touch_mode", "touch_margin", "transfer_radius", "cooldown_seconds",
  "join_immunity_seconds", "min_players",
  "detonate_break", "detonate_crush", "detonate_fire", "detonate_launch_mps",
  "crush_dv_mps", "crush_min_z", "crush_inward", "fire_seconds",
  "round_idle_seconds",
  "beacon_rate", "beacon_height", "beacon_brightness", "beacon_radius",
  "beacon_ray_range", "safety_enabled", "safety_extent_max",
}

-- Vehicle-side commands. Every one is fully guarded: a missing API must be a
-- no-op, never an error inside somebody's vehicle VM.
local BREAK_COMMAND = "pcall(function()"
  .. " if beamstate and beamstate.breakAllBreakgroups then"
  .. " beamstate.breakAllBreakgroups() end"
  .. " if beamstate and beamstate.deflateTires then beamstate.deflateTires()"
  .. " elseif beamstate and beamstate.deflateTire and wheels and wheels.wheelCount then"
  .. " for i = 0, wheels.wheelCount - 1 do beamstate.deflateTire(i) end end"
  .. " end)"

-- The press. obj:applyForceVector applies for ONE physics step, so the honest
-- way to size it is to solve for the velocity step you want:
--     F = m * dv / physicsDt
-- With physicsDt = 1/2000 s and a ~20 kg roof node, a 7.5 m/s step is about
-- 300 kN on that node. The reference blueprint's flat 80 kN one-shot works
-- out to ~2 m/s on the same node - a nudge, which is why "crushes the chassis
-- flat" never materialised. Only nodes above crush_min_z are driven, so the
-- roof travels and the sills do not: that differential is the deformation.
local CRUSH_TEMPLATE = "pcall(function()"
  .. " if not (v and v.data and v.data.nodes and obj and obj.applyForceVector) then return end"
  .. " local dv, minz, inward = %s, %s, %s"
  .. " local dt = physicsDt or 0.0005"
  .. " for cid, node in pairs(v.data.nodes) do"
  .. " local p = node.pos"
  .. " if p and p.z > minz then"
  .. " local m = 20"
  .. " if obj.getNodeMass then local okm, nm = pcall(function() return obj:getNodeMass(cid) end)"
  .. " if okm and nm and nm > 0 then m = nm end end"
  .. " local dir = vec3(-p.x * inward, -p.y * inward, -1)"
  .. " dir:normalize()"
  .. " obj:applyForceVector(cid, dir * (m * dv / dt))"
  .. " end end end)"

-- Fuel-tank ignition only: no impulse, no deformation, and silently nothing
-- at all on a vehicle with no flammable nodes or with fire disabled in
-- gameplay settings. Garnish on top of the real detonation, never the show.
local FIRE_COMMAND = "pcall(function()"
  .. " if fire and fire.explodeVehicle then fire.explodeVehicle() end end)"

local BEACON_SLOTS = {
  "beacon_glow", "beacon_ray_a", "beacon_ray_b",
}

-- --------------------------------------------------------------------------
-- Helpers. Every one is defined above its first caller: a Lua local binds at
-- its definition point, so a helper placed above the function it calls
-- resolves that name as a nil GLOBAL and only blows up when that path runs.
-- --------------------------------------------------------------------------

local function advanceClock(b, dtSim)
  -- dtSim in a prop's behavior.update is NOT wall seconds (measured ~3x
  -- fast), and this fuse is shown to the player as a number of seconds, so
  -- the wall clock is the authority and dtSim is only the fallback.
  local ok, ms = pcall(function() return Engine.Platform.getSystemTimeMS() end)
  if ok and type(ms) == "number" and ms == ms and ms > 0 then
    if not b.wallBase then b.wallBase = ms * 0.001 end
    b.now = ms * 0.001 - b.wallBase
    return
  end
  b.now = (b.now or 0) + (dtSim or 0) / 3.0
end

local function tunablesPresent(state)
  local missing = {}
  for _, key in ipairs(REQUIRED) do
    if B[key] == nil then missing[#missing + 1] = key end
  end
  if #missing == 0 then return true end
  emitError(state, "tunables_missing", {detail = table.concat(missing, ",")})
  return false
end

local function authoredAxes(state)
  -- The model rotation is orthonormal, so dotting a world offset with the
  -- three transformed unit axes is an EXACT inverse - no quat inverse call -
  -- and it is built from the same toWorldDir the triggers are placed with,
  -- so the frame the physics uses cannot drift from the authored one.
  return toWorldDir(state, vec3(1, 0, 0)),
         toWorldDir(state, vec3(0, 1, 0)),
         toWorldDir(state, vec3(0, 0, 1))
end

local function subjectExtents(state, vehicle)
  local b = state.behavior
  b.extents = b.extents or {}
  local id = vehicle:getId()
  local cached = b.extents[id]
  if cached then return cached end
  -- The SPAWN OOBB does not change with deformation, so this is one call per
  -- vehicle for the whole session rather than one per frame.
  local entry = {radius = 2.4, height = 0.85}
  local ok, half = pcall(function()
    return vehicle:getSpawnWorldOOBB():getHalfExtents()
  end)
  if ok and finiteVector3(half) then
    -- Mean of the two horizontal half-extents: the inscribed circle reads
    -- passes late on a long vehicle and the circumscribed one reads them
    -- early, so the honest approximation sits between and touch_margin is
    -- the knob. Stated as an approximation on purpose - it registers a pass
    -- slightly before paint meets paint on two long vehicles.
    entry.radius = math.max(0.6, (math.abs(half.x) + math.abs(half.y)) * 0.5)
    entry.height = math.max(0.4, math.abs(half.z))
  end
  b.extents[id] = entry
  return entry
end

local function explodedPhysics(vehicle)
  -- getSpawnWorldOOBB half-extents balloon by hundreds of metres when a node
  -- explodes. Confirmed live on 0.38.6.
  if not B.safety_enabled then return false end
  local ok, half = pcall(function()
    return vehicle:getSpawnWorldOOBB():getHalfExtents()
  end)
  if not ok or not finiteVector3(half) then return false end
  local reach = math.max(math.abs(half.x), math.abs(half.y), math.abs(half.z))
  return reach > B.safety_extent_max
end

local function roster(state)
  -- getAllVehicles() is ground truth. Trigger-set bookkeeping made a parked
  -- car invisible for minutes in the car wash rounds; nothing here is
  -- allowed to depend on a zone having delivered an event.
  local found = {}
  local ok, all = pcall(getAllVehicles)
  if not ok or type(all) ~= "table" then return found end
  local b = state.behavior
  for _, vehicle in ipairs(all) do
    local okId, id = pcall(function() return vehicle:getId() end)
    if okId and integer(id) and eligibleSubject(id) then
      if b.seen[id] == nil then b.seen[id] = b.now end
      if not b.out[id] then found[#found + 1] = {id = id, vehicle = vehicle} end
    end
  end
  return found
end

local function poseEffectAt(state, name, worldPos)
  local effect = state.effects[name]
  if not effect or not finiteVector3(worldPos) then return end
  pcall(function()
    effect:setPosRot(worldPos.x, worldPos.y, worldPos.z, 0, 0, 0, 1)
  end)
end

local function ensureBeacon(state)
  -- Real light objects parked in state.effects, which is what
  -- cleanupInstallation sweeps on unregister, destruction and mission end.
  local fields = {
    beacon_glow = {
      class = "PointLight",
      values = {
        radius = tostring(B.beacon_radius),
        brightness = tostring(B.beacon_brightness),
        castShadows = "0",
        color = "1 0.42 0.06 1",
      },
    },
    beacon_ray_a = {
      class = "SpotLight",
      values = {
        radius = tostring(B.beacon_ray_range),
        range = tostring(B.beacon_ray_range),
        brightness = tostring(B.beacon_brightness * 0.75),
        innerAngle = "10", outerAngle = "26",
        castShadows = "0",
        color = "1 0.38 0.05 1",
      },
    },
    beacon_ray_b = {
      class = "SpotLight",
      values = {
        radius = tostring(B.beacon_ray_range),
        range = tostring(B.beacon_ray_range),
        brightness = tostring(B.beacon_brightness * 0.75),
        innerAngle = "10", outerAngle = "26",
        castShadows = "0",
        color = "1 0.38 0.05 1",
      },
    },
  }
  for _, slot in ipairs(BEACON_SLOTS) do
    if not state.effects[slot] then
      local entry = fields[slot]
      local light = createObject(entry.class)
      if light then
        local built = pcall(function()
          light.loadMode = 1
          if type(light.preApply) == "function" then light:preApply() end
          setCanSaveFalse(light)
          for fieldName, fieldValue in pairs(entry.values) do
            light:setField(fieldName, 0, fieldValue)
          end
          light:setField("isEnabled", 0, "0")
          if type(light.postApply) == "function" then light:postApply() end
        end)
        local registered = built and registerInMission(
          light, string.format("%s_p%d_%s", PROP_MODEL, state.propId, slot))
        if registered then
          state.effects[slot] = light
        else
          pcall(function() light:delete() end)
        end
      end
    end
  end
end

local function beaconLit(state, lit)
  local b = state.behavior
  if b.beaconLit == lit then return end
  b.beaconLit = lit
  for _, slot in ipairs(BEACON_SLOTS) do
    local light = state.effects[slot]
    if light then
      pcall(function() light:setField("isEnabled", 0, lit and "1" or "0") end)
    end
  end
end

local function poseBeacon(state, worldPos)
  local b = state.behavior
  local glow = state.effects.beacon_glow
  if glow then
    pcall(function() glow:setPosition(vec3(worldPos.x, worldPos.y, worldPos.z)) end)
  end
  -- Aim recipe from the game's own photomodeFlash: setPosition plus the
  -- "rotation" field written as quatFromDir(dir, up):toTorqueQuat(). Never
  -- setPosRot on a light being steered every frame.
  for index, slot in ipairs({"beacon_ray_a", "beacon_ray_b"}) do
    local light = state.effects[slot]
    if light then
      local yaw = (b.beaconAngle or 0) + (index == 2 and math.pi or 0)
      local direction = vec3(-math.sin(yaw), math.cos(yaw), -0.18)
      direction:normalize()
      pcall(function()
        local rotation = quatFromDir(direction, vec3(0, 0, 1))
        if rotation.toTorqueQuat then rotation = rotation:toTorqueQuat() end
        light:setPosition(vec3(worldPos.x, worldPos.y, worldPos.z))
        light:setField("rotation", 0, rotation.x .. " " .. rotation.y
          .. " " .. rotation.z .. " " .. rotation.w)
      end)
    end
  end
end

local function posePotato(state, worldPos)
  local b = state.behavior
  local ex, ey, ez = authoredAxes(state)
  local offset = worldPos - state.origin
  -- Authored-frame point, then subtract the part's own pivot: posePartObjects
  -- computes origin + modelRotation * (pivot + offset).
  local authored = vec3(offset:dot(ex), offset:dot(ey), offset:dot(ez))
  local spin = axisAngle(vec3(0, 0, 1), b.spin or 0)
  local wobble = axisAngle(vec3(1, 0, 0), math.sin((b.now or 0) * 1.7) * 0.14)
  -- The spin has to live in the POSE QUATERNION. A baked Collada ambient
  -- clip would be restarted from frame zero by every setPosRot, and
  -- posePartObjects calls setPosRot every single frame - the clip would sit
  -- frozen on frame 0 forever.
  setPartPose(state, "potato", authored - B.potato_home, spin * wobble)
end

local function carrierAnchor(state, vehicle)
  local extents = subjectExtents(state, vehicle)
  local b = state.behavior
  local bob = math.sin((b.now or 0) * B.bob_rate) * B.bob_amplitude
  local position = vehicle:getPosition()
  return vec3(
    position.x,
    position.y,
    position.z + extents.height + B.hover_clearance + bob)
end

local function announce(state, message, ttl, event, fields)
  showMessage(message, ttl or 2.0)
  if event then emitEvent(state, "I", event, fields or {}) end
end

local function publishStats(state)
  -- getSystemState exposes state.behavior.stats verbatim, which is the only
  -- generic channel out of a behaviour. A probe cannot ask "who is holding
  -- it" any other way, and -1 rather than nil because a nil field simply
  -- vanishes from the table.
  local b = state.behavior
  b.stats = {
    carrier = b.carrier or -1,
    fuse_remaining = b.fuseEnds and math.max(0, b.fuseEnds - b.now) or -1,
    field = b.fieldPeak or 0,
    eliminated = b.outCount or 0,
  }
end

local function parkPotato(state)
  local b = state.behavior
  b.carrier = nil
  beaconLit(state, false)
  setEffectActive(state, "fuse", false)
  local home = toWorldPoint(state, B.potato_home)
  local bob = math.sin((b.now or 0) * B.bob_rate) * B.bob_amplitude
  posePotato(state, vec3(home.x, home.y, home.z + bob))
  poseEffectAt(state, "fuse", home)
end

local function giveTo(state, vehicle, reason)
  local b = state.behavior
  local id = vehicle:getId()
  local previous = b.carrier
  b.carrier = id
  b.heldSince = b.now
  if previous and previous ~= id then
    -- The anti-ping-pong window. Without it, two cars bumper to bumper swap
    -- the potato every single tick.
    b.immune[previous] = b.now + B.cooldown_seconds
  end
  if B.fuse_reset_on_pass or not b.fuseEnds then
    local span = math.max(0, B.fuse_max_seconds - B.fuse_min_seconds)
    b.fuseEnds = b.now + B.fuse_min_seconds + math.random() * span
  end
  b.lastWarned = nil
  b.phase = "live"
  setEffectActive(state, "fuse", true)
  beaconLit(state, true)
  emitEvent(state, "I", "potato_passed", {
    subject_id = id, previous_id = previous, reason = reason,
  })
end

local function detonate(state, vehicle)
  local b = state.behavior
  local id = vehicle:getId()
  b.phase = "boom"
  b.boomAt = b.now
  b.boomLaunched = false
  if not b.out[id] then b.outCount = (b.outCount or 0) + 1 end
  b.out[id] = true
  setEffectActive(state, "fuse", false)
  beaconLit(state, false)
  local anchor = carrierAnchor(state, vehicle)
  poseEffectAt(state, "blast", vec3(anchor.x, anchor.y, anchor.z - B.hover_clearance))
  setEffectActive(state, "blast", true)
  if B.detonate_break then
    pcall(function() vehicle:queueLuaCommand(BREAK_COMMAND) end)
  end
  if B.detonate_crush then
    local command = string.format(
      CRUSH_TEMPLATE,
      tostring(B.crush_dv_mps), tostring(B.crush_min_z), tostring(B.crush_inward))
    pcall(function() vehicle:queueLuaCommand(command) end)
  end
  if B.detonate_fire then
    pcall(function() vehicle:queueLuaCommand(FIRE_COMMAND) end)
  end
  announce(state, "BOOM!", 2.5, "detonation", {subject_id = id})
end

local function nearestPlayable(state, worldPos)
  local best, bestDistance
  for _, entry in ipairs(roster(state)) do
    local position = entry.vehicle:getPosition()
    if finiteVector3(position) then
      local distance = (position - worldPos):length()
      if not bestDistance or distance < bestDistance then
        best, bestDistance = entry.vehicle, distance
      end
    end
  end
  return best
end

local function sweepForPass(state, carrier)
  local b = state.behavior
  local carrierPosition = carrier:getPosition()
  if not finiteVector3(carrierPosition) then return end
  local carrierRadius = subjectExtents(state, carrier).radius
  local best, bestDistance
  for _, entry in ipairs(roster(state)) do
    local id = entry.id
    if id ~= b.carrier
      and (b.immune[id] or 0) <= b.now
      and (b.seen[id] or 0) + B.join_immunity_seconds <= b.now then
      local position = entry.vehicle:getPosition()
      if finiteVector3(position) then
        local distance = (position - carrierPosition):length()
        local threshold = B.transfer_radius
        if B.use_touch_mode then
          threshold = carrierRadius
            + subjectExtents(state, entry.vehicle).radius
            + B.touch_margin
        end
        if distance <= threshold and (not bestDistance or distance < bestDistance) then
          best, bestDistance = entry.vehicle, distance
        end
      end
    end
  end
  -- At most one pass per tick, always to the closest eligible car.
  if best then
    giveTo(state, best, "contact")
    announce(state, "PASSED!", 1.6)
  end
end

behavior.init = function(state)
  local b = state.behavior
  b.phase = "idle"
  b.now = 0
  b.wallBase = nil
  b.spin = 0
  b.beaconAngle = 0
  b.beaconLit = nil
  b.carrier = nil
  b.fuseEnds = nil
  b.lastWarned = nil
  b.fieldPeak = 0
  b.immune = {}
  b.seen = {}
  b.out = {}
  b.outCount = 0
  b.extents = {}
  b.ready = tunablesPresent(state)
  if not b.ready then return end
  ensureBeacon(state)
  setEffectActive(state, "fuse", false)
  setEffectActive(state, "blast", false)
  setEffectActive(state, "cheer", false)
  parkPotato(state)
end

behavior.reset = function(state)
  behavior.init(state)
end

behavior.onEnter = function(state, zone, vehicle)
  local b = state.behavior
  if not b.ready then return end
  if zone ~= "start_gate" then return end
  if b.phase ~= "idle" then return end
  b.out = {}
  b.outCount = 0
  b.extents = {}
  local field = roster(state)
  if #field < B.min_players then
    announce(state, "Hot Potato needs " .. tostring(B.min_players) .. " cars.", 2.5)
    return
  end
  b.fieldPeak = #field
  giveTo(state, vehicle, "gate")
  announce(state, "YOU'VE GOT IT - pass it on!", 3.0, "round_started",
    {subject_id = vehicle:getId()})
end

behavior.onSubjectGone = function(state, vehicleId, reason)
  local b = state.behavior
  if not b.ready then return end
  b.seen[vehicleId] = nil
  b.extents[vehicleId] = nil
  if b.carrier ~= vehicleId then return end
  -- The carrier vanished mid-round: the potato goes home and the fuse stops.
  -- Never silently pick a new victim, and never leave the potato orbiting a
  -- dead id.
  b.phase = "idle"
  b.fuseEnds = nil
  parkPotato(state)
  announce(state, "Potato returned to the gate.", 2.5, "carrier_lost",
    {subject_id = vehicleId, reason = reason})
end

-- The round itself. Split out of behavior.update so every early return still
-- ends with one publishStats, rather than each exit path having to remember.
local function stepRound(state, dtSim)
  local b = state.behavior

  if b.phase == "idle" then
    parkPotato(state)
    return
  end

  if b.phase == "boom" then
    local since = b.now - (b.boomAt or b.now)
    local victim = exactVehicle(b.carrier)
    -- The launch lands one tick behind the press so the panels are already
    -- shedding when the wreck leaves the ground.
    if not b.boomLaunched and since >= 0.12 then
      b.boomLaunched = true
      if victim then
        launchSubject(state, victim, vec3(0, 0, B.detonate_launch_mps))
      end
    end
    if since >= B.fire_seconds then setEffectActive(state, "blast", false) end
    if since >= B.fire_seconds + B.round_idle_seconds then
      local remaining = roster(state)
      if #remaining >= 2 then
        local home = toWorldPoint(state, B.potato_home)
        local next_carrier = nearestPlayable(state, home)
        if next_carrier then
          giveTo(state, next_carrier, "respawn")
          announce(state, "STILL IN PLAY!", 2.5)
          return
        end
      end
      -- A winner only exists if there was ever a field to win against: the
      -- peak roster size this round, not min_players, is what makes
      -- "last car standing" true. Gating on min_players instead meant the
      -- confetti could never fire at the solo default.
      if #remaining == 1 and (b.fieldPeak or 0) >= 2 then
        setEffectActive(state, "cheer", true)
        announce(state, "LAST CAR STANDING!", 4.0, "round_won",
          {subject_id = remaining[1].id})
      end
      b.phase = "idle"
      b.carrier = nil
      b.fuseEnds = nil
      parkPotato(state)
    end
    return
  end

  -- phase == "live"
  setEffectActive(state, "cheer", false)
  local carrier = exactVehicle(b.carrier)
  if not carrier then
    b.phase = "idle"
    b.fuseEnds = nil
    parkPotato(state)
    return
  end
  if explodedPhysics(carrier) then
    -- Quarantine rather than keep driving a solver that is already losing
    -- the vehicle.
    b.out[b.carrier] = true
    b.phase = "idle"
    b.fuseEnds = nil
    parkPotato(state)
    announce(state, "Carrier quarantined.", 2.5, "carrier_quarantined",
      {subject_id = b.carrier})
    return
  end

  local anchor = carrierAnchor(state, carrier)
  posePotato(state, anchor)
  poseEffectAt(state, "fuse", anchor)
  poseBeacon(state, vec3(anchor.x, anchor.y, anchor.z + B.beacon_height))

  sweepForPass(state, carrier)
  local field = #roster(state)
  if field > (b.fieldPeak or 0) then b.fieldPeak = field end

  local remaining = (b.fuseEnds or b.now) - b.now
  if remaining <= B.warn_seconds then
    local tick = math.ceil(remaining)
    if tick >= 0 and b.lastWarned ~= tick then
      b.lastWarned = tick
      if tick > 0 then showMessage(tostring(tick) .. "...", 0.9) end
    end
  end
  if remaining <= 0 then
    detonate(state, carrier)
  end
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  if not b.ready then return end
  advanceClock(b, dtSim)
  b.spin = (b.spin + (dtSim or 0) * B.spin_rate) % (math.pi * 2)
  b.beaconAngle = (b.beaconAngle + (dtSim or 0) * B.beacon_rate) % (math.pi * 2)
  stepRound(state, dtSim)
  publishStats(state)
end
"""
