export const meta = {
  name: 'colossus-tire-critics-r2',
  description: 'Round 2 critic panel on the COLOSSUS giant rollable tire after the round-1 work order was applied',
  phases: [
    { title: 'Critique', detail: 'six specialist critics re-judge' },
    { title: 'Synthesis', detail: 'verdict and any remaining work order' },
  ],
}

const REPO = 'C:/Users/ericr/beamng-mcp'
const MOD = 'examples/giant_props/colossus_tire'
const RENDERS = `${REPO}/${MOD}/authoring/verify`

const CONTEXT = `
ROUND 2 review of a BeamNG.drive mod in the repo at ${REPO}.

THE USER'S BRIEF: build a giant rollable tire, large enough that a vehicle can
drive around INSIDE it as it rolls; driving in it should make it roll because
the tire obeys physics; "spare no polygon", it should look amazing at large
size with realistic details that sell it as a super-massive realistic tire;
highly detailed textures and geometry.

WHAT IT IS: "COLOSSUS 10350/80R457" - a 28.168 m outer diameter earthmover
radial standing on its tread. A genuine free physics body (1074 free jbeam
nodes); nothing about its motion is scripted. A car boards through a bolted
access port in the right sidewall via a loading dock and a boarding gangway
that hangs off the tire. Two ratchet straps hold it at spawn; the runtime cuts
them and the tire is free.

=== WHAT ROUND 1's PANEL FOUND AND WHAT WAS DONE ABOUT IT ===
All six of you said "not wowed". The work order was applied in full. Verify
these rather than taking them on trust - several were fixed by changing the
thing that MEASURES, so if a measurement is wrong the fix is wrong:

1. VISUAL WINDING. 100% of outer-sidewall and cavity-floor triangles faced
   inward; BeamNG backface-culls flexbodies. Fixed, and the generator now
   carries assert_face_orientation() with a per-surface rule table, run every
   build. The verify renders now set use_backface_culling on every material,
   so they show what the engine shows.
2. ENTRY CORRIDOR. All six dock deck collision triangles faced DOWN (a car
   fell through the ramp); the gangway had zero cage nodes; one sidewall band
   was uncut across the doorway. Dock deck now routes through
   add_oriented_quad; the gangway has a real 6x3 free-node cage with
   collision; a SILL meridian station was inserted at exactly CAVITY_RADIUS
   (spec.SILL_FRACTION) so the port cuts on a node ring.
3. CONTACT PATCH. A static solve found 2 contact nodes over 1.68 m. The beam
   families were re-measured into place by a parameter sweep against a
   unilateral-contact solver: steel x0.25, rubber x0.5, damping x sqrt of
   each. Crown arc kept realistic at 62 m. Now 11-15 contact nodes,
   8.25 m x 3.67 m patch, omega*dt 0.76.
4. SIZE CODE. 8400/80R580 was arithmetically a heavy-truck drive tire
   (OD/width 3.354). Now 10350/80R457: OD/width 2.722, rim/width 1.122, both
   inside the earthmover band, asserted at build time.
5. sRGB. Colour maps are now sRGB-encoded (opt-in per palette entry,
   texture_kit._srgb_encode + build_set(srgb=)). Tread colour mean went from
   byte 11.4 to 57.9.
6. TREAD. Net-to-gross was 35.3%; now 70.7% (asserted). Rows are fractions of
   TREAD_HALF, shoulder row is now the widest block, lug root growth cut from
   0.225 m/side to 0.085 so the groove floor is 0.186 m not 0.010.
7. LETTERING. Bands interpenetrated; now stacked and CENTRED by the generator
   between the bead and the first buttress rib, with a fit assert. Relief cut
   0.110 -> 0.040 with a moulded bevel.
8-10, 15. Roughness maps now do work; sidewall mould ripple is concentric not
   radial; bladder lattice 92 mm -> 18.7 mm; diamond plate 320 mm -> 50 mm;
   laminate bands are a partition of unity (no black hairlines) and the port
   cut now uses a SIDEWALL section (no belts in a sidewall) and is stepped
   into 7 plies instead of one flat band.
11. TIRE_MASS re-derived from ONE torque (the double-count is gone): 18,000 kg,
   spin-up 15.9 s, asserted.
12. CAVITY LIGHTING. Emissive lane chevrons every 3 stations down the floor.
13. RUNTIME. insideTire is now called (dismount payoff, re-boarding); the exit
   window is called by TIME not angle; a strap that parts on its own is
   detected from the tire having moved.
14. STRAPS. Softened so they are not in compression at spawn; the webbing is
   now skinned to the CARCASS so it rides away with the tire.
16, 19, 20, 22. Degenerate triangles: 0 (Mesh.face rejects by AREA now).
   Buttress feathers instead of collapsing. Metric UVs on the gangway, the
   buttress (accumulating v) and the lug walls. Stale figures corrected.
21. GATES. tests/test_colossus_tire_geometry.py (13 gates incl. a
   unilateral-contact static solve and the per-NODE Gershgorin integrator
   bound) plus three new pack-wide gates in tests/test_giant_props_pack.py:
   one-way-floor detection, thumbnail derivation, and behaviour node-name /
   breakGroup resolution.

KNOWN AND DELIBERATE, do not re-report:
 - examples/giant_props/high_five/ is ANOTHER SESSION's half-landed mod. Its
   failures and the pack mod-count tripwire are not this mod's.
 - test_certified_harvest_still_ships_dds[pachinko_tower] fails on a stale
   checked-in PNG; proven byte-identical output between HEAD's texture_kit and
   the current one, so it is not caused by this work.
 - BeamNG emissives light the surface, not the space. The cavity is dark by
   design with a lit path through it; real worklights need vehicle-side
   electrics and are explicitly deferred.

FILES (read what your lens needs):
  ${MOD}/spec.py                                  authored constants + Lua behaviour
  ${MOD}/blender/create_colossus_tire.py          the deterministic generator
  ${MOD}/authoring/ericrolph_colossus_tire.handoff.json   measured physics handoff
  ${MOD}/mod/vehicles/ericrolph_colossus_tire/ericrolph_colossus_tire.jbeam
  ${MOD}/mod/vehicles/ericrolph_colossus_tire/main.materials.json
  ${MOD}/mod/lua/ge/extensions/ericrolph_colossus_tire/runtime.lua
  ${MOD}/authoring/verify_render.py               the render harness
  examples/giant_props/proplib/texture_kit.py     texture families
  examples/giant_props/proplib/blender_kit.py     CageBuilder + exporters
  examples/giant_props/proplib/prop_builder.py    handoff -> jbeam/materials
  tests/test_colossus_tire_geometry.py            this mod's gates
  tests/test_giant_props_pack.py                  pack-wide gates
  examples/giant_props/README.md, AGENTS.md

RENDERS (read as IMAGES; all now backface-culled, Standard view transform):
  ${RENDERS}/hero.jpg ${RENDERS}/profile.jpg ${RENDERS}/scale.jpg
  ${RENDERS}/tread_close.jpg ${RENDERS}/shoulder.jpg ${RENDERS}/buttress.jpg
  ${RENDERS}/sidewall_print.jpg ${RENDERS}/port.jpg ${RENDERS}/port_face.jpg
  ${RENDERS}/port_close.jpg ${RENDERS}/gangway.jpg ${RENDERS}/cabin.jpg
  ${RENDERS}/cabin_far.jpg ${RENDERS}/floor.jpg ${RENDERS}/dock.jpg
  ${RENDERS}/underside.jpg

MEASURED NOW: OD 28.168 m, section width 10.350 m, cavity radius 13.150 m,
cavity lane 8.24 m, tread depth 0.634 m, 36 variable pitches, 179,872 visual
triangles, 0 degenerate; cage 1090 nodes / 4839 beams / 3226 collision
triangles; tire 18,000 kg; ZIP 43.2 MB. All 30 colossus gates pass.

CONSTRAINTS (do not spend findings on these): jbeam "vehicle" props, one
connected cage; deterministic headless Blender 4.5.4; procedurally generated
PNG textures only; the mass is a deliberate documented departure.

YOUR JOB: same lens as round 1, same bar. "Utterly wowed" means you would stop
and stare. Be honest about whether the round-1 fixes actually landed - check,
do not assume. Every finding must name the file and symbol and say what to do.
If it is now excellent, say so plainly.
`

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['lens', 'wowed', 'verdict_reason', 'round1_fixes_verified', 'findings'],
  properties: {
    lens: { type: 'string' },
    wowed: { type: 'boolean' },
    verdict_reason: { type: 'string' },
    round1_fixes_verified: {
      type: 'array', maxItems: 10, items: { type: 'string' },
      description: 'round-1 items you actually checked, and whether they landed',
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
  ['tire-engineering', 'LENS: TIRE ENGINEERING REALISM. Tire design engineer who has stood next to 59/80R63 mining radials. Re-check the size-code shape ratios, the section profile, the tread class and net-to-gross, lug geometry, the bead (now three meridian stations), the buttress wrap, the sidewall relief and type, the sidewall-section laminate at the port cut, and the sidewall facts (MAX LOAD, TKPH, DOT TIN format).'],
  ['beamng-physics', 'LENS: BEAMNG PHYSICS AND JBEAM. Will it roll, hold shape and behave at 2000 Hz with a car inside? Re-check the softened beam families against BOTH bounds, the contact patch, collision winding on every band, the gangway cage, the port cut, the straps, refnodes, and what happens 300 m from the dock. Recompute; do not trust the summary.'],
  ['mesh-quality', 'LENS: GEOMETRY AND TOPOLOGY. Re-check face orientation independently of the generator assert (it could be testing the wrong thing), degenerate/coincident geometry, UV metric density and closure, smooth/flat shading, watertightness, and whether the 180k triangle budget is now well spent. Look hard at the culled renders for holes, seams and z-fighting.'],
  ['texture-materials', 'LENS: TEXTURE AND MATERIAL. Re-measure the shipped PNGs. Is the sRGB encode right and are the values now sane? Do the roughness maps do work? Are the feature frequencies resolvable at the metric tiling? Judge the laminate sidewall section, the bladder lattice, the diamond plate, the bloom mask, and the emissive lane marks (material JSON included).'],
  ['gameplay', 'LENS: PLAYABILITY AND FEEL. Walk the whole loop against measured clearances with a 2.0 x 4.5 x 1.5 m car: dock, gangway, port, the 90 degree turn in an 8.24 m lane, spin-up, rolling, the exit window, tipping over. Read the runtime and judge the state machine and the beats. Is it FUN? What single change would most improve it now?'],
  ['pipeline', 'LENS: REPO CONVENTION AND PIPELINE. Audit against AGENTS.md and the pack README: evidence chain, determinism, one-cage rule, SHIP_ASSETS, generated-never-hand-edited, whether the new gates actually catch what they claim, whether the shared texture_kit/prop_builder/blender_kit changes are safe for the other 20 mods, and dead code or stale comments left behind.'],
]

phase('Critique')
const reviews = (await parallel(
  LENSES.map(([key, brief]) => () =>
    agent(`${CONTEXT}\n\n${brief}\n\nSet "lens" to "${key}".`, {
      label: `r2:${key}`, phase: 'Critique', schema: SCHEMA,
    })
  )
)).filter(Boolean)

const notWowed = reviews.filter((r) => !r.wowed).map((r) => r.lens)
log(`${reviews.length}/6 reported; not wowed: ${notWowed.join(', ') || 'NONE - unanimous'}`)

phase('Synthesis')
const chair = await agent(
  `${CONTEXT}

Six critics have reported on ROUND 2. Their verdicts and findings:

${JSON.stringify(reviews, null, 2)}

As chair: verify what you cheaply can against the actual files and DROP any
finding that is factually wrong about the code (say which and why). Merge
duplicates. Then state the verdict and, if it is not unanimous, give a ranked
work order of concrete instructions. Keep it short - only what actually moves
the result.`,
  {
    label: 'chair-r2', phase: 'Synthesis',
    schema: {
      type: 'object', additionalProperties: false,
      required: ['unanimous_wow', 'summary', 'dropped', 'work_order'],
      properties: {
        unanimous_wow: { type: 'boolean' },
        summary: { type: 'string' },
        dropped: { type: 'array', items: { type: 'string' }, maxItems: 10 },
        work_order: {
          type: 'array', maxItems: 14,
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
