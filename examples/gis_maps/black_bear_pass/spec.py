"""Black Bear Pass and Ingram Basin - authored constants for the generator and the level.

A 12,840 ft shelf road descending from the pass through the Steps and the switchbacks
above Bridal Veil Falls into Ingram Basin. Forest on the Telluride side, tundra and talus above.
A 4096 m square at 1 m per sample from USGS 3DEP (San Luis / San Juan / Miguel 2020 lidar).
"""

MOD_ID = "ericrolph_black_bear_pass"
DISPLAY_NAME = "Black Bear Pass"
ZIP_BASENAME = "black_bear_pass_ericrolph.zip"
AUTHOR = "ericrolph"

SITE = {
    "place": "San Juan Mountains, San Miguel / Ouray County, Colorado, USA",
    "center_lat": 37.912,
    "center_lon": -107.762,
    "epsg": 32613,
    "size_px": 4096,
    "square_size_m": 1.0,
    "base_tex_px": 4096,  # the de-lit NAIP at its native 1 m per texel
    "detail_tex_px": 1024,
}

SOURCES = {
    "elevation": [
        {
            "kind": "usgs_3dep",
            "resolution": 1.0,
            "citation": "CO_SanLuisJuanMiguel_2020_D20 lidar via USGS 3DEP",
        },
    ],
    "imagery": {"kind": "usgs_naip", "resolution": 1.0},
    "roads": {"kind": "osm_overpass"},
    # The same 3DEP survey as a point cloud (about 4 returns per m2): its first
    # returns are the canopy, so the forest is planted from measured tree tops.
    "pointcloud": {
        "kind": "usgs_ept",
        "resource": "CO_SanLuisJuanMiguel_4_2020",
        "citation": "USGS 3DEP CO_SanLuisJuanMiguel_4_2020 point cloud, public Entwine index",
    },
}

TERRAIN = {
    "materials": [
        "bb_tundra",
        "bb_talus",
        "bb_cliff_rock",
        "bb_scree_slope",
        "bb_road_gravel",
        "bb_forest_floor",
        "bb_fellfield",
        "bb_cliff_rock_ew",
        "bb_lake",
    ],
    "classify": {
        # The summit plateau above 3,780 m is fell-field scree, not tussock turf: it
        # is painted talus whatever its slope, so the boulders the lidar found there
        # are placed and the tundra tile stays on the benches where the turf is.
        # Slopes greener than an excess-green of 0.06 in the de-lit imagery are turf
        # or forest, not rock, whatever their angle; closed conifer cover below the
        # tree line gets a needle-litter floor.
        "rules": [
            {"min_slope": 45.0, "ew_facing": True, "material": "bb_cliff_rock_ew"},
            {"min_slope": 45.0, "material": "bb_cliff_rock"},
            # Closed conifer cover is forest floor whatever its slope or greenness
            # (the base under the crowns is refilled as duff, so it is not green).
            {"min_canopy": 0.35, "max_elevation": 3600.0, "material": "bb_forest_floor"},
            {"min_slope": 30.0, "max_exg": 0.06, "material": "bb_scree_slope"},
            {"min_elevation": 3780.0, "max_slope": 30.0, "material": "bb_fellfield"},
            {"min_slope": 15.0, "max_exg": 0.06, "material": "bb_talus"},
            # Grey ground at any slope (a tarn's shore flat, an outwash flat) is
            # gravel, not turf: the turf test needs a green hue, so only grey falls here.
            {"max_exg": 0.06, "material": "bb_talus"},
        ],
        "default": "bb_tundra",
        # Turf is green by hue as well as by excess green: cream scree scores on
        # 2G-R-B because its blue is low, and it is not tundra.
        "min_green_hue": 0.02,
    },
    "smooth_sigma_px": 0.0,
}

