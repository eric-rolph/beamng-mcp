"""Charlie's Boot of Doom — authored constants for Blender + runtime.

Shipped name (2026-08-14): the beamng.com listing is "Charlie's Boot of
Doom", matching the published "Charlie's LAHC Centrifuge" and the CHARLIE
CO. builder's plate on the console back — the props read as one maker.

A giant brown leather work boot on a ground hinge behind a painted kick
pad. CROSS the pad and the boot triggers: a fast quiver-and-draw-back,
then it swings up through the strike lane and punts everything still in it
— park on the X or get caught mid-escape. Punt power is randomized between
"over sixty yards" and "call the news station" (roughly 60-120 yards).

Art pass 2026-08-13: the generated hero mesh was shard soup (3542 loose
fragments, spiky sole/collar silhouette) with 512px baked maps. Rebuilt via
voxel remesh -> smooth -> decimate (93.8k tris, one watertight shell) with
fresh smart-project UVs, then the old maps transfer-baked at 2048 and
detailed: procedural leather grain in color/normal, leather-vs-rubber
roughness split (sole masked by darkness), AO ground into the color. Goal
posts deleted; the kick pad tapers to grade on all four sides.

Play-test changes 2026-07-22: the pad moved clear of the resting toe, the
arming trigger became a drive-through Overlaps (Contains required parking
and aborted on any crossing), and the strike is a wide zone swept at punt
time like the flyswatter. 2026-07-23: the primitive-built sneaker was
replaced with a generated hero mesh (assets/boot_hero.glb — worn leather,
lugged sole, baked base/normal/roughness maps via the "external" texture
family) after the player called the primitive look terrible twice.
"""

MOD_ID = "ericrolph_boot_of_doom"
DISPLAY_NAME = "Charlie's Boot of Doom"
VALUE_DOLLARS = 22000
ZIP_BASENAME = "boot_of_doom_ericrolph.zip"

# Authored frame: right-handed, meters, Z-up, +Y drive direction. The boot
# heel hinge is at -Y; the punt flings cars downrange toward +Y.
HINGE_PIVOT = (0.0, -8.3, 0.9)
PAD_CENTER_Y = 1.2  # moved downrange so the resting toe no longer covers it

# Kick pad footprint: plateau is the flat painted surface, the skirt tapers
# to the ground on all four sides so the plate reads as a poured hump
# rather than a squared-off slab (player request 2026-08-13).
PAD_PLATEAU_HALF = (2.1, 2.3)
PAD_SKIRT_WIDTH = 0.5
PAD_HEIGHT = 0.12

# --- Mid-century control console (authored frame) -----------------------
# A floor console BEHIND the boot (player request 2026-08-13), clear of
# the hinge base block (rear edge y -9.4) and the windup shuffle (the
# heel draws back to y -9.45): cream enamel cabinet on splayed steel legs
# with walnut cheeks, a graphite legend plate with cool-white
# letterspaced type, bakelite caps, a ten-segment power ladder and a
# quarter-sweep protractor dial. Face is the -Y side, away from the boot,
# so reading the panel means looking over the cabinet at the kick.
CONSOLE_CX = 0.0
CONSOLE_CY = -11.4
CONSOLE_FACE_Y = -11.675        # cabinet front plane (fascia; never moves)

