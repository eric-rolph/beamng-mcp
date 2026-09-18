# Black Bear Pass - design blueprint

Status: **built from public data, art pass applied, static gates green** (2026-09-15).
Not yet play-tested.

## The site

From the 3,913 m (12,840 ft) summit of Black Bear Pass the road descends west into
Ingram Basin as a one-way shelf road: loose shale, two rock obstacles the trail
review calls the Wrecked Sections, the off-camber bedrock ledges known as the Steps
at 3,390 m, and the switchbacks that zigzag down the scree fans above Bridal Veil
Falls.
The summit and Ingram Basin sit above tree line (alpine tundra, talus fields and rock
outcrops); the Telluride-side slopes in the west of the square carry Engelmann
spruce and subalpine fir up to a krummholz band under the ~3,620 m tree line, with
aspen groves on the lowest benches.

## The dataset

- **USGS 3DEP 1 m** from the CO SanLuisJuanMiguel 2020 lidar.
- **The same survey as a point cloud** (USGS 3DEP `CO_SanLuisJuanMiguel_4_2020` on the
  public Entwine index, about 4 returns per m2): its highest returns are the canopy,
  its ground returns the datum check. Gridded at 1 m in the fetch stage, deleted as
  it is read; only the grids are kept. The block's returns cover 94 % of the level;
  the missing corner is the summit plateau above the tree line, where nothing would
  be planted from them anyway.
- **USGS NAIP** at 1 m; **OpenStreetMap** for Black Bear Pass Road, the Bridal Veil
  road and the Imogene track.

## Why the physics pops

1 m samples over 1378 m of relief: the shelf road is a measured 3-4 m ledge with a
real wall on one side and a real void on the other, the Steps are the actual bedrock
ledges, and a missed line is 400 m of measured scree to the basin floor. The high
slope statistics (half the level over 30 degrees) are the point.

## Driving profile

High-centre-of-gravity articulation, crawling gear ratios and suspension droop on the
shelf road; the tundra benches above for recovery and the basin for the tumble test.

## The art pass

Reference: five photographs of the road. The cliffs are charcoal-grey rock in thin
horizontal beds split by vertical joints, dark-streaked, with spruce on the ledges;
the slopes are dark grey angular rubble; the road is a pale, dusty grey-tan ribbon
that reads lighter than the scree it crosses, with angular blocks on its uphill side;
the benches are grey rubble with sparse tan grass; the forest section is spruce-fir
with yellowing aspen and willow; the peaks beyond are iron-stained yellow, orange and
white scree. Everything below is generated from data toward those pictures.

- **Forest from the lidar.** The canopy height model (highest return minus the
  ground) has a local maximum wherever a tree top stands; every top over 2 m is a
  tree at that height, with a crown-radius exclusion so two tops never share a crown.
  Species follow elevation (fir gaining on spruce toward the tree line, stunted tops
  in the last 50 m below it as krummholz) and the de-lit imagery (bright green under
  a top below 3,250 m: aspen). Tops from 1.2 m are kept: below 2.5 m and above
  3,300 m they are the willow carrs and krummholz mats of the subalpine meadows, which
  share the mat shape. Nothing is planted from cover statistics any more; the forest
  edge, the stand density and every height are measured, and the lidar corrected the
  photograph: the slope at the Bridal Veil spawn that reads as closed forest in the
  September imagery is open meadow with low willow (80 % of its returns are ground),
  while the Telluride side carries the tall stands. Closed cover in the canopy model
  (over 35 % of the ground under crowns above 2 m within 15 m) paints the needle-litter
  floor; the rest of the green ground stays tundra and meadow. Three crossed
  alpha-tested cards plus top-view whorl tiers on a real trunk; trunk-only collision.
- **Talus boulders from the lidar.** 3DEP is bare earth, so its compact bumps (0.8 m+,
  2-60 m2) on the talus, scree and cliff layers are boulders; they come out of the
  ground and go back as procedural blocks sized to their footprint. Below the grid's
  reach, 0.3-1.2 m stones are scattered at 200 a hectare on the talus and the
  fell-field (blocks every few metres, as in the photographs), 40 on the scree and 8
  on the tundra benches above 3,500 m, biased to the concave toes where scree collects.
- **Shelf road carved.** The pass road, the Steps and the switchbacks get a bounded
  smoothed grade line (24 m window, 1.5 m cut/fill budget) and a flat 3.2-5 m bed with
  2 m feathered banks; the bed is painted gravel so the tyres feel gravel.
