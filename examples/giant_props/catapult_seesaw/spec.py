"""Charlie's Catapult Seesaw — authored constants for Blender + runtime.

Shipped name (2026-08-14): the beamng.com listing is "Charlie's Catapult
Seesaw", matching the Charlie's-<thing> shelf the LAHC Centrifuge started,
so DISPLAY_NAME matches it and players find in the vehicle selector the
thing they downloaded. Internal names (MOD_ID, ZIP_BASENAME, the
catapult_seesaw directory) are unchanged: renaming those would orphan
every installed copy.

A playground seesaw scaled 10x. Drive up the low end and hold still: after
three parked seconds (with a countdown), a physical latch releases a
10-short-ton cast-iron weight. BeamNG gravity drops its 9,070 kg node cage
six metres onto a separately grouped box-truss plank. The raised, asymmetric
lever gives the parked vehicle a 1.8:1 speed advantage and starts the car on
a roughly 60-degree physical launch normal before finishing against hydraulic
catchers. The
car is moved only by tire/suspension contact with that hinged plank; runtime
code never sets, adds, or replaces subject velocity. Once the launch area is
clear, resetting the prop re-latches the physical mechanism for another run.
"""

import math

MOD_ID = "ericrolph_catapult_seesaw"
DISPLAY_NAME = "Charlie's Catapult Seesaw"
VALUE_DOLLARS = 30000
ZIP_BASENAME = "catapult_seesaw_ericrolph.zip"

# Authored frame: right-handed, meters, Z-up. The car end and physical
# downrange direction are -Y; the weight end is +Y.
# The board remains 22 m long, but the fulcrum is no longer at its geometric
# midpoint.  The longer car arm and shorter weight arm are the mechanical
# advantage; no subject-side impulse compensates for a weak lever.
PLANK_CAR_ARM = 13.5
PLANK_WEIGHT_ARM = 8.5
PLANK_CAR_END_Y = -PLANK_CAR_ARM
PLANK_WEIGHT_END_Y = PLANK_WEIGHT_ARM
PLANK_LENGTH = PLANK_CAR_ARM + PLANK_WEIGHT_ARM
PLANK_CENTER_Y = (PLANK_CAR_END_Y + PLANK_WEIGHT_END_Y) / 2.0
# 2.2 (was 1.8): a 3.6 m plank at 10x scale was unforgiving to board and
# large SUVs wandered off the collision edge (report 2026-07-23).
PLANK_HALF_WIDTH = 2.2
PLANK_THICKNESS = 0.35
# PIVOT HEIGHT, REST ANGLE AND THE RAMP ARE ONE SYSTEM (play-test
# 2026-08-25: "the ramp angle is severe").  v3 raised the pivot to 7.0 m to
# get its drop height, and then had to rake the plank to 30 degrees just to
# bring the car end back down to a boardable height.  Shallow rest + high
# pivot is the worst of both: at 8 degrees and 7.0 m the car tip sat 7.77 m
# up, the auto-derived ramp became a 50.2 degree wall, and there was still a
# 2.48 m step from ramp top to plank tip.
#
# The pre-v3 build that people liked pivoted at 1.775 m.  2.6 m keeps some
# of v3's drop while putting the car tip at 0.72 m - a 9.3 degree ramp, which
# is the gentle approach this thing had before.  The counterweight tower is
# unaffected (GANTRY_TOP_Z is absolute), so the block actually falls FURTHER.
PIVOT_Z = 2.6
# THE PARKED POSE IS NOT THE LAUNCH POSE (play-test 2026-08-25: "the angle
# is insanely steep").  v3 bought launch elevation by tilting the PARKED
# plank to 30 degrees - a 58% grade the car can barely hold station on, and
# which reads as a ski jump rather than a seesaw.  Departure elevation comes
# from the plank's angle at the moment the car LEAVES, not from where it
# sits, so the sweep can stay large while the parked pose returns to
# something drivable: park shallow, stop steeply nose-up.
#
#   v3:   +30.0 rest -> -32.0 stop   =  62 deg sweep, undrivable parked pose
#   now:  + 8.0 rest -> -45.0 stop   =  53 deg sweep, STEEPER departure
#
# 8 degrees also matches the entry ramp's own grade, so the car drives on
# without a step at the joint.
REST_ANGLE_DEG = 8.0  # car end down, drivable; departure comes from the sweep
# Bounded by ground clearance, not taste: the weight arm swings BELOW the
# pivot, so |stop| <= asin((PIVOT_Z - clearance) / PLANK_WEIGHT_ARM).
# At pivot 2.6 and an 8.5 m weight arm that is about 16 degrees.  Departure
# elevation is 90 - |stop|, so this still leaves a steep 74 degree throw;
# what it costs is sweep, and therefore tip speed.  Digging an Acme pit under
# the weight end is what buys the sweep back - see the note above.
FLING_STOP_ANGLE_DEG = -16.0
# Positions on the moving plank are local to its unrotated centerline.  Static
# scenery and trigger coordinates are authored in world space.  Keeping those
# frames explicit prevents the 30-degree rest transform from moving the impact
# mat over a metre away from the falling weight.
PLANK_IMPACT_STATION_Y = 6.0
PLANK_PARK_STATION_Y = -10.8
IMPACT_TRANSFER_STROKE = 0.25
# The impact rods terminate directly on the five heavy structural nodes in
# the deck's lower impact rib.  A 25 cm visible rubber mat occupies the same
# stroke above the wood, so force begins at visible contact rather than in air.
IMPACT_RECEIVER_NORMAL_OFFSET = -PLANK_THICKNESS / 2
_REST_ANGLE_RAD = math.radians(REST_ANGLE_DEG)


