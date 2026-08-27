export const meta = {
  name: 'colossus-tire-critics-r6',
  description: 'Round 6 critic panel on the COLOSSUS tire after the round-5 work order was executed in full',
  phases: [
    { title: 'Critique', detail: 'six specialist critics re-judge after the round-5 work order' },
    { title: 'Synthesis', detail: 'verdict and any remaining work order' },
  ],
}

const REPO = 'C:/Users/ericr/beamng-mcp'
const MOD = 'examples/giant_props/colossus_tire'
const RENDERS = `${REPO}/${MOD}/authoring/verify`

const CONTEXT = `
ROUND 6 review of a BeamNG.drive mod in the repo at ${REPO}.

THE BRIEF (unchanged since round 5): a maximally realistic 28 m earthmover
radial standing chocked in a yard; approach arms it, the release cuts all
forty tie-downs AND winches the chocks clear, and after that it obeys nothing
but physics - push it, release it on a grade and chase it, or get a car into
the cavity (deliberately no ramp; entry is the player's business) and drive:
the liner is a real surface and driving inside turns the wheel.

ROUND 5's VERDICT: 2 of 6 wowed (beamng-physics, mesh-quality). The chair
issued a ten-rank work order; ALL TEN RANKS WERE EXECUTED, plus the follow-on
engineering the execution exposed. VERIFY, DO NOT TRUST:

1. (rank 1) Chock stripes rebuilt: the floating open-quad decals are GONE.
   Stripes are closed 6 mm slabs on the climb face AND the side plates,
   every chock piece is a closed solid oriented by manifold recalc, ground
   objects now pass through assert_face_orientation under a new
   "_chock_" -> away_from_own_centroid rule, and a shipped-DAE gate
   (test_chock_hazard_faces_look_out_of_the_steel) walks hazard triangles
   per-solid via vertex-index connected components.
2. (rank 2) The chock visual no longer binds fixed anchors: wedge nodes
   carry per-wedge groups (chock_0..3), the visual flexbody binds exactly
   those four (visual_groups plumbed through write_handoff/prop_builder,
   backward-compatible default; the pack gate learned the contract), and
   test_no_flexbody_group_contains_a_fixed_node pins the rule pack-wide
   for this mod.
3. (rank 3) SOUND SHIPS. Three cues on the spin_launch discipline
   (authoring/make_colossus_tire_audio.py, PCM-sha manifest, circular
   loops, level-locked wrap 0.32 against a 3.0 gate): release_crack fired
   from cutChocks, roll_loop pitched/swelled from the same b.speed the HUD
   shows (inside the pitch-black cavity it IS the speedometer), and
   capsize_boom at the tipped beat. Vehicle-half source machinery
   (VEHICLE_LUA_EXTRA, ct-prefixed), GE-half cue/cueLoop/cueTrack with the
   loop latch and the 24-cent rate-limited pitch push, emitter node bound
   by name resolution (bead_l_j00, r = 5.8 m orbit). Four audio gates in
   tests/test_colossus_tire_audio.py. Three cues, not sixteen: the minimum
   the chair ordered, scoped deliberately.
4. (rank 4) The hamster loop talks: distance milestones at 5 m then every
   15 m (measured live: 8 fired in one interior drive), the revolution line
   stays the big beat, info.json carries a Description naming the drivable
   cavity, info_standard Weight is the 5,004 kg free body, cutChocks quotes
   the sidewall ("The 10350/80R457 is loose") instead of the physics mass,
   and a once-per-release hint names the hamster mode in game.
5. (rank 5) The ledger agrees with itself: the 115 kNm hold is pinned at
   the 6 t tune everywhere with the 4.2 t figures (~94 held vs ~125-133
   supplied) alongside; spec.py's docstring narrates the standing-in-a-yard
   product (the dock/port/gangway sections are rewritten as history);
   DOCK_BEAM -> ANCHOR_GLUE_BEAM; port_frame/gangway beam families deleted;
   LANE_MARK_NITS and its essay replaced by a deliberate headlights-only
   darkness decision; the E-4 stamp is now E-3 with the derivation note;
   winch comments carry measured numbers; README/AGENTS numbers are the
   current measurements; AGENTS' past-the-clamp list names colossus.
6. (rank 6) All three live gates use a shared content-based
   namespace_conflicts (live_support) instead of the filename scan.
7. (rank 7) The albedo gate is ARMED: family-default bases via
   inspect.signature (c1/c2 for two-colour families, envelope check for the
   shipped mean), checked >= 6 asserted, a staged-vs-shipped byte-equality
   gate added, 19 furniture-era orphan PNGs pruned from staging, the hazard
   mirror corrected to the family's safety orange, and the four drifted
   roughness mirrors corrected to the measured map means (factors are not
   written when maps exist, so mirrors are inert prose held to truth).
8. (rank 8) The chocks are fabricated: painted steel_worn body (safety
   yellow, authored base - machined_steel was tried and measured dying by
   mip 2), blunted toe, 20 mm side plates, heel gussets, tow handle,
   stripes on climb and side faces; the collision hull is CLOSED (sides +
   base, ~16 new coltris); nodes, beams, masses, seat gap untouched.
9. (rank 9) Cavity darkness is DECIDED (headlights-only realism, the
   rolling loop carries speed perception; LANE_MARK_NITS deleted) and two
   new verify views ship: cavity (the driver's frame, lamp-lit) and
   chock_face (a 3/4 on the climb face and stripes).
10. (rank 10) The honesty batch: chock climb band certified off the
    AS-BUILT face (seat gap included, 11-40 deg band); 'landing' dropped
    from the release-bridge families; the damping gate docstring argues the
    recorded convention (zeta ~ tan-delta/2 plus named settling margin);
    SERVICE_CODE restamped E-3; wear-bar skirts seated below the GROOVE
    floor; COLLADA_DECIMALS docstring agrees with the measured five.

WHAT THE EXECUTION ITSELF EXPOSED AND FIXED (all measured live):
* The winch was resized against MEASURED skid friction (node frictionCoef
  multiplies the groundmodel's: authored 0.55 reads ~0.87-1.0 effective);
  a winch sized to the authored number moved a wedge 0.29 m.
* A diagonal-outboard winch was tried and REVERTED with data: applied at
  one corner it spun the wedge in place (0.3 m centroid escape); at 42
  degrees the rolling tire edge-caught its own front wedge and ground to a
  halt; on a hillside it yanked a load-bearing wedge out from under the
  leaning shoulder and kicked the tire into a sideways skid. Straight
  fore-aft couple-free pulls measured benign everywhere and ship.
* The flat gate's ram now waits for the RELEASE EVENT via runtime state
  (b.stats.released) - polling beamng.log mid-run raced the lazy flush into
  a false "never fired" - and runs at 12 m/s, resized twice with reasons.
* The hill gate's rolling segment is bounded by TIPPED_DOT (the point of
  no return), not the early warning - a carving tire at 25 degrees of lean
  is still rolling - and the slip RATIO is certified on the plane and in
  the hamster (0.994-1.02) but only REPORTED on dirt, because this gate's
  angle frame is rebuilt from the live axis and a carving tire under-counts
  its own spin while a face-down pirouette over-counts it (measured: 274
  deg of "rotation" from a flat carcass spinning on the ground).
* The gentle-slope claim is patch statics, honestly bounded: the release
  now REMOVES the chocks, so the transient legitimately walks the tire a
  car-length downhill (measured 4.5 m at rolling slip 1.21) before the
  patch re-catches it; the bound is "does not run, does not fall".

CURRENT LIVE MEASUREMENTS (all three gates green on the shipped bytes):
* flat (smallgrid): settle 13.965 m (95 mm deflection), push -> 60.2 m of
  travel + 5.8 m coast THROUGH both 200 kg front chocks (closed hulls -
  shoving them is real momentum spent), ring slip 1.008, Crr 0.023-0.031
  by speed window, ring ~0.2 m p-p after the 12 m/s ram decaying in ~1 s.
* hill (utah, spawn square-to-slope via the calibrated conjugate quat):
  3.4 deg - shrugs 4.5 m in the release transient and re-parks, never
  tips; 13.1 deg - rolls away 29 m displacement / 14 m down the fall line
  with real rotation, carves into its ~6 deg settle lean and lies down
  (fall line and staying-up deliberately not asserted - free tires
  promise neither); 22.9 deg - 45 m displacement, 42 of them down the
  fall line, 334 deg of rotation at pre-tip slip 0.84, upright to 42 m.
* hamster (the headline): roamer teleported in, lands on the liner, the
  SHIPPED sequence releases (40/40 straps audited broken, winch echo 8/8,
  wedge centroid 2.5 m clear), and driving inside moved the tire 93.75 m
  at hamster slip 0.994 - more than a full revolution - with 8 milestone
  beats narrated and the car still inside.

GATES: 26 geometry + 7 sequence + 6 texture + 4 audio = 43 static, plus
three live files, all green. The full pack suite is green except the OTHER
session's known failures (catapult_seesaw x3, pachinko harvest-dds).

KNOWN AND DELIBERATE - do not spend findings on these:
* 4,200 kg (vs ~1,900,000 honest), documented as the hamster inequality's
  price; the mass solve essay in spec.py carries both live measurements.
* No air/pressure model; node-friction grip; a jbeam prop, not BeamNG
  wheel physics.
* Carve-and-flop on dirt hills is real free-tire behaviour, reported not
  asserted; slip ratio on dirt is reported not asserted (frame artifact,
  demonstrated numerically); the flat/hamster gates carry the slip
  certification.
* Three audio cues, not a sixteen-cue set.
* Liner COLLISION stays a 48-gon (cars inside ride 28 mm bumps).
* Entry to the cavity is teleport/spawn - no ramp, by user decree.
* The repo is shared with another active session; catapult_seesaw and
  pachinko failures are theirs.
* Serial is past the timestamp clamp: the zip hash does not reproduce from
  a clean checkout (documented in AGENTS with colossus named).

FILES (read what your lens needs):
  ${MOD}/spec.py
  ${MOD}/blender/create_colossus_tire.py
  ${MOD}/authoring/ericrolph_colossus_tire.handoff.json
  ${MOD}/authoring/make_colossus_tire_audio.py
  ${MOD}/authoring/colossus_tire_audio_manifest.json
  ${MOD}/mod/vehicles/ericrolph_colossus_tire/ericrolph_colossus_tire.jbeam
  ${MOD}/mod/vehicles/ericrolph_colossus_tire/main.materials.json
  ${MOD}/mod/vehicles/ericrolph_colossus_tire/ericrolph_colossus_tire.dae
  ${MOD}/mod/vehicles/ericrolph_colossus_tire/info.json, info_standard.json
  ${MOD}/mod/lua/ge/extensions/ericrolph_colossus_tire/runtime.lua
  ${MOD}/mod/vehicles/ericrolph_colossus_tire/lua/ericrolph_colossus_tire_vehicle.lua
  ${MOD}/authoring/verify_render.py
  examples/giant_props/proplib/{texture_kit,blender_kit,prop_builder,lua_kit}.py
  tests/test_colossus_tire_{geometry,sequence,textures,audio}.py
  tests/test_colossus_tire_{live,hill_live,hamster_live}.py, tests/live_support.py
  tests/test_giant_props_pack.py, examples/giant_props/README.md, AGENTS.md

RENDERS (read as IMAGES; backface-culled, Standard view transform; 15 views,
regenerated on the final bytes):
  ${RENDERS}/hero.jpg ${RENDERS}/profile.jpg ${RENDERS}/face.jpg
  ${RENDERS}/tread_close.jpg ${RENDERS}/shoulder.jpg ${RENDERS}/buttress.jpg
  ${RENDERS}/bead.jpg ${RENDERS}/sidewall_type.jpg ${RENDERS}/sidewall_print.jpg
  ${RENDERS}/chocks.jpg ${RENDERS}/chock_face.jpg ${RENDERS}/cavity.jpg
  ${RENDERS}/contact.jpg ${RENDERS}/scale.jpg ${RENDERS}/underside.jpg

MEASURED NOW: OD 28.168 m, section 10.350 m, cavity radius 13.150 m; 288
visual stations, ~264,900 visual triangles (0 degenerate); cage 1,100 nodes
(1,056 carcass 4,200 kg + 24 wedge 804 kg + 20 fixed buried/datum), 4,862
beams, 3,296 collision triangles; worst omega*dt 0.826 of 0.90; k_gyr
12.56 m; spin-up 7.1 s vs (5,12); ZIP ~55.6 MB, 37 members, deterministic
lock verified by every live gate.

CONSTRAINTS (do not spend findings on these): jbeam "vehicle" props, one
connected cage; deterministic headless Blender 4.5.4; procedurally generated
PNG textures and synthesised Ogg cues only.

YOUR JOB: same lens, same bar as rounds 1-5. "Utterly wowed" means you would
stop and stare. Round 5's chair-verified defects were all claimed fixed
above - CHECK the ones your lens owns before believing them. Every finding
must name the file and symbol and say what to do. If it is now excellent,
say so plainly, and say what must NOT be touched. If your round-5 flip
condition was met, say so explicitly.
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
      description: 'round-5 fix claims you actually checked against the tree, and whether they hold',
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
  ['tire-engineering', 'LENS: TIRE ENGINEERING REALISM. Your round-5 flip condition was the stripe winding fix plus fabricated chocks. Verify both in the DAE and the renders (chocks.jpg, chock_face.jpg, contact.jpg): do the chocks now read as yard hardware - paint, plates, gussets, handle, stripes visible? Then re-judge the tire itself: shoulder, buttress relief, bead, tread class (now stamped E-3 - is the restamp right?), pitch sequence, sidewall type and print band, wear bars now seated below the groove floor.'],
  ['beamng-physics', 'LENS: BEAMNG PHYSICS AND JBEAM. You were wowed in round 5 with one must-fix (the flexbody/anchor binding) and minors (open wedge hull, prose). Verify all three landed: per-wedge groups in the shipped jbeam flexbodies row, closed wedge hulls (count the chock coltris), the new static gates. Recompute omega*dt at the shipped 4,200 kg. Audit the audio dispatch for physics safety (nothing moves; the sequence gate now allows exactly cut+winch+ctAudio commands). Judge the winch-direction engineering record in spec.py - straight fore-aft with the diagonal experiment documented - and the live numbers for consistency.'],
  ['mesh-quality', 'LENS: GEOMETRY AND TOPOLOGY. You were wowed in round 5 with one major (the flexbody binding, now claimed fixed) and polish items (48-tri chocks, wear-bar rims, decimals docstring). Parse the SHIPPED .dae: are the fabricated chocks closed solids wound outward (the new per-solid hazard gate claims it - re-derive independently)? Are the wear-bar skirts seated? Did the ~600 new chock triangles introduce degenerates, unwelded edges, or UV zeros? Is the shell still watertight at 288 stations?'],
  ['texture-materials', 'LENS: TEXTURE AND MATERIAL. Your round-5 flip condition was the stripe winding plus the armed albedo gate. Verify: the gate now resolves family-default bases (c1/c2 envelope for hazard), asserts checked >= 6, and a byte-equality gate ties staging to shipped; the hazard mirror is safety orange; the four roughness mirrors match the shipped map means; chock_paint (steel_worn family, authored base) passes slope and mip gates - measure its shipped PNGs yourself. Then judge the whole 9-material palette as a system, including the new painted steel against the tire rubbers in the renders.'],
  ['gameplay', 'LENS: PLAYABILITY AND FEEL. Your round-5 flip conditions were sound and hamster feedback/discoverability. Verify: three cues wired at the three beats (read runtime.lua and the vehicle chunk), the rolling loop keyed to b.speed as the cavity speedometer, milestones at 5 m then 15 m (the hamster gate measured 8 firing), the info.json Description, the post-release hint, the sidewall-quote release line. Then judge the LOOP as shipped: approach, countdown, crack-and-winch, a 60 m push-and-coast through the chocks, runaway hills, and a 93 m hamster drive. What single change would most improve it now - and is it still worth a round?'],
  ['pipeline', 'LENS: REPO CONVENTION AND PIPELINE. Your round-5 flip condition was the ledger sweep plus the content-based shadow scan. Verify: one 115 kNm provenance across spec/README/AGENTS; dock-era prose gone from shipped files and gates renamed; dead constants deleted (DOCK_BEAM renamed, port_frame/gangway/LANE_MARK_NITS gone, 19 orphan PNGs pruned); namespace_conflicts shared and used by all three live gates; the audio pipeline is a committed artifact with a PCM-hash gate like spin_launch; the shared-file changes (visual_groups, Description/Weight hooks, pack-gate contract) are backward-compatible for the other 22 mods; serial-past-clamp documented. What remains stale or dead?'],
]

phase('Critique')
const reviews = (await parallel(
  LENSES.map(([key, brief]) => () =>
    agent(`${CONTEXT}\n\n${brief}\n\nSet "lens" to "${key}".`, {
      label: `r6:${key}`, phase: 'Critique', schema: SCHEMA,
    })
  )
)).filter(Boolean)

const notWowed = reviews.filter((r) => !r.wowed).map((r) => r.lens)
log(`${reviews.length}/6 reported; not wowed: ${notWowed.join(', ') || 'NONE - unanimous'}`)

phase('Synthesis')
const chair = await agent(
  `${CONTEXT}

Six critics have reported on ROUND 6. Their verdicts and findings:

${JSON.stringify(reviews, null, 2)}

As chair: verify what you cheaply can against the actual files and DROP any
finding that is factually wrong about the code (say which and why). Merge
duplicates. State the verdict. If it is not unanimous, give a SHORT ranked
work order - only what actually moves the result toward "utterly wowed", with
effort-vs-payoff called out per item. Also say explicitly what is now
excellent and must not be touched.`,
  {
    label: 'chair-r6', phase: 'Synthesis',
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
