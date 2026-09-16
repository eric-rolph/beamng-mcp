"""Barringer Meteor Crater - authored constants shared by the generator and the level.

A 1.2 km impact bowl 170 m deep, sitting in a 2048 m square at 0.5 m per sample so the
NCALM 0.25 m lidar survives as terrain: the upturned rim strata, the talus aprons inside
the bowl, and the low ejecta swells across the desert floor. Nothing man-made is inside
the level except the rim access road and the visitor-center car park.
"""

MOD_ID = "ericrolph_meteor_crater"
DISPLAY_NAME = "Barringer Meteor Crater"
ZIP_BASENAME = "meteor_crater_ericrolph.zip"
AUTHOR = "ericrolph"

SITE = {
    "place": "Coconino County, Arizona, USA",
    "center_lat": 35.0275,
    "center_lon": -111.0225,
    "epsg": 32612,  # WGS 84 / UTM zone 12N
    "size_px": 4096,  # heightmap edge in samples (power of two)
    "square_size_m": 0.5,  # metres per sample -> 2048 m footprint
    "base_tex_px": 4096,  # the de-lit orthoimagery at 0.5 m per texel
    "detail_tex_px": 1024,
}

SOURCES = {
    "elevation": [
        # Baseline everywhere: fills anything the lidar grid does not cover.
        {"kind": "usgs_3dep", "resolution": 1.0},
        # NCALM airborne lidar, 0.25 m grid (Palucis 2010, OpenTopography OTSDEM.112011.26912.3).
        {
            "kind": "ot_grid",
            "prefix": "AZ10_Palucis/AZ10_Palucis_hh/",
            "open_name": "hdr.adf",
            "name": "az10_palucis_hh",
            "citation": "Meteor Crater, AZ (2010). NCALM / M. Palucis. https://doi.org/10.5069/G9V40S4C",
            "license": "OpenTopography - freely available; cite the DOI",
        },
    ],
    "imagery": {"kind": "usgs_naip", "resolution": 0.5},
    "roads": {"kind": "osm_overpass"},
}

TERRAIN = {
    # index 0 is the default surface; the classifier below paints the others by slope.
    "materials": [
        "mc_desert_floor",
        "mc_ejecta_gravel",
        "mc_limestone_rim",
        "mc_talus",
        "mc_rim_rubble",
        "mc_road_asphalt",
        "mc_road_dirt",
        "mc_limestone_rim_ew",
    ],
    "classify": {
        # slope in degrees -> material index; evaluated in order, first match wins.
        # The rim crest (everything above 1718 m that is not cliff) is the red-brown
        # Moenkopi rubble of the reference photographs; the plain (1679-1712 m between
        # its 5th and 99th percentiles) never reaches it, the crest (1722-1750 m) does.
        # Terrain detail is projected top-down, so a bedded tile lies as ledges on a
        # wall that faces north or south and as stripes on one that faces east or west;
        # the east- and west-facing cliffs get the same family turned a quarter.
        "rules": [
            {"min_slope": 28.0, "ew_facing": True, "material": "mc_limestone_rim_ew"},
            {"min_slope": 28.0, "material": "mc_limestone_rim"},
            {"min_elevation": 1718.0, "max_slope": 28.0, "material": "mc_rim_rubble"},
            {"min_slope": 14.0, "material": "mc_talus"},
            {"min_slope": 5.0, "material": "mc_ejecta_gravel"},
        ],
        "default": "mc_desert_floor",
    },
    "smooth_sigma_px": 0.0,
    # Holes narrower than 6 m and deeper than 3 m (the drill shaft, lidar dropouts)
    # are filled; the walls' erosion channels are wider and shallower and stay.
    "fill_pits": {"close_m": 6.0, "depth_m": 3.0},
}

