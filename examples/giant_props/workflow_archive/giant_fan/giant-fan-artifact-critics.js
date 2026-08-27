export const meta = {
  name: 'giant-fan-artifact-critics',
  description: 'Critic panel on the BUILT Giant Fan mod; a fixer applies every blocking item and rebuilds, looping until every critic is utterly wowed',
  phases: [
    { title: 'Critique', detail: '5 aspect critics review the real artifact' },
    { title: 'Fix', detail: 'apply every blocking item, rebuild, re-gate' },
  ],
}

const REPO = 'C:/Users/ericr/beamng-mcp'
const MOD = `${REPO}/examples/giant_props/giant_fan`
const SCRATCH = 'C:/Users/ericr/AppData/Local/Temp/claude/C--Users-ericr-beamng-mcp/dc3b5fb8-2d89-4531-b17e-feb3dab22e68/scratchpad/fan'
const GAME = 'E:/SteamLibrary/steamapps/common/BeamNG.drive'
const BLENDER = 'C:/Users/ericr/Applications/Blender/4.5.4/blender.exe'
const PY = `${REPO}/.venv/Scripts/python.exe`

const VERDICT = {
  type: 'object',
  properties: {
    aspect: { type: 'string' },
    wowed: { type: 'boolean', description: 'TRUE only if the BUILT mod is genuinely astonishing AND correct in your aspect. Default FALSE.' },
    one_line: { type: 'string' },
    blocking: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          why_it_fails: { type: 'string' },
          instruction: { type: 'string', description: 'Exactly what to change in which file. Give replacement numbers/code.' },
          evidence: { type: 'string' },
        },
        required: ['title', 'why_it_fails', 'instruction'],
      },
    },
    upgrades: { type: 'array', items: { type: 'object', properties: { title: { type: 'string' }, instruction: { type: 'string' } }, required: ['title', 'instruction'] } },
  },
  required: ['aspect', 'wowed', 'one_line', 'blocking', 'upgrades'],
}

const COMMON = `
You are reviewing a BUILT BeamNG.drive mod: The Giant Fan. A GALEFORCE GF-3600 three-blade oscillating
table fan scaled 108x with the protective guard CUT OFF, so cars can be thrown into the blades. Each
blade is a city bus long (12.19 m). The rotor is a REAL jbeam \`rotators\` body - the stock large_spinner
mechanism - so cars are wrecked by moving collision geometry at the solver's 2000 Hz, not by a script.

THIS IS NOT A DESIGN REVIEW. The thing exists. Review what is ON DISK:

- ${MOD}/spec.py                          (all authored constants, palette, jbeam sections, the
                                           vehicle controller Lua, the GE behaviour chunk)
- ${MOD}/blender/create_giant_fan.py      (the deterministic generator)
- ${MOD}/mod/vehicles/ericrolph_giant_fan/ericrolph_giant_fan.jbeam    (the BUILT physics)
- ${MOD}/mod/vehicles/ericrolph_giant_fan/main.materials.json
- ${MOD}/mod/vehicles/ericrolph_giant_fan/lua/controller/giantFan.lua  (the BUILT controller)
- ${MOD}/mod/lua/ge/extensions/ericrolph_giant_fan/runtime.lua         (the BUILT GE runtime)
- ${MOD}/authoring/ericrolph_giant_fan.handoff.json
- ${REPO}/tests/test_giant_fan_rotor.py   (30 physics gates, all passing)
- Renders you can READ AS IMAGES: ${SCRATCH}/view_front.jpg, view_side.jpg, view_threequarter.jpg,
  and ${MOD}/authoring/ericrolph_giant_fan_thumbnail.jpg
- Reference material: ${SCRATCH}/ENGINE_GROUND_TRUTH.md (facts read out of the installed game;
  AUTHORITATIVE), ${SCRATCH}/DESIGN_v5.md (the design it was built from - the build deliberately
  TRIMMED invented subsystems the user never asked for: lamp arrays, a scoring scoreboard, streak
  ladders. Do NOT reinstate those; the user asked for a giant fan with power/tilt/sweep.)
- The pack it lives in: ${REPO}/examples/giant_props/ and ${REPO}/AGENTS.md (grep, don't read whole)
- Stock BeamNG for comparison: ${GAME}/content/vehicles/*.zip, ${GAME}/lua/vehicle/

You may RUN things:
  ${PY} -m pytest -q ${REPO}/tests/test_giant_fan_rotor.py
  ${PY} -c "..."   to load spec.py and check arithmetic yourself
  lupa is installed: you can COMPILE AND EXECUTE the built controller Lua against stubbed engine
  globals to prove what it really does. Do that rather than reading it and guessing.

WHAT THE USER ASKED FOR, verbatim: a giant fan mod with power/tilt/sweep; no protective grate so cars
can be launched into it; a collision mesh so vehicles running into it get wrecked the normal way a
vehicle running into a spinning BeamNG prop gets wrecked - real physics interaction; the dial adjusts
power; the back-and-forth sweep is the large button where it normally sits on an oscillating table fan;
each blade the size of a city bus.

YOUR STANDARD: "utterly wowed" means you would be astonished playing this AND can find nothing wrong in
your aspect. Default wowed:false. Do NOT pad the list - every blocking item must be a real defect you
VERIFIED (ran, measured, or cited), not a stylistic preference and not a feature request beyond the
user's ask. If it is genuinely right now, say so and set wowed:true.
`