- **Imagery de-lit** with the sun held to the 2019-09-09 13:30 flight geometry
  (az 200, alt 55) so the dark north faces stop pulling the fit to the horizon; cast
  shadows under the cliffs are refilled from lit neighbours, a wall over 45 degrees
  only from lit walls (not from the scree on its ledges) and never lifted past the
  median of its lit cells, the cap feathered in from 40 degrees so it draws no
  contour through the scree; the flight's snowfields (2019 was a record snow year,
  and the September image still has them on the north faces) are found as white,
  colourless, smooth cells and refilled with the grain of the ring round them
  carried in from the nearest ring cell along jittered boundary vectors (under a
  canopy from the canopy, in the open from open ground, so a field across a forest
  edge comes back as forest on the one side and meadow on the other); every
  refilled field, shadow or snow, is brought to the mean colour of its own 10-30 m
  ring and to the ring's grain band by band (under 2 m and 2-8 m, measured over
  the field's interior, and a gentle field takes its tone from the nearest ring
  cell along the boundary vector, so the meadow's patches run on into it; the
  ratio ships in the handoff as refill_grain_ratio); the
  crowns' cast shadows on the ground between the trees (the horizon test on the
  canopy surface) are refilled like the terrain's, the gain is held under a
  crown, not under a cover fraction, and the crowns themselves are refilled from
  the open ground round the stand at six tenths of its luminance (the game draws
  the trees; the base under them is the ground between the trunks in the tone of
  the meadow or scree round the stand, not the flight's near-black crown tops),
  the closed-cover rule going before the slope rules so a retoned stand stays
  forest floor; a soft knee keeps the pale summit plateau off
  white; the tailings ponds, turquoise in the flight, are painted the lakes' teal. What the model leaves of the sun is taken out per
  layer by a flat-field binned on the fitted sun's incidence (twelve bins over the
  incidence each layer spans, the ground under 35 degrees and the faces over it
  equalised as their own populations, two passes each), gated at 10 % across bins
  (15 % on the steep cells). The plateau's photograph is chalk; its base colour is
  pulled 70 % of the way to the fell-field's grey-brown with its grain kept, so the
  road reads lighter than the ground it crosses there as it does everywhere else.
