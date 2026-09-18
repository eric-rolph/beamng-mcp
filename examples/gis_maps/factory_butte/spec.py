"""Factory Butte badlands - authored constants shared by the generator and the level.

Mancos Shale badlands under Factory Butte: knife-edge clay fins, tightly spaced parallel
rills and the mud-wash flats between them, from Utah's statewide 1 m lidar (served
through USGS 3DEP). A 4096 m square at 1 m per sample.
"""

MOD_ID = "ericrolph_factory_butte"
DISPLAY_NAME = "Factory Butte Badlands"
ZIP_BASENAME = "factory_butte_ericrolph.zip"
AUTHOR = "ericrolph"

SITE = {
    "place": "Wayne County, Utah, USA",
    "center_lat": 38.380,
    "center_lon": -110.900,
    "epsg": 32612,
    "size_px": 4096,
    "square_size_m": 1.0,
    # 4096 px over 4096 m is 1 m per texel, matching NAIP's own
    # resolution. Without this the module default of 2048 threw away three quarters of
    # the photograph the fetch stage had already downloaded.
    "base_tex_px": 4096,
}

SOURCES = {
    "elevation": [
        # Utah Statewide South 2020 (UGRC / AGRC) 1 m lidar as published through 3DEP.
        {
            "kind": "usgs_3dep",
            "resolution": 1.0,
            "citation": (
                "UT_StatewideSouth_2020_A20 lidar (Utah Geospatial Resource Center) via USGS 3DEP"
            ),
        },
    ],
    "imagery": {"kind": "usgs_naip", "resolution": 1.0},
    "roads": {"kind": "osm_overpass"},
}

TERRAIN = {
    "materials": ["fb_mud_flat", "fb_shale_slope", "fb_clay_fin", "fb_caprock"],
    "classify": {
        "rules": [
            {"min_slope": 38.0, "material": "fb_caprock"},
            {"min_slope": 20.0, "material": "fb_clay_fin"},
            {"min_slope": 6.0, "material": "fb_shale_slope"},
        ],
        "default": "fb_mud_flat",
    },
    "smooth_sigma_px": 0.0,
}

# Mancos Shale is a cool grey where it is cut and a warm buff where the wash has
# spread it, and that warm-cool split is the only colour the badlands have. The first
# pass authored all four surfaces as warm neutrals within 1 % of each other in hue, and
# the imagery tint then pulled them tighter still: measured off the shipped textures,
# fb_shale_slope and fb_clay_fin came out 0.0006 apart, which is the same surface. The
# terrain classifies four materials by slope and a driver saw one. So the slopes and
# fins go cool, the wash and the cap stay warm, and the two that sit under most of the
# map take a lighter tint so the authored hue survives the photograph.
#
# The photograph is the reason for that last part rather than a preference: Factory
# Butte's NAIP mosaic is the flattest in the pack (mean chroma 0.097 against Meteor
# Crater's 0.271), so at the shared 0.6 tint the layer mean sets the colour and the
# authored value is decoration. tint_weight per material is the existing lever for
# that - mc_ejecta_gravel already carries 0.35 for the same reason. The cost is that a
# detail material matches the base texture less closely where the two blend by
# distance; 0.35 is where Meteor Crater put that trade and it is bounded, because the
# built chroma still only reaches 0.09-0.13 on the two cool surfaces.
#
# The first pass put that 0.35 on fb_shale_slope and fb_clay_fin and called them the
# two that sit under most of the map. They are not: the built terrain classifies
# fb_mud_flat over 61.94% of it, fb_shale_slope 26.41, fb_clay_fin 9.66 and fb_caprock
# 1.99. The lighter tint landed on a third of the map and the dominant surface kept the
# shared 0.6, which is also the warm half of the only colour split these badlands have -
# so the split was being held up by the cool side alone. At 0.6 the wash builds to b*
# 9.00 against the slopes' -5.14, a 14.14 gap in a* b*; at 0.35 it builds to 12.18, a
# gap of 17.32. The cost is the same one weighed above and it is smaller here than
# anywhere it has already been accepted: against the de-lit base the wash steps dE76
# 5.49 at 0.6 and 10.05 at 0.35, where mc_ejecta_gravel ships 12.34 at this same weight
# and this map's own fb_shale_slope and fb_clay_fin ship 22.82 and 30.20. Rendered on
# the wash_west driver sheet the ramp stays a ramp - near chroma 0.086 to 0.107, far
# 0.028 to 0.031, no edge at the 120 m fade.
PALETTE = {
    "fb_mud_flat": {
        "family": "clay_pan",
        "seed": 301,
        "size": 1024,
        "base": [0.63, 0.58, 0.47],
        "tint_weight": 0.35,
    },
    "fb_shale_slope": {
        "family": "shale",
        "seed": 302,
        "size": 1024,
        "base": [0.40, 0.44, 0.52],
        "tint_weight": 0.35,
    },
    "fb_clay_fin": {
        "family": "shale",
        "seed": 303,
        "size": 1024,
        "base": [0.30, 0.34, 0.44],
        "tint_weight": 0.35,
    },
    "fb_caprock": {
        "family": "rock_strata",
        "seed": 304,
        "size": 1024,
        "base": [0.58, 0.48, 0.35],
        "tint_weight": 0.45,
    },
}