PALETTE = {
    # Grey rubble with olive turf: the family's cushion, ground and straw tones set
    # the tonal order (cushions darker than the ground between them) and the base
    # is their mean.
    # The flight's tundra is lawn (excess green 0.19); the benches are olive turf on
    # grey rubble, so the layer is pulled half-way to the base, grain kept.
    "bb_tundra": {
        "family": "alpine_tundra",
        "seed": 501,
        "size": 1024,
        "base": [0.46, 0.46, 0.34],
        "base_pull": 0.7,  # a quarter of the layer was still lawn at 0.5
    },
    # Blocks 0.5-2 m across at a 6 m tile; cliff plates 2-4 m at a 10 m tile: the
    # shelf-road wall the driver sits 3 m from is massive blocky tuff, not a patio.
    # The reference photographs: dark grey angular rubble on the slopes, charcoal
    # cliffs in thin horizontal beds split by vertical joints (the same family turned
    # a quarter on the east- and west-facing walls), a pale dusty road across it all.
    "bb_talus": {
        "family": "talus_blocks",
        "seed": 502,
        "size": 1024,
        "base": [0.42, 0.41, 0.40],
        "tile_m": 6.0,
        # The NAIP talus is a pale grey the photographs are not: pulled most of the
        # way to the dark grey rubble, grain kept, per 200 m window (one layer-wide
        # shift left the north-east corner's chalk a pale mottle).
        "base_pull": 0.8,
        "base_pull_window_m": 200.0,
        # The pale fans are the cells over 1.25x the layer's median that the
        # default gate spares (it is for a white spoil field): here they are the
        # point of the pull, so the gate is wide.
        "base_pull_lum_gate": [0.5, 1.8],
    },
    # Still water under the lakes and tarns: its own flat dark tile, no cushions.
    "bb_lake": {
        "family": "water",
        "seed": 509,
        "size": 512,
        "base": [0.20, 0.33, 0.31],
        "keep_tint": True,
        "tile_m": 8.0,
    },
    # A 12 m tile of forty log-normal beds (median 0.3 m) so the period up a 150 m
    # wall is a dozen tiles, not thirty; the photograph of a cliff is mostly its own
    # shadow, so the tint takes only a quarter of it and keeps the charcoal.
    "bb_cliff_rock": {
        "family": "dark_strata",
        "seed": 503,
        "size": 1024,
        "base": [0.36, 0.35, 0.34],
        "tile_m": 12.0,
        "tint_weight": 0.25,
        "detail_strength": 0.7,  # the wall is the tile, not the base seen from above
        # The flight's cliffs are the palest rock on the level (0.44 against the
        # talus's 0.42 and the fell-field's 0.38); the photographs have thin-bedded
        # charcoal tuff as the darkest thing in the frame.
        "base_pull": 0.75,
        "base_pull_window_m": 200.0,
        "base_pull_lum_gate": [0.5, 1.8],
    },
    "bb_cliff_rock_ew": {
        "family": "dark_strata",
        "seed": 503,
        "size": 1024,
        "base": [0.36, 0.35, 0.34],
        "tile_m": 12.0,
        "rotate_deg": 90.0,
        "tint_weight": 0.25,
        "detail_strength": 0.7,
        # The flight's cliffs are the palest rock on the level (0.44 against the
        # talus's 0.42 and the fell-field's 0.38); the photographs have thin-bedded
        # charcoal tuff as the darkest thing in the frame.
        "base_pull": 0.75,
        "base_pull_window_m": 200.0,
        "base_pull_lum_gate": [0.5, 1.8],
    },
    "bb_scree_slope": {
        "family": "shale_plates",
        "seed": 504,
        "size": 1024,
        "base": [0.44, 0.43, 0.42],
        # The pale NAIP fans (0.55-0.64) are pulled toward the grey rubble too, so the
        # bed has room under the snow ceiling to read lighter than them.
        "base_pull": 0.7,
        "base_pull_window_m": 200.0,
        "base_pull_lum_gate": [0.5, 1.8],
    },
    # The summit plateau is fell-field: fist-to-head-sized fragments, so the block
    # pile at a 2.5 m tile, not the 6 m talus of the slopes below.
    # Grey-brown rubble in the photographs; the plateau's NAIP is cream, so the
    # tint takes a quarter of it and the road stays lighter than the ground.
    "bb_fellfield": {
        "family": "talus_blocks",
        "seed": 507,
        "size": 1024,
        "base": [0.42, 0.41, 0.38],
        "tile_m": 2.5,
        "tint_weight": 0.25,
        # The plateau's chalk comes down like the talus and scree: per 200 m window,
        # the pale fans inside the gate.
        "base_pull": 0.8,
        "base_pull_window_m": 200.0,
        "base_pull_lum_gate": [0.5, 1.8],
    },
    "bb_forest_floor": {
        "family": "forest_floor",
        "seed": 506,
        "size": 1024,
        "base": [0.28, 0.245, 0.195],
        "keep_tint": True,  # the imagery under a canopy is the canopy, not the floor
    },
    # In every ground photograph the road is a dusty grey-tan ribbon a shade lighter
    # than the dark scree it crosses, not a white one: under the game's sun a 0.64
    # gravel read as snow, so the bed and its decal sit at 0.50-0.52 and the
    # contract holds them a tenth over the ground.
    "bb_road_gravel": {
        "family": "gravel_bed",
        "seed": 505,
        "size": 1024,
        "base": [0.52, 0.49, 0.45],
        "keep_tint": True,
        "tile_m": 2.0,
    },
}

