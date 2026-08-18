"""Regulation Football Goal Post — authored constants for Blender + runtime.

A pro-style single-pedestal ("gooseneck") football goal post at true
regulation dimensions: crossbar top 10 ft (3.048 m) above grade, 18 ft 6 in
(5.6388 m) inside width between the uprights, uprights extending 35 ft
(10.668 m) above the crossbar, and the pedestal offset 8 ft (2.4384 m)
behind the goal plane through a swan-neck bend. Tube stock matches real
fabrication: 6-5/8" OD pedestal, 5" OD crossbar, 4" OD uprights, all in
safety-yellow paint over steel, with a quilted vinyl safety pad wrapping
the pedestal and red directional flags on the upright tips.

The flags are real soft-body cloth on BeamNG's physics ground wind — the
engine broadcasts wind to every spawned vehicle and derives drag and lift
per triangle, so they stream, fold and snap on their own rather than
being an animation that ignores the actual air.

Purely structural prop (all-fixed cage) with one piece of theater: a
detector zone between the uprights above the crossbar calls the kick —
loft a car through and it's GOOD.

Authored frame: right-handed, meters, Z-up, +Y drive direction — cars
approach from -Y, the goal plane is at y = 0, and the pedestal stands
behind it at +Y like a real end-line post.
"""

MOD_ID = "ericrolph_football_goal_post"
DISPLAY_NAME = "Charlie's Football Field Goal"
VALUE_DOLLARS = 14000
ZIP_BASENAME = "football_goal_post_ericrolph.zip"

# --- Regulation dimensions (meters) -------------------------------------
CROSSBAR_TOP_Z = 3.048        # 10 ft to the TOP of the crossbar
BAR_RADIUS = 0.0635           # 5" OD crossbar tube
BAR_CENTER_Z = CROSSBAR_TOP_Z - BAR_RADIUS
INSIDE_WIDTH = 5.6388         # 18 ft 6 in between upright inner faces
UPRIGHT_RADIUS = 0.0508       # 4" OD upright tube
UPRIGHT_X = INSIDE_WIDTH / 2.0 + UPRIGHT_RADIUS
UPRIGHT_TOP_Z = CROSSBAR_TOP_Z + 10.668  # 35 ft above the crossbar

POST_RADIUS = 0.0841          # 6-5/8" OD pedestal pipe
POST_Y = 2.4384               # 8 ft gooseneck offset behind the goal plane
# The gooseneck is ONE continuous sweep (ID-00001 elevation), so the
# pedestal has to hand off low enough for the curve to have room: 8 ft of
# offset inside 10 ft of height only reads as graceful if the curve owns
# most of the rise. The pole pad shortens to suit.
POST_TOP_Z = 1.55             # vertical pedestal ends, swan neck begins

PAD_RADIUS = 0.27             # vinyl pedestal pad, outer (bulge) radius
# 6 ft of padding is the NFHS/NCAA requirement and this is where the
# authored collision prism ends, so the visual shell has to reach it — the
# top 0.38 m of the wrap therefore covers the start of the sweep and leans
# out with the pipe, which is what a real gooseneck pad does.
PAD_TOP_Z = 1.93

