"""Whale Blowhole Geyser — authored constants for Blender + runtime.

A friendly cartoon whale with a drivable back: the tail is a long, gentle
ramp (max grade ~17 degrees after play-testing said the original was too
steep). Park on the blowhole pad and the whale inhales (mist wisps,
anticipation) — then the blowhole ERUPTS and BLASTS the car hundreds of
feet straight up on a towering water column, venting spray while the
passenger regrets everything.
"""

MOD_ID = "ericrolph_whale_geyser"
DISPLAY_NAME = "Whale Blowhole Geyser"
VALUE_DOLLARS = 27000
ZIP_BASENAME = "whale_geyser_ericrolph.zip"

# Authored frame: right-handed, meters, Z-up, +Y drive direction. Drive up
# the trestle ramp from -Y onto the back; the head faces +Y.
PAD_CENTER = (0.0, 6.5, 4.33)

# Hero-mesh deck stations, ray-sampled from assets/whale_hero.glb in its
# authored pose (2026-07-23): (y, drivable_half_width, (z at x-fractions
# -0.84/-0.42/0/0.42/0.84 of half_width), flank_skirt_half_width). The
# generator embeds collision DECK_EMBED below these surface heights.
WHALE_DECK = [
    (-4.0, 2.2, (3.86, 4.07, 4.10, 4.01, 3.59), 3.2),
    (-2.5, 2.2, (3.96, 4.12, 4.15, 4.06, 3.66), 3.2),
    (-1.0, 2.2, (4.02, 4.17, 4.19, 4.10, 3.74), 2.6),
    (0.5, 2.2, (4.05, 4.20, 4.22, 4.13, 3.75), 2.6),
    (2.0, 2.2, (4.10, 4.23, 4.25, 4.16, 3.75), 2.6),
    (3.5, 2.2, (4.14, 4.26, 4.27, 4.17, 3.74), 2.6),
    (5.0, 2.0, (4.21, 4.29, 4.28, 4.19, 3.86), 2.9),
    (6.5, 2.0, (4.27, 4.33, 4.32, 4.20, 3.74), 2.7),
    (8.0, 1.8, (4.31, 4.35, 4.34, 4.23, 3.75), 2.8),
    (9.5, 1.6, (4.24, 4.27, 4.27, 4.16, 3.81), 2.6),
    (11.0, 1.4, (4.14, 4.15, 4.13, 4.03, 3.78), 2.4),
    (12.5, 1.2, (4.04, 4.05, 4.00, 3.92, 3.72), 2.2),
]
DECK_EMBED = 0.05
PAD_Z = 4.33
# Research-trestle entry ramp: the hero whale's tail is a raised catwalk
# with a fluke notch, so the drive-on route is a long shallow steel ramp
# landing where the back widens (the run passes under the raised fluke).
RAMP_GROUND_Y = -27.0
RAMP_LAND_Y = -4.0
RAMP_HALF_W = 2.3

