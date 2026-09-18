# GIS maps pack: six real landscapes for BeamNG.drive from public data

Six BeamNG.drive levels whose terrain is measured, not sculpted: every heightmap sample
comes from public airborne lidar, every ground colour from public orthoimagery, every
road centreline from OpenStreetMap. Built on the same evidence chain as the Giant Props
pack (`examples/giant_props`): a deterministic generator owns every number,
an authoring handoff JSON is the single source of truth the tests hash against, and
every file the game reads is generated, never hand-edited.

| Map key | Level | Footprint | Sample | Elevation sources | The bit |
| --- | --- | --- | --- | --- | --- |
| `meteor_crater` | Barringer Meteor Crater | 2048 m | 1 m | NCALM 0.25 m lidar (OpenTopography) over USGS 3DEP 1 m | A 1.2 km, 170 m deep impact bowl: rim strata, talus aprons, ejecta ripples. Perimeter runs, scree climbs, rim drops. |
| `wallace_creek` | Carrizo Plain - Wallace Creek | 4096 m | 1 m | B4 0.5 m lidar (OpenTopography) over USGS 3DEP 1 m | The San Andreas surface trace: the 130 m offset channel, sag ponds, pressure ridges, scarps. Trophy-truck country. |
| `factory_butte` | Factory Butte Badlands | 4096 m | 1 m | Utah statewide 1 m lidar via USGS 3DEP | Mancos Shale rills, clay fins and mud-wash flats. Natural half-pipes and spine transfers. |
| `mt_st_helens` | Mount St. Helens Pumice Plain | 6144 m | 1.5 m | USGS 3DEP 1 m (2018 lidar) | The 1980 crater headwall, the lava dome, braided ash canyons down to Spirit Lake. |
| `black_bear_pass` | Black Bear Pass | 8192 m | 1 m | USGS 3DEP 1 m (2020 lidar) | 3,913 m summit, one-way shelf road, the Steps, switchbacks above Bridal Veil Falls, then the whole box canyon over Pandora into Telluride and up the far wall to Tomboy and Savage Basin. Buildings modelled from OSM outlines at lidar heights. |
| `bingham_canyon` | Bingham Canyon Mine | 6144 m | 1.5 m | USGS 3DEP 1 m (2023 lidar) | An inverted mountain: 15 m benches spiralling 1.2 km down, linked by continuous haul roads. |

None of the six has a building, a tree or a guardrail to model. That is the point: the
soft-body physics engine gets a measured surface and nothing else in the way.

## The process (the five GIS steps, automated)

The manual workflow the pack replaces is: acquire a DEM and orthophotos, crop a square
power-of-two footprint in QGIS, export a 16-bit heightmap, import it in the World
Editor, then lay roads and textures. Each step is a stage of `build.py`:

1. **fetch** (`maplib/gis_sources.py`): USGS 3DEP is exported straight from the
   `3DEPElevation` image service as float32 GeoTIFF tiles in the level's own UTM zone.
   The OpenTopography raster bucket is a plain S3 listing, so the B4 tiles are fetched
   by name and the 2.3 GB NCALM Meteor Crater grid is downloaded once, windowed to the
   footprint and deleted. NAIP orthoimagery comes from the USGS NAIP image service, and
   road centrelines from an Overpass mirror. Everything lands in `<map>/data/`, cached
   and re-validated by opening the file, never by trusting its presence.
2. **terrain** (`maplib/heightmap.py`): every source is resampled onto the level grid
   (area-average when downsampling lidar, bilinear otherwise), the lidar grid is levelled
   onto the 3DEP datum by the median offset in the overlap, composited with a feathered
   edge, holes are filled by nearest neighbour, single-sample lidar spikes are clamped,
   and a layer map is painted from slope and elevation rules in the spec.
3. **level** (`maplib/level_builder.py`): heights are encoded as u16 relative to the
   lowest sample with `maxHeight` sized to the real relief (0.3 cm steps on the crater,
   1.7 cm on the pass), written as a version-9 `theTerrain.ter` **and** as the 16-bit
   `theTerrain.terrainheightmap.png` the Import Terrain tool accepts. The level tree
   (`info.json`, `main/` scene files, terrain materials, the decal-road material, spawn
   points, previews, minimap) is generated from the spec.