# Detail families after the texture pass. ``base`` is the authored tint; with
# IMAGERY["tint_from_imagery"] the level blends it toward the measured mean colour of
# the de-lit orthoimagery under that layer, so detail and base never disagree.
PALETTE = {
    "mc_desert_floor": {
        "family": "desert_floor",
        "seed": 101,
        "size": 1024,
        "base": [0.64, 0.54, 0.40],
    },
    # The chunks are an absolute cream-grey in the family; the tint takes only a
    # third of the imagery's warm tan so they do not turn peach.
    "mc_ejecta_gravel": {
        "family": "ejecta",
        "seed": 102,
        "size": 1024,
        "base": [0.58, 0.48, 0.36],
        "tint_weight": 0.35,
    },
    "mc_limestone_rim": {
        "family": "limestone",
        "seed": 103,
        "size": 1024,
        # The tile's mean sits under the cream so its hard beds stay under 0.86
        # (nothing blooms white under the sun); the base colour is still pulled to
        # the cream the plain is measured against.
        "base": [0.72, 0.66, 0.56],
        "base_pull_target": [0.78, 0.72, 0.62],
        "tile_m": 3.0,
        "keep_tint": True,  # the authored cream, not the tan of the plain
        "base_pull": 0.8,  # the de-lit wall is the plain's tan; the ledges are cream
        # Nothing blooms white: the brightest channel rolls off to this instead of
        # clipping (a sixth of the tile's texels were pinned at 255 in red).
        "albedo_max": 0.94,
    },
    "mc_talus": {
        "family": "talus_blocks",
        "seed": 104,
        "size": 1024,
        "base": [0.50, 0.44, 0.37],
        "tile_m": 5.0,
    },
    # The crest is red-brown rubble underfoot in every rim photograph, even though the
    # NAIP shows it pale: the authored tint is kept and the detail shows through more.
    "mc_rim_rubble": {
        "family": "rim_rubble",
        "seed": 107,
        "size": 1024,
        "base": [0.50, 0.36, 0.29],  # the mix: red blocks, cream pieces, tan dust
        "tile_m": 5.0,
        "detail_strength": 0.55,
        # The crest's base is the flight's pale cream; pulled three quarters of the
        # way to the rubble's red (blue-to-red 0.45) so the base under the maroon
        # tile agrees with it, fading in over 25 m inside the layer's edge (no
        # step on the contour). Only what the flight shows warm (blue-to-red under
        # 0.80) is pulled: the grey spoil on the south rim keeps its grey. The
        # tile's dust follows the local base (no kept tint), so it does not bloom
        # cream on pale ground.
        "base_pull": 0.75,
        "base_pull_max_br": 0.80,
        "base_pull_target": [0.55, 0.36, 0.25],
        "base_pull_taper_m": 25.0,
    },
    "mc_limestone_rim_ew": {
        "family": "limestone",
        "seed": 103,
        "size": 1024,
        # The tile's mean sits under the cream so its hard beds stay under 0.86
        # (nothing blooms white under the sun); the base colour is still pulled to
        # the cream the plain is measured against.
        "base": [0.72, 0.66, 0.56],
        "base_pull_target": [0.78, 0.72, 0.62],
        "tile_m": 3.0,
        "keep_tint": True,  # the authored cream, not the tan of the plain
        "base_pull": 0.8,  # the de-lit wall is the plain's tan; the ledges are cream
        "rotate_deg": 90.0,
        # Nothing blooms white: the brightest channel rolls off to this instead of
        # clipping (a sixth of the tile's texels were pinned at 255 in red).
        "albedo_max": 0.94,
    },
    # The bed under the decal carries no shoulder (the decal's shoulder stays on
    # the decal, not repeated every 2 m across the pad and the bed margins).
    # The photograph's lot is 0.35: a 0.23 pad was the darkest thing on the map.
    "mc_road_asphalt": {
        "family": "asphalt_bed",
        "seed": 105,
        "size": 1024,
        "base": [0.34, 0.33, 0.31],
        "keep_tint": True,
        "tile_m": 8.0,  # the decal's texture length: no 2 m mottle across the lot
    },
    # A desert two-track is paler than the plain (the photographs): bed 1.06 x
    # its ground, gated per 100 m window.
    "mc_road_dirt": {
        "family": "dirt_bed",
        "seed": 106,
        "size": 1024,
        "base": [0.74, 0.67, 0.56],
        "keep_tint": True,
        "tile_m": 4.0,
    },
}

