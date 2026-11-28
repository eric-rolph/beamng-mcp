# Giant's Hearth — design amendments

The level's design is frozen (`level_design_v4.lock.json`: nine files, hashed). A frozen file
is never edited. When a built fact contradicts the design table, the amendment is recorded
here with its reason and its proof, and the gate that reads the table reads the amended
value at the ORIGINAL tolerance. A widened tolerance is not an amendment.

## A1 — 2026-09-15 — layer coverage after the brink repaint (B1 r16 → r17)

**What changed.** The world's edge is painted `scree` (18 m) then `rock` (6 m) wherever the
ground stands more than 8 m above the backdrop's gutter floor (`level/brink.py`). Critic pass
15 (B15-2) found that through r15 the paint did not mark the drop at all: 1,495–1,510 of the
1,536 backdrop columns read `forest_floor` at every inset from 2 m to 80 m. The repaint moves
**118,014 nodes** (2.81367 pp of the 2048² block) and **no heights**.

| layer | design §2.4/§2.7 (frozen) | amended | proof |
|---|---|---|---|
| forest_floor | 68.95590 % (gate 69.0 ± 0.1) | **66.14223 %** (gate 66.14 ± 0.1) | `b1/critic_r16/move_the_repaint_mine.json` `coverage_percent` |
| scree | 2.15650 % (not gated) | **4.02875 %** (gate 4.03 ± 0.02) | same |
| rock | 9.34701 % (gate 9.35 ± 0.02) | **10.28843 %** (gate 10.29 ± 0.02) | same |
| the other eight | unchanged to 0.00000 pp | unchanged | same |

**Why an amendment and not a revert.** The orchestrator's r17 ruling keeps the safety fix and
the frozen byte identity: the repaint moved out of the vendored `terrain_model.py`
(restored to sha256[:16] `36f275eeb9c292c0`) into B1's own `brink.py`, applied by
`terrain_io.grid()`. The shipped `.ter` is byte-identical either way
(`8e354091c24e30c6fafdb9e9b7a2c57e84e2cc75714ede3322e81db37569fad6`), so the coverage change
is inherent to the fix, not to where the code lives.

**What is NOT claimed.** Critic pass 16 (B16-2) showed r16's "the drop is now visible"
frame evidence was an exposure artefact (the byte-identical control wall darkened more than
the repainted ground). The repaint is real; driver visibility is unproven and stays in the
backlog with its band-on/band-off harness.

## A2 — 2026-09-15 — the kindling logs, the enamel pot, the lantern tripod and the lantern come off the map

**What changed.** At the user's request ("remove the cauldron, smoking logs and cooking
tripod"), `place_props.py` no longer places `log_north`, `log_south`, `enamel_pot`,
`lantern_tripod`, or the `giant_lantern` that hung from the tripod. Their shapes, textures,
compiled meshes and imposter atlases still ship (members, manifests and harvests are
untouched); nothing in the scene references them. The hearth round's objects that only
existed for those props are filtered out of the frozen layout at render time
(`hearth_spec.REMOVED_WITH_THE_PROPS`): the fire + smoke emitter pair at each of the four
log ends (8 of 34 nodes), the four kindling fire lights and the lantern's point and spot
lights (6 of 36 lights). The level description no longer names them.

| census | design (frozen) | amended |
|---|---|---|
| props group statics of the giant kind | bench_log 1, log_north 1, log_south 1, leaner_log 1, lantern_tripod 1, giant_lantern 1, enamel_pot 1 | bench_log 1, leaner_log 1, the other five 0 |
| hearth `ParticleEmitterNode`s | 34 | **26** |
| night lights | 36 | **30** |
| lights with a flare | 8 (four kindling, two lantern, two spout keys) | **2** (the spout keys) |

**Why an amendment.** `layout.json` is one of the nine frozen design files and is never
edited; the removal is a render-time filter with the reason beside it, and every gate that
counted the design's 34 / 36 now counts the amended 26 / 30 at the same strictness.