4. **dist** (`maplib/packaging.py`): a `ZIP_STORED` archive with only approved BeamNG
   roots, monotonic never-in-the-future member timestamps and a SHA-256 lock.

### The art pass

Every map de-lights its orthoimagery. Two carry the full treatment - objects, forest,
carved beds and their own tuned colour - and the other four carry a first-pass
`IMAGERY` block that turns the illumination model on with nothing site-specific fitted
yet. Each piece is a spec block, so any map can opt in to any of it.

- **`IMAGERY`** (`maplib/imagery.py`): the orthoimagery is de-lit against the DEM. The
  baked sun is fitted (hillshade correlation, bounded by the flight's real geometry),
  slope shading, a cast-shadow horizon test and sky occlusion are modelled, and the
  illumination is divided out with a Minnaert exponent fitted from the image. Cast
  shadows borrow the lit neighbourhood's colour and keep only their relative texture;
  a steep cell borrows only from lit steep cells and is never lifted past their
  median; the flight's snowfields are found as bright colourless cells (gated by
  aspect) and refilled the same way, with the ring's grain carried in; every refilled
  field is matched to its ring's mean colour and grain band by band; where a canopy
  height model exists, the crowns' cast shadows are refilled and the crowns
  themselves are repainted as the ground between the trunks. A per-layer flat-field binned on the fitted sun's incidence takes
  out what the model left, and a palette entry may pull its layer's base colour
  toward its own base (`base_pull`) or take less of the imagery tint
  (`tint_weight`). Detail tints blend toward the measured colour under each layer.