# The NAIP quad (m_3511164_se_12_030_20230627) was flown mid-afternoon; the sun it
# baked into the crater walls is fitted against the DEM and divided back out.
IMAGERY = {
    "delight": True,
    # The flight's cast shadow of the north-west crest, which the horizon model
    # never reached: a cell darker than half its 20 m mean and bluer than green
    # is refilled as cast shadow.
    "shadow_dark_ratio": 0.65,
    # The near-rim ejecta read lilac-grey: on the plain and ejecta layers a 100 m
    # neighbourhood bluer than the far plain (b/r 0.72) by 5 % is pulled to it.
    "chroma_pull": {
        "layers": ["mc_desert_floor", "mc_ejecta_gravel"],
        "target_br": 0.72,
        "window_m": 100.0,
        # And the ejecta within 120 m of the crest goes rust: chroma x 1.4, tapered.
        "near_layer": "mc_rim_rubble",
        "within_m": 120.0,
        # As a shift of each 100 m window's mean chroma, so the grey patches and
        # the soil move together; 1.15, the rubble pull carrying the red.
        "saturation_gain": 1.15,
    },
    "sun_altitude_range": [35.0, 80.0],
    "strength": 1.0,
    "tint_from_imagery": 0.6,
    # Whatever sun the model leaves on the walls (the shaded east-facing wall shipped
    # a quarter darker than its twin) is equalised per aspect within each rock layer.
    # Binned on the fitted sun's incidence (twelve bins over what each layer spans,
    # from 4 degrees of slope): eight compass bins left the rim 13 % brighter on one
    # side than the other.
    "aspect_flatfield": {
        "layers": ["mc_limestone_rim", "mc_limestone_rim_ew", "mc_talus", "mc_rim_rubble"],
        "strength": 1.0,
        "mode": "incidence",
        "bins": 12,
        "min_slope_deg": 4.0,
        # Each rock layer is equalised to its own mean (a "lit" target asked the
        # shaded wall for more than the clamp allows and left the sun in); the
        # ledges' cream comes from the base pull below, not from the flat-field.
        "target": "mean",
        "max_factor": 2.5,  # the whole correction, all passes together
        "aspect_pass": 1.0,
    },
    # The gate: the sunlit ledges read lighter than the plain, as in the aerials.
    "lighter_than": {"mc_limestone_rim": {"than": "mc_desert_floor", "factor": 1.06}},
}