**A2, second message (2026-09-16).** The user, reviewing the installed build: "remove this
log and this other log too and the lamp posts" — the leaner log (it lay across the trail),
the half-log bench deck (B4's drivable deck), and the four lantern posts. `place_props.py`
places none of them; the four `track_lantern_<i>` lights B2 hung on the posts are filtered
too. Props group statics 70 → **64**; night lights 30 → **26**. The description no longer
names the deck. The deck's shape, its containment wall and every gate that measures the
shipped bytes stay; only the placement is gone.

## A4 — 2026-09-16 — the backdrop skyline is a real canyon rim, not a generated one

**What changed.** The three ridge rings' crest heights come from
`authoring/ericrolph_hot_potato_arena_backdrop_gis.json`: the ground elevation of the Island
in the Sky rim above the Shafer benches, Canyonlands, Utah, sampled from USGS 3DEP 1 m lidar
(`USGS_1M_12_x60y426_UT_WestEast_B22.tif`, public domain, EPSG:26912) on three circles at
this level's own ring radii, 1,536 bearings each, in metres above the bowl floor. The
synthetic generator (ranges, massifs, spurs, crest noise, notches) is untouched and still
runs; `blender_backdrop.GIS_ENABLED` selects the source.

**The mapping is measured, not tuned** (`round_records/b7/`): vertical scale is applied to
the whole profile, the offset pins the COMBINED median crest onto the median that ships
today so the basin keeps its enclosure, and each ring is ROTATED — because a canyon that
cuts one sample circle cuts the other two at the same bearing, and turning the rings puts
wall behind canyon, which is what the synthetic rings did with independent seeds. The triple
is chosen against four requirements measured on the result: the world stays shut on all
1,536 bearings; no crest height is a clamp; no 45° window of the visible crest is flat
(`RELIEF_MIN_SPAN_M`); and the 306° outlet is a real canyon mouth with a farther wall behind
it, so the sunset frame looks through the rim.

**Two gates amended, both calibrated on the generator that no longer drives the shape:**

| gate | was | now | why |
|---|---|---|---|
| `peaks > 24` | more measured maxima than authored summits | `peaks >= 12` in GIS mode | "authored summits" is a property of the generator; a real mesa rim has fewer, broader prominences. Replaced by the provenance gate plus the relief-coverage invariant. |
| `abs(autocorrelation(lag)) < 0.30` | both signs | `< 0.30` and `> -0.60` | the failure it was written for is REPETITION (r1 scored +0.926 at lag 30). A real rim is ANTI-correlated at its own massif width (−0.3035 at 45°) because it stands high on one side and is cut by canyons 45° away. The floor keeps the teeth: one hill and one hole scores about −1.0 and still fails. |

**Added:** `test_the_backdrop_crest_is_the_lidar_profile_it_claims_to_be` reads the shipped
module against the shipped file point for point, checks the provenance the file carries, and
re-measures the closure and no-clamp invariants the mapping was chosen for.

## A5 — 2026-09-16 — the cliff outcrops' "bacon slices": measured, four fixes tried, NONE shipped

**What the user saw.** Driving delivery 4: *"some of these rocks look strange and hollow,
like there slices of bacon stacked on top of each other or cut up severely."* The shapes are
`cliff_outcrop_a`, `cliff_outcrop_b` and `crag` — 495 forest instances, 15–41 m, all built by
`rock_solid.solid_from_face_scan` (`solid="face"`): a photogrammetry cliff FACE with a body
built behind it.

**Measured on the shipped bytes** (`round_records/slab_probe.py`), against every
voxel-remeshed rock in the same tree:

| | sliver area (aspect > 8) | 99th pct normal jump | height banding |
|---|---|---|---|
| `cliff_outcrop_a` / `_b` / `crag` | **47.4 % / 30.8 % / 21.2 %** | 157–170° | 0.61–0.85 |
| every voxel rock, incl. `h_rock_face_01` | 0.1–1.3 % | 67–111° | 0.11–0.26 |

Half the surface is long thin blades and neighbouring faces fold back through 170°, which is
what reads as stacked plates with dark slots. **They are not holed:** `mesh_audit` reports
every LOD closed, one shell, χ=2, zero boundary edges. "Hollow" is shading.

**Four fixes were tried. Every one traded the defect for a worse one this level's own gates
catch, so the shipped geometry stands and the cliffs in delivery 5 are byte-identical to
delivery 4.**

| attempt | what it fixed | what it broke |
|---|---|---|
| `solid="voxel"` (the route the hearth uses for the SAME CC0 scan) | blades gone: 0.4–0.6 % sliver area | a bare face scan has no body: husk gate solidity **0.219 / 0.268 / 0.504** against its 0.54 floor; the remesher could not close the scan's own arches (**genus 4 and 9**) |
| body first, then remesh (`face_voxel`) | `_b` and `crag` clean outright | `cliff_outcrop_a` still genus 3; husk marginal (solidity 0.662 < 0.67 **and** fill 0.274 < 0.28); the closing sweep inflated the rocks by up to 2.1 m chasing handles, which put **456 forest instances inside a solid body** |
| the same, with a finer voxel (520 cells) | — | genus got **worse** (6 and 17): a fine voxel RESOLVES a scan's arches instead of filling them |
| finer skirt rows (`SKIRT_ROW_SHARE` 0.05 → 0.018) | — | sliver area moved only 47.4 → 43.1 %, so the rows are not the main source; the shifted shape still swallowed **141 instances** |

**What the attempts established, and why the next round can finish it.** The blades are an
aspect ratio: a skirt quad is one boundary edge (about 0.15 m, set by `rock_solid.GRID` = 180)
by one row deep (1.05 m at the shipped `SKIRT_ROW_SHARE`), and the decimator lengthens them.
But the rows are only part of it — the decimator makes blades out of the whole body — so the
real fix changes the body's tessellation AND re-plants the forest against the new shapes,
because any change to these three moves instances inside them. That is a revision of its own
with its own re-bake and re-plant, and it is in `round_records/BACKLOG.md`.

## A6 — 2026-09-16 — a road up the canyon wall, as a native MeshRoad

**What the user asked.** With the canyon rim of A4 on the skyline: *"let's make it drivable,
extend the road up into the side wall mountains (if possible)."* Then, while it was being
built: *"Let's make sure we're using BeamNG.drive native tools (if it makes sense) ... Decal &
Mesh Road Editors: lay down drivable asphalt, dirt paths ... with customizable widths, bank
angles, and edge falloffs."*

**What changed.** Two scene objects the frozen design does not have, in a new
`level_objects/shelf_road` group and the existing `decal_road` group (`level/shelf_road.py`),
and a strip of forest taken out from under them:

| change | what it is |
|---|---|
| `ericrolph_hot_potato_arena_shelf_road` — **MeshRoad** | 2,340 m along the near ring's face, 229 m of rise at 10 % to a pass on the rim at bearing 251.0 (z 376.9); 119 nodes; a drivable lane never under 8 m at any station as the spline lays it, widening at the pass; 3 m deep; banked 3 % toward the rock; deck ground type `ERHP_TRAIL` |
| `ericrolph_hot_potato_arena_shelf_approach` — DecalRoad | 469 m on terrain from the trail's last waypoint (150 deg, r 1,060), past the road's foot and round a 17 m turnaround loop, arriving at the road's first node 0.9 deg off its heading; steepest 25 m 16.3 % (the last pitch down onto the foot) |
| forest | **515 of 154,686 instances removed** from the corridor (`shelf_road.apply_forest_clearance`); every other instance byte-identical; per-species counts, file sha256s and the keep-out proof updated with the removal recorded beside them |

No texture, mesh or `.cdae` ships with them. The deck wears the trail terrain layer's macro and
detail maps; the slab's sides wear the ring's rock.

**Why native.** A road over a 200 m drop is what `MeshRoad` is for: nodes with their own
width, depth and normal, and collision the engine builds. It opens in the World Editor's Mesh
Road Editor like a hand-laid road. The first draft of this amendment built the bench as a
Blender DAE with a hand-made Colmesh (`round_records/b7b/retired_blender_draft/`); it passed its
own gates and was retired for the native object before it was cut into a release. The approach
is a DecalRoad because it lies on terrain.

**Why a traverse and not switchbacks.** Six of the seven alignment probes designed switchbacks
and none can be built: the face is 83-88 degrees, a bench cut into it does not daylight until
`cut x tan(face)` higher (73 m at 83 degrees, over 200 m near 88), and two legs stacked 96 m apart
still overhang by 12 m. A traverse crosses each column once.

**Why a filter and not a re-plant.** The planter is a sequential seeded Poisson disc; a new
keep-out would have moved trees across the whole map and re-opened every placement gate B3
closed. The clearance removes only corridor instances and is idempotent.

**Censuses amended, at the original exactness.**

| census | design (frozen) | shipped |
|---|---|---|
| forest instances (`plant["instances_total"]`, the per-species sum, the file line count, the keep-out proof) | 154,686 | **154,171** |
| DecalRoads | as before | **+1** (the approach) |
| MeshRoads | 0 | **1** |

The design-table gates (`fs.TOTAL_INSTANCES`, the zone density table) still assert 154,686:
that is what the design plants.

## A3 — 2026-09-15 — QB-28's archive budget: 1.0 GB → 1.1 GB, because the textures ship cooked

**What changed.** The level zip ships the engine's own cooked DDS in place of every PNG the
cook harvest proves (`build_level_zip --cooked-dir`, harvest `b6/cook_harvest_r1.py`), the
layout the giant-props releases already use. Materials keep naming the `.png`; the game
resolves the cooked sibling; the first-load texture cook, which drew the "NO TEXTURE"
placeholder on every foliage and rock surface for the first minutes of every new build, is
gone for those maps.

| | raw-PNG cut (delivery 2) | cooked cut |
|---|---|---|
| PNG members | 422 | 180 (115 terrain layer maps, 50 decal-road maps, 10 shapes, water, 4 UI/depth) |
| cooked DDS shipped in place of a PNG | 0 | **242** (DX10; 173 at 1024/11 mips, 40 at 2048/12, 26 at 512/10) |
| bytes of those maps | 346.3 MB PNG | 382.1 MB DDS |
| archive | 999,266,488 B | ≈ 1,035 MB |

**Why an amendment.** The budget was a size choice, not a tolerance on a measurement; the
cooked layout costs +35.8 MB for a first load without placeholders. The gate keeps a hard
ceiling, now 1.1 GB.

**Recorded trade.** The harvest was taken at the sentinel's `GraphicTextureQuality`
"Normal", which the user's own profile carries too: 2048-texel sources cooked at 1024. A
player at a higher setting gets that resolution for the shipped maps (the raw-PNG path would
have cooked them at full size). The 180 PNG members that stay raw are ones the engine did
not cook into `temp/levels/<id>/` in a full camera tour (terrain layers, decal roads, UI).

## A7 — 2026-09-17 — the cliff outcrops' slabs, fixed; and the shrubs get stems

**What the user said, twice.** 2026-09-16, driving delivery 4: *"some of these rocks look
strange and hollow, like there slices of bacon stacked on top of each other."* 2026-09-17,
with a screenshot circling the outcrop field above the shore: *"notice how they're not water
tight and they have very strange slices through them that shouldn't be there."* And, of the
vegetation: *"some of the trees that were very spherical were missing trunks and were half
spheres."*

### The rocks

A5 measured the defect on the shipped bytes and rejected four fixes. It named the cause as the
decimator and left the shipped geometry standing. The cause is narrower than that, and it is
visible the moment the shape is rendered untextured (`round_records/d7/shots/NEAR_now_a__*.png`):
the scan's FACE is fine, and the BODY invented behind it is a stack of ruled ledges with plates
jutting out of it. The skirt is cut into rows and **a row is a ledge**.

**The fix is the pair A5 never combined.** Cut the ledges out (`rock_solid.SKIRT_ROW_SHARE`
0.05 -> 0.008, and `cliff_outcrop_a` 0.025 on its own row) and then put the finished body
through the voxel remesher (`solid="face_voxel"`). Neither half works alone, and the reason is
the same for both failures: **the handles the remesh-only attempt could not close WERE the
rows.** Ledges a metre apart, a voxel of 0.13 m on a 21 m rock, and the remesher unions two
neighbours into a tunnel; then its closing ladder chases them and inflates the rock by 2.1 m.
Take the ledges out first and there is almost nothing left to bridge.

Measured on the SHIPPED bytes (`round_records/slab_probe.py`), worst detail of each shape:

| | sliver area (aspect > 8) | 99th pct normal jump | genus | husk solidity / fill |
|---|---|---|---|---|
| `cliff_outcrop_a` | **0.474 -> 0.018** | 170 -> 158 | 1 (declared) | 0.675 / 0.317 |
| `cliff_outcrop_b` | **0.308 -> 0.019** | 164 -> 116 | 0 | 0.777 / 0.246 |
| `crag` | **0.212 -> 0.006** | 162 -> 123 | 0 | 0.903 / 0.295 |
| every voxel rock in the tree (control) | 0.000-0.013 | 82-111 | 0 | — |

The three cliffs now sit in the band occupied by the rocks nobody complained about.
`cliff_outcrop_a` keeps ONE handle, the scan's own arch — `rock_face_01` reads genus 4 at
source, and the handle survives the remesher's entire closing ladder, so the opening is wider
than 2 x 16 voxels, about 4 m. It is declared on the row as `solid_genus`, the gate's own
mechanism, used here for the first time since r10 withdrew `mossy_rock_c`'s.

**What was measured and NOT shipped.** Re-sourcing the three onto closed 360-degree scans
through `solid="voxel"` — the route B2 used to cure this same defect on the hearth in its r7 —
was surveyed first and measures beautifully: `rock_07`, `rock_09` and `stone_01` all come out
closed, solid and in the clean band (`round_records/d7/survey/`). **The clay renders refused
it**: every candidate is a squat rounded BOULDER, and at 21-41 m that is a giant pebble, not a
cliff outcrop. B2 could re-source because a hearth stone IS a boulder. The scan's face is what
makes these read as cliffs, so the face stayed and only the body behind it changed.

**Corrected on the record.** The claim in `forest_spec.py` that `h_rock_face_01` proved the
voxel route on "the SAME CC0 scan" is false, and it had been pasted into all three cliff rows:
`hearth_spec.STONE_SOURCES` re-sources that slot to `rock_07`. Same slot name, different scan —
which is exactly why the hearth could take a route these three cannot.

### The shrubs

`shrub_01`'s shipped DAE carried exactly ONE material, `f_shrub_leaf_01`, and no stem geometry
at all: every shrub in the level was a cloud of leaf cards with nothing holding it up, and the
cards ran to the ground, so there was nowhere for a stem to be seen even if one existed. r13
fixed the "half circles" half of the user's report (a third detail keeps the mesh out to ~100 m
instead of flipping to a billboard at 30 m) and could not fix the "no trunk" half, because the
trunk was never modelled.

