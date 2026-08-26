"""Hot Potato — authored constants shared by Blender and the runtime.

A Gateway Arch in creamy white with a scorched russet potato hanging under
its apex. Drive onto the medallion and the potato lands on YOUR roof: it
rides there, hissing and pulsing, while a hidden fuse burns. Tap another car
hard enough and it jumps to them. When the fuse runs out, whoever is holding
it goes up.

Architecture notes that are easy to get wrong (see hot_potato/DESIGN.md for
the full audit of why):

- There is NO vehicle-vehicle collision hook on the GE side - zero
  occurrences in BeamNG 0.39's shipped Lua - so both the PICKUP and the
  TRANSFER are positional sweeps over ``getAllVehicles()``, not events.
  v1 used a ``Contains`` BeamNGTrigger for the pickup and the player's own
  beamng.log showed ``prop_registered`` followed by no ``zone_enter`` at all
  across 100 seconds of driving through it. The trigger survives only as
  telemetry and a secondary path.
- The fuse runs on ``Engine.Platform.getSystemTimeMS()``. ``dtSim`` inside a
  prop's ``behavior.update`` is NOT wall seconds (measured ~3x fast).
- Carrying the potato cannot damage the car. The only force the carrier ever
  receives is ``applyClusterVelocityScaleAdd``, a uniform add over the whole
  node cluster, which by construction cannot strain a single beam.
"""

MOD_ID = "ericrolph_hot_potato"
DISPLAY_NAME = "Hot Potato"
VALUE_DOLLARS = 12000
ZIP_BASENAME = "hot_potato_ericrolph.zip"

# --------------------------------------------------------------------------
# The arch. Authored frame: right-handed, meters, Z-up, +Y drive direction.
#
# Gateway Arch proportions, scaled. The published centroid curve is
#     y = 693.8597 - 68.7672 cosh(0.0100333 x)  (feet, |x| <= 299.2239)
# giving shape parameter C = 3.0023 and height / half-span = 2.089, and a
# triangular section tapering 54 ft -> 17 ft (8.57% -> 2.70% of the span).
# --------------------------------------------------------------------------
ARCH_HALF_SPAN = 15.0
ARCH_C = 3.0023
ARCH_HEIGHT = ARCH_HALF_SPAN * 2.089  # 31.34 m
ARCH_BASE_SIDE = 2.57  # 54/630 of the span
ARCH_TOP_SIDE = 0.81  # 17/630 of the span
ARCH_STATIONS = 121
ARCH_FOOT_OVERRUN = 1.005  # legs bury ~0.5 m so no end caps are needed
ARCH_UV_TILE = 4.0
ARCH_COLLIDE_MAX_Z = 9.0  # skin the cage only where a car can reach

MEDALLION_RADIUS = 4.2
MEDALLION_TOP_Z = 0.05
PAD_HALF = 3.0  # cage lattice half-extent under the medallion
PYLON_HALF = 0.9
PYLON_TOP_Z = 4.0
CAGE_RING_STRIDE = 6  # every 6th station becomes a cage ring

# The potato's idle home: under the apex, high enough to clear a city bus
# (2.994 m) with room to spare, low enough to read from a car.
POTATO_HOME = (0.0, 0.0, 5.6)
POTATO_SEMI_X = 0.95
POTATO_SEMI_Y = 0.60
POTATO_SEMI_Z = 0.58

PALETTE = {
    # The hero material. 2048 because this is the one surface a player will
    # put the camera against.
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
    # Creamy white with the faintest warm cast and a soft sheen. The real
    # arch is stainless; cream keeps the silhouette and drops the mirror,
    # which is what makes it read as elegant rather than industrial.
    f"{MOD_ID}_arch_cream": {
        "texture": {
            "family": "painted_metal",
            "size": 1024,
            "params": {"base": [0.941, 0.925, 0.878], "rough": 0.30, "peel": 0.10},
        },
        "color": [0.941, 0.925, 0.878, 1.0],
        "metallic": 0.08,
        "roughness": 0.30,
        # The arch is a swept tube whose windings are derived per face, but
        # double-siding is the pack's standing policy after an invisible ramp
        # and an invisible door leaf both shipped.
        "double_sided": True,
    },
    f"{MOD_ID}_medallion_stone": {
        "texture": {"family": "concrete", "size": 1024},
        "color": [0.80, 0.78, 0.74, 1.0],
        "metallic": 0.0,
        "roughness": 0.82,
    },
    f"{MOD_ID}_bronze": {
        "texture": {"family": "copper", "size": 512},
        "color": [0.55, 0.40, 0.20, 1.0],
        "metallic": 0.9,
        "roughness": 0.36,
    },
}

TRIGGERS = {
    # Telemetry and a SECONDARY pickup path only. The authoritative pickup is
    # the positional sweep: a Contains trigger here never fired once in a
    # real play session, and Overlaps still reads entries late and exits
    # early for a moving vehicle.
    "pad": {
        "mode": "Overlaps",
        "center": [0.0, 0.0, 1.6],
        "dimensions": [2 * PAD_HALF, 2 * PAD_HALF, 3.2],
    },
}

