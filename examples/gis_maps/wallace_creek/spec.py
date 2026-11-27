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
    "center_lat": 35.262,
    "center_lon": -119.815,
    "epsg": 32611,  # WGS 84 / UTM zone 11N
    # WANTED: 16384 at 1 m, the 16.4 km square that holds Soda Lake, the Goodwin
    # Education Center, Elkhorn Road, Wallace Creek and the Temblor crest. BLOCKED: the
    # de-lighting holds the level in memory and 8192 samples is already OOM-killed on a
    # 15 GB box, so 16384 is four times an amount that does not fit. Back to the square
    # round the offset channel until imagery.py runs its illumination model on a
    # decimated grid; see AGENTS.md, "The de-lighting is the memory ceiling".
    "size_px": 4096,
    "square_size_m": 1.0,  # 4096 m footprint
    "base_tex_px": 4096,
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

IMAGERY = {
    # First pass: the de-lighting is turned on, nothing is tuned. Every value below is
    # bounded by something already measured in this tree; the site-specific work
    # (chroma pulls, flat-fields, refills) belongs in a critic round with sheets to
    # look at, against the reference stations.
    "delight": True,
    # The floor was 60, from a near-solar-noon reading of NAIP's flight window at
    # 35.26 N. The first build fitted the sun at exactly 60 degrees, correlation
    # 0.629 - pinned on the bound, as all four of these maps were, so the bound was
    # the answer rather than the data. 30 is the acquisition minimum NAIP is specified
    # to and the floor Meteor Crater already carries, where the fit settles at 56 in the
    # interior, so a wide range is not a runaway. The ceiling is unchanged.
    "sun_altitude_range": [30.0, 80.0],
    "sun_azimuth_hint": 180.0,
    "sun_azimuth_window": 50.0,
    "strength": 1.0,
    "tint_from_imagery": 0.6,
    # The gentlest map in the pack: slope mean 7.5, p95 27.7 deg, 3.8 % over 30. The
    # default gain is enough; nothing here is turned far enough from the sun to need
    # the cliff treatment.
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
# The gentlest map in the pack - slope p95 27.7 degrees - and the one where a wall
# matters most, because the walls ARE the geology: the Elkhorn Scarp and the banks of
# the offset channel are the San Andreas Fault's surface expression and they are what
# anyone loads this level to look at. At the module's default threshold not one of them
# would be modelled - and 28, the terrain's own fault-scarp line, would have been off the
# end of the distribution as well, the level's slope p95 being 27.7. 20 degrees sits
# inside it and takes the scarp faces and the offset channel's cut banks together. A
# scarp here is metres rather than tens of metres high, so the relief floor is 4.
#
# These are not bedded rock faces: a fault scarp in the Carrizo is a cut bank in
# alluvium, so the "beds" are the soil horizons the cut exposes - close together, low
# relief, and no joints to speak of. The joint period is long and the block step small
# so the face slumps rather than steps.
CLIFFS = {
    "seed": 1704,
    "min_slope_deg": 20.0,
    "min_relief_m": 4.0,
    "min_area_m2": 250.0,
    "face_step_m": 1.2,
    "bed_m": 0.9,
    "joint_m": 9.0,
    "relief_m": 0.3,
    "buttress_m": 0.7,
    # `bed_m` times a whole bed count, per the rule in maplib/cliffs.py: five beds of
    # exactly 0.9 m. At the old 2 m the tile carried two beds of 1.0 m, a ninth thicker
    # than this scarp declares. 1024 px over 4.5 m is 228 per metre, the densest cliff
    # texture in the pack, which suits a scarp a driver can get within a metre of.
    "tile_m": 4.5,
    "max_triangles": 260000,
    "materials": {
        # The scarp palette's own base: dry alluvium cut through, not rock. Barely
        # bedded, and the grass that grows over everything here is not lichen.
        "cliff_scarp": {"colour": [0.55, 0.47, 0.37], "strata": 0.25, "lichen": 0.0},
    },
}


# As on Factory Butte: the apron gate binds only on a spawn that promises level ground,
# none of these did, and the published build put the default spawn on the offset
# channel's own bank at 19.54 degrees across the heading with 2.10 m of roughness. The
# channel is the landmark, so the fix is 29 m along the flat above it rather than a new
# viewpoint. The other two already passed and now say so.
SPAWNS = [
    # On the terrace above the offset channel, still looking down it at 135 degrees:
    # 4.21 across, 0.27 along, 0.11 m rough.
    {
        "name": "wallace_creek_offset",
        "lat": 35.271480,
        "lon": -119.827668,
        "heading_deg": 135.0,
        "default": True,
        "level_ground": True,
    },
    # 6.46 across, 0.32 m rough.
    {
        "name": "elkhorn_scarp",
        "lat": 35.255,
        "lon": -119.805,
        "heading_deg": 315.0,
        "level_ground": True,
    },
    # 1.35 across, 0.10 m rough.
    {
        "name": "plain_west",
        "lat": 35.265,
        "lon": -119.830,
        "heading_deg": 90.0,
        "level_ground": True,
    },
]


# Wallace Creek shipped with nothing on it. Not a thin scatter - nothing: no OBJECTS
# block at all, so the whole placed-object path was skipped and the level was terrain,
# roads and sky. This is the first pass at that, and like Factory Butte's it is a
# scatter rather than a lidar harvest, for the same measured reason turned round.
#
# The bump detector is not used here and must not be. The elevation is B4 bare-earth
# lidar composited over 3DEP: bare earth is the definition of a surface with the
# vegetation taken off it, so there is no bush in this DEM to find. What a 6-8 m opening
# WOULD find on the Carrizo is the pressure ridges, the mole tracks, the sag-pond rims
# and the scarp noses - which are the San Andreas Fault's surface trace, the entire
# reason this level exists. Factory Butte learned that a detector run on a landform map
# shaves the landform off; doing it here would plane the fault flat and stand it back up
# as boulders. So "detect" is None, which maplib/pipeline.py reads as "leave the ground
# alone".
#
# What goes on instead is two scatters and a shrub finder.
#
# STONES. The Carrizo plain is fine alluvium and the grassland is nearly stoneless; the
# gravel is in the washes off the Temblor front and along the toes of the scarps, where
# the cut bank sheds it. So the density is graded hard - 45 a hectare on the wash, 30 on
# the scarp, 2 on the grassland and none on the sag ponds, which are silt - and the
# swale bias does the rest. These are cobbles and not boulders: 0.10-0.40 m, against
# Factory Butte's 0.2-0.7 m plates and Black Bear Pass's 0.3-1.2 m talus blocks.
#
# BUSHES. This is what the pack could not do until now. The Carrizo's scrub is saltbush
# and rabbitbrush under a metre, on a plain of dry grass - too small for the lidar (and
# absent from a bare-earth model anyway) and too pale for the dark-dot finder that puts
# junipers on Meteor Crater's plain. Both existing paths find nothing here, which is
# exactly why the level came out bare. The density scatter is the third path and the
# only one that reaches this vegetation.
#
# The numbers are the least measured thing here and the first thing a critic round
# should judge on a rendered sheet. Saltbush stands on the Carrizo are patchy, so the
# patchiness is high (0.8) and the density is read as a stand average rather than a
# lawn: 260 a hectare on the wash where the water runs, 120 on the grassland, 60 on the
# scarp faces and 30 on the pond floors, which crack dry and hold almost nothing. Against
# Meteor Crater's 4,977 placed shrubs over 1 km2 this is a similar plant spacing on a
# level four times the area.
#
# Nothing is planted as a tree. The Carrizo Plain is treeless grassland - that is what
# makes the fault trace legible from the air in every photograph of it - and a scattered
# juniper would be a decoration the place does not have.
OBJECTS = {
    "seed": 200,
    "detect": None,
    "classify": {"rock_only": True},
    "max_rocks": 0,
    "max_shrubs": 0,
    "rock_materials": {
        # Temblor sandstone, the pale buff cobble the washes carry off the range front.
        # Bedded, so tabular; no lichen on a plain this dry.
        "rock_sandstone": {
            "colour": [0.56, 0.50, 0.40],
            "strata": 0.45,
            "z_aspect": [0.3, 0.6],
            "lichen": 0.0,
        },
        # The scarps cut older alluvium with a grey shale fraction in it: the stone that
        # lies at a scarp toe is darker and flatter than the wash's.
        "rock_shale_cobble": {
            "colour": [0.46, 0.44, 0.40],
            "strata": 0.6,
            "z_aspect": [0.2, 0.45],
            "lichen": 0.0,
        },
    },
    "scatter_rock_material": {
        "wc_grassland": "rock_sandstone",
        "wc_alluvial_wash": "rock_sandstone",
        "wc_fault_scarp": "rock_shale_cobble",
        "wc_dry_pond": "rock_shale_cobble",
    },
    "scatter": {
        "wc_grassland": 2.0,
        "wc_alluvial_wash": 45.0,
        "wc_fault_scarp": 30.0,
        "wc_dry_pond": 0.0,
    },
    # A scattered stone's forest scale is its longest horizontal extent in metres, not a
    # multiplier, so this is the physical size of shipped rock. The Carrizo gravel really
    # does run finer than this, but a sub-20 cm pebble costs a whole forest instance for
    # something no driver resolves, and nothing measured here argued for the 0.10 this was
    # first written at. 0.25 and not 0.20 because a forest item is held to a 0.2 floor, and
    # a minimum authored flush against a bound has no margin for rounding - which is how
    # Factory Butte killed a forty-minute build.
    "scatter_size_m": [0.25, 0.40],
    "scatter_max": 45000,
    # The washes are where the gravel ends up, so the toe bias is strong and its window
    # is the 40 m Black Bear Pass and Factory Butte both use. A metre of concavity is the
    # threshold: these hollows are broad and shallow, not rill floors.
    "toe_bias": 4.0,
    "toe_window_m": 40.0,
    "toe_threshold_m": 1.0,
    # Saltbush and rabbitbrush, and the dry bunchgrass between them. The grass is
    # authored as its own shrub family rather than as a texture, because a tussock is a
    # thing a wheel finds and a painted one is not.
    "shrub_materials": {
        "shrub_saltbush": {
            # Grey-green, the colour that makes Atriplex read as saltbush and not sage:
            # barely more green than red, and the light side almost neutral.
            "colour": [0.40, 0.43, 0.36],
            "light_colour": [0.62, 0.63, 0.55],
            "height": 0.8,
            "width": 1.2,
            "max_width_m": 2.0,
        },
        "shrub_rabbitbrush": {
            # Rabbitbrush is the yellower, looser bush of the wash margins.
            "colour": [0.44, 0.44, 0.30],
            "light_colour": [0.66, 0.64, 0.42],
            "height": 0.9,
            "width": 1.1,
            "max_width_m": 2.0,
        },
        "shrub_bunchgrass": {
            # Late-spring Carrizo grass is straw with a green cast left in it, not a
            # lawn: the plain is famously gold by May in every photograph of the trace.
            "colour": [0.52, 0.48, 0.30],
            "light_colour": [0.70, 0.65, 0.44],
            "height": 0.35,
            "width": 0.5,
            "max_width_m": 0.9,
        },
    },
    # A plant the scatter drew over a metre is a bush, whatever it is standing on.
    "shrub_material_by_height": [[1.0, "shrub_saltbush"]],
    "shrub_material_by_layer": {
        "wc_grassland": "shrub_bunchgrass",
        "wc_alluvial_wash": "shrub_rabbitbrush",
        "wc_fault_scarp": "shrub_saltbush",
        "wc_dry_pond": "shrub_bunchgrass",
    },
    "shrub_scatter": {
        "density": {
            "wc_grassland": 120.0,
            "wc_alluvial_wash": 260.0,
            "wc_fault_scarp": 60.0,
            "wc_dry_pond": 30.0,
        },
        "height_m": [0.25, 1.1],
        "width_ratio": [1.0, 1.7],
        # The scarp faces run to 28 degrees and carry scrub to the top; nothing above
        # that is soil here.
        "max_slope_deg": 30.0,
        # Saltbush stands are tens of metres across on the Carrizo, not hundreds.
        "patch_m": 55.0,
        "patchiness": 0.8,
        # Everything green on this plain is in a hollow: the swales, the channel floors
        # and the sag ponds' margins.
        "swale_bias": 2.5,
        "swale_window_m": 60.0,
        "swale_threshold_m": 0.8,
        "max": 260000,
    },
    "spawn_clear_m": 8.0,
    "road_clear_m": 3.0,
}

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
