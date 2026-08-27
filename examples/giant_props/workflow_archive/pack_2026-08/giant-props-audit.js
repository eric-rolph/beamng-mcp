export const meta = {
  name: 'giant-props-audit',
  description: 'Adversarial physics/behaviour audit of the 13 shipped giant-props mods + Cannon Car Wash',
  phases: [
    { title: 'Audit', detail: 'one read-only auditor per shipped mod, against the hard-won engine laws' },
    { title: 'Refute', detail: 'adversarial verifier per mod tries to kill every finding' },
  ],
}

// READ-ONLY workflow. A sibling workflow (giant-props-14-17) is writing NEW mod
// directories in this same repo right now, so nothing here may write, build,
// run Blender, or run the pack pytest - a concurrent build would produce
// spurious failures and a concurrent write would collide.
const READONLY = `
ABSOLUTE CONSTRAINTS - a sibling workflow is concurrently WRITING new mod
directories in this same repository:
- DO NOT edit, create or delete ANY file. This is a read-only audit.
- DO NOT run Blender, build.py, or pytest. The shipped artifacts under
  <mod>/mod/, <mod>/authoring/ and <mod>/dist/ are already built - audit THOSE.
- DO NOT launch BeamNG or touch %LOCALAPPDATA%/BeamNG.
- Bash resets cwd: prefix every Bash call with "cd /c/Users/ericr/beamng-mcp && ".
- Read-only Python one-liners through ./.venv/Scripts/python.exe are encouraged
  (parse jbeam/handoff JSON, diff key sets, count nodes) as long as they write
  nothing. If you need a scratch file, put it under
  C:/Users/ericr/AppData/Local/Temp/claude/C--Users-ericr/01aac343-2951-4984-a938-b549490f7a7b/scratchpad/
  and nowhere else.
- ASCII only in anything you emit.
`

// The bug classes this project has actually paid for, in blood. Every one of
// these was a real shipped defect found by a player or a live probe.
const LAWS = `
## The checklist - these are REAL defect classes this codebase has shipped before

1. NIL BEHAVIOR KEY. Tunables reach the runtime through the BLENDER handoff, not
   spec.py. Extract every \`B.<name>\` the Lua reads and diff it against
   authoring/<MOD_ID>.handoff.json -> behavior.tunables. A key present in
   spec.BEHAVIOR but absent from the shipped handoff is NIL at runtime. (This
   exact bug froze the centrifuge at 500 RPM mid-cycle.) Report every mismatch
   in BOTH directions.
2. VEC3 COERCION. A 3-number list in BEHAVIOR becomes a vec3 in Lua. Indexing it
   (\`B.pos[1]\`) throws every tick. (10,612 log errors on the centrifuge beacon.)
3. UNCAPPED PER-FRAME VELOCITY. Any addSubjectVelocity inside an update loop
   whose magnitude is not clamped is a teleport that shreds a car. Look for a
   per-frame dv cap and a sanity skip for samples already moving absurdly fast.
4. LAUNCH vs ADD SEMANTICS. launchSubject SETS velocity; addSubjectVelocity ADDS.
   Using the wrong one silently changes the mechanic.
5. STALE COLLISION BAKE. A part that MOVES and has collision True must have BOTH
   pose endpoints be surfaces that are safe to leave a stale bake at. A moving
   collision surface that can be left parked across a driving lane is a blocker.
   (Seven geometry builds died on this at the centrifuge mouth.)
6. VERTICAL COLLISION IN A DRIVING LANE. Floors and slopes only. A vertical face
   in the path pops tires and explodes physics nodes.
7. STUCK PHASE. Enumerate the state machine. Every phase needs an exit. Prove a
   wreck parked in a sensor zone, or a subject that despawns mid-cycle, cannot
   pin the machine forever. Look for timeouts, purge paths, and onSubjectGone.
8. RESET COMPLETENESS. behavior.reset must restore every part pose and clear
   every latch. Any b.* field set during a cycle that reset does not clear is a
   cross-run state leak.
9. CONTAINS TRIGGER SIZING. A Contains trigger below 2.9 x 4.5 x 3.0 m cannot
   hold a compact car and will never latch.
10. WORLD FLIP. Authored (x, y) renders at world (-x, -y); jbeam coords are the
    negated authored ones. Any hardcoded coordinate that mixes the two frames is
    a bug (this made three rounds of beacon "verification" photograph empty air).
11. EMISSIVE IS INERT on these props. Any material or comment relying on a
    surface to glow by itself is a lie in the geometry.
12. NONEXISTENT PARTICLE EMITTERS. BNG_exhaust_steam and BNG_Ambient_Dust do NOT
    exist in BeamNG 0.38.6. Any effect naming a missing emitter fails at load.
13. HANDOFF / ARTIFACT INTEGRITY. Do the parts declared in the handoff match the
    exported DAE files on disk? Do the palette materials referenced by the
    generator all exist? Does the jbeam agree with the handoff?
14. DRIVE-IN REACHABILITY. The player drives in; a car that spawns inside a prop
    gets relocated by the engine. Is the entry actually drivable - ramp grades,
    aperture width vs a 2.0 m car, no lip at the threshold?
15. NUMERICAL LANDMINES. normalize() on a possibly-zero vector, division by
    dtSim, unguarded sqrt/acos, angle wrap at +/-180, and per-frame fractions
    that silently compound with framerate (a per-FRAME damping fraction is
    framerate-dependent; a per-SECOND rate is not).
`