PALETTE = {
    # Safety-yellow paint over steel tube: subtle orange-peel and blotch,
    # semi-gloss like fresh stadium paint.
    f"{MOD_ID}_goal_yellow": {
        "texture": {
            "family": "painted_metal",
            "params": {"base": [0.94, 0.70, 0.05], "rough": 0.3, "peel": 0.35},
        },
        "color": [0.94, 0.70, 0.05, 1.0],
        "metallic": 0.25,
        "roughness": 0.3,
    },
    # Painted fastener finish. A goal post is assembled and THEN sprayed, so
    # every bolt on the yellow structure wears the same coat as the tube it
    # is in — bare silver heads all over a painted post is the tell of parts
    # dropped into a scene rather than a thing that was built (player,
    # 2026-08-15). It is not the same material as the pipe, though: paint
    # laid over a hex head goes on thicker and less evenly than over a
    # rolled tube, so the peel is up and the gloss is down, and the flats
    # keep just enough metallic to read as steel under the colour.
    f"{MOD_ID}_bolt_yellow": {
        "texture": {
            "family": "painted_metal",
            "size": 512,
            "params": {"base": [0.93, 0.69, 0.05], "rough": 0.40, "peel": 0.85},
        },
        "color": [0.93, 0.69, 0.05, 1.0],
        "metallic": 0.30,
        "roughness": 0.40,
    },
    f"{MOD_ID}_steel": {
        "texture": {"family": "steel_worn"},
        "color": [0.5, 0.53, 0.57, 1.0],
        "metallic": 0.85,
        "roughness": 0.35,
    },
    f"{MOD_ID}_concrete": {
        "texture": {"family": "concrete"},
        "color": [0.62, 0.6, 0.57, 1.0],
        "metallic": 0.0,
        "roughness": 0.85,
    },
    # Navy pole pad. A goal-post cushion is a heat-sealed vinyl SHELL over
    # a foam core, not upholstery: the old quilted pvc_weave read as a
    # fabric drum. Smooth semi-gloss plastic with a fine pebble grain, and
    # the softness lives in the cinched shell profile instead.
    f"{MOD_ID}_pad_vinyl": {
        "texture": {
            "family": "padded_vinyl",
            "size": 1024,
            "params": {
                "base": [0.085, 0.115, 0.30],
                "rough": 0.33,
                "grain": 0.55,
                "sheen": 0.5,
                "scuff": 0.3,
            },
        },
        "color": [0.085, 0.115, 0.30, 1.0],
        "metallic": 0.05,
        "roughness": 0.33,
        # ClearCoat is the engine's only second specular lobe — it gives
        # vinyl the broad wet-ish highlight that separates plastic sheeting
        # from cloth (there is no sheen lobe in this renderer).
        "stage": {"clearCoatFactor": 0.22, "clearCoatRoughnessFactor": 0.45},
    },
    # Open-cell foam core, glimpsed at the bottom edge of the wrap. Kept
    # dark grey-tan: a bright liner reads as a white sock round the pad.
    f"{MOD_ID}_pad_foam": {
        "texture": {
            "family": "eggshell",
            "params": {"base": [0.30, 0.29, 0.27]},
        },
        "color": [0.30, 0.29, 0.27, 1.0],
        "metallic": 0.0,
        "roughness": 0.95,
    },
    # --- Field build-up (ID-00003 natural grass application) -----------
    f"{MOD_ID}_field_soil": {
        "texture": {
            "family": "field_soil",
            "size": 1024,
            "params": {"base": [0.185, 0.125, 0.082], "stones": 0.35, "damp": 0.3},
        },
        "color": [0.185, 0.125, 0.082, 1.0],
        "metallic": 0.0,
        "roughness": 0.93,
    },
    f"{MOD_ID}_sod_edge": {
        "texture": {
            "family": "sod_edge",
            "size": 1024,
            "params": {"grass_frac": 0.32, "thatch_frac": 0.22},
        },
        "color": [0.20, 0.24, 0.13, 1.0],
        "metallic": 0.0,
        "roughness": 0.90,
    },
    f"{MOD_ID}_field_turf": {
        "texture": {
            "family": "field_turf",
            "size": 2048,
            "params": {
                "base": [0.085, 0.165, 0.060],
                "mow_bands": 2.6,
                "wear": 0.16,
            },
        },
        "color": [0.155, 0.285, 0.10, 1.0],
        "metallic": 0.0,
        "roughness": 0.82,
    },
    # Alpha-cutout blade cards standing proud of the mat.
    f"{MOD_ID}_grass_blades": {
        "texture": {
            "family": "grass_card",
            "size": 512,
            "params": {"blades": 160, "lean": 0.5, "dead": 0.07},
        },
        "color": [0.155, 0.285, 0.10, 1.0],
        "metallic": 0.0,
        "roughness": 0.78,
        "double_sided": True,
        # castShadows OFF: thousands of little alpha quads each throwing a
        # hard shadow is what turned the first turf into dark blotches.
        # invertBackFaceNormals keeps the far side of each card lit.
        "material": {"invertBackFaceNormals": True, "castShadows": False},
    },
    # Crossbar end cap: the maker's mark DIE-STRUCK into the disc.
    # Printed black type on a yellow cap read as a sticker (player,
    # 2026-08-14); the mark is now pure relief in the steel with the paint
    # following it down, filling most of the face the way a cast monogram
    # does. normal_strength is up from the 2.0 default because this is the
    # one surface on the prop whose entire read IS its normal map.
    f"{MOD_ID}_bar_cap": {
        "texture": {
            "family": "stamped_mark",
            "size": 1024,
            "normal_strength": 3.2,
            "params": {
                "text": "CGS",
                "base": [0.94, 0.70, 0.05],
                # The monogram OWNS the cap: sized to the largest word box
                # that fits inside the disc, with the bead pushed out to the
                # rim and the inner groove gone so nothing crowds it.
                "fit_circle": True,
                "fill": 0.895,
                "tracking": 0.050,
                "bead_band": [0.962, 0.998],
                "groove_band": None,
                "pocket_r": 0.952,
                "depth": 0.55,
            },
        },
        "color": [0.94, 0.70, 0.05, 1.0],
        "metallic": 0.25,
        "roughness": 0.34,
    },
    # Pad webbing: woven synthetic strap, not flat tape. v runs across the
    # 75 mm width so the rolled selvedge lands on the strap's real edges.
    f"{MOD_ID}_strap_black": {
        "texture": {
            "family": "webbing",
            "size": 1024,
            "params": {"warp": 54, "weft": 120},
        },
        "color": [0.09, 0.09, 0.10, 1.0],
        "metallic": 0.0,
        "roughness": 0.60,
    },
    # Buckle hardware: injection-moulded glass-filled nylon with the
    # etched-cavity pebble grain every backpack side-release buckle has.
    f"{MOD_ID}_buckle_nylon": {
        "texture": {
            "family": "molded_nylon",
            "size": 512,
            "normal_strength": 2.4,
            "params": {"grain": 0.6},
        },
        "color": [0.055, 0.055, 0.062, 1.0],
        "metallic": 0.0,
        "roughness": 0.58,
    },
    # 4 in x 42 in directional flags (GPDSTRGPT) at the upright tips.
    # The `canvas` family read as burlap: a plain weave at one flat
    # roughness has no sheen, so the flag looked like painted board. The
    # `flag_satin` family is medium-weight silky flag cloth — satin float
    # crowns polished into the roughness map, matte interstices, soft
    # drape folds — which is what gives it the moving highlight real flag
    # nylon has. Roughness 0.34 with metallic 0 is the silk window; above
    # ~0.55 the sheen dies, below ~0.25 it turns to plastic sheeting.
    f"{MOD_ID}_flag_cloth": {
        "texture": {
            "family": "flag_satin",
            "size": 1024,
            "params": {
                "base": [0.72, 0.08, 0.06],
                "rough": 0.34,
                "sheen": 0.62,
                "drape": 1.15,
                "hem": 0.035,
            },
        },
        "color": [0.72, 0.08, 0.06, 1.0],
        "metallic": 0.0,
        "roughness": 0.34,
        "double_sided": True,
        # This engine has NO sheen or anisotropic lobe — probed the whole
        # shipped shader library (brdf_spec.h.hlsl is GGX + Smith +
        # Schlick + a road-sign retroreflection term and nothing else),
        # and `sheen`/`anisotropy` appear in zero stock materials. The
        # three levers that DO exist and together read as silk:
        #   * clearCoat — a real second GGX lobe with its own roughness,
        #     which is the closest thing to a soft cloth sheen.
        #   * the stock tiled fabric detail normal, which is what
        #     BeamNG's own cloth (vehicles/common cloth_visor) uses for
        #     weave at grazing angles.
        #   * subSurface — sun-only backface wrap transmission, so the
        #     flag glows when the sun is behind it, exactly like real
        #     lightweight flag nylon.
        "stage": {
            "detailNormalMap": (
                "/vehicles/common/generic_mat_tex/detail_fabric_nm.normal.png"
            ),
            "detailNormalMapStrength": 0.55,
            "detailScale": [6, 6],
            "clearCoatFactor": 0.11,
            "clearCoatRoughnessFactor": 0.68,
        },
        # invertBackFaceNormals pairs with doubleSided: without it the
        # back of a zero-thickness sheet lights from the wrong side and
        # the flag goes black whenever it twists away (stock
        # m_fabric_polyester_trim carries the same pair).
        "material": {
            "invertBackFaceNormals": True,
            "subSurface": True,
            "subSurfaceIntensity": 0.55,
        },
    },
    # Builder's plate on the gooseneck below the crossbar joint.
    # Patent and serial data plate on the gooseneck. Real equipment data
    # plates are stamped or photo-etched STAINLESS — light brushed metal
    # with dark filled type — not a black legend panel, and the type is
    # small, centred, and stacked in a fixed order: maker, model, serial,
    # then the patent line in the smallest size at the bottom. Numbers are
    # fictional; the point is the format, which is what makes it read as
    # a real data plate rather than a label.
    # Patent / serial data plate. GRAPHIC DESIGN, not just text on metal —
    # the first version was four centred lines adrift in an empty plate,
    # which reads as placeholder. Real photo-etched equipment nameplates
    # follow a strict vocabulary:
    #   * the maker's name is the dominant element, alone on a header line;
    #   * a rule divides the header from the data block;
    #   * data is a LABEL/VALUE GRID in two columns — centred data rows are
    #     the amateur tell — with labels lighter and values heavier;
    #   * a second rule fences off the statutory patent line, which is the
    #     smallest type on the plate and runs full width;
    #   * margins are tight, so the type fills the plate.
    # Light brushed stainless with dark etched fill (numbers fictional).
    f"{MOD_ID}_builder_decal": {
        "texture": {
            "family": "panel_legend",
            "size": 1024,
            "params": {
                "title": "",
                "aspect": 2.6,
                "base": [0.60, 0.61, 0.63],
                "ink": [0.075, 0.075, 0.085],
                "label_scale": 0.115,
                "rules": [
                    [0.745, 0.44, 0.020],
                    [0.180, 0.44, 0.013],
                ],
                "labels": [
                    [0.50, 0.845, "CHARLIE GOAL SYSTEMS INC.", 0.78],
                    [0.30, 0.605, "MODEL", 0.46],
                    [0.68, 0.605, "GP835PL", 0.56],
                    [0.30, 0.435, "SERIAL No.", 0.46],
                    [0.68, 0.435, "835-04127", 0.56],
                    [0.30, 0.265, "MFG. DATE", 0.46],
                    [0.68, 0.265, "05 - 2026", 0.56],
                    [0.50, 0.070, "U.S. PAT. 7,846,041   OTHER PAT. PEND.", 0.36],
                ],
            },
        },
        "color": [0.60, 0.61, 0.63, 1.0],
        "metallic": 0.75,
        "roughness": 0.40,
    },
}

