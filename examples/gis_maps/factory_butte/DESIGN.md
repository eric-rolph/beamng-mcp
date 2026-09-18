# Factory Butte Badlands - design blueprint

Status: **built from public data, static gates green** (2026-09-15). Not yet play-tested.

## The site

Factory Butte is a 300 m mesa of Mancos Shale capped by sandstone, standing over a
plain of grey shale badlands near Hanksville, Utah. The shale erodes into thousands of
tightly spaced parallel rills, knife-edge clay fins and broad mud-wash flats. The clay
supports almost no vegetation, and the area is a designated open OHV play area
(Swing Arm City), so there is nothing to model but the ground.

## The dataset

- **Utah statewide 1 m lidar** (UT StatewideSouth 2020, Utah Geospatial Resource
  Center) as published through USGS 3DEP. Utah's lidar is public domain.
- **USGS NAIP** at 1 m; **OpenStreetMap** for the highway and the play-area tracks.

## Why the physics pops

Mancos Shale rills are 1-3 m apart with 0.5-2 m relief: at 1 m per sample they arrive
in the heightmap as a washboard of natural half-pipes and spines. Where the rills feed
into the mud-wash flats the transition is a measured 20-40 degree slope, and the fins
between drainages are real ridgelines a UTV can balance along.

## Driving profile

Free-ride, extreme off-road buggy testing, dirt-bike and UTV lines through the rills,
and the butte's own scree skirt as a hill climb. No vegetation, no props.

## Critic ledger

Each round the critic (a separate agent holding `critic_rubric.md`) reviews the
sheets in `authoring/critic/` and writes findings with generator fixes; the round is
closed when every finding is a spec or parameter change in the tree.

This map has had no round yet. What it has shipped is terrain, slope-painted materials and
OSM roads, with none of the art pass the two reviewed maps carry; what has been written
since is noted per line below, none of it built. Three things measured from the committed
handoff are round 1's agenda, before a sheet is rendered:

- ~~**The base colour: the flight's sun is out of it on paper only.**~~ Overtaken by round 1: the de-lighting does run in the published build, and what it leaves is flat rather than lit. See the round below.

  Written before that build: The last build's
  handoff records `imagery.delight` as `false` - the NAIP orthophoto went down as it was
  flown, shadows baked in, which is the rubric's first line and what the two reviewed maps
  spent most of their rounds on. A first-pass `IMAGERY` block turning the de-lighting on
  has since been written for this map, with nothing yet fitted to the site: no sun range
  narrowed to the flight's own geometry, no per-layer flat-field, no chroma or base pulls.
  It has never been built, because no session here can reach the elevation and imagery
  services, so whether it reads as de-lit is unknown rather than settled. Round 1 judges
  it on a rendered sheet; until then this line is open.
- ~~**The default spawn stands on a 20 degree cross-slope.**~~ Closed in round 1: both
  spawns moved onto ground that passes, and all three now declare `level_ground`, so the
  gate checks them from here on. The numbers that were reported and not checked were 20.8
  degrees across the heading with 2.96 m of roughness on `spawn_butte_base` and 6.03 with
  1.08 on `spawn_badlands_south`, against the gate's 8 degrees and 0.6 m.
- **The roads are the pack's stock block.** One `road_gravel` material, no `surfaces`, no
  carve and no bed-contrast contract, so `test_decal_roads_have_no_node_steps` and
  `test_road_surfaces_are_painted_and_decalled` both skip and `road_contrast` is empty.

