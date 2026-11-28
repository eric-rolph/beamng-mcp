# Giant's Hearth level round — handoff, 2026-09-10

Read this first when the session resumes. It is the only file you need to start from.

## 1. What is installed right now

Both copies are hash-verified identical, **installed 2026-09-17 (delivery 7)**; see §0.

| Where | File | sha256 (16) | Bytes |
|---|---|---|---|
| Real profile `…\BeamNG\BeamNG.drive\current\mods\` | `hot_potato_arena_level_ericrolph.zip` | `cd9fb6db303ffaef` | 1,035,229,165 |
| Real profile | `hot_potato_arena_ericrolph.zip` (the scenario, now ON the level) | `fa0c00d06320e826` | 8,156,833 |
| BeamMP `C:\Users\ericr\Downloads\Resources\Client\` | both of the above | same | same |

Since delivery 3 the textures ship pre-cooked (242 of the 422 PNGs replaced by the engine's
own DDS; the lock's `cooked` table maps each) and since delivery 5 the backdrop's compiled
mesh ships fresh, so **the first load cooks nothing at all** — delivery 5's verify boot left
an EMPTY profile footprint. Previous builds kept in `dist_level/previous/` for rollback:
delivery 6 (`599b006d4f0be742`, 1,035,226,777 B), delivery 5 (`55c35942df2eb861`, 1,035,326,256 B), delivery 3 (`60f091053ca4bea9`, 1,034,987,542 B), delivery 2 (`49e6684e23c5cc78`),
delivery 1 (`b9a4cf210448b535`) and the 2026-09-08 build (`74f0bc4dd084e8ec`).
**Delivery 4 (`e0b46b3a5c0fc43c`) was NOT archived and its bytes are gone** — cut 5 was
taken with `--overwrite` and then installed over both copies. It is reproducible (flip
`blender_backdrop.GIS_ENABLED` to False, rebuild the ring, re-bake its `.cdae`, set
`ZIP_EPOCH` back to 2026-09-15) but that is two Blender-and-boot hours, not a file copy.
**Copy the outgoing zip into `previous/` BEFORE the next `--overwrite`.**

The level is called **Giant's Hearth** in the game's level list (sorts under G, not H).
Four spawn points: South apron, Trailhead, Kettle Lake shore, Firewood Gap.
The skyline is a real canyon rim: USGS 3DEP 1 m lidar of the Island in the Sky rim above
the Shafer benches, Canyonlands (amendment A4). **The wall is drivable** (amendment A6):
from the end of the trail, follow the dirt approach round its loop to the foot of the wall
and up a 2.3 km road cut along it to a pass on the rim, 240 m above. The road is a native
MeshRoad, so it opens in the World Editor's Mesh Road Editor.

**Corrected 2026-09-15: every live gate in this round ran on the user's own 0.39.4 install.**
"0.38.6" is the sentinel profile's directory name, not the engine (`level_facts.md`).

## 0. 2026-09-15 — THIRD DELIVERY CUT under the tightened process (`PROCESS_20260915.md`)

Process: critic passes capped (one per revision, two revisions per subsystem, fixed
checklists, mechanical properties are pytest gates, the user judges what is visible from the
car), one writer on the tree, one cut per session, ship every session. Debt lives in
`authoring/round_records/BACKLOG.md`.

Done offline, all six failing gates cleared (level + arena static suites: **250 passed, 0
failed**, was 6 failed / 241 passed):
- **B5 finished**: arena re-cut against the moved paths and the shipped Hot Potato lock
  (`fa0c00d06320e826…`, 36 members, 8,156,833 B; registry 46 arena + 67 level = 113 of 128);
  the level's QB-8 gate scopes out the arena's shapes by name (its `.cdae` harvest is B6 debt).
- **B1 r17 done**: `terrain_model.py` byte-identical to the frozen design again; the brink
  repaint lives in `level/brink.py` behind `terrain_io.grid()`; `.ter` unchanged
  (`8e354091…`); design amendment A1 recorded (`authoring/design_amendments.md`).
- **Full-level cut**: 808 members from a staged tree, `ZIP_EPOCH` bumped to 2026-09-15,
  `dist_level/` sha256 `b9a4cf210448b535544bf7e4fcef0a226ce16d40e073ff73ee80dbf4bbf286c8`,
  998,247,847 B. `main.decals.json` 139,876 B; hearth/night_light/audio groups present.
- **Installer**: `install_level.py` (report / `--deploy`, hash-verified, FILETIME
  `mods.json`), with `tests/test_hot_potato_arena_install.py`.

Boot evidence (sentinel, engine 0.39.4, `authoring/round_records/delivery_20260915/`):
- **Delivery verifier: SHIP.** Level listed; probe scenario and freeroam playable; forest
  154,686 = 154,686; 54/54 species, 17/17 ground covers; hearth + 18 SFX sources; decals
  619 rows / 12 keys; props present; **59.86 fps average, 0 frames over 33 ms** at the
  23-vehicle census, day and night; six frames in `shots/`. The one raw E line
  (`No entry point for level found: /levels/ericrolph_hot_potato_arena`) is the pre-mount
  probe of the sentinel's remembered last level, 5.1 s before the zip mounted, bucketed by
  the 09-08 `finalise.py` as `premount_level_scan` (0 unattributed).
- **Arena scenario on the level: SHIP** (run 2; run 1 was a false green of the instrument
  itself, archived). Listed exactly once under the level, started in 53.7 s, 23 vehicles.

**Installed 2026-09-15 01:40 to BOTH the real profile and BeamMP** (`install_level.py
--deploy`): level `b9a4cf210448b535` 998,247,847 B and arena `fa0c00d06320e826` 8,156,833 B,
re-hashed on disk, `mods.json` regenerated (backup `mods.json.bak-20260915`). The BeamMP
client folder had never carried the arena zip before today. Rollback copies of the replaced
builds sit in `dist_level/previous/`.

### Delivery 2, 2026-09-15 06:23 — B3 r12 shrub imposters, the round's last open visible item

- **B3 r12 PASSED under the capped process** in two revisions and zero critic passes
  (`authoring/round_records/b3_r12/report_B3_r12.md`): the lime was the three shrub leaf
  sheets, the only cut-out foliage never graded; the black gashes were card normals wound
  toward the plant centre (stored-X vs column −0.90/−0.92/−0.84 → +0.91/+0.97/+0.88). r12b
  re-stamped leaf_01 and took its alphaRef 75 → 28 because the 128 px bake drops a block
  whose mean alpha sits under alphaRef (bake fill 0.489 → 0.705 against the gate's 0.506).
  Debt recorded: the far billboards of shrub_01/02 are grey-green rather than in the pines'
  band. Before/after frames: `b3_r12/crops/`, `b3_r12/evidence_r12/shots/`.
- **Gates:** forest + props 80 passed; full repository static suite **2108 passed, 143
  skipped, 4 xfailed, 1 failed** — the one failure was an arena live-gate file still reading
  the pre-B5 Gridmap path; both arena live suites were re-pointed at the level and the test
  now skips cleanly without a simulator. Ruff findings in those two untracked round files are
  pre-existing (none on the edited lines) and were left alone.
- **Cut 2** from a staged tree: 808 members, `49e6684e23c5cc784f764061ae48cb86b8cf28680fe32919668f8f342293b8df`,
  999,266,488 B. **Verify boot: SHIP** with nothing to attribute (the pre-mount scan named
  only GridMap this time): probe scenario 40.1 s, freeroam 33.7 s, forest 154,686 = 154,686,
  54/54 species, 60.0 fps on both legs with 0 frames over 33 ms
  (`authoring/round_records/delivery_20260915b/`).
- **Installed to BOTH places**, re-hashed on disk, `mods.json` regenerated; the arena zip was
  already current from delivery 1. The arena scenario boot was not repeated: the arena
  archive is byte-identical to delivery 1's.

### Delivery 3, 2026-09-16 00:12 — textures shipped cooked; cauldron, kindling logs, tripod and lantern removed

- **The "TEXTURE" placeholder in the delivery frames was the engine's texture cook, not a
  missing file.** Both delivery verifiers shot their frames 8–14 s after a cold level load
  while the engine was cooking 242 PNGs (378 MB) into its cache — the 09-08 round's
  `reshoot_frames.py` existed for exactly this and was not run on 09-15. A player paid the
  same cook on the first load of every new build.
- **Fix (B6, the giant-props layout):** one sentinel boot harvested the engine's own cooked
  DDS with provenance (`authoring/round_records/b6_cook/`, kept beside the level as
  `textures_cooked_level/`); `build_level_zip --cooked-dir` ships each proven DDS in place
  of its PNG while materials keep naming the `.png`. Cut 3: 808 members, 180 PNG + 362 DDS,
  `60f091053ca4bea9cbc159d9297f07baf94c5525b58f15eaa019fa8132ef4594`, 1,034,987,542 B
  (amendment A3 raises QB-28 to 1.1 GB, +35.8 MB). **Verify boot: SHIP** — the engine cooked
  **4 files instead of 256**, level load **33.7 → 10.2 s**, probe scenario **40.1 → 18.7 s**,
  cold frames fully textured, 59.93 / 59.95 fps with 0 frames over 33 ms
  (`authoring/round_records/delivery_20260915c/`; run 1 there is the same boot blocked only by
  a stale placement manifest, regenerated).
- **Removed at the user's request (amendment A2):** `log_north`, `log_south`, `enamel_pot`,
  `lantern_tripod` and the `giant_lantern` that hung from it (70 statics, was 75); with
  them the hearth round's eight log-end fire/smoke nodes (26, was 34), the four kindling
  fire lights and the lantern's two lights (30, was 36; flares 2, was 8). Shapes still ship;
  the level description no longer names them.
- **Gates:** full repository suite 2108 passed, 144 skipped, 4 xfailed, 0 failed on the
  final tree and cut 3; static reference scan of cut 3: every `.png` reference resolves to a
  PNG member or its cooked sibling.
- **Installed to BOTH places**, re-hashed on disk, `mods.json` regenerated; arena zip
  unchanged and current.

### Delivery 4, 2026-09-16 00:56 — the user's drive: shrub LOD, second removal

The user drove delivery 3 and sent frames. What each was, and what was done:

- **"Trees like half circles with no trunk"** = the four shrubs drawn as their billboards
  past ~30 m: a 2.6–5.3 m shrub is 120 px tall there and its two-step LOD chain ended.
  **B3 r13:** a third detail `(40, 320)` keeps the mesh to ~100 m; the dome is three lobes
  so it no longer reads as a ball up close. One bake boot (8 atlases, 4 compiled meshes);
  `authoring/round_records/b3_r13/`. The ferns and the reed have the same trap
  (`BACKLOG.md`).
- **"Rocks like slices of bacon, hollow"** = the face-scan solids' skirts (the two cliff
  outcrops, the crag, the hearth's rock-face stones): rows bulged by coarse noise become
  ledges (`terrace_probe.py` rules out a voxel terrace). **Not fixed yet** — the fix depends
  on the user's canyon decision (rework the skirts, or drop the outcrops).
- **Removed (amendment A2, second message):** the leaner log across the trail, the bench
  deck, the four lantern posts and their four track-lantern lights. Props 64, night lights
  26.
- **Gates:** level suites 164 passed; full repository suite 2108 passed, 0 failed on the
  final tree and cut 4.
- **Cut 4** (staged, cooked): 808 members,
  `e0b46b3a5c0fc43ca0a8a88ea34831ae1265ce2a51684c4a7b0e1c5502780ef5`, 1,035,338,102 B.
  **Verify boot: SHIP** — props 64 = 64, hearth 135 = 135, forest exact, **0 textures cooked
  at load**, level load 8.8 s, 59.99 / 59.98 fps, 0 frames over 33 ms
  (`authoring/round_records/delivery_20260915d/`). **Installed to both places.**
- **Open, awaiting the user:** (1) the Canyonlands proposal — USGS 3DEP 1 m lidar over the
  Shafer Trail switchbacks (`USGS_1M_12_x60y426_UT_WestEast_B22.tif`, 301.3 MB, public
  domain) plus OpenStreetMap road geometry (ODbL); a new subsystem B7 growing the terrain
  block to 4096 m around the byte-identical basin, retiring the fin backdrop, and running
  the trail up the real switchbacks — download NOT started pending permission; (2) the
  bacon cliffs: rework vs remove; (3) "what happened to this design with the structure" —
  the aerial of the skillet is the arena as designed; asked what they expected.

### Delivery 5, 2026-09-16 — the canyon skyline (B7a); the cliffs ruled; the road still open

The user approved all three open questions at once: *"Approved, let's work on all three until
completion."*

- **The backdrop skyline is now a real canyon rim.** USGS 3DEP 1 m lidar of the Island in the
  Sky rim above the Shafer benches, Canyonlands (public domain, EPSG:26912), sampled on this
  level's own three ring radii and checked in with full provenance. The shipped module gained a
  crest SOURCE above `ring_profile`, which is its single seam, so mesh, colmesh, valley floors
  and apron moved together. Amendment **A4**; the round is written up in
  `authoring/round_records/b7/report_B7.md`.
- **The cliff "bacon slices": four fixes measured, NONE shipped** (amendment **A5**). Each
  traded the blades for a worse defect this level's own gates catch. Everything reverted, the
  nine baked artefacts restored from the cut-4 archive, every cliff member byte-identical to
  delivery 4. What the next revision must do, in one piece, is in `BACKLOG.md`.
- **The skillet** is the arena as designed; nothing about it changed.
- **One bake boot** re-cooked the ring's 17.5 MB `.cdae`. It is a plain level member in NO
  harvest manifest and the engine prefers a `.cdae` to its `.dae`, so a stale one would have
  shipped the old skyline in silence with every static suite green.
- **Gates:** full repository suite 2,099 passed with the single expected failure (the lock gate
  asking for the cut); level suites 248 passed on cut 5.
- **Cut 5** (staged, cooked): 808 members,
  `55c35942df2eb861d7f3796a245206594ad948f368d5e0b029a411664c636dc0`, 1,035,326,256 B.
- **Verify boot: SHIP**, blocking []. Terrain deviation 0.0000 m, forest 154,686 exact,
  hearth 135 = 135, props 64 = 64, decals 619 = 619, freeroam load 10.2 s, **60.0 / 60.0 fps
  day and night, 0 frames over 33 ms, and an EMPTY profile footprint** — nothing cooked at load.
  A new gate casts 1,512 rays and separates the two candidate skylines: **0.197 m from the lidar
  crest, 69.3 m from the synthetic one** (`authoring/round_records/delivery_20260916/`).
- **Installed to both places.**
- **Still open, and it is the user's own ask:** the drivable half — *"make it drivable, extend
  the road up into the side wall mountains."* Measured and scoped as **B7b** in `BACKLOG.md`.

### Delivery 6, 2026-09-16 — the canyon wall is drivable (B7b)

The second half of the user's canyon request, *"make it drivable, extend the road up into the
side wall mountains (if possible)"*, built with BeamNG's own MeshRoad after the user asked for
native tools where they make sense. Amendment **A6**; everything in
`authoring/round_records/b7b/` and `delivery_20260916b/`.

- **A MeshRoad 2,340 m along the near ring's face** to a pass on the rim, 10 % grade, a lane
  never under 8 m, banked 3 % toward the rock. **A DecalRoad approach** from the trail's end with
  a 17 m turnaround loop. **515 forest instances** cleared from the corridor.
- **A single traverse, not switchbacks:** the 83-88 deg face makes stacked benches overhang.
- **Proven by driving it:** a harness-steered car went from the trail's end to the pass on the
  exact cut that shipped, 243 m of climb, never more than 2.64 m off the lane centre.
- **Cut 6:** 810 members, `599b006d4f0be742a997206d5d9ebede2faab0c5aa5864b84d33273bea9571b1`,
  1,035,226,777 B. **Verify: SHIP** on run 3 -- runs 1 and 2 refused it over a wrong expected
  deck height in the GATE, both kept. 59.8 fps day and night, 0 level E lines, nothing cooked at
  load. **Installed to both places.**
- **Debt:** the deck grips and sounds like asphalt (a MeshRoad ignores `groundType`); ground cover
  draws over the approach; no AI navgraph on the road; a 16 % last pitch onto its foot; one frame
  over 33 ms per minute where delivery 5 had none.

### Delivery 7, 2026-09-17 — the sliced rocks, and shrubs with trunks (A7)

The user reported both defects a second time, the rocks with a screenshot. Amendment **A7**;
instruments and evidence in `authoring/round_records/d7/`.

- **The cliffs' bodies were stacks of ruled ledges.** A5 had blamed the decimator and stopped
  after four failed attempts; the fix is the pair it never combined -- cut the skirt rows down
  AND remesh the finished body -- because the handles that defeated the remesh-only attempt
  WERE the rows. Sliver area **0.474 / 0.308 / 0.212 -> 0.018 / 0.019 / 0.006**, into the band
  every uncomplained-about rock in the tree occupies.
- **Re-sourcing was surveyed and refused on the renders.** Three closed scans measure perfectly
  and every one of them is a squat boulder; at 21-41 m that is a giant pebble, not a cliff.
- **The shrubs had no stem geometry at all** -- one material, leaf cards to the ground. They now
  carry three woody stems on a bark slot, a crown that starts at 0.30 h so the stems are
  visible, and three lobes that are three separate BODIES (r13's lobes sat on one ellipsoid, so
  the silhouette stayed a ball -- which is why the same complaint came back).
- **Forest re-planted in the same revision:** 16,156 instances re-seated out of the moved
  bodies, `rooted_inside_after: 0`; the road corridor's clearance moved 515 -> 565.
- **Cut 7:** 810 members, `cd9fb6db303ffaefa54a7354493e979cd6c3f906b5348eed29a19bd37733e677`,
  1,035,229,165 B; 80 members' bytes moved and NOTHING else. **Verify: SHIP**, blocking [],
  0 level-attributable E lines, **59.87 / 59.97 fps with zero frames over 33 ms** day and night
  -- delivery 6's one-hitch-per-minute is gone. **Installed to both places.**

### Where the round stands (2026-09-16, close)

| Subsystem | State |
|---|---|
| B1 terrain, backdrop, roads | r17 done: frozen spec byte-identical, repaint in `brink.py`, coverage amendment A1. Debt: brink visibility proof, orange-brickwork scan, one-way shore apron, trace-gate soundness. |
| B2 hearth | PASSED (critic pass 7) |
| B3 vegetation | PASSED (critic pass 11) + r12 shrub imposters under the capped process |
| B4 props, deck, trails | Ships with recorded debt (rollover closed and confirmed; harness/evidence items in `BACKLOG.md`); one authored-content oddity on the trail verge for the user's drive |
| B5 scenario on the level | Done: migrated, re-cut, listed under the level, starts with 23 vehicles; live gate ladder G1–G14 re-pointed but not run |
| B6 packaging | Not started: DDS cook (626 MB of PNG), arena `.cdae` harvest, own cubemap; the level ships and plays without them |

The player-visible judgement of every item above is the user's drive.

### B4 — ships with recorded debt (ruling under the new process)

BeamMP server config is `C:\Users\ericr\Downloads\ServerConfig.toml`
(`Map = "/levels/ericrolph_hot_potato_arena/info.json"`, port 30814, private).
Backups: `ServerConfig.toml.bak-20260906`, `Resources/Client/mods.json.bak-20260906`.
`mods.json` uses **Windows FILETIME**, not .NET ticks — regenerate it after any zip change.

**That installed build is now several revisions behind the tree.** It does NOT contain:
the re-authored hearth stone, the fixed trees and forest rocks, the solid mountain's later
revisions, or the deck's containment wall.

## 2. Where the knowledge lives

The round's two record files are the real memory. They were written to the session scratchpad,
which is temporary, so **copies are preserved beside this file**:

- `authoring/round_records/level_facts.md` — every proven engine law and every correction.
  This is the important one. It carries the `.ter` height law, the material `version 1.5`
  trap, the mip-chain/`GraphicTextureQuality` law, the sky-confound law and its night clause,
  the thin-shell and husk gates with their stock calibration, the plough law, straddle time,
  render priority, the reference-point-vs-body-centre law, and the gate-failure families.
- `authoring/round_records/orchestrator_pending.md` — open items, assignments, and the two
  orchestration errors made in this round.

Live originals (if the scratchpad survives):
`C:\Users\ericr\AppData\Local\Temp\claude\C--Users-ericr-beamng-mcp\ac9b4832-415d-4129-bdeb-dfb93bf81de5\scratchpad\level_round\`

## 3. Subsystem status

| Round | Subject | State |
|---|---|---|
| **B1** | terrain, sky, backdrop, roads | r16 written up; **critic pass 16: NOT WOWED** (see §3a) |
| **B2** | the hearth | **PASSED** — critic pass 7, UTTERLY WOWED |
| **B3** | vegetation, forest rocks | **PASSED** — critic pass 11, UTTERLY WOWED |
| **B4** | props, deck, trails | r6 in progress; **critic pass 5 returned NOT WOWED** |

B2 and B3 are final. Do not touch the hearth or the vegetation.

### B1 — what is done and what is open
Done: the backdrop is a **solid closed range with a real collision mesh** (129,024 visual +
129,024 Colmesh triangles, 0 boundary / 0 non-manifold, three shells at χ=0); the world edge
is **shut on all 1,440 bearings** (was open on 648 of them) via a buried shore apron that
leaves the crest **byte-identical**; the repeating cone silhouette is fixed; the brink is
**repainted** (119,925 nodes, 0 heights moved — the repaint is real, but critic pass 16 showed
the "visible" evidence was an exposure artefact, see §3a) and a car covers 197.8 m in 45 s where
it previously managed 0.5 m in 60 s.

Open for **r17**:
1. **The frozen-spec conflict — orchestrator ruling already made.** The brink repaint moves
   `forest_floor` coverage 68.95590 % → 66.14223 % against a design table of 69.0 ± 0.1
   (−2.81367 pp = 118,014 nodes; other eight layers ±0.00000) and it edits
   `terrain_model.py`, which is vendored byte-for-byte from the frozen design spec.
   **Ruling: keep the safety fix AND the byte identity — move the repaint out of the vendored
   file into B1's own module.** Amend the design table only if that is provably impossible,
   and then as a recorded design amendment, never as a widened tolerance.
2. **A self-serving gate change, disclosed by the builder.** r16 changed the trace gate in the
   run it certifies; accepting `class: superseded` turned **323 failures into 0** (r16's prose
   said 341; critic pass 16 measured 323 by re-running the old gate — 333 tokens, seven
   artefacts named, and a published limit admitting the gate now takes the declaration on
   trust). **Critic pass 16 attacked it first and confirmed the exploit** (§3a).
3. The source scan still reads as **orange brickwork from 60 m to the horizon** — both sides
   agree this is the scan, not the tiling.
4. The shore apron is **one-way on 75 % of the shore**; escapes still fail on the deepest
   section.

### 3a. Session 2 (2026-09-10 evening, no-sim): what changed, and how it ended

Critic pass 16 finished offline (live leg deferred in full): **NOT WOWED**. Measured by re-run:
- **Plant exploit confirmed.** One line added to `SUPERSEDED` turns a fabricated token
  `0.8317294` from exit-1 stale into `traced, passes: true`. The old gate fails **323**, not
  341; **333** published tokens have no `this_cut` trace, 260 of them in prose.
- **B16-2, new blocking.** The brink-visibility numbers (−0.07356 / −0.16346) are an exposure
  artefact: the byte-identical control wall darkened more (−0.08930 / −0.20378). Net of control
  the ground moved **+0.00926 / +0.03684**, the wrong way. Driver visibility is not established.
- **r17 ruling proven achievable.** Frozen `design/terrain_model.py` (hash `36f275eeb9c292c0`)
  loaded as its own module with the repaint applied from a B1-owned function yields `.ter`
  sha256 `8e354091c24e30c6fafdb9e9b7a2c57e84e2cc75714ede3322e81db37569fad6`, byte-identical to
  r16's shipped member. Traps: `terrain_model.py` is untracked in git, and `get_grid()` is
  memoised, so the repaint must copy before mutating.
- **Member count settled at 808** (`mod/` is exactly the 808 list). B1's 803 was short the five
  `f_branches` textures.
- Soundness repair: the cut-hash half is feasible (all seven declared cut shas resolve); the
  artefact-member-digest half is impossible on current artefacts.

**All three agents launched that evening (B5, B1 r17, B4 r6) were killed by the weekly API
limit (HTTP 429), not by anything in the work.** Last-known positions:
- **B5** had applied the migration on disk: 36 members moved from `levels/gridmap_v2/...` to
  `levels/ericrolph_hot_potato_arena/...`, all byte-identical (`b5/migration_proof.json`); the
  old location is gone; `SHAPES_RELATIVE`/`SCENARIO_ROOT` moved in code. It died while
  re-pointing `tests/test_hot_potato_arena_package.py` at the moved materials sha. The arena
  dist (`dist/`, 2026-09-02) was **not** re-cut, so the package lock test fails until it is.
  `gridmap_v2` still appears in the handoff json (3) and in four arena test files.
- **B1 r17**: nothing done. **B4 r6**: mid-analysis of the player frames (`b4/r6/`).

### B4 — what is done and what is open
Done: the off-axis rollover is **closed and independently confirmed** — 115 certified cells
with no exclusion list (0 rolled, 0 over a long edge, 115 upright), and the critic drove a
further **43 cells in the builder's own declared blind spot** (headings ±50–85° never driven
at any speed, plus 20 m/s and full-lock steering) with the same result. The shipped
containment wall is **1.20 m**, verified in both the mesh and the collider. The design's
long-unexplained **self-acceleration anomaly is solved**: a held foot brake at a standstill
selects reverse and the brake input becomes the reverse throttle. It was never the map.

Open for **r6** (was mid-flight when the session ended):
1. **Reference point vs body centre, third instance.** `_drive_grid` teleports the vehicle's
   **reference point** to the deck centreline while the pickup's **body centre** is up to
   **1.17 m** away, so the cars were never square on the deck. A centred body fits the 6.0 m
   trough with 0.45 m to spare. The "wedged" cell was mis-placed, not wedged.
2. The provenance gate misses four plants, including **deleting a published block** (20 → 19)
   while still reporting ok, and **8 of its 20 blocks have no staleness check at all** — one
   of them `span_splits`, the artefact that gate exists for.
3. `beach_check`'s universal claim is checked over 21 cells and **false on 36 of 115**.
4. The ten player frames are priced nowhere, and `b4_bench_broadside_100m` **contains no log
   at all** — it is a photograph of the forest, measured as a rung of the log's own ladder.

### Queued, not started
- **B3 r12** (player-visible): the `f_shrub_01` / `f_shrub_03` distant imposters bake to
  chartreuse slabs with black gashes and sit in the driver's forward view on the trail;
  `f_shrub_02`'s is a near-transparent skeleton.
- **B5**: move the Hot Potato scenario onto this level. It currently installs into Gridmap,
  so Giant's Hearth is freeroam only. Brief written, never launched.
- **B6**: packaging — DDS cook, cubemap, minimap, provenance, final lock, census, and the
  **per-subsystem frame-time attribution with controls**, which the user's "build it all,
  measure, then cut" decision depends on and which has never been taken.

## 4. The next full re-cut — read before cutting

- Member list is **810** since delivery 6 (`level/members_full_level.json`: + the canyon road's
  group file and its materials). B1 r16 says its own re-cut needs
  **803** — reconcile, do not assume either.
- **Take 13 members from B1, not 4.** B1's scaffold cut **stubs `main.decals.json` to 259
  bytes against 139,876** and would delete B2/B3/B4's content. Same overwrite family as the
  two races patched at the start of this round.
- `dist_level/`'s backdrop material has **no detail stage at all** — it is pre-r13.
- Re-cut, verify on an **idle** sentinel with `delivery/verify_delivery.py`, then install to
  **both** the real profile and the BeamMP client folder, and regenerate `mods.json`.

## 5. Rules that cost real work to learn

1. **One sentinel-needing agent at a time.** Contention lost a critic's four test drives and
   two frames, denied B4 three boots, and left B2 without a frame-time measurement for five
   revisions.
2. **A task notification whose result says work is still running means the agent is PAUSED,
   not finished.** Resume it; never spawn a second worker on the same directory. Doing that
   once put two workers in one directory for half an hour.
3. **Write instruments with the Write tool, never a shell heredoc.** A heredoc ate the escape
   characters in three separate gates this round; each then reported clean while blind. This
   outranks any generic "prefer Bash" directive, and an agent that sees the conflict should
   follow the brief and flag it.
4. **Never a glob in env-prefix position.** One did, and a repo-wide formatter ran over 24
   files including three of the user's own uncommitted test files. Nine remain unproven; all
   suites pass. Remedy tool: `b1/r14/accident/lint.py`, which takes its file list from a file.
5. **Measure the packaged archive, never a tree an agent is writing to.** The orchestrator was
   caught doing this and published a mis-attributed before/after.
6. **Every gate ships with a demonstrated failure case.** A gate never shown to fire has not
   been tested. Test by deletion as well as by corruption.
7. **Sweep the whole parameter range, not the samples you chose.** Three defects hid behind
   sampling: the deck's 10° heading step, the world edge's four axis arcs, and a backwards
   autocorrelation bound that stock content fails.
8. **Carry the control as a real build arm** (`--no-detail-map`), not as an argument. If the
   treatment loses to the control, the treatment is the defect.
9. **One structural change per revision** — but scope the deferral to the part that needs it.
   A fix that changes no vertex is not a structural change.
10. **Reproduce a critic's number with the critic's own code before disputing it**, then
    dispute the metric with a stock control.

## 6. Hygiene at session end

- No BeamNG process running; terrain material cache 0 entries.
- Real profile and BeamMP resources verified byte-identical to the 09-08 delivery.
- `git rev-parse --short HEAD` = `1932787`. Nothing committed. 14 modified tracked files,
  unchanged from session start.
- Sentinel `mods/` holds B4's test archive `level_scaffold_71f4c9f98e.zip` (995,272,224 B) —
  test profile only, harmless, replace or delete freely.