# Carcass joinery (2026-08-13 rebuild — player: "the sides don't seem well
# put together"). The old cabinet gave every corner THREE unrelated
# relationships at once: the end panels straddled the case wall (27.5 mm
# buried, 27.5 mm proud), stood 10 mm proud at front AND back, but ran
# 30 mm short at top AND bottom — under a top rail 17.5 mm NARROWER than
# the panels it capped, with legs stabbed 20 mm up into the underside.
# Nothing registered against anything, which is exactly what reads as
# pasted-together.
#
# It is now built like real cabinetry, and every reveal below is a named
# constant so the joints stay related:
#   * a cream enamel CASE captured between two solid walnut END PANELS
#     that BUTT the case sides (no burial), run the FULL case height, and
#     sit FLUSH with the case back;
#   * the frame (panels + cap + kick strip) stands FRAME_PROUD ahead of
#     the fascia, so the panel sits in a shallow well;
#   * the top cap overhangs by the SAME CAP_LIP on all four sides, so no
#     corner can mismatch;
#   * an inset steel understructure carries the legs on visible bolt
#     plates, and the four splayed feet land exactly under the four
#     corners of the cap.
CASE_W = 1.69                   # cream case width, end-panel to end-panel
CASE_D = 0.55                   # depth; front face IS CONSOLE_FACE_Y
CASE_Z0 = 0.62                  # case bottom (sits on the understructure)
CASE_Z1 = 1.70                  # case top (the cap wraps over this)
CHEEK_T = 0.075                 # solid walnut end panel thickness
FRAME_PROUD = 0.035             # frame stands this far ahead of the fascia
CAP_T = 0.045                   # top cap thickness
CAP_LIP = 0.016                 # cap overhang — identical on all four sides
BASE_INSET = 0.065              # understructure inset from the silhouette
BASE_RAIL_H = 0.055             # understructure rail height
BASE_RAIL_T = 0.045             # understructure rail thickness
BOLT_PLATE = 0.10               # leg mounting plate, square
FOOT_Z = 0.03                   # foot pad height
# One eased arris for the whole carcass. proplib's default bevel is 2
# segments, and on a 90 deg corner those two 30 deg steps both fall UNDER
# the 38 deg auto-smooth angle, so they shade together into a soft rounded
# blob — every edge of the cabinet looked melted rather than machined
# (player report 2026-08-13, "the edges line up in a funky way"). A SINGLE
# 45 deg segment is above the smoothing angle, so it stays a crisp flat
# chamfer, which is what a finished edge actually looks like.
EDGE_EASE = 0.004
PLATE_Y = -11.681               # legend plate centre (0.012 skin)
PLATE_W = 1.5                   # across the face (authored x)
PLATE_H = 0.86
PLATE_Z0 = 0.74                 # plate bottom edge
POWER_ROW_Z = 1.307
POWER_SEG_PITCH = 0.075
POWER_SEG_DX0 = -0.3375         # segment 1 (viewer LEFT = authored -x)
DIAL_CZ = 0.88                  # dial hub centre
DIAL_TICK_R = 0.2625            # tick centreline radius
NEEDLE_LEN = 0.20
BUTTON_ANCHOR_Y = -11.777       # click anchors 9 cm proud of the plate

# --- Back-panel paperwork ----------------------------------------------
# One small screwed-down nameplate, tucked into the bottom corner nearest
# the viewer's left (+x is the viewer's LEFT from behind). Aspect is held
# at the verified 1.538 so the whole type layout below scales with it.
# Corner screws are what make a metal plate read as ATTACHED rather than
# printed on, so the plate carries four.
BACK_PLATE_W = 0.27
BACK_PLATE_H = 0.1755
BACK_PLATE_MARGIN_X = 0.095     # from the case side edge
BACK_PLATE_MARGIN_Z = 0.085     # from the case bottom edge
BACK_PLATE_SCREW_INSET = 0.013  # screw centres in from the plate corners
BACK_PLATE_SCREW_R = 0.005

PANEL_BUTTONS = (
    {"id": "btn_power_down", "title": "Kick Power: Decrease",
     "dx": -0.55, "z": POWER_ROW_Z},
    {"id": "btn_power_up", "title": "Kick Power: Increase",
     "dx": 0.55, "z": POWER_ROW_Z},
    {"id": "btn_angle_down", "title": "Launch Angle: Lower",
     "dx": -0.62, "z": 0.94},
    {"id": "btn_angle_up", "title": "Launch Angle: Raise",
     "dx": 0.62, "z": 0.94},
)


def _u(dx):
    """Plate u from an authored x-offset; for a -y-facing plate the world
    mirror puts authored -x on the viewer's LEFT, so u runs WITH
    authored x (the -x-facing plate ran opposite its across-axis)."""

    return round(0.5 + dx / PLATE_W, 4)