- **Textures.** Talus as a pile: convex blocks at three sizes dropped onto the tile
  with overlap allowed, shadow under every upper block's edge, gravel where none
  landed, map lichen on a third of the big ones, in the photographs' dark grey; the
  cliffs as the photographs' thin-bedded charcoal rock (fourteen beds to a 6 m tile,
  joints in every hard bed, water stains, lichen), and because terrain detail is
  projected top-down the east- and west-facing cliffs carry the same family turned a
  quarter so the beds stay horizontal on every wall; scree as chips at every heading;
  tundra as clustered tussock cushions, olive and darker than the grey-tan gravel
  between them as in the photographs (the tile is not shaded by its height); the
  road bed pale
  crushed stone a shade lighter than the scree as in every ground photograph (held a
  tenth over its margins; a 0.64 gravel read as snow under the game's sun); 1024 px detail
  sets whose mean albedo is the authored colour, tints blended 60 % toward the de-lit
  imagery under each layer (the measured means encoded to sRGB before the blend, since
  the palette base is sRGB by the tone contract).
- **On the ground.** The game puts its first height sample on the terrain block's
  corner while the GIS grid holds the ground at each cell's centre, so the block sits
  half a square in from the footprint corner and every object placed from the grid
  lands on the ground the game draws. Trees take the bilinear height under their
  jittered top (a metre of jitter on a 40 degree slope is a metre of height), trunks
  sunk a hand's width, mats and saplings 3 cm; upright rocks sit a tenth of their
  height into the highest ground under their footprint, tilted ones 0.15 at their
  centre. Bark tiles cover 0.5 m of trunk and wrap by girth, so spruce plates are
  3-5 cm as in the photographs, not 25 cm.
- **Spawns at the trail's named places.** Six spawns on the pass road, snapped to
  the carved bed with their authored sense of direction: the summit turnout at
  3,910 m, the descent into Ingram Basin, Wrecked Section 1, the Steps (the 20-25 %
  ledges at 3,390 m, where the trail review's GPS fix puts them), the first
  hairpin of the switchbacks on the scree fans below, and the foot of the climb at
  2,756 m under Bridal Veil Falls, facing back up the road with the whole 1,150 m
  of ascent ahead of it. The two ends of the climb are the two places a player
  starts from cold, and the shelf road is 3.2 m wide: each gets the pull-off it has
  in life, a 26 by 22 m apron carved as a plane under 3 % within 1.5 m of the
  ground, feathered 18 m and keeping the ground's own colour, carved before the
  roads so each way's profile is fitted through it. Every spawn ships the ground a
  vehicle line rests on, measured as a 14 by 7 m rectangle at its heading: the tilt
  along and across the heading, the relief and the departure from the plane it sits
  on. The gate is 12 degrees across the heading and 1.2 m of departure, because a
  bed that is smooth along its length can still put a wheel over the edge. The
  review's other fixes are
  carried as trail features in the ledger: Ingram Lake and Point 13510 are inside the
  square; Bridal Veil Falls and the power station lie about 200 m beyond its western
  edge, Trico and Telluride Peaks beyond its eastern one.

## Critic ledger

Each round the critic (a separate agent holding `critic_rubric.md`) reviews the
sheets in `authoring/critic/` and writes findings with generator fixes; the round is
closed when every finding is a spec or parameter change in the tree.

| Round | Verdict | Findings and what changed |
| --- | --- | --- |
| 1 | NOT YET | Textures read as worms, corduroy and brickwork (families rewritten: Worley facets, log-normal beds, shale chips); boulders missing (talus scatter, cliff filter moved into detection); spawns off the road (snapped, facing downhill); pale halos on cards (colour dilation); tree species all one silhouette (spruce, fir, krummholz, aspen cards). |
| 2 | NOT YET | Talus and cliff tiles too small and too regular (tiles 6 m and 10 m, per-cell gap widths, non-planar faces, gravel between); summit plateau painted tundra (elevation rule above 3,780 m, tundra added to rock layers, tussocks merged into turf); road as pale as the scree (darker bed and decal, crushed-stone bed at 2 m); road notches at the Steps and a 22 m drop on the falls stub (3 m carve budget over 32 m, way 125954590 excluded, segments over 60 % cut); square tier cards showing as skirts (top-view whorl atlas, smaller drooping tiers, krummholz as a 2.6 m dome); a third of the forest krummholz (band 50 m, taller bands, 5 m spacing); rocks floating on 38 degree scree (tilted to the ground normal, sunk with slope, 4x scatter at 320 tris); rocks too round (angular 0.7-1.0, more clip planes); cliffs still carrying baked sun (de-light gain 3.5); bark seams (quieter). |
| 3 | NOT YET | De-light gain pinned at its ceiling on north cliffs (gain 5.0, sun fit freed to 42-60 deg); shadow refill darker and smoother than lit ground (refill keeps the shadow's own texture at full amplitude, no built-in darkening); green turf painted talus and scree (greenness rules: slopes with excess green over 0.06 fall through to tundra, closed conifer cover below 3,560 m gets a needle-litter floor); steps and crossed beds where carved ways meet (ends within 6 m of a carved bed take its height over a 30 m ramp, unjoined ends feather out over 10 m, the duplicate Steps way excluded, cut fragments under 100 m dropped); rocks on the road bed (3 m clearance); a flat dark hem on the conifer cards (lowest whorls shortened, ragged fade); krummholz still a spire (rounded-top mat); cliff and talus tiles as crazy paving (20 % shattered plates, wider joints, weathered faces, 40 % gravel between blocks); grid fingerprint in the forest (replaced outright: the forest is now planted from the lidar canopy height model, every top at its measured height); aspen bark seam (tileable periods). |
| 4 | NOT YET | Sun fit pinned at the floor of its range, refill mask five times too wide and the canopy over-lifted (sun pinned to the flight's 55-58 deg, de-light held to 30 % under closed canopy, refill given the lit ground's saturation, floor and tundra flat-fielded); the summit plateau under the 6 m talus tile (its own fell-field material at a 2.5 m tile, scatter halved); rocks hovering on slopes through the footprint seating (tilted rocks seated at their centre a fifth in, upright ones raised to their true footprint); cliff tile still a convex net (a tight pile of tilted plates with shatter clusters and master partings); scree chips aligned and one size, floor a flat sheet, talus faces level (chips at every heading and log-normal sizes, litter with twigs, cones and needle clumps, size-linked block heights and stronger tilts); authored tones not reaching the screen (every set's mean albedo normalised to its base, the darker-road premise dropped); bark a marbled web (grey-brown plates with short fissures); willow mats as cubes (3.6 x 1.5 m ragged domes); saplings as scaled spires (bushy sapling shapes under 4 m); a 1 m lattice in the dense mats (metric KD-tree exclusion, sub-cell jitter); steps at cut-fragment ends (fragments under 300 m dropped, beds over 40 % rejected, fragments of one way never join each other). |
| 5 | NOT YET | Every object half a square off the ground it was placed from (the game puts its first height sample on the terrain block's corner, the GIS grid holds each cell's centre: the block now sits half a square in, and trees are seated by bilinear sampling under their jittered top, trunks a hand's width in, mats and saplings 3 cm; rocks a tenth of their height in upright, 0.15 tilted); the imagery tint pulling every material dark (the layer means are linear light and were blended into the sRGB palette base unencoded; encoded first now); bark plates at 2.5x life size (one bark tile per 0.5 m of trunk, wrapped by girth); a seam across the bedded cliff tile and a jump at the tuff tile's master partings (the beds start half a bed in so the wrap falls mid-bed; partings on integer windings of the tile); aspen tops under 4.5 m drawn as tall trees (sucker clumps: three leaning stems, a low four-card crown); tundra cushions as round buttons (log-normal, up to twice as long as wide, run together in clumps, blade streaks and straw-yellow dead crowns); talus blocks as flat-topped prisms (a ridge across every block, chamfered rims); road gravel one size (5-60 mm log-uniform stones proud of a packed bed of fines); the flat-field's compass bins mixing a steep and a gentle north face (bins on the fitted sun's incidence instead); the ledges of the side track at the Steps spawn accepted as the Steps. |
| 6 | NOT YET | Round 5's seating, tint encoding, cliff seam, sucker clumps and gravel sizes read as fixed. A September 2019 snowfield beside Wrecked Section 1 painted as white ground with black boulders (bright colourless cells are refilled from the ground around them, and a soft knee keeps the gain off white); the shaded cliffs refilled from the scree on their ledges and lifted to pale grey (a steep cell now borrows only from lit steep cells, nothing on a wall is lifted past its lit median, and the cliff and fell-field tiles take a quarter of the imagery tint instead of six tenths); the flat-field's eight compass-wide bins leaving a 28-40 % sun on the south faces (twelve bins over the incidence the layer spans, from 4 degrees, with the after-means gated at 10 %); the road bed painted cream on the plateau (its palette base was sRGB-encoded twice); the cliff tile as coursed masonry (forty log-normal beds to a 12 m tile, joints in six beds of ten, a shadow line under every hard bed); tundra as bubble-wrap over torn paper (cushions dropped only where the sward noise is closed, lying with their clump, over packed fines); talus faces one flat tone (pits, one crack in ten, blocks capped at 1.2 m); bark as a Voronoi net (a shingle pile with a shadow under each scale's lower edge; aspen scars as sharp lenses with lenticel dashes); lime aspens (medium green, no boost); soft ruts (walled ruts, log-uniform stones). |
| 7 | NOT YET | Round 6's cliff refill and cap, incidence flat-field on the cliffs, road bed paint, bedded tile, shingled bark, aspen tone and the Wrecked Section 1 snowfield read as fixed. Snow the raw image held under 0.8 on the shaded north faces lifted to white by the gain (the snow test runs on the de-lit image too); the summit plateau chalk-white with the road no lighter than the ground (its base colour pulled 70 % toward the grey-brown palette base, grain kept, and the knee lowered to 0.4); walls mid-grey because the lit median of a wall seen from above is its ledge scree (capped at 0.15 linear, and the cliff tiles drawn at 70 % over the base); a 13-15 % sun left on the steep north scree that the flat-field's 1-99 % span never binned (bins over the whole span with a 200-cell floor, and the steep cells' spread gated at 15 %); corduroy in the wheel tracks (an aperiodic washboard); rock and bark normal maps at 65 degrees mean tilt (a fifth of the strength); Dalmatian aspen bark (four ragged brown scars a tile with a pale rim, dashes of varied weight); tundra as soft ovals (0.2-0.4 m cushions, twice the relief, blade streaks, straw on a fifth); pick-up-stick twigs (5-30 cm); the fell-field bare at ground level with the scatter cap binding (200 blocks a hectare on fell-field and talus, 8 on the tundra benches above 3,500 m, cap 100,000). Junction grade kinks of 0.3-0.4 m and one bed on a gorge lip are noted for the road pass. |
| 8 | NOT YET | The de-lighting no longer paints the sun (luminance uncorrelated with incidence on every layer); the cliffs, the talus and fell-field piles, the crushed-stone bed, the placement and the switchbacks view read. Snow still white in the summit fields (the refill's own 2 m ring re-seeded it: the test runs on the result too, three rounds, thresholds 0.70 / 0.08 / 4 m, sources 10 m clear of any field); every refilled patch a flat off-tone blob (snow now carries the texture of the lit ground mirrored across its edge; black cores take a third of the neighbourhood; the whole plateau above 3,780 m, rock, outcrop and refill alike, pulled to the fell-field grey-brown by elevation band so no blob stands out of the ground); the road invisible from the summit spawn (the same pull; the bed gated at 15 % lighter than its margins on every layer); rock and bark surfaces as putty and sandpaper (weathering stains, water streaks, per-bed tones, lichen patches on a third in yellow-green and black, normals at a third of the strength); ruts as smooth troughs (a washboard at a third of the rut depth at three wandering pitches, stones on through the floor); a 69 m hole in the pass road where a short OSM link was dropped (a short piece whose both ends meet surviving ways is kept); junction steps and beds on gorge lips (the join takes the exact height of the nearest cell of the way it meets, free ends are cut back until the ground beyond them is within a metre, and fade over 25 m); tundra cushions as a Voronoi net (lobed outlines, 3-8 mm blade streaks carrying tone, late-summer olive no more saturated than the base); scree normals flat and twigs as slivers (scree relief x2.3, 5-30 cm pale twigs with a shadow edge). |
| 9 | NOT YET | The sun is out of the base colour on every layer; the cliff tile, the bed and its decal, the shelf-road frames, the placement and the profiles read; rock and bark surfaces, the washboard, the scree relief, the twigs, the olive tundra and the restored link are fixed. The snow refill ate 7 % of the level into posterised blobs (seeds at 0.86 that stand 0.10 above their 60 m neighbourhood, chroma under 0.05, growth 6 m, the refill capped at 2 %); the summit road at bed/margin 1.00 under a band-wide pull (the pull is now a 200 m windowed flat-field, and the bed is gated per 100 m window at 10 %); cast-shadow refills paler than the lit ground (refill texture capped at 1.15); a 48 m stub carved into a 7 m pit (a short link is kept only when its ends are within a metre of the ways it meets) and a 1.15 m kink at the restored link (a junction end is never cut back, whatever the carving order; the snap widened to 8 m); tundra blades as a two-axis weave on felt buttons (one direction per cushion, a firm rim); scatter stepping on the 3,780 m contour and the 30 degree line (densities ramped 40 m across class lines and 80 m below a floor); lidar boulders 1.6x taller than measured (the scale reconciles the lidar's height with the footprint). The Steps' ledges, planed by the carve, are noted for the road pass. |
| 10 | NOT YET | The sun is out on every layer, the plateau lands on its target, the bright refills are down to 0.02 %, the tiles, shapes, placement and the shelf-road frames read; the scatter ramps and the boulder scale are fixed. Two beds meeting with 0.6-1 m kerbs at their seams (junction heights are now solved jointly before any bed is carved: an end takes the other way's grade line where they meet, two ends meeting take their mean, both ramp over 30 m, and the seam step is gated at 0.15 m); a hump in a 14 m gap between two free ends (free ends within 20 m and 3 m of height are bridged as one road); a 301 m stub dangling 50 m short of the pass road (fragments under 400 m are dropped); the surviving refills flat and off-tone (the field's edges join it at a 0.06 contrast, and a field's texture is quilted from the ring in 8 m patches, not mirrored); tundra as green pillows (more bare ground, cushions capped at 0.3 m, straw over a fifth of them, tan tufts between); tundra bench scatter at four times its density (a ramped density is capped at three times the class's own); the black tarn (painted the teal of Ingram Lake). The bed and the forest-road findings measured the terrain-stage colour, not the shipped base: on the shipped base the bed is 0.587 with no cell under 0.35 and the summit bed 0.575, so those are noted, not acted on. |
| 11 | NOT YET | The road pass reads as fixed on the shipped surface (every junction end within 0.05 m of the way it meets, one bed network plus the trail system, the gap bridged and the stub gone), with the tarns, the plateau's tone, the sun out of every layer, the switchbacks frame, the species and the placement. The refilled snowfields as checkerboards of 8 m squares in a forest-meadow mean (a field now takes the ring's grain carried in from the nearest ring cell along jittered boundary vectors, blended over 2 m, under a canopy from canopy and in the open from open ground); cream scree refilled as snow (seeds at 0.92, chroma under 0.04, a 5x5 spread under 0.02); a luminance contour along the 40 degree line (the cap moved to the cliff classifier's 45 degrees, feathered in from 40); cast-shadow refills 10-20 % under their rings and cooler (every field brought to the mean colour and grain amplitude of its own 10-30 m ring); rock faces as camouflage (lichen in two or three colonies of log-normal blotches on a tenth of the talus faces and a sixteenth of the summit blocks, rock-tripe under 2 %, facets +-6 %, the beds as edged bands stepping 10-20 %); the tundra tile's tonal order inverted (cushions 0.38 on grey-tan gravel 0.44, the tile no longer shaded by its height); one rock shape on 77 % of the summit (a scattered stone takes every variant in turn); scatter at 4x its density on the tundra and 2x on the scree (each class renormalised to density x area after the ramps and the toe bias); the bed within 8 % of its margins on pale ground (the bed takes factor x margin as a floor per 100 m window); the tailings ponds turquoise (a chroma branch in the lake rule); Y-shaped bark fissures (straight vertical fissures, 2-6 cm). |
| 12 | NOT YET | The sun is out on every layer, the tarn and the ponds are teal, the placement is the lidar's, the pass road's profile is clean with every junction at 0.00 m, the tundra tile's order is right, the rock variants are used evenly, the scatter is at its densities and the bark fissures are vertical; the refills are tone-matched and the 40 degree line is a soft ramp. Every refilled field flat at a third of its ring's 2-8 m grain (each field's grain is now scaled band by band to its ring's, measured over the field's interior, and the after-match ratio ships as refill_grain_ratio, gated at 0.8); the summit's scattered stones orange-tan on grey-brown ground (the fell-field's scatter takes the grey talus rock, the summit rock kept for its lidar blocks and toned to grey-brown); the bed floor never firing on pale scree (the bed and its margin are measured over the same 2-8 m band the handoff reports, the lift re-measured over three passes, and the gate reads the contract's own factor); near-black gaps between the trees on the Telluride side (the gain damp is a crown's, not a cover fraction's, and the crowns' cast shadows on the ground between them are refilled); single-node steps at the free ends of the side tracks (a decal stops where the carved bed stops: unjoined ends trimmed by the carve's 25 m end feather, the largest grade change per node reported). The cap's feather widened to 8 degrees and a patch 0.25 above its ring seeds snow on any aspect (both from the critic's notes). |
| 13 | NOT YET | The sun is out with no seam across the cliff line or the plateau contour, the tarn and ponds are teal, the summit's stones are grey talus rock, the side tracks' ends sit on the bed, the refills carry their ring's grain, the placement is the lidar's, the tiles, shapes and the shelf-road frames read; the toned bed reads as gravel and the repainted forest floor is convincing. The road vanishing against pale scree because the margin averages the olive bank with the pale fan (the bed is now floored at the contract over the margin's pale side, its mean plus two thirds of its spread, per window, never past 0.60 sRGB; the ratio against the pale side ships as windows_vs_pale); cream scree painted tundra because 2G-R-B scores low blue as green (turf now needs G-R over 0.02 as well); the plateau's shaded old snow toned but not refilled (a relative seed: raw over 0.70, a fifth above its ring, colourless and smooth, any aspect; growth from 0.80, the cap 6 %); a lidar-flat pond painted as tundra (a patch flat to 2 cm over 400 m2 is water whatever its colour); two single-node dips on the steep side tracks (a per-sample grade-change limiter was tried at 0.08 and 0.03 and only moved the kinks to the edges of what it re-averaged: the dips are benches the 3 m cut/fill budget cannot plane, and the profile keeps them); the Steps spawn facing off the bed (the heading is the bearing to the bed 15 m down the road, not the chord through the point); the last white cells on scree (growth from 0.80). The tundra cushions' hard rims are noted for the texture pass. |
| 14 | NOT YET | The sun stays out (the black north-east cliff band of the flight comes back as the lit walls' grey-brown), the snow work reads as fixed (the twenty-five largest 2019 fields at 0.93-1.09 of their rings, the plateau's old snow within 0.02), the flatness rule painted only water (a near-black lake, a green tarn, Ingram Lake), the Steps spawn faces its bed, the tundra layer is at 30 %, the shelf-road frames, tiles, shapes and placement read, the pass road's grade changes stay under 0.03. The 3,780 m contour as a tone seam (the region's elevation feather, 20 m hard-coded, is now 150 m, and the scree layer takes a base pull of 0.7 like the talus); the road still lost against pale scree (the same scree pull gives the bed floor room under the snow ceiling); refills carrying one ring-mean tone with none of the meadow's 10-50 m structure (a gentle field's tone is carried in from the nearest ring cell's 10 m mean, and the grain match gains an 8-32 m band); tilted boulders hanging off their downhill lips (the 0.4 m gap cap set, and the cliff layers take no lidar bumps); Ingram Lake as painted teal ground under the tundra tile (water cells take their own flat lake tile and each body gets a WaterBlock at its surface); mint rings round the tailings ponds (cyan excess 0.08 from 0.30, grown 4 m); the two side-track dips (a 5 m cut/fill budget for those two ways alone, which changed nothing: the map-wide budget never binds there, the deepest cut on the map being 1.8 m, so the kinks are the profile's own and stay); the tundra cushions' hard rims (a softer dome profile); grey flats below the plateau painted tundra (grey ground at any slope is gravel). |
| 15 | NOT YET | The switchbacks and Wrecked Section frames, the tiles, the shapes, the forest edge and the pass road's profile read; the 3,780 m contour, the seating (p95 0.13 m), the lakes as water, the grey flats, the cushions' rims and the Steps spawn read as fixed. The default spawn shows no road, the bed 1.12x its stippled fell-field and the pale-side windows under the contract (the contract is now 1.15 over the margin's pale side, the margin judged by that side too and giving at most 8 %, the ceiling 0.62, the plateau's target darker, and the pale-side windows gated); the cast-shadow refills under the west cliffs as flat posterised polygons (the tone carried from the nearest ring cell made a mosaic of facets: every refill now takes the lit ground's colour at a scale that grows with its distance from the edge, the steep and gentle populations joined over 4 m, and a shadow keeps its own 40 m structure and its own chroma differences, its grain under 2 m carried in from the ring because its own is the flight's noise floor; the terrain's shadows are matched to their rings on their own, apart from the forest's gap shadows that merged with them into one blob whose busy gap cells stood in for the whole field's grain; a refilled cell is left out of the flat-field's bins and takes no factor, having been lifted once already); the biggest snowfields at half their ring's grain and blue-grey, and the refill statistic no measurement of the shipped base (the 1.15 clip on the carried grain lifted, the mean match bounded to a correction, the interior measured 6 m in, a refilled cell bluer than its lit ground takes that ground's chroma, and every large field of terrain shadow or snow is now measured on the shipped base against its own ring of open ground 10 m clear of any crown or gap shadow, and gated); the north-east square a pale lilac mottle (the talus and scree pulls per 200 m window as a luminance gain and a chroma shift, their gate wide enough to take the pale fans, and the flat-field brings each incidence bin's chroma to the lit bins'); mint rings and near-dry ponds at the tailings (the shallow edge half as turquoise within 12 m joins the pond, a settled pond is cut half a metre under its 90th-percentile ground and the water surface sits a hand over the 95th; a lidar-flat patch is water only in a hollow and never on refilled snow); the tundra a lawn (pulled half-way to the olive base); the willow card a dark conifer mat (its own flat-topped grey-green dome, blended less toward the aspen's measured cover); the side-track dips remain by decision, the third way's 0.064 noted. |
| 16 | NOT YET | The switchbacks frames are the level at its best, the sun is out with no seam on the contour or the cliff line, the tarns and ponds are teal with no mint ring, the north-east lilac is gone by the numbers, the tiles, rocks, bark, the willow carr, the shapes and the placement read, the road profile's 1 m noise is fine; the willow, the tailings rings, the lakes, the seating and the north-east chroma read as fixed. The default spawn still shows no road and Ingram Basin the same, the plateau's darker target never landing (the region pull's 150 m elevation feather made it a no-op over most of the plateau, mean 0.436 to 0.433: the feather is 80 m and the fell-field takes the windowed layer pull the talus and scree have; the decal's edge crisp at 0.10); the Wrecked Section snowfield a khaki-and-mint camouflage of crown duff and meadow blobs (a snowfield is one surface: its grain is the open ground's and a crown standing in it is not damped); snow patches beside the roads 15-40 % too pale, the refill's sources seeing the flight's white road (the road corridor 6 m either side of every centreline is no source, and the check's rings leave the painted bed and its corridor out); tan halos tracing every shadow's edge (a penumbra cell the gain lifts over 2.5x within 4 m of a field is refilled with it); black holes in the west forest where crowns were refilled from shaded ground (a crown sits at no less than four tenths of the lit ground round it); the summit's outcrop shadows unrefilled, their bumps lowered out of the DEM (a cell under six tenths of its lit 60 m ground and bluer than it is refilled as cast shadow); the tundra still a lawn in patches (pulled seven tenths of the way to the olive base). Left for the next round: the largest shadow refills' interior grain and tone against the 0.8 and 0.92-1.08 the critic asks (the shipped-base check gates grain 0.45, luminance 0.85-1.25 and a blue-minus-red difference of 0.07 today, what the carry achieves: this build reads 0.60, 0.76-1.08 and 0.064 over the 24 largest fields), a gap shadow on a rock layer taking the forest's ring, the grade creases at two junctions and the free ends' residuals. |
| 17 | NOT YET | The switchbacks driver frame is the photograph, the bed reads 1.18-1.32x its ground at every one of the five spawns (round 16's missing road at the default spawn and in Ingram Basin both fixed), the profile is a clean grade line, the flat-field leaves 0-3 % spread per layer against 12-64 % before, there is not one black hole left, the summit's outcrop shadows are gone, and the shapes, placement and seating read. The refills came back mauve and green, matched on luminance and blue-to-red but not on the green axis (every field's mean is now clamped to its ring on both chroma axes and within a sixteenth in luminance, as a hard step after the band match, and the check reports the green axis and gates it at 0.05); a straight bright bar in the flight refilled as a mint snowfield (a component that fills three quarters of its own principal-axis box while being three times as long as it is wide is a cut or a tailings run, not snow, and the road corridor seeds no snow); the cliffs the palest rock on the level at 0.44 against the photographs' charcoal (both cliff layers take the windowed pull the talus and scree have); the pale lozenges beside the roads (the corridor barred as a source widened from 6 m to 12 m, so a switchback stack no longer sees the next bed up, and the mean clamp closes the rest); the pale-side windows approaching the contract rather than clearing it (the bed's reference is nine tenths of the margin's spread, not two thirds); the forest floor terracotta at red-over-blue 0.185 (base to 0.085, the duff of a spruce-fir stand); summit blocks banded like turned timber and one variant in eight never placed (the sides take their v from the block's own height so bedding lies in level planes, the family is grey-brown rather than tan, and a block picks among the three nearest aspects rather than the single nearest). Checked and not reproduced: the claim that the shipped refill check passes a field an independent ring calls 12 % pale (its ring already excludes every refilled cell; that field reads 0.963, and its green cast is the real fault, now fixed). Left open: the largest refills' interior grain against the 0.8 asked (the shipped check reads 0.60 at the tenth percentile), a gap shadow on a rock layer taking the forest's ring, the grade creases at two junctions, and the two side-track dips. |

## Play-test findings

| # | Finding | What changed |
| --- | --- | --- |
| 1 | Meteor Crater drew its orthoimagery tiled two by two in game, because a TerrainMaterial's `*TexSize` is divided into the terrain's sample count rather than its world width. This map is 4096 m sampled at 1 m, where the two readings give the same number, so it was never wrong - and could never have caught the bug. | The pack now authors every terrain texture size in metres and divides by `square_size_m`. Nothing here changes: base stays 4096, detail 2, macro 60. |
| 2 | `TerrainBlock.baseTexSize` was a hard-coded 2048 while this level's base maps are 4096 px, so the far-field bake - the whole basin from the pass - halved the orthophoto's resolution. | The block takes the site's own `base_tex_px`, and a gate holds it equal to the texture set's `baseTexSize`. |

## Level decisions

| Decision | Value | Why |
| --- | --- | --- |
| Footprint | 8192 m, centred 37.9220 N 107.7765 W | The whole box canyon: the pass summit 1,240 m inside the south edge, Bridal Veil Falls and Pandora in the middle, Telluride end to end, Tomboy and Savage Basin, Marshall Basin and Mendota Peak inside the north edge |
| Samples | 8192 @ 1 m | Four times the ground at the same metre. The shelf road is 3.2 m wide and does not survive a coarser grid, so the sample was the one thing not for trading |
| Base colour | 8192 px de-lit NAIP, 1 m/texel | The photograph at its own resolution over four times the ground; the base set goes from 67 MB to about 270 MB |
| Buildings | OSM outlines, lidar heights, fitted roofs | Telluride, Pandora and the Tomboy and Savage Basin workings are inside the level now. A town painted on bare ground reads worse than no town, so they are modelled |
| Materials | tundra, talus blocks (15-30 deg), scree slope (30-45 deg), cliff rock (>45 deg), gravel road bed | Slope-painted plus the carved beds |
| Forest and rocks | spruce, fir, krummholz, aspen at the lidar's tree tops and heights; talus boulders from lidar bumps | Forest items with trunk / full collision |
| Spawns | pass summit (default), Ingram Basin descent, Wrecked Section 1, the Steps, Bridal Veil switchbacks | The trail review's named places, every one on the pass road |
| Roads | 22 decal roads, 20.8 km, beds carved and painted gravel | OSM tracks incl. the pass road |
| Sky | 09:07 local, mid August | The descent faces west; morning keeps it lit from behind |

## Build ledger

Generated by `build.py black_bear_pass ledger` from `authoring/ericrolph_black_bear_pass.handoff.json`; the handoff is authoritative.

| Measured | Value |
| --- | --- |
| Elevation range | 2657.3 - 4132.7 m (relief 1475 m) |
| Terrain block | 4096 samples @ 2 m, maxHeight 1492 m |
| 3DEP baseline coverage | 100.0% of the level before compositing |
| Holes filled / spikes clamped | 0 / 73 (spike threshold 10 m) |
| Slope mean / p95 / over 30 deg | 29.7 / 53.4 deg / 53.3% |
| Layer split | bb_forest_floor 28%, bb_scree_slope 23%, bb_talus 15%, bb_fellfield 13%, bb_tundra 12%, bb_cliff_rock_ew 5%, bb_cliff_rock 4%, bb_road_gravel 0%, bb_lake 0% |
| Roads | 50 decal roads, 52.5 km (residential 9, service 5, tertiary 2, track 32, unclassified 2) |
| Spawns | spawn_pass_summit at (2853, -2593), 3910 m; spawn_ingram_basin at (2590, -351), 3662 m; spawn_wrecked_section_1 at (1618, -70), 3450 m; spawn_the_steps at (1387, -4), 3390 m; spawn_bridal_veil_base at (28, 761), 2757 m; spawn_switchbacks at (1247, -84), 3340 m |
| Imagery de-lighting | sun az 191 / alt 55 deg (fit r=0.33), Minnaert k 1.07, cast shadow 2.3%, gain p05-p95 0.89-1.73 |
| Surface objects removed | 15681 bumps (linear 85, rock 15596, shrub 0), 0 structures, 484300 m3 lowered |
| Canopy height model | lidar returns on 94.1% of cells, ground datum offset -0.45 m, canopy over 2 m on 29.1%, heights p95 25.1 m, max 60.0 m |
| Road beds carved | 55 ways, 53.4 km, cut/fill up to 2.6/1.8 m, 45038 bed cells |
| Placed objects | 232811 forest items: 105009 rocks, 0 shrubs, 130000 trees (aspen 12528, fir 35931, spruce 81541); 50.2 M triangles if all drawn; trees at the lidar's tops, heights p50 19.6 / p95 28.7 m |
| Trail features | Black Bear Pass summit at (2862, -2617), 3910 m, 9 m from the road; Ingram Lake at (2673, -1216), 3653 m, 26 m from the road; Ingram Basin at (2347, -486), 3580 m, 96 m from the road; Wrecked Section 1 at (1618, -70), 3450 m, 0 m from the road; Wrecked Section 2 at (1525, -34), 3427 m, 0 m from the road; The Steps at (1386, -5), 3388 m, 2 m from the road; Point 13510 at (3172, -335), 3929 m, 416 m from the road; Trico Peak at (3305, -1964), 4058 m, 320 m from the road; Telluride Peak at (3587, 204), 4112 m, 366 m from the road; Bridal Veil Falls at (-983, -286), 3457 m, 1431 m from the road; outside the footprint: Red Mountain Pass trailhead |
| Distribution | `black_bear_pass_ericrolph.zip`, 203 members, 429.5 MB, sha256 `edee09d241058364...`, build serial 24 |
