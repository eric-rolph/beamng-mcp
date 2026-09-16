# Barringer Meteor Crater - design blueprint

Status: **built from public data, art pass applied, static gates green** (2026-09-15).
Not yet play-tested on a game install; the first live run is the next step.

## The site

A 1.2 km wide, 170 m deep impact crater in the Colorado Plateau desert east of
Flagstaff, Arizona. The rim stands 45 m above the surrounding plain on upturned
Kaibab limestone and Coconino sandstone; inside, talus aprons run from the rim cliffs
down to a flat, dry lakebed floor. Outside, low ejecta swells ripple the desert for a
kilometre in every direction. Nothing is built inside the bowl; the only structures in
the level are the visitor-center car park and the rim access road on the north side.

## The dataset

- **NCALM airborne lidar, 0.25 m grid** (Palucis 2010, OpenTopography
  `OTSDEM.112011.26912.3`, https://doi.org/10.5069/G9V40S4C). A 24001 x 24001 ArcInfo
  binary grid in UTM 12N (NAD83); the pack downloads the 2.3 GB grid directory once,
  windows it to the footprint, and deletes it. OpenTopography publishes only the
  **highest-hit** surface and the intensity for this survey, so every juniper, boulder,
  fence line and the visitor centre are bumps in it; the terrain stage takes them out
  (see the art pass) rather than driving over them.
- **USGS 3DEP 1 m** as the baseline everywhere the lidar grid could have gaps (it had
  none here: the lidar covers 100 % of the level, and sits 0.03 m below 3DEP).
- **USGS NAIP** orthoimagery at 0.5 m for the base colour and previews.
- **OpenStreetMap** for the access road, the car park loop and the rim trail.

## Why the physics pops

The level is the one place in the pack where 0.5 m samples are justified: a 4096-sample
terrain over a 2048 m square. At that spacing the rim's bedding ledges, the boulder
fields on the talus, and the shallow ejecta swells all survive into the heightmap
instead of being averaged into a smooth bowl. The 16-bit height ladder is spent on a
200 m `maxHeight`, so one stored unit is 3 mm.

## Driving profile

- High-speed perimeter runs across the desert flats around the rim.
- Talus hill climbs from the crater floor to the rim at 30-40 degrees.
- Rim drops: the north rim cliff is 30-50 m of near-vertical limestone above the talus.

## The art pass

Reference: three photographs. An oblique aerial in late light (warm tan plain, cream
Kaibab ledges on the sunlit inner rim, rust-brown hummocky ejecta near the rim, dark
juniper dots across the plain, a dark paved access road and pale two-tracks); a
golden-hour aerial (the near ejecta almost maroon in shadow, the far plain gold, the
sunlit wall a cream ledge line over fluted talus); and two views along the rim from
the visitor centre (big red-brown Moenkopi blocks and rubble on the crest with
grey-green bushes and yellow grass tufts, the inner wall as stacked cream Kaibab
ledges striped with red-brown interbeds, tan talus with sparse bushes below).
Everything below is generated from data toward those pictures.

- **Imagery de-lit.** NAIP quad `m_3511164_se_12_030_20230627` was flown mid-afternoon;
  the sun it baked into the east-facing inner wall is fitted against the DEM (best
  hillshade correlation, held to 35-80 deg altitude), modelled as slope shading plus a
  cast-shadow horizon test plus sky occlusion, and divided out with a Minnaert exponent
  fitted from the image itself. Cast shadows borrow the lit neighbourhood's colour and
  keep only their own relative texture. The base colour ships at 4096 px (0.5 m/texel).
- **Bumps become objects.** A 6 m grey opening lifts every compact bump 0.45 m or
  taller out of the highest-hit surface; the imagery under each bump decides rock
  (pale) or shrub (green or dark); long thin ones of any size (the power line coming
  in from the north, the fence lines east of the rim, walls) come out of the ground and
  nothing goes back. There is no global structure rule: a 40 m one took the rim
  crest itself for a row of roofs, so the only flattened compounds are the two
  authored boxes (the visitor centre, the north compound of sheds and masts), which
  take the 3DEP bare-earth ground in place of the highest-hit lidar (no building in
  it, the rim exact at 1 m), feathered 20 m at the edge; the base colour inside them
  is repainted from the ring of plain around each (the grain of each patch cut from
  the ring arc nearest to it), the crest and walls keeping their photograph, and
  their furniture (cars, sheds, planted trees) never comes back as rocks; the
  visitor-centre box reaches over the rim crest, whose blocks and bushes stay (only
  what stood on the repainted layers goes). The drill site at the crater centre
  takes the bare earth too, but its photograph stays. The visitor-centre lot takes
  its own outline from the flight's dark cells (closed over 12 m), is carved as a
  plane under 3 % within 1.5 m of the ground, feathered 12 m in height, and wears a
  1.5 m gravel shoulder outside its kerb; the RV loop is a gravel pad. A bump over 3 m tall on more
  than 20 m2 or over 60 m2, or within 10 m of ground over 35 degrees (the cliff
  band; the talus below it keeps its boulders), is the crater and stays, unless it
  is a berm: tall, under 12 m wide and three times as long on gentle ground away
  from any cliff leaves the ground and nothing comes back, and the four segments
  of the dashed berm across the east ejecta too squat for that rule stand in four
  authored 60 m boxes whose opening takes them out; a bump over 3 m on under
  20 m2 is a pole and leaves the ground; a bump wider than 2.5 m on the floor, 4 m
  on the ejecta or 8 m on the crest is a hummock and is not placed as a rock, and a
  crest block over 4 m is cream Kaibab, not Moenkopi (the red-brown blocks of the
  photographs are car-sized). Rows of small bumps on a straight line (fence posts) are
  dropped before placement. A bush the lidar measured at 1.5 m or more is a juniper
  on any layer; sage is capped at 2.2 m.
  Rocks come back as procedural boulders (icosphere + 3-D fbm, Kaibab limestone or
  grey talus by layer) sized to their own footprint and height; shrubs as juniper
  cards. Junipers the lidar did not keep are found as dark compact dots in the imagery.
- **Roads carved.** OSM centrelines get a bounded, smoothed grade line and a flat bed
  across their width with feathered banks; the bed is painted with an asphalt
  (Meteor Crater Road, the visitor-centre loop) or dirt two-track terrain material so
  the ground model matches the decal the player sees; the asphalt decal carries a
  0.4 m tan shoulder and 18 % wheel-track wear, its bed none; the dirt two-tracks
  are held 6 % paler than their margins per 100 m window (the margin giving at
  most a tenth, the bed taking the rest), with the ruts the palest part.
- **The rim crest is its own layer.** Everything above 1,718 m that is not cliff (the
  crest and the upper outer flank; the plain sits at 1,679-1,712 m and never reaches
  that height, the crest at 1,722-1,750 m does) is painted as red-brown Moenkopi rubble, its boulders are a red-brown rock
  material, and its bushes are grey-green sage rather than the plain's junipers.
- **Textures.** Limestone rim as bedded ledges at a 3 m tile: hard beds standing
  proud with chipped lips and a few leaning joints, soft beds recessed, rubbly and
  warmer, half of them the red-brown siltstone interbeds of the rim photographs,
  four to six soft-edged desert varnish streaks a tile running down from under a
  lip and fading out. Ejecta as angular cream-grey Kaibab chunks at two sizes,
  domed, half-buried in rust-brown soil (the reference photo's hummocks); the
  chunks keep their tone whatever the imagery pull (a third of it on this layer).
  A block's top is a bedding plane: faces within 30 degrees of level take a planar
  map inside one bed, so the beds never close into rings on a domed top.
  Talus as tilted angular blocks with deep gaps. Desert floor as fine grit with sparse
  pebbles and darker crust patches. All detail tints blend 60 % toward the measured
  colour of the de-lit imagery under their layer so detail and base agree; 1024 px
  detail sets. Junipers are dense blue-green cards with only the sunlit tips going
  yellow, as in the photograph.
- **Boulder proportions.** A bump's footprint is trimmed to what its height can carry
  (1 m plus 2.5 times the height, 8 m at most): a 12 m bump half a metre high is a
  mound in the lidar, not a rock, and is not placed as one.
- **On the ground.** The game puts its first height sample on the terrain block's
  corner while the GIS grid holds the ground at each cell's centre, so the block sits
  half a square in from the footprint corner and every rock, bush and road placed from
  the grid lands on the ground the game draws; upright rocks sit a tenth of their
  height into the highest ground under their footprint, tilted ones 0.15 at their
  centre. The measured layer means are encoded to sRGB before they are blended into
  the palette base (which is sRGB by the tone contract), so the tint no longer pulls
  every material dark.

## Critic ledger

Each round the critic (a separate agent holding `critic_rubric.md`, briefed with the
three reference photographs) reviews the sheets in `authoring/critic/` and writes
findings with generator fixes; the round is closed when every finding is a spec or
parameter change in the tree.

| Round | Verdict | Findings and what changed |
| --- | --- | --- |
| 1 | NOT YET | The flight's sun still on the west wall (per-aspect flat-field of each rock layer after de-lighting); the imagery shrub finder planted the wall's shadow instead of the plain's junipers (contrast against a 20 m median, finder kept to the plain and ejecta below 12 degrees); the default spawn faced away from the crater and its horizon was the compound's trees and the visitor centre still in the DEM (snap keeps the authored heading sense; 8 m opening lifts the big junipers; a 120 m opening in an authored 360 m box takes the compound out; structures over 1 m, or 20 m2 when over 3 m tall); berm rings round flattened structures (the whole footprint down to 0.3 m proud goes, feathered 4 m); talus and rim rubble a tessellation (z-buffered pile of overlapping convex blocks with shadow under every upper edge); bedding striped on east- and west-facing walls (the same family turned a quarter as its own layer, chosen by aspect); boulders as eggs (tabular 0.35-0.65 aspect on the bedded rocks, flat base on all); a quarter of the rocks buried (seated on the highest ground under their footprint); residual bumps under the road beds (corridors opened before carving, ends feathered, junctions joined); the rim crest lost its red (authored tint kept, detail strength 0.55); ejecta cobbles rounded, two-track ruts dark, asphalt edge blurred (cell edges cut the chunks, pale ruts, 4 % edge). |
| 2 | NOT YET | Round 1's flat-field, talus pile, seated rocks, road beds, berms, ruts, ejecta chunks and crest red read as fixed. The rim crest sanded off all the way round by the 40 m structure rule (a ridge crest narrower than 40 m is a roof to it: the global rule is off, the only compound is the authored box; bumps over 3 m tall or 60 m2, or within 10 m of ground over 35 degrees (the cliff band; the talus keeps its boulders), stay as the crater); the default spawn facing away from the crater (the snap now takes the road's tangent through the point and keeps the authored sense); the visitor centre's roofs, stripes and cars still painted on the ground (the base colour inside the box is repainted from the 30 m ring of plain around it, and nothing that stood in the box comes back as a rock); house-sized boulders on the plain (a bump wider than 2.5 m on the floor or 4 m on the ejecta is a hummock, not placed); orange Moenkopi with paint-splat lichen (maroon-brown rock and rubble, lichen a hundredth of the surface in small grey-green spots, talus lichen gated to one block in five); the ejecta's second size as discs (cut blocks at that size too); five-metre sage (a bush over 1.5 m is a juniper on any layer, sage capped at 2.2 m). |
| 3 | NOT YET | Round 2's crest, spawn heading, plain rock caps, bush species and Moenkopi tone read as fixed. The compound in-paint wrote a 240 m black square (the wider filter never reached the box centre: the ring's mean colour now fills whatever the filters miss, and the crest and walls inside a box keep their photograph); the visitor centre still standing (the opening's 'wholly inside the box' test let the compound ride the rim's own lowered ground to the edge: both boxes now take the 3DEP bare-earth ground, which has no buildings, feathered 20 m); fence and power lines as rows of terrain needles (a bump over 3 m on under 20 m2 is a pole and leaves the ground; a second box for the north compound); the south rim spawn on the cliff band (moved to the flat pad on the outer flank); ejecta's large cobbles as discs (both sizes cut blocks); rim rubble a monotone brick red (its own family: a quarter of the blocks cream Kaibab, tan-grey dust between, the rock less saturated with dust and pale specks); the ledges no paler than the plain (the rock layers equalised to their lit bins, the tiles keeping their authored cream, gated at 6 % over the plain); residual sun on the walls (factor clamp 2.5 and a compass pass after the incidence bins); ruled-stripe ledges (12 cm bites along a third of the lips, rubble on a third of the soft beds); a slab asphalt decal (an 8 % soft edge with a pale gravel shoulder and a wear band). The build ledger is regenerated with every level build from now on. |
| 4 | NOT YET | The plain, the floor view, the placement, the shapes, the beds and the decals read; the compound, the poles, the south spawn, the cut cobbles and the cream ledges are fixed. The flight's sun over-corrected into its opposite, the west wall clipped white (the passes multiplied past the clamp: the whole correction is now clamped at 2.0, bins equalised by median, a knee above 0.8 so nothing reaches white, gated at 0.2 % clipped); the visitor centre's roofs still painted on the terrace edges (the keep mask is the 10 m-smoothed bare-earth slope over 28 degrees, not the layer); the in-paint a mosaic of box plateaus (a normalised Gaussian pyramid over the ring, carrying the ring's own texture mirrored across the edge); junipers baked into the terrain and painted as limestone (a tall wide bump on gentle ground leaves the ground and the imagery names it; the cliff buffer spares nothing on ground under 15 degrees; juniper cards to 6 m); four sheds on a fence line as needles (the north box widened to 300 m, a 60 m box on the sheds); rim rubble still all red (the cream pieces and tan dust are absolute colours now, the base is the mix); Moenkopi boulders in paint-splat lichen (a hundredth of cover on desert rock, grey-green); ruled ledges (notches cut the lip right out with a shadow); ribbed banks (the bed height field smoothed two cells, feather 4 m); ejecta a third pale chunks (a sixth, rust-brown soil, shadow under every edge). |
| 5 | NOT YET | The overview is the aerial's palette, the sun is out of the luminance, the floor drone view is the golden-hour photograph, the compound, the junipers, the sheds, the rubble, the rocks, the beds and the placement read as fixed. The in-paint mirrored the ring into diagonal stripes and the two big boxes overlapped (the boxes are one mask with one ring; the low pass is the pyramid, the grain is the ring's high-pass quilted in as random 16 m patches at quarter turns, feathered over the ring's width); the west wall clipped white after the layer pull (the pull is an additive shift, and the shipped base is gated at 0.2 % clipped per layer); the flight's shadow left sky-blue on the west wall (the wall shadow core widened to 0.75 visibility and 10 m, and a steep cell bluer than its lit ground takes that ground's chroma); a 10 m drill shaft and spoil mound at the crater centre (pits narrower than 8 m and deeper than 2 m filled, a box on the site); ejecta a third pale chunks in dark outlines (a sixth, shadow on the down-light side only, a third of the chunks dusted, a gradient across each face); notches as zipper teeth (open wedges at the lip, grain on the hard beds, the varnish stronger); the car park painted as plain with black aisles (an authored asphalt pad where the aerial has the lot); the asphalt decal without a visible shoulder (a 0.4 m tan shoulder inside the opaque part, wheel-track wear bands); one fence remnant left as a row (posts up to 9 m apart). |
| 6 | NOT YET | The overview is the aerial's palette with the sun out of both limestone layers, the crater-floor drone frame is the golden-hour photograph, the talus, rim-rubble and ledge tiles are nameable, the road profile is smooth (seam 0.021 m) and the in-paint has no stripes; the west-wall clipping, the sky-blue walls at large, the drill shaft, the ejecta cover, the notches and the fence rows read as fixed. The visitor-centre box swallowing 2.1 ha of rim crest behind the spawn (the box keeps the objects on the crest layers, dropping only what stood on the repainted ground); a dashed 400 m berm across the east ejecta standing as ledge-textured walls (a tall, narrow, long bump on gentle ground leaves the ground); the car-park pad covering half the lot (the whole lot and the RV lot); the terrain asphalt tile repeating the decal's shoulder every 2 m (a bed family without one); the decal's shoulder 0.24 m of grey and 6 % wear (0.4 m of tan, 18 %); the two-tracks 18 % darker than the plain with dark ruts (bed 6 % paler than its margins per window, the ruts the palest part, the tile barely shaded by its height); house-sized Moenkopi blocks on the crest (over 4 m they are Kaibab, capped at 8 m); 18 blue-grey holes at the foot of the north-west wall (a cell darker than half its 40 m mean and bluer than green is refilled as cast shadow); a grain-amplitude seam at the box edges and a visible square at the drill site (patches cut from the nearest ring arc; the drill site keeps its photograph); peach, flat ejecta chunks (absolute cream-grey, domed, a third of the pull); varnish as pencil hairlines (four to six soft streaks from under a lip); strata rings on domed rock tops (a planar map inside one bed on the tops). Every refill's own mean is now taken over the field's interior: the dilated rim of lit cells had every field 10-20 % darker at its edges. |
| 7 | NOT YET | The overview is the aerial's palette with the sun out of both limestone layers, the in-paint leaves no square, the crater-floor drone frame is the golden-hour photograph, the tiles are nameable, the shapes lumpy and flat-based, the placement traces the aprons and crest, the profile is smooth (seam 0.021 m, grade change 0.087). The blue-grey holes at the foot of the north-west wall still there (the shadow rule now measures against the lit ground of a 60 m window, blue relative to that ground's blue-to-red, two passes, ratio 0.65); the east berm still standing (the cliff test now runs on a 24 m-opened surface so a berm's own flanks no longer protect it, and seven 100 m boxes with a 100 m opening cover every segment); the car park a black draped rectangle with a 2 m colour step (each pad takes the lot's own outline from the flight, is carved as a plane under 3 % within 1.5 m of the ground, feathered 12 m in height and in colour, at the photograph's 0.34); strata rings on three domed tops (the planar map now covers faces within 60 degrees of level); the dirt decal without ruts (ruts a quarter paler than a darker crown, the tile barely shaded by height); the asphalt decal's paving-cell cracks and ruler shoulder (0.3-0.5 m cells with three edges in ten drawn, the shoulder's edge wandering with the gravel grain, wear 30 %); dark corridors along the two-tracks (the margin gives at most 2 %, tapering to nothing at 20 m, the bed takes the contrast); the crest's cream base under a maroon tile (base_pull 0.5 toward the rubble mix); hard beds at albedo 0.99 and varnish as thumbprints (hard beds 0.82-0.94 with the contrast in the soft beds, the lip notches at half weight, varnish as four to six red-brown stains 0.15-0.25 m wide fading down the face); cream-white flat ejecta chunks (grey-tan, per-face tone, twice the dome); the crest's bushes dropped in the visitor-centre box (bushes stay on every layer, a bump under seven tenths of the ground round it is a bush, the imagery finder runs on the crest); rocks floating on their downhill side (every block seats a quarter of its height into its footprint's mean ground and tilts onto the footprint's plane when the drop across it exceeds three tenths of its height; the gap ships as rock_gap_m); embossed discs in the north compound's in-paint (patches busier than 1.5x the ring's median are not laid, the box mean equalised to the ring). |
| 8 | NOT YET | The overview is the late-light aerial's palette with the sun out, the two-tracks pale hairlines, the crater-floor drone frame the golden-hour photograph, the tiles nameable with capped beds, the boulders lumpy and flat-based with planar tops, the profile smooth, the densities the data story; the NW-wall holes, the dark corridors, the crest base, the strata rings, the varnish, the bushes in the box and the seating (p95 0.11 m) read as fixed. The RV pad a black rectangle where the flight shows a gravel loop (a pad whose outline the flight does not hold is skipped, and the loop is a gravel pad); the lot's outline toothed by pale bays (max_lum 0.50, closed over 12 m); the claimed 12 m colour feather absent and unwanted (a 1.5 m gravel shoulder outside the kerb instead, the cached colour saved after the pads); a grain seam at the box edges (the ring keeps its own high-pass under the feather); road fragments quilted into the boxes (ring cells within 8 m of a centreline are not sources, and a patch whose high-pass leaves 0.88-1.12 is not laid); the dirt decal a blur (ruts a fifth paler than a darker crown over a 5 cm transition, pebble speckle, an 8 % edge); the asphalt shoulder as rick-rack and invisible cracks (1/f wander with jitter, cracks 6 % darker and finer); brown smears on the crest with nothing on them (the imagery finder to 28 degrees, and every dot nothing stands on repainted from its ring); the last berm segment (an eighth box); lilac-grey near-rim ejecta (a chroma pull to the far plain's blue-to-red); paper-cut ejecta chunks (speckle and a dark down-light edge); nine floating rocks (seated down to a 0.4 m gap or not placed). |

## Level decisions

| Decision | Value | Why |
| --- | --- | --- |
| Footprint | 2048 m, centred 35.0275 N 111.0225 W | The bowl plus a full kilometre of ejecta on every side |
| Samples | 4096 @ 0.5 m | The 0.25 m survey, area-averaged 2:1 |
| Materials | desert floor, ejecta cobbles, limestone ledges (>28 deg), talus blocks (14-28 deg), rim rubble (>1718 m), asphalt and dirt road beds | Slope- and elevation-painted plus the carved beds; the de-lit NAIP base carries the real colour |
| Objects | limestone, talus and Moenkopi boulders, junipers and sage from the lidar bumps and the imagery, as Forest items | The plain's shrub dots, the rim's red blocks and the ejecta's blocks are the reference photos' texture |
| Spawns | north rim visitor center (default), crater floor, south rim | Rim drop from the top, climb from the bottom |
| Roads | 26 decal roads, 9.7 km, beds carved and painted | Every `highway` way OSM has here; paved vs dirt by type |
| Sky | 15:20 local, late June | Low western sun rakes the rim strata |

## Build ledger

Generated by `build.py meteor_crater ledger` from `authoring/ericrolph_meteor_crater.handoff.json`; the handoff is authoritative.

| Measured | Value |
| --- | --- |
| Elevation range | 1561.7 - 1750.7 m (relief 189 m) |
| Terrain block | 4096 samples @ 0.5 m, maxHeight 192 m |
| 3DEP baseline coverage | 100.0% of the level before compositing |
| Lidar overlay `az10_palucis_hh` | covers 100.0%, levelled by -0.03 m onto 3DEP |
| Holes filled / spikes clamped | 0 / 68 (spike threshold 4 m) |
| Slope mean / p95 / over 30 deg | 10.6 / 36.8 deg / 10.3% |
| Layer split | mc_desert_floor 47%, mc_ejecta_gravel 23%, mc_rim_rubble 8%, mc_talus 8%, mc_limestone_rim_ew 6%, mc_limestone_rim 6%, mc_road_dirt 1%, mc_road_asphalt 1% |
| Roads | 26 decal roads, 9.6 km (service 10, tertiary 1, track 15) |
| Spawns | spawn_north_rim_visitor_center at (74, 646), 1710 m; spawn_crater_floor at (1, 1), 1564 m; spawn_south_rim at (-48, -638), 1728 m |
| Imagery de-lighting | sun az 257 / alt 54 deg (fit r=0.66), Minnaert k 1.40, cast shadow 0.2%, gain p05-p95 0.89-1.48 |
| Surface objects removed | 4815 bumps (linear 50, rock 3497, shrub 1178), 0 structures, 52048 m3 lowered |
| Road beds carved | 26 ways, 9.7 km, cut/fill up to 1.2/1.3 m, 154742 bed cells |
| Placed objects | 7311 forest items: 3036 rocks, 4281 shrubs, 0 trees (); 1.2 M triangles if all drawn |
| Distribution | `meteor_crater_ericrolph.zip`, 127 members, 176.4 MB, sha256 `378bcbfce4bc499a...`, build serial 9 |
