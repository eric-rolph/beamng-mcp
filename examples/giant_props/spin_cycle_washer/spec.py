"""Washing Machine Spin Cycle — authored constants for Blender + runtime.

A house-sized front loader. Drive up the ramp through the open porthole: the
glass door swings shut and the drum FILLS WITH WATER — the car starts to
float and bob as the level rises. Then the whole water body spins up: the
surface tilts and climbs the advancing wall, suds foam on top, and the car
is carried around the drum like laundry. After the spin cycle peaks, the
door flings open and the water drains out in a surge, hurling the car out
with it.

The water is a per-frame force field on the subject: buoyancy is a bobbing
controller toward the current waterline, and the swirl drags the car toward
the rotating water's local velocity (omega x r), capped so nothing exceeds
the water speed itself. The visible water is a translucent slab part whose
top rides the waterline (z-scaled to fill), tilting with spin; the ribbed
liner spins in sync with the water.
"""

import math

MOD_ID = "ericrolph_spin_cycle_washer"
DISPLAY_NAME = "Washing Machine Spin Cycle"
VALUE_DOLLARS = 34000
ZIP_BASENAME = "spin_cycle_washer_ericrolph.zip"

# Files under assets/ that must ship into the vehicle folder because the GAME
# opens them by path at runtime. The LCD webview loads
# local://local/vehicles/<mod>/lcd/screen.html, so the html has to exist on the
# player's disk; everything else under assets/ is a build input and stays home.
SHIP_ASSETS = ("lcd/screen.html",)

# Authored frame: right-handed, meters, Z-up, +Y drive direction. The car
# drives in from -Y through the porthole.
BODY_HALF = 6.5
BODY_TOP = 13.0
DRUM_AXIS_Z = 4.6
DRUM_RADIUS = 4.2
DRUM_Y_MIN = -6.0
DRUM_Y_MAX = 4.0
DRUM_BOTTOM_Z = DRUM_AXIS_Z - DRUM_RADIUS  # 0.4
DOOR_PIVOT = (3.7, -6.7, DRUM_AXIS_Z)
RAMP_GROUND_Y = -12.5
# Water slab authoring: pivot at the TOP centre so a z-scale about the DAE
# origin grows the body downward while the top surface stays on the
# waterline.
WATER_SLAB_HEIGHT = 6.0
WATER_PIVOT = (0.0, -1.0, DRUM_BOTTOM_Z)

# Front control strip (2026-08-13 look-and-feel round, grounded in real
# front-loader research: control band = top 12-18% of body height, drawer
# left / dial center / buttons+display right, dark graphite panel with
# printed white legends). All layout in the authored frame; the legend
# textures use the panel_legend (u, v-from-bottom) plate frame, so label
# positions are computed HERE from the same constants the generator uses
# for the plate geometry — print and hardware cannot drift.
STRIP_Z0, STRIP_H = 10.7, 2.2
DIAL_X, DIAL_RING_R = -1.35, 0.7
# 2.9 -> 2.6 (2026-08-13, player: "move the line that divides the dial from
# the buttons closer to the dial"): the visible divider IS the seam between
# the dial legend plate and the controls plate, so narrowing this plate
# moves the line left and gives the START ring breathing room. Label radii
# shrink with it so the outer ring of names stays on the plate.
DIAL_PLATE_W = 2.6  # plate is STRIP_H tall; aspect = W / STRIP_H

_DIAL_PROGRAMS = (
    "MAX SPIN", "COTTON", "ECO", "SYNTH", "WOOL",
    "SOFT", "RINSE", "DRAIN", "QUICK", "STEAM",
)
DIAL_LABELS = []
for _index, _name in enumerate(_DIAL_PROGRAMS):
    _angle = math.radians(90.0 - _index * 36.0)
    DIAL_LABELS.append((
        round(0.5 + 0.88 * math.cos(_angle) / DIAL_PLATE_W, 4),
        round(0.5 + 0.88 * math.sin(_angle) / STRIP_H, 4),
        _name, 0.62,
    ))
    DIAL_LABELS.append((
        round(0.5 + 0.72 * math.cos(_angle) / DIAL_PLATE_W, 4),
        round(0.5 + 0.72 * math.sin(_angle) / STRIP_H, 4),
        "•", 0.5,
    ))

# Touch controls to the right of the dial. 2026-08-13 rework (player: "we
# don't need a power button"): the ringed blue START takes the old POWER
# slot on the left, then the four option pads - and all five are REAL
# vehicle triggers now (hover tooltip + click), wired through the panel
# recipe to behavior.onPanelButton.
# X0 0.15 -> -0.01 with the right edge held at 4.4: the controls plate now
# starts just left of the START ring (divider-line move, see DIAL_PLATE_W).
CONTROLS_X0, CONTROLS_W = -0.01, 4.41
START_X = 0.55
BUTTON_XS = (1.55, 2.4, 3.25, 4.1)


def _cu(x: float) -> float:
    return round((x - CONTROLS_X0) / CONTROLS_W, 4)


# Range sub-labels removed 2026-08-13 (player) - the LCD chips carry the
# live values; the plate keeps only the button names.
CONTROLS_LABELS = [
    (_cu(START_X), 0.30, "START", 0.62),
    (_cu(BUTTON_XS[0]), 0.30, "TEMP", 0.62),
    (_cu(BUTTON_XS[1]), 0.30, "SPIN", 0.62),
    (_cu(BUTTON_XS[2]), 0.30, "SOIL", 0.62),
    (_cu(BUTTON_XS[3]), 0.30, "DELAY", 0.62),
]

