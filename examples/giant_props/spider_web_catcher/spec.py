"""200MPH Elastic Spider Web Catcher — authored constants for Blender + runtime.

A giant orb web strung between two steel towers at the end of a marked
200 MPH run-up. The web is REAL elastic jbeam: free silk nodes on soft
spoke/ring beams, skinned with per-strand ribbon meshes so the whole net
visibly stretches metres deep when a car slams into it. The membrane
arrests a 200 mph car over ~15 m of travel; the hardest hits SNAP outer
strands (finite breakStrength, per-sector breakGroups). Once the fly stops
buzzing, a giant spider descends from the crossbeam on a silk line to
inspect its catch, then retreats. When the web is empty again the prop
re-spins itself (physics reset restores snapped strands).

Authored frame: right-handed, meters, Z-up, +Y drive direction — the
run-up approaches from -Y and the catch stretches the web toward +Y.
"""

MOD_ID = "ericrolph_spider_web_catcher"
DISPLAY_NAME = "200MPH Spider Web Catcher"
VALUE_DOLLARS = 29000
ZIP_BASENAME = "spider_web_catcher_ericrolph.zip"

WEB_CENTER_Z = 8.5
WEB_RING_RADII = (1.5, 3.0, 4.5, 6.0, 7.5)
WEB_SPOKES = 8
TOWER_X = 10.5
TOWER_TOP_Z = 16.5
CROSSBEAM_Z = 16.2
SPIDER_PIVOT = (0.0, 0.0, 16.0)