const CRITICS = [
  { key: 'engine-physics', prompt: `${COMMON}

ASPECT: **BeamNG engine physics and JBeam correctness of the BUILT file.**
Parse the built .jbeam yourself. Check every field of rotators/powertrain/motor/controller/hydros
against the installed engine Lua (wheels.lua, hydros.lua, powertrain/, jbeam/stage2.lua). Check node
masses, beam stiffness vs node mass (stability), the three pin joints actually leaving one DOF, the
rotor group membership, triangle winding and dragCoef, spawn settle, and what the solver will do at
t=0 and at the top setting. COMPILE the controller under lupa and drive it. Recompute every headline
number from the built file, not from spec.py's comments.` },
  { key: 'visual-fidelity', prompt: `${COMMON}

ASPECT: **Visual fidelity and whether it looks glorious.** LOOK AT THE RENDERS (they are readable
images). Compare against a Lasko-pattern white 3-blade oscillating table fan: four-lobed rounded-square
white base, short conical neck, yoke, truncated-cone motor housing, three warm-grey paddle blades widest
outboard, white hub cap with a small chrome-bezel oval badge, recessed taupe dial with 0/3/2/1 clockwise,
eggshell sheen. Check: silhouette and proportions; that every exported object actually carries a
material (parse main.materials.json and the DAE object list); UV texel densities in px/m; the deleted
guard's storytelling (flange, empty bosses, torn stubs, the UV ghost of white shell); and what looks
WRONG at 30 m. Name the one change that would make a player stop and stare.` },
  { key: 'gameplay', prompt: `${COMMON}

ASPECT: **Gameplay and the joke.** Walk the first 90 seconds. Verify by RUNNING the built controller
under lupa: the dial's 0-3-2-1 order, spin-up time, coast-down, the sweep, the tilt rungs. Check the
console is reachable and its hitboxes are where the caps are (parse triggers2 against the node table).
Check what actually happens to a car hit by a 6.5 t blade at 68 m/s, and whether the wind field helps
or annoys. Is there a reason to press play a tenth time? Name the set pieces.` },
  { key: 'pack-conformance', prompt: `${COMMON}

ASPECT: **Repository conformance.** You are the maintainer: would you merge this?
Run the full suite. Check every assertion in tests/test_giant_props_pack.py against this mod; check the
AGENTS.md tombstones (double-sided policy, TWIN-TILING, cut_openings bevel-after-boolean, wheel-reach
node collision, metric UV, ASCII interaction titles, emissiveFactor 3-not-4, palette-lives-in-the-handoff,
AGENTS.md:357 redistribution - confirm NOTHING was copied from BeamNG); determinism (re-run the
generator and diff the handoff); the proplib changes (JBEAM_SECTIONS/VEHICLE_CONTROLLERS/metric_uv on
cone-sphere-torus/type_aspect on stamped_mark) and whether they are safe for the other 22 mods.` },
  { key: 'red-team', prompt: `${COMMON}

ASPECT: **Red team.** Find how this ships broken. Spawn at t=0 with a 33 t free rotor; reset; reload;
two fans on one map; a car between blade and deck, blade and neck, on the hub, in the swept volume as
the sweep rotates in; self-collision where the rotor passes the base; every way the wind field misfires;
sloped spawn against the 2026-08-24 stale-getRotation/quat tombstone; node/beam/triangle budget. Prove
your claims against the BUILT files and the installed engine Lua. Name the single most likely first bug
report.` },
]

const ROUNDS = 3
let round = 1
let verdictsPath = null