# Interactive panel buttons (centrifuge round-15 recipe: per-button cage
# anchors 9 cm proud of the caps + per-button orthonormal frames). Titles
# are the in-game hover tooltips - ASCII only.
_BTN_Y = -BODY_HALF - 0.35
_BTN_Z = 11.85
PANEL_BUTTONS = (
    {"id": "btn_start", "title": "START - run a cycle (laundry optional)",
     "position": (START_X, _BTN_Y, _BTN_Z), "size": 0.8},
    {"id": "btn_temp", "title": "TEMP - water feel: 20 40 60 95 C",
     "position": (BUTTON_XS[0], _BTN_Y, _BTN_Z), "size": 0.7},
    {"id": "btn_spin", "title": "SPIN - drum speed: 400 to 1600 rpm",
     "position": (BUTTON_XS[1], _BTN_Y, _BTN_Z), "size": 0.7},
    {"id": "btn_soil", "title": "SOIL - heavy suds on or off",
     "position": (BUTTON_XS[2], _BTN_Y, _BTN_Z), "size": 0.7},
    {"id": "btn_delay", "title": "DELAY - extended cycle: levitating "
     "pre-soak plus longer phases",
     "position": (BUTTON_XS[3], _BTN_Y, _BTN_Z), "size": 0.7},
    # Program dial halves (2026-08-13, player: "make the dial functional so
    # it can turn counter clockwise or clockwise - split the mouse hover
    # button in half"). The knob face sits 0.9 m proud of the fascia, so
    # these anchors push further out than the flat buttons.
    {"id": "dial_ccw", "title": "PROGRAM DIAL - turn counter-clockwise",
     "position": (DIAL_X - 0.38, -BODY_HALF - 1.0, STRIP_Z0 + STRIP_H / 2),
     "size": 0.62},
    {"id": "dial_cw", "title": "PROGRAM DIAL - turn clockwise",
     "position": (DIAL_X + 0.38, -BODY_HALF - 1.0, STRIP_Z0 + STRIP_H / 2),
     "size": 0.62},
)
PANEL_FRAME_X = (START_X + 0.4, _BTN_Y, _BTN_Z)
PANEL_FRAME_Y = (START_X, _BTN_Y, _BTN_Z + 0.4)