EFFECTS = {
    # All three are re-posed by the behaviour; the authored positions are
    # only where they sit before the first round.
    "fuse": {
        # Verified small accent (the car wash's exhaust-steam layer).
        # BNGP_waterfallsteam threw a 30 m column in the live gate that read
        # as a separate object hanging over the car, not as a smoking potato.
        "emitter": "BNGP_34",
        "position": [0.0, 0.0, 6.4],
        "direction": [0.0, 0.0, 1.0],
    },
    "blast": {
        "emitter": "BNGP_Fire_Huge",
        "position": [0.0, 0.0, 5.6],
        "direction": [0.0, 0.0, 1.0],
    },
    "cheer": {
        "emitter": "BNGP_confetti",
        "position": [0.0, 0.0, 7.2],
        "direction": [0.0, 0.0, 1.0],
    },
}

BEHAVIOR = {
    "camera_distance": 46.0,
    # --- the potato ------------------------------------------------------
    "potato_home": list(POTATO_HOME),
    "pad_center": [0.0, 0.0, 0.0],
    "spin_rate": 0.55,
    "bob_amplitude": 0.16,
    "bob_rate": 2.3,
    # How deep the tuber sits into the roof line so it reads as ATTACHED
    # rather than hovering. Measured against each car's own spawn OOBB.
    "attach_sink": 0.16,
    "attach_wobble": 0.06,
    # --- pickup ----------------------------------------------------------
    "pickup_radius": 7.5,
    "pickup_height": 4.0,
    # --- fuse (mod controls) ---------------------------------------------
    # Gaussian, not uniform: a flat 45-75 range makes 45 as likely as 60, so
    # players never learn a rhythm. Base 60 with sigma 5 puts 99.7% of draws
    # inside the 45-75 clamp and clusters them where the feel was tuned.
    "fuse_base_seconds": 60.0,
    "fuse_sigma_seconds": 5.0,
    "fuse_min_seconds": 45.0,
    "fuse_max_seconds": 75.0,
    # Guaranteed minimum hot window: a receiver always gets at least this
    # long, so being tagged with 0.4 s left is a scare, not an execution.
    "grace_seconds": 4.0,
    # --- transfer (mod controls) -----------------------------------------
    # "touch" requires real contact plus a real closing speed; "radius" is a
    # bubble of forgiveness for casual play.
    "transfer_mode": "touch",
    # Small, because contactRange is now an exact box support function
    # rather than one averaged radius: this is slack for the spawn OOBB
    # being the UNDEFORMED body, not a guess at the body itself.
    "touch_margin": 0.35,
    "radius_m": 12.0,
    # Minimum closing speed for a touch transfer. Stops two stationary cars
    # brushing fenders to farm immunity windows.
    "impact_kmh": 15.0,
    # Anti-tag-back, all three of which must clear before it can come back:
    "tagback_immunity_seconds": 3.5,
    "tagback_min_hold_seconds": 2.0,
    "tagback_separation_m": 0.305,  # one foot
    "join_immunity_seconds": 2.0,
    "min_players": 1,
    # --- carrier handicap ------------------------------------------------
    # Dodging is easier than intercepting, so the holder gets a slipstream to
    # force chases to resolve. A uniform cluster velocity add: it can move
    # the car but by construction cannot strain a beam, so carrying stays
    # harmless.
    "carrier_boost_mps2": 0.8,
    "carrier_boost_max_mps": 62.0,
    # --- cues (no numeric countdown, by design) --------------------------
    "cue_window_seconds": 30.0,
    "beep_slow_interval": 1.55,
    "beep_fast_interval": 0.13,
    "beep_pitch_rise": 0.85,
    "audio_enabled": True,
    "beacon_pulse_seconds": 0.11,
    "beacon_brightness": 2.6,
    "beacon_radius": 8.0,
    "beacon_ray_range": 26.0,
    "beacon_spin_rate": 3.0,
    # --- detonation ------------------------------------------------------
    "detonate_break": True,
    "detonate_crush": True,
    "detonate_fire": True,
    "detonate_launch_mps": 16.0,
    # Physically meaningful: the vehicle-side command solves F = m*dv/
    # physicsDt per node, so this IS the downward velocity step the roof
    # nodes take in one physics step while the sills take none.
    "crush_dv_mps": 7.5,
    "crush_min_z": 0.55,
    "crush_inward": 0.45,
    "fire_seconds": 6.0,
    "round_idle_seconds": 5.0,
    # --- safety ----------------------------------------------------------
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
-- One carrier at a time. The potato rides the carrier's roof, the carrier
-- wears a pulsing amber beacon, and a hidden Gaussian fuse burns down with
-- accelerating audio-visual cues instead of a number on screen.
--
-- Both the pickup and the transfer are POSITIONAL SWEEPS. v1 used a
-- Contains BeamNGTrigger for the pickup; the player's beamng.log recorded
-- prop_registered and then no zone_enter at all for a whole session of
-- driving through the gate. A trigger box also cannot follow a carrier, so
-- it was never an option for the transfer. The trigger that remains is
-- telemetry plus a secondary pickup path.
-- ==========================================================================

local REQUIRED = {
  "potato_home", "pad_center", "spin_rate", "bob_amplitude", "bob_rate",
  "attach_sink", "attach_wobble", "pickup_radius", "pickup_height",
  "fuse_base_seconds", "fuse_sigma_seconds", "fuse_min_seconds",
  "fuse_max_seconds", "grace_seconds",
  "transfer_mode", "touch_margin", "radius_m", "impact_kmh",
  "tagback_immunity_seconds", "tagback_min_hold_seconds",
  "tagback_separation_m", "join_immunity_seconds", "min_players",
  "carrier_boost_mps2", "carrier_boost_max_mps",
  "cue_window_seconds", "beep_slow_interval", "beep_fast_interval",
  "beep_pitch_rise", "audio_enabled", "beacon_pulse_seconds",
  "beacon_brightness", "beacon_radius", "beacon_ray_range",
  "beacon_spin_rate",
  "detonate_break", "detonate_crush", "detonate_fire", "detonate_launch_mps",
  "crush_dv_mps", "crush_min_z", "crush_inward", "fire_seconds",
  "round_idle_seconds", "safety_enabled", "safety_extent_max",
}

-- Live, player-adjustable options. OPT is seeded from the shipped B table
-- and then overlaid from the settings file; ALL gameplay reads OPT, never B,
-- so a control change takes effect on the next tick without a rebuild.
local OPT = {}
local SETTINGS_PATH = "settings/ericrolph_hot_potato.json"
local OPTION_RANGE = {
  fuse_base_seconds = {10, 600}, fuse_sigma_seconds = {0, 60},
  fuse_min_seconds = {5, 600}, fuse_max_seconds = {5, 900},
  grace_seconds = {0, 30},
  transfer_mode = "enum", touch_margin = {0, 6}, radius_m = {1, 60},
  impact_kmh = {0, 120},
  tagback_immunity_seconds = {0, 30}, tagback_min_hold_seconds = {0, 30},
  tagback_separation_m = {0, 10}, join_immunity_seconds = {0, 30},
  min_players = {1, 16},
  pickup_radius = {2, 40}, pickup_height = {1, 20},
  carrier_boost_mps2 = {0, 8}, carrier_boost_max_mps = {5, 200},
  cue_window_seconds = {1, 300}, beep_slow_interval = {0.05, 5},
  beep_fast_interval = {0.03, 5}, beep_pitch_rise = {0, 3},
  audio_enabled = "bool",
  detonate_break = "bool", detonate_crush = "bool", detonate_fire = "bool",
  detonate_launch_mps = {0, 80},
}

-- Verified stock FMOD event paths (grepped out of the shipped Lua tree, not
-- invented). Engine.Audio.playOnce takes an EVENT path on a named channel
-- and accepts volume/pitch - which is what makes an accelerating, rising
-- fuse tick possible without shipping a single audio file.
local SFX_TICK = "event:>Vehicle>Electrics>Reverse>Beep_01"
local SFX_PASS = "event:>UI>Career>Drift_Combo_1x"
local SFX_PICKUP = "event:>UI>Missions>Info_Open"
local SFX_BOOM = "event:>Vehicle>Failures>engine_explode"
local SFX_WIN = "event:>UI>Career>EndScreen_Receive_XP"

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
-- Only nodes above crush_min_z are driven, so the roof travels and the sills
-- do not: that differential is the deformation. This runs at detonation and
-- only at detonation - nothing touches the car while it is carrying.
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

local FIRE_COMMAND = "pcall(function()"
  .. " if fire and fire.explodeVehicle then fire.explodeVehicle() end end)"

local BEACON_SLOTS = {"beacon_glow", "beacon_ray_a", "beacon_ray_b"}

-- --------------------------------------------------------------------------
-- Helpers, each defined above its first caller. A Lua local binds at its
-- definition point, so a helper placed above the function it calls resolves
-- that name as a nil GLOBAL and blows up only when that path runs.
-- --------------------------------------------------------------------------

local function clampNumber(value, low, high)
  if value < low then return low end
  if value > high then return high end
  return value
end

local function seedOptions()
  for key, value in pairs(B) do OPT[key] = value end
end

local function coerceOption(key, value)
  local range = OPTION_RANGE[key]
  if range == nil then return nil, "not an adjustable option" end
  if range == "bool" then
    if type(value) == "boolean" then return value end
    if value == 1 or value == "true" then return true end
    if value == 0 or value == "false" then return false end
    return nil, "expected a boolean"
  end
  if range == "enum" then
    if value == "touch" or value == "radius" then return value end
    return nil, "expected 'touch' or 'radius'"
  end
  local number = tonumber(value)
  if not number or number ~= number then return nil, "expected a number" end
  return clampNumber(number, range[1], range[2])
end

local function loadOptions()
  seedOptions()
  local ok, stored = pcall(jsonReadFile, SETTINGS_PATH)
  if not ok or type(stored) ~= "table" then return end
  for key, value in pairs(stored) do
    local coerced = coerceOption(key, value)
    if coerced ~= nil then OPT[key] = coerced end
  end
end

local function saveOptions()
  local payload = {}
  for key in pairs(OPTION_RANGE) do payload[key] = OPT[key] end
  pcall(jsonWriteFile, SETTINGS_PATH, payload, true)
end

local function gaussianFuse()
  -- Box-Muller. Clamped to [min, max]; with base 60 and sigma 5 the clamp is
  -- three sigma out, so it almost never bites and the distribution stays
  -- honest rather than piling up on the bounds.
  local u1 = math.max(1e-12, math.random())
  local u2 = math.random()
  local z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
  return clampNumber(
    OPT.fuse_base_seconds + z * OPT.fuse_sigma_seconds,
    OPT.fuse_min_seconds, OPT.fuse_max_seconds)
end

local function advanceClock(b, dtSim)
  -- The fuse is a promise to the player about SECONDS, and dtSim in a prop's
  -- behavior.update is not wall seconds (measured ~3x fast), so the wall
  -- clock is the authority.
  --
  -- But it accumulates a DELTA rather than reading elapsed-since-start, and
  -- only on frames where the simulation actually advanced. Proven necessary
  -- live: under a paused-and-stepped session the fuse kept burning real
  -- seconds while the world stood still, so a 62 s fuse expired during 18 s
  -- of stepping. A player who hits pause should not lose the round, and a
  -- player alt-tabbed into a menu should not come back to a crater.
  b.now = b.now or 0
  local ok, ms = pcall(function() return Engine.Platform.getSystemTimeMS() end)
  if ok and type(ms) == "number" and ms == ms and ms > 0 then
    local seconds = ms * 0.001
    local previous = b.wallLast or seconds
    b.wallLast = seconds
    local delta = seconds - previous
    -- Clamp: a level load or an alt-tab can leave a huge gap, and a clock
    -- that jumps must not detonate somebody the instant the game resumes.
    if delta < 0 or delta > 0.5 then delta = 0 end
    if (dtSim or 0) > 0 then b.now = b.now + delta end
    return
  end
  b.now = b.now + (dtSim or 0) / 3.0
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

local function playSound(event, pitch, volume)
  if not OPT.audio_enabled then return end
  pcall(function()
    Engine.Audio.playOnce("AudioGui", event, {
      volume = volume or 1.0,
      pitch = pitch or 1.0,
      fadeInTime = -1,
      fadeOutTime = -1,
    })
  end)
end

local function authoredAxes(state)
  -- The model rotation is orthonormal, so dotting a world offset with the
  -- three transformed unit axes is an EXACT inverse - no quat inverse call.
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
  -- vehicle per session rather than one per frame.
  -- hx / hy / hz are half WIDTH, half LENGTH and half HEIGHT along the
  -- vehicle's own right / forward / up axes.
  local entry = {hx = 0.95, hy = 2.4, height = 0.75}
  local ok, half = pcall(function()
    return vehicle:getSpawnWorldOOBB():getHalfExtents()
  end)
  if ok and finiteVector3(half) then
    entry.hx = math.max(0.3, math.abs(half.x))
    entry.hy = math.max(0.3, math.abs(half.y))
    entry.height = math.max(0.4, math.abs(half.z))
  end
  b.extents[id] = entry
  return entry
end

local function explodedPhysics(vehicle)
  if not OPT.safety_enabled then return false end
  local ok, half = pcall(function()
    return vehicle:getSpawnWorldOOBB():getHalfExtents()
  end)
  if not ok or not finiteVector3(half) then return false end
  local reach = math.max(math.abs(half.x), math.abs(half.y), math.abs(half.z))
  return reach > OPT.safety_extent_max
end

local function roster(state)
  -- getAllVehicles() is ground truth. Trigger-set bookkeeping made a parked
  -- car invisible for minutes in the car wash rounds, and cost this mod its
  -- entire pickup path in v1.
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
  -- Real light objects parked in state.effects, which is the table
  -- cleanupInstallation sweeps on unregister, destruction and mission end.
  -- Vehicle-material emissive is inert in this pipeline, so a "glowing"
  -- marker can only ever be lights.
  local fields = {
    beacon_glow = {
      class = "PointLight",
      values = {
        radius = tostring(OPT.beacon_radius),
        brightness = tostring(OPT.beacon_brightness),
        castShadows = "0",
        color = "1 0.42 0.06 1",
      },
    },
    beacon_ray_a = {
      class = "SpotLight",
      values = {
        radius = tostring(OPT.beacon_ray_range),
        range = tostring(OPT.beacon_ray_range),
        brightness = tostring(OPT.beacon_brightness * 0.8),
        innerAngle = "10", outerAngle = "28",
        castShadows = "0",
        color = "1 0.38 0.05 1",
      },
    },
    beacon_ray_b = {
      class = "SpotLight",
      values = {
        radius = tostring(OPT.beacon_ray_range),
        range = tostring(OPT.beacon_ray_range),
        brightness = tostring(OPT.beacon_brightness * 0.8),
        innerAngle = "10", outerAngle = "28",
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
      local direction = vec3(-math.sin(yaw), math.cos(yaw), -0.16)
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

local function posePotato(state, worldPos, worldRotation)
  local ex, ey, ez = authoredAxes(state)
  local offset = worldPos - state.origin
  -- Authored-frame point, then subtract the part's own pivot:
  -- posePartObjects computes origin + modelRotation * (pivot + offset).
  local authored = vec3(offset:dot(ex), offset:dot(ey), offset:dot(ez))
  local pose = worldRotation
  if pose then
    -- posePartObjects applies `rotation * modelRotation`, and quats compose
    -- left to right, so to land on a WORLD rotation Q the pose term must be
    -- Q * modelRotation^-1. For a unit quat the conjugate IS the inverse,
    -- which avoids depending on an :inversed() method existing.
    local m = state.modelRotation
    pose = worldRotation * quat(-m.x, -m.y, -m.z, m.w)
  else
    pose = quat(0, 0, 0, 1)
  end
  setPartPose(state, "potato", authored - B.potato_home, pose)
end

local function carrierPose(state, vehicle)
  -- Sit ON the roof and follow the car's heading, so it reads as attached
  -- rather than as a balloon on a string. getRotation() is STALE for a
  -- driven vehicle (it updates on spawn/teleport/reset only), so the live
  -- basis comes from the direction vectors.
  local b = state.behavior
  local extents = subjectExtents(state, vehicle)
  -- getPosition() returns the ref node, which on most vehicles sits forward
  -- of the body centre - live it put the tuber overhanging the windscreen.
  -- The spawn OOBB's centre is the geometric middle of the body.
  local position = vehicle:getPosition()
  local okCentre, centre = pcall(function()
    return vehicle:getSpawnWorldOOBB():getCenter()
  end)
  if okCentre and finiteVector3(centre) then
    local candidate = vec3(centre.x, centre.y, centre.z)
    -- Guard: if the box ever stops tracking the vehicle, fall back rather
    -- than leave the potato parked at the spawn point.
    if (candidate - position):length() < 5.0 then position = candidate end
  end
  local up = vec3(0, 0, 1)
  local forward = vec3(0, 1, 0)
  local okUp, liveUp = pcall(function() return vehicle:getDirectionVectorUp() end)
  if okUp and finiteVector3(liveUp) and liveUp:length() > 0.1 then
    up = vec3(liveUp.x, liveUp.y, liveUp.z)
    up:normalize()
  end
  local okFwd, liveFwd = pcall(function() return vehicle:getDirectionVector() end)
  if okFwd and finiteVector3(liveFwd) and liveFwd:length() > 0.1 then
    forward = vec3(liveFwd.x, liveFwd.y, liveFwd.z)
    forward:normalize()
  end
  local lift = extents.height * 2.0 - OPT.attach_sink
  local wobble = math.sin((b.now or 0) * 5.3) * OPT.attach_wobble
  local anchor = vec3(
    position.x + up.x * lift,
    position.y + up.y * lift,
    position.z + up.z * lift + wobble)
  local rotation = nil
  local okRot, built = pcall(function() return quatFromDir(forward, up) end)
  if okRot and built then rotation = built end
  return anchor, rotation
end

local function announce(state, message, ttl, event, fields)
  showMessage(message, ttl or 2.0)
  if event then emitEvent(state, "I", event, fields or {}) end
end

local function publishStats(state)
  -- getSystemState exposes state.behavior.stats verbatim, which is the only
  -- generic channel out of a behaviour. -1 rather than nil because a nil
  -- field simply vanishes from the table.
  local b = state.behavior
  b.stats = {
    carrier = b.carrier or -1,
    fuse_remaining = b.fuseEnds and math.max(0, b.fuseEnds - b.now) or -1,
    field = b.fieldPeak or 0,
    eliminated = b.outCount or 0,
    transfers = b.transfers or 0,
    mode = OPT.transfer_mode,
  }
end

local function parkPotato(state)
  local b = state.behavior
  b.carrier = nil
  state.zones.carrier_watch = nil
  beaconLit(state, false)
  setEffectActive(state, "fuse", false)
  setEffectActive(state, "blast", false)
  local home = toWorldPoint(state, B.potato_home)
  local bob = math.sin((b.now or 0) * OPT.bob_rate) * OPT.bob_amplitude
  local idleSpin = quat(0, 0, math.sin((b.spin or 0) * 0.5), math.cos((b.spin or 0) * 0.5))
  posePotato(state, vec3(home.x, home.y, home.z + bob), idleSpin)
  poseEffectAt(state, "fuse", home)
end

local function giveTo(state, vehicle, reason)
  local b = state.behavior
  local id = vehicle:getId()
  local previous = b.carrier
  b.carrier = id
  b.heldSince = b.now
  b.transfers = (b.transfers or 0) + 1
  if previous and previous ~= id then
    -- Anti-tag-back: the passer is immune for a window, AND the pair must
    -- physically separate before the potato may come back (see sweepForPass).
    b.immune[previous] = b.now + OPT.tagback_immunity_seconds
    b.pairFrom = previous
    b.pairTo = id
    b.pairSeparated = false
  else
    b.pairFrom, b.pairTo, b.pairSeparated = nil, nil, true
  end
  -- Register the carrier in a synthetic zone. The framework's reset path
  -- (onVehicleResetted -> removeSubjectEverywhere -> behavior.onSubjectGone)
  -- only fires for vehicles it finds in state.zones - and a sweep-discovered
  -- carrier was never in any zone, so resetting it left the potato riding
  -- the reset car with the fuse still burning (review finding, PR #87).
  -- The zone name has no TRIGGER_SPECS entry on purpose: nothing poses it,
  -- and rebuildTriggers clearing it is fine because every giveTo re-arms it.
  state.zones.carrier_watch = {[id] = true}
  if not b.fuseEnds then
    -- The fuse is a SHARED POOL drawn once per round, not a per-carrier
    -- timer: passing it on buys you distance, not a fresh minute.
    b.fuseEnds = b.now + gaussianFuse()
  else
    -- Guaranteed minimum hot window.
    b.fuseEnds = math.max(b.fuseEnds, b.now + OPT.grace_seconds)
  end
  b.phase = "live"
  setEffectActive(state, "fuse", true)
  beaconLit(state, true)
  playSound(previous and SFX_PASS or SFX_PICKUP, 1.0, 1.0)
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
  local anchor = carrierPose(state, vehicle)
  poseEffectAt(state, "blast", anchor)
  setEffectActive(state, "blast", true)
  playSound(SFX_BOOM, 1.0, 1.0)
  if OPT.detonate_break then
    pcall(function() vehicle:queueLuaCommand(BREAK_COMMAND) end)
  end
  if OPT.detonate_crush then
    local command = string.format(
      CRUSH_TEMPLATE,
      tostring(OPT.crush_dv_mps), tostring(OPT.crush_min_z),
      tostring(OPT.crush_inward))
    pcall(function() vehicle:queueLuaCommand(command) end)
  end
  if OPT.detonate_fire then
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

local function closingSpeed(first, second)
  -- Relative velocity projected onto the line between them: positive when
  -- they are actually converging. There is no collision event to read an
  -- impact from, so this IS the impact speed.
  local okA, va = pcall(function() return first:getVelocity() end)
  local okB, vb = pcall(function() return second:getVelocity() end)
  if not okA or not okB or not finiteVector3(va) or not finiteVector3(vb) then
    return 0
  end
  local axis = second:getPosition() - first:getPosition()
  local distance = axis:length()
  local relative = vec3(va.x - vb.x, va.y - vb.y, va.z - vb.z)
  if distance < 0.001 then return relative:length() end
  return relative:dot(axis * (1.0 / distance))
end

local function supportRadius(state, vehicle, axis)
  -- How far this car's body reaches along `axis` from its own centre. For a
  -- box that is exactly |hx*(axis.right)| + |hy*(axis.forward)| +
  -- |hz*(axis.up)|, so a nose-to-tail approach gets the LENGTH and a
  -- side-swipe gets the WIDTH.
  --
  -- Proven necessary live (2026-08-25): the first cut used the MEAN of the
  -- two horizontal half-extents, one number for every direction. For an
  -- etk800 that is 1.68 m, so two of them bumper to bumper - centres 4.6 m
  -- apart - sat outside a 3.9 m "contact" range and a rear-end tap could
  -- never transfer the potato at all, while a side-swipe would have fired
  -- early. A ram in the live gate closed to 4.48 m and nothing happened.
  local entry = subjectExtents(state, vehicle)
  local forward = vec3(0, 1, 0)
  local up = vec3(0, 0, 1)
  local okF, liveF = pcall(function() return vehicle:getDirectionVector() end)
  if okF and finiteVector3(liveF) and liveF:length() > 0.1 then
    forward = vec3(liveF.x, liveF.y, liveF.z)
    forward:normalize()
  end
  local okU, liveU = pcall(function() return vehicle:getDirectionVectorUp() end)
  if okU and finiteVector3(liveU) and liveU:length() > 0.1 then
    up = vec3(liveU.x, liveU.y, liveU.z)
    up:normalize()
  end
  local right = forward:cross(up)
  if right:length() < 0.1 then right = vec3(1, 0, 0) end
  right:normalize()
  return math.abs(entry.hx * axis:dot(right))
    + math.abs(entry.hy * axis:dot(forward))
    + math.abs(entry.height * axis:dot(up))
end

local function contactRange(state, first, second)
  local axis = second:getPosition() - first:getPosition()
  local distance = axis:length()
  if distance < 0.001 then
    axis = vec3(0, 1, 0)
  else
    axis = axis * (1.0 / distance)
  end
  return supportRadius(state, first, axis)
    + supportRadius(state, second, axis)
    + OPT.touch_margin
end

local function sweepForPass(state, carrier)
  local b = state.behavior
  local carrierPosition = carrier:getPosition()
  if not finiteVector3(carrierPosition) then return end
  local touchMode = OPT.transfer_mode ~= "radius"

  -- The separation latch. After a pass A -> B the potato may not go back to
  -- A until the two have actually parted by tagback_separation_m beyond
  -- contact, which is what stops a locked-bumper pair trading it forever
  -- once the immunity window lapses.
  if b.pairFrom and not b.pairSeparated then
    local from = exactVehicle(b.pairFrom)
    local to = exactVehicle(b.pairTo)
    if not from or not to then
      b.pairSeparated = true
    else
      local gap = (to:getPosition() - from:getPosition()):length()
      if gap > contactRange(state, from, to) + OPT.tagback_separation_m then
        b.pairSeparated = true
      end
    end
  end

  local best, bestDistance
  for _, entry in ipairs(roster(state)) do
    local id = entry.id
    local eligible = id ~= b.carrier
      and (b.immune[id] or 0) <= b.now
      and (b.seen[id] or 0) + OPT.join_immunity_seconds <= b.now
    -- Both halves of "back and forth is allowed once it has been held long
    -- enough and they have separated".
    if eligible and id == b.pairFrom then
      eligible = b.pairSeparated
        and (b.now - (b.heldSince or b.now)) >= OPT.tagback_min_hold_seconds
    end
    if eligible then
      local position = entry.vehicle:getPosition()
      if finiteVector3(position) then
        local distance = (position - carrierPosition):length()
        local threshold = touchMode
          and contactRange(state, carrier, entry.vehicle)
          or OPT.radius_m
        if distance <= threshold then
          -- Touch mode also demands a real hit: without a minimum closing
          -- speed two stationary cars can brush fenders forever.
          local fast = true
          if touchMode and OPT.impact_kmh > 0 then
            fast = closingSpeed(carrier, entry.vehicle) >= OPT.impact_kmh / 3.6
          end
          if fast and (not bestDistance or distance < bestDistance) then
            best, bestDistance = entry.vehicle, distance
          end
        end
      end
    end
  end
  -- At most one pass per tick, always to the closest eligible car.
  if best then
    giveTo(state, best, touchMode and "impact" or "radius")
    announce(state, "PASSED!", 1.4)
  end
end

local function sweepForPickup(state)
  -- THE v1 BUG FIX. A Contains trigger over the pad never delivered a single
  -- enter event in a real session; a position test cannot miss.
  local b = state.behavior
  local pad = toWorldPoint(state, B.pad_center)
  local field = roster(state)
  if #field < OPT.min_players then return false end
  for _, entry in ipairs(field) do
    local position = entry.vehicle:getPosition()
    -- The same join-immunity window the transfer respects. Without it a
    -- carrier who RESETS while standing on the medallion is re-armed on the
    -- very next tick (the reset clears b.seen, roster re-seens the car, and
    -- the pad sweep fires) - the "potato returned" beat never gets to exist.
    -- It also keeps a car spawned directly onto the pad from being armed
    -- before its driver has ever held the wheel.
    if finiteVector3(position)
      and (b.seen[entry.id] or 0) + OPT.join_immunity_seconds <= b.now then
      -- Project into the AUTHORED frame before testing, like every other
      -- placement in this runtime. World-axis tests turn the circular pad
      -- into a tilted ellipse with asymmetric height clipping the moment the
      -- prop settles on a slope (review finding, PR #87): at a steep
      -- attitude a car sitting on the authored pad can read metres of
      -- world-Z below the pad centre and be rejected.
      local ex, ey, ez = authoredAxes(state)
      local offset = position - pad
      local lx, ly, lz = offset:dot(ex), offset:dot(ey), offset:dot(ez)
      local horizontal = math.sqrt(lx * lx + ly * ly)
      if horizontal <= OPT.pickup_radius
        and lz >= -2.0 and lz <= OPT.pickup_height then
        b.fieldPeak = #field
        giveTo(state, entry.vehicle, "pad")
        announce(state, "YOU'VE GOT IT - pass it on!", 3.0, "round_started",
          {subject_id = entry.id})
        return true
      end
    end
  end
  return false
end

local function applyCarrierBoost(state, carrier, dtSim)
  -- Dodging beats intercepting, so the holder gets a slipstream. This is a
  -- UNIFORM cluster velocity add: it can move the car but by construction
  -- cannot strain a beam, so carrying the potato stays harmless.
  if OPT.carrier_boost_mps2 <= 0 then return end
  local ok, velocity = pcall(function() return carrier:getVelocity() end)
  if not ok or not finiteVector3(velocity) then return end
  local speed = velocity:length()
  if speed < 2.0 or speed > OPT.carrier_boost_max_mps then return end
  local direction = vec3(velocity.x, velocity.y, velocity.z)
  direction:normalize()
  addSubjectVelocity(state, carrier, direction * (OPT.carrier_boost_mps2 * (dtSim or 0)))
end

local function updateFuseCues(state, worldPos)
  -- No numeric countdown anywhere, by design: the player reads urgency from
  -- an accelerating, rising tick and a beacon that pulses in step with it.
  local b = state.behavior
  local remaining = (b.fuseEnds or b.now) - b.now
  local urgency = 1.0 - clampNumber(remaining / OPT.cue_window_seconds, 0.0, 1.0)
  local interval = OPT.beep_slow_interval
    + (OPT.beep_fast_interval - OPT.beep_slow_interval) * urgency
  b.beaconAngle = (b.beaconAngle or 0)
    + (interval > 0 and (OPT.beacon_spin_rate * (1.0 + urgency * 2.0) * 0.016) or 0)
  if (b.nextBeep or 0) <= b.now then
    b.nextBeep = b.now + math.max(0.03, interval)
    b.pulseUntil = b.now + OPT.beacon_pulse_seconds
    playSound(SFX_TICK, 1.0 + urgency * OPT.beep_pitch_rise, 0.55 + urgency * 0.45)
  end
  -- The beacon strobes ON with each tick rather than burning steady, so the
  -- visual cue and the audio cue are the same accelerating pulse.
  beaconLit(state, (b.pulseUntil or 0) > b.now)
  poseBeacon(state, worldPos)
end

-- The round itself. Split out of behavior.update so every early return still
-- ends with one publishStats, rather than each exit path having to remember.
local function stepRound(state, dtSim)
  local b = state.behavior

  if b.phase == "idle" then
    parkPotato(state)
    sweepForPickup(state)
    return
  end

  if b.phase == "boom" then
    local since = b.now - (b.boomAt or b.now)
    local victim = exactVehicle(b.carrier)
    -- The launch lands a tick behind the press so the panels are already
    -- shedding when the wreck leaves the ground.
    if not b.boomLaunched and since >= 0.12 then
      b.boomLaunched = true
      if victim then
        launchSubject(state, victim, vec3(0, 0, OPT.detonate_launch_mps))
      end
    end
    if since >= OPT.fire_seconds then setEffectActive(state, "blast", false) end
    if since >= OPT.fire_seconds + OPT.round_idle_seconds then
      local remaining = roster(state)
      if #remaining >= 2 then
        local home = toWorldPoint(state, B.potato_home)
        local next_carrier = nearestPlayable(state, home)
        if next_carrier then
          b.fuseEnds = nil
          giveTo(state, next_carrier, "respawn")
          announce(state, "STILL IN PLAY!", 2.5)
          return
        end
      end
      -- A winner only exists if there was ever a field to win against.
      if #remaining == 1 and (b.fieldPeak or 0) >= 2 then
        setEffectActive(state, "cheer", true)
        playSound(SFX_WIN, 1.0, 1.0)
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
    b.out[b.carrier] = true
    b.phase = "idle"
    b.fuseEnds = nil
    parkPotato(state)
    announce(state, "Carrier quarantined.", 2.5, "carrier_quarantined",
      {subject_id = b.carrier})
    return
  end

  -- Re-arm the watch every tick: the framework's rebuildTriggers clears
  -- state.zones whenever ANY subject resets, and a one-shot registration in
  -- giveTo would be lost with it.
  state.zones.carrier_watch = {[b.carrier] = true}

  local anchor, rotation = carrierPose(state, carrier)
  posePotato(state, anchor, rotation)
  poseEffectAt(state, "fuse", anchor)
  updateFuseCues(state, anchor)
  applyCarrierBoost(state, carrier, dtSim)
  sweepForPass(state, carrier)

  local field = #roster(state)
  if field > (b.fieldPeak or 0) then b.fieldPeak = field end
  -- Everyone else despawned mid-round: the carrier is the last car standing
  -- and must WIN, not sit alone waiting for the fuse (review finding, PR
  -- #87). Same win predicate as the post-boom path: there was a field to
  -- beat, and it is gone.
  if field == 1 and (b.fieldPeak or 0) >= 2 then
    local winner = b.carrier
    b.phase = "idle"
    b.fuseEnds = nil
    parkPotato(state)
    setEffectActive(state, "cheer", true)
    playSound(SFX_WIN, 1.0, 1.0)
    announce(state, "LAST CAR STANDING!", 4.0, "round_won",
      {subject_id = winner})
    return
  end
  if ((b.fuseEnds or b.now) - b.now) <= 0 then
    detonate(state, carrier)
  end
end

behavior.init = function(state)
  local b = state.behavior
  loadOptions()
  b.phase = "idle"
  b.now = 0
  b.wallLast = nil
  b.spin = 0
  b.beaconAngle = 0
  b.beaconLit = nil
  b.carrier = nil
  b.fuseEnds = nil
  b.nextBeep = 0
  b.pulseUntil = 0
  b.fieldPeak = 0
  b.transfers = 0
  b.immune = {}
  b.seen = {}
  b.out = {}
  b.outCount = 0
  b.extents = {}
  b.pairFrom, b.pairTo, b.pairSeparated = nil, nil, true
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
  -- Secondary pickup path. The sweep is authoritative and will usually have
  -- fired first; this is here so a trigger event is never simply ignored.
  local b = state.behavior
  if not b.ready or zone ~= "pad" or b.phase ~= "idle" then return end
  local field = roster(state)
  if #field < OPT.min_players then return end
  b.fieldPeak = #field
  giveTo(state, vehicle, "pad_trigger")
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
  -- Never silently pick a new victim, and never leave it orbiting a dead id.
  b.phase = "idle"
  b.fuseEnds = nil
  parkPotato(state)
  announce(state, "Potato returned to the arch.", 2.5, "carrier_lost",
    {subject_id = vehicleId, reason = reason})
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  if not b.ready then return end
  advanceClock(b, dtSim)
  b.spin = (b.spin + (dtSim or 0) * OPT.spin_rate) % (math.pi * 2)
  stepRound(state, dtSim)
  publishStats(state)
end

-- Mod controls. Exported as GE hooks, so the UI app, the console and any
-- future scenario all drive the same one surface:
--   extensions.ericrolph_hot_potato_runtime.hotPotatoSetOption("radius_m", 20)
behavior.hooks = {
  hotPotatoGetOptions = function()
    if next(OPT) == nil then loadOptions() end
    local payload = {}
    for key in pairs(OPTION_RANGE) do payload[key] = OPT[key] end
    return payload
  end,
  hotPotatoSetOption = function(key, value)
    if next(OPT) == nil then loadOptions() end
    local coerced, reason = coerceOption(key, value)
    if coerced == nil then
      -- LOG_TAG and UI_CATEGORY are the template's own locals. Angle-style
      -- placeholders CANNOT be used in here: lua_kit substitutes them before
      -- it splices the behaviour chunk in, so one written here survives into
      -- the generated file and trips its unreplaced-token guard. (Which it
      -- duly did to the first draft of this very comment.)
      log("W", LOG_TAG, "rejected option " .. tostring(key)
        .. ": " .. tostring(reason))
      return false
    end
    OPT[key] = coerced
    saveOptions()
    showMessage("Hot Potato: " .. key .. " = " .. tostring(coerced), 3)
    return true
  end,
  hotPotatoResetOptions = function()
    seedOptions()
    saveOptions()
    return true
  end,
}
"""