- **Three woody stems** per shrub, splayed onto the crown's three lobe bearings, on a new bark
  slot (`f_knotted_bark`, the snags' bark — already shipped, already cooked, so no new texture
  and no new material). Budgeted as a SHARE of each detail's triangles (8 %), not a fixed
  count, because `foliage_ladder` judges the LOD steps on foliage alone against a 1.5 ceiling
  and the shrubs ship at 700/468/320 — steps of 1.496 and 1.463, with no room. A share leaves
  them at 1.495 and 1.476; a fixed 40-triangle stem would have taken them to 1.542 and refused.
- **The crown starts at 0.30 h** instead of 0.08 h, which is what makes the stems visible.
- **The three lobes are three BODIES**, each its own squashed ball offset from the axis and
  lifted to its own height. r13's lobes were real in the numbers and invisible on the plant,
  because every card still sat on one bounding ellipsoid — so the silhouette stayed an
  ellipsoid, and the user reported the same spherical shrub twice.
- **`shrub_04` joins the other three.** It was the last on the r12 "bush" arrangement, whose
  cards face the plant's centre so the imposter bakes back-facing normals; it was held back to
  keep its DAE byte-reproducible, and this revision re-exports all four anyway.

The bark material is filed in the DEADWOOD family's `*.materials.json` (materials are filed
beside their textures, not beside the species that use them) while the shrubs are undergrowth.
That cross-family reference was **verified, not assumed**: the four shrub imposter atlases the
engine baked in the D7 boot carry **zero** fallback-orange texels
(`round_records/d7/check_bark_resolved.json`).

### Census and cost

| | delivery 6 | delivery 7 |
|---|---|---|
| members | 810 | 810 (identical names) |
| members whose bytes moved | — | 80: 52 `forest4`, 7 DAE, 7 `.cdae`, 14 imposter atlases |
| archive | 1,035,226,777 B | 1,035,229,165 B |
| forest instances | 154,171 | **154,121** |
| road-corridor clearance | 515 | **565** |

The planter re-ran against the new cliff shapes and re-seated **16,156** instances that the
moved bodies had swallowed, returning `rooted_inside_after: 0`. Fifty more instances then fell
in the canyon road's corridor and the clearance took them, which is why 515 became 565: that
number is a function of the plant, not a constant of the road.
