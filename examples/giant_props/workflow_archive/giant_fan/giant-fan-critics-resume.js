export const meta = {
  name: 'giant-fan-critics-resume',
  description: 'Resume the Giant Fan critic loop from DESIGN_v2 + round-2 verdicts; a dead critic now BLOCKS instead of passing',
  phases: [
    { title: 'Revise', detail: 'fold every round-2 blocking item into the next dossier' },
    { title: 'Critique', detail: '5 aspect critics, must be WOWED' },
  ],
}

const DIR = 'C:/Users/ericr/AppData/Local/Temp/claude/C--Users-ericr-beamng-mcp/dc3b5fb8-2d89-4531-b17e-feb3dab22e68/scratchpad/fan'
const RECON = 'C:/Users/ericr/AppData/Local/Temp/claude/C--Users-ericr-beamng-mcp/dc3b5fb8-2d89-4531-b17e-feb3dab22e68/scratchpad/recon'
const REPO = 'C:/Users/ericr/beamng-mcp'
const GAME = 'E:/SteamLibrary/steamapps/common/BeamNG.drive'

const VERDICT = {
  type: 'object',
  properties: {
    aspect: { type: 'string' },
    wowed: { type: 'boolean', description: 'TRUE only if this design is genuinely astonishing AND correct in your aspect. Default FALSE.' },
    one_line: { type: 'string' },
    blocking: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          why_it_fails: { type: 'string', description: 'Concrete failure: what breaks, with numbers or a citation' },
          instruction: { type: 'string', description: 'Exactly what to change. Give the replacement numbers/mechanism/text.' },
          evidence: { type: 'string' },
        },
        required: ['title', 'why_it_fails', 'instruction'],
      },
    },
    upgrades: {
      type: 'array',
      items: { type: 'object', properties: { title: { type: 'string' }, instruction: { type: 'string' } }, required: ['title', 'instruction'] },
    },
  },
  required: ['aspect', 'wowed', 'one_line', 'blocking', 'upgrades'],
}

const COMMON = `
You are reviewing a design dossier for a BeamNG.drive mod: a GIANT three-blade oscillating table fan,
each blade the size of a city bus, NO protective grate, real collision so cars get wrecked by the
blades, a power dial, tilt, and a back-and-forth oscillating sweep.

READ FIRST:
- The design under review: <DESIGN>
- **${DIR}/ENGINE_GROUND_TRUTH.md** — facts read directly out of the installed game. It is
  AUTHORITATIVE. Anything the dossier asserts that contradicts it is wrong. In particular it records
  that NO stock vehicle uses \`torsionHydros\` at all, which is a live risk if the design relies on them.
- ${DIR}/VERDICTS_round2.md — what the previous round demanded. Check the fixes actually landed and
  are correct; a plausible-looking fix that is still wrong is a blocking item.
- Recon of the host codebase: ${RECON}/
- The pack: ${REPO}/examples/giant_props/ (proplib/, sibling specs)
- Repo law: ${REPO}/AGENTS.md (188 KB — grep, don't read whole) and ${REPO}/docs/SOFTBODY_AUTHORING.md
- Stock BeamNG, installed and readable: ${GAME}/content/vehicles/*.zip (unzip to temp),
  ${GAME}/lua/vehicle/ (wheels.lua, hydros.lua, jbeam/stage2.lua, controller/)

NOTE: \`proplib\` has already been patched this session — \`prop_builder.JBEAM_SECTIONS\` (spec-sourced,
validated against the cage by \`check_jbeam_section_refs\`), \`VEHICLE_CONTROLLERS\`, and \`metric_uv\`/\`bevel\`
on \`add_cone\`/\`add_sphere\`/\`add_torus\`. Read the current files; do not review the old plan for them.

YOUR STANDARD: you are the last gate. "Utterly wowed" means you would be genuinely astonished playing
this AND you can find nothing in your aspect that is wrong, hand-waved, or merely adequate.
Default to wowed:false. Do NOT be agreeable. But do NOT pad the blocking list — every blocking item
must be a real defect justified with numbers or a citation, and you must verify a claim yourself
before making it. Every instruction must be executable without further thought.
If the design is now genuinely right in your aspect, say so and set wowed:true — a critic who can
never be satisfied is as useless as one who rubber-stamps.
`