# NAIP quads m_3710702_se / m_3710703_sw were flown 2019-09-09 around 13:30 local
# (sun about az 200, alt 55); the fit is held to that geometry because the dark north
# faces of the cliffs would otherwise drag the fitted sun to the horizon.
IMAGERY = {
    "delight": True,
    # 2019-09-09 13:30 MDT at 37.9 N: the sun was at 56 degrees; the fit is pinned to
    # that, so the cast-shadow mask covers the ground that was actually in shadow.
    "sun_altitude_range": [55.0, 58.0],
    "sun_azimuth_hint": 200.0,
    "sun_azimuth_window": 40.0,
    "strength": 1.0,
    "tint_from_imagery": 0.6,
    # A cliff face turned away from a 50 degree sun needs more than the default 2.2x
    # to come back to the same material as its lit neighbours.
    "max_gain": 5.0,
    # Shadow refill keeps the shadow's own texture at full amplitude (no smear).
    "shadow_texture_gain": 1.0,
    # 2019 was a record snow year and the September flight still had snowfields on
    # the north faces: bright, colourless cells are refilled from the ground around.
    # Found on the raw and on the de-lit image, refilled until none is left, from
    # ground at least 10 m clear of the field, carrying that ground's texture.
    # Seeds are the raw image's bright colourless cells; growth (on the de-lit image,
    # three rounds) only within 20 m of snow already found.
    # A seed is bright (0.86), colourless (0.04), smooth (a 5x5 spread under
    # 0.02) and on ground that descends within 80 degrees of north or lies flat:
    # in the raw flight the snowfield west of Wrecked Section 1 and the plateau's
    # pale scree measure the same (0.87, 0.01, 0.01), and only the aspect tells
    # them apart (the snow on north-west and north-east faces, the scree on a
    # south-east one).
    "snow": {
        "seed_min_lum": 0.86,
        "min_lum": 0.80,
        # Old snow in the rim's shade on the plateau: grey (0.72-0.77) in the
        # flight, colourless and smooth, a fifth above its ring; on any aspect.
        "relative_seed": {"min_lum": 0.70, "min_contrast": 0.20, "max_chroma": 0.06},
        "max_chroma": 0.04,
        "seed_max_std": 0.02,
        "aspect_north_deg": 80.0,
        "any_aspect_contrast": 0.25,  # a patch that far above its ring is snow anywhere
        "min_contrast": 0.10,  # a seed stands 0.10 above its 60 m neighbourhood
        "dilate_m": 4.0,
        "grow_m": 6.0,
        "edge_contrast": 0.06,  # the field's edges go with the field
        "max_fraction": 0.06,
    },
    # Walls over 45 degrees (the cliff classifier's line) borrow only from lit
    # walls and are never lifted past their lit median, the cap feathered in from
    # 40 degrees so it draws no contour through the scree; the knee keeps the pale
    # plateau off white. Every refilled field (shadow or snow) is brought to the
    # mean colour and grain of its own 10-30 m ring, and a snowfield across a
    # forest edge is refilled as forest under the canopy and meadow in the open.
    "steep_deg": 45.0,
    "steep_feather_deg": 8.0,
    "refill_match_ring": True,
    "refill_by_cover": True,
    # The summit's outcrop shadows: the bumps were lowered out of the DEM, so the
    # horizon test cannot model their shadows; a cell under six tenths of its lit
    # 60 m ground and bluer than it is refilled as cast shadow.
    "shadow_dark_ratio": 0.6,
    # The game draws the trees: the base under a crown is the ground between the
    # trunks, refilled from the open ground round the stand at six tenths of its
    # luminance (duff under conifers), not the near-black crown of the flight.
    "canopy_refill": 0.6,
    "steep_cap": True,
    # The lit median of a wall seen from above is the scree on its ledges: the
    # walls are capped at 0.15 linear (0.42 sRGB) so the base under the charcoal
    # tile stays charcoal.
    "steep_cap_lum": 0.15,
    "knee_lum": 0.4,
    # The summit plateau's NAIP is chalk (0.81 sRGB): everything above 3,780 m, rock,
    # outcrop and refill alike, is brought to the grey-brown of the fell-field
    # photographs with its grain kept, so no refilled blob stands out of the ground
    # and the road bed (painted after, at 0.54) reads lighter than the ground.
    # The tarn under the north cirque is black in the photograph (water at a dark
    # angle); it is painted the teal Ingram Lake shows.
    # The tailings ponds in the north-west corner are turquoise in the flight:
    # flat, bright, green and blue both 0.15 over red; painted the same teal.
    "lakes": {
        "rgb": [0.20, 0.33, 0.31],
        "max_lum": 0.1,
        "min_area_m2": 400.0,
        "cyan_excess": 0.08,  # the shallow pond edge is the pond too
        "cyan_min_lum": 0.30,
        "cyan_grow_m": 4.0,
        "cyan_max_slope_deg": 8.0,  # the settled tailings are not level
        "cyan_edge_m": 12.0,  # the shallow edge half as turquoise within 12 m is pond
        "flat_rms_m": 0.02,  # a lidar surface flat to 2 cm over 400 m2 is water
        "material": "bb_lake",  # water cells take the lake tile and a WaterBlock
    },
    # The band's edge feathers over 150 m of elevation (3,705-3,855 m): a 20 m
    # feather drew the contour as a tone seam through every hollow and knoll.
    "base_pull_regions": [
        {
            "min_elevation": 3780.0,
            # Grey-brown fell-field, darker than the first guess: the bed's ceiling
            # was the binding constraint on the plateau's pale side.
            "target": [0.39, 0.38, 0.35],
            "weight": 1.0,
            "window_m": 200.0,
            # 150 m of elevation feather left the pull a no-op over most of the
            # plateau (mean 0.436 to 0.433); 80 m still hides the contour.
            "elevation_feather_m": 80.0,
        }
    ],
    # Residual sun on the rock layers is equalised per aspect within each layer.
    "aspect_flatfield": {
        "layers": [
            "bb_cliff_rock",
            "bb_cliff_rock_ew",
            "bb_scree_slope",
            "bb_talus",
            "bb_fellfield",
            "bb_forest_floor",
            "bb_tundra",
        ],
        "strength": 1.0,
        # Bins on the sun incidence the de-lighting fitted, not on compass aspect: a
        # steep north wall and a gentle north slope only share a bin when the sun
        # lit them alike; twelve bins over the incidence the layer spans, from 4
        # degrees of slope.
        "mode": "incidence",
        "bins": 12,
        "min_slope_deg": 4.0,
        # And each bin's chroma to the lit bins': the sky's lilac on the slopes
        # the sun did not reach goes with the shade.
        "chroma": True,
    },
    # A closed canopy does not shade with the terrain normal: under it the
    # correction is held to 30 % of itself.
    "canopy_gain_damp": 0.3,
}

