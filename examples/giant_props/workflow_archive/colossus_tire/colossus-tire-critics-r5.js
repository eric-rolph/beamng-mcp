export const meta = {
  name: 'colossus-tire-critics-r5',
  description: 'Round 5 critic panel on the COLOSSUS tire after the realism pivot, stiffening, and the hamster-wheel rework',
  phases: [
    { title: 'Critique', detail: 'six specialist critics judge the pivoted design' },
    { title: 'Synthesis', detail: 'verdict and any remaining work order' },
  ],
}

const REPO = 'C:/Users/ericr/beamng-mcp'
const MOD = 'examples/giant_props/colossus_tire'
const RENDERS = `${REPO}/${MOD}/authoring/verify`

const CONTEXT = `
ROUND 5 review of a BeamNG.drive mod in the repo at ${REPO}.

THE BRIEF HAS CHANGED SINCE ROUND 4 - judge against the CURRENT brief. The
user issued two directives after round 4:
 1. "let's forget the ramp and entrance and make the tire as realistic as
    possible. I noticed some strange jagged geometry on the face of the tire
    wall" - the loading dock, boarding gangway and bolted access port are
    GONE by decree. The jagged sidewall geometry (the buttress wraps) was the
    named defect.
 2. "it seems to wobble too much, too jelly like, it should easily roll down
    a hill in a manner that a realistic super massive tire would. We still
    want the inside drivable and to effect the physics of the tire (rolling
    around inside it could make the tire move), we don't want a ramp into
    the tire."
So the product is: a maximally realistic 28 m earthmover radial that stands
chocked in a yard, releases when approached, rolls like the real thing, and
whose cavity is a drivable hamster wheel - a car inside turns it through
nothing but contact physics. Entry is the player's problem (teleport/spawn);
that is accepted, not a defect.

WHAT IT IS NOW: "COLOSSUS 10350/80R457", 28.168 m OD, standing on its tread.
1,056 free carcass nodes (4,200 kg) + four free 201 kg chock wedges with
selfCollision, strapped to 16 buried collisionless anchors; 20 fixed nodes
total, all at or below grade, none collidable. One approach zone arms it; the
release beat cuts all 40 tie-down beams AND winches each wedge clear along
its own toe-to-heel axis (thrusters.applyImpulse, completion echoed to GE) -
because a wedge lying against the tread props the carcass through ramp
geometry even fully unstrapped (measured: 115 kNm held with 40/40 straps
audited broken).

=== WHAT CHANGED SINCE ROUND 4 (VERIFY, DO NOT TRUST) ===
1. FURNITURE STRIPPED: dock, gangway, port, tongue, lane marks, rider HUD,
   insideTire logic - all deleted. The carcass is a fully closed shell now
   (gate: assert_shell_rings_close demands it). Balance solves to x1.000.
2. JAGGED SIDEWALL FIXED: buttress rebuilt as a theta-dependent relief term
   (buttress_relief) on a 288-station visual lathe (1.25 deg, 0.84 mm
   sagitta), replacing the coarse add-on wraps the user saw as jagged.
3. STIFFENED x3.2 to the integrator ceiling after a crown mass re-split
   (MASS_FRACTIONS liner 0.19->0.25, crown 0.42->0.36): worst node omega*dt
   0.826 of a 0.90 gate. Static deflection 252->95 mm live, post-impact ring
   458->69 mm p-p, modes ~1.8x faster.
4. MASS 10,500 -> 6,000 -> 4,200 kg, each step scaling every beam family by
   the same factor (k/M and c/sqrt(kM) constant, so deflection, margins,
   damping ratios, patch all invariant). Driven by a measured law: the
   contact patch is a built-in chock - ground support migrates to the
   patch/second-facet edge (e ~ 2.0-2.7 m) and statically reacts (M+m)*g*e,
   so the hamster wheel turns only when m/(M+m) > e/(R sin phi). An etk800
   at 6t sat exactly on the line (115 kNm held, 0.2 m lean, no roll); the
   gate's subject is now a roamer, which clears it.
5. ROLLING RESISTANCE 6.2% -> 2.3% measured (free-coast decel / g). The
   residual loss lives in the engine contact model and scales with weight,
   not beams - beam damping, stiffness, and node friction (both directions)
   were each measured and none owned it.
6. CHOCKS ARE REAL NOW: previously fixed nodes without selfCollision - the
   tire never actually touched them (straps did everything, and the ram or
   gravity force-snapped the 95 kN straps, so breakBreakGroup was never
   load-bearing in any earlier gate). Now free bodies, honest steel friction
   (authored 0.55, measured effective ~0.87 because node frictionCoef
   multiplies the groundmodel's), seat gap 0.15 so the resting carcass never
   loads the wedge top, and the winch (1500 N per corner pair, 1.2 s) sized
   against MEASURED skid friction.
7. LIVE GATES, all green - rounds 1-4 never had ANY live evidence:
   - flat (smallgrid): settle 13.959 m axle (95 mm deflection), slip 1.02,
     steady ripple 7.3 mm RMS vs 30.2 mm facet sagitta, Crr 0.0227, ring
     69 mm p-p after a 10 m/s ram, coast, revolution counted, zone events.
   - hill (utah, three measured slopes, spawn SQUARE to the hill via a
     CALIBRATED slope quat - BeamNG reads rot_quat opposite-handed, the
     uncalibrated quat stood the tire side-on to the fall line): 3.4 deg
     chocked (creep < 1 m); 13.1 deg runaway - rolls off at slip 1.19 then
     carves into its lean and lies down (deliberately not asserted against:
     free tires do that); 22.9 deg thunders 38 of 40 m down the fall line,
     254 deg rotation, upright slip 0.81, over at ~38 m.
   - hamster (the mod's point): a roamer teleported into the cavity (spawn
     placement silently relocates vehicles spawned inside another - measured)
     lands on the inward-facing liner, arms the zone, the shipped release
     cuts+winches (audited 40/40, echo 8/8, wedge 5.0 m clear), and driving
     inside moves the tire 8.55 m at hamster slip 0.984 with the car still
     inside.
8. GATES: 24 geometry + 7 sequence + 3 texture = 34 static, plus the three
   live files. New since r4: fixed-nodes-are-untouchable gate, release
   component-walk (cut the group and the carcass, each wedge, and the anchor
   grid must all separate), winch-touches-only-chock-nodes gates (static +
   lupa), spawn-datum authored allowance (SPAWN_DATUM_BURIED_OK) for the
   buried anchors, weight-scaled relax residual.
9. Spin-up solve re-derived at 4,200 kg: 7.1 s measured vs (5,12) band.
   TKPH 42194 unchanged. k_gyr 12.56 m.

KNOWN AND DELIBERATE - do not spend findings on these:
 - 4,200 kg (vs ~1,900,000 honest) is the documented price of the hamster
   inequality; the user twice chose interactivity over the mass number.
 - No air/pressure model (damped truss), node-friction grip, not BeamNG
   wheel physics: it is a jbeam prop.
 - Carve-and-flop on hills is not asserted against - it is real free-tire
   behaviour.
 - PROCEDURAL SOUND is still absent. Rounds 3 and 4 both named it the
   largest single missing piece; spin_launch has a complete precedent
   pipeline. It remains deferred, not forgotten - weigh it honestly.
 - Liner COLLISION stays a 48-gon (28 mm sagitta): cars inside ride small
   bumps. Deferred; the hamster gate passes over it.
 - The repo is shared with another active session; failing tests in
   catapult_seesaw / high_five / pachinko_tower are theirs.
 - Round 4's full chair synthesis predates a context compaction and is not
   reproducible here; judge the CURRENT tree on its merits.

FILES (read what your lens needs):
  ${MOD}/spec.py                                  authored constants + Lua behaviour + the mass-solve essay
  ${MOD}/blender/create_colossus_tire.py          the deterministic generator
  ${MOD}/authoring/ericrolph_colossus_tire.handoff.json   measured physics handoff
  ${MOD}/mod/vehicles/ericrolph_colossus_tire/ericrolph_colossus_tire.jbeam
  ${MOD}/mod/vehicles/ericrolph_colossus_tire/main.materials.json
  ${MOD}/mod/vehicles/ericrolph_colossus_tire/ericrolph_colossus_tire.dae
  ${MOD}/mod/lua/ge/extensions/ericrolph_colossus_tire/runtime.lua
  ${MOD}/authoring/verify_render.py
  examples/giant_props/proplib/{texture_kit,blender_kit,prop_builder,lua_kit}.py
  tests/test_colossus_tire_{geometry,sequence,textures}.py
  tests/test_colossus_tire_{live,hill_live,hamster_live}.py
  tests/test_giant_props_pack.py, examples/giant_props/README.md, AGENTS.md

RENDERS (read as IMAGES; backface-culled, Standard view transform; 13 views,
all regenerated this morning from the current model):
  ${RENDERS}/hero.jpg ${RENDERS}/profile.jpg ${RENDERS}/face.jpg
  ${RENDERS}/tread_close.jpg ${RENDERS}/shoulder.jpg ${RENDERS}/buttress.jpg
  ${RENDERS}/bead.jpg ${RENDERS}/sidewall_type.jpg ${RENDERS}/sidewall_print.jpg
  ${RENDERS}/chocks.jpg ${RENDERS}/contact.jpg ${RENDERS}/scale.jpg
  ${RENDERS}/underside.jpg

MEASURED NOW: OD 28.168 m, section 10.350 m, cavity radius 13.150 m, cavity
floor 0.84 m above grade, tread depth 0.634 m, net-to-gross 70.1% (contact
face 80.1%), 288 visual stations, 263,784 visual triangles (0 degenerate);
cage 1,100 nodes (1,056 carcass 4,200 kg + 24 wedge 804 kg + 20 fixed),
4,862 beams, 3,280 collision triangles; k_gyr 12.56 m; spin-up 7.1 s; ZIP
55.2 MB, build serial 49, deterministic lock verified by every live gate.
All 34 static + 3 live colossus gates pass.

CONSTRAINTS (do not spend findings on these): jbeam "vehicle" props, one
connected cage; deterministic headless Blender 4.5.4; procedurally generated
PNG textures only.

YOUR JOB: same lens, same bar as rounds 1-4. "Utterly wowed" means you would
stop and stare. VERIFY the claims above against the actual files before
believing them - two previous rounds' worst defects were invisible to the
gates that existed. Every finding must name the file and symbol and say what
to do. If it is now excellent, say so plainly, and say what must NOT be
touched.
`

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['lens', 'wowed', 'verdict_reason', 'claims_verified', 'findings'],
  properties: {
    lens: { type: 'string' },
    wowed: { type: 'boolean' },
    verdict_reason: { type: 'string' },
    claims_verified: {
      type: 'array', maxItems: 12, items: { type: 'string' },
      description: 'context claims you actually checked against the tree, and whether they hold',
    },
    findings: {
      type: 'array', maxItems: 10,
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['severity', 'title', 'where', 'problem', 'fix'],
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'polish'] },
          title: { type: 'string', maxLength: 90 },
          where: { type: 'string' },
          problem: { type: 'string' },
          fix: { type: 'string' },
        },
      },
    },
  },
}

