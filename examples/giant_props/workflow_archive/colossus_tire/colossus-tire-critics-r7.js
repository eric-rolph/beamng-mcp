export const meta = {
  name: 'colossus-tire-critics-r7',
  description: 'Round 7 critic panel on the COLOSSUS tire after the round-6 work order was executed in full',
  phases: [
    { title: 'Critique', detail: 'six specialist critics re-judge after the round-6 work order' },
    { title: 'Synthesis', detail: 'the verdict' },
  ],
}

const REPO = 'C:/Users/ericr/beamng-mcp'
const MOD = 'examples/giant_props/colossus_tire'
const RENDERS = `${REPO}/${MOD}/authoring/verify`

const CONTEXT = `
ROUND 7 review of a BeamNG.drive mod in the repo at ${REPO}.

THE BRIEF (unchanged): a maximally realistic 28 m earthmover radial standing
chocked in a yard; approach arms it, the release cuts all forty tie-downs AND
winches the chocks clear, and after that it obeys nothing but physics - push
it, release it on a grade and chase it, or get a car into the cavity
(deliberately no ramp) and drive: the liner is a real surface and driving
inside turns the wheel.

ROUND 6's VERDICT: 5 of 6 wowed (beamng-physics, mesh-quality,
texture-materials, gameplay, pipeline - four declared their round-5 flip
conditions met). tire-engineering held out on two chair-verified majors, and
the chair issued a nine-rank order. ALL NINE RANKS WERE EXECUTED and the
result is committed (git f627594, 23 files, the previously-untracked audio
deliverable now under version control). VERIFY, DO NOT TRUST:

1. (rank 1, holdout flip A) The 12 outer wear bars seat PER-CORNER on
   base_r(x) - LUG_SEAT, the add_tie_bar pattern; the inverted round-5
   comment is rewritten with the correct geometry (the crown arc can only
   DROP base_r off-centre).
2. (rank 2, holdout flip B) SERVICE_CODE is E-4 again, with the real
   derivation in the comment: proportional scaling preserves depth/OD =
   2.251% exactly (reference 90 mm / 3.998 m; shipped 0.634 m / 28.168 m),
   so the as-built tread IS E-4-proportioned and the round-5 E-3 restamp
   contradicted the spec's own prose, the net-to-gross gate and the depth.
   MAX LOAD now prints kilograms rounded to three significant figures.
3. (rank 3) Seating is a GATED INVARIANT twice over: the shipped-DAE gate
   test_every_open_tread_component_is_seated_in_its_local_floor decomposes
   tread furniture by vertex-index connected components against the
   analytic local floor (it was proven FAILING on the pre-fix bytes - 12
   components at 47 mm - before rank 1 landed), and the generator's
   assert_furniture_is_seated now judges per connected component so welded
   families can never vouch for each other again.
4. (rank 4) The gameplay trio: an at-rest scoreboard ("At rest: X m, N
   revolutions." after 3 settled seconds, re-armed by movement - it FIRED
   in the live hamster run, behavior_stats.rests = 1), roll-loop
   HYSTERESIS (on >= 0.9 m/s, off <= 0.4) replacing the machine-gunning
   single threshold, and a revolution headline that pushes the next
   distance milestone out so the big beat keeps its air. The closing beat
   is pinned at source level in the sequence tests.
5. (rank 5) One rebuild on the final bytes: DAE/textures/handoff
   regenerated, zip re-cut (serial 60), all 15 renders regenerated, the
   static suite green, and all three live gates re-run and green on the
   shipped zip.
6. (rank 6) The truth micro-batch, all seven: winch comment quotes the
   gate-measured escape (asserted > 1.0 m, measured ~2.0-2.5 m; 5.0 m
   labelled as the standalone probe), mass essay quotes the measured
   12.56 m gyration with the arithmetic re-run (~4,240), the fixed-node
   sentence names the deliberately floating "up" datum, the dead
   steel_worn palette entry is deleted (family registration stays for
   chock_paint), "safety orange" corrected to safety yellow, the emitter
   node name is interpolated from AUDIO_EMITTER_NODE_NAME (one copy) with
   a new emitter-exists audio gate, and the flexbody gate normalises
   string-vs-list groups.
7. (rank 7) The dead dock-era machinery is purged: SWEPT_BINS,
   swept_profile, assert_outboard_clearance, assert_tongue_sweep (~135
   lines, zero call sites) deleted; the generator's module docstring and
   the "loading dock" banner rewritten for the closed carcass + chocks;
   orphan constants CAR_WIDTH/LENGTH/HEIGHT/TURN_RADIUS, CROWN_DROP,
   SPINUP_TARGET_SECONDS, BUTTRESS_FEATHER deleted (each with its reason
   folded into the surviving prose); TREAD_PITCHES is now asserted against
   len(PITCH_SEQUENCE) in assert_authored_claims.
8. (rank 8) Ruff: all nine named files pass "uv run ruff check" clean and
   are ruff-formatted. The 23 B023s died by deduplicating the union-find
   into one module helper (_union_find) used by all three component
   decompositions.
9. (rank 9) Committed: git f627594 stages the three oggs, the manifest,
   the audio generator, all four previously-untracked test files and every
   modified colossus/shared file - the deliverable now survives checkout.
   The other session's in-flight files were left untouched.

LIVE MEASUREMENTS on the committed bytes (all three gates green):
* flat: settle 13.965 m, 60 m push-and-coast through both front chocks,
  ring slip 1.008, Crr 0.023-0.031 by speed window.
* hill: 3.4 deg shrugs 4.5 m in the release transient and re-parks (patch
  statics); 13.1 deg rolls away with real rotation and lies down carving
  (free-tire behaviour, reported not asserted); 22.9 deg thunders 42 m
  down the fall line at pre-tip slip 0.84.
* hamster: shipped release (40/40 straps, winch echo 8/8, wedge 2.0 m
  clear), the car drove the tire on a CURVED lap - path 32.1 m against
  arc 39.3 m, rolling ratio 0.82 - with 3 milestones, 1 at-rest beat, and
  the car still inside. (A cleaner straight run earlier measured 93.75 m
  at 0.994; the gate's metric notes why path-over-arc is the honest form
  for curved laps.)

GATES: 45 static + 3 live files, all green. The full pack suite is green
except the OTHER session's known failures (catapult_seesaw x3, pachinko
harvest-dds).

KNOWN AND DELIBERATE - do not spend findings on these:
* 4,200 kg (vs ~1,900,000 honest) - the hamster inequality's documented
  price; no air model; node-friction grip; a jbeam prop.
* Carve-and-flop on dirt hills; dirt slip reported-not-asserted (the
  axis-rebuilt angle frame under/over-counts a yawing tire - demonstrated
  numerically); slip certification lives on flat/hamster.
* Three audio cues, not sixteen. Liner collision stays a 48-gon. Entry is
  teleport/spawn by user decree. Serial is past the timestamp clamp
  (documented, colossus named).
* The repo is shared with another active session; catapult_seesaw and
  pachinko failures are theirs.

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
  examples/giant_props/proplib/{texture_kit,blender_kit,prop_builder,lua_kit}.py
  tests/test_colossus_tire_{geometry,sequence,textures,audio}.py
  tests/test_colossus_tire_{live,hill_live,hamster_live}.py, tests/live_support.py
  tests/test_giant_props_pack.py, examples/giant_props/README.md, AGENTS.md

RENDERS (as IMAGES; backface-culled; 15 views on the final bytes):
  ${RENDERS}/hero.jpg ${RENDERS}/profile.jpg ${RENDERS}/face.jpg
  ${RENDERS}/tread_close.jpg ${RENDERS}/shoulder.jpg ${RENDERS}/buttress.jpg
  ${RENDERS}/bead.jpg ${RENDERS}/sidewall_type.jpg ${RENDERS}/sidewall_print.jpg
  ${RENDERS}/chocks.jpg ${RENDERS}/chock_face.jpg ${RENDERS}/cavity.jpg
  ${RENDERS}/contact.jpg ${RENDERS}/scale.jpg ${RENDERS}/underside.jpg

MEASURED NOW: OD 28.168 m, section 10.350 m; 288 visual stations, ~264,300
visual triangles (0 degenerate); cage 1,100 nodes (1,056 carcass 4,200 kg +
24 wedge 804 kg + 20 fixed), 4,862 beams, 3,296 coltris; worst omega*dt
0.826 of 0.90; k_gyr 12.56 m; spin-up 7.1 s vs (5,12); ZIP ~55.6 MB serial
60, deterministic lock verified by every live gate.

CONSTRAINTS (do not spend findings on these): jbeam "vehicle" props, one
connected cage; deterministic headless Blender 4.5.4; procedural PNG
textures and synthesised Ogg cues only.

YOUR JOB: same lens, same bar as rounds 1-6. "Utterly wowed" means you
would stop and stare. If you were wowed in round 6, verify nothing you
praised regressed under the round-6 edits and re-affirm or revoke. If you
were the holdout, your two flip conditions were rank 1 and rank 2 - check
them in the shipped DAE and the spec, then judge the whole tire fresh.
Every finding must name the file and symbol and say what to do. If it is
excellent, say so plainly.
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
      description: 'round-6 fix claims you actually checked against the tree, and whether they hold',
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
  ['tire-engineering', 'LENS: TIRE ENGINEERING REALISM. You were the round-6 holdout; your flip conditions were the wear-bar seating (rank 1) and the E-4 stamp (rank 2). Verify both: measure the 12 outer bars against their local groove floor in the SHIPPED DAE, and check the E-4 derivation against the spec arithmetic and the net-to-gross gate. Then judge the whole tire fresh: shoulder, buttress, bead, tread class and pitch sequence, sidewall type and print band (MAX LOAD now in kg), the fabricated chocks, the renders.'],
  ['beamng-physics', 'LENS: BEAMNG PHYSICS AND JBEAM. You were wowed in round 6. The round-6 edits touched the runtime (rest scoreboard, roll-loop hysteresis, milestone air) and deleted dead generator machinery - verify nothing you praised regressed: recompute a spot integrator bound, re-read the release beat and the audio dispatch, check the purge deleted only dead code, and confirm the live numbers are consistent with the shipped constants.'],
  ['mesh-quality', 'LENS: GEOMETRY AND TOPOLOGY. You were wowed in round 6 with the wear-bar rims your polish item. Verify rank 1 in the shipped DAE (measure the bar rims against the local floor yourself), confirm the new per-component gates match your own decomposition, and confirm the rebuild introduced no degenerates, unwelded edges or UV zeros.'],
  ['texture-materials', 'LENS: TEXTURE AND MATERIAL. You were wowed in round 6. The round-6 edits deleted the dead steel_worn palette entry, corrected the safety-yellow wording, and regenerated the print band with MAX LOAD in kilograms - verify the shipped print band bytes, the 8-entry palette coherence, and that the armed gates still measure what they claim.'],
  ['gameplay', 'LENS: PLAYABILITY AND FEEL. You were wowed in round 6. Verify the trio you asked for: the at-rest scoreboard (it fired live - behavior_stats.rests), the roll-loop hysteresis at exactly the speeds the tire lives at, and the revolution beat keeping its air. Then judge the loop once more as shipped. Is anything still missing that a player would feel in the first five minutes?'],
  ['pipeline', 'LENS: REPO CONVENTION AND PIPELINE. You were wowed in round 6. Verify the commit (f627594) staged the full deliverable and nothing of the other session; ruff is clean on the nine files; the dead-code purge left no dangling references (grep swept_profile, CROWN_DROP, BUTTRESS_FEATHER, SPINUP_TARGET_SECONDS, steel_worn palette); the emitter interpolation and its gate; and that every number quoted in README/AGENTS matches the shipped measurements.'],
]

phase('Critique')
const reviews = (await parallel(
  LENSES.map(([key, brief]) => () =>
    agent(`${CONTEXT}\n\n${brief}\n\nSet "lens" to "${key}".`, {
      label: `r7:${key}`, phase: 'Critique', schema: SCHEMA,
    })
  )
)).filter(Boolean)

const notWowed = reviews.filter((r) => !r.wowed).map((r) => r.lens)
log(`${reviews.length}/6 reported; not wowed: ${notWowed.join(', ') || 'NONE - unanimous'}`)

phase('Synthesis')
const chair = await agent(
  `${CONTEXT}

Six critics have reported on ROUND 7. Their verdicts and findings:

${JSON.stringify(reviews, null, 2)}

As chair: verify what you cheaply can against the actual files and DROP any
finding that is factually wrong about the code (say which and why). Merge
duplicates. State the verdict plainly. If unanimous, say what the panel is
signing off on and what must never be touched. If not, give the SHORTEST
work order that flips the holdout(s).`,
  {
    label: 'chair-r7', phase: 'Synthesis',
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
