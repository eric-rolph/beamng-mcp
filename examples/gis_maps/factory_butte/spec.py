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

PALETTE = {
    "fb_mud_flat": {"family": "clay_pan", "seed": 301, "size": 1024, "base": [0.58, 0.55, 0.50]},
    "fb_shale_slope": {"family": "shale", "seed": 302, "size": 1024, "base": [0.50, 0.48, 0.45]},
    "fb_clay_fin": {"family": "shale", "seed": 303, "size": 1024, "base": [0.44, 0.42, 0.40]},
    "fb_caprock": {"family": "rock_strata", "seed": 304, "size": 1024, "base": [0.52, 0.44, 0.36]},
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

SPAWNS = [
    {"name": "butte_base", "lat": 38.380, "lon": -110.905, "heading_deg": 60.0, "default": True},
    {"name": "badlands_south", "lat": 38.366, "lon": -110.895, "heading_deg": 0.0},
    {"name": "wash_west", "lat": 38.385, "lon": -110.918, "heading_deg": 90.0},
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
