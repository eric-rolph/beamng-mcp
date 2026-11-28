# The Gateway Skillet — Hot Potato arena map, design blueprint and round ledger

Shell B scenario mod on stock `gridmap_v2` (the Cannon Car Wash pattern): a
scenario JSON with a scenario-owned GE extension, a JSONL prefab of 72
records, thirteen Blender-authored TSStatic shapes under
`levels/gridmap_v2/art/shapes/hot_potato_arena/`, and a lock that chains to
the Hot Potato mod's own lock. The arena is a CONSUMER of the Hot Potato
runtime (`examples/giant_props/hot_potato/`, build serial 55): it sets five
options at boot, registers 46 obstacle keep-outs, runs three geyser cycles
and a boundary-decay valve, and hands everything back on exit.

Player mandate (2026-09-01): a MAP for the Hot Potato mod, workers paired
with critics who must be UTTERLY WOWED before anything ships. Four rounds ran
serially — design (three critic rounds plus a v3.1 amendment), geometry
(three rounds, an errata pass, and the v3.2 design change that made the
floor skin a driven surface), runtime hooks (five rounds, serials 42 → 47),
scenario package (five critic rounds plus a sixth regeneration) — and each
critic round ended WOWED. The integration round then ran the live ladder
G1–G14 over 79 boots (§11–§12), exposing six runtime bugs that were fixed
upstream (serials 48, 50, 51, 52, 54, 55) and eight geometry rounds. Two
findings reversed earlier decisions and both were then closed by
measurement: the magnet does not contain a powered car outside the pan —
answered by the out-of-bounds fuse penalty the brief originally asked for,
proven over 478 live samples (§11.5.4–5) — and the far-field acceptance was
measured in the wrong region, re-measured over a glacis annulus and now
honestly "clean at 100 m, still striped at 150 m and above" (§11.5.1). A third
finding was retracted by its own author (§9.2, v3.7). **§13 is the final
state; no stubs remain.**

Every number below is either a contract number from the design, a build
measurement from the generator's asserts, a live measurement from the
sentinel profile, or a critic's independent reproduction; the ledger in §8
says which. Failures are recorded because they are the useful part.

---

## 0. Identity

The Hot Potato mod's fiction is a quarter-scale stainless monument arch that
cooks a potato (hot_potato/DESIGN.md v2.2, v2.4: medallion, plinths, mash,
"CHAMPION OF THE ARCH"). The arena completes the joke the mod has been
telling all along: **the Arch stands in the middle of a colossal cast-iron
skillet.**

- The inward-banked perimeter is the **pan wall** with a rounded crest.
- Two grade-level gaps in the wall are the **pour spouts**.
- The low-friction patches are **butter pools** — golden, glossy,
  mechanically ice.
- The high-drag ring guarding the pickup pad is the **salt ring**.
- The dynamic pinch points are **spatter geysers** — steam columns that pop
  cars upward on a cycle: one gate pair in the bowl, one seated in each
  pour-spout throat (three cycling hazards).
- The one-way elevated deck is the **skillet handle**, a 4 m raised causeway
  ending in a drop-nose that dive-bombs the medallion.
- Breakable sightline breakers are **pantry stacks** — real softbody
  cardboard boxes and barrels (stock prop vehicles), not fake TSStatics.
- Inside the masher-pillar ring the centre grows its slalom: four **pepper
  grinders** (short fat pillars).

Scenario display name: **"Hot Potato: The Gateway Skillet"**. Namespace
`ericrolph_hot_potato_arena_` on every object, trigger, material and file
basename; the GE extension registers as `scenario_ericrolph_hot_potato_arena`.

## 1. Archetype