const FINDING_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['mod_key', 'headline', 'health', 'findings', 'evidence_run', 'clean_checks'],
  properties: {
    mod_key: { type: 'string' },
    headline: { type: 'string', description: 'one sentence on the state of this mod' },
    health: { type: 'number', description: '0-100, how sound this mod is' },
    evidence_run: {
      type: 'array', items: { type: 'string' },
      description: 'commands you actually ran and what they showed',
    },
    clean_checks: {
      type: 'array', items: { type: 'string' },
      description: 'checklist items you verified and found CLEAN - name them so the absence of a finding is evidence, not silence',
    },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['law', 'severity', 'summary', 'evidence', 'failure_scenario', 'fix'],
        properties: {
          law: { type: 'string', description: 'which checklist number/name, or "other"' },
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'polish'] },
          summary: { type: 'string' },
          evidence: { type: 'string', description: 'file:line or command output PROVING it' },
          failure_scenario: { type: 'string', description: 'concrete inputs/state -> what actually goes wrong in game' },
          fix: { type: 'string' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['mod_key', 'headline', 'confirmed', 'refuted', 'missed'],
  properties: {
    mod_key: { type: 'string' },
    headline: { type: 'string' },
    confirmed: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['severity', 'summary', 'evidence', 'failure_scenario', 'fix'],
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'polish'] },
          summary: { type: 'string' },
          evidence: { type: 'string' },
          failure_scenario: { type: 'string' },
          fix: { type: 'string' },
        },
      },
    },
    refuted: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['summary', 'why_wrong'],
        properties: {
          summary: { type: 'string' },
          why_wrong: { type: 'string', description: 'the evidence that kills this finding' },
        },
      },
    },
    missed: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['severity', 'summary', 'evidence', 'failure_scenario', 'fix'],
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'polish'] },
          summary: { type: 'string' },
          evidence: { type: 'string' },
          failure_scenario: { type: 'string' },
          fix: { type: 'string' },
        },
      },
      description: 'real defects the auditor did not find',
    },
  },
}

const SUBJECTS = [
  { key: 'gforce_centrifuge', note: 'The biggest and most iterated (2545-line spec). Build 123 just shipped a control-panel round: a lowered faceplate, five-segment pose-driven bar graphs, and rewritten adhesion/drag ladders. Scrutinise that new code hardest - it has never been run in game.' },
  { key: 'spin_cycle_washer', note: 'Water fill, floating car, spinning water body - the most unusual physics in the pack.' },
  { key: 'glass_atrium', note: 'Breakable glass panels; framework-level breakage support lives here.' },
  { key: 'spider_web_catcher', note: 'Elastic web catching a car at 200 mph - the highest-energy capture in the pack.' },
  { key: 'giant_toaster', note: 'Deliberately snug 3.0 m slot triggers; a tick-then-POP launch.' },
  { key: 'dino_egg_hatcher', note: 'Full shell fragmentation on hatch.' },
  { key: 'vacuum_of_doom', note: 'A suck zone feeding an exhaust eject - a continuous force field, so check the dv cap hard.' },
  { key: 'pendulum_gauntlet', note: 'Swinging wrecking balls over an inflated-mat bridge; the balls are moving collision.' },
  { key: 'catapult_seesaw', note: 'The canonical compact mod - if the pack has a reference implementation this is it, so hold it to that standard.' },
  { key: 'whale_geyser', note: 'A water column that carries a car upward.' },
  { key: 'boot_of_doom', note: 'A punt; geometry came from a generated 3D model rather than primitives.' },
  { key: 'bouncy_castle', note: 'Soft high-restitution softbody landing zone.' },
  { key: 'monster_flyswatter', note: 'A hovering swatter that slams - a large fast-moving collision part.' },
]