IMAGERY = {
    # First pass: the de-lighting is turned on, nothing is tuned. Every value below is
    # bounded by something already measured in this tree; the site-specific work
    # (chroma pulls, flat-fields, refills) belongs in a critic round with sheets to
    # look at, against the reference stations.
    "delight": True,
    # The floor was 55, from a near-solar-noon reading of NAIP's flight window at
    # 38.38 N. The first build fitted the sun at exactly 55 degrees, correlation
    # 0.641 - pinned on the bound, as all four of these maps were, so the bound was
    # the answer rather than the data. 30 is the acquisition minimum NAIP is specified
    # to and the floor Meteor Crater already carries, where the fit settles at 56 in the
    # interior, so a wide range is not a runaway. The ceiling is unchanged.
    "sun_altitude_range": [30.0, 78.0],
    "sun_azimuth_hint": 180.0,
    "sun_azimuth_window": 50.0,
    "strength": 1.0,
    "tint_from_imagery": 0.6,
    # Slope mean 8.0, p95 32.1 deg. The fins and caprock lips are short but sheer, so
    # a little over the 2.2 default; the cap follows the caprock rule at 38 degrees so
    # a shaded fin borrows only from lit fins.
    "max_gain": 2.5,
    "steep_deg": 38.0,
    "steep_feather_deg": 8.0,
    "steep_cap": True,
}

ROADS = {
    "include": [
        "primary",
        "secondary",
        "tertiary",
        "unclassified",
        "residential",
        "service",
        "track",
    ],
    "widths": {
        "primary": 8.0,
        "secondary": 7.0,
        "tertiary": 6.0,
        "unclassified": 5.0,
        "residential": 5.0,
        "service": 4.0,
        "track": 3.5,
    },
    "material": {
        "name": "road_gravel",
        "family": "gravel",
        "seed": 900,
        "base": [0.60, 0.55, 0.47],
    },
}