PALETTE = {
    f"{MOD_ID}_tower_steel": {
        "texture": {"family": "steel_worn"},
        "color": [0.5, 0.53, 0.57, 1.0],
        "metallic": 0.8,
        "roughness": 0.4,
    },
    f"{MOD_ID}_web_silk": {
        "color": [0.92, 0.94, 0.97, 1.0],
        "metallic": 0.0,
        "roughness": 0.25,
        "double_sided": True,
    },
    f"{MOD_ID}_spider_black": {
        "texture": {"family": "bakelite"},
        "color": [0.08, 0.07, 0.08, 1.0],
        "metallic": 0.15,
        "roughness": 0.45,
    },
    f"{MOD_ID}_spider_red": {
        "color": [0.8, 0.12, 0.1, 1.0],
        "metallic": 0.0,
        "roughness": 0.4,
    },
    f"{MOD_ID}_eye_glow": {
        "color": [0.9, 0.85, 0.3, 1.0],
        # THREE components, not four (2026-08-15, round 18). This was
        # [0.9, 0.8, 0.25, 1.0], and four is inert - the spider's eyes have
        # been plain yellow plastic in every build. AGENTS.md, "Round-16/17:
        # the photometric ledger"; prop_builder.check_emissive_factor now
        # refuses to build a four-element factor.
        "emissive": [0.9, 0.8, 0.25],
        "metallic": 0.0,
        "roughness": 0.3,
        # 800 nit. Eight small lenses on a dark body: a tiny emissive area
        # needs a high level to register at all, and unlike the centrifuge's
        # vision band there is no risk of a large surface fusing into a white
        # slab. Reads unmistakably lit at noon (+44.5 sRGB over control) and
        # saturates after dark, which is the whole point of glowing eyes.
        "stage": {"emissiveIntensityNits": 800},
    },
    f"{MOD_ID}_board_white": {
        "texture": {
            "family": "painted_metal",
            "params": {"base": [0.9, 0.89, 0.85], "rough": 0.45},
        },
        "color": [0.9, 0.89, 0.85, 1.0],
        "metallic": 0.1,
        "roughness": 0.45,
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
    f"{MOD_ID}_concrete": {
        "texture": {"family": "concrete"},
        "color": [0.62, 0.6, 0.57, 1.0],
        "metallic": 0.0,
        "roughness": 0.85,
    },
}

TRIGGERS = {
    # Long approach throat: arming/taunts fire while the fly is inbound.
    "approach_zone": {
        "mode": "Overlaps",
        "center": [0.0, -30.0, 5.0],
        "dimensions": [30.0, 44.0, 12.0],
    },
    # The web plane plus the full stretch pocket behind it.
    "web_zone": {
        "mode": "Overlaps",
        "center": [0.0, 7.0, 8.5],
        "dimensions": [26.0, 30.0, 19.0],
    },
}

EFFECTS = {
    "impact_dust": {
        "emitter": "BNGP_2",
        "position": [0.0, 1.0, 4.0],
        "direction": [0.0, 1.0, 0.6],
    },
}

BEHAVIOR = {
    "camera_distance": 42.0,
    "incoming_speed_mps": 25.0,
    "caught_speed_mps": 10.0,
    "stretch_axis_note": "authored +Y",
    "spider_descend_seconds": 2.6,
    "spider_inspect_seconds": 5.0,
    "spider_retreat_seconds": 2.0,
    "spider_drop_depth": 6.2,
    "rearm_delay_seconds": 4.0,
    "web_plane_margin": 0.5,
}

LUA_BEHAVIOR = r"""
local function poseSpider(state, drop, sway)
  setPartPose(
    state,
    "spider",
    vec3(sway or 0, 0, -(drop or 0)),
    nil
  )
end

behavior.init = function(state)
  local b = state.behavior
  b.phase = "idle"
  b.elapsed = 0
  b.clock = 0
  b.entrySpeed = 0
  b.stats = b.stats or {catches = 0, peak_depth_m = 0, peak_entry_mps = 0}
  poseSpider(state, 0, 0)
end

behavior.reset = function(state)
  behavior.init(state)
  setEffectActive(state, "impact_dust", false)
end

behavior.onEnter = function(state, zone, vehicle)
  local b = state.behavior
  if zone == "approach_zone" and b.phase == "idle" then
    local speed = vehicle:getVelocity():length()
    if speed > B.incoming_speed_mps then
      showMessage("A FLY! The web glistens hungrily.", 2.2)
      emitEvent(state, "I", "web_fly_incoming", {
        subject_id = vehicle:getId(),
        speed_mps = math.floor(speed * 10) / 10,
      })
    else
      showMessage("The web prefers its flies FAST. 200 MPH, please.", 2.4)
    end
  elseif zone == "web_zone" and b.phase == "idle" then
    local speed = vehicle:getVelocity():length()
    b.entrySpeed = speed
    if speed > (b.stats.peak_entry_mps or 0) then
      b.stats.peak_entry_mps = math.floor(speed * 10) / 10
    end
    b.phase = "catching"
    b.elapsed = 0
    b.catchId = vehicle:getId()
    setEffectActive(state, "impact_dust", true)
    emitEvent(state, "I", "web_impact", {
      subject_id = vehicle:getId(),
      speed_mps = math.floor(speed * 10) / 10,
    })
  end
end

behavior.onSubjectGone = function(state, vehicleId, reason)
  local b = state.behavior
  if b.catchId == vehicleId and (b.phase == "catching" or b.phase == "caught") then
    b.phase = "retreat"
    b.elapsed = 0
  end
end

local function catchDepth(state, vehicle)
  local stretch = toWorldDir(state, vec3(0, 1, 0))
  return (vehicle:getPosition() - state.origin):dot(stretch)
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  b.clock = b.clock + dtSim
  b.elapsed = b.elapsed + dtSim
  if b.phase == "catching" then
    local vehicle = b.catchId and exactVehicle(b.catchId) or nil
    if not vehicle or zoneCount(state, "web_zone") == 0 then
      b.phase = "idle"
      b.elapsed = 0
      setEffectActive(state, "impact_dust", false)
      return
    end
    local depth = catchDepth(state, vehicle)
    if depth > (b.stats.peak_depth_m or 0) then
      b.stats.peak_depth_m = math.floor(depth * 10) / 10
    end
    local speed = vehicle:getVelocity():length()
    if b.elapsed > 0.8 and speed < B.caught_speed_mps then
      b.phase = "descend"
      b.elapsed = 0
      b.stats.catches = (b.stats.catches or 0) + 1
      setEffectActive(state, "impact_dust", false)
      showMessage("CAUGHT! Something is coming down to look at you...", 2.8)
      emitEvent(state, "I", "web_catch", {
        subject_id = b.catchId,
        entry_mps = math.floor((b.entrySpeed or 0) * 10) / 10,
        depth_m = b.stats.peak_depth_m,
      })
    elseif b.elapsed > 12.0 then
      -- Never slowed enough: it tore through or bounced out.
      b.phase = "idle"
      b.elapsed = 0
      setEffectActive(state, "impact_dust", false)
      emitEvent(state, "I", "web_escaped", {subject_id = b.catchId})
    end
  elseif b.phase == "descend" then
    local t = math.min(1, b.elapsed / B.spider_descend_seconds)
    local smooth = t * t * (3 - 2 * t)
    poseSpider(state, B.spider_drop_depth * smooth, math.sin(b.clock * 2.0) * 0.3)
    if t >= 1 then
      b.phase = "inspect"
      b.elapsed = 0
      showMessage("The spider looks you over. You appear... crunchy.", 3.0)
      emitEvent(state, "I", "spider_inspected", {})
    end
  elseif b.phase == "inspect" then
    poseSpider(
      state,
      B.spider_drop_depth + math.sin(b.clock * 3.0) * 0.35,
      math.sin(b.clock * 1.6) * 0.4
    )
    if b.elapsed >= B.spider_inspect_seconds then
      b.phase = "retreat"
      b.elapsed = 0
      showMessage("Not ripe yet. The spider retreats to wait.", 2.4)
    end
  elseif b.phase == "retreat" then
    local t = math.min(1, b.elapsed / B.spider_retreat_seconds)
    local smooth = t * t * (3 - 2 * t)
    poseSpider(state, B.spider_drop_depth * (1 - smooth), 0)
    if t >= 1 then
      b.phase = "waiting_clear"
      b.elapsed = 0
    end
  elseif b.phase == "waiting_clear" then
    poseSpider(state, 0, 0)
    if zoneCount(state, "web_zone") == 0 and zoneCount(state, "approach_zone") == 0 then
      if b.elapsed >= B.rearm_delay_seconds then
        local prop = exactVehicle(state.propId)
        if prop then
          local okReset = pcall(function() prop:requestReset(RESET_PHYSICS) end)
          if okReset then
            emitEvent(state, "I", "web_rearmed", {})
            showMessage("The web re-spins itself. Good as new.", 2.2)
          end
        end
        b.phase = "idle"
        b.elapsed = 0
      end
    else
      b.elapsed = 0
    end
  end
end
"""