def _v(z):
    return round((z - PLATE_Z0) / PLATE_H, 4)


PANEL_LEGEND_LABELS = [
    [0.5, _v(1.44), "POWER", 0.8],
    [_u(-0.55), _v(1.20), "-", 0.9],
    [_u(0.55), _v(1.20), "+", 0.9],
    [_u(POWER_SEG_DX0), _v(1.24), "1X", 0.6],
    [_u(-POWER_SEG_DX0), _v(1.24), "4X", 0.6],
    [0.5, 0.07, "LAUNCH ANGLE", 0.8],
    [_u(-0.62), _v(0.845), "-", 0.9],
    [_u(0.62), _v(0.845), "+", 0.9],
    [_u(-0.36), _v(DIAL_CZ), "0", 0.6],
    [0.5, _v(DIAL_CZ + 0.31), "90", 0.6],
]

PALETTE = {
    # Baked maps extracted from the generated hero mesh, checked in under
    # assets/ so texture staging is a byte-stable copy.
    f"{MOD_ID}_boot_hero": {
        "texture": {
            "family": "external",
            "maps": {
                "baseColorMap": "assets/boot_hero.color.png",
                "normalMap": "assets/boot_hero.normal.png",
                "roughnessMap": "assets/boot_hero_roughness.data.png",
            },
        },
        "color": [0.45, 0.26, 0.15, 1.0],
        "metallic": 0.0,
        "roughness": 0.6,
    },
    # 1024 px + a slightly warmer, less blue base: at 512 the grain
    # blurred into soft banding on the 3 m hinge block (player report
    # 2026-08-13, "make the steel much more realistic"). The real fix is
    # metric UVs on the hinge geometry; the resolution keeps the grain
    # crisp at bumper distance.
    f"{MOD_ID}_steel": {
        "texture": {
            "family": "steel_worn",
            "size": 1024,
            "params": {"base": [0.53, 0.54, 0.56], "rough": 0.44},
        },
        "color": [0.53, 0.54, 0.56, 1.0],
        "metallic": 0.8,
        "roughness": 0.4,
    },
    # One-shot pad skin: the white border frame and red X are PAINT in the
    # map (kick_pad family), not geometry — marking plates cast shadows
    # and catch edge light (player report 2026-08-13; same law as the
    # catapult ramp_deck). Meter params mirror the old plate layout.
    f"{MOD_ID}_pad_deck": {
        "texture": {
            "family": "kick_pad",
            "size": 1024,
            "params": {
                "half_u": PAD_PLATEAU_HALF[0] + PAD_SKIRT_WIDTH,
                "half_v": PAD_PLATEAU_HALF[1] + PAD_SKIRT_WIDTH,
                "frame_outer": [2.1, 2.3],
                "frame_width": 0.2,
                "stroke_length": 3.4,
                "stroke_width": 0.55,
                "paint": [0.88, 0.88, 0.86],
                "target": [0.82, 0.12, 0.08],
            },
        },
        "color": [0.16, 0.16, 0.17, 1.0],
        "metallic": 0.0,
        "roughness": 0.9,
    },
    # --- Control console (mid-century) --------------------------------
    # 1024 + a tile pitch wider than the panel it lands on: at 512/0.9 m the
    # peel-wear marks repeated twice across the fascia.
    f"{MOD_ID}_console_cream": {
        "texture": {
            "family": "painted_metal",
            "size": 1024,
            "params": {"base": [0.91, 0.88, 0.80], "rough": 0.34, "peel": 0.25},
        },
        "color": [0.91, 0.88, 0.80, 1.0],
        "metallic": 0.1,
        "roughness": 0.34,
    },
    # Solid walnut, so the grain must read as ONE board: at 512/0.5 m the
    # end panel showed a hard mirrored seam straight down its middle and
    # looked like two badly butted veneer offcuts — which is exactly the
    # "not well put together" the carcass rebuild is fixing. 1024 px, and
    # the generator gives every walnut piece a tile pitch LARGER than the
    # face it lands on so no repeat is ever visible.
    # The `wood` family defaults to a FRENCH-POLISHED board (it was authored
    # for a sign face): sheen 1.0 puts the roughness map at 0.34-0.16*sheen
    # = 0.18, which is lacquer. On the cap that read as poured resin under a
    # low sun — the top looked wet. A cabinet is satin-oiled, so sheen goes
    # to 0. The stock latewood is also near-black against pale earlywood,
    # which reads as zebrano tiger-stripe rather than walnut; lifting it to
    # a dark brown and easing the ring count calms the figure down.
    f"{MOD_ID}_console_walnut": {
        "texture": {
            "family": "wood",
            "size": 1024,
            "params": {
                "early": [0.40, 0.245, 0.145],
                "late": [0.165, 0.092, 0.052],
                "rings": 17.0,
                "sheen": 0.0,
                # Pore ticks are sized in TEXELS, so at this cabinet's
                # 1.4-2.0 m tile pitch a "pore" comes out ~1 cm across —
                # ten times life size, and the normal map rendered them as
                # bright specular dashes speckling the cap like water drops.
                "pore": 0.2,
            },
        },
        "color": [0.33, 0.20, 0.11, 1.0],
        "metallic": 0.0,
        "roughness": 0.45,
    },
    f"{MOD_ID}_panel_legend": {
        "texture": {
            "family": "panel_legend",
            "size": 1024,
            "params": {
                "title": "KICK CONTROL",
                "labels": PANEL_LEGEND_LABELS,
                "aspect": PLATE_W / PLATE_H,
            },
        },
        "color": [0.055, 0.06, 0.068, 1.0],
        "metallic": 0.3,
        "roughness": 0.5,
    },
    # Anodized builder's plate. Ratings are derived from what the machine
    # actually does (see the power note above BEHAVIOR): the LINE rating,
    # not the stroke peak, because the peak comes out of the flywheel.
    # Period notation throughout — "60 CY" not "60 Hz", horsepower not
    # watts, and 2300 V 3-phase, which was THE standard supply for large
    # US industrial motors of this vintage.
    f"{MOD_ID}_plate_data": {
        "texture": {
            "family": "panel_legend",
            "size": 512,
            "params": {
                "title": "",
                "aspect": BACK_PLATE_W / BACK_PLATE_H,
                "labels": [
                    [0.5, 0.855, "C H A R L I E   C O .", 1.25],
                    [0.5, 0.665, "KINETIC FOOTWEAR DIV.", 0.8],
                    [0.5, 0.530, "MODEL BD-1   SER. 0022", 0.75],
                    [0.5, 0.395, "2300 V  3 PH  60 CY", 0.75],
                    [0.5, 0.260, "470 A   2200 H.P.", 0.75],
                    [0.5, 0.110, "PAT. PEND.   MADE IN U.S.A.", 0.58],
                ],
                "rules": [[0.775, 0.30, 0.014]],
            },
        },
        "color": [0.055, 0.06, 0.068, 1.0],
        "metallic": 0.6,
        "roughness": 0.38,
    },
    f"{MOD_ID}_btn_bakelite": {
        "texture": {"family": "bakelite"},
        "color": [0.08, 0.07, 0.07, 1.0],
        "metallic": 0.15,
        "roughness": 0.4,
    },
    f"{MOD_ID}_seg_amber": {
        "color": [0.98, 0.62, 0.10, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
    },
    f"{MOD_ID}_seg_red": {
        "color": [0.85, 0.14, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
    },
    f"{MOD_ID}_needle_red": {
        "color": [0.86, 0.10, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.3,
    },
}

TRIGGERS = {
    # Drive-through arming: any overlap with the pad wakes the boot.
    "kick_pad": {
        "mode": "Overlaps",
        "center": [0.0, PAD_CENTER_Y, 1.8],
        "dimensions": [4.6, 5.2, 4.0],
    },
    # The punt sweeps this whole lane: the pad plus the escape route
    # downrange, so crossing cars get caught mid-flight attempt.
    "strike_zone": {
        "mode": "Overlaps",
        "center": [0.0, 3.2, 2.1],
        "dimensions": [5.4, 9.4, 4.4],
    },
}

EFFECTS = {
    "punt_dust": {
        "emitter": "BNGP_2",
        "position": [0.0, PAD_CENTER_Y, 0.6],
        "direction": [0.0, 0.0, 1.0],
    },
}

# Power budget behind the nameplate ratings, derived from the timings and
# angles in this dict rather than invented:
#   boot        7.9 m about a heel hinge, ~8.6 t (lugged rubber sole
#               ~5.6 t + leather upper ~1.5 t + internal spine ~1.5 t),
#               so as a rod about one end I = mL^2/3 ~ 1.8e5 kg m^2
#   stroke      8 -> 62 deg in punt_seconds; the pose eases quadratically,
#               so omega peaks at 2*dtheta/T = 7.85 rad/s — a 62 m/s toe
#               (223 km/h) and ~35 m/s at the contact point, which is the
#               right order to fling a car off at punt_speed_max 42 m/s
#   energy      boot 5.54 MJ + car 1.32 MJ = 6.86 MJ per kick
#   PEAK        6.86 MJ / 0.24 s = 28.6 MW — which is exactly why a
#               machine like this stores and dumps rather than drawing
#               live, so the peak is NOT what goes on the plate
#   LINE        6.86 MJ over the 4.89 s cycle = 1.40 MW mechanical,
#               ~1.65 MW electrical at 85% drive efficiency
#               = 2200 H.P., and at 2300 V 3-phase pf 0.88 that is 470 A
BEHAVIOR = {
    "camera_distance": 34.0,
    "alert_seconds": 0.3,
    "windup_seconds": 0.7,
    "hold_seconds": 0.15,
    # Kick mechanics rebuilt from the player's recording (2026-08-13,
    # "the boot disappears into the floor, the kick is all wrong"): the
    # swing now takes 0.24 s (0.12 s was 7 frames — unreadable), the boot
    # LUNGES forward off its windup so the toe actually passes through
    # the car's position, and the launch fires at the moment of visual
    # contact (~15 deg into the swing, toe at rear-panel height) instead
    # of mid-swing over an empty pad.
    "punt_seconds": 0.24,
    "punt_launch_fraction": 0.32,
    "punt_lunge": 1.3,
    "follow_seconds": 0.9,
    "return_seconds": 1.6,
    "cooldown_seconds": 1.0,
    "windup_shuffle": 0.8,
    "windup_angle_deg": 8.0,
    "punt_angle_deg": 62.0,
    # Randomized per punt: ~60 yards on a weak kick, double on a screamer
    # — then multiplied by the console's power setting.
    "punt_speed_min_mps": 27.0,
    "punt_speed_max_mps": 42.0,
    "punt_lateral_per_meter": 0.05,
    # Control console: kick power 1x..4x in ten steps, launch angle 0..90
    # degrees in ten 10-degree positions (index * step; index 9 = straight
    # up). Defaults: stock power, 50 degrees (the old 0.62/0.78 punt
    # direction was 51.5 degrees).
    "power_levels": 10,
    "power_multiplier_max": 4.0,
    "angle_step_deg": 10.0,
    "default_power_level": 1,
    "default_angle_index": 5,
}

LUA_BEHAVIOR = r"""
-- Boot pose. AXIS SIGN (2026-08-13, player recording): authored
-- axisAngle(vec3(1,0,0)) pitches the toe DOWN in world -- the July
-- rotation-order fix (local rotation as LEFT operand) flipped the
-- effective sign of x-axis part rotations, and the punt was authored
-- before it: the video shows the boot buried to the collar at full
-- swing. vec3(-1,0,0) makes positive angles lift the toe.
-- slide: authored draw-back meters (negative = forward lunge).
local function bootPose(state, slide, angleDeg)
  setPartPose(
    state,
    "boot",
    vec3(0, -(slide or 0), 0),
    axisAngle(vec3(-1, 0, 0), math.rad(angleDeg or 0))
  )
end

local function powerMult(state)
  local level = state.behavior.powerLevel or B.default_power_level
  return 1.0 + (level - 1) * (B.power_multiplier_max - 1.0) / (B.power_levels - 1)
end

local function angleDegrees(state)
  return (state.behavior.angleIndex or B.default_angle_index) * B.angle_step_deg
end

-- Console instruments (console faces -y behind the boot): ladder segment
-- i is proud of the plate while the power level reaches it, otherwise
-- +0.12 authored y -- straight back through the plate into the cabinet
-- (the centrifuge bar-graph idiom). The needle points authored -x
-- (0 deg, viewer's left) and sweeps to +z (90 deg, straight up).
local function poseConsole(state)
  local b = state.behavior
  local lit = b.powerLevel or B.default_power_level
  for i = 1, B.power_levels do
    setPartPose(
      state, string.format("pow_seg%d", i),
      vec3(0, i <= lit and 0 or 0.12, 0),
      axisAngle(vec3(0, 0, 1), 0))
  end
  -- Same empirical axis-sign law as bootPose: horizontal-axis part
  -- rotations run reversed in world. Sweeping -x up to +z is authored
  -- +y, so pass -y.
  setPartPose(
    state, "angle_needle", nil,
    axisAngle(vec3(0, -1, 0), math.rad(angleDegrees(state))))
end

behavior.init = function(state)
  local b = state.behavior
  b.phase = "idle"
  b.elapsed = 0
  b.clock = 0
  b.powerLevel = b.powerLevel or B.default_power_level
  b.angleIndex = b.angleIndex or B.default_angle_index
  bootPose(state, 0, 0)
  poseConsole(state)
end

behavior.reset = function(state)
  behavior.init(state)
  setEffectActive(state, "punt_dust", false)
end

behavior.onPanelButton = function(state, buttonId)
  local b = state.behavior
  if buttonId == "btn_power_up" then
    b.powerLevel = math.min(B.power_levels, (b.powerLevel or B.default_power_level) + 1)
  elseif buttonId == "btn_power_down" then
    b.powerLevel = math.max(1, (b.powerLevel or B.default_power_level) - 1)
  elseif buttonId == "btn_angle_up" then
    b.angleIndex = math.min(B.power_levels - 1, (b.angleIndex or B.default_angle_index) + 1)
  elseif buttonId == "btn_angle_down" then
    b.angleIndex = math.max(0, (b.angleIndex or B.default_angle_index) - 1)
  else
    return
  end
  poseConsole(state)
  local mult = powerMult(state)
  local degrees = angleDegrees(state)
  showMessage(string.format("Kick power %.1fx - launch angle %d deg", mult, degrees), 1.6)
  emitEvent(state, "I", "boot_console_set", {
    power_level = b.powerLevel,
    power_mult = math.floor(mult * 100) / 100,
    angle_deg = degrees,
  })
end

behavior.onEnter = function(state, zone, vehicle)
  local b = state.behavior
  if zone == "kick_pad" and b.phase == "idle" then
    b.phase = "alert"
    b.elapsed = 0
    showMessage("The boot notices you.", 1.2)
    emitEvent(state, "I", "boot_alerted", {subject_id = vehicle:getId()})
  end
end

local function puntStrikeZone(state)
  local b = state.behavior
  local center = toWorldPoint(state, vec3(0, 3.2, 1.0))
  local lateralAxis = toWorldDir(state, vec3(1, 0, 0))
  local mult = powerMult(state)
  local angle = math.rad(angleDegrees(state))
  local kicked = 0
  for vehicleId in pairs(zoneOccupants(state, "strike_zone")) do
    local vehicle = exactVehicle(vehicleId)
    if vehicle then
      local speed = (B.punt_speed_min_mps
        + math.random() * (B.punt_speed_max_mps - B.punt_speed_min_mps)) * mult
      local offset = vehicle:getPosition() - center
      -- Lateral spread fades with loft so a straight-up setting goes
      -- straight up instead of drifting off the pad.
      local lateral = math.max(-0.25, math.min(0.25,
        offset:dot(lateralAxis) * B.punt_lateral_per_meter)) * math.cos(angle)
      local direction = toWorldDir(state, vec3(
        lateral, math.cos(angle), math.sin(angle)))
      if launchSubject(state, vehicle, direction * speed) then
        kicked = kicked + 1
        emitEvent(state, "I", "boot_punted", {
          subject_id = vehicleId,
          punt_speed_mps = speed,
          power_mult = math.floor(mult * 100) / 100,
          angle_deg = angleDegrees(state),
        })
      end
    end
  end
  if kicked > 0 then
    setEffectActive(state, "punt_dust", true)
    if mult >= 3.0 then
      showMessage("PUNT! CALL THE NEWS STATION!", 1.8)
    else
      showMessage("PUNT! IT'S GOOD!", 1.8)
    end
  else
    showMessage("The boot kicks nothing but air.", 1.6)
    emitEvent(state, "I", "boot_whiffed", {})
  end
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  b.clock = b.clock + dtSim
  b.elapsed = b.elapsed + dtSim
  if b.phase == "idle" then
    bootPose(state, 0, 0)
  elseif b.phase == "alert" then
    -- abs() keeps the quiver strictly above the resting plane.
    bootPose(state, 0, math.abs(math.sin(b.clock * 30)) * 0.5)
    if b.elapsed >= B.alert_seconds then
      b.phase = "windup"
      b.elapsed = 0
      showMessage("The boot draws back...", 1.0)
    end
  elseif b.phase == "windup" then
    local t = math.min(1, b.elapsed / B.windup_seconds)
    local smooth = t * t * (3 - 2 * t)
    bootPose(
      state,
      B.windup_shuffle * smooth,
      B.windup_angle_deg * smooth + math.abs(math.sin(b.clock * 26)) * 0.5
    )
    if t >= 1 then
      b.phase = "holdback"
      b.elapsed = 0
    end
  elseif b.phase == "holdback" then
    bootPose(state, B.windup_shuffle, B.windup_angle_deg)
    if b.elapsed >= B.hold_seconds then
      b.phase = "punting"
      b.elapsed = 0
      b.punted = false
      emitEvent(state, "I", "boot_swinging", {})
    end
  elseif b.phase == "punting" then
    -- The kick (rebuilt from the player recording 2026-08-13): the boot
    -- lunges forward off its windup while the toe sweeps up, so the sole
    -- visibly passes through the car; the launch fires at the contact
    -- moment (~15 deg, toe at rear-panel height), not over an empty pad.
    local t = math.min(1, b.elapsed / B.punt_seconds)
    bootPose(
      state,
      B.windup_shuffle - (B.windup_shuffle + B.punt_lunge) * t,
      B.windup_angle_deg + (B.punt_angle_deg - B.windup_angle_deg) * t * t
    )
    if not b.punted and t >= B.punt_launch_fraction then
      b.punted = true
      puntStrikeZone(state)
    end
    if t >= 1 then
      b.phase = "follow"
      b.elapsed = 0
    end
  elseif b.phase == "follow" then
    -- Hold the follow-through: boot high, full lunge.
    bootPose(state, -B.punt_lunge, B.punt_angle_deg)
    if b.elapsed >= B.follow_seconds then
      b.phase = "returning"
      b.elapsed = 0
      setEffectActive(state, "punt_dust", false)
    end
  elseif b.phase == "returning" then
    local t = math.min(1, b.elapsed / B.return_seconds)
    local smooth = t * t * (3 - 2 * t)
    bootPose(state, -B.punt_lunge * (1 - smooth), B.punt_angle_deg * (1 - smooth))
    if t >= 1 then
      b.phase = "cooldown"
      b.elapsed = 0
    end
  elseif b.phase == "cooldown" then
    bootPose(state, 0, 0)
    if b.elapsed >= B.cooldown_seconds then
      b.phase = "idle"
      b.elapsed = 0
      if zoneCount(state, "kick_pad") > 0 then
        b.phase = "alert"
        showMessage("The boot notices you. Again.", 1.2)
      end
    end
  end
end
"""