def _plank_surface_world(local_y: float, angle_rad: float) -> tuple[float, float]:
    normal_offset = PLANK_THICKNESS / 2
    return (
        local_y * math.cos(angle_rad) - normal_offset * math.sin(angle_rad),
        PIVOT_Z + local_y * math.sin(angle_rad) + normal_offset * math.cos(angle_rad),
    )


GANTRY_Y, SURFACE_REST_AT_WEIGHT = _plank_surface_world(PLANK_IMPACT_STATION_Y, _REST_ANGLE_RAD)
IMPACT_RECEIVER_WORLD_Y = PLANK_IMPACT_STATION_Y * math.cos(
    _REST_ANGLE_RAD
) - IMPACT_RECEIVER_NORMAL_OFFSET * math.sin(_REST_ANGLE_RAD)
IMPACT_RECEIVER_WORLD_Z = (
    PIVOT_Z
    + PLANK_IMPACT_STATION_Y * math.sin(_REST_ANGLE_RAD)
    + IMPACT_RECEIVER_NORMAL_OFFSET * math.cos(_REST_ANGLE_RAD)
)
IMPACT_CONTACT_LENGTH = math.hypot(
    GANTRY_Y - IMPACT_RECEIVER_WORLD_Y,
    SURFACE_REST_AT_WEIGHT - IMPACT_RECEIVER_WORLD_Z,
)
# CageBuilder exports authored +Y as JBeam -Y.  This is the lower impact rib's
# raw rest phase about the central hinge in vehicle coordinates.
IMPACT_RECEIVER_RAW_REST_PHASE_DEG = math.degrees(
    math.atan2(IMPACT_RECEIVER_WORLD_Z - PIVOT_Z, -IMPACT_RECEIVER_WORLD_Y)
)
PARK_STATION_Y, _PARK_SURFACE_Z = _plank_surface_world(PLANK_PARK_STATION_Y, _REST_ANGLE_RAD)
GANTRY_TOP_Z = 21.2
# 4.4 m run to the low plank tip: about a 9 degree entry ramp.
RAMP_GROUND_Y = -17.9

COUNTERWEIGHT_MASS_KG = 9070.0  # 10 US short tons / 20,000 lb
WEIGHT_BOTTOM_OFFSET = 1.46  # casting body plus foundry plinth
WEIGHT_STRIKER_DEPTH = 0.75  # central tup below the broad casting plinth
DESIGN_FREE_FALL_DISTANCE = 6.0

# Physical drop geometry. These figures document the available energy and
# provide telemetry thresholds only; BeamNG's softbody solver owns the fall,
# impact, plank rotation, and vehicle trajectory.
EARTH_GRAVITY = 9.81