TRIGGERS = {
    # The scoring window: between the uprights, above the crossbar. Only a
    # lofted car can enter it, so entry IS a made kick.
    "goal_zone": {
        "mode": "Overlaps",
        "center": [0.0, 0.0, 8.6],
        "dimensions": [5.3, 2.2, 10.1],
    },
}

EFFECTS = {}

BEHAVIOR = {
    "camera_distance": 30.0,
    "celebrate_cooldown_seconds": 6.0,
    # The flags are real soft-body cloth, so they stream on BeamNG's
    # physics ground wind (core_environment.getGroundWind, broadcast to
    # every vehicle as obj:setWind). No stock level ships a wind value —
    # it starts at (0,0,0) — so out of the box the flags would just hang,
    # which is correct but not what a stadium looks like. On spawn the
    # prop sets a light breeze ONLY IF the level's wind is still exactly
    # zero, so it never overrides a wind the player set in the Winds app.
    # Set breeze_mps to 0 to disable that entirely; ground wind is global
    # and does reach other vehicles' aero, though 4 m/s is about 9 mph.
    "breeze_mps": 4.0,
    "breeze_heading_deg": 205.0,
}

LUA_BEHAVIOR = r"""
-- BeamNG has TWO unrelated wind systems: core_environment's ground wind,
-- which is the physics one the cloth solver actually feels, and the
-- Torque legacy cloud/foliage wind. getWindSpeed() belongs to the SECOND
-- one and returns cloud scroll speed -- reading it here would be a
-- silent no-op. getGroundWind/setGroundWind are the real pair.
local function groundWind()
  local ok, wind = pcall(function()
    return core_environment and core_environment.getGroundWind
      and core_environment.getGroundWind()
  end)
  if ok and wind then return wind end
  return nil
end

local function seedBreeze(state)
  if (B.breeze_mps or 0) <= 0 then return end
  local wind = groundWind()
  -- Only seed dead air: a wind the player dialled in must win.
  if not wind or wind:length() > 0.01 then return end
  local heading = math.rad(B.breeze_heading_deg or 0)
  pcall(function()
    core_environment.setGroundWind(
      math.sin(heading) * B.breeze_mps,
      math.cos(heading) * B.breeze_mps,
      0)
  end)
end

behavior.init = function(state)
  local b = state.behavior
  b.clock = 0
  b.cooldown = 0
  b.stats = b.stats or {goods = 0, best_speed_mps = 0}
  seedBreeze(state)
end

behavior.reset = function(state)
  behavior.init(state)
end

behavior.onEnter = function(state, zone, vehicle)
  local b = state.behavior
  if zone ~= "goal_zone" or (b.cooldown or 0) > 0 then return end
  b.cooldown = B.celebrate_cooldown_seconds
  local speed = vehicle:getVelocity():length()
  b.stats.goods = (b.stats.goods or 0) + 1
  if speed > (b.stats.best_speed_mps or 0) then
    b.stats.best_speed_mps = math.floor(speed * 10) / 10
  end
  showMessage("IT'S GOOD! Right through the uprights!", 2.6)
  emitEvent(state, "I", "field_goal_good", {
    subject_id = vehicle:getId(),
    speed_mps = math.floor(speed * 10) / 10,
    total_goods = b.stats.goods,
  })
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  b.clock = (b.clock or 0) + dtSim
  if (b.cooldown or 0) > 0 then
    b.cooldown = b.cooldown - dtSim
  end
end
"""
