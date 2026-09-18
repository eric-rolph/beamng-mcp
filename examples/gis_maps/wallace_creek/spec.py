"""Carrizo Plain and Wallace Creek - authored constants shared by the generator and the level.

The San Andreas Fault's textbook surface trace: the 130 m offset channel at Wallace
Creek, sag ponds, pressure ridges and linear scarps along the Elkhorn Scarp. A 16,384 m
square at 1 m per sample, with the B4 0.5 m bare-earth lidar composited over the 3DEP
baseline wherever the B4 swath covers the level. The base colour is 8192 px, 2 m per
texel: the ground keeps its metre and the photograph pays for the reach.

The square used to be 4096 m round the offset channel alone, which is the geology and
none of the place. It now runs 16.4 km along the plain: Soda Lake and its north shore,
the Goodwin Education Center, Elkhorn Road down the fault, Wallace Creek and its
interpretive trail, and the Temblor crest above them. Terrain sizes are powers of two
and the rungs in metres are 16,384 and 32,768, so reaching KCL Campground and the run
out to Fellows - another 13 km east - would have meant a 32.8 km square: four times the
ground, 1,074 km2 of it, 5.3 GB on disk, 7.5 billion lidar returns and twelve hours of
point-cloud reading, with the base texture capped at 2 m per texel anyway because one
32,768 px image is past the GPU ceiling. This holds 268 km2 at a metre for 1.85 GB.
"""

MOD_ID = "ericrolph_wallace_creek"
DISPLAY_NAME = "Carrizo Plain - Wallace Creek"
ZIP_BASENAME = "wallace_creek_ericrolph.zip"
AUTHOR = "ericrolph"

SITE = {
    "place": "Carrizo Plain National Monument, San Luis Obispo County, California, USA",
    # Balanced over the landmarks rather than over the offset channel: the tightest of
    # them (Elkhorn Road's south end, and the Temblor crest above Wallace Creek) each
    # keep 790 m of margin, and Wallace Creek itself 2.6 km.
    "center_lat": 35.2215,
    "center_lon": -119.8310,
    "epsg": 32611,  # WGS 84 / UTM zone 11N
    "size_px": 16384,
    "square_size_m": 1.0,  # 16,384 m footprint
    # The terrain is 16,384 samples at 1 m - a float32 DEM of that size is 1.07 GB and
    # builds comfortably. The base texture is the expensive one: imagery.py de-lights
    # the whole array at once, so the working set goes as base_tex_px squared, and an
    # 8192 px base over 16,384 m is 2 m per texel. A 16,384 px base would hold the NAIP
    # at its own metre and is what this wants once the de-lighting works in overlapping
    # tiles; today it would be OOM-killed the way Black Bear Pass was (exit 137).
    "base_tex_px": 8192,
}

SOURCES = {
    "elevation": [
        {"kind": "usgs_3dep", "resolution": 1.0},
        # B4 Project (2005) bare-earth tiles, 0.5 m, OpenTopography OTSDEM.032018.32611.1.
        {
            "kind": "ot_tiles",
            "prefix": "CA05USGSB4/CA05USGSB4_be/",
            "pattern": r"b4_(\d+)_(\d+)_be\.tif$",
            "tile_m": 2000.0,
            "name": "ca05usgsb4_be",
            "citation": "B4 Project - Southern San Andreas and San Jacinto Faults (2005). "
            "USGS / NSF / NCALM. https://doi.org/10.5066/F7TQ5ZQ6",
            "license": "Public domain (U.S. Geological Survey)",
        },
    ],
    "imagery": {"kind": "usgs_naip", "resolution": 1.0},
    "roads": {"kind": "osm_overpass"},
}

TERRAIN = {
    "materials": ["wc_grassland", "wc_alluvial_wash", "wc_fault_scarp", "wc_dry_pond"],
    "classify": {
        "rules": [
            {"min_slope": 22.0, "material": "wc_fault_scarp"},
            {"min_slope": 6.0, "material": "wc_alluvial_wash"},
            {"max_slope": 0.6, "material": "wc_dry_pond"},
        ],
        "default": "wc_grassland",
    },
    "smooth_sigma_px": 0.0,
}

PALETTE = {
    "wc_grassland": {"family": "dry_grass", "seed": 201, "size": 1024, "base": [0.60, 0.54, 0.36]},
    "wc_alluvial_wash": {"family": "gravel", "seed": 202, "size": 1024, "base": [0.58, 0.52, 0.42]},
    "wc_fault_scarp": {
        "family": "rock_strata",
        "seed": 203,
        "size": 1024,
        "base": [0.55, 0.47, 0.37],
    },
    "wc_dry_pond": {"family": "clay_pan", "seed": 204, "size": 1024, "base": [0.68, 0.62, 0.52]},
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
    {
        "name": "wallace_creek_offset",
        "lat": 35.2717,
        "lon": -119.8275,
        "heading_deg": 135.0,
        "default": True,
    },
    {"name": "elkhorn_scarp", "lat": 35.255, "lon": -119.805, "heading_deg": 315.0},
    {"name": "plain_west", "lat": 35.265, "lon": -119.830, "heading_deg": 90.0},
]

SKY = {"time": 0.86, "utc_offset": "-7", "year": 2026, "month": 5, "day": 10}

BIOME = "Arid tectonic plain"
FEATURES = "San Andreas fault trace: offset channels, scarps, sag ponds, pressure ridges"
SUITABLE_FOR = "Trophy trucks and pre-runners; long-travel suspension testing"
ROADS_TEXT = "Dirt ranch tracks along the fault; no pavement"

DESCRIPTION = (
    "The San Andreas Fault across the Carrizo Plain, rebuilt from the B4 0.5 m lidar and "
    "USGS 3DEP. Wallace Creek's 130 m offset channel, sag ponds, pressure ridges and "
    "fault scarps in a 4 km square at 1 m per sample: trophy-truck terrain where every "
    "gully is a measured tectonic feature."
)
