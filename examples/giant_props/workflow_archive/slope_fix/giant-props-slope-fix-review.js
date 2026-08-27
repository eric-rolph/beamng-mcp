export const meta = {
  name: 'giant-props-slope-fix-review',
  description: 'Adversarially review the runtime frame fix, the new slope gate, and the 20-mod re-cut',
  phases: [
    { title: 'Review', detail: 'independent lenses over the diff' },
    { title: 'Verify', detail: 'refute each finding' },
  ],
}

const REPO = 'C:\\Users\\ericr\\beamng-mcp'

const CONTEXT = `
CONTEXT. In ${REPO} I fixed a shipped-mod bug: Giant Props runtime TSStatic parts were placed by
dead reckoning from vehicle:getPosition()/getRotation(). getRotation() is stale (only updates on
spawn/teleport/reset), so on sloped terrain parts flew up to 11.5 m away from the geometry they
belong to. Three compounding bugs were found and fixed in examples/giant_props/proplib/lua_kit.py
(the SHARED generator for all 20 mods):
  1. propFrame now derives the placement basis from the live node cloud (the four jbeam refNodes)
     instead of the object transform.
  2. A hand-built Shepperd quaternion must be CONJUGATED for the engine's q*vec3 convention.
  3. modelRotation must compose as MODEL_ALIGNMENT_ROTATION * vehicleRotation, not the reverse.
Also added: pcall guards, a frame_source telemetry field surfaced through getSystemState, and
per-frame selection of the best-conditioned baseline PAIR from {back,left,up}.

New file tests/test_giant_props_slope_live.py is an opt-in live gate: it boots BeamNG on utah,
spawns at flat / flat+yaw40 / slope / slope+yaw40, and asserts rigid-body invariance of every
part-to-cage-node distance, plus frame_source == "node_cloud", plus an absolute handoff check.

Live measurements (utah, panel node 13 m out): before 0.209 m flat / 11.611 m steep slope;
after 0.000 m / 0.000 m. Gate mutation-tested: reverting only fix (3) produces 18.487 m drift and
the gate rejects it.

Inspect the ACTUAL current state of these files. Use: git diff examples/giant_props/proplib/lua_kit.py
and read tests/test_giant_props_slope_live.py in full, plus a generated
examples/giant_props/<mod>/mod/lua/ge/extensions/<mod_id>/runtime.lua to see the emitted Lua.
`

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['title', 'file', 'line', 'severity', 'why_it_breaks'],
        properties: {
          title: { type: 'string' },
          file: { type: 'string' },
          line: { type: 'integer' },
          severity: { type: 'string', description: 'critical | high | medium | low' },
          why_it_breaks: { type: 'string', description: 'concrete inputs/state -> wrong behaviour' },
          suggested_fix: { type: 'string' },
        },
      },
    },
  },
}