PALETTE = {
    f"{MOD_ID}_enamel_white": {
        "texture": {
            "family": "painted_metal",
            "params": {"base": [0.92, 0.93, 0.94], "rough": 0.24, "peel": 0.6},
        },
        "color": [0.92, 0.93, 0.94, 1.0],
        "metallic": 0.1,
        "roughness": 0.25,
    },
    f"{MOD_ID}_enamel_gray": {
        "texture": {"family": "painted_metal", "params": {"base": [0.45, 0.47, 0.5], "rough": 0.4}},
        "color": [0.45, 0.47, 0.5, 1.0],
        "metallic": 0.2,
        "roughness": 0.4,
    },
    f"{MOD_ID}_drum_steel": {
        "texture": {"family": "drum_perforated"},
        "color": [0.68, 0.7, 0.74, 1.0],
        "metallic": 0.9,
        "roughness": 0.3,
        # The liner is an open tube seen from both sides (porthole view from
        # outside, drum wall from inside).
        "double_sided": True,
    },
    f"{MOD_ID}_glass_blue": {
        # Near-clear (2026-08-13, player: "view what's happening inside
        # through the window door"): the convex glass is double-sided, so
        # the eye crosses TWO surfaces and alpha compounds - 0.35 read as
        # a milky ~60% blue wall. 0.15 with a faint cool tint keeps a
        # glass cue while the drum interior stays visible.
        "color": [0.78, 0.86, 0.93, 0.15],
        "metallic": 0.0,
        "roughness": 0.05,
        "double_sided": True,
    },
    f"{MOD_ID}_wash_water": {
        # OCEAN-TECHNIQUE PASS (2026-08-13, player: "the water effect is
        # still lacking, can't we borrow how the BeamNG ocean works").
        # The real ocean shader belongs to the WaterPlane/WaterBlock/River
        # SCENE objects and cannot be attached to a mesh material - and a
        # spawned WaterBlock is useless here anyway (it cannot tilt, and
        # its water hydrolocks engines). So this copies the one place
        # BeamNG animates water on an ordinary mesh: italy's
        # `river_white_water`, which is TWO stages of the SAME maps
        # scrolled along nearly the same axis at a ~1.37x speed ratio, so
        # the beat between the layers hides the tile repeat.
        # It also borrows the ocean shader's own vocabulary where a PBR
        # material can express it: fine directional ripple normals (the
        # water_surface family is now a Gerstner-style wave spectrum
        # calibrated against ripple_nm.normal.dds), a UV wave on top of
        # the scroll (animFlags 5 = scroll|wave), near-mirror roughness
        # and a live cubemap for the fresnel-ish sheen the real shader
        # gets from its reflection pass.
        "texture": {
            "family": "water_surface",
            "size": 1024,
            # The ocean's ripple normals are STRONG; our default 2.0 baked
            # a nearly flat map that read as satin.
            "normal_strength": 7.0,
            # Deeper, more saturated than the old pale cyan: at 0.55 alpha
            # over a white drum the light tint washed out to near-white.
            "params": {"base": [0.16, 0.43, 0.58]},
        },
        # Alpha 0.55 -> 0.74: enough body to read as a filled drum while
        # a carried car still shows through.
        "color": [0.25, 0.5, 0.72, 0.74],
        "metallic": 0.0,
        "roughness": 0.05,
        "double_sided": True,
        "stage": {
            "animFlags": 5,  # scroll | wave
            "scrollDir": [0.03, -0.17],
            "scrollSpeed": 1.88,
            "waveType": "Sin",
            "waveAmp": 0.03,
            "waveFreq": 0.55,
            "useAnisotropic": True,
        },
        "stage1": {
            "inherit_maps": True,
            "animFlags": 1,
            # Same axis, 1.37x the rate: the river's anti-tiling trick.
            "scrollDir": [0.03, -0.34],
            "scrollSpeed": 1.29,
            "baseColorFactor": [1.0, 1.0, 1.0, 0.6],
            "metallicFactor": 0.0,
            "useAnisotropic": True,
        },
        "material": {
            "translucent": True,
            "castShadows": False,
            "dynamicCubemap": True,
        },
    },
    f"{MOD_ID}_suds_foam": {
        # PATCHY SUDS (2026-08-13). This was an untextured sheet spanning
        # nearly the whole waterline - a white lid the player saw INSTEAD
        # of the water, which is a big part of why the water kept reading
        # as lacking however good the ripples got. The family now ships an
        # opacity mask of broken foam rafts, so suds float in clumps and
        # the animated water shows through the gaps. It also scrolls,
        # slower than either water layer, the way real suds drift.
        "texture": {
            "family": "suds_foam",
            "size": 1024,
            "normal_strength": 3.0,
            "params": {"coverage": 0.52},
        },
        "color": [0.94, 0.96, 0.98, 1.0],
        "metallic": 0.0,
        "roughness": 0.72,
        "double_sided": True,
        "stage": {
            "animFlags": 1,
            "scrollDir": [0.02, -0.09],
            "scrollSpeed": 0.9,
        },
    },
    f"{MOD_ID}_dial_blue": {
        "color": [0.15, 0.35, 0.7, 1.0],
        "metallic": 0.0,
        "roughness": 0.4,
    },
    f"{MOD_ID}_gasket_rubber": {
        # Light-gray folded bellows, one of the strongest "real washer"
        # cues (research round 2026-08-13); was near-black.
        "color": [0.62, 0.63, 0.65, 1.0],
        "metallic": 0.0,
        "roughness": 0.8,
    },
    f"{MOD_ID}_chrome_trim": {
        "texture": {"family": "scribed_chrome"},
        "color": [0.9, 0.91, 0.93, 1.0],
        "metallic": 1.0,
        "roughness": 0.12,
    },
    f"{MOD_ID}_paddle_plastic": {
        "color": [0.84, 0.85, 0.87, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
    f"{MOD_ID}_foot_rubber": {
        "color": [0.09, 0.09, 0.1, 1.0],
        "metallic": 0.0,
        "roughness": 0.8,
    },
    f"{MOD_ID}_dial_legend": {
        "texture": {
            "family": "panel_legend",
            "size": 1024,
            "params": {
                "labels": DIAL_LABELS,
                "aspect": round(DIAL_PLATE_W / STRIP_H, 4),
                "frame": False,
            },
        },
        "color": [0.13, 0.14, 0.16, 1.0],
        "metallic": 0.4,
        "roughness": 0.4,
    },
    f"{MOD_ID}_controls_legend": {
        "texture": {
            "family": "panel_legend",
            "size": 1024,
            "params": {
                "labels": CONTROLS_LABELS,
                "aspect": round(CONTROLS_W / STRIP_H, 4),
                "frame": False,
            },
        },
        "color": [0.13, 0.14, 0.16, 1.0],
        "metallic": 0.4,
        "roughness": 0.4,
    },
    f"{MOD_ID}_display_lcd": {
        # LIVE screen (2026-08-13): the quad's emissive map is the dynamic
        # texture "@<mod>_lcd", filled at runtime by a CEF webview showing
        # assets/lcd/screen.html — the stock ETK800 dash-screen mechanism
        # (materialName "@etk800_gauges_screen" + htmlTexture.create). The
        # webview runs real Chromium, so the page's JS clock IS the
        # player's system clock, and the GE behavior streams the actual
        # cycle state (phase / drum rpm / water level) into it. Base stays
        # near-black glass so a failed webview reads as "screen off".
        "color": [0.012, 0.014, 0.02, 1.0],
        "metallic": 0.52,
        "roughness": 0.11,
        "stage": {
            "emissive": True,
            "emissiveFactor": [1.0, 1.0, 1.0],
            "emissiveIntensityNits": 800,
            "emissiveMap": f"@{MOD_ID}_lcd",
        },
        "material": {"dynamicCubemap": True},
    },
    # badge_plate DELETED 2026-08-13 (player: "make this look like a logo")
    # - the wordmark is now extruded chrome lettering + a blue underline,
    # centred over the door (marquee add_text_solid recipe).
    f"{MOD_ID}_energy_label": {
        # US-style EnergyGuide yellow card (2026-08-13), mounted on the
        # REAR panel like a real delivery sticker.
        # Real giant-drum numbers (2026-08-13): 554 m3 drum, ~360 m3 =
        # 95,000 gal per fill, ~10,500 kWh to heat a 40 C load, 295
        # loads/yr at $0.15/kWh -> ~$480k/yr, 3.1 GWh.
        "texture": {
            "family": "energy_label",
            "size": 1024,
            "params": {"cost": 480000, "lo": 210000, "hi": 740000,
                       "kwh": 3100000, "capacity": "19,600 cu ft (554 m3)",
                       "aspect": 0.74},
        },
        "color": [0.94, 0.95, 0.96, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
    f"{MOD_ID}_serial_plate": {
        # Rear rating plate: tiny white sticker with the electrical spec.
        "texture": {
            "family": "panel_legend",
            "size": 512,
            "params": {
                "base": [0.9, 0.91, 0.92],
                "ink": [0.15, 0.16, 0.18],
                "labels": [
                    [0.5, 0.72, "MAXSPIN WM-9000", 0.9],
                    [0.5, 0.42, "240V ~ 60Hz 12A", 0.75],
                    [0.5, 0.14, "SN 2026-08-4711", 0.6],
                ],
                "aspect": 1.5,
                "frame": True,
            },
        },
        "color": [0.9, 0.91, 0.92, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
    f"{MOD_ID}_brass_fitting": {
        # Hot/cold inlet valves: 3/4" garden-hose-thread brass.
        "color": [0.72, 0.55, 0.22, 1.0],
        "metallic": 1.0,
        "roughness": 0.35,
    },
    f"{MOD_ID}_hose_rubber": {
        # Corrugated gray drain hose.
        "color": [0.38, 0.4, 0.43, 1.0],
        "metallic": 0.0,
        "roughness": 0.85,
    },
    f"{MOD_ID}_cord_black": {
        "color": [0.08, 0.08, 0.09, 1.0],
        "metallic": 0.0,
        "roughness": 0.6,
    },
    f"{MOD_ID}_mark_hot": {
        "color": [0.75, 0.12, 0.1, 1.0],
        "metallic": 0.0,
        "roughness": 0.45,
    },
    f"{MOD_ID}_mark_cold": {
        "color": [0.1, 0.3, 0.75, 1.0],
        "metallic": 0.0,
        "roughness": 0.45,
    },
    # Realistic control hardware (2026-08-13 player pass): satin
    # stainless button caps, dark soft-touch knob shell, glossy blue
    # START dome with a live reflection.
    f"{MOD_ID}_button_satin": {
        "texture": {
            "family": "brushed_metal",
            "params": {"base": [0.8, 0.81, 0.83], "rough": 0.3},
        },
        "color": [0.8, 0.81, 0.83, 1.0],
        "metallic": 0.85,
        "roughness": 0.3,
    },
    f"{MOD_ID}_knob_shell": {
        "texture": {
            "family": "bakelite",
            "params": {"base": [0.13, 0.135, 0.15]},
        },
        "color": [0.13, 0.135, 0.15, 1.0],
        "metallic": 0.1,
        "roughness": 0.35,
    },
    f"{MOD_ID}_start_glass": {
        "color": [0.14, 0.36, 0.78, 1.0],
        "metallic": 0.0,
        "roughness": 0.08,
        "material": {"dynamicCubemap": True},
    },
    f"{MOD_ID}_console_graphite": {
        "texture": {
            "family": "brushed_metal",
            "params": {"base": [0.28, 0.29, 0.32], "rough": 0.4},
        },
        "color": [0.28, 0.29, 0.32, 1.0],
        "metallic": 0.6,
        "roughness": 0.4,
    },
    f"{MOD_ID}_drum_spider": {
        # Hub + spokes of the drum spider. These used to wear the
        # PERFORATED drum texture on plain box UVs, which stretched the
        # hole grid into long dark slashes down every arm (visible the
        # moment the back plate's holes were fixed, 2026-08-13). A real
        # drum spider is a solid cast/brushed stainless part - no holes.
        "texture": {
            "family": "brushed_metal",
            "params": {"base": [0.66, 0.68, 0.72], "rough": 0.28},
        },
        "color": [0.66, 0.68, 0.72, 1.0],
        "metallic": 0.9,
        "roughness": 0.28,
    },
    f"{MOD_ID}_drum_lamp": {
        "color": [0.7, 0.6, 0.42, 1.0],
        "metallic": 0.0,
        "roughness": 0.4,
        # THREE components, not four (2026-08-15, round 18). This was
        # [1.0, 0.88, 0.62, 1.0] and rendered inert, which is why this mod has
        # shipped with a WORKING glow on display_lcd (three components, 800
        # nit, right below) and a dead one on the drum lamp two hundred lines
        # later. Same file, same builder, one element apart. AGENTS.md,
        # "Round-16/17: the photometric ledger".
        "emissive": [1.0, 0.88, 0.62],
        # 800 nit, matching display_lcd: the two lit fixtures on this machine
        # should agree, and a drum lamp behind the glass door is a luminaire -
        # blowing out at night is what one does. The warm factor survives, so
        # it stays tungsten against the LCD's white.
        "stage": {"emissiveIntensityNits": 800},
    },
    f"{MOD_ID}_drum_bright": {
        # Drum BACK PLATE. Unlike the liner (which tiles every 1.9 m) this
        # texture is stretched 1:1 over the whole 8.3 m disc, so its
        # resolution is the plate's resolution. 2026-08-13 (player: the
        # holes look "blotchy or low resolution"): 1024 px with 10 rows
        # of 0.012-UV holes put ~12 stair-stepped pixels behind each
        # half-metre pothole. 2048 px with 30 rows of 0.006-UV holes is a
        # dense 28 cm-pitch perforation of ~5 cm holes - real drum-plate
        # proportions - and the family now anti-aliases every edge.
        "texture": {
            "family": "drum_perforated",
            "size": 2048,
            "params": {"base": [0.62, 0.64, 0.68], "rows": 30,
                       "hole": 0.006},
        },
        "color": [0.66, 0.68, 0.72, 1.0],
        "metallic": 0.85,
        "roughness": 0.3,
    },
    f"{MOD_ID}_ramp_asphalt": {
        "texture": {"family": "asphalt"},
        "color": [0.16, 0.16, 0.17, 1.0],
        "metallic": 0.0,
        "roughness": 0.9,
    },
}

TRIGGERS = {
    "drum_zone": {
        "mode": "Contains",
        # Bottom reaches 0.6 m below the drum floor (z 0.4): settling
        # vehicle OOBBs dip below the surface and Contains flaps without the
        # allowance (proven live 2026-07-22).
        "center": [0.0, -1.0, 3.9],
        "dimensions": [7.0, 9.6, 8.2],
    },
    "approach_zone": {
        "mode": "Overlaps",
        "center": [0.0, -9.5, 2.0],
        "dimensions": [6.0, 5.5, 4.0],
    },
}

EFFECTS = {
    "suds_mist": {
        "emitter": "BNGP_waterfallsteam",
        "position": [0.0, -1.0, 5.8],
        "direction": [0.0, 0.0, 1.0],
    },
    "fill_spray": {
        "emitter": "BNGP_sprinkler",
        "position": [0.0, 2.8, 7.6],
        "direction": [0.0, -0.4, -0.9],
    },
    "door_steam": {
        "emitter": "BNGP_34",
        "position": [0.0, -6.8, 4.8],
        "direction": [0.0, -0.8, 0.6],
    },
}

BEHAVIOR = {
    "camera_distance": 38.0,
    "door_close_seconds": 1.0,
    "fill_seconds": 3.0,
    "wash_seconds": 4.0,
    "spin_seconds": 5.0,
    "door_fling_seconds": 0.25,
    "eject_delay_seconds": 0.3,
    "drain_seconds": 1.0,
    "cooldown_seconds": 3.0,
    "door_open_angle_deg": -110.0,
    # Water body.
    "max_water_depth": 5.2,
    "water_slab_height": WATER_SLAB_HEIGHT,
    "drum_bottom_z": DRUM_BOTTOM_Z,
    "water_pivot_y": -1.0,
    "slosh_omega": 0.6,
    "wash_omega": 2.8,
    "spin_omega": 8.0,
    "water_speed_cap": 18.0,
    "water_drag_rate": 2.5,
    "tilt_per_omega": 0.1,
    "tilt_max": 0.85,
    "surface_wobble": 0.06,
    # Buoyancy bobbing controller.
    "buoy_spring": 1.8,
    "buoy_bob_cap": 2.5,
    "buoy_gain": 3.0,
    "gravity_comp": 9.81,
    "axial_centering": 2.0,
    "frame_dv_cap": 2.0,
    # Eject with the drain surge.
    "eject_out_mps": 24.0,
    "eject_up_mps": 9.0,
    "drum_center": [0.0, -1.0, DRUM_AXIS_Z],
}

LUA_BEHAVIOR = r"""
local function doorAngle(state, angleDeg)
  setPartPose(state, "door", nil, axisAngle(vec3(0, 0, 1), math.rad(angleDeg)))
end

local function poseWater(state)
  local b = state.behavior
  local level = b.waterLevel or 0
  local scale = math.max(0.02, (level + 0.4) / B.water_slab_height)
  local tilt = math.min(B.tilt_max, (b.omega or 0) * B.tilt_per_omega)
  -- SLOSH SCALES WITH SPIN (2026-08-13, player: "the spin cycle RPM
  -- strength should make the water much more sloshy depending on speed"):
  -- wobble amplitude AND frequency grow with omega, plus a second rocking
  -- axis (front-back about X) so the surface pitches as well as rolls.
  local om = math.min(1.5, (b.omega or 0) / 8.0)
  local depthGate = math.min(1, level)
  local wobble = math.sin((b.clock or 0) * (3.5 + 6.0 * om))
    * B.surface_wobble * (1.0 + 3.2 * om) * depthGate
  local rock = math.cos((b.clock or 0) * (2.6 + 4.5 * om))
    * B.surface_wobble * (0.5 + 2.4 * om) * depthGate
  local rotation = axisAngle(vec3(0, 1, 0), tilt + wobble)
    * axisAngle(vec3(1, 0, 0), rock)
  setPartPose(state, "water_body", vec3(0, 0, level), rotation, vec3(1, 1, scale))
  -- Foam is a sheet SCULPTED to the water surface (2026-08-13 slosh
  -- pass): its 6 cm float offset is baked into the mesh, so it poses at
  -- exactly the waterline and rocks on the same rotation - a flat slab at
  -- +0.02 knifed through the new wave crests and read as white ice floes.
  -- SOIL=off still parks it entirely; suds are a soil thing.
  local soilOn = (b.settings == nil) or (b.settings.soil ~= false)
  if level > 0.25 and soilOn then
    setPartPose(state, "suds_foam", vec3(0, 0, level), rotation,
      vec3(1, 1, 1))
  else
    -- Park the foam out of sight below the drum floor while empty.
    setPartPose(state, "suds_foam", vec3(0, 0, -2.0), nil, vec3(1, 1, 1))
  end
end

-- Panel settings (2026-08-13, player rework): the fascia buttons are real
-- vehicle triggers and each one bends the machine. Settings survive reset.
local TEMP_STEPS = {20, 40, 60, 95}
-- Water FEEL per temperature: cold wash is arctic molasses (hard drag
-- coupling, low terminal speed, weak buoyancy), hot wash is steam-slick
-- (loose coupling, fast water, floaty).
local TEMP_FEEL = {
  {drag = 4.5, cap = 9.0, buoy = 1.6},
  {drag = 2.5, cap = 18.0, buoy = 3.0},
  {drag = 1.7, cap = 23.0, buoy = 3.8},
  {drag = 1.1, cap = 30.0, buoy = 4.8},
}
local SPIN_STEPS = {400, 600, 800, 1000, 1200, 1400, 1500, 1600}

-- Program dial (2026-08-13, player: "the dial should adjust how far the
-- vehicle gets spit out and if it gets spun around horizontally or
-- vertically... at a higher angle or low angle with or without different
-- spins"). One entry per printed label, clockwise from 12 o'clock. out/up
-- scale the eject velocity; axis+rate add angular velocity on the way out
-- (yaw = flat horizontal spin, pitch = end-over-end flips, roll =
-- corkscrew about the flight path). No extra labelling anywhere - the
-- knob names ARE the documentation.
local DIAL_EJECT = {
  {name = "MAX SPIN", out = 1.35, up = 1.1, axis = "roll", rate = 9.0},
  {name = "COTTON", out = 1.0, up = 1.0},
  {name = "ECO", out = 0.55, up = 0.7},
  {name = "SYNTH", out = 0.9, up = 0.9, axis = "yaw", rate = 6.0},
  {name = "WOOL", out = 0.6, up = 1.5, axis = "pitch", rate = 4.0},
  {name = "SOFT", out = 0.35, up = 0.45},
  {name = "RINSE", out = 1.15, up = 0.3},
  {name = "DRAIN", out = 0.45, up = 0.12},
  {name = "QUICK", out = 1.5, up = 0.35, axis = "yaw", rate = 3.0},
  {name = "STEAM", out = 0.7, up = 1.9, axis = "pitch", rate = 8.0},
}

local function settingsOf(state)
  local b = state.behavior
  if not b.settings then
    b.settings = {temp = 2, spin = 6, soil = true, delay = false, dial = 2}
  end
  return b.settings
end

local function dialProgram(state)
  return DIAL_EJECT[settingsOf(state).dial or 2] or DIAL_EJECT[2]
end

-- DELAY = the cycle takes longer (2026-08-13, player: "make the DELAY
-- button add time to the wash cycle"): every wet phase stretches 1.6x and
-- an 8 s levitating pre-soak fronts the program.
local function timeScale(state)
  return settingsOf(state).delay and 1.6 or 1.0
end

-- The knob mesh is a posable part: ease the shown angle toward the detent
-- so presses read as a servo-driven twist (36 degrees per program,
-- positive Y rotation = clockwise from the front in this frame).
local function poseDial(state, dtSim)
  local b = state.behavior
  local target = math.rad(36.0) * ((settingsOf(state).dial or 2) - 1)
  local shown = b.dialShown or target
  local diff = target - shown
  while diff > math.pi do diff = diff - 2 * math.pi end
  while diff < -math.pi do diff = diff + 2 * math.pi end
  shown = shown + diff * math.min(1, (dtSim or 1) * 9.0)
  b.dialShown = shown
  setPartPose(state, "dial", nil, axisAngle(vec3(0, 1, 0), shown))
end

local function tempFeel(state)
  return TEMP_FEEL[settingsOf(state).temp] or TEMP_FEEL[2]
end

-- 1400 rpm is the machine's design point; the 8 SPIN steps scale every
-- omega (and the eject kick) around it.
local function omegaScale(state)
  return SPIN_STEPS[settingsOf(state).spin] / 1400.0
end

-- SOIL gates every particle emitter (player: on = more effects, off =
-- none). All cycle-driven effect calls route through here so fxWanted
-- remembers intent and a mid-cycle SOIL toggle can re-apply it.
local function soilFx(state, name, active)
  local b = state.behavior
  b.fxWanted = b.fxWanted or {}
  b.fxWanted[name] = active or false
  setEffectActive(state, name, (active and settingsOf(state).soil) or false)
end

behavior.init = function(state)
  state.behavior.phase = "idle"
  state.behavior.elapsed = 0
  state.behavior.clock = 0
  state.behavior.drumAngle = 0
  state.behavior.omega = 0
  state.behavior.waterLevel = 0
  state.behavior.tracked = {}
  doorAngle(state, B.door_open_angle_deg)
  poseWater(state)
  poseDial(state)
end

behavior.reset = function(state)
  behavior.init(state)
  state.behavior.fxWanted = {}
  setEffectActive(state, "suds_mist", false)
  setEffectActive(state, "fill_spray", false)
  setEffectActive(state, "door_steam", false)
end

behavior.onEnter = function(state, zone, vehicle)
  local b = state.behavior
  if zone == "approach_zone" and b.phase == "idle" then
    showMessage("Delicates cycle? No. MAXIMUM SPIN.", 2.2)
  elseif zone == "drum_zone" and b.phase == "idle" then
    b.phase = "loading"
    b.elapsed = 0
    b.subjectId = vehicle:getId()
    showMessage("Load detected. Closing door...", 1.8)
    emitEvent(state, "I", "washer_loaded", {subject_id = vehicle:getId()})
  end
end

behavior.onExit = function(state, zone, vehicleId)
  local b = state.behavior
  if zone == "drum_zone"
    and (b.phase == "loading" or b.phase == "presoak"
      or b.phase == "filling")
    and b.subjectId ~= nil
    and zoneCount(state, "drum_zone") == 0 then
    b.phase = "aborting"
    b.elapsed = 0
    soilFx(state, "suds_mist", false)
    soilFx(state, "fill_spray", false)
    showMessage("The laundry escaped!", 1.6)
    emitEvent(state, "I", "washer_aborted", {subject_id = vehicleId})
  end
end

behavior.onSubjectGone = function(state, vehicleId, reason)
  local b = state.behavior
  b.tracked[vehicleId] = nil
  if b.subjectId == vehicleId
    and (b.phase == "loading" or b.phase == "presoak"
      or b.phase == "filling"
      or b.phase == "washing" or b.phase == "spincycle") then
    b.phase = "aborting"
    b.elapsed = 0
    soilFx(state, "suds_mist", false)
    soilFx(state, "fill_spray", false)
  end
end

local function applyWaterForces(state, dtSim)
  local b = state.behavior
  if dtSim <= 0 or (b.waterLevel or 0) <= 0.2 then return end
  -- TEMP button rewrites the water's personality live (2026-08-13).
  local feel = tempFeel(state)
  local center = toWorldPoint(state, B.drum_center)
  local axis = toWorldDir(state, vec3(0, 1, 0))
  local waterZ = toWorldPoint(
    state, vec3(0, B.water_pivot_y, B.drum_bottom_z + b.waterLevel)).z
  for vehicleId in pairs(zoneOccupants(state, "drum_zone")) do
    local vehicle = exactVehicle(vehicleId)
    if vehicle then
      local position = vehicle:getPosition()
      local track = b.tracked[vehicleId]
      local velocity = vec3(0, 0, 0)
      if track then
        velocity = (position - track.position) * (1 / dtSim)
      end
      b.tracked[vehicleId] = {position = vec3(position.x, position.y, position.z)}
      if track then
        local depth = waterZ - position.z
        local delta = vec3(0, 0, 0)
        if depth > 0 then
          -- Bob toward the waterline plus partial weight support.
          local desired = math.max(
            -B.buoy_bob_cap, math.min(B.buoy_bob_cap, B.buoy_spring * depth))
          delta.z = (desired - velocity.z) * math.min(1, dtSim * feel.buoy)
            + B.gravity_comp * dtSim * math.min(1, depth / 0.8)
        end
        -- Drag toward the spinning water's local velocity field.
        local offset = position - center
        local along = offset:dot(axis)
        local radial = offset - axis * along
        if radial:length() > 0.3 and (b.omega or 0) > 0.05 then
          local field = axis:cross(radial) * b.omega
          if field:length() > feel.cap then
            field:normalize()
            field = field * feel.cap
          end
          local slip = field - velocity
          slip.z = 0
          delta = delta + slip * math.min(0.6, dtSim * feel.drag)
        end
        delta = delta - axis * (along * B.axial_centering * dtSim * 0.2)
        if delta:length() > B.frame_dv_cap then
          delta:normalize()
          delta = delta * B.frame_dv_cap
        end
        addSubjectVelocity(state, vehicle, delta)
      end
    end
  end
end

-- DELAY's party trick: an anti-gravity pre-soak. Before any water shows
-- up, the drum tractor-beams its load to the centre and holds it floating
-- and slowly turning - in full view through the door glass.
local function applyPresoakLift(state, dtSim)
  local b = state.behavior
  if dtSim <= 0 then return end
  local center = toWorldPoint(state, B.drum_center)
  for vehicleId in pairs(zoneOccupants(state, "drum_zone")) do
    local vehicle = exactVehicle(vehicleId)
    if vehicle then
      local position = vehicle:getPosition()
      local track = b.tracked[vehicleId]
      local velocity = vec3(0, 0, 0)
      if track then
        velocity = (position - track.position) * (1 / dtSim)
      end
      b.tracked[vehicleId] = {position = vec3(position.x, position.y, position.z)}
      if track then
        local delta = (center - position) * (1.2 * dtSim)
          - velocity * math.min(0.5, dtSim * 2.5)
        delta.z = delta.z + B.gravity_comp * dtSim * 1.05
        if delta:length() > B.frame_dv_cap then
          delta:normalize()
          delta = delta * B.frame_dv_cap
        end
        addSubjectVelocity(state, vehicle, delta)
      end
    end
  end
end

local function ejectSubject(state)
  local b = state.behavior
  local vehicle = b.subjectId and exactVehicle(b.subjectId) or nil
  if not vehicle then vehicle = firstOccupant(state, "drum_zone") end
  if not vehicle then return end
  local out = toWorldDir(state, vec3(0, -1, 0))
  local up = toWorldDir(state, vec3(0, 0, 1))
  local lateral = toWorldDir(state, vec3(1, 0, 0))
  -- SPIN setting decides how hard the drain surge throws the load; the
  -- program dial shapes the throw (distance, launch angle, spin).
  local prog = dialProgram(state)
  local kick = 0.35 + 0.65 * omegaScale(state)
  local velocity = out * (B.eject_out_mps * kick * (prog.out or 1))
    + up * (B.eject_up_mps * kick * (prog.up or 1))
  showMessage("SPIN CYCLE COMPLETE! Draining...", 2.0)
  if launchSubject(state, vehicle, velocity) then
    if prog.axis then
      -- Angular kick via the stock vehicle-side thrusters extension:
      -- applyAccel(linAccel, seconds, nodeId, angAccel) integrates the
      -- angular acceleration per physics step for the given window
      -- (lua/vehicle/thrusters.lua), so rate/window = target rad/s.
      local axisVec = up
      if prog.axis == "pitch" then axisVec = lateral
      elseif prog.axis == "roll" then axisVec = out end
      local window = 0.45
      local acc = axisVec * ((prog.rate or 0) / window)
      vehicle:queueLuaCommand(string.format(
        "thrusters.applyAccel(vec3(0,0,0), %.3f, nil, vec3(%.4f,%.4f,%.4f))",
        window, acc.x, acc.y, acc.z))
    end
    emitEvent(state, "I", "washer_ejected", {subject_id = vehicle:getId()})
    soilFx(state, "door_steam", true)
  end
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  b.clock = b.clock + dtSim
  b.elapsed = b.elapsed + dtSim

  if b.phase == "idle" then
    b.omega = 0
    b.waterLevel = math.max(0, (b.waterLevel or 0) - dtSim * 2)
    doorAngle(state, B.door_open_angle_deg)
  elseif b.phase == "loading" then
    local t = math.min(1, b.elapsed / B.door_close_seconds)
    doorAngle(state, B.door_open_angle_deg * (1 - t * t))
    if t >= 1 then
      b.elapsed = 0
      if settingsOf(state).delay then
        b.phase = "presoak"
        showMessage("DELAY PRE-SOAK: gravity is for dirty laundry.", 2.4)
        emitEvent(state, "I", "washer_presoak", {})
      else
        b.phase = "filling"
        soilFx(state, "fill_spray", true)
        showMessage("Filling with water...", 2.0)
        emitEvent(state, "I", "washer_filling", {})
      end
    end
  elseif b.phase == "presoak" then
    b.waterLevel = 0
    b.omega = 0.35
    applyPresoakLift(state, dtSim)
    if b.elapsed >= 8.0 then
      b.phase = "filling"
      b.elapsed = 0
      soilFx(state, "fill_spray", true)
      showMessage("Filling with water...", 2.0)
      emitEvent(state, "I", "washer_filling", {})
    end
  elseif b.phase == "filling" then
    local t = math.min(1, b.elapsed / (B.fill_seconds * timeScale(state)))
    b.waterLevel = B.max_water_depth * t
    b.omega = B.slosh_omega * t * omegaScale(state)
    applyWaterForces(state, dtSim)
    if t >= 1 then
      b.phase = "washing"
      b.elapsed = 0
      soilFx(state, "fill_spray", false)
      soilFx(state, "suds_mist", true)
      showMessage("Wash cycle: the water begins to spin...", 2.0)
      emitEvent(state, "I", "washer_spinup", {})
    end
  elseif b.phase == "washing" then
    local t = math.min(1, b.elapsed / (B.wash_seconds * timeScale(state)))
    b.omega = (B.slosh_omega + (B.wash_omega - B.slosh_omega) * t)
      * omegaScale(state)
    applyWaterForces(state, dtSim)
    if t >= 1 then
      b.phase = "spincycle"
      b.elapsed = 0
      showMessage("MAXIMUM SPIN", 1.6)
    end
  elseif b.phase == "spincycle" then
    local spinSpan = B.spin_seconds * timeScale(state)
    local t = math.min(1, b.elapsed / spinSpan)
    b.omega = (B.wash_omega + (B.spin_omega - B.wash_omega) * t * t)
      * omegaScale(state)
    applyWaterForces(state, dtSim)
    if b.elapsed >= spinSpan then
      b.phase = "ejecting"
      b.elapsed = 0
      b.ejected = false
      soilFx(state, "suds_mist", false)
    end
  elseif b.phase == "ejecting" then
    local t = math.min(1, b.elapsed / B.door_fling_seconds)
    doorAngle(state, B.door_open_angle_deg * t * t)
    b.waterLevel = math.max(
      0, B.max_water_depth * (1 - b.elapsed / B.drain_seconds))
    b.omega = math.max(0, (b.omega or 0) - dtSim * 6)
    if not b.ejected and b.elapsed >= B.eject_delay_seconds then
      b.ejected = true
      ejectSubject(state)
    end
    if b.ejected and b.elapsed >= B.drain_seconds + 0.5 then
      b.phase = "cooldown"
      b.elapsed = 0
      soilFx(state, "door_steam", false)
    end
  elseif b.phase == "aborting" then
    local t = math.min(1, b.elapsed / B.door_close_seconds)
    doorAngle(state, B.door_open_angle_deg * t)
    b.waterLevel = math.max(0, (b.waterLevel or 0) - dtSim * 4)
    b.omega = math.max(0, (b.omega or 0) - dtSim * 4)
    if t >= 1 and b.waterLevel <= 0 then
      b.phase = "idle"
      b.elapsed = 0
      b.subjectId = nil
      b.tracked = {}
    end
  elseif b.phase == "cooldown" then
    b.waterLevel = 0
    b.omega = 0
    if b.elapsed >= B.cooldown_seconds then
      b.phase = "idle"
      b.elapsed = 0
      b.subjectId = nil
      b.tracked = {}
      emitEvent(state, "I", "washer_rearmed", {})
    end
  end

  b.drumAngle = b.drumAngle + (b.omega or 0) * dtSim
  setPartPose(state, "drum_liner", nil, axisAngle(vec3(0, 1, 0), b.drumAngle))
  poseWater(state)
  poseDial(state, dtSim)
end

-- LCD MIRROR (2026-08-13): stream the real machine state to the washer's
-- vehicle VM, where the bootstrap (VEHICLE_LUA_EXTRA) forwards it into the
-- live html screen. Wraps behavior.update so the cycle logic above stays
-- untouched. Pushes at 2.5 Hz, immediately on every phase change, and
-- immediately on every panel-button press.
local function lcdSpans(state)
  -- Spans mirror the live settings: DELAY stretches the wet phases 1.6x
  -- and prepends the 8 s levitating pre-soak.
  local ts = timeScale(state)
  local spans = {
    {"loading", B.door_close_seconds},
    {"filling", B.fill_seconds * ts},
    {"washing", B.wash_seconds * ts},
    {"spincycle", B.spin_seconds * ts},
    {"ejecting", B.drain_seconds + 0.5},
  }
  if settingsOf(state).delay then
    table.insert(spans, 2, {"presoak", 8.0})
  end
  return spans
end

local function lcdProgress(state)
  local b = state.behavior
  if b.phase == "idle" then return 0 end
  if b.phase == "cooldown" or b.phase == "aborting" then return 1 end
  local total, before, span = 0, 0, nil
  for _, entry in ipairs(lcdSpans(state)) do
    total = total + entry[2]
    if span == nil then
      if entry[1] == b.phase then
        span = entry[2]
      else
        before = before + entry[2]
      end
    end
  end
  if span == nil then return 0 end
  return math.min(1, (before + math.min(b.elapsed or 0, span)) / total)
end

local function lcdPush(state, force)
  local b = state.behavior
  b.lcdElapsed = (b.lcdElapsed or 0)
  if not force and b.lcdElapsed < 0.4 and b.phase == b.lcdLastPhase then
    return
  end
  b.lcdElapsed = 0
  b.lcdLastPhase = b.phase
  local washer = exactVehicle(state.propId)
  if not washer then return end
  local s = settingsOf(state)
  local payload = jsonEncode({
    phase = b.phase,
    progress = lcdProgress(state),
    -- INDICATED drum speed, not the geometric one. The 8.4 m drum only
    -- reaches ~90 true rpm, which would leave a washer-scale tachometer
    -- (0-1600, player 2026-08-13) pinned at zero. omega * 175 maps the
    -- cycle so the needle peaks at EXACTLY the selected SPIN setting:
    -- spin phase tops out at spin_omega(8) * omegaScale, and
    -- 8 * (rpmSet/1400) * 175 == rpmSet.
    rpm = (b.omega or 0) * 175.0,
    water = math.min(1, (b.waterLevel or 0) / B.max_water_depth),
    temp = TEMP_STEPS[s.temp],
    rpmSet = SPIN_STEPS[s.spin],
    soil = s.soil and true or false,
    delay = s.delay and true or false,
    program = dialProgram(state).name,
  })
  washer:queueLuaCommand(string.format(
    "extensions.hook('onEricrolphSpinCycleWasherLcd', %q)", payload))
end

local lcdBaseUpdate = behavior.update
behavior.update = function(state, dtSim)
  lcdBaseUpdate(state, dtSim)
  local b = state.behavior
  b.lcdElapsed = (b.lcdElapsed or 0) + dtSim
  lcdPush(state, false)
end

-- Fascia buttons (vehicle triggers -> interaction json -> GE runtime).
behavior.onPanelButton = function(state, buttonId)
  local b = state.behavior
  local s = settingsOf(state)
  if buttonId == "btn_start" then
    if b.phase == "idle" then
      b.phase = "loading"
      b.elapsed = 0
      local subject = firstOccupant(state, "drum_zone")
      b.subjectId = subject and subject:getId() or nil
      if subject then
        showMessage("Cycle started. Contents: one (1) vehicle.", 2.2)
      else
        showMessage("Cycle started. Washing... nothing. Respect.", 2.2)
      end
      emitEvent(state, "I", "washer_started_button",
        {subject_id = b.subjectId})
    else
      showMessage("Cycle already in progress.", 1.6)
    end
  elseif buttonId == "btn_temp" then
    s.temp = s.temp % #TEMP_STEPS + 1
    local blurbs = {
      "TEMP 20 C: arctic molasses.",
      "TEMP 40 C: factory normal.",
      "TEMP 60 C: getting slippery.",
      "TEMP 95 C: steam-slick. Hold on.",
    }
    showMessage(blurbs[s.temp], 2.0)
  elseif buttonId == "btn_spin" then
    s.spin = s.spin % #SPIN_STEPS + 1
    showMessage(string.format("SPIN set: %d rpm.", SPIN_STEPS[s.spin]), 1.8)
  elseif buttonId == "btn_soil" then
    s.soil = not s.soil
    -- Re-drive whatever the cycle currently wants through the new gate.
    for name, want in pairs(b.fxWanted or {}) do
      setEffectActive(state, name, (want and s.soil) or false)
    end
    showMessage(s.soil and "SOIL: heavy suds ON." or "SOIL: suds OFF.", 1.8)
  elseif buttonId == "btn_delay" then
    s.delay = not s.delay
    showMessage(s.delay
      and "DELAY: extended cycle. Levitating pre-soak, longer everything."
      or "DELAY off: express service.", 2.2)
  elseif buttonId == "dial_cw" or buttonId == "dial_ccw" then
    local stepDir = (buttonId == "dial_cw") and 1 or -1
    s.dial = ((s.dial or 2) - 1 + stepDir) % #DIAL_EJECT + 1
    showMessage("Program: " .. DIAL_EJECT[s.dial].name, 1.8)
  end
  lcdPush(state, true)
end
"""

# Vehicle-VM bootstrap extra (2026-08-13): owns the live LCD webview. The
# CEF page keeps its own real-time clock (JS Date == player's system clock);
# Lua only (a) creates the webview, (b) forwards the GE behavior's cycle
# state (hook above), and (c) streams the washer's own motion so the screen
# can raise UNBALANCED LOAD when the machine itself gets shoved or tipped.
# 816x500 matches the LCD plate's 1.6316 aspect.
VEHICLE_LUA_EXTRA = r"""
local htmlTexture = require("htmlTexture")

local LCD_TAG = "@__MOD_ID___lcd"
local LCD_HTML = "local://local/vehicles/__MOD_ID__/lcd/screen.html"
local lcdUp = false
local lcdPushElapsed = 0

local function lcdEnsure()
  if lcdUp then return end
  lcdUp = pcall(htmlTexture.create, LCD_TAG, LCD_HTML, 816, 500, 15,
    "automatic") and true or false
end

local lcdBaseLoaded = M.onVehicleLoaded
M.onVehicleLoaded = function(...)
  lcdBaseLoaded(...)
  lcdUp = false
  lcdEnsure()
end

local lcdBaseUpdateGFX = M.updateGFX
M.updateGFX = function(dt, ...)
  lcdBaseUpdateGFX(dt, ...)
  lcdEnsure()
  if not lcdUp then return end
  lcdPushElapsed = lcdPushElapsed + dt
  if lcdPushElapsed < 0.25 then return end
  lcdPushElapsed = 0
  local velocity = obj:getVelocity()
  pcall(htmlTexture.call, LCD_TAG, "updateData",
    {speed = velocity:length()})
end

M.onEricrolphSpinCycleWasherLcd = function(payloadJson)
  if not lcdUp then return end
  local ok, data = pcall(jsonDecode, payloadJson)
  if ok and type(data) == "table" then
    pcall(htmlTexture.call, LCD_TAG, "updateData", data)
  end
end
""".replace("__MOD_ID__", MOD_ID)
