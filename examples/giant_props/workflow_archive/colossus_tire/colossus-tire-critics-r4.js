export const meta = {
  name: 'colossus-tire-critics-r4',
  description: 'Round 4 critic panel on the COLOSSUS giant rollable tire after the round-3 work order was applied and the mod was proven live in BeamNG',
  phases: [
    { title: 'Critique', detail: 'six specialist critics re-judge round 4' },
    { title: 'Synthesis', detail: 'verdict and any remaining work order' },
  ],
}

const REPO = 'C:/Users/ericr/beamng-mcp'
const MOD = 'examples/giant_props/colossus_tire'
const RENDERS = `${REPO}/${MOD}/authoring/verify`

const CONTEXT = `
ROUND 4 review of a BeamNG.drive mod in the repo at ${REPO}.

THE USER'S BRIEF: build a giant rollable tire, large enough that a vehicle can
drive around INSIDE it as it rolls; driving in it should make it roll because
the tire obeys physics; "spare no polygon", it should look amazing at large
size with realistic details that sell it as a super-massive realistic tire;
highly detailed textures and geometry.

WHAT IT IS: "COLOSSUS 10350/80R457" - a 28.168 m outer diameter earthmover
radial standing on its tread. A genuine free physics body (1072 free jbeam
nodes); nothing about its motion is scripted. A car boards through a bolted
access port in the right sidewall via a loading dock and a boarding gangway
that hangs off the tire. Ratchet straps plus four landing posts hold it at
spawn, all in one break group; the runtime cuts them and the tire is free.

IT NOW RUNS LIVE. tests/test_colossus_tire_live.py boots BeamNG 0.39.4 headless
in a sentinel-isolated profile, installs the packaged ZIP after checking it
against its lock, and passes: settled axle 13.749 m, fitted radius 13.776 m,
lean 0.063; a car parks on the dock at z 0.706 and inside the cabin at z 1.081
(so both floors are solid FROM ABOVE); the subject drives in and the cabin
trigger fires; and pushing the SUBJECT rolls the tire 7.40 m of axle travel.
No engine log issues.

=== WHAT ROUND 3's PANEL FOUND AND WHAT WAS DONE ABOUT IT ===
All six said not wowed and the panel converged. The chair's 12-item work order
was applied in full. VERIFY these rather than trusting them:

1. SHOULDER SLOT (their worst finding). shell(f,"outer") returns
   sidewall_outer + sidewall_relief but shoulder_point(0) returned
   sidewall_outer alone, so an open 0.0671 m annulus rang both shoulders,
   84.85 m each, culling to sky. FIXED: shoulder_point() carries the relief at
   the top station and dies it into the tread base. AND a new gate,
   assert_shell_rings_close(), welds the seven carcass surfaces and asserts the
   ONLY open boundary is the doorway - it prints "COLOSSUS carcass: closed
   everywhere except the doorway". That one gate covers this, the trench and
   the buttress float at once.
2. INNER LATHE OVERRUN. inner_fractions ran index/13 to 1.000 (radius 14.0839
   = OUTER_RADIUS, half width clamped), so the liner carried on 0.93 m past
   the cavity floor down to z = 0: a trench down both lane edges, full
   circumference. FIXED: the ladder is capped at spec.SILL_FRACTION and the
   fillet is aimed there; assert_surfaces_stay_home() proves no liner vertex
   exceeds CAVITY_RADIUS (prints "liner tops out at radius 13.150").
3. TYPE THROUGH THE PRINT RING. build_print_band sat at a hand-picked radius
   WHOLLY INSIDE the SIZE_CODE band. FIXED: spec.BAND_STACK is one derived
   ladder carrying BRAND / PATTERN_NAME / SIZE_CODE / PRINT_BAND, and
   PRINT_BAND_RADIUS is read out of it. Two asserts: every band inside the
   window, and no two bands closer than BAND_GAP. The window floor also moved
   up to clear the RIM LINE rib, and LETTER_HEIGHT 1.75 -> 1.45 to fit (1.45 m
   divides back to 206 mm at reference scale). BUILD_CODE left the moulded
   stack: a DOT TIN is small print and it is already one of the four lines the
   print ring carries.
4. LETTERING. Three defects: recalc_face_normals ran BEFORE an unapplied
   DECIMATE so 3,906 edges came out traversed the same way by both faces and
   27% of the type faced inward; the unwrap read only (y,z) while the extrusion
   runs in x, so 25.6% of the material had world area and ZERO uv area; and
   resolution_u=1 / bevel_resolution=0 made every bowl an octagon. FIXED: the
   whole thing is one bmesh block - remove_doubles FIRST (a converted glyph has
   ~1,850 boundary edges and is not a closed solid, which is exactly why
   recalc could not orient it), then dissolve_degenerate to kill the outline
   slivers, then dissolve_limit, triangulate, and recalc_face_normals LAST.
   resolution_u=3, bevel_resolution=1. The relief now equals LETTER_RELIEF
   exactly. The unwrap carries the standoff into both u and v.
5. ZIGZAG. GROOVE_ZIGZAG's sign was keyed to the LUG, so the two walls of each
   lateral groove swung in opposition: measured 0.062 m (interpenetration) and
   0.442 m against an authored 0.360. FIXED: groove_zigzag(boundary) keys the
   amplitude to the BOUNDARY and add_lug blends lead->trail across the block,
   so both walls of any groove move together at constant width. The tie bar
   takes the same wander.
6. BUTTRESS FLOAT. top_radius = crown_r(TREAD_HALF) = 13.9457 but the shoulder
   loft tops out at 13.5094, and outer_half_at's 24-step nearest-radius scan
   returned the same clamped answer for the first two rows. FIXED:
   outer_half_at is a real inverse (bisection on the loft's descending branch,
   with the loft's non-monotonic peak found once), top_radius is the loft's
   peak, and the wrap now has a top cap. While closing it, the wrap's TWO END
   WALLS AND ITS BOTTOM LIP were found wound inside out - 1,020 same-direction
   edges in one object, invisible to the orientation assert because an end wall
   is perpendicular to the shell and that rule declines to judge it.
7. refNODES MIRRORED. Measured across all 23 shipped jbeams: 22 return
   left - ref = +X and one sign of cross(left-ref, back-ref).(up-ref);
   colossus alone returned the opposite of both. FIXED (ground_left moved to
   x2 - 3.2) and tests/test_giant_props_pack.py now pins the handedness for
   the whole pack.
8. GAMEPLAY. updateExitWindow returned without writing b.exitIn, so the HUD
   froze on a stale countdown for the whole 1.2 s the port was down; and
   insideTire's threshold is crossed at ~20 deg of lean, so a CAPSIZE scored
   "CLEAR. NEW BEST." 24 deg before "COLOSSUS IS DOWN". FIXED: the window
   writes b.exitNow/b.exitIn and the HUD has three door states; a dismount is
   credited only when the door was open AND the tire upright, otherwise "OUT
   THROUGH THE WALL, no credit"; updateTipped runs FIRST and tipping is
   terminal; the odometer and speed callouts moved to a THIRD message
   category so they cannot wipe the door call; the HUD is throttled to 10 Hz.
9. CLEARANCE ASSERTS. The old one defended a CONSTANT. Replaced with a real
   swept-volume measurement: the tire's max |x| versus radius profile against
   every dock vertex (reports "nearest fixed approach 1.675 m"), plus a new
   assert_tongue_sweep() that rotates every gangway vertex through 90 degrees
   against the dock's boxes. It immediately found the tongue's stiffener ribs
   12 mm inside the leading girder AT REST, and the dock kerb and handrail
   were moved to start at DOCK_LANDING_X1 so the quay's ship side is open.
10. RENDER CHANNELS. A leftover lane_mark_opacity.data.png was punching holes
   through the chevrons in every verify render - ensure_textures now prunes
   orphans. blender_kit gained a _glow.color.png branch, and its emission
   wiring is now OPT-IN (it was unconditionally changing the exported DAE of
   seven other specs). The glow map is neutral greyscale so hue lives once.
11. normal_strength WAS DEAD. prop_builder reads it as
   entry["texture"]["normal_strength"]; all thirteen colossus values sat at the
   entry level and every map was baked at the default 2.0. The laminate - the
   cut edge at the port, the surface forty lines of spec prose are about - had
   95% of its texels under one degree of slope while every other map reached
   25-52 degrees. All thirteen moved inside and were then MEASURED and tuned;
   the whole set now lands between 12 and 46 degrees at p99.9.
12. DETERMINISM. Round 3's "proven byte-identical" was wrong - it pinned the
   timestamps and never touched the exporter's ULP jitter, which .gitignore
   has recorded since 2026-08. normalise_collada() now re-emits every
   float_array at FIVE decimals (six still let 97 values flip); two
   consecutive full generator runs are now byte-identical, measured.
13. STALE FACTS retired: "Eighteen tonnes" is derived from B.tire_mass; the
   dead RNG, sidewall_surface() and ring_uv() are gone; four headers said
   8400/80R580; the README's counts; the false ALLOW_SUBJECT_MUTATION
   uniqueness claim (catapult_seesaw does it too); CAVITY_LANE's 8.68 m
   comment; a REQUIRED table so the pack's tunable gate stops skipping this
   mod (which also exposed that the gate's block parser stopped at the first
   brace and could not read a nested table).
14. A PRINT RING NOBODY HAD EVER SEEN. verify_render.py's scene() never called
   build_print_band, so the small-print ring was absent from every image the
   round-3 panel judged - the second time that list drifted from main()'s. It
   is now called, its camera is DERIVED from the band stack, and a gate
   compares the two builder lists. The legend also needed a whole number of
   sheets at the family's authored 6:1 aspect (it was being mapped at the
   sidewall's 24 tiles, i.e. 24 copies of a 6:1 legend squashed into 2:1).

KNOWN AND DELIBERATE, do not re-report:
 - test_certified_harvest_still_ships_dds[pachinko_tower] fails because
   ANOTHER SESSION has pachinko_tower/spec.py modified in the working tree
   ("25 PIN" -> "28 PIN"), which invalidates its cooked-DDS harvest. Not this
   work; git diff confirms it.
 - BeamNG emissives light the surface, not the space. The cavity is dark by
   design with a lit path through it; real worklights need vehicle-side
   electrics and are explicitly deferred.
 - The tire's MASS (10,500 kg) is a documented departure, solved backwards
   from playability through the contact-point rolling inertia. The MAX LOAD on
   the sidewall is derived as pressure x footprint, i.e. scale squared, and is
   deliberately not reconciled with the mass.
 - The prop has no SOUND. Round 3's chair called that the largest remaining
   feel-per-line change; it is noted and not yet done. Say if you agree.

FILES (read what your lens needs):
  ${MOD}/spec.py                                  authored constants + Lua behaviour
  ${MOD}/blender/create_colossus_tire.py          the deterministic generator
  ${MOD}/authoring/ericrolph_colossus_tire.handoff.json   measured physics handoff
  ${MOD}/mod/vehicles/ericrolph_colossus_tire/ericrolph_colossus_tire.jbeam
  ${MOD}/mod/vehicles/ericrolph_colossus_tire/main.materials.json
  ${MOD}/mod/vehicles/ericrolph_colossus_tire/ericrolph_colossus_tire.dae
  ${MOD}/mod/lua/ge/extensions/ericrolph_colossus_tire/runtime.lua
  ${MOD}/authoring/verify_render.py
  ${MOD}/textures/*.png
  examples/giant_props/proplib/{texture_kit,blender_kit,prop_builder,lua_kit}.py
  tests/test_colossus_tire_geometry.py, tests/test_colossus_tire_sequence.py
  tests/test_colossus_tire_live.py
  tests/test_giant_props_pack.py, examples/giant_props/README.md, AGENTS.md

RENDERS (read as IMAGES; backface-culled, Standard view transform):
  ${RENDERS}/hero.jpg ${RENDERS}/profile.jpg ${RENDERS}/scale.jpg
  ${RENDERS}/tread_close.jpg ${RENDERS}/shoulder.jpg ${RENDERS}/buttress.jpg
  ${RENDERS}/sidewall_type.jpg ${RENDERS}/sidewall_print.jpg
  ${RENDERS}/port.jpg ${RENDERS}/port_face.jpg ${RENDERS}/port_close.jpg
  ${RENDERS}/gangway.jpg ${RENDERS}/cabin.jpg ${RENDERS}/cabin_far.jpg
  ${RENDERS}/floor.jpg ${RENDERS}/dock.jpg ${RENDERS}/underside.jpg

MEASURED NOW: OD 28.168 m, section width 10.350 m, cavity radius 13.150 m,
lane 7.93 m, tread depth 0.634 m, net-to-gross 70.1% at the moulded land datum
with the flat contact face 80.1% of that (BOTH summed from the crown polygons
the generator actually built, not from the row table), 36 variable pitches,
214,104 visual triangles with ZERO degenerate, ZERO duplicated, ZERO edges
traversed the same way by both faces and ZERO triangles with world area and no
UV area; cage 1094 nodes / 4860 beams / 3226 collision triangles; tire
10,500 kg; k_gyr 12.67 m; spin-up 19.4 s; outboard reach 5.529 m with the
nearest fixed approach 1.675 m; ZIP 48.6 MB, build serial 28.

GATES: 23 colossus geometry gates + 8 lupa runtime gates + 1 live BeamNG gate,
all green, plus the whole pack suite (1,615 passed). RUN THEM YOURSELF with
.venv\\\\Scripts\\\\python.exe - a bare python has no lupa and silently skips the
runtime gates, which is what happened to the round-3 panel.

CONSTRAINTS (do not spend findings on these): jbeam "vehicle" props, one
connected cage; deterministic headless Blender 4.5.4; procedurally generated
PNG textures only.

YOUR JOB: same lens, same bar. "Utterly wowed" means you would stop and stare.
CHECK whether the round-3 fixes actually landed - do not assume, and several
were fixed by changing the thing that MEASURES. Every finding must name the
file and symbol and say what to do. If it is now excellent, say so plainly,
and say what must NOT be touched.
`

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['lens', 'wowed', 'verdict_reason', 'round3_fixes_verified', 'findings'],
  properties: {
    lens: { type: 'string' },
    wowed: { type: 'boolean' },
    verdict_reason: { type: 'string' },
    round3_fixes_verified: {
      type: 'array', maxItems: 14, items: { type: 'string' },
      description: 'round-3 items you actually checked, and whether they landed',
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
  ['tire-engineering', 'LENS: TIRE ENGINEERING REALISM. Tire design engineer who has stood next to 59/80R63 mining radials. Re-check the shoulder now that the relief carries into the loft, the outer-surface meridian and whether the mesh really measures its size code now that the named stations are seeded, the bead, the tread class, BOTH net-to-gross numbers and what they mean, the lateral groove after the boundary-keyed zigzag, the buttress wrap and its new top cap, the sidewall relief, the new band stack and the small-print ring, and the sidewall facts.'],
  ['beamng-physics', 'LENS: BEAMNG PHYSICS AND JBEAM. Will it roll, hold shape and behave at 2000 Hz with a car inside, at 10,500 kg? Recompute BOTH integrator bounds and the contact patch from the shipped handoff. Re-check every collision band, the doorway, the gangway cage and its FOUR new landing posts, the break-group chain, the refNodes triad, and the rolling-inertia solve. The static solver now runs to a residual and proves the ground plus the dock carry the free weight - check that argument.'],
  ['mesh-quality', 'LENS: GEOMETRY AND TOPOLOGY. Parse the SHIPPED .dae yourself. Check face orientation independently of the generator assert, degenerate/coincident/duplicate geometry, non-manifold and unwelded edges, whether the carcass really closes now, UV metric density and closure per material, and whether the 214k budget is well spent - the moulded type is 89k of it, which is 42%. The renders are backface-culled.'],
  ['texture-materials', 'LENS: TEXTURE AND MATERIAL. Re-measure the shipped PNGs and the material JSON. normal_strength was dead for three rounds and is now live and hand-tuned - check every one of the fourteen against what its surface should look like. Check sRGB, roughness contrast, feature frequencies against the metric tiling, tileability, the lane_mark emissive now that it is neutral, and per-material UV density in the DAE.'],
  ['gameplay', 'LENS: PLAYABILITY AND FEEL. Walk the whole loop against measured clearances with a 2.0 x 4.5 x 1.5 m car: dock, gangway, port, the 90 degree turn in a 7.93 m lane, spin-up at 19.4 s, rolling, the HUD, the exit window, the three lean beats, tipping, and the new no-credit wall exit. Read the runtime and judge the state machine. Is it FUN? What single change would most improve it now?'],
  ['pipeline', 'LENS: REPO CONVENTION AND PIPELINE. Audit against AGENTS.md and the pack README: evidence chain, determinism (the five-decimal Collada quantisation is new - verify two runs yourself if you can), one-cage rule, generated-never-hand-edited, whether the new asserts and gates catch what they claim, whether the shared texture_kit/prop_builder/blender_kit changes are safe for the other 22 mods, and dead code or stale comments.'],
]

phase('Critique')
const reviews = (await parallel(
  LENSES.map(([key, brief]) => () =>
    agent(`${CONTEXT}\n\n${brief}\n\nSet "lens" to "${key}".`, {
      label: `r4:${key}`, phase: 'Critique', schema: SCHEMA,
    })
  )
)).filter(Boolean)

const notWowed = reviews.filter((r) => !r.wowed).map((r) => r.lens)
log(`${reviews.length}/6 reported; not wowed: ${notWowed.join(', ') || 'NONE - unanimous'}`)

phase('Synthesis')
const chair = await agent(
  `${CONTEXT}

Six critics have reported on ROUND 4. Their verdicts and findings:

${JSON.stringify(reviews, null, 2)}

As chair: verify what you cheaply can against the actual files and DROP any
finding that is factually wrong about the code (say which and why). Merge
duplicates. State the verdict. If it is not unanimous, give a SHORT ranked
work order - only what actually moves the result toward "utterly wowed".
Also say explicitly what is now excellent and must not be touched.`,
  {
    label: 'chair-r4', phase: 'Synthesis',
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