- **`OBJECTS`** (`maplib/objects.py`, `maplib/meshgen.py`): a grey opening lifts every
  compact bump out of the surface (junipers, boulders, fences, the visitor centre on
  the crater's highest-hit grid; talus boulders on bare-earth 3DEP). The imagery under
  a bump decides rock or shrub; wires, fences and walls (long thin blobs of any size)
  and buildings are flattened and dropped, rows of posts on a straight line too. Rocks
  and shrubs come back as procedural Collada shapes (no Blender) placed as Forest
  items, sized to their own footprint and height, with the rock and shrub material
  chosen by the terrain layer under them (`rock_material_by_layer`,
  `shrub_material_by_layer`). The terrain block sits half a square in from the
  footprint corner so the game's height samples land on the GIS cell centres, and
  every item is seated on the bilinear ground under its final position.
- **`FOREST`** (`maplib/vegetation.py`, `maplib/pointcloud.py`): with a
  `SOURCES["pointcloud"]` entry (a USGS 3DEP resource on the public Entwine index)
  the fetch stage streams the footprint's LAZ nodes through `laspy`, grids the
  highest and the ground returns at 1 m and deletes the points; the terrain stage
  turns that into a canopy height model and `FOREST["source"] = "chm"` plants a
  tree at every measured top with its measured height (species by elevation and
  imagery). Without a point cloud, tree cover is classified from the imagery and
  planted on a jittered grid thinned by local cover. Three crossed alpha-tested cards
  plus top-view whorl tiers on a real trunk, trunk collision.
- **`ROADS["carve"]`** (`maplib/roads.py`): centrelines get a bounded smoothed grade
  line and a flat, feathered bed; the bed is painted with a road terrain material
  (asphalt / dirt / gravel ground model) and decalled per surface.
- **Textures** (`maplib/texture_kit.py`, `maplib/foliage_textures.py`): periodic
  Worley cells (each with its own tilted facet) and anisotropic noise give talus
  blocks, ejecta chunks, fractured cliff plates, bedded ledges with red interbeds and
  varnish, shale plates, tussocks over bare soil and rutted decals their shapes, with
  per-channel tints for lichen, soil and rust; 1024 px detail sets. Foliage cards,
  bark and rock sets are generated the same way. Terrain materials tile in world
  space, so road beds use isotropic families and the decal carries the ruts.
- **Review** (`critic_sheets.py`, `critic_rubric.md`): `python
  examples/gis_maps/critic_sheets.py <key>` renders the sheets a critic looks at
  (overview under the level sun, driver and drone views from every spawn with all
  placed objects and the detail textures tiled in the near field, texture swatches,
  every shape rendered through its own textures, placement map, road profile) into
  `<map>/authoring/critic/`. The rubric says what "convincing" means per sheet; the
  critic's verdict per round is recorded in each map's `DESIGN.md`.

```bash
pip install -e ".[dev]"                                # rasterio, scipy, requests via the gis extra
python examples/gis_maps/build.py --list
python examples/gis_maps/build.py meteor_crater all        # fetch -> terrain -> level -> dist
python examples/gis_maps/build.py --all all                # every map
python -m pytest -q tests/test_gis_maps_pack.py   # static gates
```

### Buildings (Black Bear Pass)

Black Bear Pass grew to the whole box canyon, which put Telluride, Pandora and the
Tomboy and Savage Basin workings inside the level. A town drawn as bare ground with a
street grid painted on it reads worse than no town, so `maplib/buildings.py` models
them - and holds them to the same rule as the ground, that nothing is invented:

| what | where it comes from |
| --- | --- |
| Outline | OSM `building` ways (ODbL), projected onto the level grid |
| Eaves and ridge height | The 3DEP point cloud's highest-hit surface minus its classified ground, inside that outline: the low quartile is the eaves, the 90th percentile the ridge |
| Roof shape | Fitted to the same returns. Level means flat; a rise to a line means gabled; a fall away at both ends means hipped. The ridge runs along the outline's own long axis, from a min-area rectangle |
| Roof colour | The median of the de-lit orthophoto inside the outline, snapped to the nearest of eight roofing colours, so a red barn stays red without a hundred slightly different greys |
| Walls | Procedural, in the family OSM's `building` and `building:material` tags name - clapboard, board-and-batten, corrugated steel, brick or coursed rubble - in a colour picked by a hash of the OSM id |

Nothing is traced from a photograph of a facade. A wall is a texture family the way a
talus block is: a 4 m tile with a window on it at the height windows are, which is what
a street reads as from the pass.

Two consequences the rest of the pipeline has to know about, and does. To the bump
detector a roof is a boulder; to the canopy height model it is a nine metre tree. Both
take the building mask as an exclusion, and the ledger records how many objects and
trees it took off the roofs.

The terrain needs no healing under a building: 3DEP's 1 m raster is a bare-earth DTM
with no buildings in it. Nor does the photograph: the roof it recorded is exactly where
the roof mesh goes.

Buildings ship as one Collada shape per 512 m tile, placed as a `TSStatic` with
`Visible Mesh Final` collision, so the town culls by tile and you can drive into a wall.

## Getting the maps into your game

The shortest version needs no Python at all: download the six `*_ericrolph.zip` files
from the GitHub Release (tag `gis-maps-v1`, built by `.github/workflows/gis-maps-release.yml`
from the branch) into `%LOCALAPPDATA%\BeamNG\BeamNG.drive\current\mods\`. From PowerShell:

```powershell
$mods = "$env:LOCALAPPDATA\BeamNG\BeamNG.drive\current\mods"
foreach ($k in 'meteor_crater','wallace_creek','factory_butte','mt_st_helens','black_bear_pass','bingham_canyon') {
  Invoke-WebRequest "https://github.com/eric-rolph/beamng-mcp/releases/download/gis-maps-v1/${k}_ericrolph.zip" -OutFile "$mods\${k}_ericrolph.zip"
}
```

With the repository checked out, the same thing hash-verified, from the repository root
with BeamNG closed:

```powershell
pip install -e ".[dev]"
python examples\gis_maps\install_local.py --release gis-maps-v1     # download from the release, verify, deploy
python examples\gis_maps\install_local.py                              # or build from public data, then deploy
python examples\gis_maps\install_local.py --parts C:\path\to\parts    # or rejoin a delivered build, then deploy
```

The release is rebuilt by dispatching the workflow (Actions > GIS maps release > Run
workflow, tag `gis-maps-v1`) or by pushing a `gis-maps-v*` tag; the runner fetches
the public data, builds, runs the static gates and uploads the ZIPs, locks, handoffs
and `SHA256SUMS.txt`.

`install_local.py` makes sure every map has a dist ZIP that matches its lock (rejoined
from delivered parts, or built) and then runs `deploy_local.py --deploy`. The pieces it
orchestrates are below.

The level ZIPs (80-90 MiB each) are build output, not repository content. Two ways to
have them locally:

1. **Rejoin a delivered build.** A build handed over from a session arrives as
   `<key>_ericrolph.zip.partN` pieces plus `SHA256SUMS.txt` (whole ZIPs exceed the
   30 MiB delivery limit). Put every part and the sums file in one folder, then:

   ```powershell
   python examples\gis_maps\join_parts.py C:\path\to\downloaded_parts
   ```

   That verifies each part and each rejoined ZIP against `SHA256SUMS.txt`, writes the
   ZIPs to `examples\gis_maps\<key>\dist\` and writes their release locks. A mismatch deletes
   the ZIP rather than leaving something unverifiable to install.

2. **Rebuild from the public data.** `python examples\gis_maps\build.py --all all` downloads
   about 3 GB (2.3 GB of it the Meteor Crater lidar grid) and rebuilds everything;
   allow ten to fifteen minutes.

Then deploy, with BeamNG closed:

```powershell
python examples\gis_maps\deploy_local.py            # report: missing / stale / current per map
python examples\gis_maps\deploy_local.py --deploy   # copy what is stale into the play profile, hash-verified
```

`deploy_local.py` targets `%LOCALAPPDATA%\BeamNG\BeamNG.drive\current\mods\` (set
`BEAMNG_MAPS_PROFILE` to the profile root to override), refuses to run while the game
is open, and refuses if any other zip below `mods\` already carries one of the
`levels/ericrolph_<key>/` namespaces (BeamNG mounts every zip recursively, so a stale
copy shadows the release). Launch BeamNG.drive, then Freeroam > Select Level: the six
levels are listed under their display names (Barringer Meteor Crater, Carrizo Plain -
Wallace Creek, Factory Butte Badlands, Mount St. Helens Pumice Plain, Black Bear Pass,
Bingham Canyon Mine), each with three spawn points.

If a level does not appear after deployment, the first place to look is
`%LOCALAPPDATA%\BeamNG\BeamNG.drive\current\beamng.log` for lines mentioning
`ericrolph_`; that log says whether the zip was mounted and whether `info.json` or
the terrain failed to load.

## Layout

- `maplib/`: shared toolkit (`gis_sources.py`, `heightmap.py`, `texture_kit.py`,
  `level_builder.py`, `packaging.py`, `pipeline.py`).
- `build.py` (stages), `join_parts.py` (rejoin a delivered build), `deploy_local.py`
  (verified sync into the play profile), `install_local.py` (all of the above in one command).
- `<map_key>/spec.py`: the map's authored constants: site centre, UTM zone, sample size,
  data sources with citations, terrain materials and slope rules, road widths, spawns,
  time of day and the selector copy. The generator consumes only this.
- `<map_key>/DESIGN.md`: the blueprint and the build ledger (what the data measured).
- `<map_key>/authoring/`: `<mod_id>.handoff.json` (footprint, sources, terrain stats,
  spawn coordinates, roads, SHA-256 of every shipped terrain file) and the thumbnail.
  Tracked: this is the evidence.
- `<map_key>/data/`, `mod/`, `dist/`: downloads, the generated level tree and the ZIP.
  Not tracked (up to 2 GB of public data per map); rebuilt by `build.py`.

## Editing a map in BeamNG's own editors

Nothing here is a private format. Every map is written as the artefacts the shipped
World Editor tools own, so a level opens with `Ctrl+E` and each tool finds its own data
already populated - the generator is the first pass, the editors are the second.

| Editor | What the pack ships for it | Where |
| --- | --- | --- |
| **Terrain Editor** (sculpt, smooth, flatten) | `theTerrain.ter`, version 9: u16 heights and the u8 layer map for the level's own sample count (4096 x 4096, 8192 x 8192 on Black Bear Pass, 2048 x 2048 on Meteor Crater), plus the `.terrain.json` companion the engine writes itself | `levels/<mod_id>/theTerrain.ter` |
| **Terrain Painter** (paint surface materials) | The `.ter`'s layer map, painted by the slope and elevation classifier, over the level's TerrainMaterials - each one a v1.5 base + macro + detail set with its own groundmodel (`DIRT`, `ROCK`, `ASPHALT`, ...), so the tyres already know what they are on | `art/terrains/main.materials.json` |
| **Terrain Import/Export Heightmap** | A 16-bit greyscale PNG of the same heightmap, at the same sample count | `levels/<mod_id>/theTerrain.terrainheightmap.png` |
| **Decal Road Editor** | Every road as a `DecalRoad` with `improvedSpline`, per-node width, `material`, `textureLength`, `breakAngle`, `renderPriority`, `startEndFade` and `drivability` - the nodes are the OSM centreline draped on the carved bed | `main/MissionGroup/roads/items.level.json` |
| **Forest Editor** | A `Forest` object over a `forest4.json` of placed items, each typed by a `TSForestItemData` with `collidable`, `mass`, `radius`, `rigidity` and `snapRotationToTerrain` - so the rocks and trees have collision without a hand pass | `forest/<mod_id>.forest4.json`, `art/forest/managedItemData.json` |

To re-import a heightmap by hand, Terrain Editor's Import needs the numbers the pack
already knows. They are in each map's handoff under `terrain`:

| Map | Samples | Square size | Height scale (`maxHeight`) | Real elevation the 0..maxHeight band covers |
| --- | --- | --- | --- | --- |
| `black_bear_pass` | 8192 | 1.0 m | (rebuilding) | (rebuilding) |
| `meteor_crater` | 2048 | 1.0 m | 192 m | 1561.8 - 1750.4 m |
| `bingham_canyon` | 4096 | 1.5 m | 1556 m | 1263.8 - 2803.2 m |
| `factory_butte` | 4096 | 1.0 m | 106 m | 1353.0 - 1456.6 m |
| `mt_st_helens` | 4096 | 1.5 m | 1547 m | 946.3 - 2476.9 m |
| `wallace_creek` | 4096 | 1.0 m | 417 m | 593.3 - 1005.1 m |

Two things the pack deliberately does not use:

- **Mesh Road**. A mesh road is for a deck that leaves the ground - a bridge, a banked
  bowl, a kerbed carriageway. Every road on these maps is a real road surveyed on the
  real hillside, and the generator carves its bed into the terrain before it lays the
  decal, so the surface the tyres meet is the terrain itself and the decal only colours
  it. A mesh road here would float over the bed it was fitted to. Add one in the editor
  where you want something the ground does not do.
- **Lane markings**. The Black Bear Pass shelf road and the crater's rim access road
  carry no paint in the reference photographs, so the asphalt tile has wear bands, a
  gravel shoulder and cracks, and no centre line.

## Terrain conventions that are easy to get wrong

- **`.ter` layout (version 9)**: u8 version, u32 size, u16 heights, u8 layer indices,
  u32 count, then material internal names each prefixed by a u8 length. Verified against
  a shipped level's binary. Version 8 files carry an extra `size * size * 4` byte block
  between the layer map and the names; version 9 does not.
- **Height scale**: `metres = stored * maxHeight / 65536`. The pack sets `maxHeight` to
  the real relief plus 1 %, so precision is spent on terrain that exists.
- **Grid order**: the `.ter` starts at the TerrainBlock position (south-west corner) and
  runs east then north. The exported `terrainheightmap.png` is written north-up like any
  map image. If a manual Import Terrain of the PNG comes out mirrored north-south, flip
  the image vertically; the `.ter` the pack ships is already correct and authoritative.
  The shipped base texture set (`t_base_*.png`) is written south-up for the same
  reason: the engine maps an image's first row onto the terrain's y = 0, so a north-up
  base came out mirrored against the heightmap in-game (the visitor centre on the
  wrong rim). Every other image the pack writes (previews, thumbnails, the exported
  heightmap) stays north-up.
- **OSM road extracts are tracked** (`<map>/data/osm/roads.json`, the one piece of
  fetched data in the tree): the fetch stage keeps an existing extract, so a build is
  reproducible against the snapshot and the release runner never waits on Overpass.
  Refetch one with `build.py <key> fetch --force`.
- **Base, detail and macro texture sizes**: a TerrainMaterial's `*TexSize` fields are
  documented as world metres for one tile of the map, and a shipped 2048 m level does set
  its base size to 2048 while its texture set declares 2048 pixels. That level is sampled
  at 1 m, where metres and terrain squares are the same number. They are not the same on
  every map, and the engine uses **squares**: Meteor Crater is 2048 m across sampled at
  0.5 m, was given 2048, and BeamNG drew the orthoimagery tiled two by two (mirrored)
  across the level - four craters, one per quadrant, with the real crater's geometry
  showing through the middle. The pack authors every size in metres and divides by
  `square_size_m` on the way out, so the base map covers the terrain exactly once and
  detail and macro keep their authored periods whatever the sampling.
- **Sample at 1 m unless you have a reason not to.** The conversion above did not settle
  it: the level still tiled with the sample count in the field. The two readings of
  `*BaseTexSize` - world metres and terrain squares - are only distinguishable on a map
  whose sampling is not 1 m, and every map the pack samples at 1 m has drawn its
  orthoimagery once. Meteor Crater now samples at 1 m as well, so metres and squares are
  the same number and the field means the same thing either way. Sub-metre sampling is
  not worth a level that draws its photograph four times; the photograph keeps its own
  resolution regardless, since `base_tex_px` is independent of the sample count (4096 px
  over 2048 m is still 0.5 m per texel).
- **Far-field bake**: `TerrainBlock.baseTexSize` is the resolution, in pixels, the engine
  bakes the whole-level base map at once the cells fall out of detail range - which is
  most of the map from any ridge. It has to match the texture set's `baseTexSize`, or a
  4096 px orthophoto is shown as a 2048 px copy of itself.
- **Vehicle heading**: vehicles spawn nose toward the spawn marker's -Y, so a compass
  heading of 0 (north) is a 180-degree marker yaw.

## Data sources and licences

- USGS 3DEP elevation (public domain, U.S. Geological Survey).
- NCALM Meteor Crater lidar, Palucis 2010, OpenTopography `OTSDEM.112011.26912.3`,
  https://doi.org/10.5069/G9V40S4C (freely available; cite the DOI).
- B4 Project lidar, Southern San Andreas and San Jacinto faults 2005, USGS/NSF/NCALM,
  OpenTopography `OTSDEM.032018.32611.1`, https://doi.org/10.5066/F7TQ5ZQ6 (public domain).
- NAIP orthoimagery via The National Map (public domain, USDA/USGS).
- Road centrelines (c) OpenStreetMap contributors, ODbL 1.0.

Each level's `info.json` description carries this attribution.

## What is and is not verified

The static gates prove the artefacts: header, size, material names, layer indices and
heightmap rows of the `.ter`; the PNG heightmap is 16-bit and row-consistent with it;
every scene object parses and its parent exists; every referenced texture ships; the
ZIP matches its lock. Wherever a map de-lights, they also hold measured contracts on
the shipped base colour and terrain: the road bed lighter than the pale side of its
margin per 100 m window, every large refilled field (cast shadow or snow) within a
band of its ring's luminance and grain on the base the game draws, no clipped or
near-black cells per layer, the flat-field's residual by aspect, the decal roads' node
steps and the paved road's steepest 10 m, and a car park's kerb batter. Live behaviour
(the level loading in BeamNG, decal roads draping, material blending) has been
exercised on the user's install for the first two releases (the mirrored base and the
white road were found there); everything since has been judged on the critic sheets
and the data, so a green static suite is still not a play-test.