WEIGHT_REST_CENTER_Z = (
    SURFACE_REST_AT_WEIGHT + WEIGHT_BOTTOM_OFFSET + WEIGHT_STRIKER_DEPTH + DESIGN_FREE_FALL_DISTANCE
)
WEIGHT_BODY_BOTTOM_REST_Z = WEIGHT_REST_CENTER_Z - WEIGHT_BOTTOM_OFFSET
WEIGHT_BOTTOM_REST_Z = WEIGHT_BODY_BOTTOM_REST_Z - WEIGHT_STRIKER_DEPTH
FREE_FALL_DISTANCE = WEIGHT_BOTTOM_REST_Z - SURFACE_REST_AT_WEIGHT
FREE_FALL_SECONDS = math.sqrt(2.0 * FREE_FALL_DISTANCE / EARTH_GRAVITY)
IMPACT_SPEED = EARTH_GRAVITY * FREE_FALL_SECONDS

# 2026-08-13 Acme redesign: cartoon contraption language, built honestly.
# Natural varnished plank boards (two seeds so adjacent boards never match),
# Acme-red painted derrick steel, near-black cast-iron drop weight, ivory
# painted lettering/markings, engraved patent plate. Old family choices
# (wood_painted blue, plain concrete cube weight) retired the same day the
# listing copy was certified - listing_copy.md updated to match.
PALETTE = {
    f"{MOD_ID}_plank_wood": {
        "texture": {
            "family": "wood_plank",
            "params": {
                "early": [0.50, 0.32, 0.165],
                "late": [0.155, 0.082, 0.042],
                "rings": 17.0,
                "figure": 1.15,
                "sheen": 0.5,
            },
        },
        "color": [0.48, 0.33, 0.18, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
    # Second seed (seed = material name) so alternating boards read as
    # different sawn planks, not clones.
    f"{MOD_ID}_plank_wood_b": {
        "texture": {
            "family": "wood_plank",
            "params": {
                "early": [0.545, 0.355, 0.19],
                "late": [0.175, 0.095, 0.05],
                "rings": 21.0,
                "figure": 0.95,
                "sheen": 0.42,
            },
        },
        "color": [0.52, 0.36, 0.2, 1.0],
        "metallic": 0.0,
        "roughness": 0.52,
    },
    # Crosscut butt ends of the boards (play-test 2026-08-13 round 4:
    # the end faces showed face grain running sideways; a cut end shows
    # growth-ring arcs). Butt-face aspect = board width / thickness.
    f"{MOD_ID}_plank_end": {
        "texture": {
            "family": "end_grain",
            "params": {
                "early": [0.50, 0.32, 0.165],
                "late": [0.155, 0.082, 0.042],
                "aspect": 3.03,
            },
        },
        "color": [0.42, 0.28, 0.155, 1.0],
        "metallic": 0.0,
        "roughness": 0.65,
    },
    f"{MOD_ID}_acme_red": {
        "texture": {
            "family": "painted_metal",
            "params": {"base": [0.565, 0.085, 0.06], "rough": 0.36, "peel": 0.8},
        },
        "color": [0.58, 0.1, 0.08, 1.0],
        "metallic": 0.12,
        "roughness": 0.38,
    },
    # Hardware steel: machined_steel, not steel_worn (play-test 2026-08-13
    # round 4: mill-plate banding read as garish bright streaks on the
    # pillow-block washer face - machined parts want tight low-contrast
    # grain and oily roughness variation instead).
    f"{MOD_ID}_steel": {
        "texture": {"family": "machined_steel"},
        "color": [0.45, 0.47, 0.5, 1.0],
        "metallic": 0.85,
        "roughness": 0.4,
    },
    # Dedicated sand-cast iron family (play-test 2026-08-13: the borrowed
    # concrete map read as smeared mush on the frustum). The frustum also
    # carries metric box UVs now - both halves of that fix matter.
    f"{MOD_ID}_cast_iron": {
        "texture": {"family": "cast_iron", "size": 1024},
        "color": [0.14, 0.135, 0.14, 1.0],
        "metallic": 0.62,
        "roughness": 0.52,
    },
    f"{MOD_ID}_impact_rubber": {
        "color": [0.035, 0.04, 0.045, 1.0],
        "metallic": 0.0,
        "roughness": 0.82,
    },
    # Painted markings and cast raised letters: flat ivory, no texture.
    f"{MOD_ID}_paint_white": {
        "color": [0.93, 0.9, 0.83, 1.0],
        "metallic": 0.0,
        "roughness": 0.42,
    },
    f"{MOD_ID}_concrete": {
        "texture": {"family": "concrete", "params": {"fine": 0.7}},
        "color": [0.62, 0.6, 0.57, 1.0],
        "metallic": 0.0,
        "roughness": 0.8,
    },
    f"{MOD_ID}_hazard_yellow": {
        "texture": {"family": "hazard_chevron"},
        "color": [0.95, 0.75, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
    f"{MOD_ID}_target_red": {
        "color": [0.82, 0.12, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
    # Deck paint DECALS (play-test 2026-08-13 round 4: "look like it's
    # painted onto the wood"). Alpha-cutout skins millimetres over the
    # boards - only the paint renders, it breaks at every board seam,
    # and it casts no shadow (paint never does).
    f"{MOD_ID}_deck_target": {
        "texture": {
            "family": "target_decal",
            "size": 1024,
            "params": {
                "seams": [-1.113333, 0.0, 1.113333],
                "seam_width": 0.06,
            },
        },
        "color": [0.82, 0.12, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
        "material": {"castShadows": False},
    },
    f"{MOD_ID}_deck_stripes": {
        "texture": {
            "family": "stripe_decal",
            "size": 1024,
            "params": {
                "width_m": 4.4,
                "height_m": 0.875,
                "period_m": 0.62,
                "seams": [-1.113333, 0.0, 1.113333],
                "seam_width": 0.06,
            },
        },
        "color": [0.95, 0.75, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.55,
        "material": {"castShadows": False},
    },
    # Engraved builder's plate, laid out mid-century-modern (play-test
    # 2026-08-13: the fixed-v title crowded the frame). Centered axis,
    # letterspaced brand line with real margins, a rule under it, even
    # vertical rhythm below.
    f"{MOD_ID}_plate_legend": {
        "texture": {
            "family": "panel_legend",
            "params": {
                "title": "",
                "aspect": 1.714,
                "label_scale": 0.105,
                "labels": [
                    [0.5, 0.745, "A C M E", 1.75],
                    [0.5, 0.49, "PATENT CATAPULT", 0.95],
                    [0.5, 0.345, "MODEL No. 7", 0.9],
                    [0.5, 0.165, "MAX LOAD 20,000 LBS", 0.78],
                ],
                "rules": [[0.615, 0.27, 0.016]],
            },
        },
        "color": [0.055, 0.06, 0.068, 1.0],
        "metallic": 0.6,
        "roughness": 0.38,
    },
    f"{MOD_ID}_ramp_asphalt": {
        "texture": {"family": "asphalt"},
        "color": [0.16, 0.16, 0.17, 1.0],
        "metallic": 0.0,
        "roughness": 0.9,
    },
    # One-shot deck surface: chevrons + hazard edge bands baked INTO the
    # asphalt map (marking geometry always shows shadow/edge in-engine -
    # play-test 2026-08-13, "painted on ... no shadow or edge").
    f"{MOD_ID}_ramp_deck": {
        # aspect = deck width / slope length for the 4.4 m run; the
        # longer deck carries three chevrons instead of two.
        "texture": {
            "family": "ramp_deck",
            "params": {"aspect": 1.0772, "chevrons": [0.2, 0.45, 0.7]},
        },
        "color": [0.16, 0.16, 0.17, 1.0],
        "metallic": 0.0,
        "roughness": 0.9,
    },
}

TRIGGERS = {
    "park_zone": {
        # OVERLAPS, never Contains (play-test 2026-08-13 round 9: "larger
        # vehicles don't trigger the catapult"). Contains demands the
        # vehicle's WHOLE oriented bounding box sit inside the zone, so
        # the zone silently becomes a vehicle-size limit - a tanker truck
        # is ~9 m long and could never fit a 6.6 m box however perfectly
        # it parked. (Same trap cost us the countdown in 2026-07-23, when
        # a Roamer's OOBB dipped below the zone floor.) Overlaps just asks
        # "is any of it in here", which is size-blind; being ON the X is
        # then enforced properly in the runtime by measuring the
        # vehicle's own position against park_radius, which no bounding
        # box can distort.
        # ...and the box must FOLLOW THE DECK IN Z.  This centre was a
        # hardcoded 2.6, which happened to bracket the car while the plank
        # parked at 30 degrees and put the deck near the ground.  The
        # moment the rest angle went shallow the deck rose to 5.67 m, the
        # box still spanned 0.2..5.0, and the car sat entirely ABOVE the
        # trigger - so parking on the X armed nothing (play-test
        # 2026-08-25: "vehicle on the X of the planks don't trigger the
        # weight to fall").  _PARK_SURFACE_Z was already computed right
        # here and simply never used.  Derive it, and the zone tracks the
        # deck at any rest angle.
        "mode": "Overlaps",
        "center": [0.0, PARK_STATION_Y, _PARK_SURFACE_Z + 1.6],
        "dimensions": [5.4, 7.4, 4.8],
    },
}

EFFECTS = {
    "impact_dust": {
        "emitter": "BNGP_2",
        "position": [0.0, GANTRY_Y, SURFACE_REST_AT_WEIGHT],
        "direction": [0.0, 0.0, 1.0],
    },
}

PLANK_CAR_NODE_NAMES = [f"{MOD_ID}_plank_{index}_0_top" for index in range(5)]
PLANK_WEIGHT_NODE_NAMES = [f"{MOD_ID}_plank_{index}_9_top" for index in range(5)]
WEIGHT_NODE_NAMES = [
    f"{MOD_ID}_weight_{ix}_{iy}_{iz}" for iz in range(3) for ix in range(5) for iy in range(5)
]
IMPACT_STRIKER_NODE_NAMES = [f"{MOD_ID}_weight_striker_{index}" for index in range(5)]
IMPACT_RECEIVER_NODE_NAMES = [f"{MOD_ID}_plank_{index}_6_bottom" for index in range(5)]
# Impact-rib phase is measured around the physical centre hinge. There is no
# auxiliary receiver linkage or second fixed pivot in the force path.
IMPACT_PIVOT_NODE_NAMES = [f"{MOD_ID}_plank_hinge_2" for _ in range(5)]

BEHAVIOR = {
    "camera_distance": 48.0,
    "rest_angle_deg": REST_ANGLE_DEG,
    "park_speed_max": 0.6,
    "park_seconds": 3.0,
    "park_station_y": PARK_STATION_Y,
    "park_radius": 3.0,
    "plank_car_nodes": PLANK_CAR_NODE_NAMES,
    "plank_weight_nodes": PLANK_WEIGHT_NODE_NAMES,
    "weight_nodes": WEIGHT_NODE_NAMES,
    "impact_striker_nodes": IMPACT_STRIKER_NODE_NAMES,
    "impact_receiver_nodes": IMPACT_RECEIVER_NODE_NAMES,
    "impact_pivot_nodes": IMPACT_PIVOT_NODE_NAMES,
    "impact_activation_length": IMPACT_CONTACT_LENGTH + IMPACT_TRANSFER_STROKE,
    "impact_receiver_rest_phase_deg": IMPACT_RECEIVER_RAW_REST_PHASE_DEG,
    "weight_center_rest_z": WEIGHT_REST_CENTER_Z,
    "release_break_group": "catapult_weight_release",
    "spool_radius": 0.32,
    "cable_rest_len": 0.25,
    # Observation thresholds only: none of these values actuates a vehicle.
    "impact_drop_m": FREE_FALL_DISTANCE,
    "minimum_swing_deg": 4.0,
    "fling_rise_m": 0.65,
    "fling_up_mps": 2.0,
    # Let the full ballistic flight and physical counterweight settling finish
    # before an empty park zone resets the mechanism.
    "reset_earliest_seconds": 15.0,
    "reset_reminder_seconds": 12.0,
    "reset_retry_seconds": 5.0,
}

# Omit the shared subject velocity/teleport primitives from this runtime.
ALLOW_SUBJECT_MUTATION = False

LUA_BEHAVIOR = r"""
local function wrapDegrees(value)
  return ((value + 180) % 360) - 180
end

local function averageNodes(state, prop, names)
  local total = vec3(0, 0, 0)
  local count = 0
  for _, name in ipairs(names or {}) do
    local cid = resolveNodeCid(state, name)
    local okNode, offset = pcall(function()
      return cid and prop:getNodePosition(cid) or nil
    end)
    if okNode and offset then
      total = total + offset
      count = count + 1
    end
  end
  if count == 0 then return nil end
  return total / count
end

local function nodePosition(state, prop, name)
  local cid = resolveNodeCid(state, name)
  local okNode, offset = pcall(function()
    return cid and prop:getNodePosition(cid) or nil
  end)
  if okNode then return offset end
  return nil
end

local function sampleImpactMechanism(state, prop)
  local minimumLength = math.huge
  local maximumLength = 0
  local phaseY = 0
  local phaseZ = 0
  local count = 0
  for index, strikerName in ipairs(B.impact_striker_nodes or {}) do
    local striker = nodePosition(state, prop, strikerName)
    local receiver = nodePosition(
      state, prop, B.impact_receiver_nodes[index])
    local pivot = nodePosition(state, prop, B.impact_pivot_nodes[index])
    if striker and receiver and pivot then
      local length = (striker - receiver):length()
      minimumLength = math.min(minimumLength, length)
      maximumLength = math.max(maximumLength, length)
      phaseY = phaseY + receiver.y - pivot.y
      phaseZ = phaseZ + receiver.z - pivot.z
      count = count + 1
    end
  end
  if count == 0 then return nil end
  return {
    minimum_length_m = minimumLength,
    maximum_length_m = maximumLength,
    maximum_compression_m = math.max(
      0, B.impact_activation_length - minimumLength),
    receiver_phase_deg = math.deg(math.atan2(phaseZ, phaseY)),
  }
end

local function sampleMechanism(state)
  local prop = exactVehicle(state.propId)
  if not prop then return nil, nil, nil end
  local carEnd = averageNodes(state, prop, B.plank_car_nodes)
  local weightEnd = averageNodes(state, prop, B.plank_weight_nodes)
  local weightCenter = averageNodes(state, prop, B.weight_nodes)
  local angle = nil
  if carEnd and weightEnd then
    angle = math.deg(math.atan2(
      weightEnd.z - carEnd.z, carEnd.y - weightEnd.y))
  end
  local drop = weightCenter
    and math.max(0, B.weight_center_rest_z - weightCenter.z) or nil
  local impact = sampleImpactMechanism(state, prop)
  if impact then
    local bodyDelta = wrapDegrees(
      B.impact_receiver_rest_phase_deg - impact.receiver_phase_deg)
    impact.body_angle_deg = B.rest_angle_deg + bodyDelta
    impact.phase_error_deg = angle
      and wrapDegrees(impact.body_angle_deg - angle) or nil
  end
  return angle, drop, impact
end

local function poseCosmetics(state, drop)
  if drop == nil then
    local _, measuredDrop = sampleMechanism(state)
    drop = measuredDrop
  end
  if drop == nil then return end
  setPartPose(
    state, "cable", nil, nil,
    vec3(1, 1, 1 + drop / B.cable_rest_len))
  setPartPose(
    state, "winch", nil,
    axisAngle(vec3(1, 0, 0), drop / B.spool_radius))
end

local function queuePhysicalRelease(state)
  local prop = exactVehicle(state.propId)
  if not prop then return false, "prop_unavailable" end
  local command = string.format(
    "if beamstate then "
      .. "if beamstate.breakBreakGroup then "
      .. "beamstate.breakBreakGroup(%q) end end",
    B.release_break_group)
  local queued, queueError = pcall(function()
    prop:queueLuaCommand(command)
  end)
  if not queued then return false, tostring(queueError) end
  return true
end

local function resetReleasedImpactExtrema(b)
  b.minimumReleasedImpactRodLength = nil
  b.maximumReleasedImpactCompression = 0
end

behavior.init = function(state)
  local b = state.behavior
  b.phase = "idle"
  b.elapsed = 0
  b.clock = 0
  b.parkTimer = 0
  b.lastCount = nil
  b.tracked = nil
  b.subjectId = nil
  b.launchOrigin = nil
  b.forwardDir = nil
  b.upDir = nil
  b.impacted = false
  b.flung = false
  b.reminded = false
  b.maxRise = 0
  b.maxForward = 0
  b.maxSubjectSpeed = 0
  b.maxSubjectUpSpeed = 0
  b.maxSubjectForwardSpeed = 0
  b.maxWeightDownSpeed = 0
  b.lastWeightDrop = nil
  resetReleasedImpactExtrema(b)
  poseCosmetics(state, 0)
end

behavior.reset = function(state)
  local previous = state.behavior.phase
  behavior.init(state)
  setEffectActive(state, "impact_dust", false)
  if previous and previous ~= "idle" then
    showMessage("Catapult physically re-latched.", 1.8)
    emitEvent(state, "I", "seesaw_rearmed", {})
  end
end

behavior.onEnter = function(state, zone, vehicle)
  if zone ~= "park_zone" then return end
  if state.behavior.phase == "idle" then
    showMessage("Park on the X and hold still...", 2.2)
    emitEvent(state, "I", "seesaw_boarded", {subject_id = vehicle:getId()})
  else
    showMessage("Catapult is spent; drive clear to re-latch.", 2.0)
  end
end

behavior.onExit = function(state, zone, vehicleId)
  local b = state.behavior
  if zone == "park_zone" and b.phase == "idle" then
    b.parkTimer = 0
    b.lastCount = nil
    b.tracked = nil
  end
end

behavior.onSubjectGone = function(state, vehicleId, reason)
  local b = state.behavior
  if b.tracked and b.tracked.id == vehicleId then
    b.tracked = nil
    b.parkTimer = 0
  end
  if b.subjectId == vehicleId then b.subjectId = nil end
end

local function beginRelease(state, vehicle)
  local b = state.behavior
  local released, releaseError = queuePhysicalRelease(state)
  if not released then
    b.parkTimer = 0
    b.lastCount = nil
    emitError(state, "physical_release_failed", {detail = releaseError})
    showMessage("Latch failed. Reset the prop and try again.", 2.4)
    return
  end
  local position = vehicle:getPosition()
  b.phase = "released"
  b.elapsed = 0
  b.subjectId = vehicle:getId()
  b.launchOrigin = vec3(position.x, position.y, position.z)
  b.forwardDir = toWorldDir(state, vec3(0, -1, 0))
  b.upDir = toWorldDir(state, vec3(0, 0, 1))
  b.impacted = false
  b.flung = false
  b.reminded = false
  b.maxRise = 0
  b.maxForward = 0
  b.maxSubjectSpeed = 0
  b.maxSubjectUpSpeed = 0
  b.maxSubjectForwardSpeed = 0
  b.maxWeightDownSpeed = 0
  b.lastWeightDrop = 0
  resetReleasedImpactExtrema(b)
  showMessage("PHYSICAL LATCH RELEASED!", 1.5)
  emitEvent(state, "I", "weight_released", {
    subject_id = b.subjectId,
    release = "break_group_latch",
  })
end

local function updateParking(state, dtSim)
  local b = state.behavior
  local vehicle = firstOccupant(state, "park_zone")
  if not vehicle then
    b.parkTimer = 0
    b.lastCount = nil
    b.tracked = nil
    return
  end
  local position = vehicle:getPosition()
  local id = vehicle:getId()
  if state.origin then
    local station = state.origin
      + state.modelRotation * vec3(0, B.park_station_y, 0)
    local dx = position.x - station.x
    local dy = position.y - station.y
    if dx * dx + dy * dy > B.park_radius * B.park_radius then
      b.parkTimer = 0
      b.lastCount = nil
      b.tracked = nil
      return
    end
  end
  if b.tracked and b.tracked.id == id and dtSim > 0 then
    local speed = (position - b.tracked.position):length() / dtSim
    if speed <= B.park_speed_max then
      b.parkTimer = b.parkTimer + dtSim
    else
      b.parkTimer = 0
      b.lastCount = nil
    end
  end
  b.tracked = {id = id, position = vec3(position.x, position.y, position.z)}
  local count = math.max(0, math.ceil(B.park_seconds - b.parkTimer))
  if b.parkTimer > 0.15 and count ~= b.lastCount and count > 0 then
    b.lastCount = count
    showMessage(string.format("Hold still... %d", count), 0.9)
  end
  if b.parkTimer >= B.park_seconds then beginRelease(state, vehicle) end
end

local function requestPhysicalReset(state)
  local b = state.behavior
  local prop = exactVehicle(state.propId)
  if not prop then return false end
  local resetOk, resetError = pcall(function()
    prop:requestReset(RESET_PHYSICS)
  end)
  if not resetOk then
    emitError(state, "physical_reset_failed", {detail = tostring(resetError)})
    return false
  end
  b.phase = "resetting"
  b.elapsed = 0
  resetReleasedImpactExtrema(b)
  emitEvent(state, "I", "seesaw_reset_requested", {})
  return true
end

local function updateReleased(state, dtSim)
  local b = state.behavior
  local angle, drop, impact = sampleMechanism(state)
  poseCosmetics(state, drop)

  if impact then
    b.minimumReleasedImpactRodLength = math.min(
      b.minimumReleasedImpactRodLength or math.huge,
      impact.minimum_length_m)
    b.maximumReleasedImpactCompression = math.max(
      b.maximumReleasedImpactCompression or 0,
      impact.maximum_compression_m)
  end

  if drop and b.lastWeightDrop and dtSim > 0 then
    b.maxWeightDownSpeed = math.max(
      b.maxWeightDownSpeed,
      (drop - b.lastWeightDrop) / dtSim)
  end
  if drop then b.lastWeightDrop = drop end

  if not b.impacted and drop and drop >= B.impact_drop_m then
    b.impacted = true
    setEffectActive(state, "impact_dust", true)
    emitEvent(state, "I", "counterweight_impact", {
      drop_m = drop, plank_angle_deg = angle,
    })
  end

  local vehicle = b.subjectId and exactVehicle(b.subjectId) or nil
  if vehicle and b.launchOrigin then
    local displacement = vehicle:getPosition() - b.launchOrigin
    local rise = displacement:dot(b.upDir)
    local forward = displacement:dot(b.forwardDir)
    local velocity = vehicle:getVelocity()
    local upSpeed = velocity:dot(b.upDir)
    local forwardSpeed = velocity:dot(b.forwardDir)
    local speed = velocity:length()
    b.maxRise = math.max(b.maxRise, rise)
    b.maxForward = math.max(b.maxForward, forward)
    b.maxSubjectSpeed = math.max(b.maxSubjectSpeed, speed)
    b.maxSubjectUpSpeed = math.max(b.maxSubjectUpSpeed, upSpeed)
    b.maxSubjectForwardSpeed = math.max(
      b.maxSubjectForwardSpeed, forwardSpeed)
    local swung = angle
      and angle <= (B.rest_angle_deg - B.minimum_swing_deg)
    if not b.flung and b.impacted and swung
        and (rise >= B.fling_rise_m or upSpeed >= B.fling_up_mps) then
      b.flung = true
      showMessage("WHEEEEE - ALL PHYSICS!", 1.8)
      emitEvent(state, "I", "seesaw_flung", {
        subject_id = vehicle:getId(),
        rise_m = rise,
        forward_m = forward,
        up_mps = upSpeed,
        forward_mps = forwardSpeed,
        speed_mps = speed,
        elevation_deg = math.deg(math.atan2(upSpeed, forwardSpeed)),
        plank_angle_deg = angle,
        weight_drop_m = drop,
      })
    end
  end

  if b.elapsed >= 2.5 then setEffectActive(state, "impact_dust", false) end
  if b.elapsed >= B.reset_earliest_seconds
      and zoneCount(state, "park_zone") == 0 then
    requestPhysicalReset(state)
  elseif b.elapsed >= B.reset_reminder_seconds and not b.reminded then
    b.reminded = true
    showMessage("Drive clear of the plank to re-latch.", 2.6)
  end
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  b.clock = b.clock + dtSim
  b.elapsed = b.elapsed + dtSim
  if b.phase == "idle" then
    poseCosmetics(state, nil)
    updateParking(state, dtSim)
  elseif b.phase == "released" then
    updateReleased(state, dtSim)
  elseif b.phase == "resetting" and b.elapsed >= B.reset_retry_seconds then
    b.phase = "released"
    b.elapsed = B.reset_earliest_seconds
  end
end

behavior.getStatus = function(state)
  local angle, drop, impact = sampleMechanism(state)
  local b = state.behavior
  return {
    park_timer_s = b.parkTimer or 0,
    plank_angle_deg = angle,
    weight_drop_m = drop,
    impacted = b.impacted and true or false,
    flung = b.flung and true or false,
    max_rise_m = b.maxRise or 0,
    max_forward_m = b.maxForward or 0,
    max_subject_speed_mps = b.maxSubjectSpeed or 0,
    max_subject_up_mps = b.maxSubjectUpSpeed or 0,
    max_subject_forward_mps = b.maxSubjectForwardSpeed or 0,
    max_weight_down_mps = b.maxWeightDownSpeed or 0,
    impact_min_rod_length_m = impact and impact.minimum_length_m or nil,
    impact_max_rod_length_m = impact and impact.maximum_length_m or nil,
    impact_max_compression_m = impact and impact.maximum_compression_m or nil,
    impact_released_min_rod_length_m = b.minimumReleasedImpactRodLength,
    impact_released_max_compression_m = (
      b.maximumReleasedImpactCompression or 0),
    impact_receiver_phase_deg = impact and impact.receiver_phase_deg or nil,
    impact_body_angle_deg = impact and impact.body_angle_deg or nil,
    impact_receiver_phase_error_deg = impact and impact.phase_error_deg or nil,
  }
end
"""