# 3DEP is bare earth, so the bumps it keeps are talus boulders and outcrop blocks.
OBJECTS = {
    "seed": 200,
    "detect": {
        "open_m": 8.0,
        "min_height_m": 0.8,
        "min_area_m2": 2.0,
        "max_area_m2": 60.0,
        "structure_open_m": 40.0,
        "structure_min_area_m2": 60.0,
        "structure_min_height_m": 99.0,
    },
    "classify": {"rock_only": True},
    "max_rocks": 6000,
    "max_shrubs": 0,
    # The cliff layers take no lidar bumps: a "boulder" on a wall over 45 degrees
    # is a ledge or a pinnacle, and hung off its downhill lip as a block.
    "rock_layers": [
        "bb_tundra",
        "bb_talus",
        "bb_scree_slope",
        "bb_fellfield",
    ],
    "rock_gap_max_m": 0.4,  # a block is seated down to this gap under its base plane, or not placed
    "rock_material_by_layer": {
        "bb_tundra": "rock_talus",
        "bb_talus": "rock_talus",
        "bb_cliff_rock": "rock_talus",
        "bb_scree_slope": "rock_talus",
        "bb_fellfield": "rock_summit",
        "bb_cliff_rock_ew": "rock_talus",
    },
    # Grey talus on the slopes; the summit ridge outcrops are iron-stained tan.
    # Lichen on a tenth of the talus faces and a sixteenth of the summit blocks,
    # in colonies (an even third read as camouflage).
    "rock_materials": {
        "rock_talus": {
            "colour": [0.41, 0.40, 0.39],
            "strata": 0.25,
            "z_aspect": [0.4, 0.8],
            "lichen": 0.10,
        },
        # Grey-brown with the iron stain in the bed tones, not an orange face.
        "rock_summit": {
            # Grey-brown, a shade warmer than the talus rock but not tan: the
            # summit blocks are the same tuff with iron staining, not sandstone.
            "colour": [0.44, 0.41, 0.38],
            "strata": 0.45,
            "z_aspect": [0.35, 0.7],
            "lichen": 0.06,
        },
    },
    # The fell-field's scattered stones are its scree (grey talus rock); only its
    # lidar-measured outcrop blocks carry the iron-stained summit rock.
    "scatter_rock_material": {"bb_fellfield": "rock_talus"},
    # The 1 m grid keeps boulders; the stones that make talus read as talus are below
    # it, so they are scattered by density on the rock layers, biased to concave toes.
    # Blocks every few metres on the fell-field and talus (the photographs), a few
    # on the tundra benches above 3,500 m (grey rubble with sparse grass).
    "scatter": {
        "bb_talus": 200.0,
        "bb_scree_slope": 40.0,
        "bb_fellfield": 200.0,
        "bb_tundra": 8.0,
    },
    "scatter_min_elevation": {"bb_tundra": 3500.0},
    "scatter_size_m": [0.3, 1.2],
    "scatter_max": 100000,
    # Scree collects at concave toes: a 40 m window and a 0.5 m threshold see them on
    # a 1 m grid (a 15 m window never did).
    "toe_bias": 4.0,
    "toe_window_m": 40.0,
    "toe_threshold_m": 0.5,
    "spawn_clear_m": 8.0,
    "road_clear_m": 3.0,
}