# The NCALM grid is a highest-hit surface: every shrub, boulder, fence and building is
# a bump in it. Bumps come out of the ground and go back in as placed meshes.
OBJECTS = {
    "seed": 100,
    # An 8 m opening lifts the big plain junipers (5-8 m crowns) whole. No global
    # structure rule: the only compound is the authored box below, and a 40 m rule
    # took the rim crest itself for a row of roofs. A bump over 3 m tall or 60 m2, or
    # within 10 m of ground over 35 degrees (the Kaibab cliff band; the talus below
    # it lies at 30-35 and keeps its boulders), is the crater and stays.
    "detect": {
        "open_m": 8.0,
        "min_height_m": 0.45,
        "min_area_m2": 0.75,
        "max_area_m2": 60.0,
        "max_height_m": 3.0,
        "structure_open_m": 0.0,
        "cliff_slope_deg": 35.0,
        "cliff_buffer_m": 10.0,
        # A tall (over 3 m), narrow (under 12 m), long (3x) bump on gentle ground
        # away from any cliff is a berm or a wall: it leaves the ground and nothing
        # comes back (a dashed berm across the east ejecta stood as a row of
        # ledge-textured walls).
        "berm_min_elongation": 2.5,
        "berm_max_width_m": 12.0,
        "berm_min_height_m": 2.0,
    },
    # The visitor centre and its compound are a hundred metres of built ground that
    # no blob rule tells from a hummock: a 120 m opening inside this box takes it out,
    # the base colour inside it is repainted from the 30 m ring of plain around it
    # (no roofs, stripes or parked cars on the ground), and nothing that stood in it
    # comes back as a rock.
    # Both boxes take the 3DEP bare-earth ground (no building in it, the rim exact
    # at 1 m) in place of the highest-hit lidar, feathered 20 m at the edge; the
    # base colour inside is repainted from the ring of plain around each, the crest
    # and walls keeping their photograph.
    "flatten_boxes": [
        # The box reaches over the rim crest behind the visitor centre: the
        # crest's blocks and bushes (the ground-level view from the spawn) stay,
        # only what stood on the repainted plain and floor goes.
        {
            "center_xy": [110.0, 660.0],
            "size_m": 360.0,
            "use_baseline": True,
            "inpaint_ring_m": 30.0,
            "keep_objects_on_layers": [
                "mc_rim_rubble",
                "mc_limestone_rim",
                "mc_limestone_rim_ew",
                "mc_talus",
            ],
            "why": "visitor centre",
        },
        # Centred so the box and its 30 m ring stay inside the footprint (the
        # level's north edge is y 1024: a box past it quilted the padding's
        # reflections into a maze).
        {
            "center_xy": [100.0, 900.0],
            "size_m": 240.0,
            "use_baseline": True,
            "inpaint_ring_m": 30.0,
            "why": "north compound (sheds, masts, fence rows)",
        },
        {
            "center_xy": [950.0, 355.0],
            "size_m": 60.0,
            "use_baseline": True,
            "inpaint_ring_m": 20.0,
            "why": "the fence-line sheds east of the rim",
        },
        # The compound's west end (a water tank and three sheds) lay outside the
        # moved box: their own box, the ring clipped to the footprint.
        {
            "center_xy": [-55.0, 1000.0],
            "size_m": 60.0,
            "use_baseline": True,
            "inpaint_ring_m": 20.0,
            "why": "the water tank and sheds at the compound's west end",
        },
        # A dashed berm across the east ejecta (4-6 m tall, 12-35 m segments, in
        # the bare earth too): each segment stands wholly inside a 60 m box and a
        # 60 m opening takes it out; the cream it was painted is repainted from
        # the ring.
        {
            "center_xy": [536.0, 516.0],
            "size_m": 100.0,
            "open_m": 100.0,
            "inpaint_ring_m": 20.0,
            "why": "berm 1",
        },
        {
            "center_xy": [580.0, 499.0],
            "size_m": 100.0,
            "open_m": 100.0,
            "inpaint_ring_m": 20.0,
            "why": "berm 2",
        },
        {
            "center_xy": [606.0, 490.0],
            "size_m": 100.0,
            "open_m": 100.0,
            "inpaint_ring_m": 20.0,
            "why": "berm 3",
        },
        {
            "center_xy": [640.0, 477.0],
            "size_m": 100.0,
            "open_m": 100.0,
            "inpaint_ring_m": 20.0,
            "why": "berm 4",
        },
        {
            "center_xy": [669.0, 464.0],
            "size_m": 100.0,
            "open_m": 100.0,
            "inpaint_ring_m": 20.0,
            "why": "berm 5",
        },
        {
            "center_xy": [708.0, 450.0],
            "size_m": 100.0,
            "open_m": 100.0,
            "inpaint_ring_m": 20.0,
            "why": "berm 6",
        },
        {
            "center_xy": [890.0, 378.0],
            "size_m": 100.0,
            "open_m": 100.0,
            "inpaint_ring_m": 20.0,
            "why": "berm 7",
        },
        {
            "center_xy": [775.0, 442.0],
            "size_m": 160.0,
            "open_m": 60.0,
            "inpaint_ring_m": 20.0,
            "why": "berm 8 (a 45 x 12 m ridge and two mounds)",
        },
        # The drill site: the shaft is filled from the bare earth, but the
        # flattening is under a metre and the photograph can stay (an in-painted
        # 60 m square on the floor was a visible square).
        {
            "center_xy": [-40.0, -10.0],
            "size_m": 60.0,
            "use_baseline": True,
            "inpaint_ring_m": 0.0,
            "repaint_extremes": [0.45, 0.85],  # the shed's roof and its shadow go
            "why": "the drill site at the crater centre (a 10 m shaft, a spoil mound, a shed)",
        },
    ],
    # A fence remnant's posts stand up to 9 m apart.
    "fence_post_gap_m": 9.0,
    # A bump is a bush when green, dark, or under seven tenths of the ground
    # within 30 m of it (a juniper on the pale crest).
    "classify": {"green_threshold": 0.035, "dark_threshold": 0.36, "dark_ratio": 0.7},
    "max_rocks": 7000,
    "rock_gap_max_m": 0.4,  # seated down to this gap under the base plane, or not placed
    "max_shrubs": 6000,
    # The photographs have house-sized blocks only on the near-rim ejecta: a wider
    # bump on the plain is a hummock and is not placed as a rock.
    "max_rock_size_by_layer": {
        "mc_desert_floor": 2.5,
        "mc_ejecta_gravel": 4.0,
        "mc_rim_rubble": 8.0,
    },
    # The Moenkopi blocks of the crest are car-sized; a block over 4 m on the
    # crest is a cream Kaibab one.
    "rock_material_by_size": {"mc_rim_rubble": [[4.0, "rock_limestone"]]},
    "rock_material_by_layer": {
        "mc_desert_floor": "rock_limestone",
        "mc_ejecta_gravel": "rock_limestone",
        "mc_limestone_rim": "rock_limestone",
        "mc_talus": "rock_talus",
        "mc_rim_rubble": "rock_moenkopi",
        "mc_limestone_rim_ew": "rock_limestone",
    },
    # Kaibab and Moenkopi are bedded: their blocks are tabular (height 0.35-0.65 of
    # width) with a flat base; only the mixed talus keeps rounder shapes.
    "rock_materials": {
        # Desert rock carries a hundredth of lichen, not the alpine third.
        "rock_limestone": {
            "colour": [0.68, 0.62, 0.52],
            "strata": 0.5,
            "z_aspect": [0.35, 0.65],
            "lichen": 0.01,
        },
        "rock_talus": {
            "colour": [0.50, 0.45, 0.40],
            "strata": 0.2,
            "z_aspect": [0.4, 0.85],
            "lichen": 0.01,
        },
        # The big blocks on the rim crest: a dark maroon-brown, not orange.
        "rock_moenkopi": {
            "colour": [0.44, 0.30, 0.24],
            "strata": 0.35,
            "z_aspect": [0.35, 0.65],
            "lichen": 0.01,
        },
    },
    # Dark junipers dot the plain; on the rim and the inner slopes the bushes are the
    # smaller grey-green saltbush and sage of the rim photographs.
    "shrub_materials": {
        "shrub_juniper": {
            "colour": [0.13, 0.18, 0.15],
            "light_colour": [0.3, 0.37, 0.23],
            "height": 1.0,
            "width": 1.3,
        },
        "shrub_sage": {
            # Grey-green, not chartreuse: green over blue under 0.06 and red within
            # a fiftieth of green, the desert sage of the rim photographs.
            "colour": [0.36, 0.38, 0.33],
            "light_colour": [0.58, 0.59, 0.52],
            "height": 0.6,
            "width": 0.9,
            "max_width_m": 2.2,  # sage is never a five-metre bush
        },
    },
    # A bush the lidar measured at 1.5 m or more is a juniper on any layer.
    "shrub_material_by_height": [[1.5, "shrub_juniper"]],
    "shrub_material_by_layer": {
        "mc_desert_floor": "shrub_juniper",
        "mc_ejecta_gravel": "shrub_juniper",
        "mc_limestone_rim": "shrub_sage",
        "mc_limestone_rim_ew": "shrub_sage",
        "mc_talus": "shrub_sage",
        "mc_rim_rubble": "shrub_sage",
    },
    # Junipers on the plain that the lidar did not keep still darken the imagery.
    # Junipers the lidar did not keep still darken the plain against a 20 m median;
    # the finder stays on the plain and the ejecta below 12 degrees, so the flight's
    # shadow on the inner wall never becomes a bush.
    "shrubs_from_imagery": {
        "contrast": 0.20,
        "max_brightness": 0.45,
        "min_area_m2": 1.0,
        "max_area_m2": 25.0,
        "max": 5000,
        "layers": ["mc_desert_floor", "mc_ejecta_gravel", "mc_rim_rubble"],
        "max_slope_deg": 28.0,  # the crest layer reaches 28 degrees by construction
        "erase_unplaced": True,  # a dark dot nothing stands on is repainted
    },
    "spawn_clear_m": 8.0,
    "road_clear_m": 3.0,
}