PALETTE = {
    # Baked maps extracted from the generated hero whale, checked in under
    # assets/ so texture staging is a byte-stable copy.
    f"{MOD_ID}_whale_hero": {
        "texture": {
            "family": "external",
            "maps": {
                "baseColorMap": "assets/whale_hero.color.png",
                "normalMap": "assets/whale_hero.normal.png",
                "roughnessMap": "assets/whale_hero_roughness.data.png",
            },
        },
        "color": [0.35, 0.42, 0.5, 1.0],
        "metallic": 0.0,
        "roughness": 0.55,
    },
    f"{MOD_ID}_pupil_black": {
        "color": [0.05, 0.05, 0.06, 1.0],
        "metallic": 0.0,
        "roughness": 0.3,
    },
    f"{MOD_ID}_blowhole_dark": {
        "texture": {"family": "whale_skin", "params": {"base": [0.16, 0.26, 0.4]}},
        "color": [0.15, 0.25, 0.38, 1.0],
        "metallic": 0.0,
        "roughness": 0.6,
    },
    f"{MOD_ID}_ramp_steel": {
        "texture": {
            "family": "painted_metal",
            "params": {"base": [0.55, 0.58, 0.6], "rough": 0.5},
        },
        "color": [0.55, 0.58, 0.6, 1.0],
        "metallic": 0.3,
        "roughness": 0.5,
    },
    f"{MOD_ID}_hazard": {
        "texture": {"family": "hazard_chevron"},
        "color": [0.95, 0.75, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.55,
    },
    f"{MOD_ID}_paint_white": {
        "color": [0.92, 0.92, 0.9, 1.0],
        "metallic": 0.0,
        "roughness": 0.6,
    },
}

TRIGGERS = {
    "blowhole_zone": {
        "mode": "Contains",
        # Bottom reaches ~0.55 m below the pad surface: settling vehicle
        # OOBBs dip below the surface and Contains flaps without the
        # allowance (proven live 2026-07-22).
        # Enlarged after play-testing: a driven (not teleported) car parks
        # off-centre on the crowned back and must still be contained.
        "center": [PAD_CENTER[0], PAD_CENTER[1], PAD_CENTER[2] + 1.55],
        "dimensions": [6.6, 6.8, 4.9],
    },
    "back_zone": {
        "mode": "Overlaps",
        "center": [0.0, -3.0, 3.9],
        "dimensions": [7.0, 12.0, 4.4],
    },
}

EFFECTS = {
    "idle_puff": {
        "emitter": "BNGP_34",
        "position": [0.0, 6.5, 4.6],
        "direction": [0.0, 0.0, 1.0],
    },
    "geyser_low": {
        "emitter": "BNGP_sprinkler",
        "position": [0.0, 6.5, 4.5],
        "direction": [0.0, 0.0, 1.0],
    },
    "geyser_mid1": {
        "emitter": "BNGP_waterfallsteam",
        "position": [0.0, 6.5, 7.4],
        "direction": [0.0, 0.0, 1.0],
    },
    "geyser_mid2": {
        "emitter": "BNGP_waterfallsteam",
        "position": [0.0, 6.5, 13.0],
        "direction": [0.0, 0.0, 1.0],
    },
    "geyser_mid3": {
        "emitter": "BNGP_waterfallsteam",
        "position": [0.0, 6.5, 17.5],
        "direction": [0.0, 0.0, 1.0],
    },
    "geyser_top": {
        "emitter": "BNGP_waterfallsteam",
        "position": [0.0, 6.5, 22.0],
        "direction": [0.0, 0.0, 1.0],
    },
}

BEHAVIOR = {
    "camera_distance": 36.0,
    "idle_puff_period": 8.0,
    "idle_puff_seconds": 0.5,
    "inhale_seconds": 1.5,
    # 55 m/s straight up is a ~150 m (≈500 ft) apex: THAR SHE BLOWS.
    "blast_up_mps": 55.0,
    "blast_forward_mps": 3.0,
    "vent_seconds": 3.0,
    "cooldown_seconds": 4.0,
    "hint_period_seconds": 7.0,
    "pad_center": list(PAD_CENTER),
}

LUA_BEHAVIOR = r"""
local GEYSER_EFFECTS = {
  "geyser_low", "geyser_mid1", "geyser_mid2", "geyser_mid3", "geyser_top",
}

local function geyserActive(state, active)
  for _, name in ipairs(GEYSER_EFFECTS) do
    setEffectActive(state, name, active)
  end
end

behavior.init = function(state)
  state.behavior.phase = "idle"
  state.behavior.elapsed = 0
  state.behavior.clock = 0
  state.behavior.puffTimer = 0
  geyserActive(state, false)
  setEffectActive(state, "idle_puff", false)
end

behavior.reset = function(state)
  behavior.init(state)
end

behavior.onEnter = function(state, zone, vehicle)
  local b = state.behavior
  if zone == "back_zone" and b.phase == "idle" then
    showMessage("You are driving on a whale. It doesn't mind.", 2.4)
  elseif zone == "blowhole_zone" and b.phase == "idle" then
    b.phase = "inhale"
    b.elapsed = 0
    b.subjectId = vehicle:getId()
    setEffectActive(state, "idle_puff", true)
    showMessage("The whale is inhaling...", 1.8)
    emitEvent(state, "I", "whale_inhaling", {subject_id = vehicle:getId()})
  end
end

behavior.onExit = function(state, zone, vehicleId)
  local b = state.behavior
  if zone == "blowhole_zone" and b.phase == "inhale"
    and zoneCount(state, "blowhole_zone") == 0 then
    b.phase = "idle"
    b.elapsed = 0
    b.subjectId = nil
    setEffectActive(state, "idle_puff", false)
    showMessage("The whale exhales, disappointed.", 1.8)
  end
end

behavior.onSubjectGone = function(state, vehicleId, reason)
  local b = state.behavior
  if b.subjectId == vehicleId and b.phase == "inhale" then
    b.phase = "idle"
    b.elapsed = 0
    b.subjectId = nil
    setEffectActive(state, "idle_puff", false)
  end
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  b.clock = b.clock + dtSim
  b.elapsed = b.elapsed + dtSim

  if b.phase == "idle" then
    -- Guide drivers who are on the whale but not yet on the pad.
    if zoneCount(state, "back_zone") > 0
      and zoneCount(state, "blowhole_zone") == 0 then
      b.hintTimer = (b.hintTimer or 0) + dtSim
      if b.hintTimer >= B.hint_period_seconds then
        b.hintTimer = 0
        showMessage("Park fully ON the blowhole pad at the head!", 2.4)
      end
    else
      b.hintTimer = 0
    end
    b.puffTimer = b.puffTimer + dtSim
    if b.puffTimer >= B.idle_puff_period then
      setEffectActive(state, "idle_puff", true)
    end
    if b.puffTimer >= B.idle_puff_period + B.idle_puff_seconds then
      setEffectActive(state, "idle_puff", false)
      b.puffTimer = 0
    end
  elseif b.phase == "inhale" then
    if b.elapsed >= B.inhale_seconds then
      local vehicle = firstOccupant(state, "blowhole_zone")
      if not vehicle then
        b.phase = "idle"
        b.elapsed = 0
        setEffectActive(state, "idle_puff", false)
        return
      end
      setEffectActive(state, "idle_puff", false)
      geyserActive(state, true)
      local up = toWorldDir(state, vec3(0, 0, 1))
      local forward = toWorldDir(state, vec3(0, 1, 0))
      local velocity = up * B.blast_up_mps + forward * B.blast_forward_mps
      showMessage("THAR SHE BLOWS!", 2.0)
      if launchSubject(state, vehicle, velocity) then
        emitEvent(state, "I", "whale_erupted", {subject_id = vehicle:getId()})
        b.phase = "venting"
        b.elapsed = 0
      else
        geyserActive(state, false)
        b.phase = "idle"
        b.elapsed = 0
      end
    end
  elseif b.phase == "venting" then
    if b.elapsed >= B.vent_seconds then
      geyserActive(state, false)
      b.phase = "settle"
      b.elapsed = 0
    end
  elseif b.phase == "settle" then
    if b.elapsed >= B.cooldown_seconds then
      b.phase = "idle"
      b.elapsed = 0
      b.subjectId = nil
      b.puffTimer = 0
      emitEvent(state, "I", "whale_rearmed", {})
    end
  end
end
"""