const CRITICS = [
  { key: 'engine-physics', prompt: `${COMMON}

ASPECT: **BeamNG engine physics and JBeam correctness.** Verify against the actual installed game:
every field of \`rotators\`/\`powertrain\`/the motor block/\`controller\`; the rotator group vs the driven
body; whether the pivot construction is real; whether the sweep/tilt actuator is a primitive that
stock actually exercises (see ENGINE_GROUND_TRUTH §6); every headline number recomputed from scratch
(inertia, ratios, brake, drag torque, gyroscopic torque, beam stiffness vs node mass, solver step
travel); spawn/settle behaviour; and what will actually explode.` },
  { key: 'visual-fidelity', prompt: `${COMMON}

ASPECT: **Visual fidelity to the reference fan and whether it looks glorious at 30 m tall.**
The reference: white four-lobed rounded-square base; short white conical neck; yoke; white truncated-cone
motor housing; three warm-grey paddle blades widest outboard with a rolled leading edge and rounded tip;
white centre hub cap with a small chrome-bezel oval badge and radial nibs; recessed taupe dial escutcheon
on the base front with a polished chrome teardrop pointer and numerals 0/3/2/1 clockwise; eggshell sheen.
Verify: every body dimension present and self-consistent; every surface actually assigned a material;
every palette entry reachable by a real mesh; texture_kit family+params correct and the params real
(read the function signatures); metric UV densities in px/m; bevels and segment counts; and whether the
deleted guard is exploited as a visual story. Name what would make a player stop and stare.` },
  { key: 'gameplay', prompt: `${COMMON}

ASPECT: **Gameplay, controls, and the joke.** The pack's rule is "exaggerate the anticipation".
Verify: the first 90 seconds beat by beat; whether every control is actually reachable and whether the
mechanism named can be built with the API named; trigger zone dimensions against
\`MIN_CONTAINS_DIMENSIONS = (2.9, 4.5, 3.0)\` in tests/test_giant_props_pack.py; debounce and cooldowns;
what actually happens to a car hit by a 6.5 t blade and whether that is readable and repeatable; whether
the wind helps or annoys; whether there is a reason to press play a tenth time; and the set pieces.` },
  { key: 'pack-conformance', prompt: `${COMMON}

ASPECT: **Conformance to this repository's laws and toolchain.** You are the maintainer.
Verify: every required spec attribute present; every generator step specified; every assertion in
tests/test_giant_props_pack.py (READ IT IN FULL) satisfiable, as a checklist; CageBuilder.validate()
and the base-node/spawn-envelope/refnode gates against a half-free-node prop; AGENTS.md tombstones this
design would trip (double-sided policy, TWIN-TILING, cut_openings bevel-after-boolean, wheel-reach node
collision, metric UV, ASCII interaction titles, emissiveFactor 3-not-4, palette-lives-in-the-handoff,
AGENTS.md:357 redistribution); determinism; and the commit order. Would you merge this?` },
  { key: 'red-team', prompt: `${COMMON}

ASPECT: **Red team.** Find how this ships broken. Spawn at t=0; reset (R); reload; level change;
two fans on one map; a car between blade and deck, blade and neck, landing on the hub, inside the swept
volume as the sweep rotates in; self-collision everywhere rotor geometry approaches base geometry;
every way the wind field misfires; sloped spawn against the 2026-08-24 stale-getRotation/quat tombstone;
performance budget with numbers. Name the single most likely first bug report.` },
]

const ROUNDS = 3
let designPath = `${DIR}/DESIGN_v2.md`
let verdictsPath = `${DIR}/VERDICTS_round2.md`
let startRound = 3

