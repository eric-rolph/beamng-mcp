export const meta = {
  name: 'colossus-tire-critics-r3',
  description: 'Round 3 critic panel on the COLOSSUS giant rollable tire after the round-2 work order was applied',
  phases: [
    { title: 'Critique', detail: 'six specialist critics re-judge round 3' },
    { title: 'Synthesis', detail: 'verdict and any remaining work order' },
  ],
}

const REPO = 'C:/Users/ericr/beamng-mcp'
const MOD = 'examples/giant_props/colossus_tire'
const RENDERS = `${REPO}/${MOD}/authoring/verify`

const CONTEXT = `
ROUND 3 review of a BeamNG.drive mod in the repo at ${REPO}.

THE USER'S BRIEF: build a giant rollable tire, large enough that a vehicle can
drive around INSIDE it as it rolls; driving in it should make it roll because
the tire obeys physics; "spare no polygon", it should look amazing at large
size with realistic details that sell it as a super-massive realistic tire;
highly detailed textures and geometry.

WHAT IT IS: "COLOSSUS 10350/80R457" - a 28.168 m outer diameter earthmover
radial standing on its tread. A genuine free physics body (1072 free jbeam
nodes); nothing about its motion is scripted. A car boards through a bolted
access port in the right sidewall via a loading dock and a boarding gangway
that hangs off the tire. Two ratchet straps plus two landing struts hold it at
spawn, all in one break group; the runtime cuts them and the tire is free.

=== WHAT ROUND 2's PANEL FOUND AND WHAT WAS DONE ABOUT IT ===
All six said not wowed. The chair's work order was applied in full. VERIFY
these rather than trusting them - several were fixed by changing the thing
that MEASURES, so a wrong measurement means a wrong fix:

1. NO SHOULDER. The outer lathe ran past its last meridian station with the
   half width clamped, giving an axially-facing flange ring at |x| = 4.712
   reaching the crown radius. FIXED: meridian_fractions() now stops at
   SHL_FRACTION and build_carcass lofts an explicit shoulder
   (shoulder_point()/outer_half_at()) to the tread base's outboard ring. The
   buttress wrap was re-anchored onto that same surface.
2. DOORWAY NOT PASSABLE. FIXED three ways: nine sidewall nodes strictly
   interior to the port now have collision:false (the generator prints the
   count); TONGUE_HALF_ARC_DEG is derived as PORT_SPAN_DEG/2 so the gangway
   covers exactly what the port cut removes; and the gangway now has real
   landing struts to the dock in the tie-down break group, because
   selfCollision is false so it could not rest on the quay.
3. ROLLING INERTIA. The mass solve now uses I_cm + M*R^2 about the CONTACT
   POINT. TIRE_MASS 18000 -> 10500 kg, mu_eff 0.65 -> 0.75, target 18 s,
   measured spin-up 19.4 s. Every beamSpring was scaled by the same factor
   and every beamDamp by its square root, so the measured contact patch and
   the damping ratios survive the mass change.
4. MESH vs SIZE CODE. _MERIDIAN_BASE is now the OUTER surface with 1.000 at
   maximum section width, so the mesh measures exactly 10.350 m across; the
   bead station is chosen so the INNER face lands on the reference tire's
   0.746 rim-to-section-width ratio (measured 0.7455).
5. behavior.onExit now takes (state, zone, id) to match the runtime's call
   sites. Score is per-RIDE (rideDistance0/rideTurns0), not the lifetime
   odometer. The exit countdown refreshes every frame instead of latching.
   Tipping has three derived beats (leaning / going over / down) instead of
   one at 46 deg. A persistent HUD line in its own message category shows
   PORT time, LEAN, speed and ride distance while a rider is aboard.
6. refNodes now uses two purpose-built datum nodes (ground_left, ground_up)
   instead of reusing deck corners, so the triad is not degenerate.
7. tile_wraps() takes a reference radius and every circumferential UV routes
   through it - tread, liner, fillet, bead, shoulder - so they all close.
8. build_lettering shifts by the half-extrusion instead of clamping
   max(local.z, 0), so no glyph's back half collapses onto one plane; a
   DISSOLVE decimate dropped the type from 80,776 tris (45%) to ~31k (22%).
   Type bands are stacked and CENTRED by the generator between the bead and
   the first buttress rib with a fit assert.
9. Row phasing is now on the GLOBAL pitch grid, so the lateral groove keeps
   its authored 0.360 m instead of absorbing pitch-length changes.
10. ONE TILE PER MATERIAL (MATERIAL_TILE / tile_of()), so the same material
   is not authored at several densities. Steel measures 1.600 m/tile
   everywhere, hazard 1.200.
11. lane_mark has a real emissiveMap (hazard_chevron glow=True), so the
   chevron stripes do not glow uniformly. Blank normal maps fixed: steel,
   steel_worn, hazard, lane_mark, strap and concrete now carry real relief.
   A decametre band (base_cells=1) was added to tread/sidewall/liner
   roughness and albedo so something survives mipping to a whole-tire
   framing. tire_bead's burnish band is now periodic.
12. SHARED-CODE SAFETY: the hazard_chevron and steel relief changes are
   OPT-IN (relief defaults to the old behaviour) after an earlier version of
   them silently re-cut boot_of_doom's maps.
13. NEW ASSERTS in the generator: assert_face_orientation now FAILS on an
   object with no rule instead of skipping it (with a named exempt list);
   assert_outboard_clearance MEASURES every tire vertex against DOCK_CLEAR_X
   and caught the port bezel reaching 5.805 m, which would have destroyed the
   dock - the frame was reduced and the dock moved to 5.675 m, now 5.529 m
   measured with 0.146 m clearance; assert_no_coincident_nodes; plus the
   existing size-code, net-to-gross, groove-floor, gyration and spin-up
   checks.
14. The exported Collada stamped WALL-CLOCK time, so no DAE in the pack is
   byte-reproducible. normalise_collada() fixes it for this mod (proven:
   two consecutive generator runs now produce identical bytes) and a gate
   guards it. Fixing it in blender_kit would invalidate twenty other mods'
   hashes at once, so it is deliberately local.
15. NEW GATES: tests/test_colossus_tire_sequence.py runs the REAL generated
   runtime.lua under lupa (6 tests: axle fit + revolution counting, release
   claimed from movement not from the queued command, strap-parted
   detection, the dismount payoff, tipping, and that the runtime drives
   nothing). tests/test_colossus_tire_geometry.py is now 14 tests including
   a unilateral-contact static solve.

KNOWN AND DELIBERATE, do not re-report:
 - test_certified_harvest_still_ships_dds[pachinko_tower] fails on a stale
   checked-in PNG. Proven byte-identical output between HEAD's texture_kit
   and the current one across every pachinko material, so it is not caused
   by this work. Another session edits this repo concurrently.
 - BeamNG emissives light the surface, not the space. The cavity is dark by
   design with a lit path through it; real worklights need vehicle-side
   electrics and are explicitly deferred.
 - The mod has NOT been run in BeamNG yet. Static and headless only.

STILL OPEN from round 2's work order (say if these still matter most):
 - no gate parses the exported .dae itself;
 - the letters use the sidewall_print legend texture, bounding-box mapped,
   rather than their own material or a metric unwrap;
 - there is no real small-print band as a lathed ring;
 - laminate and strap textures are not wrap-tileable.

FILES (read what your lens needs):
  ${MOD}/spec.py                                  authored constants + Lua behaviour
  ${MOD}/blender/create_colossus_tire.py          the deterministic generator
  ${MOD}/authoring/ericrolph_colossus_tire.handoff.json   measured physics handoff
  ${MOD}/mod/vehicles/ericrolph_colossus_tire/ericrolph_colossus_tire.jbeam
  ${MOD}/mod/vehicles/ericrolph_colossus_tire/main.materials.json
  ${MOD}/mod/vehicles/ericrolph_colossus_tire/ericrolph_colossus_tire.dae
  ${MOD}/mod/lua/ge/extensions/ericrolph_colossus_tire/runtime.lua
  ${MOD}/authoring/verify_render.py
  examples/giant_props/proplib/{texture_kit,blender_kit,prop_builder,lua_kit}.py
  tests/test_colossus_tire_geometry.py, tests/test_colossus_tire_sequence.py
  tests/test_giant_props_pack.py, examples/giant_props/README.md, AGENTS.md

RENDERS (read as IMAGES; backface-culled, Standard view transform):
  ${RENDERS}/hero.jpg ${RENDERS}/profile.jpg ${RENDERS}/scale.jpg
  ${RENDERS}/tread_close.jpg ${RENDERS}/shoulder.jpg ${RENDERS}/buttress.jpg
  ${RENDERS}/sidewall_print.jpg ${RENDERS}/port.jpg ${RENDERS}/port_face.jpg
  ${RENDERS}/port_close.jpg ${RENDERS}/gangway.jpg ${RENDERS}/cabin.jpg
  ${RENDERS}/cabin_far.jpg ${RENDERS}/floor.jpg ${RENDERS}/dock.jpg
  ${RENDERS}/underside.jpg

MEASURED NOW: OD 28.168 m, section width 10.350 m (mesh == code), cavity
radius 13.150 m, lane 7.93 m, tread depth 0.634 m, net-to-gross 70.7%,
36 variable pitches, 147,204 visual triangles / 0 degenerate; cage 1090 nodes
/ 4842 beams / 3226 collision triangles; tire 10,500 kg; k_gyr 12.67 m;
spin-up 19.4 s; outboard reach 5.529 m against DOCK_CLEAR_X 5.675 m; ZIP
40.2 MB, build serial 21. All 41 colossus gates pass.

CONSTRAINTS (do not spend findings on these): jbeam "vehicle" props, one
connected cage; deterministic headless Blender 4.5.4; procedurally generated
PNG textures only; the mass is a deliberate documented departure.

YOUR JOB: same lens, same bar. "Utterly wowed" means you would stop and
stare. CHECK whether the round-2 fixes actually landed - do not assume. Every
finding must name the file and symbol and say what to do. If it is now
excellent, say so plainly, and say what must NOT be touched.
`

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['lens', 'wowed', 'verdict_reason', 'round2_fixes_verified', 'findings'],
  properties: {
    lens: { type: 'string' },
    wowed: { type: 'boolean' },
    verdict_reason: { type: 'string' },
    round2_fixes_verified: {
      type: 'array', maxItems: 12, items: { type: 'string' },
      description: 'round-2 items you actually checked, and whether they landed',
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
  ['tire-engineering', 'LENS: TIRE ENGINEERING REALISM. Tire design engineer who has stood next to 59/80R63 mining radials. Re-check the shoulder now that it is lofted, the outer-surface meridian and whether the mesh really measures its size code, the bead, the tread class and net-to-gross, the lateral groove after the global-pitch-grid fix, the buttress wrap, the sidewall relief and type, the sidewall-section laminate, and the sidewall facts.'],
  ['beamng-physics', 'LENS: BEAMNG PHYSICS AND JBEAM. Will it roll, hold shape and behave at 2000 Hz with a car inside, at 10,500 kg? Recompute BOTH integrator bounds and the contact patch from the shipped handoff. Re-check every collision band, the doorway now that nine nodes were cleared, the gangway cage and its landing struts, the break-group chain, the refNodes triad, and the rolling-inertia solve.'],
  ['mesh-quality', 'LENS: GEOMETRY AND TOPOLOGY. Parse the SHIPPED .dae yourself. Check face orientation independently of the generator assert, degenerate/coincident/duplicate geometry, non-manifold and unwelded edges, whether the shell closes at the new shoulder, UV metric density and closure per material, and whether the 147k budget is now well spent. The renders are backface-culled.'],
  ['texture-materials', 'LENS: TEXTURE AND MATERIAL. Re-measure the shipped PNGs and the material JSON. Check the sRGB values, roughness contrast, the new decametre band across mip levels, feature frequencies against the metric tiling, tileability, the lane_mark emissive map, the previously-blank normal maps, and per-material UV density in the DAE.'],
  ['gameplay', 'LENS: PLAYABILITY AND FEEL. Walk the whole loop against measured clearances with a 2.0 x 4.5 x 1.5 m car: dock, gangway (now with landing struts), port, the 90 degree turn in a 7.93 m lane, spin-up at 19.4 s, rolling, the HUD, the exit window, the three lean beats, tipping. Read the runtime and judge the state machine. Is it FUN? What single change would most improve it now?'],
  ['pipeline', 'LENS: REPO CONVENTION AND PIPELINE. Audit against AGENTS.md and the pack README: evidence chain, determinism (the Collada normalisation is new - verify it), one-cage rule, generated-never-hand-edited, whether the new asserts and gates catch what they claim, whether the shared texture_kit/prop_builder/blender_kit changes are safe for the other 20 mods, and dead code or stale comments.'],
]

phase('Critique')
const reviews = (await parallel(
  LENSES.map(([key, brief]) => () =>
    agent(`${CONTEXT}\n\n${brief}\n\nSet "lens" to "${key}".`, {
      label: `r3:${key}`, phase: 'Critique', schema: SCHEMA,
    })
  )
)).filter(Boolean)

const notWowed = reviews.filter((r) => !r.wowed).map((r) => r.lens)
log(`${reviews.length}/6 reported; not wowed: ${notWowed.join(', ') || 'NONE - unanimous'}`)

phase('Synthesis')
const chair = await agent(
  `${CONTEXT}

Six critics have reported on ROUND 3. Their verdicts and findings:

${JSON.stringify(reviews, null, 2)}

As chair: verify what you cheaply can against the actual files and DROP any
finding that is factually wrong about the code (say which and why). Merge
duplicates. State the verdict. If it is not unanimous, give a SHORT ranked
work order - only what actually moves the result toward "utterly wowed".
Also say explicitly what is now excellent and must not be touched.`,
  {
    label: 'chair-r3', phase: 'Synthesis',
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