const LENSES = [
  {
    key: 'lua-correctness',
    prompt: `${CONTEXT}
LENS: Lua correctness of the generated runtime. Hunt for REAL defects, not style:
- vec3 aliasing/in-place mutation (BeamNG vec3 :normalize() mutates in place). Does any code path
  mutate FRAME_NODES' stored mesh vectors, or a table shared between frames?
- the new best-pair loop: is the scoring stable frame to frame? Could it pick different pairs on
  successive frames and make the frame jitter? Is the authored-geometry scoring actually constant?
- nil handling, multiple-return-value handling from baselineBasis, degenerate cages
- basisQuat branch coverage and numerical behaviour near 180 degree rotations
- lexical binding: is any local function called before it is defined (silently a nil global)?
- LuaJIT limits: count chunk-level locals in the LARGEST generated runtime and compare to 200
- does the emitted Lua actually parse? Verify syntactically however you can.
Report only defects you can justify with a concrete failure scenario.`,
  },
  {
    key: 'frame-math',
    prompt: `${CONTEXT}
LENS: the geometry and the frame math itself. Verify INDEPENDENTLY, deriving it yourself:
- Is R = V * transpose(U) actually correct for mapping authored/mesh coordinates to world, given
  how baselineBasis constructs U and V? Prove it or refute it with algebra.
- Is the conjugation in basisQuat right, or does it only appear right because it was tuned against
  one measurement? Reason about the engine's left-to-right composition rule.
- Is MODEL_ALIGNMENT_ROTATION * vehicleRotation the correct order under that rule?
- Does the best-pair selection preserve handedness for EVERY pair, including (left, up) where the
  authored mesh triad may be left-handed relative to (back, left)? THIS IS THE KEY QUESTION -- if
  swapping pairs silently flips handedness for some mods, those mods get a mirrored frame.
  Check it numerically: for each of the 20 mods read FRAME_NODES from the generated runtime and
  compute what basis each candidate pair yields; confirm all pairs give the SAME rotation for a
  given rigid attitude. Write and run a small python simulation of the exact Lua algorithm.
- Are there attitudes (gimbal-ish, 180 degree yaw, upside down) where the math degrades?
Report concrete defects with numbers.`,
  },
  {
    key: 'gate-quality',
    prompt: `${CONTEXT}
LENS: is the new live gate actually a good test? Read tests/test_giant_props_slope_live.py fully.
- Can it pass while the bug is present? Enumerate every way it could be vacuous.
- Is the rigid-body invariance argument sound, or is it circular anywhere (does ground truth ever
  come from the same frame math under test)?
- The gate compares distances between attitudes. Could a behaviour animating between spawns make
  it flaky? Is the behaviour_phase equality check sufficient? What about parts that animate on a
  clock rather than on state?
- Terrain spot hardcoding: what happens on a different BeamNG version or if utah changes?
- Cleanup/safety: does it follow the repo's live-test rules (isolated_profile_lock, owned process,
  artifact cleanup) exactly? Compare against tests/test_giant_props_live.py. Any leak on failure?
- Does the absolute-check math (authored pivot 180 degree flip) actually match what the runtime does?
- Is TOLERANCE_M defensible?
Report concrete defects.`,
  },
  {
    key: 'release-integrity',
    prompt: `${CONTEXT}
LENS: release integrity of the 20-mod re-cut. I re-cut every giant_props dist zip so each differs
from its previously shipped release by EXACTLY the generated runtime.lua. I did that by restoring
non-runtime members from a snapshot of the shipped zip back into mod/ before re-zipping, because
build.py <key> prop had downgraded cooked .dds to raw .png for 7 mods.
VERIFY INDEPENDENTLY, do not trust my claim:
- For each of the 20 mods, compare the CURRENT dist zip against its lock file and against the
  mod/ tree. Does every lock sha256 match its zip? Does every zip's member list look sane?
- Are cooked .dds textures still present in the mods that shipped them? Count them.
- Is any mod's zip now missing files, or carrying files it should not?
- Check examples/giant_props/catapult_seesaw/dist/repo_update and boot_of_doom/dist/repo_submission
  are consistent with their dist zips.
- Does anything else in the repo pin a giant_props zip hash that I may have missed? Search broadly
  (tests, docs, changelogs, authoring scripts, lock/serial files).
Report concrete problems. Read-only: do NOT rebuild or modify anything.`,
  },
]

phase('Review')

const reviewed = await parallel(
  LENSES.map((l) => () =>
    agent(l.prompt, { label: `review:${l.key}`, phase: 'Review', schema: SCHEMA })
      .then((r) => ({ key: l.key, findings: (r && r.findings) || [] })),
  ),
)

const all = reviewed.filter(Boolean).flatMap((r) =>
  r.findings.map((f) => ({ ...f, lens: r.key })),
)
log(`${all.length} candidate findings from ${reviewed.filter(Boolean).length} lenses`)
if (!all.length) return { confirmed: [], note: 'no candidate findings' }

phase('Verify')

const VERDICT = {
  type: 'object',
  additionalProperties: false,
  required: ['refuted', 'reasoning'],
  properties: {
    refuted: { type: 'boolean', description: 'true if the finding does NOT hold' },
    reasoning: { type: 'string' },
    corrected_severity: { type: 'string' },
  },
}

const verified = await parallel(
  all.map((f) => () =>
    agent(
      `${CONTEXT}
A reviewer claims the following defect. Try HARD to REFUTE it by reading the actual code and, where
possible, running a small experiment (python simulation of the Lua, or read-only inspection).
Default to refuted=true if you cannot demonstrate the defect is real.

TITLE: ${f.title}
FILE: ${f.file}:${f.line}
SEVERITY CLAIMED: ${f.severity}
WHY IT BREAKS: ${f.why_it_breaks}
SUGGESTED FIX: ${f.suggested_fix || '(none given)'}

Do NOT modify any repo file.`,
      { label: `verify:${f.title.slice(0, 40)}`, phase: 'Verify', schema: VERDICT },
    ).then((v) => ({ ...f, verdict: v })),
  ),
)

const confirmed = verified
  .filter(Boolean)
  .filter((f) => f.verdict && f.verdict.refuted === false)

log(`${confirmed.length} of ${all.length} findings survived refutation`)
return { confirmed, refuted_count: all.length - confirmed.length }