# Round 1's verdict could not be better than NOT YET for one reason: every driver view
# reported 0 objects in range. This is the first pass at that, and it is a scatter and
# nothing else, which is a choice the terrain forced rather than a shortcut.
#
# The lidar-scale bump detector, which is where the other two maps get their boulders,
# cannot be used here. Measured on the shipped terrain at open_m 6.0 and min_height_m
# 0.6, it finds 6,768 bumps over the 16.8 km2 and not one of them is on fb_mud_flat -
# the 61.94% of the map where a block resting on a wash floor would actually be. All of
# them are on fb_shale_slope and fb_clay_fin: on badlands a 6 m opening resolves the fin
# crests and spur noses, which are the landform, and it takes 106,602 m3 of terrain off
# to place them. Tightening it does not help, because there is nothing on the flat to
# find: at open_m 4.0 the count goes UP and the share on the fins goes from 67% to 86%.
# `rock_layers` would not have saved it either - that decides which bumps become meshes,
# and the opened surface has replaced the DEM before it is consulted. So `detect` is
# None, which maplib/pipeline.py reads as "leave the ground alone".
#
# Where the stones go instead is measured too. Mancos Shale sheds plates continuously
# and the wash carries them to the rill floors and the fin toes, so the scatter's toe
# bias is doing the real work: with a 40 m window the wash floor within 12 m of a flank
# reads 0.67 m of concavity at the 90th percentile against the open wash's 0.08, an
# 8-fold separation, and at a 0.35 m threshold the first saturates while the second
# stays near zero. The bias moves a layer's stones without adding any, so fb_mud_flat's
# allowance collects in the rills and the open plains stay as bare as they are.
#
# One side effect to hold onto when round 2 reads the sheet, because it is not a
# scatter at all: having an OBJECTS block at all moves this map's imagery onto the
# terrain stage's conditioning path. The level stage's fallback calls conditioned_colour
# with no `source_exclude`; the terrain stage passes the 12 m road corridor, so the
# de-lighting's refills stop drawing on the flight's own tracks. Black Bear Pass's round
# 17 found pale lozenges beside its roads from exactly that. Expect the base under the
# tracks to move a little, and do not read it as a scatter effect.
#
# The densities are the least measured thing here and the first thing round 2 should
# judge on a rendered sheet. They put about 14 stones inside 25 m of each spawn and 3,200
# per km2 over the level, against Black Bear Pass's 1,500, on the reasoning that badlands
# shed harder than a tundra bench and hold far less than a talus field.
OBJECTS = {
    "seed": 300,
    "detect": None,
    "classify": {"rock_only": True},
    "max_rocks": 0,
    "max_shrubs": 0,
    # No vegetation, and that is the place rather than an omission: the Factory Butte
    # badlands are bare Mancos Shale, too saline and too mobile to hold a shrub, which
    # is why the level's description promises "no vegetation to scatter". A sparse
    # saltbush would be a decoration the photographs do not support.
    "rock_materials": {
        # Shale plates. The tile the fins are painted in means (0.447, 0.468, 0.514);
        # a freshly split plate weathers paler than the face it came off, so a shade
        # up from that. Bedded harder than anything else in the pack - shale is the
        # rock that splits along its bedding - and no lichen: these slopes move every
        # time it rains and nothing gets a hold.
        "rock_shale_plate": {
            "colour": [0.38, 0.40, 0.45],
            "strata": 0.75,
            "z_aspect": [0.12, 0.30],
            "lichen": 0.0,
        },
        # The caprock's own blocks, the only warm rock on the level and the only one
        # with any thickness: Emery Sandstone, which is what holds the fins up.
        "rock_caprock_block": {
            "colour": [0.52, 0.45, 0.35],
            "strata": 0.35,
            "z_aspect": [0.35, 0.70],
            "lichen": 0.0,
        },
    },
    "scatter_rock_material": {
        "fb_mud_flat": "rock_shale_plate",
        "fb_shale_slope": "rock_shale_plate",
        "fb_clay_fin": "rock_shale_plate",
        "fb_caprock": "rock_caprock_block",
    },
    "scatter": {
        "fb_mud_flat": 18.0,
        "fb_shale_slope": 60.0,
        "fb_clay_fin": 45.0,
        "fb_caprock": 35.0,
    },
    # Plates, not boulders: a 0.7 m slab is a big one here, and the z_aspect above keeps
    # them flat. Black Bear Pass's 0.3-1.2 m is a talus block.
    # 0.25 rather than 0.2, which was flush against the 0.2 floor a forest item is held
    # to. A minimum authored exactly on a bound fails on some draws and passes on
    # others: run 51 died on one 0.18 m stone out of tens of thousands.
    "scatter_size_m": [0.25, 0.7],
    "scatter_max": 60000,
    # 40 m and 0.35 m are the measured numbers above. Black Bear Pass's 40 m window
    # carries over; its 0.5 m threshold does not, because these toes are shallower.
    "toe_bias": 5.0,
    "toe_window_m": 40.0,
    "toe_threshold_m": 0.35,
    "spawn_clear_m": 8.0,
    "road_clear_m": 3.0,
}
# The fins are the landform here and they are also the thing the heightmap handles
# worst: a knife-edge of Mancos Shale is two triangles wide on the terrain grid with the
# photograph smeared down both sides. The level's slope p95 is 32.1 degrees, so the
# threshold is 26 - six degrees over the line the terrain calls clay fin, and well inside
# the distribution rather than off its end, which is what 34 would have been. The fins
# are short, so the relief floor is 6 m
# and the area floor 300: a fin is a narrow thing and the pack's default would throw
# every one of them away.
#
# Shale is the most finely bedded rock in the pack and it sheds plates continuously, so
# the beds are 1.2 m, the joints are close, and the relief is small - a shale fin is
# ribbed, not blocky. The stone scatter below already carries the plates that come off
# it.
CLIFFS = {
    "seed": 1703,
    "min_slope_deg": 26.0,
    "min_relief_m": 6.0,
    "min_area_m2": 300.0,
    "face_step_m": 1.2,
    "bed_m": 1.2,
    "joint_m": 3.5,
    "relief_m": 0.45,
    "buttress_m": 0.9,
    "tile_m": 2.0,
    "max_triangles": 420000,
    "materials": {
        # The fin tile's own base. Shale splits along its bedding harder than any rock
        # here, hence the strata; nothing holds on a slope that moves every time it
        # rains, hence no lichen.
        "cliff_shale": {"colour": [0.30, 0.34, 0.44], "strata": 0.8, "lichen": 0.0},
    },
}


