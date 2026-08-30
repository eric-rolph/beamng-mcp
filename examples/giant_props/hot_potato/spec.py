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
MEDALLION_TOP_Z = 0.05
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
        "color": [0.87, 0.78, 0.52, 1.0],
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
    # guaranteed hearty knockback — bumper-car chaos.
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
  game_mode = {"classic", "hoarder", "pinball"},
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
  b.stats = {
    carrier = b.carrier or -1,
    fuse_remaining = remaining,
    field = b.fieldPeak or 0,
    eliminated = b.outCount or 0,
    transfers = b.transfers or 0,
    mode = OPT.transfer_mode,
  }
  -- The HUD payload. The numeric countdown is GATED behind show_countdown
  -- (the hidden fuse is the design; the option is the party-host override),
  -- but urgency ships always: it reveals nothing the accelerating tick is
  -- not already broadcasting in everyone's ears.
  LAST.phase = b.phase or "idle"
  LAST.carrier = b.carrier or -1
  LAST.carrier_name = b.carrier and subjectName(state, b.carrier) or ""
  local okPlayer, playerId = pcall(function() return be:getPlayerVehicleID(0) end)
  LAST.carrier_is_player =
    (okPlayer and b.carrier ~= nil and playerId == b.carrier) or false
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
  b.fuseEnds = nil
  b.silenced = false
  b.sputtered = false
  b.out = {}
  b.outCount = 0
  b.fieldPeak = 0
  b.pairFrom, b.pairTo, b.pairSeparated = nil, nil, true
  parkPotato(state)
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
local FW_PX = 1.05
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
-- plane the whole plaza can read.
local function fwPixelWorld(state, name, letterIndex, col, row, bloom)
  local width = #name * 6.0 * FW_PX - FW_PX
  local cx = -width * 0.5 + (letterIndex - 1) * 6.0 * FW_PX + 2.0 * FW_PX
  local cz = B.fireworks_base_z + 3.5 * FW_PX
  local x = cx + (col - 2.0) * FW_PX * bloom
  local z = cz + (4.0 - row) * FW_PX * bloom
  return toWorldPoint(state, vec3(x, 0.0, z))
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
  state.behavior.fw = {name = name, index = 1, stage = "launch", t0 = state.behavior.now}
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
    -- One shell rising from the apex toward the letter centre.
    local ease = smoothstep(t / FW_LAUNCH)
    local target = fwPixelWorld(state, name, fw.index, 2, 4, 1.0)
    local apex = toWorldPoint(state, vec3(0.0, 0.0, B.fireworks_base_z - 8.0))
    fwSetLight(state, 1, vec3(
      apex.x + (target.x - apex.x) * ease,
      apex.y + (target.y - apex.y) * ease,
      apex.z + (target.z - apex.z) * ease),
      {1.0, 0.9, 0.7}, 1.5 + ease * 2.0)
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
    for index, pixel in ipairs(pixels) do
      if index > FW_POOL then break end
      fwSetLight(state, index,
        fwPixelWorld(state, name, fw.index, pixel.col, pixel.row, bloom),
        color, 4.5 * fade * fade)
    end
    for index = #pixels + 1, FW_POOL do
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
  -- Finale: sparkle rain across the full width of the name.
  if t >= FW_FINALE then
    fwDouse(state)
    b.fw = nil
    return
  end
  local fade = 1.0 - t / FW_FINALE
  local width = count * 6.0 * FW_PX
  for index = 1, FW_POOL do
    if math.random() < 0.30 then
      local color = FW_COLORS[math.random(#FW_COLORS)]
      fwSetLight(state, index, toWorldPoint(state, vec3(
        (math.random() - 0.5) * width,
        (math.random() - 0.5) * 6.0,
        B.fireworks_base_z + math.random() * 9.0)),
        color, (1.5 + math.random() * 3.0) * fade)
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
          setPartPose(state, "mash_" .. i, vec3(0, 0, 0), quat(0, 0, 0, 1))
        end
      end
      if not chunk.gone then
        live = true
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
      playSputter(state, vehicle, 1.1, 0.9)
    end
    playSound(SFX_HISS, 0.9, 1.2, anchor)
    playSound(SFX_HISS_ALT, 1.3, 0.9, anchor)
    announce(state, "COOKED! The potato goes home.", 3.0, "fizzled",
      {subject_id = id})
    emitEvent(state, "I", "potato_fizzled", {subject_id = id})
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
            addSubjectVelocity(state, entry.vehicle, vec3(
              axis.x * OPT.blast_push_mps * falloff,
              axis.y * OPT.blast_push_mps * falloff,
              OPT.blast_push_mps * falloff * 0.35))
          end
        end
      end
    end
  end
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
        addSubjectVelocity(state, best, vec3(
          axis.x * knock,
          axis.y * knock,
          knock * 0.3))
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
  b.aiTuning = nil
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
  local present = {}
  for _, entry in ipairs(field) do
    local id = entry.id
    if id ~= playerId then
      present[id] = true
      local role
      if carrierId and id == carrierId then
        -- The hunter: chase the nearest other car — the player included —
        -- because touching someone is how the potato moves on.
        local best, bestDist = nil, nil
        local okPos, myPos = pcall(function() return entry.vehicle:getPosition() end)
        if okPos and finiteVector3(myPos) then
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
        role = best and ("chase:" .. best) or "stop"
      elseif carrierId then
        role = "flee:" .. carrierId
      else
        -- No round running: hold position and look innocent.
        role = "stop"
      end
      if b.aiApplied[id] ~= role then
        b.aiApplied[id] = role
        local mode, target = role:match("^(%a+):?(%d*)")
        if mode == "stop" then
          aiCommand(entry.vehicle, "pcall(function() ai.setMode('stop') end)")
        else
          aiCommand(entry.vehicle, string.format(
            "pcall(function() ai.setAggression(%.2f)"
            .. " ai.setSpeedMode('limit') ai.setSpeed(%.1f)"
            .. " ai.setTargetObjectID(%d) ai.setMode('%s') end)",
            OPT.ai_aggression, speedMps, tonumber(target), mode))
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
        playSputter(state, carrier, 0.9, 1.0)
      end
    else
      local wpitch = escalating and (1.0 - 0.28 * cueU) or 1.0
      driveWhistle(state, carrier, 0.5 + 0.1 * cueU, wpitch)
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
        launchSubject(state, victim, vec3(0, 0, OPT.detonate_launch_mps))
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
  -- has a price.
  if OPT.game_mode == "hoarder" then
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

behavior.init = function(state)
  local b = state.behavior
  loadOptions()
  -- A prop reset arrives here with the previous round's state intact:
  -- silence the carrier's loops and release the AI BEFORE the wipe below
  -- forgets who had them.
  silenceTick(state)
  silenceWhistle(state)
  aiRelease(state)
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
  b.quarantined = {}
  b.extents = {}
  b.tickOn = nil
  b.tickLastSent = nil
  b.whistleOn = nil
  b.whistleLastSent = nil
  b.sputtered = false
  b.aiApplied = nil
  b.aiTuning = nil
  b.aiNextSweep = 0
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
  ensureBeacon(state)
  setEffectActive(state, "fuse", false)
  setEffectActive(state, "blast", false)
  setEffectActive(state, "cheer", false)
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
  stepRound(state, dtSim, dtReal)
  -- The AI sweep runs on the phase stepRound just resolved, so a pass this
  -- frame flips hunter and hunted on the very next sweep.
  stepAI(state)
  -- Phase-independent animations (v2.4): the mash splatter outlives the
  -- boom phase, and the champion fireworks play over whatever the round is
  -- doing next.
  stepMash(state)
  stepFireworks(state)
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
