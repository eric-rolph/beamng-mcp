"""Hot Potato — authored constants shared by Blender and the runtime.

A quarter-scale stainless Gateway Arch with a scorched russet potato hanging
under its apex. Drive onto the medallion and the potato lands on YOUR roof: it
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

# The fuse tick: a 1.3 s beep+sizzle loop synthesized by
# authoring/make_tick_audio.py, played inside the CARRIER's vehicle VM via
# obj:createSFXSource (audio mechanism v3 — the pack's only proven-audible
# path). v1 ticked a looping stock FMOD event through Engine.Audio.playOnce
# and leaked one immortal beeper per tick; see the TICK_* block in
# LUA_BEHAVIOR.
SHIP_ASSETS = (
    "sound/ericrolph_hot_potato_tick.ogg",
    "sound/ericrolph_hot_potato_whistle.ogg",
    "sound/ericrolph_hot_potato_sputter.ogg",
)

# Files copied from assets/ to the MOD ROOT (not vehicles/<mod_id>/) — the
# in-game settings panel (v2.2, 2026-08-29). BeamNG discovers UI apps by
# scanning ui/modules/apps/*/app.json across every mounted mod, so the app
# ships at the zip root exactly like a stock app. The app's controls are
# built at runtime from hotPotatoGetOptionSchema, so it never drifts from
# OPTION_RANGE.
SHIP_ROOT_ASSETS = (
    # BeamMP's custom-event bridge. This is the one narrow exception to the
    # Giant Props "no global modScript" rule: the script loads only a
    # transport adapter, never the gameplay runtime. The spawned prop still
    # owns runtime registration, reset, and teardown exactly as it does in
    # single-player. BeamMP requires a modScript in a Client resource before
    # AddEventHandler/TriggerServerEvent traffic can reach a downloaded mod.
    (
        "beammp/modScript.lua",
        "scripts/ericrolph_hot_potato/modScript.lua",
    ),
    (
        "beammp/client.lua",
        "lua/ge/extensions/ericrolphHotPotatoBeamMP.lua",
    ),
    ("ui/hotPotatoTuner/app.json", "ui/modules/apps/hotPotatoTuner/app.json"),
    ("ui/hotPotatoTuner/app.js", "ui/modules/apps/hotPotatoTuner/app.js"),
    ("ui/hotPotatoTuner/app.html", "ui/modules/apps/hotPotatoTuner/app.html"),
    # The Add-App browser tile (v2.4, 2026-08-29, measured against the
    # game's ui/appSelector/general.lua): a missing app.png falls back to
    # the generic /ui/images/appDefault.png, which is why the player could
    # not find the app in the grid. Authored by make_app_icon.py.
    ("ui/hotPotatoTuner/app.png", "ui/modules/apps/hotPotatoTuner/app.png"),
    # A whole shipped HUD layout (v2.4.2, 2026-08-29, measured against the
    # game's ui/appLayouts.lua): getAvailableLayouts() re-scans the virtual
    # /settings/ui_apps/originalLayouts/ on EVERY call (no cache, unlike the
    # Add-App grid), and mod zips overlay that VFS root, so this file puts a
    # ready-made "Hot Potato" entry straight into the HUD Layouts list —
    # stock Freeroam apps plus the tuner already placed. Type "freeroam"
    # with a non-"freeroam" filename stem keeps the stock default layout in
    # charge until the player explicitly picks this one.
    (
        "ui/hotPotatoTuner/hot_potato.uilayout.json",
        "settings/ui_apps/originalLayouts/hot_potato.uilayout.json",
    ),
)

# --------------------------------------------------------------------------
# The arch. Authored frame: right-handed, meters, Z-up, +Y drive direction.
#
# TRUE QUARTER SCALE of the monument (v2.2, 2026-08-29: "scaled to 1/4 size
# ... hyper-realistic"). The published centroid curve is
#     y = 693.8597 - 68.7672 cosh(0.0100333 x)  (feet, |x| <= 299.2239)
# giving shape parameter C = 3.0023 and height / half-span = 2.089, and a
# triangular section tapering 54 ft -> 17 ft. Every number below is the
# published foot figure, divided by four, in metres — not a look-alike.
# --------------------------------------------------------------------------
ARCH_HALF_SPAN = 22.801  # centroid half span, 299.2239 ft / 4
ARCH_C = 3.0023
ARCH_HEIGHT = ARCH_HALF_SPAN * 2.089  # centroid apex 47.63 m (625.09 ft / 4)
ARCH_BASE_SIDE = 4.115  # 54 ft / 4
ARCH_TOP_SIDE = 1.295  # 17 ft / 4
ARCH_STATIONS = 181
ARCH_FOOT_OVERRUN = 1.005  # legs bury below grade so no end caps are needed
# One texture tile is FOUR panel courses; the prototype's sections are 12 ft
# tall, so a course is 0.9144 m at quarter scale and the tile is 3.6576 m.
# The arch_stainless family draws 4 courses x 3 panel columns per tile.
ARCH_UV_TILE = 3.6576
ARCH_COLLIDE_MAX_Z = 9.0  # skin the cage only where a car can reach

MEDALLION_RADIUS = 4.2
# The plate is a FLUSH INLAY, not a raised platform (v2.6, player report:
# "driving over the center metal medallion can pop tires"). The tire-popper
# was the cage pad's collision plane: a 6x6 m face floating 0.05 m above
# grade with no side faces, so its rim was a razor step hidden in the middle
# of an 8.4 m disc that LOOKS smooth. The fix is twofold: the visual plate
# drops to 12 mm proud (a plaza inlay a tyre never feels), and the cage pad
# ships NO collision faces at all — cars roll on the real ground straight
# through the visual. PAD_CAGE_TOP_Z keeps the lattice's authored height so
# the refnode frame and every node id stay byte-identical.
MEDALLION_TOP_Z = 0.012
PAD_CAGE_TOP_Z = 0.05
PAD_HALF = 3.0  # cage lattice half-extent under the medallion
PYLON_HALF = 2.2  # quarter-scale legs are 4.1 m wide; the old 0.9 was inside them
PYLON_TOP_Z = 6.0
CAGE_RING_STRIDE = 6  # every 6th station becomes a cage ring

# The potato's idle home: under the apex, high enough to clear a city bus
# (2.994 m) with room to spare, low enough to read from a car.
POTATO_HOME = (0.0, 0.0, 5.6)
POTATO_SEMI_X = 0.95
POTATO_SEMI_Y = 0.60
POTATO_SEMI_Z = 0.58

# The mash chunks (v2.4, "make it appear like mash potato went everywhere").
# Six high-poly lumps of mashed potato, authored PARKED underground beneath
# the plaza; the runtime flings them ballistically out of the detonation and
# parks them again when the splatter has faded. One authored home per chunk
# (they are separate parts so each flies its own arc), shared with Blender
# so the pivots and the runtime agree byte-for-byte. Semi-size per chunk is
# the sculpt radius Blender uses.
MASH_HOMES = [
    [-3.0, -3.0, -30.0],
    [3.0, -3.0, -30.0],
    [-3.0, 3.0, -30.0],
    [3.0, 3.0, -30.0],
    [0.0, -4.5, -30.0],
    [0.0, 4.5, -30.0],
]
# Sized for the MONEY SHOT (v2.4 critic: "provably invisible in hp_boom" —
# the first radii were half-buried at rest and flew over the camera).
# Comedy beats conservation of potato.
MASH_RADII = [0.84, 0.65, 0.74, 0.54, 0.95, 0.46]

# THE PALETTE RIDES THE HANDOFF (2026-08-29, measured the hard way): the
# Blender generator copies this table into handoff.json and prop_builder
# reads THAT copy, so a palette edit that skips the Blender rerun ships
# NOTHING — two emissive-nits bumps in a row silently missed serials 19-20
# this way, with `build.py prop` reporting success both times. Editing
# below means: textures -> Blender -> prop -> dist, always.
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
    # The monument skin (v2.2, 2026-08-29: "hyper-realistic ... notice the
    # texture and geometry of the original"). Metallic-1.0 stainless whose
    # albedo is the alloy's F0 (~0.57 linear; the family docstring has the
    # measurement note), panel-quilted by the arch_stainless family, and
    # given REAL reflections by dynamicCubemap — the same engine binding the
    # washer drum and centrifuge glazing shipped with. This deliberately
    # retires the v1 "creamy white drops the mirror" call: the mirror IS the
    # Gateway Arch. sRGB opt-in per the transfer-function law.
    f"{MOD_ID}_arch_steel": {
        "texture": {
            "family": "arch_stainless",
            "size": 2048,
            "normal_strength": 2.6,
            "srgb": True,
            # rough 0.30 (round-1 critic: the leg went "matte concrete" at
            # range) — a tighter reflection lobe keeps the sky gradient
            # alive once the mips have averaged the panel cant away.
            "params": {"base": [0.57, 0.58, 0.60], "rough": 0.30},
        },
        "color": [0.57, 0.58, 0.60, 1.0],
        "metallic": 1.0,
        "roughness": 0.30,
        # The arch is a swept tube whose windings are derived per face, but
        # double-siding is the pack's standing policy after an invisible ramp
        # and an invisible door leaf both shipped.
        "double_sided": True,
        "material": {"dynamicCubemap": True},
    },
    # The landing medallion top: machined stainless, coarse grain (a 8.4 m
    # plate is fabricated, not lathe-turned), mirror-bound like the arch so
    # the pad reads as one composition with the monument.
    f"{MOD_ID}_pad_steel": {
        "texture": {
            # honed_steel_disc, purpose-built for the medallion's polar UVs
            # (critic round 2: machined_steel's blotches sheared into "six
            # fat spiral arms ... marbled taffy" under the polar map). The
            # family draws the tool mark itself: ~120 fine concentric
            # grooves per tile, per-ring depth, whisper-level mottle.
            "family": "honed_steel_disc",
            "size": 1024,
            "normal_strength": 2.2,
            "srgb": True,
            # rough 0.52: at 0.30 the plate mirrored the sky into navy
            # lacquer (run 5), at 0.44 it still read as a blue pool at
            # range (run 10). A walked plate is grit-honed; the wide lobe
            # integrates sun as well as sky and reads STEEL-grey.
            "params": {"base": [0.50, 0.51, 0.53], "rough": 0.52},
        },
        "color": [0.50, 0.51, 0.53, 1.0],
        "metallic": 1.0,
        "roughness": 0.52,
        "material": {"dynamicCubemap": True},
    },
    # Foundation plinths under the legs: fine-finish cast concrete (the
    # "fine" mode exists precisely because the legacy pits read as Minecraft
    # chips at metric UV density).
    f"{MOD_ID}_plinth_concrete": {
        "texture": {
            "family": "concrete",
            "size": 1024,
            "params": {"fine": 1.0},
        },
        "color": [0.62, 0.60, 0.57, 1.0],
        "metallic": 0.0,
        "roughness": 0.82,
    },
    # The mash (v2.4): fluffy mashed potato for the detonation splatter
    # chunks. Cream-yellow with butter pools (the roughness map is where the
    # glisten lives) and russet skin flecks folded through. New additive
    # texture family — existing families' bytes cannot move (the
    # colossus_tire critic blessed exactly this extension pattern).
    f"{MOD_ID}_mash": {
        "texture": {
            "family": "mashed_potato",
            "size": 1024,
            "normal_strength": 2.4,
        },
        # v2.7 critic round: the old [0.87, 0.78, 0.52] read as dijon-khaki
        # — "crumpled tarps" at mid distance. Lightened ~25% with the green
        # pulled out of the yellow: pale butter-cream, like actual mash.
        "color": [0.97, 0.88, 0.70, 1.0],
        "metallic": 0.0,
        "roughness": 0.55,
    },
    # Polished architectural copper for the medallion's inlaid rings ("real
    # copper rings"): the stock worn-penny family, brightened and tightened
    # — an inlay in a maintained plaza floor, not a weathered fin.
    f"{MOD_ID}_copper": {
        "texture": {
            "family": "copper",
            "size": 512,
            "srgb": True,
            # The family's oxide/verd defaults are DISPLAY values (its own
            # comment arms this trap for "whoever sets srgb=True first" —
            # that is this entry). Everything here is authored linear.
            # Round-1 critic: "mottled gray-brown ... zero orange-pink
            # copper hue ... reads as weathered leather." Two causes, two
            # fixes: the base is now copper's MEASURED F0 (linear 0.955 /
            # 0.637 / 0.538 — the alloy's actual reflectance, notably more
            # green/blue than the hand-picked warm brown that preceded it),
            # and the new polish knob collapses the worn-penny weathering
            # swings that were crushing that tint. The reflection ladder,
            # measured across three shoots: 0.30 handed the band the sharp
            # blue sky ("dark grooves"), 0.40 blurred it to "dusty mauve"
            # (round 2) — under a blue sky a PURE metal can only ever show
            # sky-times-F0. rough 0.52 + metallic 0.85 is the game-art
            # answer: the 15% diffuse floor carries the base hue under sun.
            # And the HUE is the round-3 lesson, sampled off the frame, not
            # argued: the textbook F0 (0.955/0.637/0.538 linear) rendered
            # the band at sRGB (139,122,123) — G equal to B, i.e. ROSE.
            # A band a viewer NAMES as copper needs R > G > B with G-B
            # clearly positive (the critic's daylight reference: ~(184,
            # 115, 81)). This base decodes to exactly that family: linear
            # (0.50, 0.18, 0.09) -> sRGB ~(188, 117, 84).
            "params": {
                "base": [0.50, 0.18, 0.09],
                "rough": 0.52,
                "polish": 0.85,
                "oxide": [0.064, 0.022, 0.012],
                "verd": [0.12, 0.18, 0.15],
            },
        },
        "color": [0.50, 0.18, 0.09, 1.0],
        "metallic": 0.85,
        "roughness": 0.52,
        "material": {"dynamicCubemap": True},
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
        # Chosen by MEASUREMENT, third iteration (critic round 2026-08-29).
        # BNGP_waterfallsteam threw a 30 m column; BNGP_34's particle
        # (BNG_steam_light_exhaust, managedParticleData.json) grows
        # 0.1 -> 3.0 m over a 3 s life at a 1 ms ejection period — a
        # car-sized cumulus that swallowed the potato in every carry shot.
        # FIFTH iteration, and this one is chosen on the numbers that
        # actually failed: BNGP_46 read as "a water jet" (round 1), and
        # BNGP_48 — for all its billow — still stacked an OPAQUE core when
        # parked and laid a marching row at carry speed (round 2), because
        # both eject at a 1 ms period: a thousand puffs a second pile into
        # a solid column, and at 10 m/s each render-frame batch lands as a
        # separate evenly-spaced blob. BNGP_20 is BNG_smoke_white2: a 50 ms
        # period (20/s — the puffs OVERLAP into one translucent ribbon at
        # speed instead of a dotted line), peak particle alpha 0.199 (you
        # can see through the plume by construction), 0.8 -> 1.2 m growth,
        # 0.7 s +-0.4 s life, drag 4 with slight buoyancy — a soft, short,
        # flickering steam puff.
        # v2.3 (2026-08-29, "remove the wick, keep the potato smoking"): the
        # modelled fuse cord is gone; the wisp now rises off the scorched
        # CROWN of the tuber itself (SMOKE_RISE in the runtime), and it also
        # smokes while idle — with the ember lamp retired, the smoke IS the
        # "this thing is hot" invitation.
        "emitter": "BNGP_20",
        "position": [0.0, 0.0, 6.10],
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

# v2.7: very light steam off the landed mash chunks ("perhaps very light
# steam to come off the chunks?"). TWO BNGP_20 wisps per chunk — the same
# measured soft, short, see-through puff the potato's crown smoke uses
# (peak particle alpha 0.199, 50 ms ejection; the lightest steam voice in
# the managed set). One wisp per chunk was "functionally invisible at
# 85 m" (v2.7 critic round), so each chunk carries a pair, posed at
# wavering offsets on the crown for a fuller, living column while staying
# the light voice the brief asked for. They ship inactive at the chunks'
# under-plaza homes; stepMash activates and poses them onto a chunk only
# while it sits landed and steaming, and shuts them off when it melts.
for _steam_index, _steam_home in enumerate(MASH_HOMES, start=1):
    for _steam_slot in ("mash_steam_", "mash_steam_b"):
        EFFECTS[f"{_steam_slot}{_steam_index}"] = {
            "emitter": "BNGP_20",
            "position": list(_steam_home),
            "direction": [0.0, 0.0, 1.0],
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
    # Extra daylight between the roof and the potato's belly (v2.4, player
    # report: "it collides with the vehicle mesh"). The spawn OOBB is the
    # UNDEFORMED body, so roof rails, light bars and a deformed roof all
    # poke through a belly seated exactly on the box top; this rides above
    # them. The rhythm bounce below always lifts UP from this baseline.
    "carry_clearance_m": 0.30,
    # The carried potato hops ON the tick beat (v2.4, "bounce in a rhythm
    # according to how close it's to explode"): hop height grows from a
    # baseline 0.10 m by this much at full urgency, and the hops come
    # faster with the beat itself.
    "bounce_enabled": True,
    "bounce_amplitude_m": 0.35,
    # v2.4 game modes: "classic" hot potato; "hoarder" inverts the chase
    # (holding the potato SCORES — first to hoard_target_points is crowned,
    # a detonation halves your hoard); "pinball" passes on ANY touch with a
    # guaranteed hearty knockback — bumper-car chaos. v2.6 adds "protect"
    # (the reverse game: KEEP the potato — held seconds score toward the
    # same target, the AI mob hunts the carrier, and the boom costs nothing
    # because holding to the end is the whole point).
    "game_mode": "classic",
    "hoard_target_points": 120.0,
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
    # Anti-camping (v2.3): while the carrier dawdles below camp_speed_kmh the
    # fuse burns camp_burn_multiplier times faster. 1.0 = off (the shipped
    # default keeps the classic feel; the tuner is where the party mode is).
    "camp_burn_multiplier": 1.0,
    "camp_speed_kmh": 20.0,
    # Publish the fuse seconds to the HUD app. Off by default: the hidden
    # fuse read through the accelerating tick IS the design; this is the
    # party-host override.
    "show_countdown": False,
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
    # Comedy dial (v2.3): the receiver of an impact pass gets shoved along
    # the hit axis. 0 = off by default — it is a party option, not physics.
    "pass_knockback_mps": 0.0,
    # --- carrier handicap ------------------------------------------------
    # Dodging is easier than intercepting, so the holder gets a slipstream to
    # force chases to resolve. A uniform cluster velocity add: it can move
    # the car but by construction cannot strain a beam, so carrying stays
    # harmless. NEGATIVE values (v2.3, tuner range -6..8) flip it into a
    # ball-and-chain handicap: the potato is heavy and the mob is fast.
    "carrier_boost_mps2": 0.8,
    "carrier_boost_max_mps": 62.0,
    # --- cues (no numeric countdown, by design) --------------------------
    "cue_window_seconds": 30.0,
    "beep_slow_interval": 1.55,
    "beep_fast_interval": 0.13,
    "beep_pitch_rise": 0.85,
    "audio_enabled": True,
    # Master volume for every mod sound (tick loop and one-shot stingers).
    "audio_volume": 1.0,
    # How the tick tells time (v2.4, the hardcore ask): "escalating" is the
    # classic accelerating, rising cue; "steady" plays the hot-potato song
    # at constant rate and pitch — no audio tell at all that the end is
    # near (pair with the visual toggles below for full hardcore); "off"
    # silences the loop and keeps only the one-shot stingers.
    "tick_style": "escalating",
    # The horror cut-to-black (v2.4 audio critic, rank 1): in escalating
    # style the tick STOPS this many seconds before the boom, and the
    # beacon goes dark with it. Silence is the loudest sound in the mod.
    "silence_gap_seconds": 0.9,
    # The wisp off the scorched crown — the potato's own "I am hot" tell.
    "smoke_enabled": True,
    # The microwave-potato vent (v2.4): while the idle or returning potato
    # smokes, it periodically lets off a pitched-up air hiss. Stock one-shot
    # FMOD events only — the raw-file GE channel is recorded silent in this
    # repo's evidence chain.
    "steam_hiss_enabled": True,
    # The potato's own voice (v2.5, the acoustic brief): while carried it
    # WHISTLES — a synthesized aerodynamic orifice whistle (fundamental in
    # the 1.5–4 kHz band, fluttering skin-flap vibrato over a wet sputtering
    # hiss; authoring/make_whistle_audio.py) looping in the carrier's VM
    # beside the tick. In escalating tick style the pitch GLIDES DOWN as the
    # fuse runs out — the internal pressure subsiding — and the loop breaks
    # into a baked staccato sputter one-shot that dies into the silence gap;
    # steady style holds constant pitch (no tell). Its own channel: tick
    # style "off" does not silence it.
    "whistle_enabled": True,
    "whistle_volume": 1.0,
    # Visual escalation toggles (v2.4: "the visual, auditory, light effects
    # should be optional ... even the exploding and color changing").
    "beacon_enabled": True,
    "glow_ramp_enabled": True,
    "beacon_pulse_seconds": 0.11,
    "beacon_brightness": 2.6,
    "beacon_radius": 8.0,
    "beacon_ray_range": 26.0,
    "beacon_spin_rate": 3.0,
    # --- detonation ------------------------------------------------------
    # Master switch (v2.4): False = the fizzle. At fuse end the potato just
    # vents — a steam burst, a loud hiss, the holder is COOKED and out for
    # the round — and nothing is broken, crushed, burned or launched.
    "detonate_enabled": True,
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
    # Area shockwave (v2.3): every OTHER car inside blast_radius_m gets a
    # radial velocity shove with linear falloff — bystanders feel the boom
    # without taking damage (a uniform cluster add cannot strain a beam).
    "blast_radius_m": 22.0,
    "blast_push_mps": 9.0,
    "fire_seconds": 6.0,
    "round_idle_seconds": 5.0,
    # The splatter (v2.4, "spare no expense polygon wise"): six sculpted
    # mash chunks fly out of the detonation, land, sit steaming for
    # mash_seconds, then sink back under the plaza.
    "mash_enabled": True,
    "mash_seconds": 7.0,
    "mash_homes": MASH_HOMES,
    "mash_radii": MASH_RADII,
    # Multi-round scoring (v2.3): survive this many round wins and the HUD
    # crowns you Champion of the Arch (ledger resets, confetti doubles).
    "wins_to_champion": 3,
    # The crowning show (v2.4): the champion's name written across the sky
    # above the arch, letter by letter, as firework bursts drawn with a
    # pool of point lights. fireworks_base_z is authored geometry (the
    # burst line sits above the quarter-scale apex), not an option.
    "fireworks_enabled": True,
    "fireworks_base_z": round(ARCH_HEIGHT + 6.0, 2),
    # --- AI drivers (v2.5) -----------------------------------------------
    # "This game is meant to be multiplayer": with ai_enabled on, every
    # vehicle that is not the player's plays hot potato through the stock
    # vehicle AI (the police-pursuit machinery, lua/vehicle/ai.lua): the
    # carrier CHASES its nearest target to pass the potato on, everyone
    # else FLEES the carrier, and between rounds they hold position. Off by
    # default — commandeering every parked car is a party mode, not a
    # default.
    "ai_enabled": False,
    "ai_aggression": 1.0,
    "ai_speed_kmh": 90.0,
    # --- arena (v2.6) ----------------------------------------------------
    # The game happens INSIDE a circle around the medallion ("create a
    # radius that the AI stay within... about 100 yards"). Vehicles outside
    # it are not part of the game: they cannot receive the potato and the
    # AI never conscripts them; a conscripted AI car that strays out is
    # steered straight back to the arch (ai.setSlotTrafficTarget — the one
    # vehicle-AI export that takes raw world coordinates and needs no
    # navgraph; measured, lua/vehicle/ai.lua:5833, with a 0.5 s watchdog
    # the runtime refreshes). The halo is a translucent boundary wall drawn
    # per frame with the debug drawer while a round is live — the same
    # immediate-mode fence gameplay/sites/zone.lua renders zones with.
    "arena_enabled": True,
    "arena_radius_m": 91.4,  # 100 yards
    "arena_halo_enabled": True,
    # The arena magnet (v2.7): "a magnetic force that pulls vehicles back
    # into the center of the game radius if they drive outside". Carried by
    # the engine's own gravity wells — obj:setPlanets{x,y,z,radius,mass} is
    # the physics-side attractor funstuff.lua drives (positive mass pulls,
    # applied per node every physics step, no heartbeat to starve). The
    # runtime recomputes the well mass from each strayed car's CURRENT
    # distance so the pull is a constant arena_magnet_g everywhere outside
    # the ring; raw G*M/d^2 would fade exactly when a runaway needs it
    # most. Only game members are pulled — any vehicle (the player
    # included) seen inside the ring during a live round joins for that
    # round; bystanders beyond the line are never touched.
    "arena_magnet_enabled": True,
    "arena_magnet_g": 0.6,
    # --- damage (v2.6, "to make it more arcade like") --------------------
    # "normal": stock BeamNG consequences. "tires_safe": tires cannot pop
    # (wheel and pressure-group beams armored, beamstate.deflateTire
    # patched out — both halves are needed, the spike-strip path calls the
    # module field and the beam-break path calls a local upvalue).
    # "no_damage": every beam armored to math.huge strength and deform —
    # the exact semantic the jbeam loader gives authored-unbreakable beams
    # (lua/vehicle/jbeam/stage2.lua:28) — so arena cars bounce instead of
    # crumple. The detonation VICTIM always has armor stripped first: the
    # boom must land whatever the mode says.
    "damage_mode": "normal",
    # Pass-collision shield ("vehicles transferring the potato are
    # temporarily invincible when they collide"): both cars in an impact
    # transfer get full armor for this many seconds, then return to
    # whatever damage_mode wants. 0 = off.
    "transfer_shield_seconds": 3.0,
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
  "attach_sink", "attach_wobble", "carry_clearance_m",
  "bounce_enabled", "bounce_amplitude_m",
  "game_mode", "hoard_target_points",
  "pickup_radius", "pickup_height",
  "fuse_base_seconds", "fuse_sigma_seconds", "fuse_min_seconds",
  "fuse_max_seconds", "grace_seconds",
  "camp_burn_multiplier", "camp_speed_kmh", "show_countdown",
  "transfer_mode", "touch_margin", "radius_m", "impact_kmh",
  "tagback_immunity_seconds", "tagback_min_hold_seconds",
  "tagback_separation_m", "join_immunity_seconds", "min_players",
  "pass_knockback_mps",
  "carrier_boost_mps2", "carrier_boost_max_mps",
  "cue_window_seconds", "beep_slow_interval", "beep_fast_interval",
  "beep_pitch_rise", "audio_enabled", "audio_volume",
  "tick_style", "silence_gap_seconds",
  "smoke_enabled", "steam_hiss_enabled",
  "whistle_enabled", "whistle_volume",
  "ai_enabled", "ai_aggression", "ai_speed_kmh",
  "arena_enabled", "arena_radius_m", "arena_halo_enabled",
  "arena_magnet_enabled", "arena_magnet_g",
  "damage_mode", "transfer_shield_seconds",
  "beacon_enabled", "glow_ramp_enabled",
  "beacon_pulse_seconds",
  "beacon_brightness", "beacon_radius", "beacon_ray_range",
  "beacon_spin_rate",
  "detonate_enabled",
  "detonate_break", "detonate_crush", "detonate_fire", "detonate_launch_mps",
  "crush_dv_mps", "crush_min_z", "crush_inward",
  "blast_radius_m", "blast_push_mps", "fire_seconds",
  "round_idle_seconds",
  "mash_enabled", "mash_seconds", "mash_homes", "mash_radii",
  "wins_to_champion", "fireworks_enabled", "fireworks_base_z",
  "safety_enabled", "safety_extent_max",
}

-- Live, player-adjustable options. OPT is seeded from the shipped B table
-- and then overlaid from the settings file; ALL gameplay reads OPT, never B,
-- so a control change takes effect on the next tick without a rebuild.
local OPT = {}
local SETTINGS_PATH = "settings/ericrolph_hot_potato.json"

-- The HUD payload (hotPotatoGetStats). One potato prop per session, so a
-- module-level table the hooks can reach without a prop handle is honest;
-- publishStats refreshes it every frame the behaviour runs.
local LAST = {phase = "none", carrier = -1, countdown = -1, urgency = 0}
local OPTION_RANGE = {
  fuse_base_seconds = {10, 600}, fuse_sigma_seconds = {0, 60},
  fuse_min_seconds = {5, 600}, fuse_max_seconds = {5, 900},
  grace_seconds = {0, 30},
  camp_burn_multiplier = {1, 5}, camp_speed_kmh = {0, 120},
  show_countdown = "bool",
  game_mode = "enum", hoard_target_points = {10, 2000},
  transfer_mode = "enum", touch_margin = {0, 6}, radius_m = {1, 60},
  impact_kmh = {0, 120},
  tagback_immunity_seconds = {0, 30}, tagback_min_hold_seconds = {0, 30},
  tagback_separation_m = {0, 10}, join_immunity_seconds = {0, 30},
  min_players = {1, 16},
  pass_knockback_mps = {0, 15},
  pickup_radius = {2, 40}, pickup_height = {1, 20},
  -- Negative boost = the potato is a ball and chain (v2.3 handicap mode).
  carrier_boost_mps2 = {-6, 8}, carrier_boost_max_mps = {5, 200},
  -- The beep intervals steer ONE looping source through its pitch (rate and
  -- tone move together; see tickPitch), so the reachable interval is bounded
  -- by the loop length over the pitch clamp — extreme settings saturate
  -- rather than track exactly. beep_pitch_rise stacks a panic multiplier on
  -- the pitch as the cue window closes.
  cue_window_seconds = {1, 300}, beep_slow_interval = {0.05, 5},
  beep_fast_interval = {0.03, 5}, beep_pitch_rise = {0, 3},
  audio_enabled = "bool", audio_volume = {0, 2},
  tick_style = "enum", silence_gap_seconds = {0, 3},
  smoke_enabled = "bool", steam_hiss_enabled = "bool",
  whistle_enabled = "bool", whistle_volume = {0, 2},
  ai_enabled = "bool", ai_aggression = {0.3, 2}, ai_speed_kmh = {20, 200},
  arena_enabled = "bool", arena_radius_m = {20, 500},
  arena_halo_enabled = "bool",
  arena_magnet_enabled = "bool", arena_magnet_g = {0.1, 2.5},
  damage_mode = "enum", transfer_shield_seconds = {0, 10},
  beacon_enabled = "bool", glow_ramp_enabled = "bool",
  bounce_enabled = "bool", bounce_amplitude_m = {0, 1.5},
  carry_clearance_m = {0, 3},
  detonate_enabled = "bool",
  detonate_break = "bool", detonate_crush = "bool", detonate_fire = "bool",
  detonate_launch_mps = {0, 80},
  blast_radius_m = {0, 80}, blast_push_mps = {0, 40},
  mash_enabled = "bool", mash_seconds = {1, 30},
  wins_to_champion = {1, 20}, fireworks_enabled = "bool",
  -- "Every gameplay number is a live option" (DESIGN §11) was false until
  -- the critic counted (2026-08-29): the crush, fire, pacing, attach and
  -- beacon numbers were unreachable. The beacon_* values are read at
  -- ensureBeacon time, so a live change lands on the next prop reset.
  crush_dv_mps = {1, 30}, crush_min_z = {0, 3}, crush_inward = {0, 2},
  fire_seconds = {0, 30}, round_idle_seconds = {0, 60},
  attach_sink = {0, 1}, attach_wobble = {0, 0.5},
  spin_rate = {0, 5}, bob_amplitude = {0, 2}, bob_rate = {0, 10},
  beacon_brightness = {0, 20}, beacon_radius = {1, 60},
  beacon_ray_range = {1, 120}, beacon_pulse_seconds = {0.02, 2},
  beacon_spin_rate = {0, 20},
  safety_enabled = "bool", safety_extent_max = {5, 200},
}

-- The legal values behind every "enum" above — coerceOption validates
-- against this table and the schema hook serves it, so the UI app's
-- dropdowns and the clamp can never drift apart.
local OPTION_ENUM = {
  transfer_mode = {"touch", "radius"},
  tick_style = {"escalating", "steady", "off"},
  game_mode = {"classic", "hoarder", "pinball", "protect"},
  damage_mode = {"normal", "tires_safe", "no_damage"},
}

-- ONE-SHOT stock FMOD event paths (grepped out of the shipped Lua tree, not
-- invented). Engine.Audio.playOnce is safe for these and ONLY these: a
-- playOnce instance has no stop handle, so a LOOPING event leaks an
-- immortal instance per call. v1 ticked the game's REVERSE BEEP that way
-- and the player filmed the wreckage (2026-08-29): beeps at 0.45-1.1 s
-- spacing against an authored 1.55 s interval — one new looping beeper per
-- tick, stacking — and the pile kept beeping after the mod was deleted.
-- The tick therefore rides the CARRIER's own VM below (TICK_START); these
-- four are single-sample UI/failure stingers.
local SFX_PASS = "event:>UI>Career>Drift_Combo_1x"
local SFX_PICKUP = "event:>UI>Missions>Info_Open"
local SFX_BOOM = "event:>Vehicle>Failures>engine_explode"
local SFX_WIN = "event:>UI>Career>EndScreen_Receive_XP"
-- The steam vent (v2.4). Both are one-shot events (played by the game via
-- obj:playSFXOnce — airbrakes.lua:38, compressor.lua's purge): a truck air
-- brake PSSHT and the air-dryer purge, pitched UP into a potato-sized
-- whistle of escaping steam. The raw-file GE playOnce route stays banned
-- (recorded silent in this repo's evidence chain).
local SFX_HISS = "event:>Vehicle>Pneumatics>Air_Brakes"
local SFX_HISS_ALT = "event:>Vehicle>Pneumatics>Air_Dryer_Purge"

-- --------------------------------------------------------------------------
-- The fuse tick: audio mechanism v3, in the CARRIER's vehicle VM.
--
-- obj:createSFXSource is an obj method — the source must live in SOME
-- vehicle's VM, and the carrier's is the right one: the loop is positional
-- ON the moving car (an approaching carrier beeps toward you, with doppler,
-- for free), and it is self-limiting on every path playOnce leaked through.
-- A carrier reset wipes its VM; a despawn deletes the object; the explicit
-- TICK_STOP below covers transfer, detonation, round end, prop reset and
-- prop teardown (behavior.cleanup). The shipped ogg is a 1.3 s LOOP (beep +
-- fuse sizzle, authoring/make_tick_audio.py), so ONE source serves the
-- whole round: setVolumePitch scales playback rate and tone together,
-- which IS the accelerating, rising cue — no per-beep calls to leak.
--
-- Node 0 is not a resolved emitter node (spin_launch's law: its node 0 sat
-- 76 m away on a plinth corner) — but this source only has to sit ON the
-- carrier, and node 0 of any VEHICLE does, within its own body length.
-- --------------------------------------------------------------------------
local TICK_OGG = "vehicles/ericrolph_hot_potato/sound/ericrolph_hot_potato_tick.ogg"
local TICK_LOOP_SECONDS = 1.3
local TICK_PITCH_MIN = 0.6
local TICK_PITCH_MAX = 3.4  -- rate ceiling from interval mapping alone
local TICK_PITCH_CAP = 5.0  -- absolute ceiling after the pitch_rise boost

-- The potato's vertical half-extent (spec POTATO_SEMI_Z) and how high above
-- the potato's centre the smoke wisp is posed. v2.2 posed it at a modelled
-- fuse tip 1.12 up; v2.3 removed the wick ("remove the wick, keep the potato
-- smoking"), so the wisp now births just inside the scorched crown and rolls
-- off the skin.
local POTATO_BELLY = 0.58
local SMOKE_RISE = 0.50

-- START uses the stock loop-restart recipe (sounds.lua playSoundSkipAI:
-- setVolume + cutSFX + playSFX): the cut kills any zombie voice from a lost
-- or failed stop BEFORE the play, so a restart self-heals the audio state
-- instead of stacking on top of it.
local TICK_START = [[pcall(function()
  local S = rawget(_G, "ericrolph_hot_potato_tick")
  if not S then S = {} rawset(_G, "ericrolph_hot_potato_tick", S) end
  if S.id == nil then
    local ok, id = pcall(function()
      return obj:createSFXSource(%q, "AudioDefaultLoop3D", "erhp_tick", 0)
    end)
    if ok and id ~= nil then S.id = id end
  end
  if S.id ~= nil then
    pcall(function() obj:setVolumePitch(S.id, %.3f, %.3f) end)
    if not S.on then
      S.on = true
      pcall(function() obj:cutSFX(S.id) end)
      pcall(function() obj:playSFX(S.id) end)
    end
  end
end)]]

local TICK_SET = [[pcall(function()
  local S = rawget(_G, "ericrolph_hot_potato_tick")
  if S and S.id ~= nil and S.on then
    pcall(function() obj:setVolumePitch(S.id, %.3f, %.3f) end)
  end
end)]]

-- STOP is belt and braces, and UNCONDITIONAL on S.on (a stale S.on=false
-- must never veto silencing a voice that is audibly still playing — the
-- 2026-08-29 player report: the sizzle persisted after the detonation).
-- Every stock loop is an FMOD event; this is the pack's only raw-ogg loop,
-- so stopSFX alone is unproven — the volume-0 write is the guarantee (the
-- pitch writes on this same source are proven audible live), stopSFX is
-- the polite stop, cutSFX the immediate kill.
local TICK_STOP = [[pcall(function()
  local S = rawget(_G, "ericrolph_hot_potato_tick")
  if S and S.id ~= nil then
    S.on = false
    pcall(function() obj:setVolume(S.id, 0) end)
    pcall(function() obj:stopSFX(S.id) end)
    pcall(function() obj:cutSFX(S.id) end)
  end
end)]]

-- --------------------------------------------------------------------------
-- The steam whistle (v2.5, the acoustic brief): the potato's own voice while
-- it is carried, riding the SAME proven channel as the tick — a raw-ogg
-- source in the carrier's VM. Two baked assets carry the acoustics the brief
-- specifies (authoring/make_whistle_audio.py): a seamless whistle LOOP
-- (2.1 kHz fundamental, 27 Hz skin-flap flutter, wet sputtering hiss bed)
-- whose live pitch write gives the downward glissando as the pressure runs
-- out, and a one-shot SPUTTER (glissando collapsing into staccato chirps and
-- wheezes, decaying to true silence) that plays once as the fuse enters its
-- final seconds and dies into the horror-cut silence gap. The sputter source
-- uses AudioDefault3D — the stock NON-looping description the game's own
-- crash and glass one-shots use (gameengine.zip
-- art/datablocks/audioProfiles.datablocks.json) — so cutSFX+playSFX fires it
-- once with no loop to leak.
-- --------------------------------------------------------------------------
local WHISTLE_OGG = "vehicles/ericrolph_hot_potato/sound/ericrolph_hot_potato_whistle.ogg"
local SPUTTER_OGG = "vehicles/ericrolph_hot_potato/sound/ericrolph_hot_potato_sputter.ogg"
local SPUTTER_SECONDS = 2.8

local WHISTLE_START = [[pcall(function()
  local S = rawget(_G, "ericrolph_hot_potato_whistle")
  if not S then S = {} rawset(_G, "ericrolph_hot_potato_whistle", S) end
  if S.id == nil then
    local ok, id = pcall(function()
      return obj:createSFXSource(%q, "AudioDefaultLoop3D", "erhp_whistle", 0)
    end)
    if ok and id ~= nil then S.id = id end
  end
  if S.id ~= nil then
    pcall(function() obj:setVolumePitch(S.id, %.3f, %.3f) end)
    if not S.on then
      S.on = true
      pcall(function() obj:cutSFX(S.id) end)
      pcall(function() obj:playSFX(S.id) end)
    end
  end
end)]]

local WHISTLE_SET = [[pcall(function()
  local S = rawget(_G, "ericrolph_hot_potato_whistle")
  if S and S.id ~= nil and S.on then
    pcall(function() obj:setVolumePitch(S.id, %.3f, %.3f) end)
  end
end)]]

local WHISTLE_STOP = [[pcall(function()
  local S = rawget(_G, "ericrolph_hot_potato_whistle")
  if S and S.id ~= nil then
    S.on = false
    pcall(function() obj:setVolume(S.id, 0) end)
    pcall(function() obj:stopSFX(S.id) end)
    pcall(function() obj:cutSFX(S.id) end)
  end
end)]]

-- One-shot: always cut then play, so a re-trigger restarts cleanly and a
-- finished instance never blocks the next.
local SPUTTER_PLAY = [[pcall(function()
  local S = rawget(_G, "ericrolph_hot_potato_sputter")
  if not S then S = {} rawset(_G, "ericrolph_hot_potato_sputter", S) end
  if S.id == nil then
    local ok, id = pcall(function()
      return obj:createSFXSource(%q, "AudioDefault3D", "erhp_sputter", 0)
    end)
    if ok and id ~= nil then S.id = id end
  end
  if S.id ~= nil then
    pcall(function() obj:setVolumePitch(S.id, %.3f, %.3f) end)
    pcall(function() obj:cutSFX(S.id) end)
    pcall(function() obj:playSFX(S.id) end)
  end
end)]]

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
    local legal = OPTION_ENUM[key] or {}
    for _, candidate in ipairs(legal) do
      if value == candidate then return value end
    end
    return nil, "expected one of: " .. table.concat(legal, ", ")
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
    b.lastDelta = 0
    if (dtSim or 0) > 0 then
      b.now = b.now + delta
      b.lastDelta = delta
    end
    return
  end
  b.lastDelta = (dtSim or 0) / 3.0
  b.now = b.now + b.lastDelta
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

local function playSound(event, pitch, volume, worldPos)
  -- ONE-SHOT events only (see the SFX_* block): playOnce has no stop handle.
  -- worldPos is optional and rides the stock positional recipe
  -- (gasStations.lua:158: playOnce with a position table entry).
  if not OPT.audio_enabled then return end
  local scaled = (volume or 1.0) * (OPT.audio_volume or 1.0)
  if scaled <= 0 then return end
  pcall(function()
    local params = {
      volume = scaled,
      pitch = pitch or 1.0,
      fadeInTime = -1,
      fadeOutTime = -1,
    }
    if worldPos then
      params.position = vec3(worldPos.x, worldPos.y, worldPos.z)
    end
    Engine.Audio.playOnce("AudioGui", event, params)
  end)
end

-- The microwave-potato vent: while the potato smokes unattended (idle at
-- the arch, or on its return flight) it periodically lets off a pitched-up
-- air hiss. Jittered period, two source events, random pitch and volume —
-- four axes of variation so it never reads as a loop (v2.4 audio critic).
-- Carried potatoes stay quiet here: the tick loop's sizzle already speaks
-- for the fuse on the carrier.
local function stepHiss(state, worldPos)
  local b = state.behavior
  if not (OPT.smoke_enabled and OPT.steam_hiss_enabled) then return end
  if (b.nextHissAt or 0) > b.now then return end
  b.nextHissAt = b.now + 2.4 + math.random() * 2.6
  local event = math.random() < 0.7 and SFX_HISS or SFX_HISS_ALT
  playSound(event, 1.5 + math.random() * 0.45, 0.35 + math.random() * 0.25,
    worldPos)
end

-- interval -> loop pitch. Pitch scales playback rate and tone as one knob,
-- so the beep interval options map through the authored loop length; the
-- clamp bounds the reachable interval to [LOOP/max, LOOP/min].
local function tickPitch(interval)
  if interval <= 0 then return TICK_PITCH_MAX end
  return clampNumber(TICK_LOOP_SECONDS / interval, TICK_PITCH_MIN, TICK_PITCH_MAX)
end

-- Stop the loop wherever it last played. Safe on every path: a gone or
-- reset carrier simply no-ops (its VM died with the source in it).
local function silenceTick(state)
  local b = state.behavior
  local id = b.tickOn
  b.tickOn = nil
  b.tickLastSent = nil
  if not id then return end
  local vehicle = exactVehicle(id)
  if not vehicle then return end
  pcall(function() vehicle:queueLuaCommand(TICK_STOP) end)
end

local function driveTick(state, vehicle, volume, pitch)
  if not OPT.audio_enabled then
    silenceTick(state)
    return
  end
  volume = volume * (OPT.audio_volume or 1.0)
  local b = state.behavior
  local id = vehicle:getId()
  if b.tickOn ~= id then
    if b.tickOn then silenceTick(state) end
    b.tickOn = id
    b.tickLastSent = {volume, pitch}
    pcall(function()
      vehicle:queueLuaCommand(string.format(TICK_START, TICK_OGG, volume, pitch))
    end)
    return
  end
  -- Throttle: queueLuaCommand crosses the GE->vehicle boundary every call,
  -- and sixty sub-percent pitch nudges a second are noise in both VMs.
  local last = b.tickLastSent
  if last
    and math.abs(last[1] - volume) < 0.02
    and math.abs(last[2] - pitch) < 0.02 then
    return
  end
  b.tickLastSent = {volume, pitch}
  pcall(function()
    vehicle:queueLuaCommand(string.format(TICK_SET, volume, pitch))
  end)
end

-- The whistle mirrors the tick's lifecycle exactly: one loop source in the
-- carrier's VM, moved by id change, throttled writes, belt-and-braces stop.
local function silenceWhistle(state)
  local b = state.behavior
  local id = b.whistleOn
  b.whistleOn = nil
  b.whistleLastSent = nil
  if not id then return end
  local vehicle = exactVehicle(id)
  if not vehicle then return end
  pcall(function() vehicle:queueLuaCommand(WHISTLE_STOP) end)
end

local function driveWhistle(state, vehicle, volume, pitch)
  if not (OPT.audio_enabled and OPT.whistle_enabled) then
    silenceWhistle(state)
    return
  end
  volume = volume * (OPT.audio_volume or 1.0) * (OPT.whistle_volume or 1.0)
  local b = state.behavior
  local id = vehicle:getId()
  if b.whistleOn ~= id then
    if b.whistleOn then silenceWhistle(state) end
    b.whistleOn = id
    b.whistleLastSent = {volume, pitch}
    pcall(function()
      vehicle:queueLuaCommand(string.format(WHISTLE_START, WHISTLE_OGG, volume, pitch))
    end)
    return
  end
  local last = b.whistleLastSent
  if last
    and math.abs(last[1] - volume) < 0.02
    and math.abs(last[2] - pitch) < 0.02 then
    return
  end
  b.whistleLastSent = {volume, pitch}
  pcall(function()
    vehicle:queueLuaCommand(string.format(WHISTLE_SET, volume, pitch))
  end)
end

-- The staccato finish: fire the baked sputter one-shot in this vehicle's VM.
local function playSputter(state, vehicle, volume, pitch)
  if not (OPT.audio_enabled and OPT.whistle_enabled) then return end
  volume = volume * (OPT.audio_volume or 1.0) * (OPT.whistle_volume or 1.0)
  pcall(function()
    vehicle:queueLuaCommand(
      string.format(SPUTTER_PLAY, SPUTTER_OGG, volume, pitch))
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
      -- b.out is PER-ROUND elimination (cleared by endRound); b.quarantined
      -- is exploded-node physics and outlives rounds (cleared on prop
      -- init/reset only).
      if not b.out[id] and not (b.quarantined and b.quarantined[id]) then
        found[#found + 1] = {id = id, vehicle = vehicle}
      end
    end
  end
  return found
end

-- --------------------------------------------------------------------------
-- v2.6 lives in ONE table local, by necessity: Lua caps a function at 200
-- local variables and the generated runtime's main chunk stood at 198
-- before this round — fifteen new `local function`s compiled in lupa (and
-- would have compiled in LuaJIT) to "too many local variables". A table
-- field per helper costs zero locals; every future family should follow
-- this shape rather than spend the last two slots.
--
-- The arena: the game happens inside a circle around the medallion.
-- Distance is horizontal — a car on the arch ramp is as "in" as one on the
-- plaza — and every consumer (transfer eligibility, AI conscription and
-- containment, the halo) reads the same helpers so the circle can never
-- drift between them.
--
-- The damage armor ("to make it more arcade like"): one idempotent
-- vehicle-side command, three modes:
--   "full"  — every beam's strength AND deform raised to math.huge: the
--             exact semantic the jbeam loader gives authored-unbreakable
--             beams (lua/vehicle/jbeam/stage2.lua:28 measured), so the car
--             bounces instead of crumpling. Also arms the tire patch.
--   "tires" — only wheel and pressure-group beams armored, plus the
--             beamstate.deflateTire nop. BOTH halves are required: the
--             spike-strip path (wheels.lua:321) calls the module field,
--             the beam-break path (beamstate.lua:822) calls a local
--             upvalue that only unbreakable wheel beams can dodge.
--   "none"  — everything restored from v.data's authored values (they
--             survive the physics-side override untouched) and the
--             deflateTire patch removed.
-- No engine invulnerability flag exists anywhere in stock 0.38/0.39 Lua —
-- this measured beam-armor recipe is the real mechanism. GE-side truth
-- lives in b.armorApplied ({id -> "full"|"tires"|"none"}); the command is
-- idempotent, so a resend is always safe.
-- --------------------------------------------------------------------------
local v26 = {}

-- BeamMP synchronization lives in one table local because this generated
-- main chunk is already pressed against Lua's 200-local ceiling. The
-- downloaded Client resource loads a thin transport adapter; this table
-- owns only gameplay-mode decisions and canonical vehicle-id translation.
-- Outside an MP session every helper deliberately reduces to the original
-- single-client behavior.
local Sync = {}

Sync.PROTOCOL = 1
Sync.GAME = "hot_potato"
Sync.PUBLISH_SECONDS = 0.20

function Sync.network()
  if extensions and extensions.MPCoreNetwork then
    return extensions.MPCoreNetwork
  end
  return rawget(_G, "MPCoreNetwork")
end

function Sync.isMPSession()
  local network = Sync.network()
  if not network or type(network.isMPSession) ~= "function" then return false end
  local ok, active = pcall(network.isMPSession)
  return ok and active == true
end

function Sync.vehicles()
  if extensions and extensions.MPVehicleGE then return extensions.MPVehicleGE end
  return rawget(_G, "MPVehicleGE")
end

function Sync.sidForGameId(gameId)
  local api = Sync.vehicles()
  if not api or type(api.getServerVehicleID) ~= "function" then return nil end
  local ok, sid = pcall(api.getServerVehicleID, gameId)
  if ok and type(sid) == "string" and sid:match("^%d+%-%d+$") then return sid end
  return nil
end

function Sync.gameIdForSid(sid)
  if type(sid) ~= "string" or not sid:match("^%d+%-%d+$") then return nil end
  local api = Sync.vehicles()
  if not api or type(api.getGameVehicleID) ~= "function" then return nil end
  local ok, gameId = pcall(api.getGameVehicleID, sid)
  if ok and integer(gameId) and gameId >= 0 then return gameId end
  return nil
end

function Sync.canMutate(vehicle)
  if not Sync.isMPSession() then return true end
  if not vehicle then return false end
  local api = Sync.vehicles()
  if not api or type(api.isOwn) ~= "function" then return false end
  local okId, gameId = pcall(function() return vehicle:getId() end)
  if not okId or not integer(gameId) then return false end
  local ok, owned = pcall(api.isOwn, gameId)
  return ok and owned == true
end

function Sync.transport()
  if extensions then return extensions.ericrolphHotPotatoBeamMP end
  return nil
end

function Sync.isAuthority(state)
  local mode = state.behavior.sync and state.behavior.sync.mode or "standalone"
  return mode == "standalone" or mode == "authority"
end

function Sync.isReplica(state)
  local mode = state.behavior.sync and state.behavior.sync.mode or "standalone"
  return mode == "pending" or mode == "follower"
end

v26.ARMOR_SET = [[pcall(function()
  local S = rawget(_G, "ericrolph_hot_potato_armor")
  if not S then S = {} rawset(_G, "ericrolph_hot_potato_armor", S) end
  local mode = %q
  if S.mode == mode then return end
  S.mode = mode
  if beamstate then
    if mode == "none" then
      if S.deflate then beamstate.deflateTire = S.deflate S.deflate = nil end
    elseif S.deflate == nil and beamstate.deflateTire then
      S.deflate = beamstate.deflateTire
      beamstate.deflateTire = function() end
    end
  end
  if not (v and v.data and v.data.beams and obj and obj.setBeamStrength) then
    return
  end
  for _, b in pairs(v.data.beams) do
    local armored = mode == "full" or (mode == "tires"
      and (b.wheelID ~= nil or b.pressureGroupId ~= nil))
    if armored then
      obj:setBeamStrength(b.cid, math.huge)
      if mode == "full" and obj.setBeamDeform then
        obj:setBeamDeform(b.cid, math.huge)
      end
    else
      obj:setBeamStrength(b.cid, b.beamStrength or math.huge)
      if obj.setBeamDeform then
        obj:setBeamDeform(b.cid, b.beamDeform or math.huge)
      end
    end
  end
end)]]

function v26.arenaDistance(state, position)
  local centre = toWorldPoint(state, B.pad_center)
  local dx = position.x - centre.x
  local dy = position.y - centre.y
  return math.sqrt(dx * dx + dy * dy)
end

function v26.insideArena(state, position)
  if not OPT.arena_enabled then return true end
  return v26.arenaDistance(state, position) <= OPT.arena_radius_m
end

-- The arena halo: a translucent boundary wall drawn EVERY FRAME with the
-- debug drawer while a round is running ("a see through halo surrounding
-- the game arena radius when the game starts that goes away when the game
-- ends"). Immediate-mode drawTriSolid quads, both windings so the wall
-- reads from inside and outside — the exact fence recipe the game's own
-- gameplay/sites/zone.lua:414-434 renders zones with. Immediate mode means
-- there is no scene object to leak: on any frame this does not run, the
-- halo simply is not there. 48 segments, 7 m tall, alpha 22/255.
function v26.drawArenaHalo(state)
  local b = state.behavior
  if not (OPT.arena_enabled and OPT.arena_halo_enabled) then return end
  if b.phase ~= "live" and b.phase ~= "boom" then return end
  if not debugDrawer then return end
  pcall(function()
    local centre = toWorldPoint(state, B.pad_center)
    local radius = OPT.arena_radius_m
    local tint = color(255, 150, 60, 22)
    local step = 2.0 * math.pi / 48
    for i = 0, 47 do
      local a0, a1 = i * step, (i + 1) * step
      local x0, y0 = centre.x + radius * math.cos(a0), centre.y + radius * math.sin(a0)
      local x1, y1 = centre.x + radius * math.cos(a1), centre.y + radius * math.sin(a1)
      local lo0 = vec3(x0, y0, centre.z - 1.0)
      local hi0 = vec3(x0, y0, centre.z + 7.0)
      local lo1 = vec3(x1, y1, centre.z - 1.0)
      local hi1 = vec3(x1, y1, centre.z + 7.0)
      debugDrawer:drawTriSolid(lo0, hi0, hi1, tint)
      debugDrawer:drawTriSolid(hi1, lo1, lo0, tint)
      debugDrawer:drawTriSolid(hi0, lo0, hi1, tint)
      debugDrawer:drawTriSolid(lo1, hi1, lo0, tint)
    end
  end)
end

-- desiredArmor is the ONE place the mode and the transfer shield are
-- weighed against each other.
function v26.desiredArmor(state, id)
  if OPT.damage_mode == "no_damage" then return "full" end
  local b = state.behavior
  if b.shield and (b.shield[id] or 0) > b.now then return "full" end
  if OPT.damage_mode == "tires_safe" then return "tires" end
  return "none"
end

function v26.sendArmor(state, vehicle, mode)
  -- BeamMP synchronizes the owning vehicle outward. Mutating a remote proxy
  -- here is both redundant and liable to be overwritten by its owner.
  if not Sync.canMutate(vehicle) then return end
  local b = state.behavior
  b.armorApplied = b.armorApplied or {}
  b.armorApplied[vehicle:getId()] = mode
  pcall(function()
    vehicle:queueLuaCommand(string.format(v26.ARMOR_SET, mode))
  end)
end

-- Restore stock damage everywhere the mod touched. Runs on prop init/reset
-- and at teardown — armor must never outlive the mod that applied it.
function v26.armorRelease(state)
  local b = state.behavior
  if not b.armorApplied then return end
  for id, mode in pairs(b.armorApplied) do
    if mode ~= "none" then
      local vehicle = exactVehicle(id)
      if vehicle and Sync.canMutate(vehicle) then
        pcall(function()
          vehicle:queueLuaCommand(string.format(v26.ARMOR_SET, "none"))
        end)
      end
    end
  end
  b.armorApplied = nil
  b.shield = nil
end

-- The armor sweep (0.7 s): settles damage_mode changes and expired
-- transfer shields for everyone still on the field.
function v26.stepArmor(state)
  local b = state.behavior
  if (b.armorNext or 0) > b.now then return end
  b.armorNext = b.now + 0.7
  b.armorApplied = b.armorApplied or {}
  for _, entry in ipairs(roster(state)) do
    local desired = v26.desiredArmor(state, entry.id)
    local current = b.armorApplied[entry.id]
    -- nil -> "none" is a car the mod never touched: leave its VM alone.
    if current ~= desired and not (current == nil and desired == "none") then
      v26.sendArmor(state, entry.vehicle, desired)
    end
  end
end

local function poseEffectAt(state, name, worldPos)
  local effect = state.effects[name]
  if not effect or not finiteVector3(worldPos) then return end
  -- Keep the authored emitter direction. Identity rotation aims the
  -- emitter along its default axis: the live run filmed BNGP_34 as a 30 m
  -- HORIZONTAL steam jet hanging beside the carrier (2026-08-29). This is
  -- the same recipe synchronizeInstallation uses for the parked pose.
  local rotation = quat(0, 0, 0, 1)
  local spec = EFFECT_SPECS[name]
  if spec and spec.direction then
    local direction = state.modelRotation * spec.direction
    direction:normalize()
    rotation = vec3(0, 0, 1):getRotationTo(direction)
  end
  pcall(function()
    effect:setPosRot(worldPos.x, worldPos.y, worldPos.z,
      rotation.x, rotation.y, rotation.z, rotation.w)
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
          light:setField("isEnabled", 0, entry.enabled or "0")
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
  -- The beacon master switch (v2.4): a disabled beacon can only ever be
  -- told "off", whatever the cue logic asked for.
  if not OPT.beacon_enabled then lit = false end
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

-- The internal light gets PHYSICALLY hotter (v2.4: "like it glows hotter
-- and hotter"): a blackbody-style ramp on the carrier glow — deep ember
-- red rising through orange toward yellow-white as the fuse closes, with
-- brightness climbing in step. Real incandescence brightens AND whitens
-- together; that coupling is what sells "hot" rather than "colour cycle".
-- Writes are throttled: sixty setField calls a second on a static value
-- are noise.
local function glowHeat(state, urgency)
  local b = state.behavior
  if not (OPT.glow_ramp_enabled and OPT.beacon_enabled) then return end
  local glow = state.effects.beacon_glow
  if not glow then return end
  if math.abs(urgency - (b.glowLast or -1)) < 0.02
    and (b.glowNext or 0) > b.now then
    return
  end
  b.glowLast = urgency
  b.glowNext = b.now + 0.12
  local green = 0.30 + 0.56 * urgency
  local blue = 0.05 + 0.45 * urgency
  local bright = OPT.beacon_brightness * (0.7 + 1.7 * urgency)
  pcall(function()
    glow:setField("color", 0,
      string.format("1 %.3f %.3f 1", green, blue))
    glow:setField("brightness", 0, string.format("%.2f", bright))
  end)
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
  -- Track where the potato IS: the return flight (v2.4) starts from the
  -- last posed position, whatever path ended the round.
  state.behavior.potatoAt = vec3(worldPos.x, worldPos.y, worldPos.z)
  setPartPose(state, "potato", authored - B.potato_home, pose)
end

-- Pose any named part at a world position/rotation, given its authored
-- pivot — the same origin/modelRotation inversion posePotato does for the
-- tuber. The mash chunks fly through here.
local function posePartWorld(state, part, pivot, worldPos, worldRotation)
  local ex, ey, ez = authoredAxes(state)
  local offset = worldPos - state.origin
  local authored = vec3(offset:dot(ex), offset:dot(ey), offset:dot(ez))
  local pose = quat(0, 0, 0, 1)
  if worldRotation then
    local m = state.modelRotation
    pose = worldRotation * quat(-m.x, -m.y, -m.z, m.w)
  end
  setPartPose(state, part, authored - pivot, pose)
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
  -- Roof top = OOBB centre + ONE half-height; the potato's own belly then
  -- sits under its centre. The first cut used height * 2.0 (centre + a FULL
  -- height = roof + half a car) and the potato hovered on 0.3-0.4 m of
  -- daylight in every carry shot, on two body styles — the critic round's
  -- D1, 2026-08-29. attach_sink absorbs the OOBB's padding so the belly
  -- visually seats on the paint.
  -- carry_clearance_m rides on top (v2.4, "it collides with the vehicle
  -- mesh"): the OOBB is the UNDEFORMED body, so roof rails and a crumpled
  -- roof line both poke through a belly seated exactly on the box top.
  local lift = extents.height + POTATO_BELLY - OPT.attach_sink
    + OPT.carry_clearance_m
  -- The rhythm bounce (v2.4): a parabolic hop launched ON each tick beat
  -- by updateFuseCues — the potato jumps with its own countdown, higher
  -- and faster as the fuse closes. Always upward from the clearance
  -- baseline, never into the roof. The old free-running wobble stays
  -- underneath as idle body language.
  local wobble = math.sin((b.now or 0) * 5.3) * OPT.attach_wobble
  if OPT.bounce_enabled and b.hopStart then
    local progress = (b.now - b.hopStart) / math.max(b.hopDur or 0.4, 0.05)
    if progress >= 0 and progress <= 1.0 then
      wobble = wobble + (b.hopAmp or 0.1) * 4.0 * progress * (1.0 - progress)
    end
  end
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

local function subjectName(state, id)
  local b = state.behavior
  b.names = b.names or {}
  if b.names[id] then return b.names[id] end
  local label = "car " .. tostring(id)
  local vehicle = exactVehicle(id)
  if vehicle then
    local ok, model = pcall(function() return vehicle:getJBeamFilename() end)
    if ok and type(model) == "string" and model ~= "" then label = model end
  end
  b.names[id] = label
  return label
end

local function publishStats(state)
  -- getSystemState exposes state.behavior.stats verbatim, which is the only
  -- generic channel out of a behaviour. -1 rather than nil because a nil
  -- field simply vanishes from the table.
  local b = state.behavior
  local remaining = b.fuseEnds and math.max(0, b.fuseEnds - b.now) or -1
  local sync = b.sync or {
    mode = "standalone", status = "single-player", revision = 0,
  }
  local carrierSid = b.carrierSid
    or (b.carrier and Sync.sidForGameId(b.carrier))
  b.stats = {
    carrier = b.carrier or -1,
    carrier_sid = carrierSid or "",
    fuse_remaining = remaining,
    field = b.fieldPeak or 0,
    eliminated = b.outCount or 0,
    transfers = b.transfers or 0,
    mode = OPT.transfer_mode,
    sync_mode = sync.mode,
    sync_status = sync.status,
    sync_arena = sync.arena or "",
    sync_epoch = sync.epoch or 0,
    sync_revision = sync.revision or 0,
    options_writable = Sync.optionsWritable(),
    -- v2.7: the show's stage, so the live gate can time its cameras
    -- against the letters.
    fw_stage = b.fw and b.fw.stage or "",
  }
  -- The HUD payload. The numeric countdown is GATED behind show_countdown
  -- (the hidden fuse is the design; the option is the party-host override),
  -- but urgency ships always: it reveals nothing the accelerating tick is
  -- not already broadcasting in everyone's ears.
  LAST.phase = b.phase or "idle"
  LAST.carrier = b.carrier or -1
  LAST.carrier_sid = carrierSid or ""
  LAST.carrier_name = b.carrier and subjectName(state, b.carrier)
    or Sync.nameForSid(state, carrierSid)
  local okPlayer, playerId = pcall(function() return be:getPlayerVehicleID(0) end)
  LAST.carrier_is_player =
    (okPlayer and b.carrier ~= nil and playerId == b.carrier) or false
  LAST.sync_mode = sync.mode
  LAST.sync_status = sync.status
  LAST.sync_arena = sync.arena or ""
  LAST.sync_epoch = sync.epoch or 0
  LAST.sync_revision = sync.revision or 0
  LAST.options_writable = Sync.optionsWritable()
  LAST.countdown =
    (OPT.show_countdown and b.phase == "live") and remaining or -1
  -- Urgency ships only in escalating style: in "steady" (hardcore) the
  -- fuse bar filling up would leak through the HUD exactly what the frozen
  -- pitch is hiding (v2.4 audio critic: "freezing pitch alone ships a
  -- lie"). Same for the countdown, whatever show_countdown says.
  local urgency = 0
  if b.phase == "live" and remaining >= 0 and OPT.tick_style == "escalating" then
    urgency = 1.0 - clampNumber(remaining / OPT.cue_window_seconds, 0.0, 1.0)
  end
  if OPT.tick_style ~= "escalating" then LAST.countdown = -1 end
  LAST.urgency = urgency
  -- v2.7: the show's stage, so the live gate (and any curious host) can
  -- time a camera against the letters.
  LAST.fw_stage = b.fw and b.fw.stage or ""
  LAST.transfers = b.transfers or 0
  LAST.field = b.fieldPeak or 0
  LAST.mode = OPT.transfer_mode
  LAST.game_mode = OPT.game_mode
  LAST.wins_to_champion = OPT.wins_to_champion
  local board = {}
  for id, count in pairs(b.wins or {}) do
    board[#board + 1] = {name = subjectName(state, id), wins = count}
  end
  table.sort(board, function(x, y) return x.wins > y.wins end)
  LAST.wins = board
  -- The hoarder scoreboard (v2.4): points held, race to the target.
  LAST.hoard_target = OPT.hoard_target_points
  local scores = {}
  for id, points in pairs(b.score or {}) do
    scores[#scores + 1] =
      {name = subjectName(state, id), points = math.floor(points)}
  end
  table.sort(scores, function(x, y) return x.points > y.points end)
  LAST.scores = scores
end

local function parkPotato(state)
  local b = state.behavior
  b.carrier = nil
  state.zones.carrier_watch = nil
  silenceTick(state)
  silenceWhistle(state)
  beaconLit(state, false)
  -- v2.3: the idle potato SMOKES. With the wick and its ember lamp retired,
  -- the wisp curling off the scorched crown is the "come and take it"
  -- invitation.
  setEffectActive(state, "fuse", OPT.smoke_enabled and true or false)
  setEffectActive(state, "blast", false)
  local home = toWorldPoint(state, B.potato_home)
  local bob = math.sin((b.now or 0) * OPT.bob_rate) * OPT.bob_amplitude
  local idleSpin = quat(0, 0, math.sin((b.spin or 0) * 0.5), math.cos((b.spin or 0) * 0.5))
  posePotato(state, vec3(home.x, home.y, home.z + bob), idleSpin)
  -- The wisp rises off the crown, bobbing with the potato.
  poseEffectAt(state, "fuse", vec3(home.x, home.y, home.z + SMOKE_RISE + bob))
  -- The idle potato VENTS (v2.4): a jittered microwave-potato hiss under
  -- the smoke — the audible half of "come and take it".
  stepHiss(state, home)
  -- Victory confetti burns out on a timer rather than fountaining forever
  -- (it used to run from the win until the NEXT pickup — critic round D5).
  if b.cheerUntil and b.now > b.cheerUntil then
    b.cheerUntil = nil
    setEffectActive(state, "cheer", false)
  end
end

-- ONE exit for every round-over path. Eliminations are PER-ROUND state:
-- v2.0 never cleared b.out, so the first detonation banned that car from
-- every future round — in single player that bricked the mod on the first
-- boom (the player's 2026-08-28 log: four pad crossings after the boom,
-- zero pickups, because roster() saw an empty field every time). Physics
-- quarantine is the exception and keeps its own table in roster().
local function endRound(state)
  local b = state.behavior
  b.phase = "idle"
  b.carrier = nil
  b.carrierSid = nil
  b.fuseEnds = nil
  b.silenced = false
  b.sputtered = false
  b.out = {}
  b.outCount = 0
  b.fieldPeak = 0
  b.pairFrom, b.pairTo, b.pairSeparated = nil, nil, true
  parkPotato(state)
  Sync.publish(state, true)
end

-- The alien return flight (v2.4: "the hot potato should always travel back
-- to its spawn location ... flying straight up and then hovering down to
-- its spawn perch"). Three legs from wherever the round left the tuber:
-- straight UP to a cruise line above everything, a level drift to the
-- point over the perch, then a slow eased descent onto it. The round is
-- over the moment this starts (carrier cleared, fuse dead, cues silent);
-- the NEXT round arms only when someone drives over the medallion — never
-- by teleporting the potato onto a car ("the game should only restart once
-- someone passes over the hot potato").
local function beginReturn(state, fromPos)
  local b = state.behavior
  b.carrier = nil
  b.carrierSid = nil
  state.zones.carrier_watch = nil
  b.fuseEnds = nil
  b.silenced = false
  b.out = {}
  b.outCount = 0
  b.fieldPeak = 0
  b.pairFrom, b.pairTo, b.pairSeparated = nil, nil, true
  b.sputtered = false
  silenceTick(state)
  silenceWhistle(state)
  beaconLit(state, false)
  setEffectActive(state, "blast", false)
  setEffectActive(state, "fuse", OPT.smoke_enabled and true or false)
  local home = toWorldPoint(state, B.potato_home)
  if not (fromPos and finiteVector3(fromPos))
    or (fromPos - home):length() < 2.0 then
    endRound(state)
    return
  end
  b.phase = "return"
  b.retFrom = vec3(fromPos.x, fromPos.y, fromPos.z)
  b.retStart = b.now
  local horizontal = math.sqrt(
    (fromPos.x - home.x) ^ 2 + (fromPos.y - home.y) ^ 2)
  b.retCruiseZ = math.max(fromPos.z, home.z + 10.0) + 8.0
  b.retUp = 2.2
  b.retCross = clampNumber(horizontal / 22.0, 0.6, 6.0)
  b.retDown = 3.0
  Sync.publish(state, true)
end

local function smoothstep(progress)
  progress = clampNumber(progress, 0.0, 1.0)
  return progress * progress * (3.0 - 2.0 * progress)
end

local function stepReturn(state)
  local b = state.behavior
  local home = toWorldPoint(state, B.potato_home)
  local from = b.retFrom or home
  local t = b.now - (b.retStart or b.now)
  local position
  if t < b.retUp then
    -- Straight up, easing out as it reaches the cruise line.
    local ease = smoothstep(t / b.retUp)
    position = vec3(from.x, from.y,
      from.z + (b.retCruiseZ - from.z) * ease)
  elseif t < b.retUp + b.retCross then
    local ease = smoothstep((t - b.retUp) / b.retCross)
    position = vec3(
      from.x + (home.x - from.x) * ease,
      from.y + (home.y - from.y) * ease,
      b.retCruiseZ)
  elseif t < b.retUp + b.retCross + b.retDown then
    local ease = smoothstep((t - b.retUp - b.retCross) / b.retDown)
    position = vec3(home.x, home.y,
      b.retCruiseZ + (home.z - b.retCruiseZ) * ease)
  else
    endRound(state)
    return
  end
  -- The strange hover: a slow yaw with a small circling nutation — a thing
  -- being carried by nothing, deliberately.
  local sway = 0.10
  local tilt = axisAngle(
    vec3(sway * math.sin(t * 1.3), sway * math.cos(t * 0.9), 1.0),
    (b.spin or 0))
  position.x = position.x + 0.25 * math.sin(t * 0.8)
  position.y = position.y + 0.25 * math.cos(t * 1.1)
  posePotato(state, position, tilt)
  poseEffectAt(state, "fuse",
    vec3(position.x, position.y, position.z + SMOKE_RISE))
  -- It vents on the way home too.
  stepHiss(state, position)
end

-- ==========================================================================
-- The champion fireworks (v2.4): the champion's name written across the sky
-- above the arch, letter by letter, each letter a firework burst — a shell
-- streaks up from the apex and blooms into the glyph, drawn with a reusable
-- pool of point lights. Lights live in state.effects, so the framework's
-- cleanup sweep owns them like every other effect.
-- ==========================================================================

-- 5x7 bitmap font, MSB = left column. Enough for names: A-Z, 0-9, space.
local FW_FONT = {
  A = {14,17,17,31,17,17,17}, B = {30,17,17,30,17,17,30},
  C = {14,17,16,16,16,17,14}, D = {28,18,17,17,17,18,28},
  E = {31,16,16,30,16,16,31}, F = {31,16,16,30,16,16,16},
  G = {14,17,16,23,17,17,15}, H = {17,17,17,31,17,17,17},
  I = {14,4,4,4,4,4,14},      J = {7,2,2,2,2,18,12},
  K = {17,18,20,24,20,18,17}, L = {16,16,16,16,16,16,31},
  M = {17,27,21,21,17,17,17}, N = {17,25,21,19,17,17,17},
  O = {14,17,17,17,17,17,14}, P = {30,17,17,30,16,16,16},
  Q = {14,17,17,17,21,18,13}, R = {30,17,17,30,20,18,17},
  S = {15,16,16,14,1,1,30},   T = {31,4,4,4,4,4,4},
  U = {17,17,17,17,17,17,14}, V = {17,17,17,17,17,10,4},
  W = {17,17,17,21,21,27,17}, X = {17,10,4,4,4,10,17},
  Y = {17,17,10,4,4,4,4},     Z = {31,1,2,4,8,16,31},
  ["0"] = {14,17,19,21,25,17,14}, ["1"] = {4,12,4,4,4,4,14},
  ["2"] = {14,17,1,6,8,16,31},    ["3"] = {31,2,4,2,1,17,14},
  ["4"] = {2,6,10,18,31,2,2},     ["5"] = {31,16,30,1,1,17,14},
  ["6"] = {6,8,16,30,17,17,14},   ["7"] = {31,1,2,4,8,8,8},
  ["8"] = {14,17,17,14,17,17,14}, ["9"] = {14,17,17,15,1,2,12},
}

-- Densest glyph is 20 lit pixels (B); 28 lights leaves margin and feeds
-- the finale sparkle.
local FW_POOL = 28
-- v2.7, sized against the live shots twice: at 1.05 the letters were
-- pinpricks from the plaza (a 7 m glyph at a 90 m camera); the critic
-- round called 1.6's 11 m "8% of frame height" and ordered it doubled.
-- 2.6 writes an 18 m letter — unmissable from anywhere in the arena.
local FW_PX = 2.6
local FW_LAUNCH = 0.7
local FW_BURST = 1.6
local FW_GAP = 0.3
local FW_FINALE = 2.8
local FW_COLORS = {
  {1.0, 0.84, 0.35}, {1.0, 0.36, 0.28}, {0.45, 0.85, 1.0},
  {0.80, 0.52, 1.0}, {0.55, 1.0, 0.55}, {1.0, 0.62, 0.20},
}

local function ensureFireworkPool(state)
  for i = 1, FW_POOL do
    local slot = "fw_px_" .. i
    if not state.effects[slot] then
      local light = createObject("PointLight")
      if light then
        local built = pcall(function()
          light.loadMode = 1
          if type(light.preApply) == "function" then light:preApply() end
          setCanSaveFalse(light)
          light:setField("radius", 0, "24")
          light:setField("brightness", 0, "0")
          light:setField("castShadows", 0, "0")
          light:setField("color", 0, "1 0.84 0.35 1")
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

local function fwSetLight(state, index, worldPos, color, brightness)
  local light = state.effects["fw_px_" .. index]
  if not light then return end
  pcall(function()
    if worldPos then
      light:setPosition(vec3(worldPos.x, worldPos.y, worldPos.z))
    end
    if color then
      light:setField("color", 0, string.format(
        "%.3f %.3f %.3f 1", color[1], color[2], color[3]))
    end
    light:setField("brightness", 0, string.format("%.2f", brightness or 0))
    light:setField("isEnabled", 0, (brightness or 0) > 0.02 and "1" or "0")
  end)
end

local function fwDouse(state)
  for i = 1, FW_POOL do fwSetLight(state, i, nil, nil, 0) end
end

local function glyphPixels(letter)
  local rows = FW_FONT[letter]
  if not rows then return {} end
  local pixels = {}
  for row = 1, 7 do
    local bits = rows[row]
    for col = 0, 4 do
      if math.floor(bits / 2 ^ (4 - col)) % 2 == 1 then
        pixels[#pixels + 1] = {col = col, row = row}
      end
    end
  end
  return pixels
end

-- Authored-frame position of a glyph pixel: the name marches along the
-- authored X axis (the arch's span), centred over the apex, on a vertical
-- plane. A flat glyph reads correctly from ONE side only (the v2.7 r2
-- live shot photographed 'E' as '3' from the south camera), so the whole
-- layout mirrors through fw.flip — chosen at showtime to face the PLAYER,
-- whose name it usually is.
local function fwPixelWorld(state, name, letterIndex, col, row, bloom)
  local flip = (state.behavior.fw and state.behavior.fw.flip) or 1.0
  local width = #name * 6.0 * FW_PX - FW_PX
  local cx = -width * 0.5 + (letterIndex - 1) * 6.0 * FW_PX + 2.0 * FW_PX
  local cz = B.fireworks_base_z + 3.5 * FW_PX
  local x = cx + (col - 2.0) * FW_PX * bloom
  local z = cz + (4.0 - row) * FW_PX * bloom
  return toWorldPoint(state, vec3(flip * x, 0.0, z))
end

local function championName(state, id)
  -- The PLAYER's crown carries their own name (Steam.playerName is how the
  -- game's chat seeds a nickname); an AI champion gets its model name.
  local name
  local okPlayer, playerId = pcall(function() return be:getPlayerVehicleID(0) end)
  if okPlayer and playerId == id then
    local okSteam, steamName = pcall(function() return Steam.playerName end)
    if okSteam and type(steamName) == "string" and steamName ~= "" then
      name = steamName
    end
  end
  return name or subjectName(state, id)
end

local function beginFireworks(state, name)
  if not OPT.fireworks_enabled then return end
  name = tostring(name or ""):upper():gsub("[^%w ]", ""):sub(1, 12)
  if name:gsub(" ", "") == "" then name = "CHAMPION" end
  ensureFireworkPool(state)
  -- Face the writing toward the player: a flat glyph mirrors from the far
  -- side, so pick the layout's handedness from which side of the authored
  -- XZ plane the player's car sits on when the show starts.
  local flip = 1.0
  local okPlayer, playerId = pcall(function() return be:getPlayerVehicleID(0) end)
  if okPlayer and playerId then
    local vehicle = exactVehicle(playerId)
    local okPos, playerPos = vehicle
      and pcall(function() return vehicle:getPosition() end)
    if okPos and finiteVector3(playerPos) then
      local forward = state.modelRotation * vec3(0, 1, 0)
      local origin = toWorldPoint(state, vec3(0, 0, 0))
      local side = (playerPos.x - origin.x) * forward.x
        + (playerPos.y - origin.y) * forward.y
      if side < 0 then flip = -1.0 end
    end
  end
  state.behavior.fw = {
    name = name, index = 1, stage = "launch", t0 = state.behavior.now,
    flip = flip,
  }
end

-- One firework star: a coloured glow shell around a white-hot core, drawn
-- with the debug drawer so it reads against OPEN SKY. The v2.4 show was
-- point lights alone — and a point light with no surface near it renders
-- nothing at all, which is why the player never saw a single letter
-- (v2.7, "I don't think the fireworks are working"). The lights stay, but
-- demoted to what they can actually do: throw the bursts' glow onto the
-- monument below.
function v26.fwStar(position, radius, red, green, blue, alpha)
  if not debugDrawer then return end
  local a = math.min(1.0, math.max(0.0, alpha))
  -- Critic-tuned anatomy: a coloured shell held near 0.85 alpha with an
  -- OPAQUE white-hot core at 0.4x — the pale-ring look died here.
  pcall(function()
    debugDrawer:drawSphere(
      vec3(position.x, position.y, position.z), radius,
      ColorF(red, green, blue, math.min(0.85, a)))
    debugDrawer:drawSphere(
      vec3(position.x, position.y, position.z), radius * 0.4,
      ColorF(1.0, 1.0, 0.96, math.min(1.0, a * 1.8)))
  end)
end

local function stepFireworks(state)
  local b = state.behavior
  local fw = b.fw
  if not fw then return end
  local t = b.now - fw.t0
  local name = fw.name
  local count = #name
  local letter = name:sub(fw.index, fw.index)
  if fw.stage == "launch" then
    if letter == " " then
      -- A silent beat between words.
      fw.stage = "gap"
      fw.t0 = b.now
      return
    end
    if t >= FW_LAUNCH then
      fw.stage = "burst"
      fw.t0 = b.now
      -- The arpeggio (v2.4 audio critic): one stinger per letter, pitch
      -- stepping up across the whole name.
      playSound(SFX_PASS,
        1.0 + 0.5 * (fw.index - 1) / math.max(1, count - 1), 0.9)
      return
    end
    -- One shell rising from the apex toward the letter centre: a white-hot
    -- head swaying like a real mortar shell, an ember trail cooling and
    -- falling behind it, and the pool light riding the head so the arch
    -- catches its glow.
    local ease = smoothstep(t / FW_LAUNCH)
    local target = fwPixelWorld(state, name, fw.index, 2, 4, 1.0)
    local apex = toWorldPoint(state, vec3(0.0, 0.0, B.fireworks_base_z - 8.0))
    local head = vec3(
      apex.x + (target.x - apex.x) * ease
        + math.sin(t * 9.0 + fw.index) * 0.7 * (1.0 - ease),
      apex.y + (target.y - apex.y) * ease,
      apex.z + (target.z - apex.z) * ease)
    v26.fwStar(head, 0.42, 1.0, 0.95, 0.80, 0.95)
    for i = 1, 7 do
      local back = smoothstep(math.max(0.0, t - i * 0.06) / FW_LAUNCH)
      v26.fwStar(vec3(
        apex.x + (target.x - apex.x) * back
          + math.sin((t - i * 0.06) * 9.0 + fw.index) * 0.7 * (1.0 - back),
        apex.y + (target.y - apex.y) * back,
        apex.z + (target.z - apex.z) * back - i * 0.16),
        0.26 - i * 0.022,
        1.0, 0.62 - i * 0.05, 0.25, 0.75 - i * 0.09)
    end
    fwSetLight(state, 1, head, {1.0, 0.9, 0.7}, 1.5 + ease * 2.0)
    return
  end
  if fw.stage == "burst" then
    if t >= FW_BURST then
      fwDouse(state)
      fw.stage = "gap"
      fw.t0 = b.now
      return
    end
    -- The glyph blooms outward from its centre, then fades as embers do:
    -- quadratic decay, brighter at birth.
    local bloom = smoothstep(math.min(t / 0.25, 1.0))
    local fade = 1.0 - t / FW_BURST
    local color = FW_COLORS[(fw.index - 1) % #FW_COLORS + 1]
    local pixels = glyphPixels(letter)
    -- The detonation flash: one fat white sphere collapsing over the first
    -- tenth of a second while the centre light spikes — the "whump" that
    -- washes the monument in light.
    local centre = fwPixelWorld(state, name, fw.index, 2, 4, 0.0)
    if t < 0.12 then
      local flash = 1.0 - t / 0.12
      v26.fwStar(centre, 0.6 + 4.2 * flash, 1.0, 0.98, 0.90, flash)
      -- Critic round: brightness 40 smeared the arch apex into the
      -- frame's brightest pixels and upstaged the letter. Halved.
      fwSetLight(state, 1, centre, {1.0, 0.95, 0.85}, 18.0 * flash)
    else
      fwSetLight(state, 1, centre, color, 6.0 * fade * fade)
    end
    -- The stars: one per lit glyph pixel, blooming outward, sagging as
    -- they burn (real stars fall), each twinkling on its own phase. The
    -- first dozen also carry pool lights for the ground glow. While the
    -- bloom is young, radiating streaks connect the centre to every star
    -- — the chrysanthemum spokes of a real shell. Between every pair of
    -- adjacent lit pixels a half-size midpoint star fills the stroke
    -- (critic round: "the E's spine has a hole and its top arm trails
    -- off" — the dot pitch is halved along every stroke).
    local droop = 1.8 * math.max(0.0, t - 0.35) ^ 2
    local spokes = t < 0.45 and (1.0 - t / 0.45) or 0.0
    local lit = {}
    for _, pixel in ipairs(pixels) do
      lit[pixel.col * 16 + pixel.row] = true
    end
    for index, pixel in ipairs(pixels) do
      local world = fwPixelWorld(state, name, fw.index, pixel.col, pixel.row, bloom)
      local twinkle = 0.72 + 0.28 * math.sin(b.now * 12.0 + index * 2.63)
      local star = vec3(world.x, world.y, world.z - droop)
      local radius = (0.95 + 0.35 * bloom) * twinkle
      local brightness = fade * fade * twinkle
      v26.fwStar(star, radius,
        color[1], color[2], color[3], brightness)
      if lit[(pixel.col + 1) * 16 + pixel.row] then
        local mid = fwPixelWorld(
          state, name, fw.index, pixel.col + 0.5, pixel.row, bloom)
        v26.fwStar(vec3(mid.x, mid.y, mid.z - droop), radius * 0.5,
          color[1], color[2], color[3], brightness * 0.85)
      end
      if lit[pixel.col * 16 + pixel.row + 1] then
        local mid = fwPixelWorld(
          state, name, fw.index, pixel.col, pixel.row + 0.5, bloom)
        v26.fwStar(vec3(mid.x, mid.y, mid.z - droop), radius * 0.5,
          color[1], color[2], color[3], brightness * 0.85)
      end
      if spokes > 0 and debugDrawer then
        pcall(function()
          debugDrawer:drawLine(
            vec3(centre.x, centre.y, centre.z), star,
            ColorF(color[1], color[2], color[3], 0.55 * spokes))
        end)
      end
      if index <= 12 then
        fwSetLight(state, index + 1, world, color, 3.0 * fade * fade)
      end
    end
    for index = math.min(#pixels, 12) + 2, FW_POOL do
      fwSetLight(state, index, nil, nil, 0)
    end
    return
  end
  if fw.stage == "gap" then
    if t >= FW_GAP then
      fw.index = fw.index + 1
      if fw.index > count then
        fw.stage = "finale"
        fw.t0 = b.now
        playSound(SFX_WIN, 1.0, 1.0)
      else
        fw.stage = "launch"
        fw.t0 = b.now
      end
    end
    return
  end
  -- Finale: sparkle rain across the full width of the name — falling,
  -- twinkling embers rather than bare light pips, sinking lower as the
  -- rain dies, under one warm lamp fading over the apex.
  if t >= FW_FINALE then
    fwDouse(state)
    b.fw = nil
    return
  end
  local fade = 1.0 - t / FW_FINALE
  local width = count * 6.0 * FW_PX
  fwSetLight(state, 1,
    toWorldPoint(state, vec3(0.0, 0.0, B.fireworks_base_z + 3.0)),
    {1.0, 0.84, 0.45}, 8.0 * fade)
  -- Critic round: "12 dots is confetti pixels, not rain" — the rain is
  -- now sixty-plus stars deep with 4.5 m segmented comet tails tapering
  -- to nothing, and only the first pool-light's worth carry real lights.
  for index = 2, 72 do
    if math.random() < 0.8 then
      local color = FW_COLORS[math.random(#FW_COLORS)]
      local world = toWorldPoint(state, vec3(
        (math.random() - 0.5) * width,
        (math.random() - 0.5) * 6.0,
        B.fireworks_base_z + math.random() * 9.0 - t * 2.2))
      v26.fwStar(world, 0.42 + math.random() * 0.30,
        color[1], color[2], color[3], fade * (0.5 + math.random() * 0.5))
      if debugDrawer then
        pcall(function()
          for segment = 0, 2 do
            local base = world.z + segment * 1.5
            debugDrawer:drawLine(
              vec3(world.x, world.y, base),
              vec3(world.x, world.y, base + 1.5),
              ColorF(color[1], color[2], color[3],
                fade * (0.5 - segment * 0.16)))
          end
        end)
      end
      if index <= FW_POOL then
        fwSetLight(state, index, world, color,
          (1.5 + math.random() * 3.0) * fade)
      end
    end
  end
end

-- ==========================================================================
-- The mash (v2.4: "make it appear like mash potato went everywhere"). Six
-- sculpted chunks live parked at their authored homes under the plaza;
-- detonation flings them out of the fireball on ballistic arcs, they land
-- and sit steaming, then melt back below grade and re-park. Pure visual
-- animation — the chunks are posed parts with no cage, so they cannot
-- touch physics.
-- ==========================================================================

local function parkMash(state)
  for i = 1, #(B.mash_homes or {}) do
    setPartPose(state, "mash_" .. i, vec3(0, 0, 0), quat(0, 0, 0, 1))
  end
end

local function spawnMash(state, anchor, groundZ)
  local homes = B.mash_homes or {}
  if #homes == 0 then return end
  local b = state.behavior
  b.mash = {}
  b.mashUntil = b.now + OPT.mash_seconds
  -- Tuned against the money shot (v2.4 critic round: the first fountain
  -- flew OVER the boom camera and out of frame). Slower spread and a
  -- shorter toss keep the splatter hanging around the blast anchor where
  -- the eye — and the screenshot — actually is.
  for i = 1, #homes do
    local heading = math.random() * 2.0 * math.pi
    local speed = 3.5 + math.random() * 4.0
    b.mash[i] = {
      pos = vec3(
        anchor.x + (math.random() - 0.5) * 1.2,
        anchor.y + (math.random() - 0.5) * 1.2,
        anchor.z + 0.4),
      vel = vec3(
        math.cos(heading) * speed,
        math.sin(heading) * speed,
        5.0 + math.random() * 4.0),
      spinAxis = vec3(
        math.random() - 0.5, math.random() - 0.5, math.random() - 0.5),
      spinRate = 2.0 + math.random() * 6.0,
      angle = math.random() * 6.28,
      ground = groundZ,
      landed = false,
      gone = false,
    }
  end
end

local function stepMash(state)
  local b = state.behavior
  if not b.mash then return end
  local dt = b.lastDelta or 0
  local live = false
  for i, chunk in ipairs(b.mash) do
    if not chunk.gone then
      if not chunk.landed then
        chunk.vel.z = chunk.vel.z - 9.81 * dt
        chunk.pos = chunk.pos + chunk.vel * dt
        chunk.angle = chunk.angle + chunk.spinRate * dt
        -- Rest PROUD of the ground: chunk.pos is the dollop's CENTRE, so
        -- settling it at the ground line buried it to the waist (v2.4
        -- critic: only shadow smudges in the money shot). It squats a
        -- little into its own splat, hence 0.45 rather than a full radius.
        local radius = (B.mash_radii and B.mash_radii[i]) or 0.5
        local rest = chunk.ground + radius * 0.45
        if chunk.pos.z <= rest and chunk.vel.z < 0 then
          chunk.pos.z = rest
          chunk.landed = true
        end
      elseif b.now > (b.mashUntil or 0) then
        -- Melt back into the plaza.
        chunk.pos.z = chunk.pos.z - 0.6 * dt
        if chunk.pos.z < chunk.ground - 2.5 then
          chunk.gone = true
          if chunk.steam then
            chunk.steam = nil
            setEffectActive(state, "mash_steam_" .. i, false)
            setEffectActive(state, "mash_steam_b" .. i, false)
          end
          setPartPose(state, "mash_" .. i, vec3(0, 0, 0), quat(0, 0, 0, 1))
        end
      end
      if not chunk.gone then
        live = true
        -- Very light steam off the dollop (v2.7): a PAIR of wisps switch
        -- on when the chunk lands, waver across its crown while it sits
        -- cooking and melts, and die with it (one wisp was functionally
        -- invisible at play distance — the critic round). Gated by the
        -- same smoke toggle as the potato's own wisp.
        local wantSteam = chunk.landed == true and OPT.smoke_enabled == true
        if wantSteam ~= (chunk.steam == true) then
          chunk.steam = wantSteam
          setEffectActive(state, "mash_steam_" .. i, wantSteam)
          setEffectActive(state, "mash_steam_b" .. i, wantSteam)
        end
        if wantSteam then
          local crown = (B.mash_radii and B.mash_radii[i]) or 0.5
          local waver = b.now * 0.9 + i * 2.1
          poseEffectAt(state, "mash_steam_" .. i, vec3(
            chunk.pos.x + math.sin(waver) * crown * 0.35,
            chunk.pos.y + math.cos(waver * 0.8) * crown * 0.35,
            chunk.pos.z + crown * 0.6))
          poseEffectAt(state, "mash_steam_b" .. i, vec3(
            chunk.pos.x - math.sin(waver * 1.1) * crown * 0.4,
            chunk.pos.y - math.cos(waver * 0.7) * crown * 0.4,
            chunk.pos.z + crown * 0.5))
        end
        -- The splatter ring (critic round: "chunks sit on untouched
        -- clean tile like they were placed by hand"): a deterministic
        -- ring of half-sunk butter-cream droplets around each landing —
        -- part of the landing itself, not the smoke toggle.
        if chunk.landed and debugDrawer then
          local crown = (B.mash_radii and B.mash_radii[i]) or 0.5
          pcall(function()
            for j = 1, 8 do
              local angle = j * 0.785 + i * 1.31
              local reach = crown * (1.25 + 0.3 * ((i * 7 + j * 13) % 10) / 10)
              debugDrawer:drawSphere(vec3(
                chunk.pos.x + math.cos(angle) * reach,
                chunk.pos.y + math.sin(angle) * reach,
                chunk.ground + 0.05),
                0.10 + 0.16 * ((i * 3 + j * 5) % 10) / 10,
                ColorF(0.95, 0.89, 0.66, 0.55))
            end
          end)
        end
        local rotation = chunk.landed
          and axisAngle(vec3(0, 0, 1), chunk.angle)
          or axisAngle(chunk.spinAxis, chunk.angle)
        -- The generator serialises 3-lists as vec3 literals, so the
        -- authored home IS a vec3 already (indexing it [1] reads nil).
        posePartWorld(state, "mash_" .. i, B.mash_homes[i], chunk.pos, rotation)
      end
    end
  end
  if not live then b.mash = nil end
end

-- Confetti erupts over the WINNER, not back at the arch: the last car
-- standing may be hundreds of metres from the monument and deserves to see
-- its own victory. And it burns out on a timer (parkPotato) instead of
-- fountaining until the next pickup. (Critic round D5, 2026-08-29.)
-- v2.3: wins now accrue in a ledger that outlives rounds (cleared on prop
-- init/reset only) — reach wins_to_champion and the session crowns you.
-- One crowning for both routes to the throne (round wins in classic play,
-- the points race in hoarder): the announce, the long confetti, and the
-- name in fireworks over the arch (v2.4).
local function crownChampion(state, id, measure)
  local b = state.behavior
  announce(state, "CHAMPION OF THE ARCH!", 6.0, "champion",
    {subject_id = id, measure = measure})
  b.cheerUntil = b.now + 16.0
  beginFireworks(state, championName(state, id))
end

local function celebrate(state, vehicle)
  local b = state.behavior
  local id = vehicle:getId()
  local ok, position = pcall(function() return vehicle:getPosition() end)
  if ok and finiteVector3(position) then
    poseEffectAt(state, "cheer", vec3(position.x, position.y, position.z + 4.0))
  end
  b.wins = b.wins or {}
  b.wins[id] = (b.wins[id] or 0) + 1
  if b.wins[id] >= OPT.wins_to_champion then
    crownChampion(state, id, b.wins[id])
    b.wins = {}
  else
    b.cheerUntil = b.now + 8.0
    -- v2.5 ("Champion fireworks should be for any winner"): every round
    -- winner gets their name written across the sky, not only the
    -- crowning — the champion still earns the longer confetti burn.
    beginFireworks(state, championName(state, id))
  end
  setEffectActive(state, "cheer", true)
  playSound(SFX_WIN, 1.0, 1.0)
end

local function giveTo(state, vehicle, reason, passSpeed)
  local b = state.behavior
  local id = vehicle:getId()
  local previous = b.carrier
  b.carrier = id
  b.carrierSid = Sync.sidForGameId(id)
  b.heldSince = b.now
  b.transfers = (b.transfers or 0) + 1
  b.silenced = false
  -- A fresh hot window re-excites the steam: the whistle restarts at peak
  -- for the new carrier (driveWhistle moves the loop by id on the next cue
  -- tick), and the sputter re-arms.
  b.sputtered = false
  b.hopStart = nil
  if previous and previous ~= id then
    -- Anti-tag-back: the passer is immune for a window, AND the pair must
    -- physically separate before the potato may come back (see sweepForPass).
    b.immune[previous] = b.now + OPT.tagback_immunity_seconds
    b.pairFrom = previous
    b.pairTo = id
    b.pairSeparated = false
    -- The transfer shield (v2.6): both cars in a pass get full armor for
    -- the window ("temporarily invincible when they collide in order to
    -- transfer ... to make it more arcade like"), then the armor sweep
    -- settles them back to whatever damage_mode wants. Applied INLINE,
    -- not on the sweep: the collision is happening right now.
    if OPT.transfer_shield_seconds > 0 then
      b.shield = b.shield or {}
      b.shield[previous] = b.now + OPT.transfer_shield_seconds
      b.shield[id] = b.now + OPT.transfer_shield_seconds
      v26.sendArmor(state, vehicle, "full")
      local passer = exactVehicle(previous)
      if passer then v26.sendArmor(state, passer, "full") end
    end
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
  setEffectActive(state, "fuse", OPT.smoke_enabled and true or false)
  beaconLit(state, true)
  -- Move the loop to the new carrier immediately (driveTick silences the
  -- previous one first); the per-frame cue update refines volume/pitch.
  driveTick(state, vehicle, 0.55, tickPitch(OPT.beep_slow_interval))
  -- The pass ding rings sharper the harder the hit (v2.4 audio critic):
  -- +1 cent per cm/s of closing speed, capped at 30 m/s. Subconscious,
  -- cheap, delightful.
  playSound(previous and SFX_PASS or SFX_PICKUP,
    1.0 + clampNumber(passSpeed or 0, 0, 30) * 0.01, 1.0)
  emitEvent(state, "I", "potato_passed", {
    subject_id = id, previous_id = previous, reason = reason,
  })
  Sync.publish(state, true)
end

local function detonate(state, vehicle)
  local b = state.behavior
  local id = vehicle:getId()
  b.phase = "boom"
  b.boomAt = b.now
  b.boomLaunched = false
  b.nextHush = 0
  -- The fizzle (v2.4, "even the exploding ... optional"): with detonation
  -- disabled the fuse end COOKS the holder instead of destroying them — a
  -- steam burst and a loud vent, elimination without a scratch.
  b.fizzle = not OPT.detonate_enabled
  b.fireDur = b.fizzle and 2.0 or OPT.fire_seconds
  if not b.out[id] then b.outCount = (b.outCount or 0) + 1 end
  b.out[id] = true
  -- Re-stamp the victim's first-seen time PAST the boom sequence AND the
  -- return flight: without this, a wreck that happens to be burning ON the
  -- medallion re-arms a fresh round — and a fresh tick — the moment the
  -- potato settles back on its perch. Beeping resuming over a wreck is
  -- indistinguishable from "the audio never stopped" (the 2026-08-29
  -- report's second half).
  b.seen[id] = b.now + b.fireDur + 14.0
  -- A hoard is a dangerous thing to hold (v2.4 hoarder mode): the boom
  -- costs the victim half their points.
  if OPT.game_mode == "hoarder" and b.score and b.score[id] then
    b.score[id] = b.score[id] * 0.5
  end
  silenceTick(state)
  silenceWhistle(state)
  beaconLit(state, false)
  local anchor = carrierPose(state, vehicle)
  b.boomFrom = vec3(anchor.x, anchor.y, anchor.z)
  -- Ground estimate for the mash rain: the OOBB centre sits one half-height
  -- above the wheels.
  local groundZ = anchor.z - 2.0
  local okPos, victimPos = pcall(function() return vehicle:getPosition() end)
  if okPos and finiteVector3(victimPos) then
    groundZ = victimPos.z - subjectExtents(state, vehicle).height + 0.15
  end
  if b.fizzle then
    -- The steam burst: the wisp keeps running at the anchor, the vent
    -- screams once, and nothing else happens to the car.
    setEffectActive(state, "fuse", OPT.smoke_enabled and true or false)
    poseEffectAt(state, "fuse", anchor)
    -- The potato's own death wheeze (v2.5): the baked sputter one-shot in
    -- the cooked holder's VM, under the FMOD vent pair. In escalating style
    -- the fuse cue already sputtered moments ago — do not stutter it.
    if not b.sputtered then
      b.sputtered = true
      playSputter(state, vehicle, 0.9, 0.9)
    end
    playSound(SFX_HISS, 0.9, 1.2, anchor)
    playSound(SFX_HISS_ALT, 1.3, 0.9, anchor)
    announce(state, "COOKED! The potato goes home.", 3.0, "fizzled",
      {subject_id = id})
    emitEvent(state, "I", "potato_fizzled", {subject_id = id})
    Sync.sendCommand(state, "detonate", {
      target_sid = Sync.sidForGameId(id),
      fizzle = true,
    }, true)
    Sync.publish(state, true)
    return
  end
  setEffectActive(state, "fuse", false)
  poseEffectAt(state, "blast", anchor)
  setEffectActive(state, "blast", true)
  -- The detonation stack (v2.4 audio critic): crack + body + debris ring —
  -- the same proven one-shot at three pitches, the two copies scheduled a
  -- beat behind by the boom phase.
  playSound(SFX_BOOM, 0.85, 1.0)
  b.boomStack = {
    {at = b.now + 0.08, pitch = 0.55, volume = 0.8},
    {at = b.now + 0.25, pitch = 1.6, volume = 0.35},
  }
  if OPT.mash_enabled then
    spawnMash(state, anchor, groundZ)
  end
  -- The area shockwave (v2.3): bystanders inside blast_radius_m get a
  -- radial shove with linear falloff — a uniform cluster velocity add, so
  -- it moves cars without straining a single beam. The victim is excluded
  -- (roster already dropped it via b.out; it gets the real launch).
  if OPT.blast_push_mps > 0 and OPT.blast_radius_m > 0 then
    for _, entry in ipairs(roster(state)) do
      if entry.id ~= id then
        local position = entry.vehicle:getPosition()
        if finiteVector3(position) then
          local axis = position - anchor
          local distance = axis:length()
          if distance > 0.01 and distance < OPT.blast_radius_m then
            local falloff = 1.0 - distance / OPT.blast_radius_m
            axis = axis * (1.0 / distance)
            local delta = vec3(
              axis.x * OPT.blast_push_mps * falloff,
              axis.y * OPT.blast_push_mps * falloff,
              OPT.blast_push_mps * falloff * 0.35)
            local applied = Sync.canMutate(entry.vehicle)
              and addSubjectVelocity(state, entry.vehicle, delta) == true
            Sync.sendCommand(state, "impulse", {
              target_sid = Sync.sidForGameId(entry.id),
              delta = Sync.vectorTable(delta),
            }, applied)
          end
        end
      end
    end
  end
  -- Strip the victim's armor FIRST (v2.6): the boom must land whatever
  -- damage_mode says, and the break/crush/fire commands queue behind this
  -- restore in the same vehicle VM, in order. The shield dies with it.
  if b.shield then b.shield[id] = nil end
  local armored = b.armorApplied and b.armorApplied[id]
  if armored and armored ~= "none" then
    v26.sendArmor(state, vehicle, "none")
  end
  if OPT.detonate_break then
    if Sync.canMutate(vehicle) then
      pcall(function() vehicle:queueLuaCommand(BREAK_COMMAND) end)
    end
  end
  if OPT.detonate_crush then
    local command = string.format(
      CRUSH_TEMPLATE,
      tostring(OPT.crush_dv_mps), tostring(OPT.crush_min_z),
      tostring(OPT.crush_inward))
    if Sync.canMutate(vehicle) then
      pcall(function() vehicle:queueLuaCommand(command) end)
    end
  end
  if OPT.detonate_fire then
    if Sync.canMutate(vehicle) then
      pcall(function() vehicle:queueLuaCommand(FIRE_COMMAND) end)
    end
  end
  Sync.sendCommand(state, "detonate", {
    target_sid = Sync.sidForGameId(id),
    fizzle = false,
    break_vehicle = OPT.detonate_break == true,
    crush_vehicle = OPT.detonate_crush == true,
    fire_vehicle = OPT.detonate_fire == true,
    crush_dv_mps = OPT.crush_dv_mps,
    crush_min_z = OPT.crush_min_z,
    crush_inward = OPT.crush_inward,
  }, Sync.canMutate(vehicle))
  announce(state, "BOOM!", 2.5, "detonation", {subject_id = id})
  Sync.publish(state, true)
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
      -- The arena gate (v2.6): a car outside the circle is not part of the
      -- game and cannot receive the potato — chasing a runner into the
      -- distance is exactly what the arena exists to end.
      if finiteVector3(position) and v26.insideArena(state, position) then
        local distance = (position - carrierPosition):length()
        local threshold = touchMode
          and contactRange(state, carrier, entry.vehicle)
          or OPT.radius_m
        if distance <= threshold then
          -- Touch mode also demands a real hit: without a minimum closing
          -- speed two stationary cars can brush fenders forever. Pinball
          -- mode (v2.4) waives it — ANY touch passes, that is the game.
          local fast = true
          if touchMode and OPT.impact_kmh > 0
            and OPT.game_mode ~= "pinball" then
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
    local hitSpeed = closingSpeed(carrier, best)
    giveTo(state, best, touchMode and "impact" or "radius", hitSpeed)
    -- Comedy dial (v2.3): the receiver of an impact pass gets shoved along
    -- the hit axis, with a little lift. A cluster velocity add — the shove
    -- moves the car, it cannot damage it. Pinball mode (v2.4) guarantees a
    -- hearty minimum: the pass IS a bumper.
    local knock = OPT.pass_knockback_mps
    if OPT.game_mode == "pinball" then knock = math.max(knock, 8.0) end
    if touchMode and knock > 0 then
      local axis = best:getPosition() - carrierPosition
      axis.z = 0
      if axis:length() > 0.01 then
        axis:normalize()
        local delta = vec3(axis.x * knock, axis.y * knock, knock * 0.3)
        local applied = Sync.canMutate(best)
          and addSubjectVelocity(state, best, delta) == true
        Sync.sendCommand(state, "impulse", {
          target_sid = Sync.sidForGameId(best:getId()),
          delta = Sync.vectorTable(delta),
        }, applied)
      end
    end
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
  -- NEGATIVE boost (v2.3) is the ball-and-chain handicap: a drag along the
  -- velocity, floored so it can only slow a moving car, never reverse it.
  if not Sync.canMutate(carrier) then return end
  local boost = OPT.carrier_boost_mps2
  if boost == 0 then return end
  local ok, velocity = pcall(function() return carrier:getVelocity() end)
  if not ok or not finiteVector3(velocity) then return end
  local speed = velocity:length()
  local direction = vec3(velocity.x, velocity.y, velocity.z)
  if boost > 0 then
    if speed < 2.0 or speed > OPT.carrier_boost_max_mps then return end
    direction:normalize()
    addSubjectVelocity(state, carrier, direction * (boost * (dtSim or 0)))
    return
  end
  if speed < 3.0 then return end
  direction:normalize()
  local drag = math.min(-boost * (dtSim or 0), speed - 3.0)
  addSubjectVelocity(state, carrier, direction * (-drag))
end

-- --------------------------------------------------------------------------
-- AI drivers (v2.5, "this game is meant to be multiplayer"). With ai_enabled
-- on, every vehicle that is not the player's becomes a hot-potato player of
-- its own through the stock vehicle AI — the same machinery police pursuits
-- ride: the carrier CHASES its nearest target to pass the potato on, every
-- other car FLEES the carrier, and between rounds they hold position. Roles
-- re-resolve on a throttled sweep, so a pass flips hunter and hunted
-- mid-corner. Every command is a queued vehicle-side call to ai.setMode /
-- ai.setTargetObjectID / ai.setAggression / ai.setSpeedMode / ai.setSpeed —
-- the exact exported surface of lua/vehicle/ai.lua (measured, 0.38.6:
-- M.setMode line 6192, M.setTargetObjectID line 6210, and a manually set
-- target id overrides the AI's own player pick in targetObjectSelector).
-- --------------------------------------------------------------------------
local AI_SWEEP_SECONDS = 0.8

local function aiCommand(vehicle, command)
  if not Sync.canMutate(vehicle) then return end
  pcall(function() vehicle:queueLuaCommand(command) end)
end

-- Hand every commanded vehicle back to its user. Runs when ai_enabled flips
-- off, on prop init/reset, and at teardown — the AI must never outlive the
-- mod that switched it on.
local function aiRelease(state)
  local b = state.behavior
  if not b.aiApplied then return end
  for id in pairs(b.aiApplied) do
    local vehicle = exactVehicle(id)
    if vehicle then
      aiCommand(vehicle, "pcall(function() ai.setMode('disabled') end)")
    end
  end
  b.aiApplied = nil
  b.aiReturning = nil
  b.aiTuning = nil
end

-- One containment write: steer this car straight back at the arch.
-- ai.setSlotTrafficTarget is the ONE vehicle-AI export that takes raw world
-- coordinates and needs no navgraph (measured, ai.lua:5833) — it
-- self-switches the mode, drives pure pursuit at the point, and brakes on
-- its own 0.5 s watchdog, which is why v26.stepAiReturn refreshes it.
function v26.sendReturn(state, vehicle)
  local centre = toWorldPoint(state, B.pad_center)
  aiCommand(vehicle, string.format(
    "pcall(function() ai.setSlotTrafficTarget(%.1f, %.1f, %.1f, %.1f) end)",
    centre.x, centre.y, centre.z, OPT.ai_speed_kmh / 3.6))
end

local function stepAI(state)
  local b = state.behavior
  if not OPT.ai_enabled then
    if b.aiApplied then aiRelease(state) end
    return
  end
  if (b.aiNextSweep or 0) > b.now then return end
  b.aiNextSweep = b.now + AI_SWEEP_SECONDS
  local playerId = nil
  pcall(function() playerId = be:getPlayerVehicleID(0) end)
  b.aiApplied = b.aiApplied or {}
  b.aiReturning = b.aiReturning or {}
  -- A tuning change re-arms everyone: aggression and the speed cap ride
  -- along with the next role command, so clearing the applied map resends.
  local tuning = string.format("%.2f|%.1f", OPT.ai_aggression, OPT.ai_speed_kmh)
  if b.aiTuning ~= tuning then
    b.aiTuning = tuning
    b.aiApplied = {}
  end
  local field = roster(state)
  local carrierId = b.phase == "live" and b.carrier or nil
  local speedMps = OPT.ai_speed_kmh / 3.6
  -- Hold modes invert the desire (v2.6): in hoarder and protect the carrier
  -- WANTS the potato, so the mob hunts the carrier and the carrier runs. In
  -- classic and pinball the carrier hunts and everyone else flees.
  local holdMode = OPT.game_mode == "hoarder" or OPT.game_mode == "protect"
  local present = {}
  for _, entry in ipairs(field) do
    local id = entry.id
    if id ~= playerId then
      local okPos, myPos = pcall(function() return entry.vehicle:getPosition() end)
      local havePos = okPos and finiteVector3(myPos)
      local distance = havePos and v26.arenaDistance(state, myPos) or nil
      local outNow = OPT.arena_enabled and distance ~= nil
        and distance > OPT.arena_radius_m
      if outNow and b.aiApplied[id] == nil then
        -- Outside the circle and never conscripted: not part of the game
        -- ("any AI vehicle within the game radius becomes part of the hot
        -- potato game" — and only those).
        present[id] = nil
      else
        present[id] = true
        local role
        if outNow or (b.aiReturning[id] and OPT.arena_enabled
          and distance ~= nil and distance > OPT.arena_radius_m * 0.8) then
          -- Containment, with hysteresis: a strayed car returns until it is
          -- well inside (80% of the radius), not merely on the line —
          -- otherwise it flip-flops role at the boundary every sweep.
          role = "return"
        elseif carrierId and id == carrierId then
          -- The carrier resolves against its nearest other car — the
          -- player included: prey to chase in the hot modes, a hunter to
          -- run from in the hold modes.
          local best, bestDist = nil, nil
          if havePos then
            for _, other in ipairs(field) do
              if other.id ~= id then
                local okOther, otherPos = pcall(function() return other.vehicle:getPosition() end)
                if okOther and finiteVector3(otherPos) then
                  local dist = (otherPos - myPos):length()
                  if not bestDist or dist < bestDist then
                    best, bestDist = other.id, dist
                  end
                end
              end
            end
          end
          if not best then
            role = "stop"
          else
            role = (holdMode and "flee:" or "chase:") .. best
          end
        elseif carrierId then
          role = (holdMode and "chase:" or "flee:") .. carrierId
        else
          -- No round running: hold position and look innocent.
          role = "stop"
        end
        if b.aiApplied[id] ~= role then
          b.aiApplied[id] = role
          if role == "return" then
            b.aiReturning[id] = true
            v26.sendReturn(state, entry.vehicle)
          else
            b.aiReturning[id] = nil
            local mode, target = role:match("^(%a+):?(%d*)")
            if mode == "stop" then
              aiCommand(entry.vehicle, "pcall(function() ai.setMode('stop') end)")
            else
              -- setMode FIRST (v2.6, measured): setMode -> resetMapAndRoute
              -- (ai.lua:5780) calls resetAggression/resetParameters, so
              -- tuning sent before the mode is silently wiped by it. The
              -- v2.5 order shipped exactly that bug.
              aiCommand(entry.vehicle, string.format(
                "pcall(function() ai.setMode('%s')"
                .. " ai.setTargetObjectID(%d) ai.setAggression(%.2f)"
                .. " ai.setSpeedMode('limit') ai.setSpeed(%.1f) end)",
                mode, tonumber(target), OPT.ai_aggression, speedMps))
            end
          end
        end
      end
    end
  end
  -- A car that left the field (eliminated, quarantined, despawned) parks; a
  -- car the player took over gets its controls back.
  for id in pairs(b.aiApplied) do
    if not present[id] then
      local vehicle = exactVehicle(id)
      if vehicle then
        aiCommand(vehicle, id == playerId
          and "pcall(function() ai.setMode('disabled') end)"
          or "pcall(function() ai.setMode('stop') end)")
      end
      b.aiApplied[id] = nil
      b.aiReturning[id] = nil
    end
  end
end

-- The containment heartbeat: runs every frame (throttled inside to 0.25 s)
-- so the slotTraffic watchdog (0.5 s, ai.lua:5165-5167) never starves
-- between the 0.8 s role sweeps.
function v26.stepAiReturn(state)
  local b = state.behavior
  if not (OPT.ai_enabled and OPT.arena_enabled and b.aiReturning) then return end
  if next(b.aiReturning) == nil then return end
  if (b.aiReturnNext or 0) > b.now then return end
  b.aiReturnNext = b.now + 0.25
  for id in pairs(b.aiReturning) do
    local vehicle = exactVehicle(id)
    if vehicle then v26.sendReturn(state, vehicle) end
  end
end

-- ==========================================================================
-- The arena magnet (v2.7): the physical rubber band under the AI steering.
-- obj:setPlanets{x, y, z, radius, mass} is the engine's own gravity well
-- (vehicle physics side, per node, every physics step — funstuff.lua's
-- explode drives it with negative mass to repel; positive mass attracts).
-- A well is a STANDING setting, so unlike the slotTraffic return there is
-- no watchdog to feed: the 0.5 s sweep only has to place it when a member
-- strays out, refresh its mass as the range changes, and lift it again.
-- ==========================================================================

v26.G = 6.674e-11

function v26.sendMagnet(state, vehicle, distance)
  local centre = toWorldPoint(state, B.pad_center)
  -- Constant-force tether: mass = a * d^2 / G with a = arena_magnet_g in
  -- gees at the car's CURRENT range, so the pull never fades with escape
  -- distance the way raw planet gravity would.
  local mass = OPT.arena_magnet_g * 9.81 * distance * distance / v26.G
  aiCommand(vehicle, string.format(
    "pcall(function() obj:setPlanets({%.1f, %.1f, %.1f, 10, %.5g}) end)",
    centre.x, centre.y, centre.z, mass))
end

function v26.magnetClear(state, vehicle)
  aiCommand(vehicle, "pcall(function() obj:setPlanets({}) end)")
end

-- Lift every standing well. Runs when the toggle flips off, when the round
-- leaves the live phase, and on prop init/reset/teardown — a gravity well
-- must never outlive the game that placed it.
function v26.magnetRelease(state)
  local b = state.behavior
  if not b.magnetApplied then return end
  for id in pairs(b.magnetApplied) do
    local vehicle = exactVehicle(id)
    if vehicle then v26.magnetClear(state, vehicle) end
  end
  b.magnetApplied = nil
end

function v26.stepMagnet(state)
  local b = state.behavior
  if not (OPT.arena_enabled and b.phase == "live") then
    if b.magnetApplied then v26.magnetRelease(state) end
    -- Membership is per round: a fresh game re-drafts from whoever is
    -- inside the ring then.
    if b.phase ~= "live" then b.arenaMembers = nil end
    return
  end
  if (b.magnetNext or 0) > b.now then return end
  b.magnetNext = b.now + 0.5
  -- Membership rides the ARENA, not the magnet toggle: a host flipping the
  -- magnet on mid-round must still catch the car that is already outside.
  local magnetOn = OPT.arena_magnet_enabled
  if not magnetOn and b.magnetApplied then v26.magnetRelease(state) end
  b.arenaMembers = b.arenaMembers or {}
  b.magnetApplied = b.magnetApplied or {}
  if b.carrier then b.arenaMembers[b.carrier] = true end
  for _, entry in ipairs(roster(state)) do
    local id = entry.id
    local okPos, position = pcall(function() return entry.vehicle:getPosition() end)
    if okPos and finiteVector3(position) then
      local distance = v26.arenaDistance(state, position)
      if distance <= OPT.arena_radius_m then
        -- Inside the ring: a member for the rest of the round — the player
        -- included, which is the difference from the AI-only steering…
        b.arenaMembers[id] = true
        -- …and the well lifts once the car is WELL inside (90%), not at
        -- the line, so the boundary cannot chatter it on and off.
        if b.magnetApplied[id] and distance <= OPT.arena_radius_m * 0.9 then
          v26.magnetClear(state, entry.vehicle)
          b.magnetApplied[id] = nil
        end
      elseif magnetOn and b.arenaMembers[id] then
        v26.sendMagnet(state, entry.vehicle, distance)
        b.magnetApplied[id] = true
      end
    end
  end
end

local function updateFuseCues(state, carrier, worldPos, dtReal)
  -- No numeric countdown anywhere, by design: the player reads urgency from
  -- an accelerating, rising tick and a beacon that pulses in step with it.
  -- The tick is ONE looping source in the carrier's VM (TICK_START): pitch
  -- maps the interval options through the authored loop length so rate and
  -- tone accelerate as one gesture, and beep_pitch_rise stacks an extra
  -- panic multiplier on top as the window closes.
  --
  -- v2.4 layers three player-requested behaviours on top:
  -- - tick_style: "escalating" (classic), "steady" (the hot-potato song at
  --   constant rate and pitch — NO tell that the end is near; the cue
  --   urgency is pinned to 0 so volume, beat, spin, hop and glow all hold
  --   steady too, and hotPotatoGetStats publishes urgency 0 — freezing the
  --   pitch alone would ship a lie through the other channels), or "off".
  -- - The silence beat: in escalating style the tick STOPS silence_gap
  --   seconds before the boom and the beacon goes dark. After a minute of
  --   accelerating tick, a second of nothing is the loudest sound in the
  --   mod.
  -- - The hop trigger: each audible beat launches the carried potato's
  --   parabolic bounce (carrierPose), so the potato jumps its own rhythm.
  local b = state.behavior
  local remaining = (b.fuseEnds or b.now) - b.now
  local urgency = 1.0 - clampNumber(remaining / OPT.cue_window_seconds, 0.0, 1.0)
  local escalating = OPT.tick_style == "escalating"
  local cueU = escalating and urgency or 0.0
  b.cueUrgency = cueU

  -- The steam whistle (v2.5): the potato's own voice while carried, its own
  -- channel beside the tick. Begins abruptly at peak on pickup (the brief's
  -- decay curve), holds steady, then — in escalating style — glides DOWN as
  -- the internal pressure runs out, and finally breaks into the baked
  -- staccato sputter one-shot timed so its dying wheeze lands exactly at
  -- the mouth of the silence gap. Steady style holds constant pitch: the
  -- whistle must not leak the tell the steady tick withholds.
  if OPT.audio_enabled and OPT.whistle_enabled and b.fuseEnds then
    if escalating and remaining <= (SPUTTER_SECONDS + OPT.silence_gap_seconds) then
      if not b.sputtered then
        b.sputtered = true
        silenceWhistle(state)
        playSputter(state, carrier, 0.75, 1.0)
      end
    else
      local wpitch = escalating and (1.0 - 0.28 * cueU) or 1.0
      -- v2.6 tone-down ("the noise is annoying now"): the re-voiced asset
      -- peaks 7.5 dB lower AND the drive gain dropped from 0.5+0.1u — the
      -- vent is a texture under the tick, not a siren over it.
      driveWhistle(state, carrier, 0.30 + 0.08 * cueU, wpitch)
    end
  else
    silenceWhistle(state)
  end

  -- The horror cut: silence, darkness, then the boom.
  if escalating and b.fuseEnds
    and remaining <= OPT.silence_gap_seconds and remaining > -0.5 then
    if not b.silenced then
      b.silenced = true
      silenceTick(state)
    end
    beaconLit(state, false)
    return
  end

  local interval = OPT.beep_slow_interval
    + (OPT.beep_fast_interval - OPT.beep_slow_interval) * cueU
  -- Real-time spin: the hardcoded 0.016 made the beacon sweep frame-rate
  -- dependent (critic round D7, 2026-08-29).
  b.beaconAngle = (b.beaconAngle or 0)
    + OPT.beacon_spin_rate * (1.0 + cueU * 2.0) * (dtReal or 0.016)
  local pitch = clampNumber(
    tickPitch(interval) * (1.0 + cueU * OPT.beep_pitch_rise),
    TICK_PITCH_MIN, TICK_PITCH_CAP)
  if OPT.tick_style == "off" then
    silenceTick(state)
  elseif escalating then
    driveTick(state, carrier, 0.55 + cueU * 0.45, pitch)
  else
    -- Steady: the song, constant. Legitimately scarier than the ramp.
    driveTick(state, carrier, 0.7, tickPitch(OPT.beep_slow_interval))
  end
  -- The beacon strobes on the AUDIBLE beat — the loop's true period at the
  -- pitch just sent — not on the requested interval. The clamp saturates
  -- the audio near the end of the window, and a strobe that kept
  -- accelerating past the sound it claims to mirror reads as a glitch.
  local audible = TICK_LOOP_SECONDS / math.max(pitch, 0.01)
  if (b.nextBeep or 0) <= b.now then
    b.nextBeep = b.now + math.max(0.03, audible)
    b.pulseUntil = b.now + OPT.beacon_pulse_seconds
    -- Launch the rhythm hop with this beat.
    b.hopStart = b.now
    b.hopDur = clampNumber(audible * 0.9, 0.12, 0.7)
    b.hopAmp = 0.10 + OPT.bounce_amplitude_m * cueU
  end
  -- The beacon strobes ON with each tick rather than burning steady, so the
  -- visual cue and the audio cue are the same accelerating pulse.
  beaconLit(state, (b.pulseUntil or 0) > b.now)
  glowHeat(state, cueU)
  poseBeacon(state, worldPos)
end

-- The round itself. Split out of behavior.update so every early return still
-- ends with one publishStats, rather than each exit path having to remember.
local function stepRound(state, dtSim, dtReal)
  local b = state.behavior

  if b.phase == "idle" then
    parkPotato(state)
    sweepForPickup(state)
    return
  end

  if b.phase == "return" then
    stepReturn(state)
    return
  end

  if b.phase == "boom" then
    local since = b.now - (b.boomAt or b.now)
    local victim = exactVehicle(b.carrier)
    local fireDur = b.fireDur or OPT.fire_seconds
    -- Silence redundancy (v2.3, the "audio persists after the explosion"
    -- report): the one TICK_STOP detonate() queued crosses the GE->vehicle
    -- boundary in the same frame the VM is being fed break, crush and fire
    -- commands. Re-send it a few times over the first second of the boom —
    -- an already-silent VM no-ops, a missed stop gets caught.
    if victim and since < 1.2 and (b.nextHush or 0) <= b.now then
      b.nextHush = b.now + 0.3
      pcall(function() victim:queueLuaCommand(TICK_STOP) end)
      pcall(function() victim:queueLuaCommand(WHISTLE_STOP) end)
    end
    -- The delayed layers of the detonation stack.
    if b.boomStack then
      local rest = {}
      for _, layer in ipairs(b.boomStack) do
        if layer.at <= b.now then
          playSound(SFX_BOOM, layer.pitch, layer.volume)
        else
          rest[#rest + 1] = layer
        end
      end
      b.boomStack = #rest > 0 and rest or nil
    end
    -- The launch lands a tick behind the press so the panels are already
    -- shedding when the wreck leaves the ground. A fizzle launches nothing.
    if not b.boomLaunched and since >= 0.12 then
      b.boomLaunched = true
      if victim and not b.fizzle then
        local delta = vec3(0, 0, OPT.detonate_launch_mps)
        local applied = Sync.canMutate(victim)
          and launchSubject(state, victim, delta) == true
        Sync.sendCommand(state, "impulse", {
          target_sid = Sync.sidForGameId(victim:getId()),
          delta = Sync.vectorTable(delta),
        }, applied)
      end
    end
    if since < fireDur then
      -- The potato rides the blast: it climbs out of the fireball tumbling,
      -- at half the wreck's launch speed, instead of freezing at roof
      -- height for eleven seconds (critic round D4, 2026-08-29). b.boomFrom
      -- is the blast anchor detonate() recorded. A fizzle just drifts up
      -- gently on its own steam.
      local liftoff = b.boomFrom or toWorldPoint(state, B.potato_home)
      local rate = b.fizzle and 1.2 or OPT.detonate_launch_mps * 0.5
      local climb = since * rate
      local tumble = axisAngle(vec3(0.4, 0.2, 1.0), since * (b.fizzle and 1.2 or 3.5))
      posePotato(
        state, vec3(liftoff.x, liftoff.y, liftoff.z + climb), tumble)
      poseEffectAt(
        state, "fuse", vec3(liftoff.x, liftoff.y, liftoff.z + climb + SMOKE_RISE))
      return
    end
    -- The fire is out. Settle the round ONCE, then send the potato home the
    -- long way: winner honours first, then the alien return flight. The
    -- next round arms only at the medallion (v2.4 — the old path teleported
    -- the potato onto the nearest car here, "STILL IN PLAY!", and the
    -- player read it as the game restarting itself).
    setEffectActive(state, "blast", false)
    local remaining = roster(state)
    if #remaining == 1 and (b.fieldPeak or 0) >= 2 then
      celebrate(state, remaining[1].vehicle)
      announce(state, "LAST CAR STANDING!", 4.0, "round_won",
        {subject_id = remaining[1].id})
    elseif #remaining >= 2 then
      announce(state, "The potato returns to the arch...", 3.0)
    end
    local liftoff = b.boomFrom or toWorldPoint(state, B.potato_home)
    local rate = b.fizzle and 1.2 or OPT.detonate_launch_mps * 0.5
    beginReturn(state, vec3(
      liftoff.x, liftoff.y, liftoff.z + fireDur * rate))
    return
  end

  -- phase == "live"
  setEffectActive(state, "cheer", false)
  local carrier = exactVehicle(b.carrier)
  if not carrier then
    beginReturn(state, b.potatoAt)
    return
  end
  if explodedPhysics(carrier) then
    local broken = b.carrier
    b.quarantined[broken] = true
    beginReturn(state, b.potatoAt)
    announce(state, "Carrier quarantined.", 2.5, "carrier_quarantined",
      {subject_id = broken})
    return
  end

  -- Re-arm the watch every tick: the framework's rebuildTriggers clears
  -- state.zones whenever ANY subject resets, and a one-shot registration in
  -- giveTo would be lost with it.
  state.zones.carrier_watch = {[b.carrier] = true}

  local anchor, rotation = carrierPose(state, carrier)
  posePotato(state, anchor, rotation)
  -- The wisp rolls off the crown over the roof, not out of the belly.
  poseEffectAt(
    state, "fuse", vec3(anchor.x, anchor.y, anchor.z + SMOKE_RISE))
  -- Anti-camping (v2.3): dawdling below camp_speed_kmh burns the shared
  -- fuse camp_burn_multiplier times faster. lastDelta is the wall-clock
  -- delta advanceClock actually applied this frame, so the extra burn is
  -- honest seconds and freezes with the sim exactly like the fuse does.
  if OPT.camp_burn_multiplier > 1.0 and b.fuseEnds then
    local okV, velocity = pcall(function() return carrier:getVelocity() end)
    if okV and finiteVector3(velocity)
      and velocity:length() < OPT.camp_speed_kmh / 3.6 then
      b.fuseEnds = b.fuseEnds
        - (OPT.camp_burn_multiplier - 1.0) * (b.lastDelta or 0)
    end
  end
  -- Hoarder mode (v2.4): holding the potato IS the game — a point a
  -- second, first to the target takes the crown and the fireworks. The
  -- potato still blows, and the boom halves the victim's hoard, so greed
  -- has a price. Protect mode (v2.6, "the reverse game type") scores the
  -- same held-seconds race, but the boom costs NOTHING — riding the fuse
  -- to the very end is the whole point, and the AI mob hunting you is the
  -- obstacle (detonate() halves hoarder scores only).
  if OPT.game_mode == "hoarder" or OPT.game_mode == "protect" then
    b.score = b.score or {}
    b.score[b.carrier] = (b.score[b.carrier] or 0) + (b.lastDelta or 0)
    if b.score[b.carrier] >= OPT.hoard_target_points then
      local crowned = b.carrier
      crownChampion(state, crowned, math.floor(b.score[crowned]))
      b.score = {}
      local okPos, position = pcall(function() return carrier:getPosition() end)
      if okPos and finiteVector3(position) then
        poseEffectAt(state, "cheer",
          vec3(position.x, position.y, position.z + 4.0))
      end
      setEffectActive(state, "cheer", true)
      playSound(SFX_WIN, 1.0, 1.0)
      beginReturn(state, b.potatoAt)
      return
    end
  end
  updateFuseCues(state, carrier, anchor, dtReal)
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
    beginReturn(state, b.potatoAt)
    celebrate(state, carrier)
    announce(state, "LAST CAR STANDING!", 4.0, "round_won",
      {subject_id = winner})
    return
  end
  if ((b.fuseEnds or b.now) - b.now) <= 0 then
    detonate(state, carrier)
  end
end

-- --------------------------------------------------------------------------
-- BeamMP replica protocol. The owning client keeps the existing state
-- machine as the authority; followers consume complete, idempotent snapshots
-- and render them without running pickup/pass/fuse/scoring decisions.
-- --------------------------------------------------------------------------

function Sync.vectorTable(value)
  if not finiteVector3(value) then return nil end
  return {value.x, value.y, value.z}
end

function Sync.readVector(value)
  if type(value) ~= "table" then return nil end
  local x, y, z = tonumber(value[1] or value.x),
    tonumber(value[2] or value.y), tonumber(value[3] or value.z)
  if not finiteNumber(x) or not finiteNumber(y) or not finiteNumber(z) then return nil end
  return vec3(x, y, z)
end

function Sync.nameForSid(state, sid)
  if type(sid) ~= "string" then return "" end
  local b = state.behavior
  if b.sync and b.sync.namesBySid and b.sync.namesBySid[sid] then
    return b.sync.namesBySid[sid]
  end
  local id = Sync.gameIdForSid(sid)
  return id and subjectName(state, id) or sid
end

function Sync.optionsWritable()
  for _, state in pairs(installations) do
    local sync = state.behavior.sync
    if sync and sync.mode ~= "standalone" and sync.mode ~= "authority" then
      return false
    end
  end
  return true
end

function Sync.status()
  local payload = {
    mode = Sync.isMPSession() and "pending" or "standalone",
    status = Sync.isMPSession() and "waiting for BeamMP relay" or "single-player",
    options_writable = Sync.optionsWritable(),
    arenas = {},
  }
  for _, state in pairs(installations) do
    local sync = state.behavior.sync
    if sync then
      local entry = {
        prop_id = state.propId,
        arena = sync.arena or "",
        mode = sync.mode,
        status = sync.status,
        epoch = sync.epoch or 0,
        revision = sync.revision or 0,
      }
      payload.arenas[#payload.arenas + 1] = entry
      if #payload.arenas == 1 then
        payload.mode = entry.mode
        payload.status = entry.status
        payload.arena = entry.arena
        payload.epoch = entry.epoch
        payload.revision = entry.revision
      end
    end
  end
  return payload
end

function Sync.encodeIdMap(state, source, timed)
  local payload = {}
  for id, value in pairs(source or {}) do
    local sid = Sync.sidForGameId(tonumber(id))
    if sid then
      if timed then
        payload[sid] = math.max(0, (tonumber(value) or state.behavior.now) - state.behavior.now)
      else
        payload[sid] = value
      end
    end
  end
  return payload
end

function Sync.decodeIdMap(state, source, timed)
  local restored = {}
  if type(source) ~= "table" then return restored end
  for sid, value in pairs(source) do
    local id = Sync.gameIdForSid(sid)
    if id then
      restored[id] = timed
        and state.behavior.now + math.max(0, tonumber(value) or 0)
        or value
    end
  end
  return restored
end

function Sync.optionSnapshot()
  local payload = {}
  for key in pairs(OPTION_RANGE) do payload[key] = OPT[key] end
  return payload
end

function Sync.applyOptions(payload)
  if type(payload) ~= "table" then return end
  for key, value in pairs(payload) do
    local coerced = coerceOption(key, value)
    if coerced ~= nil then OPT[key] = coerced end
  end
end

function Sync.snapshot(state)
  local b = state.behavior
  local remaining = b.fuseEnds and math.max(0, b.fuseEnds - b.now) or nil
  local names = {}
  for _, entry in ipairs(roster(state)) do
    local sid = Sync.sidForGameId(entry.id)
    if sid then names[sid] = subjectName(state, entry.id) end
  end
  local snapshot = {
    phase = b.phase or "idle",
    carrier_sid = b.carrier and Sync.sidForGameId(b.carrier) or b.carrierSid,
    fuse_remaining = remaining,
    held_elapsed = b.heldSince and math.max(0, b.now - b.heldSince) or 0,
    transfers = b.transfers or 0,
    field_peak = b.fieldPeak or 0,
    out_count = b.outCount or 0,
    pair_from_sid = b.pairFrom and Sync.sidForGameId(b.pairFrom) or nil,
    pair_to_sid = b.pairTo and Sync.sidForGameId(b.pairTo) or nil,
    pair_separated = b.pairSeparated == true,
    immune = Sync.encodeIdMap(state, b.immune, true),
    shield = Sync.encodeIdMap(state, b.shield, true),
    seen = Sync.encodeIdMap(state, b.seen, true),
    out = Sync.encodeIdMap(state, b.out, false),
    quarantined = Sync.encodeIdMap(state, b.quarantined, false),
    wins = Sync.encodeIdMap(state, b.wins, false),
    score = Sync.encodeIdMap(state, b.score, false),
    names = names,
    options = Sync.optionSnapshot(),
    potato_at = Sync.vectorTable(b.potatoAt),
    cheer_remaining = b.cheerUntil and math.max(0, b.cheerUntil - b.now) or 0,
  }
  if b.phase == "boom" then
    snapshot.boom = {
      elapsed = math.max(0, b.now - (b.boomAt or b.now)),
      fizzle = b.fizzle == true,
      fire_duration = b.fireDur or OPT.fire_seconds,
      from = Sync.vectorTable(b.boomFrom),
    }
  elseif b.phase == "return" then
    snapshot.return_flight = {
      elapsed = math.max(0, b.now - (b.retStart or b.now)),
      from = Sync.vectorTable(b.retFrom),
      cruise_z = b.retCruiseZ,
      up = b.retUp,
      cross = b.retCross,
      down = b.retDown,
    }
  end
  return snapshot
end

function Sync.quietRound(state)
  local b = state.behavior
  silenceTick(state)
  silenceWhistle(state)
  aiRelease(state)
  v26.armorRelease(state)
  v26.magnetRelease(state)
  b.phase = "idle"
  b.carrier = nil
  b.carrierSid = nil
  b.fuseEnds = nil
  b.heldSince = nil
  b.out = {}
  b.outCount = 0
  b.fieldPeak = 0
  b.transfers = 0
  b.immune = {}
  b.pairFrom, b.pairTo, b.pairSeparated = nil, nil, true
  state.zones.carrier_watch = nil
  setEffectActive(state, "blast", false)
  beaconLit(state, false)
  if b.ready then parkPotato(state) end
end

function Sync.init(state)
  local b = state.behavior
  b.sync = {
    mode = Sync.isMPSession() and "pending" or "standalone",
    status = Sync.isMPSession() and "waiting for BeamMP relay" or "single-player",
    arena = Sync.sidForGameId(state.propId),
    epoch = nil,
    revision = 0,
    serverSeq = 0,
    nextPublish = 0,
    nextRegister = 0,
    commandSeq = 0,
    seenCommands = {},
    namesBySid = {},
  }
  if Sync.isMPSession() then
    local adapter = Sync.transport()
    if adapter and type(adapter.registerProp) == "function" then
      pcall(adapter.registerProp, state.propId)
    end
  end
end

function Sync.unregister(state)
  local adapter = Sync.transport()
  if adapter and type(adapter.unregisterProp) == "function" then
    pcall(adapter.unregisterProp, state.propId)
  end
end

function Sync.publish(state, force)
  local b = state.behavior
  local sync = b.sync
  if not sync or sync.mode ~= "authority" then return false end
  if not force and (sync.nextPublish or 0) > b.now then return false end
  sync.nextPublish = b.now + Sync.PUBLISH_SECONDS
  local adapter = Sync.transport()
  if not adapter or type(adapter.publishState) ~= "function" then return false end
  local ok, sent = pcall(adapter.publishState, state.propId, Sync.snapshot(state))
  return ok and sent == true
end

function Sync.publishAll(force)
  local sent = false
  for _, state in pairs(installations) do
    if Sync.publish(state, force) then sent = true end
  end
  return sent
end

function Sync.sendCommand(state, name, fields, locallyApplied)
  local b = state.behavior
  local sync = b.sync
  if not sync or sync.mode ~= "authority" then return nil end
  sync.commandSeq = (sync.commandSeq or 0) + 1
  local eventId = string.format("%s:%s:%d", tostring(sync.arena or state.propId),
    tostring(sync.epoch or "pending"), sync.commandSeq)
  local command = {event_id = eventId, name = name}
  for key, value in pairs(fields or {}) do command[key] = value end
  if locallyApplied then sync.seenCommands[eventId] = true end
  local adapter = Sync.transport()
  if adapter and type(adapter.publishCommand) == "function" then
    pcall(adapter.publishCommand, state.propId, command)
  end
  return eventId
end

function Sync.findState(arena)
  for _, state in pairs(installations) do
    local b = state.behavior
    if b.sync then
      b.sync.arena = b.sync.arena or Sync.sidForGameId(state.propId)
      if b.sync.arena == arena then return state end
    end
  end
  return nil
end

function Sync.applySnapshot(state, snapshot)
  if type(snapshot) ~= "table" then return false end
  local phase = snapshot.phase
  if phase ~= "idle" and phase ~= "live" and phase ~= "boom" and phase ~= "return" then
    return false
  end
  local b = state.behavior
  local previousPhase = b.phase
  Sync.applyOptions(snapshot.options)
  b.phase = phase
  b.carrierSid = type(snapshot.carrier_sid) == "string" and snapshot.carrier_sid or nil
  b.carrier = b.carrierSid and Sync.gameIdForSid(b.carrierSid) or nil
  local remaining = tonumber(snapshot.fuse_remaining)
  b.fuseEnds = remaining and remaining >= 0 and b.now + remaining or nil
  b.heldSince = b.now - math.max(0, tonumber(snapshot.held_elapsed) or 0)
  b.transfers = math.max(0, tonumber(snapshot.transfers) or 0)
  b.fieldPeak = math.max(0, tonumber(snapshot.field_peak) or 0)
  b.outCount = math.max(0, tonumber(snapshot.out_count) or 0)
  b.immune = Sync.decodeIdMap(state, snapshot.immune, true)
  b.shield = Sync.decodeIdMap(state, snapshot.shield, true)
  b.seen = Sync.decodeIdMap(state, snapshot.seen, true)
  b.out = Sync.decodeIdMap(state, snapshot.out, false)
  b.quarantined = Sync.decodeIdMap(state, snapshot.quarantined, false)
  b.wins = Sync.decodeIdMap(state, snapshot.wins, false)
  b.score = Sync.decodeIdMap(state, snapshot.score, false)
  b.pairFrom = Sync.gameIdForSid(snapshot.pair_from_sid)
  b.pairTo = Sync.gameIdForSid(snapshot.pair_to_sid)
  b.pairSeparated = snapshot.pair_separated == true
  b.potatoAt = Sync.readVector(snapshot.potato_at) or b.potatoAt
  b.cheerUntil = b.now + math.max(0, tonumber(snapshot.cheer_remaining) or 0)
  if b.sync and type(snapshot.names) == "table" then
    for sid, name in pairs(snapshot.names) do
      if type(sid) == "string" and type(name) == "string" then
        b.sync.namesBySid[sid] = name
        local id = Sync.gameIdForSid(sid)
        if id then b.names[id] = name end
      end
    end
  end
  if phase == "live" and b.carrier then
    state.zones.carrier_watch = {[b.carrier] = true}
  else
    state.zones.carrier_watch = nil
  end
  if phase == "boom" then
    local boom = type(snapshot.boom) == "table" and snapshot.boom or {}
    b.boomAt = b.now - math.max(0, tonumber(boom.elapsed) or 0)
    b.fizzle = boom.fizzle == true
    b.fireDur = math.max(0, tonumber(boom.fire_duration) or OPT.fire_seconds)
    b.boomFrom = Sync.readVector(boom.from) or b.potatoAt
    if previousPhase ~= "boom" then
      silenceTick(state)
      silenceWhistle(state)
      beaconLit(state, false)
      if not b.fizzle then
        poseEffectAt(state, "blast", b.boomFrom or toWorldPoint(state, B.potato_home))
        setEffectActive(state, "blast", true)
        playSound(SFX_BOOM, 0.85, 1.0)
        if OPT.mash_enabled and b.boomFrom then
          spawnMash(state, b.boomFrom, b.boomFrom.z - 2.0)
        end
      end
    end
  elseif phase == "return" then
    local flight = type(snapshot.return_flight) == "table" and snapshot.return_flight or {}
    b.retStart = b.now - math.max(0, tonumber(flight.elapsed) or 0)
    b.retFrom = Sync.readVector(flight.from) or b.potatoAt
    b.retCruiseZ = tonumber(flight.cruise_z) or (b.retFrom and b.retFrom.z + 8.0) or 14.0
    b.retUp = math.max(0.01, tonumber(flight.up) or 2.2)
    b.retCross = math.max(0.01, tonumber(flight.cross) or 0.6)
    b.retDown = math.max(0.01, tonumber(flight.down) or 3.0)
  elseif previousPhase == "boom" then
    setEffectActive(state, "blast", false)
  end
  if b.sync then b.sync.lastStateAt = b.now end
  return true
end

function Sync.applyCommand(state, command)
  if type(command) ~= "table" or type(command.event_id) ~= "string" then return false end
  local b = state.behavior
  local sync = b.sync
  if not sync or sync.seenCommands[command.event_id] then return false end
  sync.seenCommands[command.event_id] = true
  local targetId = Sync.gameIdForSid(command.target_sid)
  local target = targetId and exactVehicle(targetId) or nil
  if command.name == "impulse" then
    local delta = Sync.readVector(command.delta)
    if target and delta and Sync.canMutate(target) then
      return addSubjectVelocity(state, target, delta)
    end
    return true
  end
  if command.name == "detonate" then
    if not target or not Sync.canMutate(target) or command.fizzle == true then return true end
    v26.sendArmor(state, target, "none")
    if command.break_vehicle == true then
      pcall(function() target:queueLuaCommand(BREAK_COMMAND) end)
    end
    if command.crush_vehicle == true then
      pcall(function() target:queueLuaCommand(string.format(CRUSH_TEMPLATE,
        tostring(command.crush_dv_mps or OPT.crush_dv_mps),
        tostring(command.crush_min_z or OPT.crush_min_z),
        tostring(command.crush_inward or OPT.crush_inward))) end)
    end
    if command.fire_vehicle == true then
      pcall(function() target:queueLuaCommand(FIRE_COMMAND) end)
    end
    local launch = tonumber(command.launch_mps) or 0
    if launch > 0 then launchSubject(state, target, vec3(0, 0, launch)) end
    return true
  end
  return true
end

function Sync.receive(packet)
  if type(packet) ~= "table" or packet.v ~= Sync.PROTOCOL
    or packet.game ~= Sync.GAME or type(packet.arena) ~= "string" then return false end
  if packet.epoch ~= nil and (not integer(packet.epoch) or packet.epoch < 0) then
    return false
  end
  local state = Sync.findState(packet.arena)
  if not state then return false end
  local b, sync = state.behavior, state.behavior.sync
  local serverSeq = tonumber(packet.seq)
  if not integer(serverSeq) or serverSeq < 0 then return false end
  local revision = tonumber(packet.revision) or 0
  local body = packet.body or packet.payload or {}
  if type(body) ~= "table" then return false end
  -- Relay reset/close packets start a new epoch at revision zero, so they
  -- must be handled before stale-revision and epoch guards.
  if packet.kind == "closed" or packet.kind == "reject" then
    Sync.quietRound(state)
    sync.mode = "pending"
    sync.status = packet.kind == "reject"
      and ("BeamMP rejected: " .. tostring(body.reason or "protocol"))
      or "BeamMP arena closed"
    sync.epoch = packet.epoch
    sync.revision = 0
    sync.serverSeq = serverSeq
    sync.nextRegister = b.now
    sync.seenCommands = {}
    return true
  end
  if packet.kind == "role" then
    if packet.epoch == sync.epoch and serverSeq <= (sync.serverSeq or 0) then
      return false
    end
    sync.arena = packet.arena
    sync.epoch = packet.epoch
    sync.revision = revision
    sync.serverSeq = serverSeq
    sync.seenCommands = {}
    local role = body.role
    if role ~= "authority" and role ~= "follower" then
      role = body.authority == true and "authority" or "follower"
    end
    local prop = exactVehicle(state.propId)
    if role == "authority" and Sync.canMutate(prop) then
      sync.mode = "authority"
      sync.status = "BeamMP authority"
      Sync.publish(state, true)
    else
      sync.mode = "follower"
      sync.status = "BeamMP synchronized"
      Sync.quietRound(state)
      if type(body.state) == "table" then Sync.applySnapshot(state, body.state) end
    end
    return true
  end
  if packet.epoch ~= nil and sync.epoch ~= nil and packet.epoch ~= sync.epoch then return false end
  if serverSeq <= (sync.serverSeq or 0) then return false end
  sync.serverSeq = serverSeq
  sync.revision = revision
  if packet.kind == "state" then
    if sync.mode == "follower" then
      return Sync.applySnapshot(state,
        type(body.state) == "table" and body.state or body)
    end
    return true
  end
  if packet.kind == "command" then return Sync.applyCommand(state, body) end
  return false
end

function Sync.transportChanged(info)
  if type(info) ~= "table" then return false end
  for _, state in pairs(installations) do
    local b = state.behavior
    if b.sync and (tonumber(info.game_id) == state.propId
      or info.arena == nil or b.sync.arena == nil or info.arena == b.sync.arena) then
      if info.connected == true then
        if b.sync.mode == "standalone" then Sync.quietRound(state) end
        b.sync.mode = "pending"
        b.sync.status = "waiting for BeamMP relay"
        b.sync.serverSeq = 0
        b.sync.arena = info.arena or b.sync.arena or Sync.sidForGameId(state.propId)
        local adapter = Sync.transport()
        if adapter and type(adapter.registerProp) == "function" then
          pcall(adapter.registerProp, state.propId)
        end
      else
        Sync.quietRound(state)
        loadOptions()
        b.sync.mode = "standalone"
        b.sync.status = "single-player"
        b.sync.epoch = nil
        b.sync.revision = 0
        b.sync.serverSeq = 0
      end
    end
  end
  return true
end

function Sync.renderReplica(state, dtSim, dtReal)
  local b = state.behavior
  if not b.sync or b.sync.mode == "pending" then
    parkPotato(state)
    return
  end
  if b.phase == "idle" then
    parkPotato(state)
    return
  end
  if b.phase == "return" then
    stepReturn(state)
    return
  end
  if b.phase == "boom" then
    local since = math.max(0, b.now - (b.boomAt or b.now))
    local anchor = b.boomFrom or b.potatoAt or toWorldPoint(state, B.potato_home)
    local rate = b.fizzle and 1.2 or OPT.detonate_launch_mps * 0.5
    local position = vec3(anchor.x, anchor.y, anchor.z + since * rate)
    posePotato(state, position,
      axisAngle(vec3(0.4, 0.2, 1.0), since * (b.fizzle and 1.2 or 3.5)))
    poseEffectAt(state, "fuse", vec3(position.x, position.y, position.z + SMOKE_RISE))
    return
  end
  b.carrier = b.carrier or Sync.gameIdForSid(b.carrierSid)
  local carrier = b.carrier and exactVehicle(b.carrier) or nil
  if not carrier then
    if b.potatoAt then posePotato(state, b.potatoAt, nil) end
    return
  end
  state.zones.carrier_watch = {[b.carrier] = true}
  local anchor, rotation = carrierPose(state, carrier)
  b.potatoAt = vec3(anchor.x, anchor.y, anchor.z)
  posePotato(state, anchor, rotation)
  poseEffectAt(state, "fuse", vec3(anchor.x, anchor.y, anchor.z + SMOKE_RISE))
  setEffectActive(state, "fuse", OPT.smoke_enabled and true or false)
  beaconLit(state, true)
  updateFuseCues(state, carrier, anchor, dtReal)
  applyCarrierBoost(state, carrier, dtSim)
end

behavior.init = function(state)
  local b = state.behavior
  if b.sync then Sync.unregister(state) end
  loadOptions()
  -- A prop reset arrives here with the previous round's state intact:
  -- silence the carrier's loops and release the AI BEFORE the wipe below
  -- forgets who had them.
  silenceTick(state)
  silenceWhistle(state)
  aiRelease(state)
  v26.armorRelease(state)
  v26.magnetRelease(state)
  b.phase = "idle"
  b.now = 0
  b.wallLast = nil
  b.spin = 0
  b.beaconAngle = 0
  b.beaconLit = nil
  b.carrier = nil
  b.carrierSid = nil
  b.fuseEnds = nil
  b.nextBeep = 0
  b.pulseUntil = 0
  b.fieldPeak = 0
  b.transfers = 0
  b.immune = {}
  b.seen = {}
  b.out = {}
  b.outCount = 0
  b.quarantined = {}
  b.extents = {}
  b.tickOn = nil
  b.tickLastSent = nil
  b.whistleOn = nil
  b.whistleLastSent = nil
  b.sputtered = false
  b.aiApplied = nil
  b.aiReturning = nil
  b.aiTuning = nil
  b.aiNextSweep = 0
  b.aiReturnNext = 0
  b.armorApplied = nil
  b.shield = nil
  b.armorNext = 0
  b.magnetApplied = nil
  b.arenaMembers = nil
  b.magnetNext = 0
  b.lastDelta = 0
  b.nextHush = 0
  b.silenced = false
  b.hopStart = nil
  b.glowLast = nil
  b.glowNext = nil
  b.boomStack = nil
  b.fizzle = false
  b.fireDur = nil
  b.mash = nil
  b.mashUntil = nil
  b.fw = nil
  b.nextHissAt = 0
  b.potatoAt = nil
  -- The champion ledger, the hoard scores and the name cache outlive
  -- rounds; only a prop init/reset clears them.
  b.wins = {}
  b.score = {}
  b.names = {}
  b.pairFrom, b.pairTo, b.pairSeparated = nil, nil, true
  b.ready = tunablesPresent(state)
  if not b.ready then return end
  Sync.init(state)
  ensureBeacon(state)
  setEffectActive(state, "fuse", false)
  setEffectActive(state, "blast", false)
  setEffectActive(state, "cheer", false)
  for i = 1, #(B.mash_homes or {}) do
    setEffectActive(state, "mash_steam_" .. i, false)
    setEffectActive(state, "mash_steam_b" .. i, false)
  end
  parkMash(state)
  parkPotato(state)
end

behavior.reset = function(state)
  behavior.init(state)
end

-- Framework teardown hook: cleanupInstallation calls this FIRST, while the
-- state still names what it owns. The scene-object sweep cannot see the
-- audio loop parked in the carrier's VM; without this, deleting the prop
-- mid-round leaves the tick beeping forever (the 2026-08-29 recording).
behavior.cleanup = function(state, reason)
  silenceTick(state)
  silenceWhistle(state)
  aiRelease(state)
  v26.armorRelease(state)
  v26.magnetRelease(state)
  Sync.unregister(state)
end

behavior.onEnter = function(state, zone, vehicle)
  -- Secondary pickup path. The sweep is authoritative and will usually have
  -- fired first; this is here so a trigger event is never simply ignored.
  local b = state.behavior
  if not b.ready or not Sync.isAuthority(state)
    or zone ~= "pad" or b.phase ~= "idle" then return end
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
  if not Sync.isAuthority(state) then
    b.carrier = nil
    state.zones.carrier_watch = nil
    return
  end
  -- The carrier vanished mid-round: the potato flies home and the fuse
  -- stops. Never silently pick a new victim, and never leave it orbiting a
  -- dead id.
  beginReturn(state, b.potatoAt)
  announce(state, "Potato returning to the arch.", 2.5, "carrier_lost",
    {subject_id = vehicleId, reason = reason})
end

behavior.update = function(state, dtSim, dtReal)
  local b = state.behavior
  if not b.ready then return end
  advanceClock(b, dtSim)
  b.spin = (b.spin + (dtSim or 0) * OPT.spin_rate) % (math.pi * 2)
  local active = Sync.isMPSession()
  if active and b.sync.mode == "standalone" then
    Sync.transportChanged({
      connected = true,
      game_id = state.propId,
      arena = Sync.sidForGameId(state.propId),
      reason = "session_detected",
    })
  elseif not active and b.sync.mode ~= "standalone" then
    Sync.transportChanged({
      connected = false,
      game_id = state.propId,
      arena = b.sync.arena,
      reason = "session_ended",
    })
  end
  -- Joining MP is fail-closed: until the relay elects the prop owner, no
  -- client runs local pickup/pass/fuse decisions. Registration is retried
  -- here as a backstop if the downloaded adapter loaded after this prop.
  if active and b.sync.mode == "pending"
    and (b.sync.nextRegister or 0) <= b.now then
    b.sync.nextRegister = b.now + 2.0
    local adapter = Sync.transport()
    if adapter and type(adapter.registerProp) == "function" then
      pcall(adapter.registerProp, state.propId)
    end
  end
  if Sync.isReplica(state) then
    Sync.renderReplica(state, dtSim, dtReal)
  else
    stepRound(state, dtSim, dtReal)
    -- The AI sweep runs on the phase stepRound just resolved, so a pass this
    -- frame flips hunter and hunted on the very next sweep. The containment
    -- heartbeat runs every frame under it (the slotTraffic watchdog is
    -- 0.5 s), and the armor sweep settles damage_mode and expired shields.
    stepAI(state)
    v26.stepAiReturn(state)
    v26.stepArmor(state)
    -- The arena magnet rides under both (v2.7): a standing physics-side
    -- gravity well per strayed member, so it needs only the 0.5 s sweep.
    v26.stepMagnet(state)
  end
  -- A synchronized follower applies canonical armor only to vehicles owned
  -- by this client. Pending clients stay entirely inert.
  if b.sync.mode == "follower" then v26.stepArmor(state) end
  -- The arena halo is immediate-mode: drawn only on frames a round runs.
  v26.drawArenaHalo(state)
  -- The HUD app's show-tester (v2.7): the hook parks the request here
  -- because only the behaviour frame holds the prop state.
  if v26.fwTest then
    local testName = v26.fwTest
    v26.fwTest = nil
    beginFireworks(state, testName ~= "" and testName or nil)
  end
  -- Phase-independent animations (v2.4): the mash splatter outlives the
  -- boom phase, and the champion fireworks play over whatever the round is
  -- doing next.
  stepMash(state)
  stepFireworks(state)
  Sync.publish(state, false)
  publishStats(state)
end

-- Mod controls. Exported as GE hooks, so the UI app, the console and any
-- future scenario all drive the same one surface:
--   extensions.ericrolph__hot__potato_runtime.hotPotatoSetOption("radius_m", 20)
-- (double underscores: BeamNG doubles literal underscores in extension names)
behavior.hooks = {
  hotPotatoGetOptions = function()
    if next(OPT) == nil then loadOptions() end
    local payload = {}
    for key in pairs(OPTION_RANGE) do payload[key] = OPT[key] end
    return payload
  end,
  -- The UI app builds its controls FROM this schema (v2.2, 2026-08-29), so
  -- OPTION_RANGE stays the single source of truth: a new option added above
  -- appears in the in-game panel with no app change and no drift. Numeric
  -- ranges become {kind="number", min, max}; "bool"/"enum" pass through as
  -- {kind="bool"} / {kind="enum", values}.
  hotPotatoGetOptionSchema = function()
    local schema = {}
    for key, range in pairs(OPTION_RANGE) do
      if range == "bool" then
        schema[key] = {kind = "bool"}
      elseif range == "enum" then
        schema[key] = {kind = "enum", values = OPTION_ENUM[key]}
      else
        schema[key] = {kind = "number", min = range[1], max = range[2]}
      end
    end
    return schema
  end,
  -- Live HUD readout: the payload publishStats refreshes each behaviour
  -- frame. The numeric countdown inside is gated by show_countdown; urgency
  -- ships always (the tick already broadcasts it audibly).
  hotPotatoGetStats = function()
    return LAST
  end,
  hotPotatoGetSyncStatus = function()
    return Sync.status()
  end,
  -- Called only by the downloaded BeamMP transport extension. Keeping the
  -- hook tiny preserves the prop-owned gameplay lifecycle.
  hotPotatoBeamMPReceive = function(packet)
    return Sync.receive(packet)
  end,
  hotPotatoBeamMPTransport = function(info)
    return Sync.transportChanged(info)
  end,
  hotPotatoSetOption = function(key, value)
    if next(OPT) == nil then loadOptions() end
    if not Sync.optionsWritable() then
      log("W", LOG_TAG, "BeamMP follower options are read-only")
      showMessage("Hot Potato options are controlled by the BeamMP authority.", 3)
      return false
    end
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
    Sync.publishAll(true)
    return true
  end,
  -- The show-tester (v2.7): one button in the HUD app fires a full
  -- fireworks pass without waiting for a champion — how a party host (and
  -- the live gate) proves the sky works. The request parks on v26 because
  -- hooks have no prop handle; the next behaviour frame owns the state and
  -- consumes it.
  hotPotatoTestFireworks = function(name)
    if next(OPT) == nil then loadOptions() end
    if not OPT.fireworks_enabled then
      showMessage("Hot Potato: fireworks are disabled", 3)
      return false
    end
    v26.fwTest = tostring(name or "")
    return true
  end,
  hotPotatoResetOptions = function()
    if not Sync.optionsWritable() then
      log("W", LOG_TAG, "BeamMP follower options are read-only")
      showMessage("Hot Potato options are controlled by the BeamMP authority.", 3)
      return false
    end
    seedOptions()
    saveOptions()
    Sync.publishAll(true)
    return true
  end,
}
"""
