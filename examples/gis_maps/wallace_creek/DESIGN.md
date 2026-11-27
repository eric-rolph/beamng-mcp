# Carrizo Plain - Wallace Creek - design blueprint

Status: **built from public data, static gates green** (2026-09-15). Not yet play-tested.

## The site

The San Andreas Fault crosses the Carrizo Plain as a single, sharp trace along the foot
of the Temblor Range. At Wallace Creek the stream channel is offset 130 m right-lateral
where it crosses the fault; along the Elkhorn Scarp the trace is a line of pressure
ridges, sag ponds, shutter ridges and beheaded gullies. The plain itself is dry
grassland and alluvial fans with ranch tracks and no pavement.

## The dataset

- **B4 Project lidar, 0.5 m bare-earth tiles** (2005, USGS/NSF/NCALM, OpenTopography
  `OTSDEM.032018.32611.1`, https://doi.org/10.5066/F7TQ5ZQ6). The survey is a swath
  along the fault; it covers 39 % of this level, and the pack composites it over the
  baseline with a feathered edge.
- **USGS 3DEP 1 m** (CA CaliforniaGaps 2023 lidar) as the baseline for the rest.
- The B4 tiles are ellipsoidal heights and 3DEP is orthometric: the pack measured a
  +34.5 m median offset in the overlap and levelled the B4 grid onto 3DEP before
  compositing, which is the local geoid separation to within a few centimetres.
- **USGS NAIP** at 1 m; **OpenStreetMap** for the ranch tracks.

## Why the physics pops

Everything a pre-runner wants from "natural desert" is here as measured geometry
rather than procedural noise: the scarp is a real 2-8 m step, the pressure ridges are
real compression humps, and the offset channel is a 130 m dog-leg with 3 m banks.
At 1 m per sample the gully cross-sections keep their true width, so suspension
rebound over them is a test of the car, not of the heightmap filter.

## Driving profile

Trophy-truck and pre-runner territory: long high-speed runs along the fault, gully
crossings at speed, and the scarp as a natural jump line. The sag ponds are dry.

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
- ~~**The default spawn stands on a 20 degree cross-slope.**~~ Closed in round 1: the
  default moved 29 m onto the terrace above the offset channel, and all three spawns now
  declare `level_ground`. The numbers that were reported and not checked were 19.54
  degrees across the heading with 2.1 m of roughness on `spawn_wallace_creek_offset`,
  against the gate's 8 degrees and 0.6 m.
- **The roads are the pack's stock block.** One `road_gravel` material, no `surfaces`, no
  carve and no bed-contrast contract, so `test_decal_roads_have_no_node_steps` and
  `test_road_surfaces_are_painted_and_decalled` both skip and `road_contrast` is empty.

The footprint is its own open question, recorded in `spec.py` as `WANTED: 16384 at 1 m` /
`BLOCKED`: this 4096 m square holds the offset channel and not the place, and the 16.4 km
square that holds Soda Lake, the Goodwin Education Center, Elkhorn Road and the Temblor
crest waits on the de-lighting's memory ceiling.

| Round | Verdict | Findings and what changed |
| --- | --- | --- |
| 1 | NOT YET | First round, judged from sheets rendered in-session from the published ZIP at `a9662fc`. As on Factory Butte, the de-lighting runs now - `imagery.delight` true, gain 0.864 to 1.097, 0.17% cast shadow - and the base it produces is the flattest of the four maps: luminance p5 to p95 spans 0.131 against Meteor Crater's 0.242 and Black Bear Pass's 0.301, with a gain range a third of Black Bear Pass's 0.892 to 1.711. Nothing clips and nothing is near black, so every colour gate passes a map with almost no tonal range in it. New, and the finding this round is really for: the terrain itself is corrugated. A single wave dominates the high-pass in four of five 800 m boxes across the map, 50 to 100 m long, consistently oriented between 29 and 45 degrees, about 0.2 m in amplitude, and 423 to 1370 times the median high-pass power against Meteor Crater's 64 to 153 - it draws as diagonal corduroy on every smooth slope in the driver view, which on a grass plain is most of the map. Whether that is flight-line striping in the B4 source or something the composite introduces cannot be settled from a session, because the source tiles need the hosts the network policy denies; the comparison belongs on a runner and it is the first thing round 2 should resolve, since a destripe belongs in the terrain stage and not in the art pass. The default spawn is fixed: `spawn_wallace_creek_offset` stood at 19.54 degrees across its apron with 2.1 m of roughness, and is now 29 m away on the terrace above the offset channel, still looking down it at 135 degrees, with all three spawns declaring `level_ground` and measuring inside the gate. Not started, and why this cannot be better than NOT YET: no art pass at all, 0 objects in every driver view, stock single-material roads, and the footprint question above still open. |

## Level decisions

| Decision | Value | Why |
| --- | --- | --- |
| Footprint | 4096 m, centred 35.262 N 119.815 W | Wallace Creek in the north-west corner, the Elkhorn Scarp ridges to the south-east |
| Samples | 4096 @ 1 m | Native 3DEP spacing; B4 area-averaged 2:1 |
| Materials | grassland, alluvial wash (6-22 deg), fault scarp (>22 deg), dry pond (<0.6 deg) | Slope-painted |
| Spawns | Wallace Creek offset (default), Elkhorn Scarp, plain west | The famous jog first |
| Roads | 11 decal roads, 13.3 km | OSM tracks and unclassified ranch roads |
| Sky | 08:40 local, May | Low eastern sun throws the scarp into relief |

## Build ledger

Generated by `build.py wallace_creek ledger` from `authoring/ericrolph_wallace_creek.handoff.json`; the handoff is authoritative.

| Measured | Value |
| --- | --- |
| Elevation range | 593.3 - 1005.1 m (relief 412 m) |
| Terrain block | 4096 samples @ 1 m, maxHeight 417 m |
| 3DEP baseline coverage | 100.0% of the level before compositing |
| Lidar overlay `ca05usgsb4_be` | covers 39.0%, levelled by +34.51 m onto 3DEP |
| Holes filled / spikes clamped | 0 / 0 (spike threshold 8 m) |
| Slope mean / p95 / over 30 deg | 7.5 / 27.7 deg / 3.8% |
| Layer split | wc_grassland 67%, wc_alluvial_wash 24%, wc_fault_scarp 9%, wc_dry_pond 0% |
| Roads | 11 decal roads, 13.3 km (track 8, unclassified 3) |
| Spawns | spawn_wallace_creek_offset at (-1106, 1109), 694 m; spawn_elkhorn_scarp at (888, -802), 711 m; spawn_plain_west at (-1355, 372), 659 m |
| Distribution | `wallace_creek_ericrolph.zip`, 55 members, 91.2 MB, sha256 `06eff6fb828fc1e8...`, build serial 5 |
