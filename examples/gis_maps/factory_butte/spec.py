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