| Round | Verdict | Findings and what changed |
| --- | --- | --- |
| 1 | NOT YET | First round, judged from sheets rendered in-session from the published ZIP at `a9662fc`. The agenda's first line is answered and the answer is not the one it expected: the de-lighting does run now, `imagery.delight` true with a gain of 0.919 to 1.259 and 0.26% of cast shadow, and the map still reads as bleached bone. It is flat, not clipped - luminance p5 to p95 spans 0.152 against Meteor Crater's 0.242 and Black Bear Pass's 0.301, mean saturation is 0.097 against 0.271, and the median at 0.752 is as bright as Meteor Crater's 95th percentile, while 0.084% is over 0.94 and nothing at all is near black. So the gates that assert clipped and near-black fractions pass it and always would: a map can be uniformly overexposed without either number moving, and the p5-p95 spread is the measure that separates these maps. The palette is not at fault, which only became visible once the critic sheet carried colour at all: fb_clay_fin's tile means (0.447, 0.468, 0.514) and fb_shale_slope's (0.523, 0.543, 0.576), blue over green over red, which is Mancos Shale, while the de-lit base under them means (0.715, 0.699, 0.644), red over green over blue - chroma-direction gaps of 0.141 and 0.108. The near field in the fixed sheet is the cool grey the materials are authored in and everything past the 120 m detail fade is the beige the base carries, which at 2 m eye height is most of the frame. The default spawn is fixed: `spawn_butte_base` stood at 20.8 degrees across its 14 by 7 m apron with 2.96 m of roughness against the gate's 8 and 0.6, and all three spawns now declare `level_ground` and measure inside it. Choosing where to put it needed more than the gate, and this is worth carrying to any incised map: these badlands are cut below the plain, so the nearest passing ground to a bad spawn is the plateau on top - the first pick passed at 0.69 degrees and showed an empty horizon to the skyline. Both new positions are scored on the 90th percentile elevation angle along the heading out to 700 m as well as on the apron, and checked by rendering the view. Not started, and the reason this cannot be better than NOT YET: there is no art pass. One thing the round did land on the colour: the per-material tint the palette comment describes was never on the material that matters. The built terrain classifies `fb_mud_flat` over 61.94% of the map, `fb_shale_slope` 26.41, `fb_clay_fin` 9.66 and `fb_caprock` 1.99, so the lighter 0.35 tint the comment reasoned for went to a third of the map while the dominant surface - and the warm half of the only colour split these badlands have - kept the shared 0.6. It is 0.35 now. Both tiles were rebuilt and rendered on the fixed sheet; the 0.6 rebuild matched the shipped tile to a max absolute difference of 0.0, so the 0.35 render is the real thing and not an approximation. What it buys: the wash against the slopes goes from a 14.14 a* b* gap to 17.32. What it costs is the near-to-far step, and that is the number this decision turned on rather than a preference - against the de-lit base the wash steps dE76 5.49 at 0.6 and 10.05 at 0.35, where `mc_ejecta_gravel` already ships 12.34 at this same weight and this map's own `fb_shale_slope` and `fb_clay_fin` already ship 22.82 and 30.20. The step at 0.35 is below every one of them, so the cost argument does not reach. On the wash_west driver view it stays a ramp with no edge at the 120 m detail fade: near chroma 0.086 to 0.107, far 0.028 to 0.031. Every driver view reports 0 objects in range, and the roads are still the pack's stock single-material block. |

## Level decisions

| Decision | Value | Why |
| --- | --- | --- |
| Footprint | 4096 m, centred 38.380 N 110.900 W | The butte in the north-east, the badlands filling the rest |
| Samples | 4096 @ 1 m | Native 3DEP spacing |
| Materials | mud flat, shale slope (6-20 deg), clay fin (20-38 deg), caprock (>38 deg) | Slope-painted |
| Spawns | butte base (default), badlands south, wash west | Play area first |
| Roads | 13 decal roads, 14.3 km | The state highway and OSM tracks |
| Sky | 15:50 local, late June | Afternoon sun rakes the rills |

## Build ledger

Generated by `build.py factory_butte ledger` from `authoring/ericrolph_factory_butte.handoff.json`; the handoff is authoritative.

| Measured | Value |
| --- | --- |
| Elevation range | 1353.0 - 1456.6 m (relief 104 m) |
| Terrain block | 4096 samples @ 1 m, maxHeight 106 m |
| 3DEP baseline coverage | 100.0% of the level before compositing |
| Holes filled / spikes clamped | 0 / 2 (spike threshold 8 m) |
| Slope mean / p95 / over 30 deg | 8.0 / 32.1 deg / 6.0% |
| Layer split | fb_mud_flat 62%, fb_shale_slope 26%, fb_clay_fin 10%, fb_caprock 2% |
| Roads | 13 decal roads, 14.3 km (primary 1, track 11, unclassified 1) |
| Spawns | spawn_butte_base at (-436, 0), 1406 m; spawn_badlands_south at (439, -1552), 1403 m; spawn_wash_west at (-1572, 554), 1427 m |
| Distribution | `factory_butte_ericrolph.zip`, 55 members, 93.9 MB, sha256 `8052412d540eca6d...`, build serial 5 |