Hybrid: **Inverted Bowl** (primary) + **Pillar Slalom** (centre) + one
**Multi-Tier** element (the Handle). The mod's real field is the player, five
conscripted AI and a BeamMP handful — 6–10 vehicles, the Inverted Bowl's own
band in the player's archetype table. The slalom covers the 2–6 endgame
(doubled in v2 after critic round 1 found "four pillars 68 m apart is open
field"). A full multi-tiered deck overshoots the field, so it is reduced to
the Handle. Figure-8 was rejected because the runtime's AI drives straight
lines (chase/flee beeline plus a dodge reflex) and cannot play a timing
crossroad.

## 2. Dimensioned layout, as shipped (v3.2 geometry)

World anchor **C = (850, −280, 100)**; bearings compass-style, 0° = +Y,
90° = +X; a point at (θ, r) is `(850 + r·sin θ, −280 + r·cos θ)`. Grade
z = 100.000 exactly (F-P4.4). Arch feet on the 90°/270° axis at r = 22.8
(prop-authored half-span 22.801 m); the under-arch lane runs north–south.
`arena_radius_m` stays at the runtime's default **91.4 m**: the crest is
built AT the runtime's number.

### 2.1 Radial plan

| Zone | r (m) | z above grade | What lives there |
| --- | --- | --- | --- |
| Medallion / pad | 0–6 | prop-owned | Dispenser prop (`ericrolph_hot_potato`, at z 100.1) |
| Salt ring | 12–20 | +0.020 plates on the lifted skin (instance z 100.05) | two SAND arcs, ±45° about 90° and 270°; 3.0 m clear of the skirt top |
| Pepper grinders | 26 | 4.5 m tall, ⌀ 3.0 | 45/135/225/315° (bases 50 mm under the skin) |
| Inner plaza | 6–73.5 | floor skin **+0.050, driven and colliding** (v3.2) | inner skirt r 6.0 → 9.0 at 2.00 % from grade; flat plaza r 9–73.5; AI spawn ring r 40; two centre pantry stacks at r 34 |
| Skin feather | 73.5–76.0 | 0.050 → 0.012 | slope trapezoid, 0.5 m eases, peak grade 1.90 %; lands on the 12 mm datum with a 0.000 mm lip, vertex-coincident with both wall shapes' r 76 toe rings |
| Masher pillars | 48 | 7.5 m tall, ⌀ 2.4 | 45/135/225/315° |
| Feature band | 48–70 | grade | gate geysers (0°), pantry stacks (105°/255°), barrels (160°/200°), butter pools (30°/228°/300°) |
| Pan wall | 76–91.4 | 0 → 5.5 | banked climb, §2.2 |
| Crest | 91.4 | 5.5 | rounded crest = the `arena_radius_m` line; no curl |
| Outer glacis | 91.4–113 | 5.5 → 0 | 27.2 % constant middle, 0.3 m toe feather, lands at (113, 0) |
| Runoff apron | 113–161.95 | stock groundplane | nearest stock mesh at 161.95 m (§8, F-SC2); the clearance gate asserts > 155 m |

### 2.2 Pan wall profile

Knots (r, z) = (76, 0) (79.5, 0.4) (84, 1.7) (88.5, 4.0) (91.4, **5.5**),
monotone PCHIP with zero end slopes, slope-interpolated-and-integrated
(AGENTS.md L1283–1290). Measured on the DAE: **peak grade 69.0 % at r 89.47**
(contract `MAX_GRADE` 0.70, assert A11); deck-end slope 51.4 %; crest exactly
5.5000 (station forced at r 91.4, A14); 31 radial stations including 76.0,
88.5, 91.4 and 113.0; 24 tangential columns per 45° arc wherever grade >
0.35, 12 elsewhere; worst tangential ripple **16.4 mm** at r 112.70 (cap
20 mm, A12); radial sagitta 14.3 mm; every wall vertex within 14 µm / 10 µm
of the analytic profile on both wall shapes (A2, two-sided). The 8 wall seams
and 2 floor seams close at 0.000 mm under the engine's rotation convention
(A6). The bank tax band is therefore 13–69 %; the crest-over at speed is a
≤ 35° hop onto the glacis, not the 49° kicker v3's knots would have built
(§9.2, geometry r1 fix 2).

v1's "45° inward catch-curl" was deleted in v2 (design r1 fix 1): its own
coordinates leaned outward, it contradicted the monotone-r law it cited, and
the magnet (F14, F22) is the proven return mechanism anyway.

### 2.3 Pour spouts

Two grade-level openings at bearings **60° and 240°**: **36.0 m** wide at
the r 76 throat, jambs splayed 15° (44.0 m at the crest floor), jambs
**battered 1:1** from the corridor floor to the bank surface at 52 stations
(zero overhang, top outboard at every station) so the opening measures
54.5 m at the bank surface. Battered faces are matte iron, not rim steel
(geometry r2 fix 3). Corridor floor sits on the 12 mm datum (0.000–0.004 m
proud, feathered).

### 2.4 The Handle

Deck at bearing 180°: **14 m wide (x 843–857), z +4.0, r 30 → 88.2**
(y −310 → −368.223), solid embankment to grade, flush merge with the bank at
the 4.0 knot (r 88.5; measured bank_z(88.5) = 4.000000, 12 end-arc vertices
flush, 7 µm tuck). Ramps are **tangential arcs on the bank apron, r 80–88**
(8 m wide): toes at **149.0° / 211.0°**, 23.1° of slope arc with 3.0 m
eases, 4.0 m flat merge, merge flanks at 175.0° / 185.0°. Surface law: warped,
`z(r, θ) = bank_z(r) + s(θ)·(4.0 − bank_z(r))` — no blended height datum
(AGENTS.md L1285). Measured: along-path grade **11.98 % max, monotone**
(contract ≤ 12 %, A15), toe conformal on the wall MESH at +4.0 mm across all
seven station rows (92 foot vertices within ±0.01 mm), outer-face lip
0.004 → **0.270 m** at the merge (contract ≤ 0.3 m; outside the ±0.02 m
relief law by design, so G2 carries a line for it). The west ramp is its own
mirror DAE (a chiral arc cannot be placed by a 180° rotation; 0 vertices
differ from the mirrored east). Each merge is closed by a **quarter-round
fillet** (ρ 6 m, 98 tris, own shape) tangent to the deck flank and the r 80
ring: junction angles 173.9° / 168.1° × 7 / ≈ 175° (contract ≥ 135°, A16).

Exits: **six** — two ramps, three 4.0 m one-way drop edges (both flanks and
the nose), and the deck rear onto the lowered lip (51 → 69 %, crawlable; at
speed a ≤ 35° launch over the glacis, recorded as a feature). The nose faces
the medallion between the abeam arch feet with ≥ 60 m of clear landing lane.

### 2.5 Placement table

| Object (`ericrolph_hot_potato_arena_…`) | Bearing / r | World (x, y) | Size / notes |
| --- | --- | --- | --- |
| `dispenser` (BeamNGVehicle, jBeam `ericrolph_hot_potato`) | — | (850.0, −280.0, 100.1) | `autoEnterVehicle "false"`, licence POTATO |
| `masher_ne/se/sw/nw` | 45/135/225/315°, r 48 | (883.941, −246.059) (883.941, −313.941) (816.059, −313.941) (816.059, −246.059) | ⌀ 2.4 m, h 7.5 m |
| `grinder_ne/se/sw/nw` | 45/135/225/315°, r 26 | (868.385, −261.615) (868.385, −298.385) (831.615, −298.385) (831.615, −261.615) | ⌀ 3.0 m, h 4.5 m, cylindrical stave UVs |
| `geyser_tower_l/r` | ∓6°, r 58 | (843.937, −222.318) (856.063, −222.318) | 3 × 3 × 6 m boxes, 12.1 m centre to centre |
| `butter_pool_1/2/3` | 30° / **228°** / 300°, r 66 | (883.0, −222.842) (800.952, −324.163) (792.842, −247.0), z 100.05 | 18 × 10 m, groundtype ICE; top +20.0 mm proud of the lifted skin, rim flush on it; r 61–71, 2.5 m short of the feather |
| `salt_arc_e/w` | 45–135° / 225–315°, r 12–20 | arcs, z 100.05 | 8 m wide, groundtype SAND, +20.0 mm proud of the skin; 4.50 m from the grinders |
| `handle`, `handle_ramp_e/w`, `merge_fillet` | 180° (toes 149°/211°) | deck (850, −310) → (850, −368.2) | §2.4 |
| `wall_015/105/150/195/285/330`, `wall_spout_060/240` | 8 × 45° arcs | — | two arc shapes; spout arcs carry the jamb batter |
| `floor_045/135/225/315` | 4 quadrants, r 6–76 | — | +50 mm driven skin, `collisionType "Visible Mesh Final"` (v3.2; was a 12 mm no-collision inlay through v3.1); single mesh detail, §6 |
| `trim_ring` | crest / plate | — | name plate +18.0 mm, base rebated −3.0 mm; 0 geometry rivets |
| `boxwall_1/2` (3 × `cardboard_box`) | 105° / 255°, r 60 | — | 3 wide × 1 high, 1.4 m pitch along the tangent |
| `boxwall_3/4` (3 × `cardboard_box`) | **20° / 200°**, r 34 | (861.6, −248.1) (838.4, −311.9) | centre pantry stacks |
| `barrels_1/2` (2 × `barrels`) | 160° / 200°, r 64 | — | 1.8 m pitch |
| AI ×5 (covet, bx, etk800, barstow, bluebuck) | 30/150/210/270/330°, r 40 | ring, z 100.6 | facing the pad (heading·to-pad 0.99999998 live) |
| Player (etk800) | 120°, r 40 | (884.641, −300.0, 100.6) | `startFocus`, licence SKILLET |
| Geyser sites | gate: tower midpoint (850, −222.318); spouts: 60°/240° at **r 90** | (927.942, −235.0) (772.058, −325.0) | §4.4 |

v3.1 moves relative to v3: pool 2 210° → 228° (it was buried under the west
ramp, geometry r1), centre stacks 15°/195° → 20°/200° (boxwall_4 was 1.8 m
from the deck flank; now 4.8 m), spout sites at r 90 (scenario round 1 had
typed 91.4; corrected in the layout file). Box walls are 3 × 1, not the
design table's "3 × 2": the 12-box census the perf probe proved wins.

### 2.6 Hard proportions

Heaviest guaranteed class: the D-Series pickup — wheelbase **2.98 m** (front
hubs y −1.49, rear axle `ax2` y +1.49; v1's 3.05 was corrected by the design
critic), half-track 0.82 m, body half-width ≈ 0.95 m, front overhang
≈ 0.9 m. With a conservative 33° outer-wheel lock the curb radius is ≈ 6.8 m
→ turning circle ≈ 13.5 m; **the design keeps 14 m**. Mandatory lanes ≥
2.5 × 14 = **35 m**; open-field slalom spacing floor **14 m** (one full-lock
U-turn). **G2 later drove the figure-eight and measured 11.18 m right /
13.27 m left** (§11.6): the assumption was conservative in the safe
direction, so every clearance below has more margin than the contract asked
for, and the grinder-ring contingency was retired unused. Measured against the placement table: masher↔masher chord 67.9 m,
masher↔arch foot 35.7 m, masher↔wall base 26.8 m + 9 m of ≤ 32 % apron =
35.8 m, gate tower↔masher 36.6 m, spouts 36 m, under-arch lane 45.6 m,
masher_se → east ramp inner flank where it first exceeds 0.5 m (≈ 153°, r 80)
36.2 m; grinder↔foot **15.3 m face / 14.5 m corner** (foot half-side 2.06 m,
the runtime's own `DODGE_KEEPOUT` comment), grinder↔masher 19.3 m,
grinder↔grinder 36.8 m. Contingency: if G2's driven figure-eight measures
the real circle above 14 m, the grinder ring moves outward metre for metre.
Named exceptions: gate tower gap (an optional pinch with ≥ 36 m bypasses),
the 14 m Handle deck (exactly one U-turn wide, the risk element), and the
breakable stacks (the wall IS the route). The Wentward bus (wheelbase
7.45 m, circle ≈ 26–28 m) is supported in the bowl, spouts and under-arch
lane; the pillar rings and Handle are not guaranteed for it.

## 3. The two failure modes

### 3.1 Infinite perimeter looping — three mechanisms, no null layer

1. **The bank taxes the orbit.** The perimeter is a 13–69 % climb with no
   vertical face to lean on; a wide line bleeds speed into grade and easing
   off slides the car back into the bowl.
2. **The rim is interrupted and the outside is a losing position.** Two
   spouts cut the annulus. Past the crest a car has left the circle: it
   cannot receive the potato (F20), and the magnet — grab past r 91.4,
   release at 0.9 × 91.4 = 82.3 m (F22), 1.2 g default at ≈ 31° elevation
   (F28) — reels it back through ~9 m of control-compromised re-entry.
   **MEASURED, and this holds only for a ballistic stray.** G8/G9/G10 haul a
   crest-over home in 6.85–6.95 s every time; but a POWERED car that climbs
   the bank and reaches the flat apron past the r 113 toe is never brought
   back at either magnet dial (§11.5.4), while a powered exit through a
   SPOUT is caught in 5.5–6.6 s. Mechanism 2 is therefore true at the
   spouts and false over the bank, and the gap is what runtime ask #7
   (§11.5.5) exists to close.
3. **Butter pools sit on the wide line.** Three ICE plates at r 66: the mod
   material binds the engine's ICE groundmodel (measured μ 0.200 / 0.204
   against 1.00 on the control plate, F-P1.7) — cross them at speed and
   skate into the bank, or swing inside and stop being a perimeter runner.

v1 claimed a fourth layer, camp burn, "left on by the boot". Both halves were
false (`camp_burn_multiplier` defaults to 1.0 = off and only taxes a CARRIER
below 20 km/h, F21); the layer was deleted, not patched. The boot does not
touch it.

**The magnet-orbit wall-rider** (design r2 fix B): a constant central force
plus tangential speed is an orbit at v = √(a·r). With the runtime's real
hoist split (0.515 lift / 0.857 horizontal, `lift = distance * 0.6` in the
sweep), 1.2 g gives 1.03 g centripetal → **31.8 m/s (114 km/h) at r 100** —
inside a fast car's envelope — contested by the glacis cross-slope and only
≈ 0.37 g of residual tire authority. The escalation lever is owned: lift
exceeds 1 g at **≥ 1.95 g**, so `hotPotatoSetOption("arena_magnet_g", 2.0)`
(range 0.1–3.0) makes a powered orbit physically impossible; it is pulled
only on measured G3 failure because it makes every haul-back airborne.

**The spout dive** (design r1 fix 3): a non-carrier can dive out a spout and
be untaggable until hauled back. Countered by the spout geysers (36 % duty,
§4.4); by the emergent price in classic/pinball (nothing to score outside,
and the ~9 m haul-back is a free-tag window for a carrier at the mouth,
softened only by the 4 s grace, F23); and in hoarder/protect — where v2
claimed a diver "cannot score" and was wrong at the file level (F25) —
closed UPSTREAM by runtime ask #2 (§5.1). G3 carries three adversarial
sub-tests with numeric thresholds (§7.3).

### 3.2 Corner stalling

No corners exist; every junction is a curve; no enclosed alcove exists. The
generator asserts it: A10 rasters the plaza r < 80 at 1 m (19,322 free
cells, one region, every feature and spawn on it, 0 pocket cells); A16 finds
no plaza cell with solids on ≥ 13/16 of its 8 m horizon (worst 12/16 at
bearing 187.0°, r 78.1 — the concave fillet cove, open across its whole
inboard 180°) and every tall-face junction ≥ 135° (built ≥ 168°). The
Handle has six exits. Being cornered by CARS is the game (contact =
transfer); the dodge hook keeps AI from wedging into geometry it cannot see.

## 4. Player-requested elements, each with its mechanism or its deferral

| Element | Mechanism as shipped | Status |
| --- | --- | --- |
| Breakable sightline breakers | 16 stock softbody prop vehicles (12 `cardboard_box`, 4 `barrels`) as prefab BeamNGVehicle records; the runtime classifies them scenery (ask #3) so they block sight and scatter but never hold the potato; the detonation shockwave still shoves them | built |
| One-way drop-off ledges | the Handle: three 4.0 m drop edges, no climb back; ramps are the only way up | built |
| Momentum hazard patches | mod materials carrying `groundtype` ICE (butter) and SAND (salt) on plates 20 mm proud of the driven skin (instance z 100.05, A21) under `levels/gridmap_v2/art/shapes/` — the level-scoped root that auto-loads (F-P1.5); ICE measured 5× lower deceleration than the control plate (F-P1.7) | built; SAND not separately braked (one G2 run recommended) |
| Dynamic pinch points | three spatter geysers on staggered cycles (§4.4); a pop is a velocity ADD of +5.5 m/s, once per vehicle per ON window, only inside a resolved curtain | built |
| Kinetic / repulsion boundary | the bank + the runtime magnet (F22 grab/release semantics); no flat wall exists to slide along | built (runtime-owned) |
| Active boundary decay | the decay valve: 120 s without a pass → `arena_radius_m` 75, 180 s → 60, every round exit → 91.4; ≤ 3 option calls per stalled round | built |
| Out-of-bounds fuse penalty | NOT built: the runtime's v2.6 ledger rejected it as "invisible punishment, illegible in play" (hot_potato/DESIGN.md L981); the magnet is the shipped answer | deferred by ledger law |
| Velocity-bleed walls | redesigned into the bank + butter: there is no wall to scrape | redesigned |
| Corridors ≥ 2.5 × turning circle; ≥ 35–50 m runoff past blind drops; ≥ 3 exits per alcove | §2.6; 47 m of verified-clear apron past the glacis toe (161.95 − 113 − margin); no alcoves, Handle 6 exits | built |

### 4.4 Spatter geysers

| Site | Centre | Strip (half-length × half-width) | Cycle | Emitter nodes |
| --- | --- | --- | --- | --- |
| gate | tower midpoint (850, −222.318) | 4.55 × 1.5 m | 8 s off / 4 s on, phase 0 | 1 wisp + 2 steam curtains + 1 spatter = 4 |
| spout_e | 60°, r 90 (927.942, −235.0) | 15 × 3 m | 9 s off / 5 s on, phase 4.667 s | 1 wisp + 4 curtains (±4, ±12 m) + 1 spatter = 6 |
| spout_w | 240°, r 90 (772.058, −325.0) | 15 × 3 m | 9 s off / 5 s on, phase 9.333 s | 6 |

Wisps (`BNGP_waterfallsteam` at the site centre) ship `active: true` and
stay on as the OFF tell; curtains and the `BNGP_34` spatter switch with the
window via `setActive`. A vehicle inside the strip and within −1..+4 m of
grade takes `applyClusterVelocityScaleAdd(refNode, 1, 0, 0, 5.5)` once per
window; the popped set is dropped at each window start. A site whose emitter
census did not resolve never pops (`geyser_blind`, one warning). Lupa: ≥ 75 %
of frames have some site ON and < 25 % have all three ON; 20 cars × 7
windows = 140 pops with no state growth. Live (moving car at 6.04 m/s):
horizontal 6.043 → 6.035 m/s across the pop frame (0.12 % change), vz
+5.34 m/s in one frame, apex rise 1.55 m.

## 5. Integration contract with the runtime

### 5.1 The three runtime asks (Hot Potato v2.8, serials 43 → 47)

1. **Obstacle registration** — `hotPotatoRegisterObstacles(list)` /
   `hotPotatoGetObstacles()`. A dense array of `{x, y, r}` (world metres,
   2-D, r in [0.5, 30], at most 64). A call REPLACES the set; only `nil` or
   `{}` clears; everything else is refused WHOLE with `false`, one warning,
   prior set intact — including a lone post without its braces, a holed
   list, a keyed table and a 65th entry (runtime r1 fixes 1–2). Posts join
   the dodge sweep beside the arch feet, and the ray keeps the NEAREST
   threatening post along the heading (a fix to the shipped v2.7.1 dodge:
   westbound along the span from (30, 0) the old first-found order aimed at
   (−30.8, −9.5) through the near foot; now (14.8, −9.5)).
2. **Hold-mode scoring gate** — hoarder/protect accrual and the crown check
   sit behind `v26.insideArena` on their own per-frame carrier fetch; arena
   off → identical to before; classic/pinball untouched.
3. **Subject filter** — `v26.isPropVehicle`: `vehicle:getJBeamFilename()` →
   `core_vehicles.getModel(name).model.Type`; `SCENERY_TYPES = {prop,
   trailer}` case-insensitive; `unicycle` always a subject (traffic's own
   special case); fail OPEN for Unknown / Heavy Machinery / Traffic / Debug /
   missing `core_vehicles` / throwing lookup. Cache `{model, prop}` per id
   with the model re-read every roster pass (the engine reuses the object on
   in-place replace). A carrier that becomes scenery hits the carrier-lost
   path before the pass sweep (`carrier_became_scenery`). `field` (round
   peak) and `props_excluded` (per frame) ship in both stats channels.

The runtime also ships the `MPCoreNetwork` rawget fix (§10, law a) in the
serial-47 zip.

### 5.2 Boot, snapshot and hand-back

Retry every `onPreRender` until `extensions.ericrolph__hot__potato_runtime`
resolves (silent for 30 s, then one warning), then in order:

1. If `settings/ericrolph_hot_potato_arena.snapshot.json` exists the
   previous visit never handed back (crash / Alt-F4): hand its values back
   FIRST (`crash_recovery`, valve radii excluded), delete it.
2. Snapshot `hotPotatoGetOptions()` for exactly the **five** boot keys; write
   the snapshot file BEFORE the first option write (`snapshot_file_written`
   reflects `jsonWriteFile`'s own return; fail-open by design — the
   runtime's `saveOptions` ignores the same return, so a folder the arena
   cannot write is one nothing can dirty).
3. Exactly **five** `hotPotatoSetOption` calls: `arena_radius_m 91.4`
   (self-heal of any dirty persist), `arena_enabled true`, `ai_enabled true`,
   `arena_magnet_enabled true`, and — since scenario round 8 —
   **`oob_burn_multiplier 3.0`**, placed fifth, after the magnet, because it
   is the other boundary mechanism. The runtime ships that penalty at
   **1.0 = OFF**, so the arena must switch it on or nothing changes; the
   option clamps to {1, 5} and combines with camp burn through `max()`, so
   3.0 is inside the clamp. Each call is a `saveOptions()` disk write, a 3 s
   toast and a `Sync.publishAll` (F18) — five, once per extension instance,
   all five covered by the snapshot and the hand-back rule.
4. `hotPotatoRegisterObstacles` with the 42-entry table.

**Hand-back rule** (mission end, `onExtensionUnloaded` — which is the pause
menu's "Exit scenario" and a restart's unload — and crash recovery): a key is
written back to its snapshot value ONLY when its current value differs from
the snapshot AND equals the arena's own last-written value. A key the player
changed through the HUD tuner mid-mission is theirs and stays. **Accepted
edge, pinned by a lupa gate as expected behaviour:** a key the player sets to
exactly the arena's value mid-mission (toggle off → on; 91.4 typed over a
pre-mission 120) reads as the arena's write and is handed back to the
pre-mission value — the runtime exposes no author for an option write and the
effect is unobservable at exit. The snapshot is consumed on the first
hand-back, so the two exit paths in either order are one hand-back; nothing
global is kept. A restart costs the engine's own reload boot (4 writes) plus
the keys still holding the arena's value at unload — 5 on a default profile.
BeamMP (`MPCoreNetwork.isMPSession()` true): no writes at all, valve off,
obstacles still registered, a leftover snapshot file left alone.

### 5.3 Decay valve

Live round with no pass (`transfers` and `carrier` unchanged in
`hotPotatoGetStats`) for 120 s → 75 m; 180 s → 60 m; any non-live phase →
91.4. Worst case three calls per stalled round; a pass resets the clock; a
refused step is logged once and never retried per frame. **Restore only over
the valve's own step**: if the runtime's current radius is not the 75/60 the
valve wrote (a tuner edit mid-decay), the valve logs `valve_restore_skipped`,
resets its bookkeeping and leaves the value alone. **Watchdog on prop
liveness** (the Dispenser object resolving AND `getSystemState(id).registered`
— never the stats payload, which is legitimately static under a steady tick):
5 s dead while armed or decayed → one restore and disarm; re-arms when the
prop is back. The halo and magnet snap to each new radius because every
consumer reads `OPT.arena_radius_m`.

### 5.4 Obstacle upkeep

Re-register when the runtime module is a new instance (`runtime_reloaded`),
when the Dispenser comes back after dying (`prop_returned`), or when a 5 s
count check finds `hotPotatoGetObstacles().count ~= 42` (`count_drift`). A
refusing hook backs off 10 → 20 → 40 → 60 s (7 calls in 300 s), re-armed on
instance change or prop return; a refusing or missing hook never blocks play.
Cleanup clears the set with `hotPotatoRegisterObstacles({})`.

### 5.5 What the arena does not touch

Transfer, fuse, detonation, mash, fireworks, HUD, BeamMP authority, and every
option except the five boot keys, the valve's radius steps, and — only on a
measured G3 orbit failure — `arena_magnet_g` 2.0. Every engine call is
pcall-wrapped; state is bounded (per-window pop sets keyed by vehicle id,
the option log keeps 16 rows).

## 6. Asset plan

**13 shapes / 32 prefab TSStatic instances / 42 obstacle points / 6 texture
families / 18,288 scene triangles** (geometry round v3.2; through v3.1 the
floor DAE held 864 = near + a `_a70` far detail, now dropped).

| Shape | Instances | Tris | Budget | Notes |
| --- | --- | --- | --- | --- |
| `wall_arc_45` | 6 | 960 | 1,000 | 24-column lip stations |
| `wall_arc_spout` | 2 | 1,072 | 1,400 | battered jambs |
| `floor_skin_quadrant` | 4 | 432 | 350 | +50 mm driven skin with collision (v3.2); rings 6/6.5/8.5/9/40/60/73.5/74/75.5/76, 9 bands × 24 columns; single detail under the stock tree `base00 → {start01 → _a290, nulldetail10}`; **v3.3 sha `1ca6b37e…`, 64,396 B** (a material-symbol rename only — tris and node tree unchanged from v3.2's `4ce0cdcb…`) |
| `handle` | 1 | 2,022 | 1,800 | embankment to grade |
| `handle_ramp_e` / `_w` | 1 + 1 | 720 / 720 | 700 | mirror DAEs |
| `merge_fillet` | 1 (both sides in one shape) | 98 | 120 | |
| `masher_pillar` / `grinder_pillar` / `geyser_tower` | 4 / 4 / 2 | 456 / 304 / 418 | 400 / 300 / 500 | |
| `butter_pool` / `salt_arc` | 3 / 2 | 140 / 160 | 120 / 150 | groundtype plates |
| `trim_ring` | 1 | 480 | 500 | name plate + jamb lip strips |

Texture families: `cast_iron`, `butter`, `salt`, `skillet_steel`,
`handle_wood`, `rim` (baked rivet domes and lip highlight; the 42 geometry
rivets were deleted) — **six families, eight materials** since v3.3 split the
shared matte iron so the floor skin could stop casting shadows (§9.2).
Materials live in
`levels/gridmap_v2/art/shapes/hot_potato_arena/ericrolph_hot_potato_arena.materials.json`
(sha `b584e1d4…`), textures ship as PNG (the engine cooks DDS under `temp/`
at load; a pre-cook is a later re-cut decision). Prefab: 72 JSONL records —
32 TSStatic (every one `collisionType "Visible Mesh Final"` with
`prebuildCollisionData "1"` since v3.2; no `forceDetail` / `meshCulling` /
`originSort` on any record), 23 BeamNGVehicle, 16 ParticleEmitterNode,
1 SimGroup; uuid5 persistentIds. Stock jbeams and particle datablocks are
referenced, never copied. Pillar, tower, deck and fillet bases keep their
grade-level origins and sit 50 mm under the skin (recorded in the handoff's
`bases_buried_under_skin_mm`).

Dist: `dist/hot_potato_arena_ericrolph.zip`, **36 members, 8,146,038 bytes,
sha256 `cfafe4fc2580104b6bad302132389502135db8cd8b706f9e7fcdc7b2902feffc`**
(cut against geometry v3.8), ZIP_STORED at a single pinned epoch, root exactly
`levels`; the lock's `depends_on` pins `hot_potato_ericrolph.zip` **serial 55,
sha `45912b9d…`**. Every shipped DAE / texture / materials member equals
`authoring/ericrolph_hot_potato_arena.hashes.json` (**round v3.8**, baseline
v3.7), in the tree and inside the zip. The shipped Lua carries **46** obstacle
rows.

**Read the locks, do not trust this paragraph.** The archive was byte-stable
from v3.3 through five lock-only re-cuts (`depends_on` 47 → 48 → 50 → 51 →
52), then moved for v3.4, v3.5 and again for v3.6–v3.8, with the runtime
reaching serial 55. `dist/ericrolph_hot_potato_arena.lock.json` and
`examples/giant_props/hot_potato/dist/ericrolph_hot_potato.lock.json` are the
authority; the gate that matters asserts the two **agree**, not that either
holds a particular number. README's verification snippet reads the locks
rather than any printed digest, for exactly this reason.

*State at close: chain agrees at serial 55, and the arena static suites are
**81 passed** (20 package + 57 lupa + 4 site clearance).*

## 7. Build and gate plan

### 7.1 Build

```
& $blender454 --factory-startup --background --python examples/hot_potato_arena/blender/create_arena.py -- [--export a,b,c] [--round LABEL]
.\.venv\Scripts\python.exe examples\hot_potato_arena\textures\generate_arena_textures.py
.\.venv\Scripts\python.exe examples\hot_potato_arena\sync_scenario_outputs.py
.\.venv\Scripts\python.exe -m examples.hot_potato_arena.build_distribution --overwrite
```

The generator runs asserts A1–A21 (plus A4b/A4c) on every build — A19 skin
relief (analytic profile monotone on skirt and feather, peak grade ≤ 2.5 %,
every vertex on the profile, facet sagitta ≤ 0.02 m, top == 0.050, outer lip
≤ 2 mm, all 432 triangles face up), A20 quadrant seam collision step ≤ 2 mm
on the built mesh AND the re-parsed DAE plus the wall toe rings on the skin's
outer chord (108 vertices), A21 every plate inside the footprint fully on the
flat r 9–73.5 and 20 ± 2 mm proud with its rim on the skin; `--export`
writes only the named DAEs because the Collada exporter's timestamps make a
re-export never byte-identical (a frozen shape stays out of the export set;
the hashes manifest is the proof and A18 the guard). The scenario generator
reads the handoff (statics, obstacles, shapes, hashes) and the layout file
(cars, stacks, barrels, geyser sites) and emits the prefab, scenario JSON,
the generated Lua block and the thumbnail. The packer computes its member
list from the handoff's shape table plus the materials json's texture
references plus the four scenario files.

### 7.2 Static, lupa and clearance gates (82 tests)

```
.\.venv\Scripts\python.exe -m pytest tests\test_hot_potato_arena_package.py tests\test_hot_potato_arena_logic.py tests\test_hot_potato_arena_site_clearance.py -q
```

- `test_hot_potato_arena_package.py` — 20: outputs synchronized with the
  authoring files; handoff refusals (64-point cap, declared-convention
  mismatch); strict JSONL / uuid5 / namespaces; statics mirror the handoff
  and honour collision flags — every static "Visible Mesh Final", the four
  floors with `prebuildCollisionData "1"`, the handoff's `lod` blocks null,
  the five plates at z 100.05, no `forceDetail` family fields; vehicle
  census from the layout with every nose on the pad; emitters stock with
  wisps on / curtains off; scenario JSON contract; Lua generated block ==
  authoring; Lua contract (boot order, scale-1 pop, hook tolerance, MP
  guard, valve constants, no `_G`); LF + strict JSON; materials namespaced,
  level-scoped, groundtype ICE/SAND; no stock copies; derived manifest;
  deterministic stored archive + lock; refusal of an unexpected file and a
  CRLF member; art members pinned to the hashes manifest (round v3.2 and the
  floor digest `4ce0cdcb…`); checked-in lock == dist == the Hot Potato lock.
- `test_hot_potato_arena_logic.py` — 57 (lupa, skip silently without it):
  boot retry / order / snapshot-before-write; MP; refused boot fails closed;
  restart keeps the boot; every exit path hands back once; crash recovery;
  the tuner rules and the accepted edge; unwritable snapshot file; obstacle
  re-registration transitions and back-off; geyser cycles, phases, one pop
  per window as a velocity ADD, blind sites, bounded state; valve two-step
  decay, every round-exit path (three-way parametrised), stall-clock reset,
  watchdog on liveness with the steady-tick no-false-restore case, restore
  only over the valve's own step; missing runtime never raises.
- `test_hot_potato_arena_site_clearance.py` — 4 against the stock
  `gridmap_v2.zip` (skips without an install): both matrix conventions
  computed and shown to disagree by > 10 m on this site; nothing stock
  inside r ≤ 155 m under the measured convention; the nearest stock mesh is
  an interzone `s_gm_cube_4m` stack between 155 and 175 m; groundplane tiles
  under the arena sit at z = 100.
- `test_hot_potato_arena_live.py` — 1 `beamng_live` smoke (sentinel profile
  only): both zips lock-verified at install; the shipped scenario loaded
  from the game's own list; runtime registered at the first poll (part_count
  7); the boot calls read back; 42 obstacles registered; census 32/16/23;
  materials resolve; `forceDetail` read-back `-1` on 32/32; surfaces (spout
  throats 100.004, crests 105.498, the structure10 convention witnesses
  100.0 / 116.0; plaza and pool expectations are derived from the handoff's
  `plate_instance_lift_m` — plaza 100.05 ± 0.02, pool in [100.05, 100.10) on
  the v3.2 skin; the round-4 run measured 100.000 / +0.020 on the v3.1
  inlay); heading dot > 0.98; round
  live with `field == 6` and `props_excluded == 16`; a MOVING car popped
  with horizontal speed preserved within 10 %; restart +4 writes / +1 boot;
  Exit scenario → persisted settings byte-equal to the snapshot and the
  snapshot file gone; six far-field frames through the band metric,
  RECORDED not asserted; `log_issues == []`; seven-plus screenshots.

### 7.3 Live gates (the integration round)

The ladder is owned by the integration round and lives in
`tests/test_hot_potato_arena_gates_live.py` (sentinel profile, serial, one
owned BeamNG process at a time), separate from the package smoke above. What
follows is the PLAN as written before the round; §11 records what it
measured, including the two extra rungs the round added (G8 crest rams after
the magnet fix, G9 after the dodge fix) and the G10 still pending.

- **G1 site truth** — player-camera normal-exposure shots: bowl floor,
  mid-bank, glacis; halo readability (1.5 m ribbon above the 5.5 m crest);
  tethers with the halo off; the far-field floor from ~300 m on ≥ 3 boots
  (band metric expected clean, 1.2–1.8, now that the skin is drawn 50 mm
  over the groundplane); drive off the glacis foot at three bearings (no
  lip or void at the groundplane transition); r 75 and r 113 z-fight bands;
  the interzone cube stack at 162 m reads as distant set-dressing.
- **G2 surface** — crawl (1.1 m/s) and 2 m/s lines on the wall, both ramps,
  pools, salt (one braked SAND run), fillets; radial crossings of the skin
  feather (r 73.5–76, 1.90 %) and the inner skirt (r 6–9, 2.00 %) at crawl
  and 60 km/h; the r 88.5 tangential line
  across the 0.270 m ramp lip at 60 km/h (no launch, no rollover); "bank at
  r 86, bearing 45°, drift into the 60° spout" down the chute; the stall
  discriminator (AGENTS.md L1291–1294); a driven figure-eight replacing the
  33° assumption; crest ram runs at 60–110 km/h: exit, glacis landing, magnet
  engage, haul-back, no trap. Watch for the F-P1.10 self-drive anomaly.
- **G3 AI** — 3 minutes of chase/flee with zero pillar / tower / ramp / jamb
  collisions against the 42 registered obstacles (degrade ladder: 2 grinders
  or ring to r 30 → masher ring to r 52 → rings deleted only if the hook is
  refused); braked-hulk haul from outside a spout; release feel at the
  82.3 m line; classic spout-spam (< 25 % transfer-immunity uptime and a tag
  landing during a haul-back); hold-mode spout-spam (zero out-of-ring accrual,
  now by construction); magnet-orbit attempt (re-entry within 15 s per
  excursion; failure pulls `arena_magnet_g` 2.0 and re-runs).
- **G4 geysers** — per-site pop assertions at all three sites (≥ 4 m/s
  vertical, once per ON window, zero during OFF, horizontal speed preserved);
  AI entries through spouts during ON windows recover (degrade: 25 % duty or
  outbound-only pops).
- **G5 round** — the multi-vehicle Hot Potato live sequence ON the arena:
  `field == 6`, `props_excluded == 16`; boom → return flight; winner
  fireworks over the arch; a forced valve step and restore; Exit-scenario
  and crash-recovery hand-back.
- **G6 perf / culling** — 23 vehicles + geysers ON, 60 s frame-time log with
  a recorded floor (the probe measured 60.0 fps average, worst frame 22.4 ms,
  physics real-time factor 1.000 with no arena geometry, and one isolated
  2.04 s hitch in a second window); orbit the bowl at distance: every arc
  renders and collides, no seam popping, rim band continuous, fillet reads
  as wood; the feather reads as nothing from player height.
- **G7 the lifted skin (re-run on v3.2)** — the physics drop-test the tree
  cannot prove: a wheel at rest on the plaza reads z ≈ 100.05 (skin collision
  engaged under the `{_a290, nulldetail10}` tree, which has render evidence
  from the negative control but has never been BOOTED for collision), on
  the feather between 100.05 and 100.012, on the corridor / wall toe 100.012
  — never sinking to 100.0; then the G1 far-field bands and the G2 skin lines
  above. Fallback if the drop-test fails: `FLOOR_SKIN_STOCK_NODES = False`
  in `create_arena.py` and a re-export as a plain object like the other
  twelve shapes (which all collide).

## 8. Verified-facts ledger

Ids are kept from the round that opened them so every later citation stays
traceable: F1–F28 (design v1–v3), F29–F31 (v3.1 amendment), F-P/F-R/F-X
(probe round), F-GC (geometry critic), F-RC (runtime critic), F-SC (scenario
critic / scenario worker live). `spec.py` lines are the Hot Potato spec at
the time of reading; `L` references into AGENTS.md are stable section lines.

### 8.1 Design facts (F1–F31)

| # | Fact | Verified where |
| --- | --- | --- |
| F1 | Prefab TSStatics get collision at level load; runtime spawns need `be:reloadCollision()` and are invisible to `castRayStatic` | AGENTS.md L904–913 |
| F2 | Scenario shape: array JSON + `extensions`, JSONL prefab, uuid5 persistentIds | CCW files; `sync_scenario_outputs.py` |
| F3 / F4 | A prefab TSStatic may reference a stock DAE by path; a prefab BeamNGVehicle spawns by jbeam name | CCW prefab |
| F5 | Scenario GE Lua: emitter `setActive`; `applyClusterVelocityScaleAdd`; `requestReset(RESET_PHYSICS)`; onPreRender retry boot — **erratum (scenario r1 fix 1): the pop is scale 1; scale 0 is CCW's launch/stop form** (CCW scenario lua L594 launches from rest with 0, L731 stops with `0, 0, 0, 0`) | CCW lua; AGENTS.md L1271 |
| F6 | Site (850, −280): record-origin sweep clean to 170 m was wrong twice (v1 "208 m", v2 "219.3 m"; real nearest origin 178.7 m, structure4); with Prefab children expanded, a `s_gm_cube_4m` stack at ≈ 160.0 m; corrected again by the clearance gate under the measured matrix convention to **161.95 m** (F-SC2); the children carry `isRenderEnabled = "false"` in the source `.prefab` (964/964 in 44 files) and the Prefab renders and collides them; nearest walked DecalRoad NODE is an `aiPaths` spline at 170.0 m (zone_markings decal 184.2 m) | items.level.json + `.prefab` parse; `tests/test_hot_potato_arena_site_clearance.py` |
| F7 | Stock groundmodels ASPHALT 0.98/0.70, ICE 0.40/0.20, SAND 0.60/0.60 | gameengine.zip groundmodels.json; live read F-P1.8 |
| F8 | Surface → groundmodel binding is the lowercase Material field `groundtype` | `m_gm_ice` in the gridmap materials |
| F9 | Stock flat-ice DAE = 34 × 98 m plane (units cm) | parsed |
| F10 / F11 | Citybus wheelbase 7.45 m; D-Series wheelbase **2.98 m** (front −1.49, rear `ax2` +1.49) | jbeam nodes |
| F12 | Prop jbeams `cardboard_box`, `barrels`; AI cars covet/bx/etk800/barstow/bluebuck | vehicle zips |
| F13 | `hotPotatoSetOption` clamps via OPTION_RANGE; `arena_radius_m` {20, 500} live; `arena_magnet_g` {0.1, 3.0}; `arch_feet` handoff-only | spec.py L668–748 |
| F14 | Runtime provides the arena circle, conscription, return steering, halo, hoisted magnet + bead tether, dodge on `B.arch_feet`; OOB burn rejected on the ledger | hot_potato/DESIGN.md v2.6–v2.7.1, L981 |
| F15 | Drivable-surface laws: relief ±0.02 m, undersides to grade, slope-integrated crests, monotone-r sweep, collision ≤ visual, flared-portal fills | AGENTS.md L1109–1174, L1283–1300 |
| F16 | Prop spawn name `ericrolph_hot_potato` | mod tree |
| F17 | Stock banked turns are motorway-scale (145–540 m) — grounds only the decision to author the wall | round-1 DAE parse, not re-measured |
| F18 | Every successful `hotPotatoSetOption` does `saveOptions()`, a 3 s toast and `Sync.publishAll(true)`; on a BeamMP follower options are read-only | spec.py L4492–4515 |
| F19 | Halo: `drawTriSolid` cylinder at r = `arena_radius_m` from centre.z − 1 to + 7, 48 segments, alpha 22/255, live/boom frames only; tethers drawn even with the halo off | spec.py L1440–1470 |
| F20 | A car outside the circle cannot receive the potato | spec.py L2939–2947 |
| F21 | `camp_burn_multiplier` defaults 1.0 = off; taxes only a carrier below `camp_speed_kmh` 20 | spec.py L439–442, L3658–3668 |
| F22 | Magnet: member drafted when seen inside; well applied only at distance > `arena_radius_m`; released at 0.9 × (82.3 m) | spec.py L3390–3412 |
| F23 | Receiver grace ≥ `grace_seconds` 4.0 | spec.py L435–437 |
| F24 | gridmap_v2 `theTerrain` at (−1023.5, −1023.5, 50); the site's drive surface is the groundplane statics at z = 100.000 (F-P4.4) | items.level.json; probe P4 |
| F25 | Hold-mode accrual and crown were unconditional on position — fixed upstream (ask #2) | spec.py L3677–3683 at reading; v2.8 |
| F26 | `v26.DODGE_KEEPOUT = 6.5 -- foot half-side 2.06 + car half-width + margin` | spec.py L3263 at reading |
| F27 | `LAST` (served by `hotPotatoGetStats`) republishes every behaviour frame and FREEZES if the prop's behaviour stops — why the watchdog keys on prop liveness | spec.py L1875–1882 |
| F28 | Magnet hoist: well hangs 0.6 × horizontal range above the pad → constant 0.515 lift / 0.857 horizontal split at any dial (`lift = distance * 0.6`, spec.py L3341–3347) | hot_potato/DESIGN.md L1007–1020; code |
| F29 | v3's knots peak at 116.3 % at r 89.65 (independent Fritsch–Carlson, matches the critic and the DAE within 15 µm); crest at 5.5 gives 69.0 % at r 89.47; ripple 33.0 mm at 12 columns, 8.3 mm at 24 | v3.1 computation; geometry critique r1 |
| F30 | v3-built ramps were E–W strips at y ≈ −332 forming a 103 m barrier; pool 2 had 38/85 vertices under the west strip with 0.97–2.48 m of ramp above | geometry critique r1, measured on the DAEs |
| F31 | v3-built jamb fills were vertical, tallest 6.49 m at r 91.6, with the registered obstacle at the 0 m-tall nose | geometry critique r1 |

### 8.2 Probe facts (2026-09-01, sentinel profile, BeamNGpy 1.35.1 `-headless`)

| # | Fact |
| --- | --- |
| F-P4.1 | A prefab-record Dispenser bootstraps the runtime with no help: `registered = true` at the FIRST post-start poll, `part_count = 7` |
| F-P4.2 | Five prefab vehicles: roster exactly 5; `be:getPlayerVehicle(0)` is the `startFocus` record |
| F-P4.3 | A round runs from prefab spawns: `phase = "live"`, carrier = player, `field = 4` with three AI cars; `log_issues = []` |
| F-P4.4 | `castRayStatic((850, −280, 200), −Z)` → surface z = **100.000** exactly (re-measured at (874, −230)) |
| F-P4.5 | A prefab-scenario boot + round + teardown is under 4 minutes wall clock (later: a full smoke ≈ 43 s) |
| F-P1.1 | A `main.materials.json` under the level-INDEPENDENT `art/shapes/<id>/` root of a mod zip does NOT auto-load (both materials MISSING; an explicit `loadJsonMaterialsFile` resolves them) |
| F-P1.2 | Prefab mod-TSStatic collision exists at level load and is `castRayStatic`-visible: 100.050 on both plates, 100.000 on bare ground |
| F-P1.3 | A late material load does NOT rebind visuals: shapes imported before their materials stay NO-MATERIAL orange |
| F-P1.4 | Stock flat-ice sheet referenced by path with `scale (0.5, 0.8, 1.0)` loads, collides, and honours the scale: 17.0 × 78.4 m world box |
| F-P1.5 | Materials under `levels/gridmap_v2/art/shapes/<id>/` DO auto-load at level load — the shipping shape (CCW's too) |
| F-P1.6 | The tires report the mod plate as `ICE` (`wheels.wheels[*].contactMaterialID1` → `particles.getMaterialsParticlesTable()[id].name`); a material without `groundtype` binds ASPHALT |
| F-P1.7 | Braking from ≈ 11 m/s: ICE plate decel **1.97 / 2.00 m/s² (μ 0.200 / 0.204)**, ≈ 31.7 m to stop; control plate (no groundtype) **9.84 / 9.82 m/s² (μ 1.003 / 1.001)**, 4.7 m; bare groundplane 7.14 / 9.10 m/s²; stock ice sheet 1.83 m/s² |
| F-P1.8 | Engine groundmodels read live via `core_environment.groundModels[name].cdata`: 60 registered; F7's numbers confirmed |
| F-P1.9 | Under `set_deterministic(60)` one `step(1)` advances ≈ 0.0492 s of sim (≈ 3 physics steps) |
| F-P1.10 | **Anomaly, cause unidentified:** a probe car left with `brake = 1` on a low-μ surface re-accelerated 7.4–7.9 s later to a constant 20.19 m/s and drove 1.1–1.4 km; friction numbers were taken before onset |
| F-P1.11 | At the ICE plate's north end the REAR wheels read ASPHALT while the fronts read ICE (plate-edge triangle region); braking numbers unaffected |
| F-P1.12 | SAND on the authored salt plates binds by the same mechanism; not separately braked |
| F-R3.1 | 23 vehicles (player + 22 runtime spawns in 6.3 s); the Dispenser registered under load |
| F-R3.2 | 60 s at the full census with AI chase/flee: 3600 frames = **60.0 fps average (limiter cap), worst frame 22.4 ms, 0 frames > 33 ms, physics real-time factor 1.000** |
| F-R3.3 / F-R3.4 | Second 30 s window 54.1 fps with ONE 2.04 s hitch (cause unidentified; G6 keeps a per-frame log) |
| F-R3.5 / F-R3.6 | The 12 → 8 → 4 prop degrade ladder was never needed; numbers are `-headless` (no window), the physics factor is the headless-independent result |
| F-X.1–3 | The Dispenser bootstraps both from a prefab record and a runtime spawn; no probe produced a runtime `|E|` line; every install was removed at cleanup |

### 8.3 Geometry critic verifications (F-GC)

| # | Round | Verified |
| --- | --- | --- |
| F-GC1 | r1 | Every DAE parsed independently: radial relief ≤ 14.2 mm, monotone, seams 0.000 mm (37/37 verts at every wall seam under the handoff rotations), 118/118 deck-top boundary vertices backed, ramp 10.96 % then; plates 0.0200 m, trim 18.0 mm; 13 point features within 1 cm; throat 36.0 m at r 76, 43.9 m at the crest |
| F-GC2 | r1 | The bank peak was 116.3 % at r 89.65 (≥ 100 % from r 89.0 to 90.3); mesh crest 6.497 with no station at 91.4; tangential ripple 31 mm at r 88.5 / 55 mm at the peak, unasserted |
| F-GC3 | r2 | Under rows-are-local-axes: spouts at 60.00° / 240.00°, salt at 90.00° / 270.00°, pools 0.0° off tangential; `handle_ramp_w` an exact x-mirror (0 vertices differ, 540/540 top and 180/180 flank triangles facing right) |
| F-GC4 | r2 | Ramp toe +4.0 mm over the wall MESH at all 7 rows; grade 11.98/11.05/9.95/7.47/6.02/4.33/0.81 % by row, monotone, max facet change 3.29 pts; outer face 0.004 → 0.270 m; batter rise/run 1.000 at 52 stations, 44.0 → 54.5 m; A10 raster with the bank > 0.3 m blocked: one region, 0 unreachable; own steep-face sweep: 0 uncovered triangles |
| F-GC5 | r2 | Two corridor-floor triangles at r 76.32 faced DOWN (a bow-tie quad after the chord foot); fixed by A4b (per-triangle winding after triangulation, sliver < 1e-4 m² fails the build) |
| F-GC6 | r3 | Fillet: 8/8 shared vertices with the ramp at 0.000 mm, flush with the deck (z 4.000 at x 7), 18 grade vertices, 4 tuck vertices at |x| 6.70 / z 3.996, 64 wall tris facing the free side, 0 down, 0 slivers; west == mirror(east) |
| F-GC7 | r3 | Stock LOD convention in `gridmap_v2.zip`: 205 DAEs, 197 with `base00`/`start01`, 115 with `_a<N>` nodes (308), 91 with `nulldetail` — 90 under `base00` as a sibling of `start01`, 1 at the scene root, 0 under `start01`; `s_gm_groundplane_64m` = `base00 → {collision-1, nulldetail10, start01 → {_a150, Colmesh, _a15}}` |
| F-GC8 | r3 | Far floor detail = near mesh + 0.050 m exactly, 432 + 432 tris; switch ≈ 189 m under both distance readings at 1080p/65° (later corrected: ~126 m at the smoke's 720p; vanish ~520 m / ~780 m at 720p / 1080p — the 5.5 km "cull" was withdrawn) |
| F-GC9 | r3 | Name-plate uphill skirt: 2 triangles wound inverted (normal (0, −0.20, −0.98)) — fixed by A4c |
| F-GC10 | v3.1 | Errata pass changed exactly three DAEs (floor `7a12c129…` → `8c073005…`, trim `1125dc28…` → `195708a6…`, fillet `5e76c191…` → `3a291f03…`); 10 DAEs, 18 textures and the materials json hash-equal; the critic's r3 script has a chain-ordering bug (IndexError at L83 on the round-3 DAEs too) — adapted copy documented, original untouched |
| F-GC11 | v3.2 | Integration gate G1 measured the far-field banding persisting on 2 of 3 boots of the shipped v3.1 package (band metric 2.63–2.89 / 1.18–1.24 / 4.06–4.75 across three boots; clean 1.2–1.8, line 2.2) and the negative control (F-SC13) had shown the far detail never engages, so the design owner lifted the skin to a DRIVEN, COLLIDING +50 mm surface: feather r 73.5 → 76.0 (peak grade 1.90 %, mean 1.52 %), inner skirt r 6.0 → 9.0 (2.00 %), outer lip 0.000 mm on the 12 mm datum, vertex-coincident with both wall shapes' r 76 toe rings (108 vertices, step 0.000 mm on the built mesh AND the re-parsed DAE), facet sagitta 1.25 mm, vertices within 0.06 µm of the profile; 432 tris single detail; plates re-based by instance z 100.0 → 100.05 (5/5 tops +20.0 mm, rims +0.0 mm; pools r 61–71 are 2.5 m short of the feather, salt 3.0 m clear of the skirt); wheel-track spread 32.0 mm on the skirt / 30.4 mm on the feather (a ramp, not relief). Only `floor_skin_quadrant.dae` changed: `8c073005…` (110,715 B) → `4ce0cdcb…` (64,403 B); manifest round v3.2, baseline v3.1; the v3.1 handoff kept beside as `…handoff.v3.1.json` |

### 8.4 Runtime critic verifications (F-RC)

| # | Round | Verified |
| --- | --- | --- |
| F-RC1 | r1 | `lua_kit.generate_runtime(spec)` == the shipped `runtime.lua` byte for byte; the baseline regenerates to `c2addf9d…`; 45/45 members, only `runtime.lua` moved; 185 top-level locals (ceiling 200) |
| F-RC2 | r1 | Dodge probes: side-step sign unchanged; nearest-along beats a far larger post and a decoy; a post behind the car or at the exact keep-out radius never dodges; probe B along-span divergence `(−30.8, −9.5)` → `(14.8, −9.5)` |
| F-RC3 | r1 | Registration hole: a lone dict, a holed list and a keyed table were accepted as a clear (`True`, count 0/1/1, 0 warnings); 65 entries truncated with `True` |
| F-RC4 | r1 | The lupa harness's `tick()` crash guard had been dead since the file's first commit (stub `jsonEncode = tostring`): ten throwing frames, zero assertions |
| F-RC5 | r2 | All refusal shapes now `False`, set intact, one warning each, zero E events; exactly 64 → `True`; the crash guard raises on a throwing frame; 76 logic + sync green under it |
| F-RC6 | r3 | Engine reuses the vehicle object on replace (`core/vehicles.lua` L1699–1765, `vehsToReuse`, `onVehicleReplaced` unsubscribed by lua_kit); `onSubjectGone` fires only `if wasTracked` (lua_kit L826–840); a box replaced in place by a car stayed `props_excluded 1` and never received |
| F-RC7 | r3 | Stock `unicycle` ships `Type = "Prop"`; traffic special-cases it to `player` (`traffic/vehicle.lua` L31) |
| F-RC8 | r4 | Cache `{model, prop}` re-read each pass reclassifies in place and after destroy/reuse; the filter is a net WIN at 23 vehicles: 0.174 ms/frame vs 0.193 baseline (downstream sweeps walk 7 entries, not 23) |
| F-RC9 | r4 | A carrier replaced in place by a box was crowned LAST CAR STANDING with a `round_won` in the persistent ledger |
| F-RC10 | r5 | The scenery-carrier fold runs before the pass sweep (`sweepForPass` L3917, `detonate` L3934, last-car-standing L3908–3919 all downstream); trailer, boom-phase, mirror and hoarder attacks all held; stock census Prop 67 / Car 28 / Trailer 13 / Truck 10 / Heavy Machinery 2 / Traffic 1 / Debug 1 (`containerTrailer.zip` is the only mixed-case name — the worker's lowercased path missed exactly it) |

### 8.5 Scenario critic and live verifications (F-SC)

| # | Round | Verified |
| --- | --- | --- |
| F-SC1 | r1 | **`rotationMatrix` rows are the object's local axes** (the transpose of the textbook matrix) — three witnesses: structure10 (`[0,−1,0, 1,0,0, 0,0,1]`) covers (640, −252) only under the transposed reading and the live ray read z 116.0 there / 100.0 at the textbook footprint; CCW's spotlight basis writes rows = (right, forward, up); the arena's own spouts and headings under derived matrices (under textbook matrices run 1 mirrored every arc: bearing 60° read a bare arc_45 crest, 300° read 106.518 = crest + the trim ring's rivet) |
| F-SC2 | r1 | Under the measured convention the nearest stock mesh is structure4's cube stack at **161.95 m** (corner-origin cube); under the textbook convention structure10 would sit at **132 m**, inside the apron |
| F-SC3 | r1 | A restart cost 8 option calls / 3 boots (`set_option` 4 → 12 measured live); `stop()` unloads the scenario extension, `tickRestart` reloads it, the fresh instance boots, then `onScenarioRestarted` cleared `booted` and it booted again |
| F-SC4 | r1 | The pop at scale 0 is a velocity REPLACE (AGENTS.md L1271; CCW L731 stops with the same form); a moving car crossing the strip would be stopped dead then lofted |
| F-SC5 | r1 | With serial 44 the runtime reported `field = 22` (all 16 props were subjects) |
| F-SC6 | r2 | Pop is an add: moving car 6.043 → 6.035 m/s horizontal, +5.34 m/s vertical in one frame; restart = +4 writes / +1 boot; wisps `active: true` ×3, curtains `false` ×13 |
| F-SC7 | r2 | The pause menu's **"Exit scenario"** (`ui/pause/features/homeRail.lua` L433) calls `scenario_scenarios.stop()`, which unloads the scenario extension (`scenarios.lua` L467–486) BEFORE any `clientEndMission` — measured: options and the settings file left at the arena's values, the GE global leaked, 0 `mission_ended` restores |
| F-SC8 | r2 | Bowl-floor streaks are slivers of the light groundplane winning the depth test against the 12 mm skin 250–320 m from the camera: 1201 bright pixels in one shipped frame, 0–6 in the rest, 0 with the skin raised +0.05 m, ~150 at +0.30 m (its own edge), 25,661 with the skin hidden; present in round 1's frames too; clean at every player-height camera; "quadrant seams" not reproduced in 12 frames |
| F-SC9 | r3 | `getField('forceDetail', 0)` on the shipped records read garbage (12589; −1073729235 / 1090531629 / −1509936851 / −1258278611 across the four floors in boot 2) while stock TSStatics read `-1` and a runtime `setField` reads back exactly; the JSON prefab loader leaves the string-typed S32 slot uninitialised; stock gridmap_v2 (8,993 records) and CCW emit none of `forceDetail` / `meshCulling` / `originSort` |
| F-SC10 | r3 | Band metric (mean row gradient / mean column gradient in the plaza disc r 140 at (640, 372)): unbanded floors 1.2–1.8, banded 3–5.7; the same zip scored 5.7 and 1.8 at the same far-field camera in consecutive boots; runtime `setField('forceDetail')` to 0/1/2/−1 changed nothing |
| F-SC11 | r3 | The hand-back rule wrote the snapshot over a mid-mission tuner change (live: `ai_enabled` true written back over the tuner's false on both the restart and Exit paths) |
| F-SC12 | r4 | Records field-less; `forceDetail` read-back `-1` on 32/32 in two independent boots; the hashes gate refused the round-3 rebuild, a one-byte texture flip and the control zip, and passed the shipped zip |
| F-SC13 | r4 | **Negative control:** the shipped package with the floor DAE's `_a70` node removed (details {a290, nulldetail10}) still renders the NEAR mesh at 300 m — plaza-disc median 95–119 against 148 with the skins hidden (150 m: 92–98; 100 m: 102–113; overview 245 m: 89–105) — so six clean far-field frames (1.407–1.424) are not evidence that the far detail engages |
| F-SC14 | r5 | Only the scenario Lua changed between the round-4 and round-5 dists (two hunks, +18/−0); 81 gates; dist `2f78e1b7…` rebuilds byte-identical; the E1/E2 hand-back edges and E4 valve case reproduce |
| F-SC15 | r6 | The v3.2 handoff regenerated with NO generator or Lua change: four floor records "Visible Mesh Final" / `prebuildCollisionData "1"`, five plate records at z 100.05, the null `lod` blocks skipped by the generator's `isinstance(lod, dict)` check; 72 records unchanged in count; dist re-cut to `c37754b6…`, 36 members, 8,137,356 B, `depends_on` serial 47; 81 gates (20 + 57 + 4); no live boot (the simulator was held for the integration round — G7 covers the skin) |

## 9. Round ledger

### 9.1 Design (worker design v1 → v3, design owner v3.1)

| Round | Verdict | What the critic found | What changed | The number that closed it |
| --- | --- | --- | --- | --- |
| r1 (v1) | NOT WOWED (fun 6.5, looping 7, corners 9, completeness 8, honesty 8.5, buildability 8, identity 9.5) | Fix 1 CRITICAL: the crest curl's own coordinates leaned OUTWARD and contradicted the monotone-r law it cited. Fix 2 CRITICAL: the 30 s decay walk was wired to `hotPotatoSetOption`, which saves/toasts/syncs per call and can leave a persisted radius dirty. Fix 3 HIGH: grade-level spouts + F20 = a transfer-immunity exploit never confronted. Fix 4 MED: camp burn "left on by the boot" was false (default 1.0 = off). Fix 5 MED: four pillars 68 m apart is not a slalom. Fix 6: halo/magnet oversold (only ~0.5 m of halo above a 6.5 m crest). Fix 7: wheelbase 3.05 → 2.98; terrain unstated. Fix 8: one pinch; one 232 m DAE with no precedent | v2: curl deleted (magnet is the return); coarse two-step decay with boot self-heal; spout geysers + emergent-cost argument + a G3 sub-test; camp-burn layer deleted; grinders + centre stacks under a 35 m / 14 m two-tier doctrine; halo stated from F19; three geysers; export split into shapes | 7 of 8 closed in r2's audit; F18 (side effects) and F21 (camp burn) entered the ledger |
| r2 (v2) | NOT WOWED, narrowly (honesty 7.5) | Fix A HIGH: "a diver cannot score" is false in hoarder/protect — accrual and crown unconditional at spec L3677–3683. Fix B MED: a tangential exit is an orbit at √(a·r) ≈ 34 m/s (flat estimate). Fix C LOW-MED: F6 wrong a second time (real nearest origin 178.7 m; Prefab children never expanded). Fix D: foot half-side 2.06 not 1.2; frozen-stats watchdog; dodge degrade ladder; tri column did not sum (~15,760 vs ~14,600) | v3: hold-mode hole dissected per mode and routed upstream as ask #2; §4.4 with the hoist split (31.8 m/s) and the 1.95 g ceiling; site re-swept with children expanded → 160.0 m, clean radius shrunk, 155 m assert; grinder↔foot 15.3/14.5 m; watchdog; ladder; column sums (15,760; 11 shapes / 31 records) | the worker reported a number WORSE for its own design (160 m) and asserted it |
| r3 (v3) | UTTERLY WOWED (looping 9, honesty 9) | Five binding errata: cubes are not "render-disabled" (later reversed — they ARE `isRenderEnabled=false` in the source, scenario r1); nearest walked road node is aiPaths at 170.0 m; the assert must compose Prefab rotation; the scoring gate needs its own fetch; the watchdog must key on liveness, not payload delta | carried into the build rounds; all five landed (clearance test composes rotation; gate fetches; watchdog on liveness with a steady-tick case) | F25–F28 verified at their lines, `lift = distance * 0.6` traced to spec L3341–3347 |
| v3.1 amendment (design owner, after geometry r1) | — | Root cause owned: §3.4 under-specified the ramp footprint and §3.5 put pool 2 at the same radius; §3.2's "~57 %" was fiction from its own knots (F29: 116.3 %) | Ramps → tangential arcs r 80–88 (toes 149°/211°, ≤ 12 %); pool 2 → 228°; stacks → 20°/200°; obstacles 16 → 28 (built 42 to satisfy A13); crest 6.5 → 5.5, `MAX_GRADE` 0.70; jambs battered 1:1 with mid-face points; stations 76/88.5/91.4/113 mandatory; 24 columns where grade > 0.35; rivets to a sixth texture family; budgets re-summed to ~18,360; asserts A9–A15 | built peak 69.0 % at r 89.47 |
| §6.3 addendum (2026-09-02, after scenario r4) | — | The accepted hand-back edge; the far-field LOD not proven | recorded in §5.2 and §10 | — |

### 9.2 Geometry (`blender/create_arena.py`)

| Round | Verdict | What the critic found | What changed | The number that closed it |
| --- | --- | --- | --- | --- |
| r1 | NOT WOWED (law 7, fidelity 5, look 4, drive 4, asserts 6) | Pool 2 buried under the west ramp (38/85 verts, 0.97–2.48 m of wood above); ramps + deck = a 103 m barrier with two pockets, ramp faces unregistered; the lip is 116.3 % at r 89.65 while the contract said ~57 %; ripple 55 mm unasserted; no crest station (6.497); jambs 6.49 m vertical cliffs with the obstacle at the 0 m nose; rivets sub-pixel, plate blank, wood contour-banded | v3.1 amendment; asserts A9–A15 | — |
| r2 | NOT WOWED, narrowly (9 / 8 / 7 / 7 / 8) | All seven r1 fixes closed and reproduced (toe +4.0 mm, 11.98 % monotone, batter 1:1 ×52, crest 5.5000, ripple 16.4 mm). Remaining: each ramp merge a 90° inside corner (13/16 blocked, A10 cannot see it); 2 down-facing floor triangles; rim steel on the chutes; salt trimmed ±36° unilaterally; the 0.270 m lip needs a G2 line | r3: quarter-round fillets (13th shape), A4b per-triangle winding, matte chutes, salt ±45° with A9 groundtype-aware (ICE 5.0 m / SAND 1.5 m), floor-skin LOD nodes, wood/stave/rim-band look fixes (the bright glacis line root-caused to UV bleed at V = 0.5) | junctions 173.9° / 168.1° / 175°; 0 down-facing |
| r3 | UTTERLY WOWED (9.5 / 9.5 / 8.5 / 9 / 9) | Four binding errata: `nulldetail10` parented under `start01` (stock: 90/91 under `base00`); 2 inverted skirt triangles; no hash manifest per round; plank rows break on the fillet round | v3.1 errata pass: `--export floor_skin_quadrant,trim_ring,merge_fillet`; A4c near-carrier faces up; A17 node tree == authored; A18 kept DAEs' tri count == the build; `authoring/*.hashes.json` per build with a baseline diff; fillet round UVs by arc length (a texture-mirror line at one tangent junction is unavoidable and recorded) | exactly three DAEs changed; 10 hash-equal; 13 / 32 / 42; 18,288 tris |
| v3.8 (design owner, 2026-09-02) | design change, **the handle DAE's first movement since round 2** | v3.7's A26 found the tuck strip standing **+4.741 mm proud** of the bank at mid-facet — inside the relief cap, so cosmetic, but a z-fight/sliver risk visible at grazing angles | diagnosis before method: the cause was **a single chord spanning the bank's slope break at wall station 88.875** (0.0239 m/step inboard, 0.0273 outboard), not an insufficient rebate — so deepening the rebate could only shrink the sagitta, never remove it. Option (a), matching the bank's radial tessellation, was **built and measured (+0.646 mm)** and still crossed, because the deck edge is pinned at exactly 4.000 with 0.6 mm of headroom. Option (b) shipped: **the skirt DESCENDS 50 mm** instead of climbing, so it is under the bank *by construction*, independent of how either surface facets. The A26 check now walks the **built triangles** and barycentrically samples them, one-sided (a hidden element's depth is harmless; only the proud side is capped) | **+4.741 → −2.427 mm, strictly below, 549 samples across 22 built triangles**; skirt vertices −348 mm one-sided; A26 still passes all 14 junctions, worst 4.001 mm (the ramp toes' authored lift), `handle_deck_rear → bank` unchanged at 0.002 mm. Handle DAE `3dac6cd3…` → **`88cbb1c5…`** (234,333 → 234,351 B, **2022 tris both sides**, 12 vertices moved), now pinned as a named exception in the art gate so any further movement fails loudly |
| v3.7 (design owner, 2026-09-02) | **a RETRACTION, and the assert that came out of it** | v3.6 reported the deck rear standing **145 mm** proud of the bank at mid-span — "a straight edge against a circular lip", 7× the relief cap, pre-existing since round 2 | **the finding was wrong and no geometry changed.** The generator has always authored that edge on the r 88.5 arc (`end_y(x) = −√(HANDLE_END_R² − x²)`, and `build_handle`'s own docstring says "curved end edge flush on the bank arc at the 4.0 knot"); v3.6's audit had **modelled it as a straight chord** and measured a standoff from an edge the generator does not build. Measured on the shipped DAE: all 12 vertices at r 88.5000, relief **0.002 mm**. The round's product is therefore an assert, not a fix: **A26, relief ACROSS shape-to-shape junctions** — a class every earlier check missed because they all ran *within* a shape | 14 capped junctions, all inside ±20 mm; the handle kept `3dac6cd3…`. A first draft of A26 asserted whole ramp bodies and fired at 3,510 mm — the assert catching a bad definition of "junction" before it shipped |
| v3.6 (design owner, 2026-09-02) | design change, handoff-only | G13: the 14 m handle nose carried only its two end corners, leaving a **7.0 m** uncovered half-span where the anti-pin reflex could not arm (§11.5.6) | the nose gains **four interior sample points at 2.8 m pitch**, worst gap **7.00 → 1.40 m**; the registry goes **42 → 46**. The method changed with it: **audit by SOLID FACE, not by point class** — A25 now walks every face and fails the build if one marked covered exceeds the arming half-span, which is itself **derived** (1.73 m at the 2.18 m minimum reach → pitch ≤ 3.45 m) rather than chosen, so a future reach change re-derives it instead of stranding a magic number | G14 echoed 46/46 with `rp ≤ r` on every one; **G13's own pin replays from gap +1.471 m to −0.628 m**. The self-critique on the record: v3.5's caveat "covered the classes I had already thought about" — it measured spacing for the 16 points classed `face` and silently omitted a 14 m wall classed `corner` |
| v3.5 (design owner, 2026-09-02) | design change, **handoff-only — no DAE re-exported** (`exported_this_build` is empty) | D-8: the anti-pin reflex armed on the keep-out radius, a flat 9.4 m disc that made it shove cars in open ground and still miss real pins | every obstacle point gains a **measured physical radius `rp`** — the post's real solid extent, distinct from its keep-out `r` — so a reflex can arm on what the car can actually touch. Census `rp` 0.1 ×24 (8 corners + 16 faces, the contract floor; measured 0.0), 1.2 ×8 (mashers, jamb-outer batter), 1.5 ×4 (grinders), 2.121 ×2 (geyser towers), 2.321 ×4 (jamb-mid batter). New assert **A24**; the honest caveat published with it named a **6.25 m worst uncovered half-span on the flanks** | G13 echoed all **42** back with `r` and `rp` equal to the digit and **0 entries with `rp > r`**; the arming disc fell from 9.4 m to **3.13–5.35 m**. The caveat did NOT cover the handle nose, because each of its endpoints really is a corner — §11.5.7 |
| v3.4 (design owner, 2026-09-02) | design change, aimed by the final critic's evidence | v3.3 disarmed shadow casting on the two FLOOR materials and deliberately left `cast_iron_matte` — the walls and **the glacis** — casting, and the glacis is exactly where the 150 m stripes are (§11.5.1) | the wall shapes' glacis band gets its own material copy **`cast_iron_glacis`** with `castShadows: false`, on the same pattern v3.3 used for the skin: materials 8 → **9**, the disabled set now `cast_iron` + `cast_iron_skin` + `cast_iron_glacis`, and `cast_iron_matte` still casts for the bank, batter jambs and rim. A22 and the scenario-side mirror both derive their expected set from the handoff, so they moved with it | two DAEs re-exported for the new material symbol — `wall_arc_45` `c587f18f…` → `3af9f916…` (139,161 → 141,611 B) and `wall_arc_spout` `989b319d…` → `cb0bc02d…` (142,979 → 145,437 B), **tri counts unchanged at 960 / 1,072**; materials json `c507ec48…` → `70de26ae…` (8,899 B); 11 of 13 DAEs and all 18 textures byte-identical; 13 shapes / 32 instances / 42 obstacles / 18,288 tris all unchanged. **It did NOT remove the 150 m glacis stripes** (§11.5.1): G12 measured every post-fix boot at the pre-fix *banded* level, and the mechanism explains why — a non-casting surface still RECEIVES, and the remaining caster over that band is `cast_iron_matte`, the bank, left casting on purpose. Correct work aimed at the wrong half of the mechanism; the untried next step is the same flag on the bank |
| v3.3 (design owner, 2026-09-02) | design change, not a critic round | G7.1 re-diagnosed the surviving stripes: the skin is demonstrably DRAWN on the banded boot (plaza medians 90.8–101.9 against a skins-hidden 145.5), so the artifact is **self-shadow acne decided per boot by the cascade fit**, not a depth fight | the floor skin stops CASTING shadows, at material level. The glossy `cast_iron` is floor-only, but the matte was **shared with both wall shapes** whose bank, batter jambs and rim throw real shadows onto the plaza — so the skin got its own identical copy `cast_iron_skin` and `castShadows: false` went on those two only; `cast_iron_matte` still casts. Materials 7 → 8, texture families still 6. **New assert A22**, read back from the WRITTEN materials json: the disabled set equals the skin's own material set exactly, every other material omits the key, and the wall matte must still cast. Object-level control was rejected on evidence — 0 of gridmap_v2's 7,167 stock TSStatic records carry any shadow field — which also sidesteps the uninitialised-S32 trap by adding no record field at all; and `castShadows` is written only when false (81/81 stock uses are false; absent means casts) | two members moved: floor DAE `4ce0cdcb…` → `1ca6b37e…` (64,396 B, material-symbol rename only — 432 tris and the node tree unchanged) and the materials json `b584e1d4…` → `c507ec48…` (7,890 B). All 12 other DAEs and all 18 textures byte-identical; A19–A21 reproduce v3.2 to the digit. **The fix was shipped unbooted** — whether it removes the banding was left to a G7.1 re-run, and §11.5.1 now records that it did not, and that the metric was pointed at the wrong region anyway |
| v3.2 (design owner, 2026-09-02) | design change, not a critic round | G1 found the 12 mm no-collision inlay depth-fighting the groundplane at 300 m on 2 of 3 boots (2.63–2.89 / 1.18–1.24 / 4.06–4.75) and the negative control had proved the `_a70` far detail never engages; +50 mm was the measured fight-free separation | the skin becomes a driven, colliding +50 mm surface: feather r 73.5 → 76 (1.90 %), skirt r 6 → 9 (2.00 %), 0.000 mm lip on the datum, `_a70` and every LOD number dropped, plates re-based via instance z 100.05, asserts A19–A21; `--export floor_skin_quadrant --round v3.2 --baseline …hashes.v3.1.json`; ledger entries #34–#39 (supersedes the medallion-law inlay for THIS skin and the withdrawn switch/cull figures; `FLOOR_SKIN_STOCK_NODES` is the one-constant fallback) | one DAE changed (`4ce0cdcb…`, 64,403 B, 432 tris); A1–A18 unchanged to the digit; 13 / 32 / 42; 18,288 tris |

### 9.3 Runtime (Hot Potato v2.8, `examples/giant_props/hot_potato/spec.py`; the re-cut law proven each time — 45/45 members, only `runtime.lua` moved)

| Round | Serial (runtime.lua) | Verdict | What the critic found | What changed |
| --- | --- | --- | --- | --- |
| r1 | 42 → 43 (`c2addf9d…` → `7fc49006…`) | NOT WOWED | HIGH: non-dense tables accepted as a silent clear. MED: the 64 cap truncated with `true`. MED: "with two feet never mattered" was false (probe B). MED: the harness crash guard was dead. LOW: pcall note; z ignored undocumented | asks #1 and #2 landed; 71 lupa |
| r2 | 43 → 44 (`7fc49006…` → `cb43403e…`, 2026-09-01T15:54:33, zip `ba0bc013…`, 57,698,867 B) | UTTERLY WOWED | — | `pairs`-vs-`ipairs` refusal; 65th entry refuses; along-span gate pinned; STUBS `jsonEncode` renders records so the guard is live; 72 lupa, 551 combined |
| r3 | 44 → 45 (`cb43403e…` → `24db22d7…`, 16:11:11, zip `9539e78f…`, 57,702,253 B) | NOT WOWED | HIGH: `b.propKind` stale under in-place replace and destroy/reuse — a real car failed closed. MED: the on-foot player excluded undocumented. LOW: trailers; wording (`getJBeamFilename`) | ask #3 landed: Prop-only exclusion, fail-open, `roster(state, includeProps)`; 75 lupa |
| r4 | 45 → 46 (`24db22d7…` → `4a136fd9…`, 16:23:13, zip `c034559a…`, 57,703,603 B) | NOT WOWED | MED: a carrier that becomes scenery is crowned last car standing. LOW: trailer census 13, not 12 | `{model, prop}` cache re-read every pass; `unicycle` a subject; `SCENERY_TYPES = {prop, trailer}`; 78 lupa |
| r5 | 46 → 47 (`4a136fd9…` → `2e24400d…`, 18:52:10, zip `a4bde9d3…`, 57,704,315 B, 45 members) | UTTERLY WOWED | — | scenery-carrier fold before the pass sweep; census 13 with its cause; 80 lupa, 559 combined; do-not-regress list of ten items |

### 9.4 Scenario package (`examples/hot_potato_arena/`)

| Round | Dist (sha, members, bytes) → depends_on | Gates | Verdict | What the critic found | What changed |
| --- | --- | --- | --- | --- | --- |
| r1 | `89bf5424…`, 31, 6,363,518 → serial 44 | 17 + 25 + 4 + 1 | NOT WOWED | HIGH: pop at scale 0 is a velocity REPLACE. HIGH: restart cost 8 writes (12 measured). HIGH: three booleans left persisted after the mission. HIGH: `field = 22` — the lock chained to a runtime without the filter. MED: pops with zero emitters resolved; no OFF tell in the spouts. MED: no re-registration after a runtime reload. MED: spawns/props/sites were generator constants. LOW: a test enshrined a re-boot after mission end; a refused decay spent a restore; strips wider than the steam. Adjudicated: the matrix convention (three witnesses), `isRenderEnabled` (worker right), R-1 severity | the load-bearing discovery: every matrix derived from the authored angle in the engine's convention; clearance pinned to the same constant |
| r2 | `0a9bc873…`, 35, 8,289,169 → serial 47 | 19 + 41 + 4 + 1 | NOT WOWED | HIGH: "Exit scenario" unloads before `clientEndMission`; the GE global leaked and was reused stale. MED: a crash leaves three booleans dirty. LOW: a refusing hook nagged every 5 s. Streaks diagnosed as a depth fight and routed to geometry | scale-1 pop (live-measured); restart keeps `booted`; snapshot + mission-end hand-back; role marker field; blind sites never pop, wisps on; three re-registration transitions; `authoring/*.layout.json`; `ended` latch; geometry v2 handoff (mirror ramp, 42 obstacles, crest 5.5) |
| r3 | `a58a4aa3…`, 36, 8,183,556 → serial 47 | 19 + 48 + 4 + 1 | NOT WOWED | HIGH: `forceDetail` uninitialised on every shipped static; the LOD claim rested on one frame of a phenomenon that flickers. MED: the hand-back rule writes over a mid-mission tuner change. LOW: `snapshot_file_written` lies on a `false` return; back-off cadence wording | hand-back on `onExtensionUnloaded`; GE global deleted; disk-backed snapshot written before the first write; exponential back-off; geometry v3 (fillet, LOD block) |
| r4 | `fd716b49…`, 36, 8,182,602 → serial 47 | 20 + 53 + 4 + 1 | NOT WOWED, narrowly | MED: six clean far-field frames are not a witness that the far detail engages (the negative control renders the near mesh at 300 m). LOW: the accepted hand-back edge undocumented. LOW: the valve's restore writes 91.4 over a tuner radius | `forceDetail` / `meshCulling` / `originSort` dropped, read-back `-1` ×32; hand back only `current ≠ snapshot AND current == arena value`; honest snapshot flag; back-off pinned at 7 calls / 300 s; hashes gate; geometry v3.1 errata DAEs consumed |
| r5 | `2f78e1b7…`, 36, 8,183,551 → serial 47 | 20 + 57 + 4 (+ 1 live, not re-run) | UTTERLY WOWED | one open item, owned by geometry (§10) | LOD claim withdrawn in place, band ratio recorded not asserted; the edge documented and gated; `restoreRadius` only over the valve's own step |
| r10 | `cfafe4fc…`, 36, 8,146,038 → serial 55 | 20 + 57 + 4 | regeneration, no critic verdict | — | all three geometry rounds (v3.6 nose points, v3.7's assert-only retraction, v3.8's descending tuck skirt) folded into **one** re-cut, with **exactly one member moved** — `handle` — and the shipped Lua carrying **46** obstacle rows. 81 gates green |
| r9 | `0adb6cc2…`, 36, 8,145,720 → serial 55 | 20 + 57 + 4 | regeneration, no critic verdict | — | geometry v3.5's `rp` passed through: the 42 obstacle points carry a measured physical radius beside the dodge keep-out, and the registration payload is now exactly `{x, y, r, rp}`. `rp_kind` is authoring metadata and **never ships** (a gate asserts no `rp_kind =` field). A new static gate catches a bad `rp` before a boot, because the runtime refuses the WHOLE registration if any `rp` is non-finite, below 0.1, or larger than its own `r` |
| r8 | `d0e2b325…`, 36, 8,144,777 → serial 54 | 20 + 57 + 4 | regeneration, no critic verdict | — | the **fifth boot call**: the runtime's out-of-bounds penalty ships at 1.0 = OFF, so the arena must switch it on. `BOOT_CALLS` gains `{"oob_burn_multiplier", 3.0}` in fifth place — after the magnet, the other boundary mechanism — with the self-heal radius still first; `BOOT_OPTION_KEYS` gains the key so the snapshot and hand-back cover it like the other four. Read from the shipped runtime before relying on it: the option clamps to {1, 5} and combines with camp burn through `max()`, so 3.0 is inside the clamp. Folded into ONE re-cut with geometry v3.4, so the archive bytes moved this round |
| r7 | `91f05bbc…`, 36, 8,138,378 → serial 47, then re-cut to 48 / 50 / 51 / 52 | 20 + 57 + 4 | regeneration, no critic verdict | — | geometry v3.3 consumed: **no prefab record changed** (object-level shadow control was ruled out — 0 of 7,167 stock TSStatic records carry a shadow field), so the generated prefab, scenario json, Lua and thumbnail came out byte-identical and this round is a re-cut plus two gate pins. `test_dist_art_members…` moved v3.2 → v3.3 with the floor prefix `1ca6b37e` and a new materials-sha pin `c507ec48`; `test_materials_are_namespaced…` gained the shadow assert, derived from the handoff's `floor_skin.shadows.disabled_materials` so it cannot drift — the scenario-side mirror of geometry's A22. Then five lock-only re-cuts as the runtime advanced |
| r6 | `c37754b6…`, 36, 8,137,356 → serial 47 | 20 + 57 + 4 (+ 1 live, not run — G7) | regeneration, no critic verdict | — | geometry v3.2 consumed with no code change: floors "Visible Mesh Final" / `prebuildCollisionData "1"`, plates at z 100.05, null LOD skipped; three static gates flipped honestly (`test_prefab_statics_mirror…` now asserts the floors collide and `lod` is null; the hashes gate pinned to round v3.2 + the floor sha; the smoke's plaza / pool surface expectations derived from `plate_instance_lift_m`) |

## 10. Open items

1. **Far-field floor banding — CLOSED as a design change, then ACCEPTED as a
   documented cosmetic.** Through v3.1 the floor was a 12 mm no-collision
   inlay whose far LOD never engaged (F-SC13, re-confirmed by G1's control
   boot); G1 measured the depth fight on 2 of 3 boots. The v3.2 answer was no
   LOD at all — a driven, colliding +50 mm skin (§2.1, F-GC11). **G7.0 booted
   the collision question and it passed** (ride height 0.2117 m on the plaza
   against 0.2116 m on a far reference lot, +50.1 mm over the groundplane),
   so `FLOOR_SKIN_STOCK_NODES = False` was never needed. The striping
   improved (worst 4.75 → 2.73 → 2.69, banded 2/3 → 1/3 → 1/3) without
   disappearing and is accepted on the record — see §11.5.1 for the table and
   the rejected candidates. The smoke keeps recording the band ratio.
2. **BeamMP scenario play is deferred.** Scenario lifecycle under BeamMP is
   unexercised; a follower cannot set options (F18), so the boot writes
   nothing and the valve is off in an MP session — single-player scope, on
   the record.
3. **F-P1.10, the self-acceleration anomaly.** A probe car held at
   `brake = 1` on ice re-accelerated to a constant 20.19 m/s ~7.4–7.9 s after
   braking and drove 1.1–1.4 km; the one-shot `set_velocity` thruster is an
   unlikely cause; nothing else was commanded. Cause unidentified; it did not
   recur in the gate ladder, whose braking runs all reached a stop.
4. **The cross-slope trip roll — fix in flight (runtime ask #6), G10
   pending.** See §11.5.3: cars are rolled by slow lateral drag on the 30 %
   glacis, never by speed.
5. **Sumo Gyro's runtime was not re-cut.** The `MPCoreNetwork` rawget fix is
   in `examples/giant_props/sumo_gyro_platform/spec.py` (working tree) and
   pinned by `tests/test_sumo_gyro_platform_beammp_sync.py`, but the shipped
   `mod/.../runtime.lua` and `dist/sumo_gyro_platform_ericrolph.zip` (serial
   40, stamped 2026-08-30, lock == zip) still read `extensions.MPCoreNetwork`
   and will log `extension unavailable` twice a frame in single player. Sumo
   has no certified harvest manifest (no `textures_cooked/`; its dist ships
   63 raw PNGs), so the one-member re-cut proof Hot Potato gave five times
   has no certified texture baseline to hold Sumo's other 128 members
   against; the re-cut is deferred, not forgotten.
6. **The real profile.** `deploy_local.py` does not know the arena (its
   release table is `examples/giant_props/*/spec.py` plus the car wash);
   both zips are installed by hand, hash-verified against their locks. The
   runtime critic observed the profile's Hot Potato zip carrying an older
   runtime (`fe92e11d…`) on 2026-09-01; deploying is the user's call.
7. Textures ship as PNG; a DDS pre-cook (the CCW harvest pattern) is a later
   re-cut decision.

## 11. Integration round (G1–G14)

**32** `beamng_live` tests in `tests/test_hot_potato_arena_gates_live.py`,
run serially on the sentinel-isolated profile, one owned BeamNG process at a
time, with both zips hash-verified against their locks at every boot and the
profile cleaned afterwards (zips, settings, snapshot, screenshots, compiled
arena cache). The real profile was never touched. **79 boots wrote a report
JSON**; artifacts are `scratchpad/arena_gate_shots/G<n>/` — **566 PNG** and
79 per-boot report JSON beside 35 `index.json`.

*(Counts are as at the close of G14. They moved five times during the round —
the final critic counted 405/42/19 before G11 ran — so re-count the tree
rather than quoting this paragraph.)*

### 11.1 The builds under test

The runtime moved five times mid-round (asks #4 and #6, the dodge latch, and
the pin reflex) and the geometry twice, so gates were measured on **seven**
package combinations. The pairing is recorded per gate because it decides
what a number means.

| Pair | Arena dist | Hot Potato | Boots | What it is |
| --- | --- | --- | --- | --- |
| A | `2f78e1b7…` (v3.1, 12 mm no-collision inlay) | serial 47 `a4bde9d3…` | 9 | pre-lift |
| B | `c37754b6…` (v3.2, driven +50 mm skin) | serial 47 `a4bde9d3…` | 12 | lifted skin |
| B′ | `91f05bbc…` (v3.3, shadow fix) | serial 47 `a4bde9d3…` | 1 | **G6 alone** — v3.3 geometry against the pre-ask-#4 runtime |
| C | `91f05bbc…` | serial 48 `973a212e…` | 12 | + magnet-membership fix (ask #4) |
| D | `91f05bbc…` | serial 50 `5253ad91…` | 4 | + dodge latch (ask #5, withdrawn as an ask — see §11.3) |
| E | `91f05bbc…` | serial 51 `7b943dd8…` | 4 | + slope-aware tip limit (ask #6) |
| F | `91f05bbc…` | serial 52 `0d0d6585…` | 2 | + the pin/unpin reflex |
| G | `d0e2b325…` (v3.4, glacis shadow split) | serial 54 | 21 | + the out-of-bounds fuse (ask #7) |
| H | `0adb6cc2…` (v3.5, measured `rp` per post) | serial 55 `45912b9d…` | 7 | + the fuse fix and the reflex on the measured radius |
| I | `cfafe4fc…` (v3.6–v3.8: nose points, junction assert, descending tuck skirt) | serial 55 `45912b9d…` | 7 | the closing round — 46 registry points |

Ten combinations in all. **The arena archive was byte-stable from v3.3
through five lock-only re-cuts** (`depends_on` 47 → 48 → 50 → 51 → 52), then
moved twice for real art/handoff changes (v3.4, v3.5). The static suites were
green at every re-cut — **81 passed** (20 package + 57 lupa + 4 site
clearance) — re-confirmed at this writing against **serial 55**, with the
chain agreeing (`depends_on` 55 `45912b9d…` == the Hot Potato lock).

### 11.2 Per-gate results

| Gate | Pair | Result | The numbers |
| --- | --- | --- | --- |
| G1 site truth (3 boots) | A | banding + one halo finding | halo ribbon **1.5 m** above the crest; readable from the bowl floor (peak chroma +19.3), crest (+32.9) and glacis (+39.4) but **NOT from mid-bank** (band 14 rows, +8.5) — recorded, not a defect; glacis toe drive-off at three bearings: **0 voids**, worst step 13.6 mm per 0.05 m, local slope ≤ 27.3 %, z reaching exactly 100.0 by r 113 |
| G1 control zip | A | LOD never engaged | the `_a70`-removed control renders the near mesh at 300 m (far medians 141.6–156.4 against 155.5 with the skins hidden), at 150 m 94.8–101.2 against 145.4 hidden — the negative control the design change answered |
| G2 surface (6 boots) | A (5) + B (1) | pre-fix failures that became asks #4/#5 | **turning circle measured 11.18 m right / 13.27 m left**; crest rams pre-fix: 85 km/h flew to **r 190.51** and the haul never completed (still sitting at r 183.61, 0.19 m up, 0.0 m/s at t = 75 s), 110 km/h rolled (min uz 0.20) |
| G3 AI | C | pillar contacts remain | 3 min chase, field 6 / props_excluded 16; **24 contact SAMPLES** (see the units note in §11.8 — no gate before G13 grouped correctly), largest class **`handle_flank_e` 13**, then `ramp_e_inner_flank` 9, `grinder_se` 1, `grinder_nw` 1. The handle flank being the biggest class is the fact the segment-primitive question turned on, and the integration report's own G3 line omits it |
| **G4 geysers** (3 boots) | B, C | **PASS** | peak vertical **4.842–4.852 m/s** at all three sites, exactly **1 pop per ON window**, **0 OFF-window pops**; a moving car keeps **99.88 %** of its horizontal speed across the pop frame (6.004 → 5.997 m/s, vz +5.34, rise 1.55 m); AI spout entries recover in **1.05 s** at both spouts |
| **G5 round** (5 boots) | B, C | **PASS** | field 6 / props_excluded 16, carrier the player, transfer by impact through the immunity window; valve stepped to 75 m and held it through stall 179 s, then to **60 m at stall 182 s** (threshold 180), 3 calls, restored to 91.4 at round end; the halo ring measured **319 px at 91.4 m → 261 px at 75 m** (the 60 m frame's mask was not clean and is not counted); **Exit hand-back byte-equal to expectation** with the tuner's `ai_enabled = false` and `arena_magnet_enabled = false` surviving; crash recovery **1 call**; boot 42 obstacles, part_count 7 |
| **G6 perf and culling** | B′ | **PASS** | **3,575 frames in 60.0 s = 59.6 fps**, worst frame **33.8 ms**, 1 frame over 33 ms, 0 over 67 ms; all six plain wall arcs ray the crest at **105.500** (one at 105.4986), both spout throats at 100.012; arc popping **0.49–0.70 % at 150 m**, rising to **2.01–5.46 % at 250–400 m**. **Unexplained:** this report carries `physics_realtime_factor` **2.998** where probe F-R3.2 recorded **1.000** — a 3× move on a field the ledger cites. It may be a definition difference (windowed vs `-headless`, or sim-vs-real accounting), but it is unexplained and is recorded here rather than quietly dropped |
| **G7.0 drop test** (4 boots) | B, C | **PASS** | the skin carries the car: ride height over its own four-corner footprint **0.2117 m on the plaza against 0.2116 m on a far reference lot**, lift over the groundplane **+50.1 mm**, four ASPHALT contacts, uz 0.9999; rays 100.05 plaza, 100.0303 feather, 100.0135 toe, 100.07 plate tops, 100.0 at the medallion |
| G7.1 far field (6 boots) | B, C | banding persists | §11.5 |
| **G7.2 surface** | B | **PASS** | **12/12 feather crossings 0.0 s airborne** (min uz 0.989); the quadrant seam crossed tangentially reads **0.085 m/s peak vertical over a 14 mm span**; butter μ **0.276** with four ICE contacts, plaza asphalt μ 0.976; salt arcs read **four SAND contacts** at 100.07 — closing the "SAND never braked" debt |
| G7.3 AI + perf | B | contacts remain | 60.0 fps, worst 26.2 ms, 0 frames over 33 ms; **25 contact samples** — the baseline ask #5 improved on (samples, not events: §11.8) |
| **G7.4 round** | B | **PASS** | field 6 / props_excluded 16 live; boom; a dodge win reached `fw_stage launch`; radius back to 91.4, valve stage 0, out of round |
| **G8 crest rams** | C | **PASS** | 60 / 85 / 110 km/h all **six clauses true**; the 85 km/h case that had stranded at r 190.5 now peaks at **r 114.58 and is hauled home in 6.9 s**; 110 km/h min uz 0.858 where it was 0.20 |
| G9.1 AI dodge | D | **1 contact** | 3 min chase: **1 contact sample total**, class jamb; **zero pillar/tower and zero ramp-flank**; closest approaches masher ≥ 8.24 m, grinder_se 0.61 m, handle flanks ≥ 11.04 m |
| G9.2 magnet orbit | D | rolls remain | at 1.2 g, 5 of 6 attempts rolled (4 on the glacis cross-slope, 1 inside the ring); at 2.0 g, 4 of 6 |
| G9.3 crest rams (2 boots) | D | 1 roll per boot | every other clause held both boots; boot 1 the 85 km/h ram rolled (min uz 0.25), boot 2 the 110 km/h ram rolled (min uz −0.317) |
| G10.0 far field (4 boots) | E | banded at 300 m only *by this metric* | d300 clean in 2 boots (1.027–1.038, 1.627–1.668) and banded 4/4 in 2 (2.583–2.679, 2.943–3.057); d150 **0.887–0.915** and d100 **0.867–0.886**, no frame over 2.2 at either distance in any boot. **The 150 m reading is now known to be measured in the wrong place — see §11.5.1** |
| G10.1 magnet orbit | E | **the brief's failure mode, relocated** | re-entry **2/6** at both dials (was 3/6); uprightness **1/6 → 5/6** and 2/6 → 5/6; the four bearings that never return reach **r 114.7–115.1 at 29.9 m/s and hold it 40 s, min uz 0.94**; a D-series pickup **0/3 re-entered**, min uz 0.378, its one roll at **r 82.5 INSIDE the ring on the bank**. §11.5.4 |
| G10.2 crest rams (2 boots) | E | 1 roll in 6 | hauls **6.85–6.95 s on all six**, as predicted; boot 1's 110 km/h rolled (uz −0.826), boot 2 clean 3/3 |
| G10.3 dodge re-check | E | new failure mode, not the old one | **23 pillar/tower samples, 0 ramp-flank, 0 jamb, 0 handle**; all at `grinder_sw` (13) / `grinder_se` (10), **every one ≤ 2.7 m/s** (median 0.7). Not G7.3's 9–17 m/s signature — cars **pinned below the dodge's own 3 m/s activation floor**. Became D-8. **Duration corrected:** the integration report's "spread over t 4.6 → 149.7 s" reads as a 145-second pin and is not one — grouped, it is **two short pins (car 3 on `grinder_sw` t 4.6–7.9 ≈ 3.3 s; car 1 on `grinder_se` t 15.5–20.0 ≈ 4.5 s) plus five isolated brushes by car 2 over ~100 s**, and the round still ran 4 transfers. A player sees one AI car fumble a pillar early and recover. The four- and five-figure damage readings at ≤ 2.7 m/s are **cumulative-attribution artifacts**, not impacts — the harness's own note says damage is cumulative |
| G12 far field (3 boots) | G | **the measurement the reopened item owed — and its first reading was wrong** | the band metric widened to a **24-sector glacis annulus, r 93.9–110.5**, swept at three distances against skins-hidden references. **d100 clean in every boot** (0 sectors over 2.2, ratio_max 1.28–1.37, mean 0.96–0.98); **d150 at 4/4/4 sectors**, matching the pre-fix *clean-boot* count — but with a mean of **1.72–1.84** that matches the pre-fix *banded* boot (1.77), not the clean one (1.38); **d300 striped at 6/6/6 sectors** (ratio_max 9.08–12.28). The count and the mean disagree; an independent stripe instrument broke the tie against the count. **Corrected conclusion in §11.5.1: clean at 100 m, still striped at 150 m and above in every boot** |
| G12 realtime perf | G | **PASS, and it settles G6's anomaly** | run in **non-deterministic real time**: 3,600 frames in 60.0 s = **60.0 fps**, worst frame **19.8 ms**, floor 50.4 fps, **0 frames over 33 ms**, and `physics_realtime_factor` **1.000** — the honest number, against G6's unexplained 2.998 under the deterministic stepper |
| G12 D-8 baseline | G | the 51 | **51 contact samples** (pillar/tower 41, handle 10), envelope **4,093 samples** on the 9.4 m keep-out-radius arming disc; `2::grinder_sw` grinding 8 events over 104.6 s |
| G12 OOB fuse | G | **inconclusive — instrument, not runtime** | the option landed (`oob_burn_multiplier` 3) and the boundary read true (first r flagged 94.6, largest not flagged 84.9, pad offset 0.0), but the rate inferred from `countdown` gave 1.71× parked and 1.00× driven, and several boots read no fuse at all (`-1.0`). Resolved in G13 |
| **G13 out-of-bounds fuse** (2 boots) | H | **PASS — the counter is PROVEN** | §12.3 |
| G13 pin reflex (3 boots) | H | **D-8 improved, not closed** | §12.4 |
| **G13 regression** | H | **PASS** | one full round: field **6**, props_excluded **16**, pad pickup → ram transfer → the **actual carrier at the boom launched at 12.04 m/s** → return flight → `round_won` with `fw_stage` reaching `burst` → idle, potato home; `arena_radius_m` restored to **91.4**, valve stage **0**, `in_round` false. The runtime log carries `carrier_out_of_bounds` / `carrier_back_in_bounds` in ordinary play, not only under a gate's teleports |
| **G14 pin reflex** (3 boots) | I | **the nose defect CLOSED; the bar missed** | §12.6 |
| **G14 deck-rear junction** (3 boots) | I | **PASS in the engine** | deck top **104.000** at r 88.0, seam **104.005** at r 88.5, **104.303** at r 89.0; **deck-to-seam 0.0000 m**; worst step in the seam band **0.0287 m** at r 88.55 — the authored **30.3 %** bank climb, not a lip. All four crossings **0.0 s airborne**, no bump / launch / rollover, band min uz **0.935–0.942**; the crawl-outbound run stalled **grade-limited** 1.0 m past the seam with +2 damage, matching G2's independent bank finding. Grazing-angle and driver's-eye frames show one clean wood-to-iron line, no interleave, no shimmer. **v3.7's retraction and v3.8's fix both hold in-engine** |
| **G14 regression** | I | **PASS** | field **6**, props_excluded **16**, ram transfer (rammer 18565), carrier launched at **13.65 m/s**, return flight, fireworks to `launch`, idle; `arena_radius_m` restored **91.4**, valve stage **0**, `in_round` false |
| G11 pin reflex | F | **D-8 NOT closed** | the reflex predicted 0–2 residual transient contacts; measured **17 contact samples, all pillar/tower**, of which `4::masher_se` is **12 samples at one spot** (position spread **0.22 m**, span 56 s, max speed 1.0 m/s) — the `fixed_position_grinding` signature the runtime worker named as its own discriminator. **Not the car-pinned-by-another-car case it predicted**: `events_with_car_within_6_5m` is 0 and the nearest car never closer than 12.2 m. The reflex's own envelope counter reads **0 samples within 1.5 m at ≤ 3 m/s**, while the grinding pair's min clearance is **1.85–2.02 m** — i.e. the car sat outside the 1.5 m trigger radius and the reflex never armed. Interpretation is the runtime worker's call; the measurement is here. Far field this boot: d300 banded **4/4 (4.123–4.156)**, d150 0.867–0.876, d100 0.823–0.831 |

### 11.3 Two runtime bugs the arena exposed

Both were found by gates, fixed upstream in the Hot Potato runtime, and
re-measured. Neither is an arena accommodation.

- **Ask #4 — magnet membership was sampled only by the 0.25 s sweep (serial
  48).** A car leaving the ring at 85 km/h covers ~5.9 m per sweep, so a fast
  exit was never drafted as a member and no well was ever placed: G2 measured
  it flying to r 190.51 and still sitting at r 183.61, 0.19 m up, 0.0 m/s at
  t = 75 s, with the round end abandoning the stray. After the fix G8 hauled
  the same ram home from r 114.58 in 6.9 s.
- **Ask #5 — the dodge was a 4 Hz limit cycle (serial 50).** The side-step
  was recomputed from the car's CURRENT heading and released the instant the
  ray cleared, whereupon the 0.8 s role sweep re-aimed straight through the
  post; the detection geometry also allowed a 12° deviation at 37 m. The
  fix latches the side-step. Contacts fell from **25 contact samples
  (G7.3, serial 47) to a single contact sample (G9.1, serial 50)**, with zero
  pillar/tower and zero ramp-flank strikes.

**The segment-primitive ask was PROPOSED and DECLINED.** The runtime worker
offered a line-segment obstacle primitive to replace the point chains; on G9
evidence it was not built, because the latch alone cleared the 44.5 m handle
flank without a new primitive. The honest caveat: the one surviving contact
was a spout jamb approximated by a 4-point chain, so the jamb chain is the
case that would argue for the primitive if it is ever revisited.

### 11.4 The altitude falsifier — a verified engine law

The design assumed `obj:setPlanets` hoists an attractor above the pad and
that the lift is what unloads the tires (F28), but the repo could not tell
from the shipped Lua whether the call ADDS an attractor or REPLACES world
gravity. The gates settle it. Pre-fix, with no well ever placed, the 85 km/h
car simply sat on the ground (r 183.61, 0.19 m up, 0.0 m/s). Post-fix every
haul lifts, and the ground falls away beneath it:

| Ram | Max height above the ground under the car | Ground z, first → last | Tether |
| --- | --- | --- | --- |
| 60 km/h | 2.089–2.12 m | 105.33 → 102.77–102.98 | 3,580–3,739 amber px |
| 85 km/h | 7.855–7.872 m | 104.80 → 100.0 | 3,665–3,743 px |
| 110 km/h | 13.31–13.53 m | 104.65 → 100.0–102.44 | 3,996–4,213 px |

`rose_while_tethered` is true in every case. A car that is lifted while a
well holds it, on a map whose own gravity is unchanged for everything else,
is an ADDED attractor — not a replaced gravity vector.

### 11.5 Open items out of the round

1. **Far-field striping — acceptance withdrawn, re-measured twice, and
   settled as "clean at 100 m; still striped at 150 m and above."** The numbers below are real,
   and so is the trend, but they do not support the sentence they were used
   to justify ("a 300 m-only artifact, not present at play distance").

   | Build | Worst band ratio | Boots banded (frames > 2.2) |
   | --- | --- | --- |
   | A pre-lift `2f78e1b7…` | **4.75** | 2 of 3 |
   | B lifted `c37754b6…` | **2.73** | 1 of 3 |
   | C `91f05bbc…` (serial 48) | **2.69** | 1 of 3 |
   | E `91f05bbc…` (serial 51, G10) | **3.06** | 2 of 4 |
   | F `91f05bbc…` (serial 52, G11) | **4.16** | 1 of 1 |

   **What the metric actually samples is a plaza disc at frame centre.** At
   150 m the artifact has migrated radially outward off the plaza and onto
   the **glacis**, outside the sampled region — so the 0.87–0.92 "clean"
   readings at 150 m measure ground the stripes had already left. The final
   critic cropped the same 150 m camera from a banded and a clean boot and
   put them side by side: the banded boot's outer glacis is covered in dense
   evenly-spaced white stripes; the clean boot's is spotless. The artifact
   did not go away between 300 m and 150 m; **the ruler stopped covering
   it.** It IS genuinely gone at 100 m.

   **Both owed actions were then done, and the item is closed at play
   distance and open at 300 m.** Geometry v3.4 gave the glacis its own
   material copy (`cast_iron_glacis`) with `castShadows: false` — the
   candidate that was pointed at exactly where the stripes were — and G12
   re-measured with a **24-sector annulus over r 93.9–110.5** at three
   distances, three boots:

   | Camera | Sectors over 2.2 (3 boots) | Worst sector ratio | Mean |
   | --- | --- | --- | --- |
   | 100 m | **0 / 0 / 0** | 1.28–1.37 | 0.96–0.98 |
   | 150 m | **4 / 4 / 4** | 5.64–6.78 | 1.72–1.84 |
   | 300 m | **6 / 6 / 6** | 9.08–12.28 | 2.12–2.25 |

   **The first reading of this table was wrong, and the table itself said
   so.** It was read as "at 150 m every boot now sits at the clean-boot
   floor of 4 sectors, bimodality gone" — treating the sector MEAN of
   1.72–1.84 as a caveat. It is not a caveat, it is the finding: against
   the same instrument's own pre-fix baseline (**clean boot 4 sectors /
   mean 1.38; banded boot 8 sectors / mean 1.77**) the v3.4 mean sits on
   the *banded* value, not the clean one. Sector count says clean, sector
   mean says banded, the two disagree, and the tie-break is the pixels.

   **The final critic broke the tie with an independent instrument** —
   row-alternation energy (the second difference of row-mean luma, which
   cancels smooth shading) plus a stripe-line count, on a patch lying
   entirely on glacis surface at the same camera pose:

   | Build / boot (150 m) | Alternation energy | Stripe lines |
   | --- | --- | --- |
   | pre-fix **clean** boot (G10_1) | **0.362** | **0** |
   | pre-fix **banded** boot (G10_3) | 6.980 | 11 |
   | v3.4 boot `3546db`, 2 frames | 7.664 / 7.980 | 11 / 11 |
   | v3.4 boot `8421cc`, 2 frames | 6.956 / 7.251 | 11 / 11 |
   | v3.4 boot `8ee6e4`, 2 frames | 6.908 / 7.214 | 11 / 11 |

   Every post-fix frame is indistinguishable from the pre-fix **banded**
   boot and ~19× the pre-fix clean boot: eleven stripes, every frame, every
   boot. (Re-checked here on a differently-chosen patch: v3.4 energy
   0.72–0.87 against a pre-fix clean 0.44–0.47 and banded 0.79–0.86 — the
   absolute scale depends on the patch, the ordering does not.)

   **So the conclusion inverts: the bimodality is gone because every boot is
   now banded, not because the artifact was removed.** v3.4 did not fix the
   150 m stripes; it removed the chance of drawing a clean boot. The honest
   statement, which replaces "fixed at play distance" wherever it appeared:

   > **Clean at 100 m — 0 sectors, and visually spotless, verified both by
   > metric and by eye.** Still striped on the glacis at 150 m and at 300 m,
   > in every boot. Cosmetic, invisible from the car, and accepted on that
   > basis — 100 m and below is every camera a player actually uses.

   **What went wrong is worth more than the artifact.** §11.5.1's first
   correction moved the sample REGION from a plaza disc to the glacis
   annulus, which was right — but it inherited the plaza disc's **2.2
   threshold**, and v3.4's stripes sit just under it. **The blind spot moved
   from the region to the threshold rather than closing.** A metric's
   threshold is calibrated against the region it was designed for and does
   not transfer with it.

   **And the mechanism, which falsifies the fix's own hypothesis:**
   disabling `castShadows` on the glacis changed nothing **because a
   non-casting surface still RECEIVES shadows.** The remaining caster over
   that band is `cast_iron_matte` — the bank — which v3.4 deliberately left
   casting (§9.2). v3.4 was correct work aimed at the wrong half of the
   mechanism. The next experiment is therefore **one material flag and one
   boot**: disable casting on the bank and re-measure at 150 m. Not now —
   the artifact is cosmetic. Rejected candidates remain a further lift
   (moves the plates, the medallion crossing and every spawn z), plate LODs
   (reopens which-detail-carries-collision on critic-verified shapes) and
   killing the skin (it is the arena's floor).
2. **One jamb graze.** G9.1's single contact: `jamb_240_far`, 9.3 m/s,
   **181 damage**, closest approach **0.03 m**. Not re-observed on serial 51
   or 52.
3. **The cross-slope trip roll — improved and accepted as a trade, not
   closed.** Ask #6's slope-aware tip limit took orbit uprightness from
   **1/6 → 5/6** at 1.2 g and 2/6 → 5/6 at 2.0 g, and one crest ram still
   rolls in about one boot of two (G10.2: boot 1's 110 km/h at uz −0.826,
   boot 2 clean 3/3). The runtime worker's diagnosis, accepted: on a
   traverse the inward direction IS the lateral direction, so "less tipping"
   and "less inward drag" are numerically the same reduction and cannot be
   separated inside a well that hangs over the pad — magnitude is the only
   free variable and raising it re-rolls the car. Recorded as an accepted
   trade (an upright car outside is strictly better than a rolled one, and
   it can drive itself back in) with the re-entry cost stated in item 4.
   The residual it leaves is **not purely vehicle-specific or purely
   position-specific**: the taller car tipped on the steeper surface (a
   pickup at r 82.5 on the bank, min uz 0.378), which is what one shared
   tipping ratio (`half-track / CG height = 1.2` for every car) predicts.
   A per-vehicle ratio from `getSpawnWorldOOBB():getHalfExtents()` is the
   named future round.
4. **The outside orbit — the brief's failure mode #1, RELOCATED rather than
   countered. This is the round's most serious finding.** G10.1, on the
   shipped build at both magnet dials: a powered car over the crest holds
   **29.9 m/s (107 km/h) at r 114.7–115.1 on flat ground for 40 s and never
   crosses the 82.3 m release line**, upright throughout (min uz 0.94), on
   **4 of 6 bearings**; the D-series pickup is worse at **0 of 3**.

   **The bearing pattern is the insight, and no gate report stated it:** the
   two bearings that re-enter (250°, 65°) are the **spouts** — exit at grade
   through a spout and the magnet catches you in 5.5–6.6 s. The four that
   escape (100°, 20°, 145°, 305°) climb the **bank** and get onto the flat
   runoff apron past the r 113 toe, where the well never brings them back.
   The apron is 47 m of clean flat ground — a racetrack. So the design's
   §3.1 mechanism 2 ("the magnet reels it back") holds for a ballistic stray
   over a spout and fails for a powered car over the bank, and the brief's
   "infinite perimeter looping" is not countered but **moved outside the
   pan, where it is measurably better for the exploiter than looping inside
   would have been** — outside the ring a car cannot be tagged (F20), so in
   a 1v1 endgame the orbiter wins by driving in a circle while the carrier's
   fuse burns.

   Both counters the design named for this exact attack were measured and
   both failed: the glacis cross-slope does not contest a powered car, and
   the **2.0 g escalation lever changes nothing** (2/6 re-entry at both
   dials). The lever must stop being described as the answer to a sustained
   orbit; it has been measured and it is not one.

   **This voids the standing justification for declining the out-of-bounds
   fuse penalty**, and that reversal is recorded in §11.5.5.
5. **The OOB fuse penalty, reinstated as runtime ask #7 — a reversal.** The
   penalty (the carrier's fuse burns faster while outside the ring) was in
   the player's original brief and was declined on the Hot Potato v2.6
   ledger's own words: *"invisible punishment, illegible in play"* — with
   the justification that **"the magnet is the shipped answer"**
   (hot_potato/DESIGN.md L981; this design carried it forward at §4 and
   §3.1). G10.1 measures the magnet failing at precisely that job for the
   one case that matters, so the justification no longer holds and nobody in
   the record had gone back to say so. The design owner has reinstated it as
   **runtime ask #7**, and the original objection is answered rather than
   ignored: the new build makes the penalty *legible* — a HUD flag while the
   carrier is outside the ring, and transition messages on leaving and
   re-entering — so it is a visible rule instead of an invisible tax. **Not
   yet built or gated at this writing**; §13 is its stub. Two other
   candidates were named and are cheaper to test than to argue: make the
   magnet's horizontal term grow with excess radius past the toe rather than
   staying flat, and measure the decay valve against an orbiter (at a 60 m
   ring the orbiter at r 115 is 55 m outside instead of 24 m, which should
   deepen the well) — **nobody has measured the valve against an orbiter**,
   and that is one boot.

   **CLOSED — the penalty shipped as serial 55 and G13 proved it.** Two
   boots, **478 live samples, not one disagreement in either direction**,
   against a per-sample contract no clock stall can dilute:

   > for every live sample: `oob == (arena_distance > arena_radius_m)` and
   > `fuse_burn == 3.0 if oob else 1.0`

   `fuse_burn` read exactly **{1.0} inside** and **{3.0} outside** in every
   sample; `flag ≠ distance` **0**, `burn ≠ flag` **0**; the round was
   `live` in all 478 and the carrier was held throughout. Verified first, in
   order: `oob_burn_multiplier` **3.0** landed and `camp_burn_multiplier`
   **1.0** — they share one `max()`, so a camp burn above 1.0 would have
   meant a parked carrier's baseline was not the out-of-bounds multiplier's
   alone. Both boots read `arena_radius_m` 91.4. The windows, boot 2:

   | Window | Samples | Arena distance | `fuse_burn` |
   | --- | --- | --- | --- |
   | parked inside r 40 | 16 | 40.0–40.1 | 1.0 |
   | parked outside r 118 | 16 | 118.1 → 8.2 (the magnet hauling it home) | 1.0 and 3.0, each matching its own sample |
   | **driven, bank bearing 305, the exploit band** | **167** | up to **120.8** | **3.0 on all 167** |
   | driven at escape speed (33 m/s injected) | 80 | up to 122.2 | **3.0 on all 80** |

   The exploit state was entered deliberately rather than hoped for: **71 of
   those 167 samples sit inside G10's own 19–26 m/s band**, on the apron, on
   a bank bearing, across 24.9 s of sim — the exact state in which a powered
   car held the apron for 40 s and was never recovered. The fuse burned
   3.0× in every one of them. **And it ends the round rather than
   stalemating it:** a 60 s-fuse orbit on the same bearing ran 396 samples,
   every one flagged out of bounds at 3.0×, fuse **59.516 → 0.0**, phase →
   `boom` with the carrier at **arena distance 169.5 m**, outside —
   reproduced in boot 1 (59.564 → 0.0, boom at 169.7 m). So D-5 stays an
   accepted trade, but **its counter no longer depends on the magnet winning
   a traction fight**: the penalty fires at full strength on the apron,
   where the magnet does not reach. The brief's failure mode #1 is answered
   by the mechanism the brief originally asked for.
6. **D-8, the low-speed pin — the arming defect is CLOSED; the residual is
   dwell, not coverage.** The chain of fixes ran: G11's reflex never armed
   (it keyed on the keep-out radius); v3.5 published a **measured physical
   radius `rp`** per post and serial 55 armed on that, shrinking the disc
   from a flat 9.4 m to 3.13–5.35 m; v3.6 then closed the coverage hole
   v3.5's caveat had missed. **The decisive number is a replay:** G13's own
   pin position, evaluated against the new 46-point registry, goes
   **gap +1.471 m → −0.628 m — it arms now.** Registry echo exact at 46/46
   matched to the handoff, `rp ≤ r` on every one, census `rp` 0.1 ×28 /
   1.2 ×8 / 1.5 ×4 / 2.121 ×2 / 2.321 ×4, the four new nose points at
   **2.8 m pitch** (x 845.8 / 848.6 / 851.4 / 854.2 at y −310).

   | Boot | Samples | Events | Grinds | Nose contacts | Envelope |
   | --- | --- | --- | --- | --- | --- |
   | 1 | 36 | 10 | 2 | 2 (inside the disc, −0.714 / −1.091, transient) | 4,291 |
   | 2 | 14 | 6 | 1 | 0 | 3,468 |
   | 3 | **8** | **2** | **0** | 0 | 741 |

   **Boot 3 is the first run of the whole effort with no fixed-position
   grinding at all** — its only two contacts are transient brushes at 23.7
   and 6.7 m/s, both above the 3 m/s pin floor. Grinds went **2 → 1 → 0**,
   and there were **zero low-speed contacts outside the arming disc in all
   three boots** — the exact metric G13's pin failed.

   **The raw counts did not meet the ≤ 7 bar, and the record says so.** In
   the one comparable unit the series is **51 (G12) → 30 / 7 / 16 (G13) →
   36 / 14 / 8 (G14)**: G13 and G14 are the same distribution, dominated by
   how long one unlucky car dwells against a **grinder** — which v3.6 does
   not touch and was never claimed to. What changed is the class picture,
   and that is what the fix was aimed at.
7. **The spout jambs are the largest remaining registry gap — and it is a
   steering question, not a pinning one.** Four contacts landed outside the
   arming disc across boots 1 and 3, **every one at or above the 3 m/s pin
   floor**, so none of them is the reflex's job: `jamb_240_far` at gap
   **+3.365** (3.7 m/s) and **+3.117** (11.9 m/s), `jamb_60_gate` at
   **+1.908** (23.7 m/s), and one `grinder_se` at **+0.73** (6.7 m/s). The
   three jamb entries are the biggest gaps and the clearest signal: the
   battered jamb faces are approximated by points whose keep-out `r` does
   not cover where a car travelling at speed actually meets them. **Open,
   framed as an `r` (dodge) question rather than an `rp` (pin) one.**
8. **Flanks: zero across six boots.** handle_flank 0/0/0 and ramp_flank
   0/0/0 in G13, repeated 0/0/0 in G14 — 16 `face` points, six boots,
   1,080 s of chase, no contact. **The segment primitive is retired
   permanently on six boots of evidence**, and the deck flanks, ramp flanks
   and jamb batters stay deliberately under-sampled with their measured
   contact counts on the record.
9. **The plaza is under-furnished and the breakables never come back**
   (final critic, taste + mechanism). Eight pillars across a 73.5 m plaza is
   not the brief's "densely populated" slalom, and the four pantry stacks —
   the only sightline breakers — are consumed permanently within the first
   half-minute, with **no respawn mechanism anywhere in the package**. That
   absence was never recorded before now. Candidates: a third pillar ring
   inside r 40 (the measured 13.27 m circle leaves room the 14 m assumption
   did not), or respawning the stacks at each round start via the
   `requestReset(RESET_PHYSICS)` path the design already priced at §4.
10. **The pinch points do not pinch** (final critic). Mechanically flawless —
   1 pop per ON window, 0 OFF-window pops, three sites, three boots — but a
   pop costs a car **0.12 % of its horizontal speed** and a 1.55 m hop, and
   it recovers in 1.05 s. The spout curtain is the best-looking hazard in
   the map and the least consequential; the fiction-to-mechanic gap runs in
   the wrong direction. Candidates: a lateral component, a longer ON window,
   or 8–9 m/s.
11. **The salt's measured decel is under-sampled and physically odd.** G7.2's
   salt figure (23.19 m/s², μ 2.36) is above asphalt's on a groundmodel
   whose coefficients are 0.60/0.60 — below asphalt — and rests on **3
   samples**. The arcs function as high drag, which is what the brief asked
   for, and the four SAND wheel contacts are solid; but that specific number
   must not be cited again as a result.

### 11.6 A correction to the design's own contract

§2.6 assumed a 33° outer-wheel lock and carried 14 m as its turning circle,
with 13.5 m as the arithmetic. G2 drove the figure-eight and measured
**11.18 m right / 13.27 m left**. Both are at or under the assumption, so
every clearance in §2.6 has MORE margin than the contract required, not
less — the 35 m mandatory-lane and 14 m open-field floors stand unchanged and
the grinder-ring contingency (move the ring out if the measured circle
exceeded 14 m) is retired unused.

### 11.7 Harness facts (repo knowledge, not arena trivia)

Measured while building this ladder; every one cost a boot to learn.

- **A teleport quaternion `(0, 0, sin ψ/2, cos ψ/2)` lands the nose at
  compass 180 + ψ, not 180 − ψ.** A requested 85.5° put the car on 274.5°
  and drove it off the handle flank, so ψ = heading − 180.
- **`control.step(6)` is ~0.3 s of sim** at the 60 Hz deterministic setting
  (one step ≈ 3 physics frames, probe F-P1.9); the 0.1 s controller tick is
  `step(2)`.
- **Automatic gear indices are `{-1 R, 0 N, 1 P, 2 D, 3 S}`**
  (`shiftLogic/automaticGearbox.lua:658`) — index 2 is D. After a teleport an
  etk800 drove BACKWARDS on throttle until the range was selected
  explicitly, so every driven line now selects D and reads the gear back.
- **debugDrawer output exists only on frames the sim actually runs.** Every
  paused halo-on frame measured zero ribbon pixels; a capture must resume,
  shoot, and re-pause.
- **`doScreenshot` is asynchronous** — the PNG lands after the call and can
  miss a 0.7 s window entirely under load. Wait for the file, and for its
  size to stop growing, before measuring it.
- **Measure an overlay by chroma (red minus blue), never by raw frame
  difference.** Exposure drift moves luma between two frames: the raw diffs
  here counted 850k–919k changed pixels while the real 22/255 amber ribbon
  was a band of rows with a +8 to +40 chroma delta.
- **A teleport lands several frames later.** A calibration once read the
  pre-teleport position as its start; settle until the pose stops moving.
- **Ride height must be measured over the car's own four-corner footprint,
  not a single centre ray.** A 4.4 × 1.8 m car on graded ground does not
  stand on the point the centre ray hit — the footprint mean is what proves
  a surface really carries the car (it is what made the G7.0 drop test
  conclusive: 0.2117 vs 0.2116 m).
- **`clock_delta` is 0.0 in every sample a paused-stepper gate can take, so
  never infer a rate from two reads of a runtime clock.** `advanceClock`
  discards any wall gap over 0.5 s and skips `dtSim == 0`, and a gate's
  Python round trip between behaviour frames always exceeds 0.5 s — so the
  frame a gate samples is always the first after a discarded delta. Measured
  **0.0 in 478 of 478 samples**. The fuse still falls (286.15 → 261.31 over
  a 25 s driven window) because the frames *inside* each step burst count.
  Any slope measured against the gate's own wall or sim clock therefore
  under-reports by an amount that depends only on the gate's latency — which
  is exactly how G12 got 1.71× and 1.00× for a multiplier that is exactly
  3.0. **Read the rate the runtime publishes; do not compute one.**
- **There is no `fuse_remaining` field to read casually.** The stat is
  `countdown`, gated behind `show_countdown` and the escalating tick, so a
  gate that asks for the wrong name silently gets `-1.0` — several G12 boots
  reported "no fuse" for this reason. G13 reads `behavior_stats`
  (`fuse_remaining`, `fuse_burn`, `clock_delta`, `oob`) plus `behavior_phase`
  — `b.phase` itself, not the HUD mirror.
- **Teleporting the CARRIER with `reset=True` is the carrier-lost signal and
  ends the round.** Move the carrier without a reset, or move somebody else.
- **A contact census must state its unit.** Damage is cumulative, so
  consecutive readings must be grouped into events — and a grouping helper
  that silently never matches will hand you sample counts labelled as
  events for five gate rounds (§11.8).
- **Never sample a mesh on its own symmetry plane: a ray on a shared
  triangle edge reads exactly like a hole.** The handle is symmetric about
  x = 850.000, so a raster run down bearing 180.000 put every ray on the
  edge two triangles share. That one bearing returned **15 spikes with
  z_min exactly 100.000** (the groundplane 4 m below) and a worst step of
  5.17 m, while **all 16 other bearings** sampled at 0.5° either side read
  z_min 104.003–104.007 with a worst step of 13.6 mm. Three independent
  proofs that it was the instrument: a **5 mm sidestep closes it
  completely** (dx ±0.005 / ±0.020 / ±0.050 all give 0 spikes and z_min
  104.0, while dx +0.000 alone gives 15 and 100.0); the anomaly appears on
  exactly the bearing the model is symmetric about; and **three car drops
  at that spot rest on the bank** with four ASPHALT contacts. Offset any
  raster from a plane of symmetry, and treat an isolated exact-groundplane
  reading as a suspected edge hit before reporting a void.

### 11.8 Test and asset record

`tests/test_hot_potato_arena_gates_live.py` — **32** `beamng_live` tests.
Artifacts: **566 PNG and 79 report JSON** (plus 35 `index.json`) under
`scratchpad/arena_gate_shots/`, across 79 boots.

**Instrument faults found and fixed, all in the gate suite itself.** Five
more in the closing round, on top of the retroactive grouping bug below and
G13's four: the boot assert was **pinned to a literal 42** obstacle points
(now derived from the handoff — which immediately caught the dist lagging
the source); the armed-span tracker carried the **same global-last defect**
`_group_contacts` had, reporting **4,192 "spans" across 4,291 samples**;
"outside the arming disc" was **charging the anti-pin reflex for 12–24 m/s
steering contacts**, which is a different mechanism; the junction raster
**sampled on the mesh symmetry plane** (§11.7); and "crossed the seam" asked
whether the reference point had traversed it rather than **the car**. Nine
instrument faults across the last three rounds, every one the gate author's
own and every one found by a gate disagreeing with itself.

> **Units — a retroactive correction that touches numbers printed above.**
> The gate suite's `_group_contacts` helper never grouped anything from G7
> onward: it compared the full scene name (`…_ai_3`) against an
> already-shortened id (`3`), so no run ever matched, and it only tracked the
> globally last event, so two cars touching different solids in the same
> second broke each other's runs. **Every "grouped event" count in this
> record before G13 — 25, 1, 23, 17, 51 — is a raw contact-SAMPLE count**,
> and every such label above now says "sample". The comparisons between them
> remain valid, because the same broken grouping produced all of them; only
> the unit was mislabelled. The helper is fixed (the open event is tracked
> per car+solid pair) and **G13 reports both units side by side** so the
> comparison to 17 and 51 stays like-for-like while "one contact" means one
> contact. G13's own figures: boot 2 **7 samples / 4 events**, boot 3 **16
> samples / 10 events**. The gates' lock
guard was corrected during the round: it had asserted Hot Potato serial **47
literally**, which refused every boot once the runtime moved to 48, so it now
asserts that **the two locks AGREE** (`arena depends_on.sha256 ==
hot_potato lock sha256` and the same `build_serial`) with a floor of 47 — the
chain is the invariant, not any one serial. That guard is why five re-cuts
(47 → 48 → 50 → 51 → 52) cost nothing but a lock each.

The static suites were **81 passed** at every re-cut and are 81 at this
writing against serial 52. The final critic caught them at **80 passed / 1
failed** mid-round — `test_checked_in_lock_matches_the_dist_archive_and_the_hot_potato_lock`,
with the arena lock pinning serial 51 while the Hot Potato lock had already
moved to 52. That is exactly the transient the guard is designed to surface,
and the serial-52 re-cut closed it.

## 12. Rounds G10 to G14 — the limit, the reflex, the fuse, the wall

Four more runtime rounds were gated after §11's first ladder closed. All are
in §11.2's table and §11.5's open items; this section is the narrative and
the predictions-versus-outcome record, which is the part worth keeping.

### 12.1 G10 — runtime ask #6, the slope-aware tip limit (serial 51, 4 boots)

The ask: make the magnet's tip limit slope-aware so a car dragged sideways
across the 30 % glacis stops being rolled by it. The runtime's own summary of
the mechanism — at grade 0 every new term collapses to the previous
expression exactly (allowance `RATIO·MARGIN·cos θ − sin θ` → `RATIO·MARGIN`,
hoist factor `1 − grade/0.30` → 1, speed gate → 8.0) — is what made its
falsifier meaningful.

| What was predicted | What G10 measured |
| --- | --- |
| uprightness improves | **1/6 → 5/6** at 1.2 g, 2/6 → 5/6 at 2.0 g |
| re-entry unchanged | **worsened 3/6 → 2/6** at both dials |
| crest hauls unchanged | **6.85–6.95 s on all six**, exactly as predicted |
| flat-ground behaviour untouched | **falsifier FIRED** |

**The falsifier, and the ruling.** The reference orbit run was believed
grade-0, so its numbers were asserted not to move between serials 50 and 51.
They moved: max r **113.2 → 115.1 (+1.9 m)** and min uz **0.886 → 0.942
(+0.056)** at 1.2 g, with **max speed unchanged to the decimal** (29.9).
The integration worker reported this as a fired falsifier rather than
explaining it away, and the runtime worker then ruled the reading correct:
that path reaches r 113–115, i.e. the glacis toe and past it, so it was never
grade-0 for its length and the slope terms legitimately engage. The direction
corroborates it — less lateral pull on the sloped portion gives less tipping
and slightly less inward drag, with speed untouched; a genuine flat-path
regression would have moved speed or shown no uz gain. It is now pinned from
both sides by `test_the_flat_well_is_untouched_by_the_slope_work` (the flat
well asserted to the digit — hoist 9.0 m, lift 0.139 g, haul 0.620 g — and
the same car on a 30 % grade asserted to see the slope terms), so neither
half can drift silently. **This is the record working**: a falsifier fired,
was reported as a failure rather than a pass, and was then ruled on with an
argument that could itself be checked.

G10 also produced the round's most serious finding (the orbit escape,
§11.5.4) and a new one (D-8, the low-speed pin) that is not the old dodge
failure returning: G7.3's signature was strikes at 9–17 m/s, while G10.3
recorded **zero contacts above 2.7 m/s** — cars pinned below the dodge's own
3 m/s activation floor, grinding in place.

### 12.2 G11 — the pin/unpin reflex (serial 52, 1 boot)

The fix for D-8 was a new reflex rather than a lowered threshold, and the
reasoning was sound: the dodge rays the *velocity vector*, and a pinned car
has none, so there is no ray to cast — a stationary car needs "back away from
what you are already touching", not "steer around what you are about to
hit". A car within **1.5 m** of a registered keep-out at **≤ 3 m/s** for
**1.5 s** gets a latched target 10.5 m clear on the far side of itself from
the post, time-boxed at 6 s, with the ask-#5 limit-cycle guards carried over
(latched, never recomputed; range-only release; open-ground creeping
ignored). It consumes the arena's own 42-point keep-out set. A correction the
round made to itself belongs here too: the `speed > 3.0` dodge floor is
**v2.7.1's own**, present in the pre-v2.8 baseline, not anything the arena
work introduced.

**It did not close D-8.** Predicted 0–2 residual contacts, all transient;
measured **17 contact samples, all pillar/tower**, including `4::masher_se` at **12
events at one position** (spread 0.22 m over 56 s, max speed 1.0 m/s) — the
`fixed_position_grinding` shape the runtime worker itself named as the
discriminator for "not fixed". It is also **not** the failure mode it had
pre-registered as its likely miss (a car pinned by *another car*): the
report records `events_with_car_within_6_5m = 0` and the nearest car never
closer than **12.2 m**. The reflex's own envelope counter reads **0 samples
within 1.5 m at ≤ 3 m/s** while the grinding pair's minimum clearance is
**1.85–2.02 m** — the car sat outside the 1.5 m trigger radius for the whole
episode, so the reflex never armed. Whether that is an envelope too small for
this geometry or a clearance metric measured to a different reference is the
runtime worker's call; the measurement is recorded here either way.

Everything else held as predicted: zero contacts above 2.7 m/s, and the
far-field sweep unchanged in character (d300 banded 4/4 at 4.123–4.156; d150
and d100 "clean" by the plaza-disc metric that §11.5.1 now says is pointed at
the wrong region).

### 12.3 G13 A — the out-of-bounds fuse, and why G12 disagreed with itself

**The instrument changed, and that is the whole result.** G12 inferred a rate
from two reads of `countdown`, a clock it does not own, and got 1.71× parked
and 1.00× driven for a multiplier that is exactly 3.0. G13 **reads** the
rate instead: each sample is one `getSystemState(propId)` carrying
`behavior_stats` and `behavior_phase` beside the gate's own pose and the
carrier's distance from the runtime's **own pad origin**, asserted as a
per-sample contract rather than a slope. The result is in §11.5.5 — 478/478,
zero disagreements, detonation twice.

G12's numbers are explained with a measurement, not a shrug: **`clock_delta`
was 0.0 in 478 of 478 samples.** `advanceClock` discards wall gaps over 0.5 s
and skips `dtSim == 0`, and a paused-stepper gate's round trip always exceeds
that, so any inferred slope was guaranteed to land strictly between 1 and 3 —
1.71× was that artifact, and the 1.00× driven reading was the same artifact
at its extreme. **No runtime defect existed here at any point.** The general
form is now a harness law (§11.7).

### 12.4 G13 B — D-8 on the measured radius, and the wall the nose still is

Full numbers in §11.5.6–7. The shape of it: G11's reflex could not arm
because it keyed on the keep-out radius (a flat 9.4 m disc); geometry v3.5
published a **measured physical radius per post** and serial 55 arms on that,
shrinking the disc to 3.13–5.35 m. The envelope now arms in every boot,
contacts fell from 51 to 7/16/30 samples, open-ground shoving stopped, and
the flanks took **zero** contacts in 540 s — which is what permanently
declines the segment primitive.

What is left is one grind per boot in two different mechanisms, and the more
interesting one is geometric rather than behavioural: a **14 m handle nose
carrying only its two end corners**, worst uncovered half-span **7.0 m**,
where the escape provably could not arm (gap **+1.471 m**). It is the same
"a circle cannot represent a wall" problem as the flanks, on a face that
v3.5's caveat did not cover because each endpoint really is a corner. It is
recorded as adjacent to the segment-primitive question and **not counted as
flank evidence.**

### 12.5 Two instrument faults worth keeping

- **The serial-50 orbit falsifier is RETIRED.** It compared every later
  serial against a frozen serial-50 baseline, so it fired on every run and
  its message still said "serial 51". Its ruling is settled (D-6 explained in
  §12.1) and the invariant it guarded — at grade 0 the v2.11 expression
  reduces to v2.10 exactly — is algebra, pinned by the lupa suite without the
  game. It is now **recorded, not gated**.
- **The G1 control-zip staleness could not have been caught by any existing
  gate, and that gap is worth naming.** The control-zip builder was the only
  place outside the geometry build that pinned a DAE's internal node *name*;
  the hash manifest tracks DAE bytes and the package suite pins member
  hashes, and **both legitimately stayed green across the rename**. The
  failure surfaced as a `StopIteration` inside the single test that used the
  name, and only when that test ran. The named closer: assert the shipped
  floor DAE's **LOD node census** at boot, from the zip, in the same place
  the boot already asserts 42 obstacles — then a rename fails loudly in every
  gate instead of silently in one.

### 12.6 G14 — the nose closed, the bar missed, and a wall that was never there

Three things were on trial: whether v3.6's four nose points made the
anti-pin reflex arm where G13 proved it could not; whether v3.7's retraction
of its own 145 mm deck-rear finding survived contact with the engine; and
whether v3.8's descending tuck skirt read clean.

**The nose is closed, by replay rather than by absence of evidence.** It
would have been easy to call it fixed because no boot pinned there again;
instead the gate re-evaluated G13's own pin position against the new
registry and got **+1.471 m → −0.628 m**. That is the arming margin
crossing zero at the exact coordinates that failed before — a positive
result, not a null one. Boots 2 and 3 took zero nose contacts; boot 1's two
were *inside* the disc at −0.714 and −1.091 and were transient brushes, not
pins.

**The bar was missed and the reasoning is on the record.** The ≤ 7 raw-sample
target was not met (36 / 14 / 8). Rather than re-cut the target, the record
states the comparable series — 51 → 30/7/16 → 36/14/8 — and names the
dominant variable: how long one unlucky car dwells against a *grinder*,
which v3.6 never touched. What v3.6 was aimed at, the class picture, did
change: nose contacts to zero in two of three boots, grinds 2 → 1 → 0, and
boot 3 the first clean run of the effort.

**The deck rear reads flush in the engine, so the retraction holds.** Deck
top 104.000 at r 88.0, seam 104.005 at r 88.5, 104.303 at r 89.0, deck-to-seam
0.0000 m, worst seam-band step 0.0287 m — which is the authored 30.3 % bank
climb, not a lip. Four crossings, none airborne, none bumped or launched or
rolled. The crawl-outbound run stalled 1.0 m past the seam **grade-limited**
with +2 damage, independently reproducing G2's bank finding rather than
revealing anything new.

**And the one alarming number in the round was the instrument.** A raster
down bearing 180.000 reported 15 spikes reaching exactly z 100.000 — a 4 m
hole through the deck, on paper. It was a ray running along the edge two
triangles share on the handle's own plane of symmetry: 16 other bearings
were clean, a 5 mm sidestep closed it completely, and three car drops at the
spot rested on the bank on four ASPHALT contacts. The gate labelled it
`ray_edge_artifact_not_a_gap` and it became the harness law in §11.7. Worth
noting what did *not* happen: nobody re-cut geometry to chase it.

## 13. Final state at close

The ladder is closed. Fourteen live gates over **79 boots** and ten
package/runtime combinations, four component critic tracks each ending
WOWED, and a final adversarial critique whose four findings are all
answered: the stale record and wrong install hashes (fixed and now
lock-derived), the far-field measurement aimed at the wrong region
(re-measured over a glacis annulus), the red package gate (a lock-chain
transient, green at serial 55), and the orbit exploit — the one the critic
called "the real one" — closed by the mechanism the player's brief asked for
in the first place.

**What ships.** Arena dist `cfafe4fc…`, 8,146,038 B, 36 members, cut against
geometry v3.8, `depends_on` Hot Potato serial 55; 13 shapes / 32 instances /
**46** obstacle points / 6 texture families / 9 materials / 18,288 scene
triangles; 81 static gates green (20 package + 57 lupa + 4 site clearance).
Read the two locks, never a printed digest.

**What is open, with its framing.**

| Item | State |
| --- | --- |
| **Spout-jamb steering gap** | The largest remaining registry gap. Four contacts outside the arming disc, **all at or above the 3 m/s pin floor** (3.7 / 11.9 / 23.7 / 6.7 m/s) — so this is an **`r` (dodge) question, not an `rp` (pin) one**: the battered jamb faces are approximated by points whose keep-out does not cover where a car at speed meets them (§11.5.7) |
| **D-3 far-field striping** | **Clean at 100 m; still striped at 150 m and above, in every boot.** 100 m verified spotless by metric (0 sectors) and by eye. v3.4 removed the boot-to-boot bimodality by making every boot band, not by removing the artifact — the sector mean 1.72–1.84 matches the pre-fix *banded* boot (1.77), and an independent stripe instrument counts 11 lines in every post-fix frame against the pre-fix clean boot's 0. Cosmetic, invisible from the car, accepted on that basis. The untried next step is one flag and one boot: **`cast_iron_matte` (the bank) is the remaining caster over that band** — a non-casting surface still receives (§11.5.1) |
| **D-7 crest-ram rolls / D-9 tall-vehicle rolls** | Open, and they share one cause: the magnet's tip budget uses a single generic `half-track / CG height = 1.2` for every car in the field, so a taller vehicle tips on a steeper surface exactly as one shared ratio predicts. The named path is a **per-vehicle ratio measured from `getSpawnWorldOOBB():getHalfExtents()`** — already read once per car for the extents cache, giving half-track (x) and a CG-height proxy (z). That changes the magnet's contract and deserves its own round and live gate, not a bolt-on (§11.5.3) |
| **D-8 residual** | The arming defect is closed (§11.5.6); what remains is dwell against a *grinder*, not coverage — one fixed-position grind in two boots of three, none in the third |
| Plaza furnishing, geyser consequence, salt μ | Taste and calibration items from the final critique, recorded at §11.5.9–11 |

**No stubs remain.** Anything not measured is named above as open, with the
instrument that would close it.

*The player's word outranks the critic's screenshot (hot_potato DESIGN.md
v2.7.1).*