const LENSES = [
  ['tire-engineering', 'LENS: TIRE ENGINEERING REALISM. Tire design engineer who has stood next to 59/80R63 mining radials. The tire IS the product now - no furniture to hide behind. Judge the shoulder and buttress after the 288-station relief rebuild (the user called the old one "jagged" - is that dead?), the bead and rim seat, tread class/net-to-gross/pitch sequence, the sidewall type and print band, the crown arc, and whether the CHOCKS read as real yard hardware (geometry, proportions, placement under the shoulders, the seat gap). Use the renders AND the generator source.'],
  ['beamng-physics', 'LENS: BEAMNG PHYSICS AND JBEAM. Recompute BOTH integrator bounds and the damping ratios from the SHIPPED handoff at 4,200 kg - the context claims 0.826 worst; check it. Audit the new chock system end to end: wedge cages, selfCollision flags, anchor straps, the 40-beam break group, the component-walk claim (cut the group on paper and see what separates), the winch command in runtime.lua (does it really touch only chock nodes? is the force sized sanely?), and refNodes. Judge the mass-rescale reasoning in spec.py: is k/M-constant scaling actually sound, and are the live numbers consistent with the shipped constants?'],
  ['mesh-quality', 'LENS: GEOMETRY AND TOPOLOGY. Parse the SHIPPED .dae yourself (263,784 tris claimed). Face orientation independently of the generator asserts, degenerates/duplicates, non-manifold and unwelded edges, shell closure now that the doorway exception is gone, UV metric density and closure per material, the 288-station lathe (is the sagitta really sub-mm?), the buttress relief blend, and whether the triangle budget is well spent with the furniture gone. The renders are backface-culled - use them to spot-check.'],
  ['texture-materials', 'LENS: TEXTURE AND MATERIAL. Re-measure the shipped PNGs and main.materials.json. The palette shrank to 8 materials when the furniture died - is what remains coherent? Check sRGB sanity, roughness contrast, normal strengths, mip survival (the decametre bands), metric tiling against the DAE UVs, the sidewall print band legibility, and the chock hazard treatment. tests/test_colossus_tire_textures.py exists now - does it measure what matters, and would you add one check?'],
  ['gameplay', 'LENS: PLAYABILITY AND FEEL. The loop is new: walk/drive up, the machine arms, a countdown, CHOCKS CUT AND WINCHED CLEAR - four wedges yanked out from under 4.2 tonnes - then it is a free giant you can push, chase downhill, or drive around INSIDE as a hamster wheel. Read runtime.lua for the beats (messages, speed bands, revolution counts, capsize detection) and the three live gates for what actually happens. Judge: is the arming/release theatrical enough? Is losing the boarding beat a net loss or a purification? Is the hamster experience discoverable without a gate script doing the teleport? What SINGLE change would most improve it - and is missing SOUND still the answer?'],
  ['pipeline', 'LENS: REPO CONVENTION AND PIPELINE. Audit against AGENTS.md and the pack README: evidence chain (are the README/AGENTS numbers the CURRENT measurements?), determinism, one-cage rule vs the new component-walk release semantics, the shared-file changes this round (test_giant_props_pack.py spawn-datum allowance keyed on SPAWN_DATUM_BURIED_OK - safe for the other 22 mods? sumo xfail preserved?), stale docstrings/comments after the pivot (masses, node counts, deleted furniture references anywhere?), dead code (BEAM_SPECS still ships port_frame and gangway families - justified or cruft?), and whether the new gates measure the artifact rather than constants.'],
]

