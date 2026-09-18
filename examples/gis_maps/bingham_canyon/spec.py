"""Bingham Canyon open-pit mine - authored constants for the generator and the level.

The inverted mountain: a 4 km wide, 1.2 km deep spiral of 15 m benches linked by
continuous 8-10 % haul roads. A 4096-sample terrain at 1.5 m per sample gives a 6144 m
square holding the full pit, its rim and the graded waste-rock terraces around it.
"""

MOD_ID = "ericrolph_bingham_canyon"
DISPLAY_NAME = "Bingham Canyon Mine"
ZIP_BASENAME = "bingham_canyon_ericrolph.zip"
AUTHOR = "ericrolph"

SITE = {
    "place": "Salt Lake County, Utah, USA",
    "center_lat": 40.523,
    "center_lon": -112.151,
    "epsg": 32612,
    "size_px": 4096,
    "square_size_m": 1.5,  # 6144 m footprint
    # 8192 px over 6144 m is 0.75 m per texel. Without this the module default of 2048
    # left the ground at 3 m per texel, where a 15 m bench is five texels wide. Drop to
    # 4096 (1.5 m per texel, still double) if the release job cannot carry the bytes.
    "base_tex_px": 8192,
}

SOURCES = {
    "elevation": [
        {
            "kind": "usgs_3dep",
            "resolution": 1.0,
            "citation": "UT_2023SaltLakeCo_C24 lidar via USGS 3DEP",
        },
    ],
    "imagery": {"kind": "usgs_naip", "resolution": 1.0},
    "roads": {"kind": "osm_overpass"},
}

TERRAIN = {
    "materials": ["bc_haul_gravel", "bc_bench_face", "bc_waste_rock", "bc_scrub_hillside"],
    "classify": {
        "rules": [
            {"min_slope": 32.0, "material": "bc_bench_face"},
            {"min_slope": 14.0, "material": "bc_waste_rock"},
            {"max_slope": 7.0, "material": "bc_haul_gravel"},
        ],
        "default": "bc_scrub_hillside",
    },
    "smooth_sigma_px": 0.0,
}

PALETTE = {
    "bc_haul_gravel": {"family": "gravel", "seed": 601, "size": 1024, "base": [0.56, 0.52, 0.47]},
    "bc_bench_face": {
        "family": "rock_strata",
        "seed": 602,
        "size": 1024,
        "base": [0.50, 0.46, 0.42],
    },
    "bc_waste_rock": {"family": "scree", "seed": 603, "size": 1024, "base": [0.54, 0.50, 0.46]},
    "bc_scrub_hillside": {
        "family": "dry_grass",
        "seed": 604,
        "size": 1024,
        "base": [0.50, 0.47, 0.34],
    },
}

IMAGERY = {
    # First pass: the de-lighting is turned on, nothing is tuned. Every value below is
    # bounded by something already measured in this tree; the site-specific work
    # (chroma pulls, flat-fields, refills) belongs in a critic round with sheets to
    # look at, against the reference stations.
    "delight": True,
    # NAIP flies within a couple of hours of solar noon in the growing season. At
    # 40.52 N that puts the sun between 52 and 74 degrees up, and the azimuth within
    # 50 degrees of due south.
    "sun_altitude_range": [52.0, 74.0],
    "sun_azimuth_hint": 180.0,
    "sun_azimuth_window": 50.0,
    "strength": 1.0,
    "tint_from_imagery": 0.6,
    # The steepest of the four: slope mean 25.2, p95 49.3 deg, 46 % over 30. A pit this
    # deep casts its own south wall into shadow in the flight, and that shadow is real
    # DEM geometry, so the horizon test models it - but the wall still needs a large
    # gain to come back to the same rock as the lit benches. The cap follows this map's
    # own bench-face rule at 32 degrees, so a shaded bench borrows only from lit ones.
    "max_gain": 4.5,
    "steep_deg": 32.0,
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
    {"name": "pit_rim_east", "lat": 40.523, "lon": -112.128, "heading_deg": 270.0, "default": True},
    {"name": "pit_floor", "lat": 40.523, "lon": -112.151, "heading_deg": 90.0},
    {"name": "north_terraces", "lat": 40.545, "lon": -112.151, "heading_deg": 180.0},
]

SKY = {"time": 0.12, "utc_offset": "-6", "year": 2026, "month": 6, "day": 20}

BIOME = "Open-pit mine"
FEATURES = "4 km wide, 1.2 km deep spiral of 15 m benches and continuous haul roads"
SUITABLE_FOR = "Heavy haulers, brake fade, sustained grades, multi-terrace crashes"
ROADS_TEXT = "Mine haul and access roads as mapped in OSM; benches drive as terrain"

DESCRIPTION = (
    "Bingham Canyon open-pit mine, Utah, rebuilt from USGS 3DEP 1 m lidar. A 6 km square "
    "at 1.5 m per sample: dozens of 15 m benches spiralling 1.2 km down, linked by the "
    "continuous haul roads that make it a brake-fade test bench for heavy haulers."
)