# Engelmann spruce / subalpine fir up to a ~3,620 m tree line with a krummholz band
# below it, aspen only on the low Telluride-side slopes; cover comes from the imagery.
FOREST = {
    "seed": 7,
    # Trees stand where the lidar's canopy height model has a top, at its height.
    "source": "chm",
    # Tops from 1.2 m: below 2.5 m and above 3,300 m they are willow carrs and
    # krummholz mats, which share the mat shape; the meadows read as meadows with them.
    "min_tree_height_m": 1.2,
    "mat_max_height_m": 2.5,
    "mat_min_elevation_m": 3300.0,
    # Young conifers under 4 m are bushy saplings, not a spire at a tenth scale.
    "sapling_max_height_m": 4.0,
    # A bright green top under this is an aspen sucker clump, not a lone stem.
    "aspen_sapling_max_height_m": 4.5,
    "treeline_m": 3620.0,
    "krummholz_band_m": 50.0,
    "krummholz_keep": 0.55,
    "broadleaf_max_m": 3250.0,
    "spacing_m": 5.0,
    "max_trees": 130000,
    "max_slope_deg": 42.0,
    "height_bands": [[0, 3300, 12, 22], [3300, 3560, 8, 15], [3560, 9999, 4, 8]],
    "jitter_cells": 1.5,
    "gap_strength": 0.75,
}