phase('Audit')
const results = await pipeline(
  SUBJECTS,

  (subject) => agent(
    `You are auditing a SHIPPED BeamNG prop mod for latent physics and behaviour defects.
Mod key: "${subject.key}", at C:/Users/ericr/beamng-mcp/examples/giant_props/${subject.key}/.

Context on this particular mod: ${subject.note}

${READONLY}

## Orientation

Read, in this order:
1. C:/Users/ericr/beamng-mcp/AGENTS.md, the "Prop authoring field guide" section and the
   giant-props/centrifuge round notes. This is where the engine laws below come from and it
   is long - skim for the laws, then come back to it when a finding needs backing.
2. examples/giant_props/proplib/lua_kit.py - the runtime the mod's Lua is spliced into.
   Knowing what setPartPose, launchSubject, addSubjectVelocity, firstOccupant and the
   trigger/zone machinery actually DO is what separates a real finding from a guess.
3. The mod itself: spec.py (especially LUA_BEHAVIOR), blender/create_${subject.key}.py, and
   the SHIPPED artifacts under mod/ and authoring/.

${LAWS}

## How to work

Go through the checklist item by item against this mod. Prefer machine checks to reading:
for law 1, actually extract the \`B.<name>\` identifiers with a regex and set-diff them
against the handoff tunables. For law 13, list the DAE files on disk and diff against the
handoff's declared parts. Parse the jbeam by stripping // comments then json.loads.

Every finding needs file:line or command output as EVIDENCE and a concrete
FAILURE SCENARIO - specific inputs or game state leading to a specific wrong outcome. A
finding you cannot evidence does not go in the list; speculation is worse than silence here
because a downstream verifier will spend real effort killing it.

Equally important: record in "clean_checks" every checklist item you verified and found
sound. A clean bill of health that names what was checked is a useful result; one that just
returns an empty list is indistinguishable from not looking.

An adversarial verifier reads your findings next and will try to REFUTE each one.`,
    { label: `audit:${subject.key}`, phase: 'Audit', schema: FINDING_SCHEMA },
  ),

  (audit, subject) => agent(
    `You are an adversarial verifier. An auditor has reported defects in the shipped BeamNG
prop mod "${subject.key}" at C:/Users/ericr/beamng-mcp/examples/giant_props/${subject.key}/.
Your job is to KILL the wrong ones and catch what the auditor missed.

${READONLY}

## The audit you are attacking

${JSON.stringify(audit, null, 2)}

## Your standard

Default to REFUTED. For each finding, go to the actual source and try to prove it wrong:
the guard exists further up the function; the value is clamped by the caller; the phase
does have an exit via onSubjectGone; the key IS in the shipped handoff; the coordinate is
in the authored frame and correctly flipped downstream; that part has collision False so a
stale bake is impossible. Confirm a finding ONLY when you have independently reproduced the
evidence yourself and can state the failure scenario in your own words. If you are unsure,
it is REFUTED.

Read the runtime (examples/giant_props/proplib/lua_kit.py) before ruling on any claim about
Lua helper semantics - several plausible-sounding findings about setPartPose,
launchSubject/addSubjectVelocity and the trigger machinery are wrong for reasons only
visible in the runtime.

Then do your own independent pass for what the auditor MISSED. You have the same checklist:

${LAWS}

Put anything genuinely broken that the auditor did not report into "missed", to the same
evidence standard you are applying to them.`,
    { label: `refute:${subject.key}`, phase: 'Refute', schema: VERDICT_SCHEMA },
  ),
)

const real = results.filter(Boolean)
const blockers = real.flatMap(r => (r.confirmed || []).filter(f => f.severity === 'blocker'))
const majors = real.flatMap(r => (r.confirmed || []).filter(f => f.severity === 'major'))
const missed = real.flatMap(r => r.missed || [])
log(`audited ${real.length}/${SUBJECTS.length} mods -> ${blockers.length} confirmed blockers, ${majors.length} majors, ${missed.length} caught only by the verifier`)
return { perMod: real, totals: { blockers: blockers.length, majors: majors.length, missedByAuditors: missed.length } }