phase('Critique')
const reviews = (await parallel(
  LENSES.map(([key, brief]) => () =>
    agent(`${CONTEXT}\n\n${brief}\n\nSet "lens" to "${key}".`, {
      label: `r5:${key}`, phase: 'Critique', schema: SCHEMA,
    })
  )
)).filter(Boolean)

const notWowed = reviews.filter((r) => !r.wowed).map((r) => r.lens)
log(`${reviews.length}/6 reported; not wowed: ${notWowed.join(', ') || 'NONE - unanimous'}`)

phase('Synthesis')
const chair = await agent(
  `${CONTEXT}

Six critics have reported on ROUND 5. Their verdicts and findings:

${JSON.stringify(reviews, null, 2)}

As chair: verify what you cheaply can against the actual files and DROP any
finding that is factually wrong about the code (say which and why). Merge
duplicates. State the verdict. If it is not unanimous, give a SHORT ranked
work order - only what actually moves the result toward "utterly wowed", with
effort-vs-payoff called out per item. Also say explicitly what is now
excellent and must not be touched.`,
  {
    label: 'chair-r5', phase: 'Synthesis',
    schema: {
      type: 'object', additionalProperties: false,
      required: ['unanimous_wow', 'summary', 'do_not_touch', 'dropped', 'work_order'],
      properties: {
        unanimous_wow: { type: 'boolean' },
        summary: { type: 'string' },
        do_not_touch: { type: 'array', items: { type: 'string' }, maxItems: 10 },
        dropped: { type: 'array', items: { type: 'string' }, maxItems: 10 },
        work_order: {
          type: 'array', maxItems: 12,
          items: {
            type: 'object', additionalProperties: false,
            required: ['rank', 'title', 'where', 'instruction'],
            properties: {
              rank: { type: 'integer' },
              title: { type: 'string', maxLength: 90 },
              where: { type: 'string' },
              instruction: { type: 'string' },
            },
          },
        },
      },
    },
  }
)

return { verdicts: reviews.map((r) => ({ lens: r.lens, wowed: r.wowed })), chair }