ROADS = {
    # The visitor-centre car park: one asphalt pad where the aerial shows one dark
    # rectangle, so the default spawn stands on a lot and not on painted plain.
    # The whole visitor-centre lot (its southern angled rows too) and the RV lot
    # the loop encloses.
    # Each pad takes the lot's own outline from the flight (the dark cells inside
    # the rectangle), is carved as a plane under 3 % grade within 1.5 m of the
    # ground, and is feathered 12 m in height and in colour.
    "pads": [
        {
            "center_xy": [5.0, 641.0],
            "size_m": [170.0, 112.0],
            "surface": "paved",
            "from_imagery": {"max_lum": 0.50, "min_area_m2": 400.0, "exclude_green": 0.03},
            "max_grade": 0.03,
            # The lot is cut into the rim's flank behind a retaining wall the lidar
            # holds at 4-5 m: a 6 m budget lets the plane hold to the wall's foot
            # and the kerb batter start from the plane, not from a ramp.
            "max_cut_fill_m": 6.0,
            # The kerb: the lidar's retaining wall within 30 m is held under 15
            # degrees (the lot is cut 2.5 m into the flank at its east end, and a
            # 15 degree batter needs the width), and the ground round the lot is
            # pinned to the plain.
            # The lot keeps the flight's own grain over its painted mean, and
            # whatever stood in it (a car, a roof) is repainted from its 6 m ring.
            "keep_flight_grain": True,
            "repaint_outside": [0.6, 1.6],
            "kerb_m": 30.0,
            "kerb_max_slope_deg": 15.0,
            "pin_layer": "mc_desert_floor",
            "pin_layer_m": 15.0,
            # The lot's low edge is 2.5 m of fill on a 6-9 % flank: over 12 m that
            # batter was a 20 % ramp the access road followed; over 40 m it is 6 %.
            "feather_m": 40.0,
        },
        # The RV loop is a pale gravel lot in the flight, not asphalt.
        {
            "center_xy": [160.0, 712.0],
            "size_m": [40.0, 25.0],
            "surface": "dirt",
            "paint": False,  # the flight's own gravel colour, no stamp
            "max_grade": 0.03,
            "max_cut_fill_m": 1.5,
            "feather_m": 12.0,
        },
    ],
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
    # Meteor Crater Road and the visitor-centre loop are paved; everything else is a
    # dirt two-track. The bed is carved flat into the terrain and painted with a
    # terrain material whose ground model the tyres feel; the decal is the look.
    "surface_by_type": {
        "tertiary": "paved",
        "unclassified": "paved",
        "residential": "paved",
        "service": "paved",
        "track": "dirt",
    },
    "carve": {
        # The paved road is graded: no node-to-node grade over 11.5 % where the
        # budget allows (the access road left the lot at 14 % down the rim flank).
        "max_grade_by_surface": {"paved": 0.115},
        "profile_window_m": 40.0,
        "feather_m": 4.0,
        "max_cut_fill_m": 1.5,
        "junction_snap_m": 6.0,
        "end_feather_m": 10.0,
    },
    # The two-tracks read pale on the plain and on the near-white rim: the dirt
    # bed is held 6 % lighter than its margins per 100 m window, the margin giving
    # at most a tenth and the bed taking the rest as a floor. Asphalt is dark.
    # No 10 m of the paved road steeper than 12 %: the access road leaves the lot
    # down its batter and the rim flank, and a real paved road is graded.
    "max_grade_10m": {"paved": 0.12},
    "bed_lighter_than_ground": {"dirt": 1.06},
    "bed_contrast_margin_min": 0.98,  # the bed takes the contrast, not a dark corridor
    "bed_ceiling": 0.78,  # a two-track on the near-white rim may go this pale
    "surfaces": {
        "paved": {
            "terrain_material": "mc_road_asphalt",
            "texture_length_m": 8.0,
            "decal": {
                "name": "road_asphalt",
                "family": "asphalt",
                "seed": 901,
                "size": 1024,
                "base": [0.30, 0.30, 0.29],
                "edge_fraction": 0.03,  # an 18 cm soft edge; the shoulder is inside it
            },
        },
        "dirt": {
            "terrain_material": "mc_road_dirt",
            "texture_length_m": 6.0,
            "decal": {
                "name": "road_dirt",
                "family": "dirt_track",
                "seed": 900,
                "size": 1024,
                "base": [0.72, 0.65, 0.54],
                "edge_fraction": 0.08,  # a two-track has an edge
            },
        },
    },
}