ROADS = {
    # The gate: the bed reads 15 % lighter than the pale side of the ground either
    # side of it, per 100 m window (about a quarter over its mean): a shade lighter
    # than the scree, visible on the stippled fell-field, never white (the ceiling).
    "bed_lighter_than_ground": 1.15,
    "bed_ceiling": 0.62,
    "bed_contrast_margin_min": 0.92,  # the margin gives at most 8 %, tapered to 20 m
    "include": [
        "primary",
        "secondary",
        "tertiary",
        "unclassified",
        "residential",
        "service",
        "track",
    ],
    # The shelf road is 3.2 m wide: a spawn on it has half a metre either side of a
    # vehicle before the cut bank or the drop, and the pass summit carries a 5 degree
    # camber. Both ends of the climb get the pull-off they have in life, carved as a
    # plane under 3 % and feathered 18 m, keeping the ground's own colour (a gravel
    # turnout, not a painted bed). The pads are carved before the roads, so each
    # road's profile is fitted through its apron.
    "pads": [
        {
            "center_xy": [1611.0, -1445.0],
            "size_m": [26.0, 22.0],
            "surface": "dirt",
            "paint": False,
            "max_grade": 0.03,
            "max_cut_fill_m": 1.5,
            "feather_m": 18.0,
            "why": "the pass summit turnout, where the five ways meet at 3,910 m",
        },
        {
            "center_xy": [-1224.0, 1896.0],
            "size_m": [26.0, 22.0],
            "surface": "dirt",
            "paint": False,
            "max_grade": 0.03,
            "max_cut_fill_m": 1.5,
            "feather_m": 18.0,
            "why": "the foot of the climb under Bridal Veil Falls, at 2,756 m",
        },
    ],
    "widths": {
        "primary": 8.0,
        "secondary": 7.0,
        "tertiary": 6.0,
        "unclassified": 5.0,
        "residential": 5.0,
        "service": 4.0,
        "track": 3.2,
    },
    "material": {
        "name": "road_gravel",
        "family": "gravel",
        "seed": 900,
        "base": [0.60, 0.55, 0.47],
    },
    "surface_by_type": {
        "tertiary": "dirt",
        "unclassified": "dirt",
        "residential": "dirt",
        "service": "dirt",
        "track": "dirt",
    },
    # A 3 m budget over a 32 m window bridges the gullies the road crosses at the
    # Steps; way 125954590 is a stub that ends at the top of Bridal Veil Falls with a
    # 22 m drop in one segment, and any segment steeper than 60 % is cut out of a way.
    # Ways meet in one bed (ends within 6 m of a carved bed take its height);
    # 701139027 is a 52 m OSM duplicate of the Steps line.
    "carve": {
        "profile_window_m": 32.0,
        "feather_m": 2.0,
        "max_cut_fill_m": 3.0,
        "junction_snap_m": 8.0,
        "bridge_m": 20.0,  # two free ends this close, within 3 m of height, are one road
        "end_feather_m": 25.0,  # a cut fragment's free end fades over 25 m
        "max_profile_grade": 0.4,  # a bed still over 40 % after smoothing stays terrain
        # The two single-node dips on the side tracks are benches the 3 m cut/fill
        # budget cannot plane: a per-sample grade-change limiter only moved the
        # kinks to the edges of what it re-averaged (0.03 made it worse), so the
        # profile keeps the terrain's own bench and the limiter is off.
        "max_grade_change": 0.0,
        # The two steep side tracks whose benches dip: a wider cut/fill budget for
        # those ways alone, so their grade line can plane the bench.
        "max_cut_fill_m_by_way": {"247923922": 5.0, "935556275": 5.0},
    },
    "exclude_ways": [125954590, 701139027],
    "max_grade": 0.6,
    "cliff_cut_min_length_m": 400.0,  # a 300 m stub dangling 50 m short of the road is no road
    "surfaces": {
        "dirt": {
            "terrain_material": "bb_road_gravel",
            "texture_length_m": 5.0,
            "decal": {
                "name": "road_gravel",
                "family": "gravel_track",
                "seed": 900,
                "size": 1024,
                "base": [0.50, 0.47, 0.43],
                "edge_fraction": 0.10,  # a crisp edge: a soft one vanished in the stipple
            },
        },
    },
}