for (let round = startRound; round < startRound + ROUNDS; round++) {
  phase('Revise')
  const nextPath = `${DIR}/DESIGN_v${round}.md`
  log(`revising ${designPath} -> DESIGN_v${round}.md`)
  const changelog = await agent(
    `You are the author of the Giant Fan design. Read ${designPath} IN FULL, then read
${verdictsPath} IN FULL — that is every blocking item the critic panel raised against it.
Also read ${DIR}/ENGINE_GROUND_TRUTH.md, which is AUTHORITATIVE (facts read out of the installed game).

Write ${nextPath}: the next version of the dossier, resolving EVERY blocking item and folding in the
upgrades that genuinely improve it.

Rules:
- VERIFY each critic claim yourself before acting on it. A critic can be wrong. If you reject an
  instruction, keep the original and add "REBUTTED: <aspect> — <why, with evidence>" in a dedicated
  section at the end. Rebut only with evidence, never to save effort.
- ENGINE_GROUND_TRUTH.md outranks both the dossier and the critics. In particular: if the design still
  relies on \`torsionHydros\`, either justify it against §6 (no stock content uses it at all) or switch
  to a mechanism with a stock exemplar and say so.
- Keep everything that was not criticised. This is a revision, not a rewrite.
- Every number derived, with the derivation shown inline. Write and RUN python to check arithmetic;
  put scratch scripts in ${DIR}/.
- The result must be COMPLETE and self-contained — the build is executed straight from it: full
  geometry table, mass table, palette table with exact texture_kit families and verified params, the
  exact JBeam sections, the exact control set, the exact Lua behaviour contract, the exact test list,
  and the beat sheet.
- Read the repo and stock game files yourself: ${REPO}/examples/giant_props, ${REPO}/AGENTS.md,
  ${RECON}/, ${GAME}/content/vehicles/, ${GAME}/lua/vehicle/.
Write the file with the Write tool. Return a one-paragraph changelog of what changed and what you rebutted.`,
    { label: `revise:r${round}`, phase: 'Revise', effort: 'high' })

  if (!changelog) {
    return { wowed: false, reason: `reviser died at round ${round}`, designPath }
  }
  designPath = nextPath
  log(`revise r${round} done`)

  phase('Critique')
  const settled = await parallel(CRITICS.map(c => () =>
    agent(c.prompt.replace('<DESIGN>', designPath) + `\n\nThis is review round ${round}.`,
      { label: `critic:${c.key}:r${round}`, phase: 'Critique', schema: VERDICT, effort: 'high' })
      .then(v => ({ key: c.key, v }))
  ))

  // A DEAD critic is NOT a passing critic. The previous run declared victory on an
  // empty verdict list after every round-3 agent died on a session limit.
  const dead = settled.filter(r => !r || !r.v).map(r => (r && r.key) || 'unknown')
  const verdicts = settled.filter(r => r && r.v).map(r => r.v)
  const unhappy = verdicts.filter(v => !v.wowed)
  log(`round ${round}: ${verdicts.length - unhappy.length}/${CRITICS.length} wowed, ${dead.length} dead (${dead.join(',')})`)

  if (dead.length > 0) {
    return { wowed: false, reason: `critics died, cannot certify: ${dead.join(', ')}`, round, designPath, verdicts }
  }
  if (verdicts.length !== CRITICS.length) {
    return { wowed: false, reason: 'verdict count mismatch', round, designPath, verdicts }
  }
  if (unhappy.length === 0) {
    log(`ALL ${CRITICS.length} CRITICS WOWED at round ${round}`)
    return { wowed: true, round, designPath, verdicts }
  }

  // Persist this round's verdicts for the next reviser.
  const vPath = `${DIR}/VERDICTS_round${round}.md`
  await agent(
    `Write ${vPath}. Its content is a faithful, complete markdown rendering of the JSON below —
one "## <aspect>" section per critic, its one_line verdict, then every blocking item as
"**Bn. title**" / "*Why it fails:*" / "*Instruction:*" / "*Evidence:*", then an "### Upgrades" list.
Do not summarise, editorialise, or drop anything. Use the Write tool.

${JSON.stringify(verdicts)}`,
    { label: `record:r${round}`, phase: 'Critique', effort: 'low' })
  verdictsPath = vPath
}

return { wowed: false, reason: 'ran out of rounds', designPath }