while (round <= ROUNDS) {
  phase('Critique')
  const settled = await parallel(CRITICS.map(c => () =>
    agent(c.prompt + `\n\nThis is artifact review round ${round}.` +
      (verdictsPath ? `\n\nThe previous round's verdicts are at ${verdictsPath}. Check the fixes actually landed and are correct; a plausible-looking fix that is still wrong is a blocking item.` : ''),
      { label: `critic:${c.key}:r${round}`, phase: 'Critique', schema: VERDICT, effort: 'high' })
      .then(v => ({ key: c.key, v }))
  ))

  const dead = settled.filter(r => !r || !r.v).map(r => (r && r.key) || 'unknown')
  const verdicts = settled.filter(r => r && r.v).map(r => r.v)
  const unhappy = verdicts.filter(v => !v.wowed)
  log(`round ${round}: ${verdicts.length - unhappy.length}/${CRITICS.length} wowed, ${dead.length} dead`)

  if (dead.length > 0) {
    return { wowed: false, reason: `critics died, cannot certify: ${dead.join(', ')}`, round, verdicts }
  }
  if (unhappy.length === 0) {
    log(`ALL ${CRITICS.length} CRITICS WOWED on the built artifact at round ${round}`)
    return { wowed: true, round, verdicts }
  }
  if (round === ROUNDS) {
    return { wowed: false, reason: 'ran out of rounds', round, verdicts }
  }

  const vPath = `${SCRATCH}/ARTIFACT_VERDICTS_round${round}.md`
  await agent(
    `Write ${vPath}: a faithful, complete markdown rendering of the JSON below - one "## <aspect>"
section per critic, its one_line verdict, then every blocking item as "**Bn. title**" / "*Why it fails:*"
/ "*Instruction:*" / "*Evidence:*", then an "### Upgrades" list. Do not summarise or drop anything.

${JSON.stringify(verdicts)}`,
    { label: `record:r${round}`, phase: 'Critique', effort: 'low' })
  verdictsPath = vPath

  phase('Fix')
  const fixed = await agent(
    `You are the author of The Giant Fan. Read ${vPath} IN FULL: every blocking item the critic panel
raised against the BUILT mod. Fix them.

RULES - these are not negotiable:
- VERIFY each claim yourself before acting. A critic can be wrong. If you reject one, say so in your
  report with evidence, and leave the code alone.
- Do NOT add features the user did not ask for. The user asked for: a giant fan, blades the size of a
  city bus, no grate, real collision that wrecks cars the normal BeamNG way, dial = power, the big
  plunger = oscillating sweep, and tilt. Scoring systems, lamp ladders and streak counters were
  DELIBERATELY trimmed; do not reinstate them.
- Edit ONLY ${MOD}/spec.py and ${MOD}/blender/create_giant_fan.py (and, only if a critic proves a
  defect there, ${REPO}/examples/giant_props/proplib/*.py - that directory is SHARED with 22 other
  mods and three other sessions, so any change must be additive and must leave the whole suite green).
- Never hand-edit anything under ${MOD}/mod/ or the handoff: those are GENERATED. Change the source
  and rebuild.
- After your edits you MUST run, in this order, and all must succeed:
    "${BLENDER}" --factory-startup --background --python ${MOD}/blender/create_giant_fan.py
    ${PY} ${REPO}/examples/giant_props/build.py giant_fan prop
    ${PY} ${REPO}/examples/giant_props/build.py giant_fan dist
    ${PY} -m pytest -q ${REPO}/tests/test_giant_fan_rotor.py ${REPO}/tests/test_giant_props_jbeam_sections.py
    ${PY} -m pytest -q ${REPO}/tests/test_giant_props_pack.py -k "not colossus_tire and not high_five"
  The last command has ONE known pre-existing failure, test_certified_harvest_still_ships_dds
  [pachinko_tower], caused by a different session's texture_kit edit. Everything else must pass.
  If you regressed a gate, fix it before you finish. If you had to change a texture, re-run
  "${PY} ${REPO}/examples/giant_props/build.py giant_fan textures" first.
- If a fix changes the look, re-render and LOOK at it:
    "${BLENDER}" --factory-startup --background --python ${SCRATCH}/diag_views.py
- Add a gate to ${REPO}/tests/test_giant_fan_rotor.py for any defect that a gate would have caught.

Return a report: what you changed, what you rejected and why, and the final output of every command
above.`,
    { label: `fix:r${round}`, phase: 'Fix', effort: 'high' })

  if (!fixed) return { wowed: false, reason: `fixer died at round ${round}`, round }
  round += 1
}