# Every spawn sits on the pass road and snaps to the carved bed keeping its authored
# sense of direction. The named places come from the trail review's GPS fixes
# (trail4runner.com, Black Bear Pass trail review) checked against the OSM way: the
# summit junction at 3,910 m, the descent into Ingram Basin, the two "Wrecked"
# obstacles, the Steps themselves (the 20-25 % ledges at 3,390 m) and the first
# hairpin of the switchbacks on the scree fans below them.
SPAWNS = [
    {
        "name": "pass_summit",
        # On the summit turnout, 30 m down the road from the pass itself: the ground
        # a vehicle line stands on is level there, which the shelf road is not.
        "lat": 37.899411,
        "lon": -107.743212,
        "heading_deg": 300.0,
        "snap_to_road": True,
        "default": True,
        "level_ground": True,  # a carved apron holds the gate below
    },
    {
        "name": "ingram_basin",
        "label": "Ingram Basin descent",
        "lat": 37.91953,
        "lon": -107.74695,
        "heading_deg": 250.0,
        "snap_to_road": True,
    },
    {
        "name": "wrecked_section_1",
        "label": "Wrecked Section 1",
        "lat": 37.921795,
        "lon": -107.758093,
        "heading_deg": 250.0,
        "snap_to_road": True,
    },
    {
        "name": "the_steps",
        "label": "The Steps",
        "lat": 37.9223208,
        "lon": -107.7607468,
        "heading_deg": 250.0,
        "snap_to_road": True,
    },
    {
        # The bottom of the mountain road, on the last way before Telluride: the
        # whole climb ahead of you, 1,150 m of it.
        "name": "bridal_veil_base",
        "label": "Foot of the climb (Bridal Veil)",
        "lat": 37.928730,
        "lon": -107.776555,
        "heading_deg": 92.0,  # up the road, not down the valley
        "snap_to_road": True,
        "level_ground": True,
    },
    {
        "name": "switchbacks",
        "label": "Bridal Veil switchbacks",
        "lat": 37.92157,
        "lon": -107.7623,
        "heading_deg": 200.0,
        "snap_to_road": True,
    },
]

# Named places along the trail, with their published fixes, so the ledger can say
# where each one falls on the level (or that it lies outside the footprint).
TRAIL_FEATURES = [
    {"name": "Black Bear Pass summit", "lat": 37.8992, "lon": -107.7431, "source": "Wikipedia"},
    {"name": "Ingram Lake", "lat": 37.9117649, "lon": -107.7457121, "source": "trail4runner"},
    {"name": "Ingram Basin", "lat": 37.918250, "lon": -107.749667, "source": "trail4runner"},
    {"name": "Wrecked Section 1", "lat": 37.921795, "lon": -107.758093, "source": "trail4runner"},
    {"name": "Wrecked Section 2", "lat": 37.922093, "lon": -107.759164, "source": "trail4runner"},
    {"name": "The Steps", "lat": 37.9223208, "lon": -107.7607468, "source": "trail4runner"},
    {"name": "Point 13510", "lat": 37.9198242, "lon": -107.7403423, "source": "trail4runner"},
    {"name": "Trico Peak", "lat": 37.90519, "lon": -107.73829, "source": "trail4runner"},
    {"name": "Telluride Peak", "lat": 37.9247846, "lon": -107.7358058, "source": "trail4runner"},
    {"name": "Bridal Veil Falls", "lat": 37.9191592, "lon": -107.7875716, "source": "trail4runner"},
    {
        "name": "Red Mountain Pass trailhead",
        "lat": 37.8954414,
        "lon": -107.7181308,
        "source": "trail4runner",
    },
]

SKY = {"time": 0.88, "utc_offset": "-6", "year": 2026, "month": 8, "day": 15}

BIOME = "Subalpine spruce-fir forest, alpine tundra and talus"
FEATURES = "3,913 m pass, one-way shelf road, the Steps, switchbacks above Bridal Veil Falls"
SUITABLE_FOR = "Rock crawling, articulation and low-range gearing tests"
ROADS_TEXT = "Black Bear Pass Road (OSM), Bridal Veil and Imogene tracks"

DESCRIPTION = (
    "Black Bear Pass and Ingram Basin, Colorado, rebuilt from USGS 3DEP 1 m lidar. A 4 km "
    "square at 1 m per sample from the 3,913 m summit down the one-way shelf road, the "
    "Steps and the switchbacks above Bridal Veil Falls. Spruce-fir forest and aspen "
    "planted from the orthoimagery below the 3,620 m tree line, talus boulders placed "
    "where the lidar found them, the shelf road carved into the ground."
)