SPAWNS = [
    {
        "name": "north_rim_visitor_center",
        "lat": 35.0335,
        "lon": -111.0222,
        "heading_deg": 180.0,
        "snap_to_road": True,
        "default": True,
    },
    {"name": "crater_floor", "lat": 35.0275, "lon": -111.0225, "heading_deg": 0.0},
    # The flat pad on the outer flank of the south rim (under 8 degrees over 10 m),
    # not the cliff band a car would slide down.
    # 130 m east of the first pick, off the mine spoil (which the rubble pull
    # rightly leaves grey) and on warm red-brown crest.
    {"name": "south_rim", "lat": 35.02169, "lon": -111.02162, "heading_deg": 0.0},
]

SKY = {"time": 0.14, "utc_offset": "-7", "year": 2026, "month": 6, "day": 20}

BIOME = "Desert impact crater"
FEATURES = "1.2 km impact bowl, rim strata, talus, ejecta flats"
SUITABLE_FOR = "High-speed perimeter runs, scree hill climbs, rim drops"
ROADS_TEXT = "Paved access road and visitor-center loop, dirt two-tracks; the rest is open desert"

DESCRIPTION = (
    "Barringer Meteor Crater, Arizona, rebuilt from 0.25 m NCALM airborne lidar and "
    "USGS 3DEP. A 1.2 km, 170 m deep impact bowl in a 2 km square at 0.5 m per terrain "
    "sample: rim strata, interior talus aprons and the ejecta ripples of the desert floor "
    "are all measured, not sculpted. Every boulder and juniper the lidar and the imagery "
    "found is a placed object, the roads are carved into the ground, and the orthoimagery "
    "was de-lit against the DEM so the crater walls read under the game's own sun."
)