# The apron the gate measures is a 14 by 7 m rectangle at the heading: no more than 8
# degrees across it and 0.6 m off the plane it sits on. Nothing here promised that, so
# the gate skipped, and the published build stood the default spawn on a 20.8 degree
# face with 2.96 m of roughness - a car slides off it before anyone drives. They promise
# it now, so a later build cannot quietly walk one back onto a slope.
#
# These badlands are incised, not raised: the rills are cut BELOW the plain, so the
# nearest level ground to a bad spawn is usually the plateau on top, where the horizon
# is dead flat and there is nothing to look at. Both picks below are level AND have
# landform in front of them, measured as the 90th percentile elevation angle along the
# heading out to 700 m.
SPAWNS = [
    # 70 m south, still down in the cut but out on the wash floor (1402.8 m, the 10th
    # percentile of the ground around here) instead of the narrow spot the old pick sat
    # in, which had 25 degrees of wall on every heading. 1.77 across, 2.68 along, 0.25 m
    # rough, with the ridge line 9.7 degrees up at the 90th percentile out to 700 m. The
    # old heading of 60 looked out over the flats; 15 puts the wash and its skyline in
    # frame. The level ground nearest the old pick is the plateau on top, 19 m up, where
    # the horizon is dead flat and there is nothing to see - passing the gate is not the
    # same as being somewhere worth starting.
    {
        "name": "butte_base",
        "lat": 38.379370,
        "lon": -110.904887,
        "heading_deg": 15.0,
        "default": True,
        "level_ground": True,
    },
    # 11 m north-east, off the rill flank: 2.08 across, 2.38 along, 0.25 m rough.
    {
        "name": "badlands_south",
        "lat": 38.366072,
        "lon": -110.894908,
        "heading_deg": 0.0,
        "level_ground": True,
    },
    # Already on the mud flat: 1.70 across, 0.23 m rough.
    {
        "name": "wash_west",
        "lat": 38.385,
        "lon": -110.918,
        "heading_deg": 90.0,
        "level_ground": True,
    },
]

SKY = {"time": 0.16, "utc_offset": "-6", "year": 2026, "month": 6, "day": 20}

BIOME = "Shale badlands"
FEATURES = "Mancos Shale rills, clay fins and mud-wash flats under Factory Butte"
SUITABLE_FOR = "Free-ride, buggies, UTV and dirt-bike lines"
ROADS_TEXT = "A few dirt tracks; the badlands themselves are the road"

DESCRIPTION = (
    "The Mancos Shale badlands under Factory Butte, Utah, rebuilt from the state's 1 m "
    "lidar via USGS 3DEP. Thousands of parallel clay rills, knife-edge fins and mud-wash "
    "flats in a 4 km square: natural dirt half-pipes and spine transfers with no "
    "vegetation to scatter."
)
